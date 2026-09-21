#!/usr/bin/env python3
"""Own fresh replay services and a sidecar for Playwright; never reuse ports."""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FAKE = ROOT / "e2e" / "replay_fake.py"
sys.path.insert(0, str(BACKEND / "src"))


LCU_PORT = 23123
LIVE_PORT = 23124
SIDECAR_PORT = 23122
TOKEN = "local-sidecar-development-token-32chars"


def port_answers(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.15)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_port(port: int, process: subprocess.Popen[bytes], label: str) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"{label} exited with {process.returncode}")
        if port_answers(port):
            return
        time.sleep(0.05)
    raise RuntimeError(f"{label} did not bind {port}")


def terminate(processes: list[subprocess.Popen[bytes]]) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and any(p.poll() is None for p in processes):
        time.sleep(0.05)
    for process in reversed(processes):
        if process.poll() is None:
            process.kill()
    for process in processes:
        process.wait()


def seed_champion_cache(data_dir: Path) -> None:
    cache = data_dir / "ddragon" / "ddragon.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(
            {
                "fetched_at": time.time(),
                "champions": {
                    "1": "Annie",
                    "22": "Lucian",
                    "25": "Miss Fortune",
                    "34": "Amumu",
                    "60": "Elise",
                    "117": "Udyr",
                    "238": "Zed",
                    "412": "Thresh",
                    "498": "Xayah",
                    "999": "Replay Champion",
                },
            }
        ),
        encoding="utf-8",
    )

def personal_feature_payload(eligibility: str) -> str:
    features = {
        "cs10": 150.0,
        "level10": 9.5,
        "gold_diff_10": 0.0,
        "team_gold_diff_15m": 0.0,
        "recalls_before_15m": 2.0,
        "avg_banked_gold_at_recall_by_15m": 650.0,
        "avg_banked_gold_at_recall_by_20m": 700.0,
        "unseen_recall_share_by_15m": 0.5,
        "unseen_recall_share_by_20m": 0.5,
        "first_dragon_by_20m_s": 600.0,
        "first_riftherald_by_20m_s": 800.0,
        "first_baron_by_20m_s": 0.0,
        "early_fight_participation_rate": 0.5,
        "plates_taken_by_14m": 7.5,
    }
    return json.dumps(
        {
            "feature_contract_version": "loltrends-parity-v2",
            "personal_history_eligibility": eligibility,
            "features": features,
            "feature_status": {name: "available" for name in features},
            "team_state": {
                "feature": "team_gold_diff_15m",
                "feature_contract_version": "loltrends-parity-v2",
                "team_gold_diff_15m": 0.0,
                "observed_through_s": 1200.0,
                "non_surrendered": eligibility == "eligible",
            },
        },
        allow_nan=False,
        separators=(",", ":"),
    )


def seed_personal_history(data_dir: Path) -> None:
    from bhayanak_legends.store import Store

    store = Store(data_dir / "app.db")
    try:
        store.set_setting("riot_id", "replay#E2E")
        store.set_setting("region_route", "sea")
        generation = store.begin_owner_transition("resolving")
        owner_key = store.activate_owner(
            "fixture-puuid-what-if",
            "replay#E2E",
            "sea",
            generation,
        )
        store.upsert_match(
            "what-if-eligible",
            "2026-03-01T00:00:00Z",
            "16.16",
            "MIDDLE",
            "Ahri",
            False,
            1800,
            personal_feature_payload("eligible"),
            owner_key=owner_key,
        )
        store.upsert_match(
            "what-if-ineligible",
            "2026-02-01T00:00:00Z",
            "16.16",
            "MIDDLE",
            "Ahri",
            False,
            1800,
            personal_feature_payload("ineligible"),
            owner_key=owner_key,
        )
    finally:
        store.close()


def main() -> int:
    occupied = [port for port in (LCU_PORT, LIVE_PORT, SIDECAR_PORT) if port_answers(port)]
    if occupied:
        print(f"replay refuses stale process on configured port(s): {occupied}", file=sys.stderr, flush=True)
        return 23

    temp_dir = Path(tempfile.mkdtemp(prefix="bl-playwright-replay-"))
    lockfile = temp_dir / "lockfile"
    lockfile.write_text(f"ReplayClient:{os.getpid()}:{LCU_PORT}:replay:{'http'}", encoding="utf-8")
    seed_champion_cache(temp_dir)
    seed_personal_history(temp_dir)
    (temp_dir / "replay-import").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "BHAYANAK_LIVE_PATCH": "15.18",
            "BHAYANAK_PORT": str(SIDECAR_PORT),
            "BHAYANAK_TOKEN": TOKEN,
            "BHAYANAK_ALLOW_IMPORT": "1",
            "BHAYANAK_DATA_DIR": str(temp_dir),
            "BHAYANAK_LCU_LOCKFILE": str(lockfile),
            "BHAYANAK_LIVE_CLIENT_DATA_URL": f"http://127.0.0.1:{LIVE_PORT}/liveclientdata/allgamedata",
            "BHAYANAK_IMPORT_ROOTS": json.dumps([str(temp_dir / "replay-import")]),
            "PYTHONUNBUFFERED": "1",
        }
    )
    processes: list[subprocess.Popen[bytes]] = []
    try:
        for kind, port in (("lcu", LCU_PORT), ("live", LIVE_PORT)):
            command = [sys.executable, str(FAKE), "--kind", kind, "--port", str(port)]
            if kind == "lcu":
                command.extend(("--data-dir", str(temp_dir)))
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
            )
            processes.append(process)
            wait_for_port(port, process, f"fake {kind}")

        sidecar = subprocess.Popen(
            ["uv", "run", "python", "-m", "bhayanak_legends.sidecar"],
            cwd=BACKEND,
            env=env,
        )
        processes.append(sidecar)
        wait_for_port(SIDECAR_PORT, sidecar, "sidecar")
        print(json.dumps({"type": "ready", "port": SIDECAR_PORT}), flush=True)

        while True:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("replay process exited unexpectedly")
            time.sleep(0.2)
    except (OSError, RuntimeError) as exc:
        print(f"replay stack failed: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        terminate(processes)
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    raise SystemExit(main())

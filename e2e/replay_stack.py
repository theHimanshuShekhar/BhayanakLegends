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
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FAKE = ROOT / "e2e" / "replay_fake.py"
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
            output = process.stdout.read().decode(errors="replace") if process.stdout is not None else ""
            raise RuntimeError(f"{label} exited with {process.returncode}: {output[-2000:]}")
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
def seed_personal_history(data_dir: Path) -> None:
    seed_dir = data_dir / "replay-import"
    seed_dir.mkdir(parents=True, exist_ok=True)
    fixtures = BACKEND / "tests" / "fixtures"
    details = sorted(fixtures.glob("SG2_*.json"))
    if not details:
        raise RuntimeError("missing committed CI match fixture")
    puuid = None
    for source in details:
        shutil.copy(source, seed_dir / source.name)
        if source.name.endswith("_timeline.json"):
            continue
        payload = json.loads(source.read_text(encoding="utf-8"))
        puuid = puuid or payload["metadata"]["participants"][0]
    (seed_dir / "fetch_state.json").write_text(
        json.dumps({"name": "replay#E2E", "puuid": puuid, "status": "complete"}),
        encoding="utf-8",
    )
    request = urllib.request.Request(
        f"http://127.0.0.1:{SIDECAR_PORT}/dev/import",
        data=json.dumps({"dir": str(seed_dir)}).encode("utf-8"),
        headers={
            "X-BL-Token": TOKEN,
            "Host": f"127.0.0.1:{SIDECAR_PORT}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.status != 200:
            raise RuntimeError(f"CI fixture import failed with {response.status}")


def main() -> int:
    occupied = [port for port in (LCU_PORT, LIVE_PORT, SIDECAR_PORT) if port_answers(port)]
    if occupied:
        print(f"replay refuses stale process on configured port(s): {occupied}", file=sys.stderr, flush=True)
        return 23

    temp_dir = Path(tempfile.mkdtemp(prefix="bl-playwright-replay-"))
    lockfile = temp_dir / "lockfile"
    lockfile.write_text(f"ReplayClient:{os.getpid()}:{LCU_PORT}:replay:{'http'}", encoding="utf-8")
    seed_champion_cache(temp_dir)
    env = os.environ.copy()
    env.update(
        {
            "BHAYANAK_PORT": str(SIDECAR_PORT),
            "BHAYANAK_TOKEN": TOKEN,
            "BHAYANAK_ALLOW_IMPORT": "1",
            "BHAYANAK_DATA_DIR": str(temp_dir),
            "BHAYANAK_LCU_LOCKFILE": str(lockfile),
            "BHAYANAK_LIVE_CLIENT_DATA_URL": f"http://127.0.0.1:{LIVE_PORT}/liveclientdata/allgamedata",
            "BHAYANAK_ALLOW_IMPORT": "1",
            "BHAYANAK_IMPORT_ROOTS": json.dumps([str(temp_dir / "replay-import")]),
            "PYTHONUNBUFFERED": "1",
        }
    )
    processes: list[subprocess.Popen[bytes]] = []
    try:
        for kind, port in (("lcu", LCU_PORT), ("live", LIVE_PORT)):
            process = subprocess.Popen(
                [sys.executable, str(FAKE), "--kind", kind, "--port", str(port)],
                cwd=ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            processes.append(process)
            wait_for_port(port, process, f"fake {kind}")

        sidecar = subprocess.Popen(
            ["uv", "run", "python", "-m", "bhayanak_legends.sidecar"],
            cwd=BACKEND,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(sidecar)
        wait_for_port(SIDECAR_PORT, sidecar, "sidecar")
        seed_personal_history(temp_dir)
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

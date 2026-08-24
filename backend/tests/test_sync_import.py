import asyncio
import json
import shutil
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.sse import Hub
from bhayanak_legends.store import Store
from bhayanak_legends.sync import SyncService

REPO = Path(__file__).resolve().parents[2]
DEV_DIR = REPO / "data" / "dev-import" / "Gankruptcy-DADDY"
# These tests exercise the real import path against gitignored, locally
# downloaded matches. CI runs the same path deterministically through
# tools/ci_seed.py + Playwright instead.
requires_dev_import = pytest.mark.skipif(
    not (DEV_DIR / "fetch_state.json").exists(),
    reason="requires gitignored data/dev-import real-match fixtures",
)
AUTH = {"X-BL-Token": "dev"}
FIRST_FIVE = [
    "SG2_140646556",
    "SG2_140997685",
    "SG2_141207901",
    "SG2_141232486",
    "SG2_141401951",
]
PUUID = "Pi3CECbTWk32o-z4uYe4fr1gH6OEVeex3PHDFcZj3L5tIjrCq3-lqccb0p6oyrUQ0kFJRO349UK9IQ"


def make_import_dir(tmp_path: Path) -> Path:
    target = tmp_path / "import"
    target.mkdir()
    shutil.copy(DEV_DIR / "fetch_state.json", target / "fetch_state.json")
    for match_id in FIRST_FIVE:
        shutil.copy(DEV_DIR / f"{match_id}.json", target / f"{match_id}.json")
        timeline = DEV_DIR / f"{match_id}_timeline.json"
        if timeline.exists():
            shutil.copy(timeline, target / f"{match_id}_timeline.json")
    return target


def build_app(tmp_path: Path):
    config = SidecarConfig(
        port=23110,
        token="dev",
        data_dir=tmp_path / "data",
        pack_dir=REPO / "pack" if (REPO / "pack").exists() else None,
    )
    app = create_app(config)
    return app, TestClient(app)


async def drain(queue: asyncio.Queue) -> list[dict]:
    await asyncio.sleep(0)
    events = []
    while not queue.empty():
        frame = queue.get_nowait()
        events.append(json.loads(frame.removeprefix("data: ")))
    return events


@requires_dev_import
async def test_import_from_dir_end_to_end(tmp_path: Path):
    app, client = build_app(tmp_path)
    svc = app.state.sync_service
    hub = app.state.hub
    queue = hub.subscribe()

    status = await asyncio.to_thread(svc.import_from_dir, make_import_dir(tmp_path), asyncio.get_running_loop())

    assert app.state.store.match_count() == 5
    assert status["state"] == "idle"
    assert status["mode"] == "import"
    assert status["total_queued"] == 5
    assert status["downloaded"] == 5
    assert status["failed"] == 0
    assert app.state.store.get_setting("puuid") == (
        "Pi3CECbTWk32o-z4uYe4fr1gH6OEVeex3PHDFcZj3L5tIjrCq3-lqccb0p6oyrUQ0kFJRO349UK9IQ"
    )
    assert app.state.store.get_setting("sync_mode") == "import"

    envelopes = await drain(queue)
    types = [e["type"] for e in envelopes]
    assert "sync.progress" in types
    assert types[-1] == "sync.done"
    done = envelopes[-1]["data"]
    assert done["downloaded"] == 5

    with client:
        res = client.get("/history/summary", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["matches"] == 5


@requires_dev_import
async def test_import_is_idempotent_on_rerun(tmp_path: Path):
    app, _client = build_app(tmp_path)
    svc = app.state.sync_service
    directory = make_import_dir(tmp_path)

    await asyncio.to_thread(svc.import_from_dir, directory, asyncio.get_running_loop())
    second = await asyncio.to_thread(svc.import_from_dir, directory, asyncio.get_running_loop())

    assert app.state.store.match_count() == 5
    assert second["total_queued"] == 0
    assert second["downloaded"] == 0


@requires_dev_import
def test_dev_import_endpoint_guarded(tmp_path: Path):
    app, client = build_app(tmp_path)
    app.state.config.token = "prod-secret"
    body = {"dir": str(make_import_dir(tmp_path))}
    with client:
        res = client.post("/dev/import", json=body, headers={"X-BL-Token": "dev"})
    assert res.status_code == 403


class FakeRiotClient:
    def __init__(self, detail: dict, timeline: dict) -> None:
        self.detail = detail
        self.timeline_payload = timeline
        self.account_requests: list[str] = []
        self.match_id_requests: list[tuple[str, int]] = []
        self.detail_requests: list[str] = []
        self.timeline_requests: list[str] = []
        self.closed = False

    async def account_by_riot_id(self, riot_id: str) -> dict[str, str]:
        self.account_requests.append(riot_id)
        return {"puuid": PUUID}

    async def match_ids(self, puuid: str, total: int) -> list[str]:
        self.match_id_requests.append((puuid, total))
        return ["SG2_170114893"]

    async def match(self, match_id: str) -> dict:
        self.detail_requests.append(match_id)
        return self.detail

    async def timeline(self, match_id: str) -> dict:
        self.timeline_requests.append(match_id)
        return self.timeline_payload

    async def aclose(self) -> None:
        self.closed = True


def test_http_fetcher_factory_is_callable(tmp_path: Path):
    service = SyncService(
        Store(tmp_path / "app.db"),
        Hub(),
        lambda: {},
    )

    assert callable(service._http_fetcher(object()))


def test_start_is_idempotent_while_backfill_worker_is_running(tmp_path: Path):
    service = SyncService(
        Store(tmp_path / "app.db"),
        Hub(),
        lambda: {
            "riot_key": "test-key",
            "riot_id": "Player#1234",
            "region_route": "sea",
        },
    )
    entered = threading.Event()
    release = threading.Event()

    def blocked_run(_settings: dict) -> None:
        entered.set()
        release.wait(1.0)

    service._run_riot = blocked_run  # type: ignore[method-assign]
    first = service.start()
    assert entered.wait(1.0)
    second = service.start()
    release.set()
    service.shutdown()

    assert first["state"] == "running"
    assert second["state"] == "running"


async def test_riot_backfill_resolves_and_persists_match(tmp_path: Path):
    fixture_dir = Path(__file__).parent / "fixtures"
    fake_client = FakeRiotClient(
        json.loads((fixture_dir / "SG2_170114893.json").read_text()),
        json.loads((fixture_dir / "SG2_170114893_timeline.json").read_text()),
    )
    store = Store(tmp_path / "app.db")
    store.enqueue(["SG2_170114893"], priority=0)
    store.set_setting("puuid", "stale-puuid")
    store.set_setting("puuid_identity", "OldPlayer#9999")
    store.set_setting("puuid_region", "sea")
    hub = Hub()
    queue = hub.subscribe()
    settings = {
        "riot_key": "test-key",
        "riot_id": "Gankruptcy#DADDY",
        "region_route": "sea",
    }
    service = SyncService(
        store,
        hub,
        lambda: settings,
        client_factory=lambda key, route: fake_client,
    )
    service.attach_loop(asyncio.get_running_loop())

    service.start()
    assert service._thread is not None
    await asyncio.to_thread(service._thread.join, 2.0)
    status = service.status()

    assert not service._thread.is_alive()
    assert fake_client.account_requests == ["Gankruptcy#DADDY"]
    assert fake_client.match_id_requests == [
        (
            PUUID,
            1000,
        )
    ]
    assert fake_client.detail_requests == ["SG2_170114893"]
    assert fake_client.timeline_requests == ["SG2_170114893"]
    assert fake_client.closed
    assert store.get_setting("puuid") == PUUID
    assert store.match_count() == 1
    assert store.all_matches()[0]["match_id"] == "SG2_170114893"
    assert status["state"] == "idle"
    assert status["total_queued"] == 1
    assert status["downloaded"] == 1
    assert status["skipped"] == 0
    assert status["failed"] == 0

    events = await drain(queue)
    assert events[-1]["type"] == "sync.done"
    assert events[-1]["data"] == status

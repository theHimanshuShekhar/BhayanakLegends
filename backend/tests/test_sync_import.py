import asyncio
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig

REPO = Path(__file__).resolve().parents[2]
DEV_DIR = REPO / "data" / "dev-import" / "Gankruptcy-DADDY"
AUTH = {"X-BL-Token": "dev"}
FIRST_FIVE = [
    "SG2_140646556",
    "SG2_140997685",
    "SG2_141207901",
    "SG2_141232486",
    "SG2_141401951",
]


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


async def test_import_is_idempotent_on_rerun(tmp_path: Path):
    app, _client = build_app(tmp_path)
    svc = app.state.sync_service
    directory = make_import_dir(tmp_path)

    await asyncio.to_thread(svc.import_from_dir, directory, asyncio.get_running_loop())
    second = await asyncio.to_thread(svc.import_from_dir, directory, asyncio.get_running_loop())

    assert app.state.store.match_count() == 5
    assert second["total_queued"] == 0
    assert second["downloaded"] == 0


def test_dev_import_endpoint_guarded(tmp_path: Path):
    app, client = build_app(tmp_path)
    app.state.config.token = "prod-secret"
    body = {"dir": str(make_import_dir(tmp_path))}
    with client:
        res = client.post("/dev/import", json=body, headers={"X-BL-Token": "dev"})
    assert res.status_code == 403

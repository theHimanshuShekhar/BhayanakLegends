import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fastapi.testclient import TestClient

from bhayanak_legends.app import APP_VERSION, create_app
from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.credentials import InMemoryCredentialStore
from bhayanak_legends.routers_events import event_stream
from bhayanak_legends.sse import Hub

@pytest.fixture
def client(tmp_path: Path):
    config = SidecarConfig(
        port=23110,
        token="test-token-123",
        data_dir=tmp_path / "data",
        pack_dir=None,
    )
    # point pack dir at repo pack/ if present, else tests skip pack-dependent asserts
    repo_pack = Path(__file__).resolve().parents[2] / "pack"
    if repo_pack.exists():
        config.pack_dir = repo_pack
    app = create_app(config, credential_store=InMemoryCredentialStore())
    return TestClient(app)


AUTH = {"X-BL-Token": "test-token-123"}


def test_health_requires_auth(client):
    assert client.get("/health").status_code == 401
    res = client.get("/health", headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["app_version"] == APP_VERSION
    assert "pack_version" in body


def test_requires_token(client):
    assert client.get("/settings").status_code == 401
    bad = {**AUTH, "X-BL-Token": "wrong"}
    assert client.get("/settings", headers=bad).status_code == 401
    assert client.get("/settings", headers=AUTH).status_code == 200

def test_fresh_install_has_empty_riot_identity(client):
    response = client.get("/settings", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["riot_id"] is None


def test_settings_roundtrip(client):
    res = client.put(
        "/settings",
        headers=AUTH,
        json={"riot_id": "SacredButtholio#OOF", "riot_key": "RGAPI-test"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["riot_id"] == "SacredButtholio#OOF"
    assert body["has_key"] is True
    assert "riot_key" not in body

def test_settings_key_delete(client):
    saved = client.put("/settings", headers=AUTH, json={"riot_key": "RGAPI-test"})
    assert saved.status_code == 200
    deleted = client.put("/settings", headers=AUTH, json={"riot_key": None})
    assert deleted.status_code == 200
    assert deleted.json()["has_key"] is False

def test_settings_omitted_fields_preserve_and_nullable_fields_clear(client):
    initial = client.put(
        "/settings",
        headers=AUTH,
        json={
            "riot_id": "Player#1234",
            "region_route": "europe",
            "riot_key": "RGAPI-test",
            "auto_sync": True,
        },
    )
    assert initial.status_code == 200

    preserved = client.put(
        "/settings", headers=AUTH, json={"auto_sync": False}
    )
    assert preserved.status_code == 200
    assert preserved.json() == {
        "riot_id": "Player#1234",
        "region_route": "europe",
        "has_key": True,
        "auto_sync": False,
    }

    cleared = client.put(
        "/settings", headers=AUTH, json={"riot_id": None, "riot_key": None}
    )
    assert cleared.status_code == 200
    assert cleared.json() == {
        "riot_id": None,
        "region_route": "europe",
        "has_key": False,
        "auto_sync": False,
    }


def test_sync_start_rejects_missing_or_invalid_identity(client):
    saved = client.put("/settings", headers=AUTH, json={"riot_key": "RGAPI-test"})
    assert saved.status_code == 200

    missing = client.post("/sync/start", headers=AUTH)
    assert missing.status_code == 400
    assert "riot id" in missing.json()["detail"].lower()

    invalid = client.put("/settings", headers=AUTH, json={"riot_id": "not-an-id"})
    assert invalid.status_code == 200
    rejected = client.post("/sync/start", headers=AUTH)
    assert rejected.status_code == 400
    assert "riot id" in rejected.json()["detail"].lower()


def test_changing_identity_or_region_clears_cached_puuid(client):
    store = client.app.state.store
    store.set_setting("puuid", "stale-puuid")
    changed_id = client.put(
        "/settings", headers=AUTH, json={"riot_id": "Player#1234"}
    )
    assert changed_id.status_code == 200
    assert store.get_setting("puuid") is None

    store.set_setting("puuid", "stale-puuid")
    changed_region = client.put(
        "/settings", headers=AUTH, json={"region_route": "americas"}
    )
    assert changed_region.status_code == 200
    assert store.get_setting("puuid") is None

def test_sync_status_idle_stub(client):
    res = client.get("/sync/status", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["state"] == "idle"

def _startup_app(tmp_path: Path):
    config = SidecarConfig(
        port=23110,
        token="test-token-123",
        data_dir=tmp_path / "data",
        pack_dir=None,
    )
    return create_app(config, credential_store=InMemoryCredentialStore())


def test_auto_sync_startup_schedules_backfill_without_waiting(tmp_path: Path, monkeypatch):
    app = _startup_app(tmp_path)
    app.state.store.set_setting("riot_id", "Player#1234")
    app.state.store.set_setting("region_route", "europe")
    app.state.store.set_setting("auto_sync", "1")
    app.state.credential_store.save("RGAPI-test")
    started: list[bool] = []
    monkeypatch.setattr(app.state.sync_service, "start", lambda: started.append(True))

    with TestClient(app):
        assert started == [True]


def test_auto_sync_startup_skips_disabled_or_incomplete_settings(
    tmp_path: Path, monkeypatch
):
    app = _startup_app(tmp_path)
    app.state.store.set_setting("riot_id", "not-an-id")
    app.state.store.set_setting("auto_sync", "1")
    app.state.credential_store.save("RGAPI-test")
    started: list[bool] = []
    monkeypatch.setattr(app.state.sync_service, "start", lambda: started.append(True))

    with TestClient(app):
        pass

    assert started == []

    app = _startup_app(tmp_path / "disabled")
    app.state.store.set_setting("riot_id", "Player#1234")
    app.state.store.set_setting("auto_sync", "0")
    app.state.credential_store.save("RGAPI-test")
    started = []
    monkeypatch.setattr(app.state.sync_service, "start", lambda: started.append(True))
    with TestClient(app):
        pass
    assert started == []



def test_auto_sync_startup_skips_missing_credential(tmp_path: Path, monkeypatch):
    app = _startup_app(tmp_path)
    app.state.store.set_setting("riot_id", "Player#1234")
    app.state.store.set_setting("auto_sync", "1")
    started: list[bool] = []
    monkeypatch.setattr(app.state.sync_service, "start", lambda: started.append(True))

    with TestClient(app):
        pass

    assert started == []

def test_repeated_startup_hooks_do_not_schedule_duplicate_backfills(
    tmp_path: Path, monkeypatch
):
    app = _startup_app(tmp_path)
    app.state.store.set_setting("riot_id", "Player#1234")
    app.state.store.set_setting("auto_sync", "1")
    app.state.credential_store.save("RGAPI-test")
    started: list[bool] = []
    monkeypatch.setattr(app.state.sync_service, "start", lambda: started.append(True))

    with TestClient(app):
        pass
    with TestClient(app):
        pass

    assert started == [True]


async def test_event_stream_delivers_envelopes():
    hub = Hub()
    queue = hub.subscribe()
    gen = event_stream(hub, queue, "test")

    hello = await gen.__anext__()
    hello_body = json.loads(hello.removeprefix("data: "))
    assert hello_body["type"] == "hello"
    assert hello_body["data"] == {"app_version": "test", "pack_version": None}

    await hub.publish("sync.progress", {"downloaded": 1})
    frame = await asyncio.wait_for(gen.__anext__(), timeout=2)
    envelope = json.loads(frame.removeprefix("data: "))
    assert envelope["type"] == "sync.progress"
    assert envelope["data"]["downloaded"] == 1

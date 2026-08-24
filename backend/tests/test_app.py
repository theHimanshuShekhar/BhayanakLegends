import asyncio
import json
from pathlib import Path

import pytest
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


def test_health_exempt_from_auth(client):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["app_version"] == APP_VERSION


def test_requires_token(client):
    assert client.get("/settings").status_code == 401
    bad = {**AUTH, "X-BL-Token": "wrong"}
    assert client.get("/settings", headers=bad).status_code == 401
    assert client.get("/settings", headers=AUTH).status_code == 200


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


def test_sync_status_idle_stub(client):
    res = client.get("/sync/status", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["state"] == "idle"


async def test_event_stream_delivers_envelopes():
    hub = Hub()
    queue = hub.subscribe()
    gen = event_stream(hub, queue, "test")

    hello = await gen.__anext__()
    assert json.loads(hello.removeprefix("data: "))["type"] == "hello"

    await hub.publish("sync.progress", {"downloaded": 1})
    frame = await asyncio.wait_for(gen.__anext__(), timeout=2)
    envelope = json.loads(frame.removeprefix("data: "))
    assert envelope["type"] == "sync.progress"
    assert envelope["data"]["downloaded"] == 1

import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from fastapi.testclient import TestClient

from bhayanak_legends.app import APP_VERSION, create_app
from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.credentials import InMemoryCredentialStore
from bhayanak_legends.pack import PackError
from bhayanak_legends.routers_events import event_stream
from bhayanak_legends.sse import Hub

@pytest.fixture
def client(tmp_path: Path):
    config = SidecarConfig(
        port=23110,
        token="test-token-123456789012345678901234",
        data_dir=tmp_path / "data",
        pack_dir=None,
    )
    # point pack dir at repo pack/ if present, else tests skip pack-dependent asserts
    repo_pack = Path(__file__).resolve().parents[2] / "pack"
    if repo_pack.exists():
        config.pack_dir = repo_pack
    app = create_app(config, credential_store=InMemoryCredentialStore())
    return TestClient(app)


AUTH = {
    "X-BL-Token": "test-token-123456789012345678901234",
    "Host": "127.0.0.1:23110",
}


def test_health_requires_auth(client):
    assert client.get("/health", headers={"Host": "127.0.0.1:23110"}).status_code == 401
    res = client.get("/health", headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["app_version"] == APP_VERSION
    assert "pack_version" in body



def test_invalid_findings_pack_returns_bounded_503_and_degraded_health(
    client, monkeypatch
):
    invalid_pack = {
        "schema_version": 1,
        "pack_version": "v1",
        "raw_secret": "do-not-leak",
    }
    monkeypatch.setattr(client.app.state.pack, "load", lambda: invalid_pack)

    pack_response = client.get("/pack", headers=AUTH)
    assert pack_response.status_code == 503
    assert pack_response.json() == {"detail": "Findings Pack validation failed"}
    assert "raw_secret" not in pack_response.text
    assert "traceback" not in pack_response.text.lower()

    health_response = client.get("/health", headers=AUTH)
    assert health_response.status_code == 200
    assert health_response.json()["status"] == "degraded"
    assert health_response.json()["pack_version"] is None


def test_unrelated_pack_error_is_not_mapped_to_validation_503(client, monkeypatch):
    def fail_unexpectedly():
        raise RuntimeError("programmer failure")

    monkeypatch.setattr(client.app.state.pack, "load", fail_unexpectedly)

    with pytest.raises(RuntimeError, match="programmer failure"):
        client.get("/pack", headers=AUTH)


def test_pack_load_failure_returns_same_bounded_503(client, monkeypatch):
    def fail_to_load():
        raise PackError("raw pack path and body")

    monkeypatch.setattr(client.app.state.pack, "load", fail_to_load)

    response = client.get("/pack", headers=AUTH)

    assert response.status_code == 503
    assert response.json() == {"detail": "Findings Pack validation failed"}
    assert "raw pack" not in response.text

def test_requires_token(client):
    valid_host = {"Host": "127.0.0.1:23110"}
    assert client.get("/settings", headers=valid_host).status_code == 401
    bad = {**AUTH, "X-BL-Token": "wrong"}
    assert client.get("/settings", headers=bad).status_code == 401
    assert (
        client.get(
            "/events?token=t%C3%B6k%C3%A9n",
            headers=valid_host,
        ).status_code
        == 401
    )
    assert client.get("/settings", headers=AUTH).status_code == 200

def test_fresh_install_has_empty_riot_identity(client):
    response = client.get("/settings", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["riot_id"] is None

@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "127.0.0.1:23110",
        "localhost",
        "LOCALHOST:23110",
        "[::1]",
        "[::1]:23110",
    ],
)
def test_loopback_hosts_are_accepted(client, host):
    response = client.get("/health", headers={"Host": host, "X-BL-Token": AUTH["X-BL-Token"]})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        None,
        "127.0.0.1:80",
        "127.0.0.1:23111",
        "localhost:0",
        "127.0.0.2",
        "example.test",
        "user@localhost",
        "[::1",
        "::1",
        "[::2]",
        "[::1]x",
        "localhost:",
        "localhost:abc",
    ],
)
def test_invalid_hosts_are_rejected_before_token(client, host):
    headers = {"X-BL-Token": AUTH["X-BL-Token"]}
    if host is not None:
        headers["Host"] = host
    response = client.get("/health", headers=headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid host"}


def test_duplicate_hosts_are_rejected(client):
    response = client.request(
        "GET",
        "/health",
        headers=[
            ("Host", "127.0.0.1:23110"),
            ("Host", "localhost:23110"),
            ("X-BL-Token", AUTH["X-BL-Token"]),
        ],
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid host"}


def test_invalid_host_takes_precedence_over_invalid_token(client):
    response = client.get(
        "/health",
        headers={"Host": "example.test", "X-BL-Token": "wrong"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_request_logs_redact_query_and_token(client, caplog):
    secret = AUTH["X-BL-Token"]
    with caplog.at_level("INFO", logger="bhayanak_legends.requests"):
        failed = client.get(
            f"/events?token={secret}-wrong",
            headers={"Host": "127.0.0.1:23110"},
        )
        assert failed.status_code == 401

        async def receive():
            await asyncio.sleep(3600)
            return {"type": "http.disconnect"}

        messages: list[dict] = []
        started = asyncio.Event()

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.start":
                started.set()

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/events",
            "raw_path": b"/events",
            "query_string": f"token={secret}".encode(),
            "headers": [(b"host", b"127.0.0.1:23110")],
            "scheme": "http",
            "server": ("127.0.0.1", 23110),
            "client": ("127.0.0.1", 12345),
            "root_path": "",
            "http_version": "1.1",
        }
        task = asyncio.create_task(client.app(scope, receive, send))
        await asyncio.wait_for(started.wait(), timeout=1)
        assert messages[0]["status"] == 200
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert "/events" in caplog.text
    assert "?token=" not in caplog.text
    assert secret not in caplog.text


@pytest.mark.parametrize("origin", ["http://localhost:1420", "tauri://localhost"])
def test_desktop_cors_origins_remain_allowed(client, origin):
    response = client.options(
        "/health",
        headers={
            "Host": "127.0.0.1:23110",
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin




def test_cors_preflight_rejects_foreign_host(client):
    response = client.options(
        "/health",
        headers={
            "Host": "attacker.example",
            "Origin": "http://localhost:1420",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid host"}
def test_settings_roundtrip(client):
    res = client.put(
        "/settings",
        headers=AUTH,
        json={"riot_id": "FixturePlayer03#BL03", "riot_key": "RGAPI-test"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["riot_id"] == "FixturePlayer03#BL03"
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
        token="test-token-123456789012345678901234",
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

    import time

    with TestClient(app):
        # The startup task runs deferred on the loop; wait bounded so the
        # assertion is deterministic rather than timing-dependent.
        deadline = time.monotonic() + 2.0
        while not started and time.monotonic() < deadline:
            time.sleep(0.01)
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

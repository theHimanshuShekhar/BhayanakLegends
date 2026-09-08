"""App-level release activation transaction tests.

These exercise the production seam in ``app._run_release_channel_check``:
activation is only reported (``pack.updated``, version state) after the
post-activation ``PackStore.reload()`` succeeds, and any failure restores the
previous pack bytes and version reporting. The active pack lives under
``<data_dir>/findings-pack/active`` — the durable activation directory, not a
frozen bundle.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bhayanak_legends.app import APP_VERSION, _run_release_channel_check, create_app
from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.credentials import InMemoryCredentialStore
from bhayanak_legends.pack import PackStore
from bhayanak_legends.release_channel import ReleaseChannel
from pack_fixture_helpers import canonical_model_assets, minimal_pack, model_manifest_pins
from bhayanak_legends.routers_events import event_stream

TEST_PRIVATE_KEY = Ed25519PrivateKey.generate()
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key().public_bytes_raw()


TOKEN = "test-token-123456789012345678901234"
AUTH = {"X-BL-Token": TOKEN, "Host": "127.0.0.1:23110"}


def _asset(*, extra_artifact: bool = False) -> bytes:
    pack = minimal_pack()
    pack["pack_version"] = "v3"
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("findings-pack.v2.json", json.dumps(pack))
        for relative, data in canonical_model_assets(pack).items():
            archive.writestr(relative, data)
        archive.writestr("payload/honest-model.bin", b"model-v3")
        if extra_artifact:
            archive.writestr("payload/added-in-v3.bin", b"brand-new")
    return output.getvalue()


def _app_and_channel(
    tmp_path: Path,
    asset: bytes,
    *,
    manifest_extra: dict | None = None,
) -> tuple[FastAPI, ReleaseChannel]:
    config = SidecarConfig(
        port=23110,
        token=TOKEN,
        data_dir=tmp_path / "data",
        pack_dir=None,  # durable active directory under data_dir
    )
    app = create_app(config, credential_store=InMemoryCredentialStore())
    active = app.state.pack.pack_dir
    assert active == tmp_path / "data" / "findings-pack" / "active"

    canonical = minimal_pack()
    manifest = {
        "pack_version": "v3",
        "schema_version": 2,
        "feature_contract_version": canonical["feature_contracts"]["population"],
        "download_url": "asset.zip",
        "sha256": hashlib.sha256(asset).hexdigest(),
        "size": len(asset),
        "required_model_artifacts": model_manifest_pins(canonical),
        **(manifest_extra or {}),
    }
    raw_manifest = json.dumps(manifest).encode()
    signature = base64.b64encode(TEST_PRIVATE_KEY.sign(raw_manifest))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/manifest.json":
            return httpx.Response(200, content=raw_manifest, request=request)
        if request.url.path == "/manifest.json.sig":
            return httpx.Response(200, content=signature, request=request)
        if request.url.path == "/asset.zip":
            return httpx.Response(200, content=asset, request=request)
        return httpx.Response(404, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = ReleaseChannel(
        active,
        manifest_url="http://127.0.0.1:8080/manifest.json",
        app_version=APP_VERSION,
        client=client,
        allow_loopback_http=True,
        manifest_public_key=TEST_PUBLIC_KEY,
        pack_store=app.state.pack,
    )
    return app, channel


def _drain(queue: asyncio.Queue) -> list[str]:
    frames: list[str] = []
    while True:
        try:
            frames.append(queue.get_nowait())
        except asyncio.QueueEmpty:
            return frames


def _leftovers(app: FastAPI) -> tuple[list[Path], list[Path]]:
    parent = app.state.pack.pack_dir.parent
    return sorted(parent.glob("bl-pack-*")), sorted(parent.glob(".active-rollback-*"))


def _seed_previous_model(active: Path) -> None:
    (active / "payload").mkdir(parents=True, exist_ok=True)
    (active / "payload" / "honest-model.bin").write_bytes(b"model-previous")


async def test_update_publishes_pack_updated_after_reload(tmp_path: Path) -> None:
    app, channel = _app_and_channel(tmp_path, _asset())
    queue = app.state.hub.subscribe()

    await _run_release_channel_check(app, channel)

    frames = [json.loads(frame.removeprefix("data: ")) for frame in _drain(queue)]
    assert [frame["type"] for frame in frames] == ["pack.updated"]
    assert frames[0]["data"] == {"schema_version": 2, "pack_version": "v3"}
    assert app.state.pack_version == "v3"
    temps, rollbacks = _leftovers(app)
    assert not temps and not rollbacks

    health = TestClient(app).get("/health", headers=AUTH)
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["pack_version"] == "v3"


async def test_activated_generation_survives_restart(tmp_path: Path) -> None:
    app, channel = _app_and_channel(tmp_path, _asset())
    previous = app.state.pack.pack_dir

    await _run_release_channel_check(app, channel)

    current = app.state.pack.pack_dir
    assert current != previous
    assert json.loads((previous / "findings-pack.v2.json").read_text())["pack_version"] == "v2"
    assert json.loads((current / "findings-pack.v2.json").read_text())["pack_version"] == "v3"

    restarted = PackStore(app.state.config.resolved_active_pack_dir())
    restarted.initialize()
    assert restarted.version() == "v3"


async def test_corrupt_pointer_recovers_last_successfully_activated_pack(
    tmp_path: Path,
) -> None:
    app, channel = _app_and_channel(tmp_path, _asset())
    logical = app.state.config.resolved_active_pack_dir()

    await _run_release_channel_check(app, channel)
    pointer = logical.parent / f".{logical.name}-pointer"
    pointer.write_text("../uncommitted-generation", encoding="ascii")

    restarted = PackStore(logical)
    restarted.initialize()

    assert restarted.version() == "v3"
    assert json.loads((logical / "findings-pack.v2.json").read_text())["pack_version"] == "v3"


async def test_reload_failure_restores_previous_pack_and_suppresses_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, channel = _app_and_channel(tmp_path, _asset(extra_artifact=True))
    active = app.state.pack.pack_dir
    _seed_previous_model(active)
    original_json = (active / "findings-pack.v2.json").read_bytes()

    bound_reload = app.state.pack.reload
    calls = {"count": 0}

    def flaky_reload() -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated post-activation reload failure")
        bound_reload()

    monkeypatch.setattr(app.state.pack, "reload", flaky_reload)
    queue = app.state.hub.subscribe()

    await _run_release_channel_check(app, channel)

    # No event may escape a failed transaction; prior state is fully restored.
    assert _drain(queue) == []
    assert calls["count"] >= 2
    assert (active / "findings-pack.v2.json").read_bytes() == original_json
    assert (active / "payload" / "honest-model.bin").read_bytes() == b"model-previous"
    assert not (active / "payload" / "added-in-v3.bin").exists()
    assert app.state.pack_version == "v2"
    temps, rollbacks = _leftovers(app)
    assert not temps and not rollbacks

    hello_gen = event_stream(
        app.state.hub,
        app.state.hub.subscribe(),
        app.state.app_version,
        app.state.pack_version,
    )
    hello = json.loads((await hello_gen.__anext__()).removeprefix("data: "))
    assert hello["type"] == "hello"
    assert hello["data"] == {"app_version": APP_VERSION, "pack_version": "v2"}

    client = TestClient(app)
    assert client.get("/health", headers=AUTH).json()["pack_version"] == "v2"
    assert client.get("/pack", headers=AUTH).status_code == 200


async def test_interrupted_artifact_staging_keeps_previous_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, channel = _app_and_channel(tmp_path, _asset())
    active = app.state.pack.pack_dir
    _seed_previous_model(active)
    original_json = (active / "findings-pack.v2.json").read_bytes()

    real_replace = os.replace

    pointer_calls = 0

    def interrupted(source: str | Path, target: str | Path) -> None:
        nonlocal pointer_calls
        if Path(target).name == ".active-pointer":
            pointer_calls += 1
            if pointer_calls == 1:
                raise OSError("simulated interrupted generation setup")
        real_replace(source, target)

    monkeypatch.setattr("bhayanak_legends.release_channel.os.replace", interrupted)
    queue = app.state.hub.subscribe()

    await _run_release_channel_check(app, channel)

    assert _drain(queue) == []
    assert (active / "findings-pack.v2.json").read_bytes() == original_json
    assert (active / "payload" / "honest-model.bin").read_bytes() == b"model-previous"
    assert app.state.pack_version == "v2"
    temps, rollbacks = _leftovers(app)
    assert not temps and not rollbacks


async def test_interrupted_json_commit_keeps_previous_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app, channel = _app_and_channel(tmp_path, _asset())
    active = app.state.pack.pack_dir
    _seed_previous_model(active)
    original_json = (active / "findings-pack.v2.json").read_bytes()

    real_replace = os.replace

    pointer_calls = 0

    def interrupted(source: str | Path, target: str | Path) -> None:
        nonlocal pointer_calls
        if Path(target).name == ".active-pointer":
            pointer_calls += 1
            if pointer_calls == 2:
                raise OSError("simulated interrupted generation commit")
        real_replace(source, target)

    monkeypatch.setattr("bhayanak_legends.release_channel.os.replace", interrupted)
    queue = app.state.hub.subscribe()

    await _run_release_channel_check(app, channel)

    assert _drain(queue) == []
    assert (active / "findings-pack.v2.json").read_bytes() == original_json
    assert (active / "payload" / "honest-model.bin").read_bytes() == b"model-previous"
    assert app.state.pack_version == "v2"
    temps, rollbacks = _leftovers(app)
    assert not temps and not rollbacks


async def test_rejected_candidate_keeps_prior_version_reporting(tmp_path: Path) -> None:
    app, channel = _app_and_channel(
        tmp_path, _asset(), manifest_extra={"schema_version": 1}
    )
    active = app.state.pack.pack_dir
    original_json = (active / "findings-pack.v2.json").read_bytes()
    queue = app.state.hub.subscribe()

    await _run_release_channel_check(app, channel)

    assert _drain(queue) == []
    assert (active / "findings-pack.v2.json").read_bytes() == original_json
    assert app.state.pack_version == "v2"
    temps, rollbacks = _leftovers(app)
    assert not temps and not rollbacks

    client = TestClient(app)
    health = client.get("/health", headers=AUTH)
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["pack_version"] == "v2"

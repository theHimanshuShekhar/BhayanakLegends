"""Release channel tests use an in-process HTTP transport (no GitHub token)."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bhayanak_legends.release_channel import ReleaseChannel

TEST_PRIVATE_KEY = Ed25519PrivateKey.generate()
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key().public_bytes_raw()

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "pack" / "findings-pack.v1.json"
SCHEMA = ROOT / "pack" / "pack.schema.json"


def _asset(tmp_path: Path, *, pack_version: str = "v2", schema_version: int = 1) -> bytes:
    pack = json.loads(PACK.read_text())
    pack["pack_version"] = pack_version
    pack["schema_version"] = schema_version
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("findings-pack.v1.json", json.dumps(pack))
        archive.writestr("pack.schema.json", SCHEMA.read_text())
        archive.writestr("models/honest-model.bin", b"model-v2")
    return output.getvalue()
def _channel(tmp_path: Path, asset: bytes, *, manifest: dict | None = None) -> ReleaseChannel:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir(exist_ok=True)
    (pack_dir / "pack.schema.json").write_bytes(SCHEMA.read_bytes())
    manifest = {
        "pack_version": "v2",
        "schema_version": 1,
        "feature_contract_version": "loltrends-parity-v1",
        "download_url": "asset.zip",
        "sha256": hashlib.sha256(asset).hexdigest(),
        "size": len(asset),
        "required_model_artifacts": [
            {
                "path": "models/honest-model.bin",
                "sha256": hashlib.sha256(b"model-v2").hexdigest(),
            }
        ],
        **(manifest or {}),
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

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return ReleaseChannel(
        tmp_path / "pack",
        manifest_url="http://127.0.0.1:8080/manifest.json",
        app_version="0.1.0",
        client=client,
        allow_loopback_http=True,
        manifest_public_key=TEST_PUBLIC_KEY,
    )


@pytest.fixture
def current_pack(tmp_path: Path) -> Path:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (pack_dir / "findings-pack.v1.json").write_bytes(PACK.read_bytes())
    (pack_dir / "pack.schema.json").write_bytes(SCHEMA.read_bytes())
    return pack_dir


@pytest.mark.asyncio
async def test_no_update_does_not_download(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset)
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert result.reason == "up-to-date"


@pytest.mark.asyncio
async def test_valid_update_activates_and_preserves_artifact_hash(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset)
    result = await channel.check_and_activate("v1")
    assert result.activated
    assert result.pack_version == "v2"
    assert json.loads((tmp_path / "pack" / "findings-pack.v1.json").read_text())["pack_version"] == "v2"
    assert (tmp_path / "pack" / "models" / "honest-model.bin").read_bytes() == b"model-v2"


@pytest.mark.asyncio
async def test_bad_schema_is_rejected(tmp_path: Path) -> None:
    asset = _asset(tmp_path, schema_version=2)
    channel = _channel(tmp_path, asset)
    result = await channel.check_and_activate("v1")
    assert not result.activated
    assert "schema_version" in (result.reason or "")
    assert not (tmp_path / "pack" / "findings-pack.v1.json").exists()


@pytest.mark.asyncio
async def test_incompatible_contract_is_rejected(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset, manifest={"feature_contract_version": "future-v2"})
    result = await channel.check_and_activate("v1")
    assert not result.activated
    assert "contract" in (result.reason or "")


@pytest.mark.asyncio
async def test_corrupt_download_is_rejected(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset)
    manifest = {
        "pack_version": "v2",
        "schema_version": 1,
        "feature_contract_version": "loltrends-parity-v1",
        "download_url": "asset.zip",
        "sha256": hashlib.sha256(asset).hexdigest(),
    }
    raw_manifest = json.dumps(manifest).encode()
    signature = base64.b64encode(TEST_PRIVATE_KEY.sign(raw_manifest))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/manifest.json":
            return httpx.Response(200, content=raw_manifest, request=request)
        if request.url.path == "/manifest.json.sig":
            return httpx.Response(200, content=signature, request=request)
        return httpx.Response(200, content=b"truncated", request=request)

    channel.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await channel.check_and_activate("v1")
    assert not result.activated
    assert "hash mismatch" in (result.reason or "")


@pytest.mark.asyncio
async def test_interrupted_swap_leaves_current_pack_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset)
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir(exist_ok=True)
    old = b"old-pack"
    (pack_dir / "findings-pack.v1.json").write_bytes(old)
    (pack_dir / "pack.schema.json").write_bytes(SCHEMA.read_bytes())
    real_replace = __import__("os").replace

    def interrupted(source: str | Path, target: str | Path) -> None:
        if Path(target).name == "findings-pack.v1.json":
            raise OSError("simulated interrupted swap")
        real_replace(source, target)

    monkeypatch.setattr("bhayanak_legends.release_channel.os.replace", interrupted)
    result = await channel.check_and_activate("v1")
    assert not result.activated
    assert (pack_dir / "findings-pack.v1.json").read_bytes() == old
    assert (pack_dir / "pack.schema.json").read_bytes() == SCHEMA.read_bytes()


@pytest.mark.asyncio
async def test_activation_transaction_can_roll_back_after_reload_failure(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset)
    pack_dir = tmp_path / "pack"
    old_pack = PACK.read_bytes()
    old_artifact = b"model-v1"
    (pack_dir / "findings-pack.v1.json").write_bytes(old_pack)
    (pack_dir / "models").mkdir()
    (pack_dir / "models" / "honest-model.bin").write_bytes(old_artifact)

    result = await channel.check_and_activate("v1", defer_finalize=True)

    assert result.activated
    assert result.activation is not None
    assert (pack_dir / "models" / "honest-model.bin").read_bytes() == b"model-v2"
    result.activation.rollback()
    assert (pack_dir / "findings-pack.v1.json").read_bytes() == old_pack
    assert (pack_dir / "models" / "honest-model.bin").read_bytes() == old_artifact

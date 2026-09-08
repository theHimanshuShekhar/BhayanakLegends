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

from bhayanak_legends.release_channel import (
    COMPRESSED_ASSET_MAX_BYTES,
    EXPANDED_ASSET_MAX_BYTES,
    MANIFEST_MAX_BYTES,
    MAX_ARCHIVE_MEMBERS,
    ReleaseChannel,
    ReleaseChannelError,
    _extract_candidate,
    _manifest,
)
from pack_fixture_helpers import (
    canonical_model_assets,
    minimal_pack,
    model_manifest_pins,
    write_canonical_pack,
)

TEST_PRIVATE_KEY = Ed25519PrivateKey.generate()
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key().public_bytes_raw()

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "pack" / "pack.schema.json"

def _asset(tmp_path: Path, *, pack_version: str = "v3", schema_version: int = 2) -> bytes:
    del tmp_path
    pack = minimal_pack()
    pack["pack_version"] = pack_version
    pack["schema_version"] = schema_version
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("findings-pack.v2.json", json.dumps(pack))
        archive.writestr("pack.schema.json", SCHEMA.read_bytes())
        for relative, data in canonical_model_assets(pack).items():
            archive.writestr(relative, data)
    return output.getvalue()


def _channel(tmp_path: Path, asset: bytes, *, manifest: dict | None = None) -> ReleaseChannel:
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir(exist_ok=True)
    (pack_dir / "pack.schema.json").write_bytes(SCHEMA.read_bytes())
    canonical = minimal_pack()
    manifest = {
        "pack_version": "v3",
        "schema_version": 2,
        "feature_contract_version": canonical["feature_contracts"]["population"],
        "download_url": "asset.zip",
        "sha256": hashlib.sha256(asset).hexdigest(),
        "size": len(asset),
        "required_model_artifacts": model_manifest_pins(canonical),
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
    write_canonical_pack(pack_dir, minimal_pack())
    return pack_dir


@pytest.mark.asyncio
async def test_no_update_does_not_download(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset)
    result = await channel.check_and_activate("v3")
    assert not result.activated
    assert result.reason == "up-to-date"


@pytest.mark.asyncio
async def test_valid_update_activates_and_preserves_artifact_hash(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset)
    result = await channel.check_and_activate("v2")
    assert result.activated
    assert result.pack_version == "v3"
    active = channel.pack_dir
    assert json.loads((active / "findings-pack.v2.json").read_text())["pack_version"] == "v3"

    for relative, expected in canonical_model_assets().items():
        assert (active / relative).read_bytes() == expected

@pytest.mark.asyncio
async def test_bad_schema_is_rejected(tmp_path: Path) -> None:
    asset = _asset(tmp_path, schema_version=1)
    channel = _channel(tmp_path, asset)
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "schema_version" in (result.reason or "")
    assert not (tmp_path / "pack" / "findings-pack.v2.json").exists()


@pytest.mark.asyncio
async def test_incompatible_contract_is_rejected(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset, manifest={"feature_contract_version": "future-v2"})
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "contract" in (result.reason or "")


@pytest.mark.asyncio
async def test_corrupt_download_is_rejected(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset)
    manifest = {
        "pack_version": "v3",
        "schema_version": 2,
        "feature_contract_version": "loltrends-population-v2",
        "download_url": "asset.zip",
        "sha256": hashlib.sha256(asset).hexdigest(),
        "size": len(b"truncated"),
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
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "hash mismatch" in (result.reason or "")


@pytest.mark.asyncio
async def test_interrupted_swap_leaves_current_pack_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset)
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir(exist_ok=True)
    old = b"old-pack"
    (pack_dir / "findings-pack.v2.json").write_bytes(old)
    (pack_dir / "pack.schema.json").write_bytes(SCHEMA.read_bytes())
    real_replace = __import__("os").replace

    def interrupted(source: str | Path, target: str | Path) -> None:
        if Path(target).name == ".pack-pointer":
            raise OSError("simulated interrupted pointer swap")
        real_replace(source, target)

    monkeypatch.setattr("bhayanak_legends.release_channel.os.replace", interrupted)
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert (pack_dir / "findings-pack.v2.json").read_bytes() == old
    assert (pack_dir / "pack.schema.json").read_bytes() == SCHEMA.read_bytes()


@pytest.mark.asyncio
async def test_activation_transaction_can_roll_back_after_reload_failure(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    channel = _channel(tmp_path, asset)
    pack_dir = tmp_path / "pack"
    old_pack = json.dumps(minimal_pack(), separators=(",", ":")).encode()
    old_artifact = b"previous-model"
    primary_model_path = model_manifest_pins(minimal_pack())[0]["path"]
    (pack_dir / "findings-pack.v2.json").write_bytes(old_pack)
    (pack_dir / primary_model_path).parent.mkdir(parents=True, exist_ok=True)
    (pack_dir / primary_model_path).write_bytes(old_artifact)

    result = await channel.check_and_activate("v2", defer_finalize=True)

    assert result.activated
    assert result.activation is not None
    active = channel.pack_dir
    assert (
        (active / primary_model_path).read_bytes()
        == canonical_model_assets()[primary_model_path]
    )
    result.activation.rollback()
    assert (pack_dir / "findings-pack.v2.json").read_bytes() == old_pack
    assert (pack_dir / primary_model_path).read_bytes() == old_artifact


def _manifest_base(asset: bytes) -> dict:
    return {
        "pack_version": "v3",
        "schema_version": 2,
        "feature_contract_version": minimal_pack()["feature_contracts"]["population"],
        "download_url": "asset.zip",
        "sha256": hashlib.sha256(asset).hexdigest(),
        "size": len(asset),
    }


def _asset_padded_to(tmp_path: Path, target: int) -> bytes:
    """A stored (uncompressed) zip padded to exactly ``target`` bytes."""
    del tmp_path
    pack = minimal_pack()
    pack["pack_version"] = "v3"
    assets = canonical_model_assets(pack)
    pad = target
    for _ in range(16):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("findings-pack.v2.json", json.dumps(pack))
            archive.writestr("pack.schema.json", SCHEMA.read_bytes())
            for relative, data in assets.items():
                archive.writestr(relative, data)
            if pad > 0:
                archive.writestr("padding.bin", b"\0" * pad)
        size = output.getbuffer().nbytes
        if size == target:
            return output.getvalue()
        pad -= size - target
        if pad < 0:
            break
    pytest.fail("unable to pad release asset to the exact boundary size")


def _asset_with_file_entries(count: int) -> bytes:
    pack = minimal_pack()
    pack["pack_version"] = "v3"
    assets = canonical_model_assets(pack)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("findings-pack.v2.json", json.dumps(pack))
        archive.writestr("pack.schema.json", SCHEMA.read_bytes())
        for relative, data in assets.items():
            archive.writestr(relative, data)
        base_members = 2 + len(assets)
        for index in range(count - base_members):
            archive.writestr(f"pad-{index:05}.bin", b"x")
    return output.getvalue()


def _zeros_zip(total: int) -> bytes:
    """A deflated zip whose single member expands to exactly ``total`` bytes."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        with archive.open("big.bin", "w") as payload:
            remaining = total
            chunk = b"\0" * (1024 * 1024)
            while remaining > 0:
                step = min(remaining, len(chunk))
                payload.write(chunk[:step])
                remaining -= step
    return output.getvalue()


def _blob(path: Path, total: int) -> None:
    chunk = b"0" * (1024 * 1024)
    with path.open("wb") as stream:
        remaining = total
        while remaining > 0:
            step = min(remaining, len(chunk))
            stream.write(chunk[:step])
            remaining -= step


def _assert_no_leftovers(tmp_path: Path) -> None:
    assert not list(tmp_path.glob("bl-pack-*"))
    assert not list(tmp_path.glob(".pack-rollback-*"))


@pytest.mark.asyncio
async def test_manifest_without_declared_size_is_refused(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    manifest = _manifest_base(asset)
    # The channel helper fills its default size back in when the key is
    # merely absent; an explicit null is what a missing field decodes to.
    manifest["size"] = None
    channel = _channel(tmp_path, asset, manifest=manifest)
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "declared" in (result.reason or "")
    assert not (tmp_path / "pack" / "findings-pack.v2.json").exists()
    _assert_no_leftovers(tmp_path)


def test_manifest_rejects_invalid_declared_sizes() -> None:
    base = {
        "pack_version": "v3",
        "schema_version": 2,
        "feature_contract_version": "loltrends-population-v2",
        "download_url": "asset.zip",
        "sha256": "a" * 64,
    }
    url = "https://127.0.0.1:8/manifest.json"
    for bad in (True, -1, "64"):
        with pytest.raises(ReleaseChannelError, match="declared"):
            _manifest({**base, "size": bad}, url)
    boundary = _manifest({**base, "size": COMPRESSED_ASSET_MAX_BYTES}, url)
    assert boundary.size == COMPRESSED_ASSET_MAX_BYTES


@pytest.mark.asyncio
async def test_manifest_declaring_over_cap_size_is_refused(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    manifest = {
        **_manifest_base(asset),
        "size": COMPRESSED_ASSET_MAX_BYTES + 1,
    }
    channel = _channel(tmp_path, asset, manifest=manifest)
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "limit" in (result.reason or "")
    assert not (tmp_path / "pack" / "findings-pack.v2.json").exists()
    _assert_no_leftovers(tmp_path)


@pytest.mark.asyncio
async def test_download_at_exact_64mib_boundary_is_eligible(tmp_path: Path) -> None:
    asset = _asset_padded_to(tmp_path, COMPRESSED_ASSET_MAX_BYTES)
    assert len(asset) == COMPRESSED_ASSET_MAX_BYTES
    channel = _channel(tmp_path, asset)
    result = await channel.check_and_activate("v2")
    active = channel.pack_dir
    assert json.loads((active / "findings-pack.v2.json").read_text())["pack_version"] == "v3"
    assert result.pack_version == "v3"
    _assert_no_leftovers(tmp_path)


@pytest.mark.asyncio
async def test_streaming_without_content_length_stops_at_first_byte_over_cap(
    tmp_path: Path,
) -> None:
    asset = _asset_padded_to(tmp_path, COMPRESSED_ASSET_MAX_BYTES)
    pack_dir = tmp_path / "pack"
    write_canonical_pack(pack_dir, minimal_pack())
    previous_pack = (pack_dir / "findings-pack.v2.json").read_bytes()
    primary_model_path = model_manifest_pins(minimal_pack())[0]["path"]
    (pack_dir / primary_model_path).write_bytes(b"model-previous")

    async def one_mib_chunks():
        payload = asset + b"\0"  # exactly one byte over the declared cap
        for index in range(0, len(payload), 1024 * 1024):
            yield payload[index : index + (1024 * 1024)]

    manifest = _manifest_base(asset)  # declares exactly the 64 MiB cap
    raw_manifest = json.dumps(manifest).encode()
    signature = base64.b64encode(TEST_PRIVATE_KEY.sign(raw_manifest))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/manifest.json":
            return httpx.Response(200, content=raw_manifest, request=request)
        if request.url.path == "/manifest.json.sig":
            return httpx.Response(200, content=signature, request=request)
        if request.url.path == "/asset.zip":
            # Async generator body: no content-length header reaches the client.
            return httpx.Response(200, content=one_mib_chunks(), request=request)
        return httpx.Response(404, request=request)

    channel = _channel(tmp_path, asset)
    channel.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "exceeds" in (result.reason or "")
    assert (pack_dir / "findings-pack.v2.json").read_bytes() == previous_pack
    assert (pack_dir / primary_model_path).read_bytes() == b"model-previous"
    _assert_no_leftovers(tmp_path)


@pytest.mark.asyncio
async def test_false_content_length_header_is_rejected(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    manifest = _manifest_base(asset)
    raw_manifest = json.dumps(manifest).encode()
    signature = base64.b64encode(TEST_PRIVATE_KEY.sign(raw_manifest))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/asset.zip":
            return httpx.Response(
                200,
                content=asset,
                headers={"content-length": str(len(asset) - 1)},
                request=request,
            )
        if request.url.path == "/manifest.json":
            return httpx.Response(200, content=raw_manifest, request=request)
        if request.url.path == "/manifest.json.sig":
            return httpx.Response(200, content=signature, request=request)
        return httpx.Response(404, request=request)

    channel = _channel(tmp_path, asset)
    channel.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "does not match manifest" in (result.reason or "")
    assert not (tmp_path / "pack" / "findings-pack.v2.json").exists()
    _assert_no_leftovers(tmp_path)


@pytest.mark.asyncio
async def test_short_body_with_matching_header_is_truncated(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    manifest = _manifest_base(asset)
    raw_manifest = json.dumps(manifest).encode()
    signature = base64.b64encode(TEST_PRIVATE_KEY.sign(raw_manifest))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/asset.zip":
            return httpx.Response(
                200,
                content=asset[:-1],
                headers={"content-length": str(len(asset))},
                request=request,
            )
        if request.url.path == "/manifest.json":
            return httpx.Response(200, content=raw_manifest, request=request)
        if request.url.path == "/manifest.json.sig":
            return httpx.Response(200, content=signature, request=request)
        return httpx.Response(404, request=request)

    channel = _channel(tmp_path, asset)
    channel.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "truncated" in (result.reason or "")
    assert not (tmp_path / "pack" / "findings-pack.v2.json").exists()
    _assert_no_leftovers(tmp_path)


@pytest.mark.asyncio
async def test_zip_with_exactly_1024_entries_is_eligible(tmp_path: Path) -> None:
    asset = _asset_with_file_entries(MAX_ARCHIVE_MEMBERS)
    channel = _channel(tmp_path, asset)
    result = await channel.check_and_activate("v2")
    assert result.activated
    assert result.pack_version == "v3"
    _assert_no_leftovers(tmp_path)


@pytest.mark.asyncio
async def test_zip_with_1025_entries_is_rejected(tmp_path: Path) -> None:
    asset = _asset_with_file_entries(MAX_ARCHIVE_MEMBERS + 1)
    channel = _channel(tmp_path, asset)
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "too many file members" in (result.reason or "")
    assert not (tmp_path / "pack" / "findings-pack.v2.json").exists()
    _assert_no_leftovers(tmp_path)


def test_zip_expanded_bytes_at_exact_boundary_extracts(tmp_path: Path) -> None:
    download = tmp_path / "download.zip"
    download.write_bytes(_zeros_zip(EXPANDED_ASSET_MAX_BYTES))
    destination = tmp_path / "candidate"
    _extract_candidate(download, destination)
    written = sum(path.stat().st_size for path in destination.rglob("*") if path.is_file())
    assert written == EXPANDED_ASSET_MAX_BYTES


def test_zip_over_expanded_limit_is_rejected_before_extraction(tmp_path: Path) -> None:
    download = tmp_path / "download.zip"
    download.write_bytes(_zeros_zip(EXPANDED_ASSET_MAX_BYTES + 1))
    destination = tmp_path / "candidate"
    with pytest.raises(ReleaseChannelError, match="expanded size limit"):
        _extract_candidate(download, destination)
    assert not [path for path in destination.rglob("*") if path.is_file()]


@pytest.mark.asyncio
async def test_plain_json_asset_with_available_models_is_rejected(tmp_path: Path) -> None:
    pack = minimal_pack()
    pack["pack_version"] = "v3"
    asset = json.dumps(pack).encode()
    manifest = _manifest_base(asset)
    manifest["required_model_artifacts"] = []
    channel = _channel(tmp_path, asset, manifest=manifest)
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "model artifact" in (result.reason or "")
    assert not (tmp_path / "pack" / "findings-pack.v2.json").exists()
    _assert_no_leftovers(tmp_path)


def test_json_asset_at_exact_expanded_boundary_extracts(tmp_path: Path) -> None:
    download = tmp_path / "download.json"
    _blob(download, EXPANDED_ASSET_MAX_BYTES)
    destination = tmp_path / "candidate"
    _extract_candidate(download, destination)
    assert (destination / "findings-pack.v2.json").stat().st_size == EXPANDED_ASSET_MAX_BYTES


def test_json_asset_over_expanded_limit_is_rejected(tmp_path: Path) -> None:
    download = tmp_path / "download.json"
    _blob(download, EXPANDED_ASSET_MAX_BYTES + 1)
    destination = tmp_path / "candidate"
    with pytest.raises(ReleaseChannelError, match="exceeds expanded size limit"):
        _extract_candidate(download, destination)


def test_archive_traversal_members_are_rejected(tmp_path: Path) -> None:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("../evil.bin", b"x")
        archive.writestr("/absolute.bin", b"x")
    download = tmp_path / "download.zip"
    download.write_bytes(output.getvalue())
    destination = tmp_path / "candidate"
    with pytest.raises(ReleaseChannelError, match="unsafe path"):
        _extract_candidate(download, destination)
    assert not (tmp_path / "evil.bin").exists()
    assert not (tmp_path / "absolute.bin").exists()


@pytest.mark.asyncio
async def test_corrupt_zip_member_is_rejected_gracefully(tmp_path: Path) -> None:
    pack = minimal_pack()
    pack["pack_version"] = "v3"
    assets = canonical_model_assets(pack)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("findings-pack.v2.json", json.dumps(pack))
        archive.writestr("pack.schema.json", SCHEMA.read_bytes())
        for relative, data in assets.items():
            archive.writestr(relative, data)
    raw = bytearray(output.getvalue())
    model_bytes = next(data for path, data in assets.items() if path.endswith(".onnx"))
    raw[raw.index(model_bytes)] ^= 0xFF  # break the member's CRC-32
    asset = bytes(raw)
    channel = _channel(tmp_path, asset)
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "CRC" in (result.reason or "")
    assert not (tmp_path / "pack" / "findings-pack.v2.json").exists()
    _assert_no_leftovers(tmp_path)


@pytest.mark.asyncio
async def test_wrong_artifact_hash_is_rejected(tmp_path: Path) -> None:
    asset = _asset(tmp_path)
    pins = model_manifest_pins(minimal_pack())
    wrong_pin = dict(pins[0])
    wrong_pin["sha256"] = "0" * 64
    manifest = {
        **_manifest_base(asset),
        "required_model_artifacts": [*pins, wrong_pin],
    }
    channel = _channel(tmp_path, asset, manifest=manifest)
    result = await channel.check_and_activate("v2")
    assert not result.activated
    assert "hash mismatch" in (result.reason or "")
    assert not (tmp_path / "pack" / "findings-pack.v2.json").exists()
    _assert_no_leftovers(tmp_path)


@pytest.mark.asyncio
async def test_github_latest_direct_cdn_redirect_is_pinned_by_metadata(
    tmp_path: Path,
) -> None:
    latest_url = (
        "https://github.com/acme/project/releases/latest/download/findings-pack-manifest.json"
    )
    tag_lookup_url = "https://github.com/acme/project/releases/latest"
    tag_url = (
        "https://github.com/acme/project/releases/download/v3.4.5/"
        "findings-pack-manifest.json"
    )
    cdn_url = (
        "https://release-assets.githubusercontent.com/github-production-release-asset/"
        "acme/project/123/findings-pack-manifest.json?X-Amz-Signature=fixture"
    )
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url) == latest_url:
            return httpx.Response(302, headers={"location": cdn_url}, request=request)
        if str(request.url) == tag_lookup_url:
            return httpx.Response(
                302,
                headers={"location": "/acme/project/releases/tag/v3.4.5"},
                request=request,
            )
        if str(request.url) == cdn_url:
            return httpx.Response(200, content=b"signed-manifest", request=request)
        return httpx.Response(404, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = ReleaseChannel(tmp_path / "pack")
    fetched = await channel._fetch_bytes(
        client,
        latest_url,
        limit=MANIFEST_MAX_BYTES,
        label="release manifest",
    )
    await client.aclose()

    assert fetched.logical_url == tag_url
    assert fetched.transfer_url == cdn_url
    assert fetched.body == b"signed-manifest"
    assert seen == [latest_url, tag_lookup_url, cdn_url]


@pytest.mark.asyncio
async def test_github_latest_direct_cdn_redirect_requires_valid_metadata(
    tmp_path: Path,
) -> None:
    latest_url = "https://github.com/acme/project/releases/latest/download/asset.zip"
    tag_lookup_url = "https://github.com/acme/project/releases/latest"
    cdn_url = (
        "https://release-assets.githubusercontent.com/github-production-release-asset/"
        "acme/project/123/asset.zip?X-Amz-Signature=fixture"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == latest_url:
            return httpx.Response(302, headers={"location": cdn_url}, request=request)
        if str(request.url) == tag_lookup_url:
            return httpx.Response(
                302,
                headers={"location": "https://github.com/other/project/releases/tag/v3.4.5"},
                request=request,
            )
        raise AssertionError(f"unexpected request: {request.url}")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = ReleaseChannel(tmp_path / "pack")
    with pytest.raises(ReleaseChannelError, match="tag"):
        await channel._fetch_bytes(
            client,
            latest_url,
            limit=COMPRESSED_ASSET_MAX_BYTES,
            label="release asset",
        )
    await client.aclose()


@pytest.mark.asyncio
async def test_github_cdn_cannot_be_used_as_an_unpinned_start(
    tmp_path: Path,
) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"untrusted", request=request)
        )
    )
    channel = ReleaseChannel(tmp_path / "pack")
    with pytest.raises(ReleaseChannelError, match="cannot start"):
        await channel._fetch_bytes(
            client,
            "https://release-assets.githubusercontent.com/arbitrary/asset.zip",
            limit=COMPRESSED_ASSET_MAX_BYTES,
            label="release asset",
        )
    await client.aclose()

"""Raw manifest authentication and release transport policy tests."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bhayanak_legends.manifest_signing import ManifestSignatureError, verify_manifest_signature
from bhayanak_legends.release_channel import ReleaseChannel

TEST_PRIVATE_KEY = Ed25519PrivateKey.generate()
TEST_PUBLIC_KEY = TEST_PRIVATE_KEY.public_key().public_bytes_raw()


def _signature(raw: bytes) -> bytes:
    return base64.b64encode(TEST_PRIVATE_KEY.sign(raw))

def test_valid_signature_authenticates_exact_bytes() -> None:
    raw = b'{"pack_version":"v2"}'
    verify_manifest_signature(raw, _signature(raw), public_key=TEST_PUBLIC_KEY)


def test_test_key_is_not_the_production_key() -> None:
    raw = b'{"pack_version":"v2"}'
    with pytest.raises(ManifestSignatureError, match="invalid"):
        verify_manifest_signature(raw, _signature(raw))


def test_tampered_bytes_are_rejected() -> None:
    raw = b'{"pack_version":"v2"}'
    with pytest.raises(ManifestSignatureError, match="invalid"):
        verify_manifest_signature(raw + b" ", _signature(raw), public_key=TEST_PUBLIC_KEY)


def test_malformed_signature_is_rejected_before_json_decoding() -> None:
    with pytest.raises(ManifestSignatureError, match="malformed"):
        verify_manifest_signature(b"not json at all", b"not-a-signature")


async def _channel(
    tmp_path: Path,
    raw_manifest: bytes,
    signature: bytes,
    *,
    url: str = "https://release.test/manifest.json",
    allow_loopback_http: bool = False,
    routes: dict[str, httpx.Response] | None = None,
) -> tuple[ReleaseChannel, list[str]]:
    requests: list[str] = []
    routes = routes or {}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/manifest.json":
            return httpx.Response(200, content=raw_manifest, request=request)
        if request.url.path == "/manifest.json.sig":
            return httpx.Response(200, content=signature, request=request)
        return routes.get(request.url.path, httpx.Response(404, request=request))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return (
        ReleaseChannel(
            tmp_path / "pack",
            manifest_url=url,
            client=client,
            allow_loopback_http=allow_loopback_http,
            manifest_public_key=TEST_PUBLIC_KEY,
        ),
        requests,
    )


def _manifest(*, asset: str = "asset.zip") -> bytes:
    return json.dumps(
        {
            "pack_version": "v2",
            "schema_version": 1,
            "feature_contract_version": "loltrends-parity-v1",
            "download_url": asset,
            "sha256": "0" * 64,
        },
        separators=(",", ":"),
    ).encode()


@pytest.mark.asyncio
async def test_invalid_signature_does_not_parse_or_download_asset(tmp_path: Path) -> None:
    raw = b"not valid json"
    channel, requests = await _channel(tmp_path, raw, b"bad")
    result = await channel.check_and_activate()
    assert not result.activated
    assert "signature" in (result.reason or "")
    assert requests == ["/manifest.json", "/manifest.json.sig"]


@pytest.mark.asyncio
async def test_manifest_cap_rejects_first_byte_over_limit(tmp_path: Path) -> None:
    raw = b"{" + b"a" * (256 * 1024) + b"}"
    channel, requests = await _channel(tmp_path, raw, _signature(raw))
    result = await channel.check_and_activate()
    assert not result.activated
    assert "262144" in (result.reason or "")
    assert requests == ["/manifest.json"]


@pytest.mark.asyncio
async def test_signature_cap_rejects_first_byte_over_limit(tmp_path: Path) -> None:
    raw = _manifest()
    channel, requests = await _channel(tmp_path, raw, b"x" * (16 * 1024 + 1))
    result = await channel.check_and_activate()
    assert not result.activated
    assert "signature" in (result.reason or "")
    assert requests == ["/manifest.json", "/manifest.json.sig"]


@pytest.mark.asyncio
async def test_http_non_loopback_is_rejected_before_request(tmp_path: Path) -> None:
    raw = _manifest()
    channel, requests = await _channel(
        tmp_path,
        raw,
        _signature(raw),
        url="http://release.test/manifest.json",
    )
    result = await channel.check_and_activate()
    assert not result.activated
    assert "HTTPS" in (result.reason or "")
    assert requests == []


@pytest.mark.asyncio
async def test_cross_origin_asset_is_rejected_before_download(tmp_path: Path) -> None:
    raw = _manifest(asset="https://other.test/asset.zip")
    channel, requests = await _channel(tmp_path, raw, _signature(raw))
    result = await channel.check_and_activate()
    assert not result.activated
    assert "relative" in (result.reason or "")
    assert requests == ["/manifest.json", "/manifest.json.sig"]


@pytest.mark.asyncio
async def test_loopback_redirect_cannot_escape_loopback(tmp_path: Path) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/manifest.json":
            return httpx.Response(302, headers={"location": "https://release.test/manifest.json"}, request=request)
        return httpx.Response(404, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel = ReleaseChannel(
        tmp_path / "pack",
        manifest_url="http://127.0.0.1:8080/manifest.json",
        client=client,
        allow_loopback_http=True,
    )
    result = await channel.check_and_activate()
    assert not result.activated
    assert "host" in (result.reason or "")
    assert len(requests) == 1

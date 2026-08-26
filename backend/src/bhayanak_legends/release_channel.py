"""Findings Pack release channel.

The release channel is deliberately independent from the GitHub client.  A public
manifest describes a pack asset and its compatibility; the client downloads into
a temporary directory, validates every declared input, then replaces only the
pack payload as one final filesystem operation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
import urllib.parse
import zipfile
from typing import Any
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import httpx

from .pack import PackError, validate_pack_directory

from .manifest_signing import (
    PINNED_MANIFEST_PUBLIC_KEY,
    ManifestSignatureError,
    verify_manifest_signature,
)

MANIFEST_MAX_BYTES = 256 * 1024
COMPRESSED_ASSET_MAX_BYTES = 64 * 1024 * 1024
EXPANDED_ASSET_MAX_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1024
SIGNATURE_MAX_BYTES = 16 * 1024
MAX_REDIRECTS = 8

log = logging.getLogger(__name__)

DEFAULT_MANIFEST_URL = (
    "https://github.com/theHimanshuShekhar/BhayanakLegends/"
    "releases/latest/download/findings-pack-manifest.json"
)
FEATURE_CONTRACT_VERSION = "loltrends-parity-v1"
PACK_FILENAME = "findings-pack.v1.json"
SCHEMA_FILENAME = "pack.schema.json"


class ReleaseChannelError(RuntimeError):
    """A release was unavailable or failed pre-activation validation."""

@dataclass(frozen=True)
class ReleaseResult:
    activated: bool
    pack_version: str | None
    schema_version: int | None = None
    reason: str | None = None
    activation: ActivationTransaction | None = None


@dataclass(frozen=True)
class ReleaseManifest:
    pack_version: str
    schema_version: int
    feature_contract_version: str
    download_url: str
    sha256: str
    size: int | None
    required_model_artifacts: tuple[dict[str, str], ...]
    min_app_version: str | None
    max_app_version: str | None


def _version_key(version: str) -> tuple[Any, ...]:
    """Return a comparable key for release versions (``v1.2.3`` included)."""
    value = version.strip()
    if value.startswith(("v", "V")):
        value = value[1:]
    parts: list[Any] = []
    for part in re.split(r"[.\-_+]", value):
        if part.isdigit():
            parts.append((0, int(part)))
        else:
            parts.append((1, part.lower()))
    return tuple(parts) or ((0, 0),)


def is_newer_version(candidate: str, current: str | None) -> bool:
    """Compare pack versions without assuming a particular release tag format."""
    return current is None or _version_key(candidate) > _version_key(current)


def _read_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _effective_port(parsed: urllib.parse.ParseResult) -> int | None:
    if parsed.port is not None:
        return parsed.port
    return {"http": 80, "https": 443}.get(parsed.scheme)


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urllib.parse.urlparse(url)
    return (parsed.scheme.lower(), (parsed.hostname or "").lower(), _effective_port(parsed))


def _url_from_manifest(manifest: dict[str, Any], base_url: str) -> str:
    asset = manifest.get("asset")
    asset = asset if isinstance(asset, dict) else {}
    value = (
        manifest.get("download_url")
        or manifest.get("asset_url")
        or manifest.get("url")
        or asset.get("download_url")
        or asset.get("url")
    )
    if not isinstance(value, str) or not value:
        raise ReleaseChannelError("release manifest has no download URL")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme or parsed.netloc:
        raise ReleaseChannelError("release asset URL must be relative")
    resolved = urllib.parse.urljoin(base_url, value)
    if _origin(resolved) != _origin(base_url):
        raise ReleaseChannelError("release asset URL must match manifest origin")
    return resolved


def _signature_url(manifest_url: str) -> str:
    parsed = urllib.parse.urlparse(manifest_url)
    return urllib.parse.urlunparse(parsed._replace(path=f"{parsed.path}.sig"))


def _artifact_specs(value: Any) -> tuple[dict[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ReleaseChannelError("required_model_artifacts must be a list")
    result: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str):
            result.append({"path": item})
            continue
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ReleaseChannelError("invalid required model artifact declaration")
        entry = {"path": item["path"]}
        if item.get("sha256") is not None:
            if not isinstance(item["sha256"], str):
                raise ReleaseChannelError("invalid model artifact hash")
            entry["sha256"] = item["sha256"].lower()
        result.append(entry)
    return tuple(result)


def _manifest(raw: Any, base_url: str) -> ReleaseManifest:
    if not isinstance(raw, dict):
        raise ReleaseChannelError("release manifest must be an object")
    asset = raw.get("asset")
    asset = asset if isinstance(asset, dict) else {}
    pack_version = raw.get("pack_version") or raw.get("version")
    if not isinstance(pack_version, str) or not pack_version.strip():
        raise ReleaseChannelError("release manifest has no pack version")
    schema_version = raw.get("schema_version", 1)
    if not isinstance(schema_version, int):
        raise ReleaseChannelError("release manifest schema_version must be an integer")
    contract = raw.get("feature_contract_version")
    if not isinstance(contract, str):
        raise ReleaseChannelError("release manifest has no feature contract version")
    sha = raw.get("sha256") or raw.get("sha") or asset.get("sha256") or asset.get("sha")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", sha):
        raise ReleaseChannelError("release manifest has no valid asset sha256")
    # Transport/URL policy is validated before size accounting so a
    # policy-violating manifest is never reported as a size problem.
    download_url = _url_from_manifest(raw, base_url)
    size = raw.get("size", asset.get("size"))
    # A missing declared size would let an unbounded body negotiate the cap
    # away, so the manifest must declare a non-negative integer byte size.
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ReleaseChannelError(
            "release manifest requires a declared non-negative integer asset size"
        )
    if size > COMPRESSED_ASSET_MAX_BYTES:
        raise ReleaseChannelError(
            f"release manifest size exceeds {COMPRESSED_ASSET_MAX_BYTES} byte limit"
        )
    compatibility = raw.get("app_compatibility")
    if compatibility is not None and not isinstance(compatibility, dict):
        raise ReleaseChannelError("app_compatibility must be an object")
    compatibility = compatibility or {}
    min_app = raw.get("min_app_version", compatibility.get("min_version"))
    max_app = raw.get("max_app_version", compatibility.get("max_version"))
    for value in (min_app, max_app):
        if value is not None and not isinstance(value, str):
            raise ReleaseChannelError("app compatibility versions must be strings")
    return ReleaseManifest(
        pack_version=pack_version.strip(),
        schema_version=schema_version,
        feature_contract_version=contract,
        download_url=download_url,
        sha256=sha.lower(),
        size=size,
        required_model_artifacts=_artifact_specs(
            raw.get("required_model_artifacts", raw.get("required_artifacts"))
        ),
        min_app_version=min_app,
        max_app_version=max_app,
    )


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ReleaseChannelError("release archive contains an unsafe path")
    return path

def _extract_candidate(download: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(download):
        with zipfile.ZipFile(download) as archive:
            files: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            declared_total = 0
            for info in archive.infolist():
                path = _safe_member(info.filename)
                if not path.parts or info.is_dir():
                    continue
                if info.file_size < 0:
                    raise ReleaseChannelError("release archive has an invalid member size")
                files.append((info, path))
                declared_total += info.file_size
                if len(files) > MAX_ARCHIVE_MEMBERS:
                    raise ReleaseChannelError("release archive has too many file members")
                if declared_total > EXPANDED_ASSET_MAX_BYTES:
                    raise ReleaseChannelError("release archive exceeds expanded size limit")

            written_total = 0
            for info, path in files:
                target = destination.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as sink:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        if not chunk:
                            continue
                        written_total += len(chunk)
                        if written_total > EXPANDED_ASSET_MAX_BYTES:
                            raise ReleaseChannelError("release archive exceeds expanded size limit")
                        sink.write(chunk)
        return
    # A plain JSON asset is useful for a tiny release and for local/offline tests.
    target = destination / PACK_FILENAME
    if download.stat().st_size > EXPANDED_ASSET_MAX_BYTES:
        raise ReleaseChannelError("release JSON exceeds expanded size limit")
    written = 0
    with download.open("rb") as source, target.open("wb") as sink:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            if not chunk:
                continue
            written += len(chunk)
            if written > EXPANDED_ASSET_MAX_BYTES:
                raise ReleaseChannelError("release JSON exceeds expanded size limit")
            sink.write(chunk)


def _validate_candidate(
    directory: Path,
    release: ReleaseManifest,
    *,
    app_version: str,
    schema_path: Path | None,
) -> dict[str, Any]:
    pack_path = directory / PACK_FILENAME
    if not pack_path.exists():
        raise ReleaseChannelError(f"release is missing {PACK_FILENAME}")
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseChannelError(f"release pack is not valid JSON: {exc}") from exc
    if not isinstance(pack, dict):
        raise ReleaseChannelError("release pack must be an object")
    if pack.get("schema_version") != release.schema_version:
        raise ReleaseChannelError("release schema_version does not match its manifest")
    if pack.get("schema_version") != 1:
        raise ReleaseChannelError(f"unsupported pack schema_version {pack.get('schema_version')}")
    pack_version = pack.get("pack_version")
    if pack_version is not None and pack_version != release.pack_version:
        raise ReleaseChannelError("release pack_version does not match its manifest")
    provenance = pack.get("provenance")
    if not isinstance(provenance, dict):
        raise ReleaseChannelError("release pack has no provenance")
    contracts = {row.get("feature_contract_version") for row in provenance.values() if isinstance(row, dict)}
    if release.feature_contract_version != FEATURE_CONTRACT_VERSION or contracts != {FEATURE_CONTRACT_VERSION}:
        raise ReleaseChannelError("release feature contract is incompatible")
    if release.min_app_version and _version_key(app_version) < _version_key(release.min_app_version):
        raise ReleaseChannelError("release requires a newer app")
    if release.max_app_version and _version_key(app_version) > _version_key(release.max_app_version):
        raise ReleaseChannelError("release is not compatible with this app")
    selected_schema = schema_path or (directory / SCHEMA_FILENAME)
    artifact_specs = tuple(
        (
            directory / _safe_member(artifact["path"]),
            artifact.get("sha256"),
        )
        for artifact in release.required_model_artifacts
    )
    try:
        return validate_pack_directory(
            directory,
            schema_path=selected_schema,
            required_model_artifacts=artifact_specs,
        )
    except PackError as exc:
        raise ReleaseChannelError(f"release pack failed validation: {exc}") from exc

class ActivationTransaction:
    """Retain activation backups until the new pack has been reloaded."""

    def __init__(
        self,
        rollback_dir: Path,
        changed: list[tuple[Path, Path | None]],
    ) -> None:
        self._rollback_dir = rollback_dir
        self._changed = changed
        self._closed = False

    def finalize(self) -> None:
        if self._closed:
            return
        shutil.rmtree(self._rollback_dir, ignore_errors=False)
        self._closed = True

    def rollback(self) -> None:
        if self._closed:
            return
        first_error: OSError | None = None
        for target, backup in reversed(self._changed):
            try:
                if backup is not None and backup.exists():
                    os.replace(backup, target)
                elif target.exists():
                    target.unlink()
            except OSError as exc:
                first_error = first_error or exc
        try:
            shutil.rmtree(self._rollback_dir, ignore_errors=False)
        except OSError as exc:
            first_error = first_error or exc
        self._closed = True
        if first_error is not None:
            raise first_error


class ReleaseChannel:
    """Download and activate a compatible Findings Pack release."""

    def __init__(
        self,
        pack_dir: Path,
        *,
        manifest_url: str = DEFAULT_MANIFEST_URL,
        app_version: str = "0.1.0",
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
        allow_loopback_http: bool = False,
        manifest_public_key: bytes | None = None,
    ) -> None:
        self.pack_dir = Path(pack_dir)
        self.manifest_url = manifest_url
        self.app_version = app_version
        self.timeout = timeout
        self.client = client
        self.allow_loopback_http = allow_loopback_http
        self.manifest_public_key = manifest_public_key

    def _validate_transport_url(
        self,
        url: str,
        *,
        label: str,
        expected_origin: tuple[str, str, int | None] | None = None,
    ) -> urllib.parse.ParseResult:
        try:
            parsed = urllib.parse.urlparse(url)
            host = (parsed.hostname or "").lower()
            port = _effective_port(parsed)
        except ValueError as exc:
            raise ReleaseChannelError(f"{label} URL is invalid") from exc
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            raise ReleaseChannelError(f"{label} URL is invalid")
        loopback = host == "127.0.0.1"
        if parsed.scheme != "https" and not (self.allow_loopback_http and loopback):
            raise ReleaseChannelError(f"{label} must use HTTPS")
        if expected_origin is not None:
            expected_scheme, expected_host, expected_port = expected_origin
            if host != expected_host:
                raise ReleaseChannelError(f"{label} redirect changed host")
            if port != expected_port:
                raise ReleaseChannelError(f"{label} redirect changed origin")
            if (
                parsed.scheme != expected_scheme
                and (expected_host != "127.0.0.1" or not self.allow_loopback_http)
            ):
                raise ReleaseChannelError(f"{label} redirect changed origin")
        return parsed

    async def _fetch_bytes(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        limit: int,
        label: str,
    ) -> tuple[str, bytes]:
        parsed = self._validate_transport_url(url, label=label)
        expected_origin = _origin(url)
        current = urllib.parse.urlunparse(parsed)
        for _ in range(MAX_REDIRECTS + 1):
            self._validate_transport_url(current, label=label, expected_origin=expected_origin)
            async with client.stream("GET", current, follow_redirects=False) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ReleaseChannelError(f"{label} redirect has no location")
                    current = urllib.parse.urljoin(current, location)
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise ReleaseChannelError(f"{label} request failed") from exc
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes(64 * 1024):
                    if chunk:
                        total += len(chunk)
                        if total > limit:
                            raise ReleaseChannelError(f"{label} exceeds {limit} byte limit")
                        chunks.append(chunk)
                final_url = str(response.url)
                self._validate_transport_url(final_url, label=label, expected_origin=expected_origin)
                return final_url, b"".join(chunks)
        raise ReleaseChannelError(f"{label} has too many redirects")

    async def check_and_activate(
        self,
        current_version: str | None = None,
        *,
        defer_finalize: bool = False,
    ) -> ReleaseResult:
        """Check the public manifest and activate only a newer valid candidate."""
        transaction: ActivationTransaction | None = None
        try:
            async with self._client_context() as client:
                manifest_response_url, raw_manifest = await self._fetch_bytes(
                    client,
                    self.manifest_url,
                    limit=MANIFEST_MAX_BYTES,
                    label="release manifest",
                )
                signature_url = _signature_url(manifest_response_url)
                _, raw_signature = await self._fetch_bytes(
                    client,
                    signature_url,
                    limit=SIGNATURE_MAX_BYTES,
                    label="release manifest signature",
                )
                try:
                    verify_manifest_signature(
                        raw_manifest,
                        raw_signature,
                        public_key=self.manifest_public_key or PINNED_MANIFEST_PUBLIC_KEY,
                    )
                except ManifestSignatureError as exc:
                    raise ReleaseChannelError(str(exc)) from exc
                try:
                    raw_manifest_json = json.loads(raw_manifest.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ReleaseChannelError(f"release manifest is not valid JSON: {exc}") from exc
                release = _manifest(raw_manifest_json, manifest_response_url)
                if not is_newer_version(release.pack_version, current_version):
                    return ReleaseResult(False, current_version, release.schema_version, "up-to-date")
                with tempfile.TemporaryDirectory(prefix="bl-pack-", dir=self.pack_dir.parent) as temporary:
                    temp_root = Path(temporary)
                    download = temp_root / "download"
                    await self._download(
                        client,
                        release.download_url,
                        download,
                        release.size,
                        expected_origin=_origin(manifest_response_url),
                    )
                    if _read_sha256(download) != release.sha256:
                        raise ReleaseChannelError("release asset hash mismatch")
                    candidate = temp_root / "candidate"
                    _extract_candidate(download, candidate)
                    pack = _validate_candidate(
                        candidate,
                        release,
                        app_version=self.app_version,
                        schema_path=self.pack_dir / SCHEMA_FILENAME,
                    )
                    transaction = self._activate(candidate)
                if transaction is not None and not defer_finalize:
                    transaction.finalize()
                    transaction = None
                return ReleaseResult(
                    True,
                    release.pack_version,
                    pack["schema_version"],
                    "activated",
                    transaction,
                )
        except (
            httpx.HTTPError,
            OSError,
            zipfile.BadZipFile,
            ReleaseChannelError,
            json.JSONDecodeError,
        ) as exc:
            if transaction is not None:
                transaction.rollback()
            log.warning("Findings Pack release check failed: %s", exc)
            return ReleaseResult(False, current_version, None, str(exc))

    def _client_context(self):
        if self.client is not None:
            return _ExistingClientContext(self.client)
        return httpx.AsyncClient(timeout=httpx.Timeout(self.timeout), follow_redirects=False)

    async def _download(
        self,
        client: httpx.AsyncClient,
        url: str,
        target: Path,
        expected_size: int,
        *,
        expected_origin: tuple[str, str, int | None],
    ) -> None:
        if expected_size < 0 or expected_size > COMPRESSED_ASSET_MAX_BYTES:
            raise ReleaseChannelError("release asset size is outside the allowed limit")
        current = url
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            for _ in range(MAX_REDIRECTS + 1):
                self._validate_transport_url(current, label="release asset", expected_origin=expected_origin)
                async with client.stream("GET", current, follow_redirects=False) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise ReleaseChannelError("release asset redirect has no location")
                        current = urllib.parse.urljoin(current, location)
                        continue
                    try:
                        response.raise_for_status()
                    except httpx.HTTPError as exc:
                        raise ReleaseChannelError("release asset request failed") from exc
                    content_length = response.headers.get("content-length")
                    if content_length is not None:
                        try:
                            declared_length = int(content_length)
                        except ValueError as exc:
                            raise ReleaseChannelError("release asset content length is invalid") from exc
                        if declared_length != expected_size:
                            raise ReleaseChannelError("release asset size does not match manifest")
                        if declared_length > COMPRESSED_ASSET_MAX_BYTES:
                            raise ReleaseChannelError("release asset exceeds size limit")
                    written = 0
                    with target.open("wb") as stream:
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            if not chunk:
                                continue
                            written += len(chunk)
                            if written > COMPRESSED_ASSET_MAX_BYTES or written > expected_size:
                                raise ReleaseChannelError("release asset exceeds declared size limit")
                            stream.write(chunk)
                    if written != expected_size:
                        raise ReleaseChannelError("release asset was truncated")
                    self._validate_transport_url(
                        str(response.url),
                        label="release asset",
                        expected_origin=expected_origin,
                    )
                    return
            raise ReleaseChannelError("release asset has too many redirects")
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def _activate(self, candidate: Path) -> ActivationTransaction:
        """Replace the active pack with an already-validated candidate.

        Artifacts stage first; the pack JSON swap is the single commit point.
        Backups live in a sibling rollback directory until the caller finalizes
        the transaction after a successful reload.
        """
        self.pack_dir.mkdir(parents=True, exist_ok=True)

        rollback_dir = Path(
            tempfile.mkdtemp(prefix=f".{self.pack_dir.name}-rollback-", dir=self.pack_dir.parent)
        )
        changed: list[tuple[Path, Path | None]] = []
        transaction = ActivationTransaction(rollback_dir, changed)
        staged_pack = candidate / PACK_FILENAME
        target_pack = self.pack_dir / PACK_FILENAME
        try:
            # Artifacts are staged first. The JSON is the commit point: readers
            # see either the old validated pack or the complete new pack.
            for source in candidate.rglob("*"):
                if not source.is_file() or source.name == PACK_FILENAME:
                    continue
                relative = source.relative_to(candidate)
                target = self.pack_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                backup: Path | None = None
                if target.exists():
                    backup = rollback_dir / relative
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                changed.append((target, backup))
                os.replace(source, target)

            if not staged_pack.is_file():
                raise ReleaseChannelError(f"release is missing {PACK_FILENAME}")
            backup = None
            if target_pack.exists():
                backup = rollback_dir / PACK_FILENAME
                shutil.copy2(target_pack, backup)
            changed.append((target_pack, backup))
            os.replace(staged_pack, target_pack)
        except Exception:
            transaction.rollback()
            raise
        return transaction

    async def __aexit__(self, *args: object) -> None:
        return None


class _ExistingClientContext:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.client

    async def __aexit__(self, *args: object) -> None:
        return None


__all__ = [
    "DEFAULT_MANIFEST_URL",
    "FEATURE_CONTRACT_VERSION",
    "ReleaseChannel",
    "ReleaseChannelError",
    "ReleaseManifest",
    "ReleaseResult",
    "is_newer_version",
]

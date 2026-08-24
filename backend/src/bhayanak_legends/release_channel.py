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
import jsonschema

from .models import FindingsPack

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
    return urllib.parse.urljoin(base_url, value)


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
    size = raw.get("size", asset.get("size"))
    if size is not None and (not isinstance(size, int) or size < 0):
        raise ReleaseChannelError("release manifest size must be a non-negative integer")
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
        download_url=_url_from_manifest(raw, base_url),
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
            for info in archive.infolist():
                path = _safe_member(info.filename)
                if not path.parts or info.is_dir():
                    continue
                target = destination.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as sink:
                    shutil.copyfileobj(source, sink)
        return
    # A plain JSON asset is useful for a tiny release and for local/offline tests.
    target = destination / PACK_FILENAME
    shutil.copyfile(download, target)


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
    if not selected_schema.exists():
        raise ReleaseChannelError(f"release is missing {SCHEMA_FILENAME}")
    try:
        schema = json.loads(selected_schema.read_text(encoding="utf-8"))
        jsonschema.validate(pack, schema)
        FindingsPack.model_validate(pack)
    except (OSError, json.JSONDecodeError, jsonschema.SchemaError, jsonschema.ValidationError, ValueError) as exc:
        raise ReleaseChannelError(f"release pack failed validation: {exc}") from exc
    for artifact in release.required_model_artifacts:
        artifact_path = directory / _safe_member(artifact["path"])
        if not artifact_path.is_file():
            raise ReleaseChannelError(f"release is missing model artifact {artifact['path']}")
        expected = artifact.get("sha256")
        if expected and _read_sha256(artifact_path) != expected:
            raise ReleaseChannelError(f"model artifact hash mismatch: {artifact['path']}")
    return pack


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
    ) -> None:
        self.pack_dir = Path(pack_dir)
        self.manifest_url = manifest_url
        self.app_version = app_version
        self.timeout = timeout
        self.client = client

    async def check_and_activate(self, current_version: str | None = None) -> ReleaseResult:
        """Check the public manifest and activate only a newer valid candidate."""
        try:
            async with self._client_context() as client:
                response = await client.get(self.manifest_url)
                response.raise_for_status()
                raw_manifest = response.json()
                release = _manifest(raw_manifest, str(response.url))
                if not is_newer_version(release.pack_version, current_version):
                    return ReleaseResult(False, current_version, release.schema_version, "up-to-date")
                with tempfile.TemporaryDirectory(prefix="bl-pack-", dir=self.pack_dir.parent) as temporary:
                    temp_root = Path(temporary)
                    download = temp_root / "download"
                    await self._download(client, release.download_url, download, release.size)
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
                    self._activate(candidate)
                return ReleaseResult(True, release.pack_version, pack["schema_version"], "activated")
        except (httpx.HTTPError, OSError, ReleaseChannelError, json.JSONDecodeError) as exc:
            log.warning("Findings Pack release check failed: %s", exc)
            return ReleaseResult(False, current_version, None, str(exc))

    def _client_context(self):
        if self.client is not None:
            return _ExistingClientContext(self.client)
        return httpx.AsyncClient(timeout=httpx.Timeout(self.timeout), follow_redirects=True)

    async def _download(self, client: httpx.AsyncClient, url: str, target: Path, expected_size: int | None) -> None:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if expected_size is not None and content_length and int(content_length) != expected_size:
                raise ReleaseChannelError("release asset size does not match manifest")
            written = 0
            with target.open("wb") as stream:
                async for chunk in response.aiter_bytes(1024 * 1024):
                    if chunk:
                        stream.write(chunk)
                        written += len(chunk)
            if expected_size is not None and written != expected_size:
                raise ReleaseChannelError("release asset was truncated")

    def _activate(self, candidate: Path) -> None:
        self.pack_dir.mkdir(parents=True, exist_ok=True)
        staged_pack = candidate / PACK_FILENAME
        target_pack = self.pack_dir / PACK_FILENAME
        changed: list[tuple[Path, Path | None]] = []
        rollback = candidate.parent / "rollback"
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
                    backup = rollback / relative
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)
                os.replace(source, target)
                changed.append((target, backup))
            os.replace(staged_pack, target_pack)
        except Exception:
            # An interrupted final replace must not leave old pack metadata
            # paired with new model bytes.
            for target, backup in reversed(changed):
                if backup is not None and backup.exists():
                    os.replace(backup, target)
                elif target.exists():
                    target.unlink()
            raise

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

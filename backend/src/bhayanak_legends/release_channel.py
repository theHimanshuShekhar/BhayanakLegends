"""Findings Pack release channel.

The release channel is deliberately independent from the GitHub client. A public
manifest describes a pack asset and its compatibility; the client downloads into
a temporary directory, validates every declared input, then hands the complete
candidate to PackStore for atomic generation activation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import os
import posixpath
import re
import tempfile
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
from pydantic import ValidationError

from .manifest_signing import (
    PINNED_MANIFEST_PUBLIC_KEY,
    ManifestSignatureError,
    verify_manifest_signature,
)
from .pack import PackActivationTransaction, PackError, PackStore, validate_pack_directory
from .pack_v2 import EXECUTABLE_MODEL_KEYS, FindingsPackV2
from .version import APP_VERSION

MANIFEST_MAX_BYTES = 256 * 1024
COMPRESSED_ASSET_MAX_BYTES = 64 * 1024 * 1024
EXPANDED_ASSET_MAX_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 1024
SIGNATURE_MAX_BYTES = 16 * 1024
MAX_REDIRECTS = 8

GITHUB_HOST = "github.com"
GITHUB_CDN_HOST = "release-assets.githubusercontent.com"
_GITHUB_LATEST_RE = re.compile(
    r"^(?P<repo>/[^/]+/[^/]+)/releases/latest/download/(?P<asset>[^/]+)$"
)
_GITHUB_TAGGED_RE = re.compile(
    r"^(?P<repo>/[^/]+/[^/]+)/releases/download/(?P<tag>[^/]+)/(?P<asset>[^/]+)$"
)
_GITHUB_LATEST_TAG_RE = re.compile(
    r"^(?P<repo>/[^/]+/[^/]+)/releases/tag/(?P<tag>[^/]+)$"
)

log = logging.getLogger(__name__)

DEFAULT_MANIFEST_URL = (
    "https://github.com/theHimanshuShekhar/BhayanakLegends/"
    "releases/latest/download/findings-pack-manifest.json"
)
PACK_FILENAME = "findings-pack.v2.json"
SCHEMA_FILENAME = "pack.schema.json"


@dataclass(frozen=True)
class _FetchResult:
    """Bytes plus the logical URL used to resolve sibling release assets."""

    logical_url: str
    transfer_url: str
    body: bytes


@dataclass(frozen=True)
class _TransportPolicy:
    """The immutable-origin policy for one resource fetch."""

    origin: tuple[str, str, int | None]
    initial_url: str
    github_repo: str | None = None
    github_asset: str | None = None
    github_latest: bool = False



class ReleaseChannelError(RuntimeError):
    """A release was unavailable or failed pre-activation validation."""


@dataclass(frozen=True)
class ReleaseResult:
    activated: bool
    pack_version: str | None
    schema_version: int | None = None
    reason: str | None = None
    activation: PackActivationTransaction | None = None


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
    feature_contract_versions: tuple[tuple[str, str], ...] = ()


def _version_key(version: str) -> tuple[Any, ...]:
    """Return a comparable key for release versions (``1.2.3`` included)."""
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

_URL_IN_DIAGNOSTIC_RE = re.compile(r"https?://[^\s<>'\"]+")


def _sanitize_diagnostic(exc: BaseException) -> str:
    """Keep transport diagnostics free of signed queries and credentials."""
    if isinstance(exc, httpx.HTTPError):
        return "release transport failed"
    message = str(exc)

    def replace(match: re.Match[str]) -> str:
        value = match.group(0).rstrip(".,);")
        try:
            parsed = urllib.parse.urlsplit(value)
            host = parsed.hostname or ""
            if parsed.port is not None:
                host = f"{host}:{parsed.port}"
            return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        except ValueError:
            return "[release URL redacted]"

    return _URL_IN_DIAGNOSTIC_RE.sub(replace, message)


def _is_literal_loopback_http(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        return (
            parsed.scheme == "http"
            and parsed.hostname == "127.0.0.1"
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and _effective_port(parsed) is not None
        )
    except ValueError:
        return False


def _decode_manifest_public_key(value: str) -> bytes:
    encoded = value.strip()
    try:
        raw = (
            bytes.fromhex(encoded)
            if len(encoded) == 64
            else base64.b64decode(encoded, validate=True)
        )
    except (ValueError, binascii.Error) as exc:
        raise ReleaseChannelError(
            "loopback manifest public key is not valid key material"
        ) from exc
    if len(raw) != 32:
        raise ReleaseChannelError(
            "loopback manifest public key must contain 32 bytes"
        )
    return raw


def _url_from_manifest(manifest: dict[str, Any], base_url: str) -> str:
    """Resolve a signed payload reference under the logical release path."""
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
    decoded_path = urllib.parse.unquote(parsed.path)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or not parsed.path
        or parsed.path.startswith(("/", "\\"))
        or decoded_path.startswith(("/", "\\"))
        or "\\" in decoded_path
    ):
        raise ReleaseChannelError("release asset URL must be relative")
    relative = PurePosixPath(decoded_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ReleaseChannelError("release asset path escapes its logical release")
    resolved = urllib.parse.urljoin(base_url, parsed.path)
    try:
        base = urllib.parse.urlparse(base_url)
        destination = urllib.parse.urlparse(resolved)
        base_dir = posixpath.dirname(base.path).rstrip("/") or "/"
        prefix = f"{base_dir}/" if base_dir != "/" else "/"
        if (
            _origin(resolved) != _origin(base_url)
            or not destination.path.startswith(prefix)
        ):
            raise ReleaseChannelError("release asset URL must remain in its logical release")
    except ValueError as exc:
        raise ReleaseChannelError("release asset URL is invalid") from exc
    return resolved


def _signature_url(manifest_url: str) -> str:
    parsed = urllib.parse.urlparse(manifest_url)
    if parsed.query or parsed.fragment:
        raise ReleaseChannelError("release manifest URL must not contain query or fragment")
    return urllib.parse.urlunparse(parsed._replace(path=f"{parsed.path}.sig"))


def _github_route(
    url: str,
    *,
    repository: str | None = None,
    require_tag: bool = False,
) -> tuple[str, str | None, str] | None:
    """Return ``(repository, tag, asset)`` for a canonical GitHub release URL."""
    parsed = urllib.parse.urlparse(url)
    try:
        port = _effective_port(parsed)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != GITHUB_HOST
        or port != 443
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return None
    latest = _GITHUB_LATEST_RE.fullmatch(parsed.path)
    tagged = _GITHUB_TAGGED_RE.fullmatch(parsed.path)
    if latest is not None:
        if require_tag:
            return None
        route = (latest.group("repo"), None, latest.group("asset"))
    elif tagged is not None:
        tag = urllib.parse.unquote(tagged.group("tag"))
        if not tag or "/" in tag or "\\" in tag:
            return None
        route = (tagged.group("repo"), tag, tagged.group("asset"))
    else:
        return None
    asset = urllib.parse.unquote(route[2])
    if not asset or "/" in asset or "\\" in asset:
        return None
    route = (route[0], route[1], asset)
    if repository is not None and route[0] != repository:
        return None
    return route

def _github_latest_tag(
    url: str,
    *,
    repository: str | None = None,
) -> tuple[str, str] | None:
    """Return ``(repository, tag)`` for a same-repository latest redirect."""
    parsed = urllib.parse.urlparse(url)
    try:
        port = _effective_port(parsed)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname != GITHUB_HOST
        or port != 443
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return None
    match = _GITHUB_LATEST_TAG_RE.fullmatch(parsed.path)
    if match is None:
        return None
    tag = urllib.parse.unquote(match.group("tag"))
    repo = match.group("repo")
    if not tag or "/" in tag or "\\" in tag or (repository is not None and repo != repository):
        return None
    return repo, tag

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
            if not isinstance(item["sha256"], str) or not re.fullmatch(
                r"[0-9a-fA-F]{64}", item["sha256"]
            ):
                raise ReleaseChannelError("invalid model artifact hash")
            entry["sha256"] = item["sha256"].lower()
        if item.get("size") is not None:
            size = item["size"]
            if isinstance(size, bool) or not isinstance(size, int) or size < 0:
                raise ReleaseChannelError("invalid model artifact size")
            entry["size"] = str(size)
        if item.get("model_card_path") is not None:
            if not isinstance(item["model_card_path"], str):
                raise ReleaseChannelError("invalid model card path")
            entry["model_card_path"] = item["model_card_path"]
        for key in ("model_card_sha256",):
            if item.get(key) is not None:
                value_for_key = item[key]
                if not isinstance(value_for_key, str) or not re.fullmatch(
                    r"[0-9a-fA-F]{64}", value_for_key
                ):
                    raise ReleaseChannelError("invalid model card hash")
                entry[key] = value_for_key.lower()
        if item.get("model_card_size") is not None:
            card_size = item["model_card_size"]
            if (
                isinstance(card_size, bool)
                or not isinstance(card_size, int)
                or card_size < 0
            ):
                raise ReleaseChannelError("invalid model card size")
            entry["model_card_size"] = str(card_size)
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
    schema_version = raw.get("schema_version")
    if schema_version != 2:
        raise ReleaseChannelError("release manifest schema_version must be 2")
    contracts_value = raw.get("feature_contract_versions")
    if contracts_value is None:
        contract = raw.get("feature_contract_version")
        if not isinstance(contract, str) or not contract.strip():
            raise ReleaseChannelError("release manifest has no feature contract version")
        feature_contract_versions = (("population", contract.strip()),)
    elif isinstance(contracts_value, dict):
        if not contracts_value or any(
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(value, str)
            or not value.strip()
            for key, value in contracts_value.items()
        ):
            raise ReleaseChannelError("release manifest feature contract versions are invalid")
        feature_contract_versions = tuple(
            sorted(
                ((key.strip(), value.strip()) for key, value in contracts_value.items()),
                key=lambda item: item[0],
            )
        )
        contract = raw.get("feature_contract_version")
        if not isinstance(contract, str) or not contract.strip():
            contract = dict(feature_contract_versions).get("population") or feature_contract_versions[0][1]
        else:
            contract = contract.strip()
    else:
        raise ReleaseChannelError("release manifest feature contract versions are invalid")
    if not isinstance(contract, str) or not contract.strip():
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
    min_app = raw.get(
        "min_app_version",
        raw.get("minimum_app_version", compatibility.get("min_version")),
    )
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
        feature_contract_versions=feature_contract_versions,
    )


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or not path.parts
        or ":" in path.parts[0]
    ):
        raise ReleaseChannelError("release archive contains an unsafe path")
    return path


def _extract_candidate(
    download: Path,
    destination: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if zipfile.is_zipfile(download):
        with zipfile.ZipFile(download) as archive:
            files: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for info in archive.infolist():
                path = _safe_member(info.filename)
                if not path.parts or info.is_dir():
                    continue
                if info.file_size < 0:
                    raise ReleaseChannelError("release archive has an invalid member size")
                files.append((info, path))
            if len(files) > MAX_ARCHIVE_MEMBERS:
                raise ReleaseChannelError(
                    f"release archive has too many file members (maximum {MAX_ARCHIVE_MEMBERS})"
                )
            declared_total = sum(info.file_size for info, _ in files)
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


def _candidate_pack_path(directory: Path) -> Path:
    path = directory / PACK_FILENAME
    if not path.is_file():
        raise ReleaseChannelError("release is missing its Findings Pack v2 payload")
    return path


def _validate_declared_artifacts(
    directory: Path,
    artifacts: tuple[dict[str, str], ...],
) -> None:
    for artifact in artifacts:
        try:
            relative = _safe_member(artifact["path"])
        except (KeyError, TypeError) as exc:
            raise ReleaseChannelError("invalid model artifact declaration") from exc
        path = directory.joinpath(*relative.parts)
        if not path.is_file():
            raise ReleaseChannelError("release model artifact is missing")
        try:
            actual_size = path.stat().st_size
        except OSError as exc:
            raise ReleaseChannelError("release model artifact could not be inspected") from exc
        if actual_size <= 0 or actual_size > EXPANDED_ASSET_MAX_BYTES:
            raise ReleaseChannelError("release model artifact exceeds size limits")
        expected_hash = artifact.get("sha256")
        if expected_hash is not None:
            if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
                raise ReleaseChannelError("release model artifact hash is invalid")
            if _read_sha256(path) != expected_hash:
                raise ReleaseChannelError("release model artifact hash mismatch")
        expected_size = artifact.get("size")
        if expected_size is not None:
            try:
                declared_size = int(expected_size)
            except (TypeError, ValueError) as exc:
                raise ReleaseChannelError("release model artifact size is invalid") from exc
            if actual_size != declared_size:
                raise ReleaseChannelError("release model artifact size mismatch")

        model_card = artifact.get("model_card_path")
        if model_card is None:
            continue
        try:
            card_relative = _safe_member(model_card)
        except (TypeError, ValueError) as exc:
            raise ReleaseChannelError("release model card path is invalid") from exc
        card_path = directory.joinpath(*card_relative.parts)
        if not card_path.is_file():
            raise ReleaseChannelError("release model card is missing")
        try:
            card_size = card_path.stat().st_size
        except OSError as exc:
            raise ReleaseChannelError("release model card could not be inspected") from exc
        if card_size <= 0 or card_size > 1024 * 1024:
            raise ReleaseChannelError("release model card exceeds size limits")
        card_hash = artifact.get("model_card_sha256")
        if card_hash is not None:
            if not re.fullmatch(r"[0-9a-f]{64}", card_hash):
                raise ReleaseChannelError("release model card hash is invalid")
            if _read_sha256(card_path) != card_hash:
                raise ReleaseChannelError("release model card hash mismatch")
        card_size_value = artifact.get("model_card_size")
        if card_size_value is not None:
            try:
                declared_card_size = int(card_size_value)
            except (TypeError, ValueError) as exc:
                raise ReleaseChannelError("release model card size is invalid") from exc
            if card_size != declared_card_size:
                raise ReleaseChannelError("release model card size mismatch")


def _validate_v2_candidate(
    directory: Path,
    pack: dict[str, Any],
    release: ReleaseManifest,
) -> None:
    try:
        parsed = FindingsPackV2.model_validate(pack)
    except (ValidationError, ValueError, TypeError) as exc:
        raise ReleaseChannelError(f"release Findings Pack v2 failed validation: {exc}") from exc
    candidate_contracts = pack.get("feature_contracts")
    if not isinstance(candidate_contracts, dict):
        raise ReleaseChannelError("release Findings Pack v2 has no feature contracts")
    declared_contracts = dict(release.feature_contract_versions)
    declared_model_contracts = candidate_contracts.get("models")
    if not isinstance(declared_model_contracts, dict):
        declared_model_contracts = {}
    if any(
        (
            declared_model_contracts.get(key)
            if key in EXECUTABLE_MODEL_KEYS
            else candidate_contracts.get(key)
        )
        != value
        for key, value in declared_contracts.items()
    ):
        raise ReleaseChannelError("release feature contract is incompatible")

    manifest_artifacts = release.required_model_artifacts
    declared_artifacts: list[dict[str, str]] = list(manifest_artifacts)
    for model in (parsed.models or {}).values():
        if model.release_status != "available":
            continue
        artifact = model.artifact
        if artifact is None:
            raise ReleaseChannelError("available release model has no artifact")
        expected = {
            "path": artifact.path,
            "sha256": artifact.sha256,
            "size": str(artifact.size),
            "model_card_path": artifact.model_card_path,
            "model_card_sha256": artifact.model_card_sha256,
            "model_card_size": str(artifact.model_card_size),
        }
        if not any(
            all(spec.get(key) == value for key, value in expected.items())
            for spec in manifest_artifacts
        ):
            raise ReleaseChannelError("release manifest does not pin the model artifact and card")
        declared_artifacts.append(expected)
    _validate_declared_artifacts(directory, tuple(declared_artifacts))


def _validate_candidate(
    directory: Path,
    release: ReleaseManifest,
    *,
    app_version: str,
    schema_path: Path | None,
) -> dict[str, Any]:
    pack_path = _candidate_pack_path(directory)
    try:
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseChannelError(f"release pack is not valid JSON: {exc}") from exc
    if not isinstance(pack, dict):
        raise ReleaseChannelError("release pack must be an object")
    if pack.get("schema_version") != 2:
        raise ReleaseChannelError("release schema_version must be 2")
    pack_version = pack.get("pack_version")
    if pack_version is not None and pack_version != release.pack_version:
        raise ReleaseChannelError("release pack_version does not match its manifest")
    if release.min_app_version and _version_key(app_version) < _version_key(release.min_app_version):
        raise ReleaseChannelError("release requires a newer app")
    if release.max_app_version and _version_key(app_version) > _version_key(release.max_app_version):
        raise ReleaseChannelError("release is not compatible with this app")

    _validate_v2_candidate(directory, pack, release)
    candidate_schema = directory / SCHEMA_FILENAME
    try:
        validate_pack_directory(
            directory,
            schema_path=(
                candidate_schema
                if candidate_schema.exists()
                else schema_path
                if schema_path is not None and schema_path.exists()
                else None
            ),
            require_schema=False,
        )
    except PackError as exc:
        raise ReleaseChannelError("release model payload failed validation") from exc
    return pack




class ReleaseChannel:
    """Download and activate a compatible Findings Pack release."""

    def __init__(
        self,
        pack_dir: Path,
        *,
        manifest_url: str = DEFAULT_MANIFEST_URL,
        app_version: str = APP_VERSION,
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
        allow_loopback_http: bool = False,
        manifest_public_key: bytes | None = None,
        pack_store: PackStore | None = None,
    ) -> None:
        self.pack_store = pack_store or PackStore(pack_dir)
        self.manifest_url = manifest_url
        self.app_version = app_version
        self.timeout = timeout
        self.client = client
        self.allow_loopback_http = allow_loopback_http
        if manifest_public_key is None:
            override = os.environ.get("BHAYANAK_PACK_RELEASE_MANIFEST_PUBLIC_KEY")
            if override:
                if not allow_loopback_http or not _is_literal_loopback_http(manifest_url):
                    raise ReleaseChannelError(
                        "loopback manifest public key requires explicit loopback transport"
                    )
                manifest_public_key = _decode_manifest_public_key(override)
        self.manifest_public_key = manifest_public_key

    @property
    def pack_dir(self) -> Path:
        return self.pack_store.pack_dir

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
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise ReleaseChannelError(f"{label} URL is invalid")
        loopback = host == "127.0.0.1"
        if parsed.scheme != "https" and not (self.allow_loopback_http and loopback):
            raise ReleaseChannelError(f"{label} must use HTTPS")
        if expected_origin is not None:
            expected_scheme, expected_host, expected_port = expected_origin
            if host != expected_host:
                raise ReleaseChannelError(f"{label} redirect changed host")
            if port != expected_port or parsed.scheme != expected_scheme:
                raise ReleaseChannelError(f"{label} redirect changed origin")
        return parsed

    def _fetch_policy(
        self,
        url: str,
        *,
        label: str,
        expected_logical_url: str | None,
    ) -> tuple[_TransportPolicy, str | None]:
        parsed = self._validate_transport_url(url, label=label)
        route = _github_route(url)
        if parsed.hostname == GITHUB_HOST:
            if route is None:
                raise ReleaseChannelError(f"{label} GitHub release URL is invalid")
            repository, tag, asset = route
            pinned = expected_logical_url
            if pinned is not None:
                expected_route = _github_route(
                    pinned, repository=repository, require_tag=True
                )
                if expected_route is None:
                    raise ReleaseChannelError(f"{label} logical release URL is invalid")
                pinned = urllib.parse.urlunparse(
                    urllib.parse.urlparse(pinned)._replace(query="", fragment="")
                )
            elif tag is not None:
                pinned = url
            return (
                _TransportPolicy(
                    _origin(url),
                    initial_url=url,
                    github_repo=repository,
                    github_asset=asset,
                    github_latest=tag is None,
                ),
                pinned,
            )
        if parsed.hostname == GITHUB_CDN_HOST:
            raise ReleaseChannelError(f"{label} cannot start at the GitHub asset CDN")
        return _TransportPolicy(_origin(url), initial_url=url), expected_logical_url

    async def _resolve_github_latest(
        self,
        client: httpx.AsyncClient,
        policy: _TransportPolicy,
        *,
        label: str,
    ) -> str:
        """Resolve a latest route through GitHub's same-origin tag redirect."""
        if not policy.github_latest or policy.github_repo is None or policy.github_asset is None:
            raise ReleaseChannelError(f"{label} GitHub latest release is unavailable")
        route = _github_route(policy.initial_url)
        if (
            route is None
            or route[1] is not None
            or route[0] != policy.github_repo
            or route[2] != policy.github_asset
        ):
            raise ReleaseChannelError(f"{label} GitHub latest release is invalid")
        repository, _, asset = route
        metadata_url = f"https://{GITHUB_HOST}{repository}/releases/latest"
        metadata_label = f"{label} GitHub latest tag"
        metadata_parsed = self._validate_transport_url(metadata_url, label=metadata_label)
        if (
            metadata_parsed.hostname != GITHUB_HOST
            or _effective_port(metadata_parsed) != 443
            or metadata_parsed.path != f"{repository}/releases/latest"
            or metadata_parsed.query
            or metadata_parsed.fragment
        ):
            raise ReleaseChannelError(f"{metadata_label} URL is invalid")

        async with client.stream(
            "GET",
            metadata_url,
            headers={"User-Agent": "BhayanakLegends-release-channel"},
            follow_redirects=False,
        ) as response:
            if not response.is_redirect:
                raise ReleaseChannelError(f"{metadata_label} did not redirect to a tag")
            location = response.headers.get("location")
            if not location:
                raise ReleaseChannelError(f"{metadata_label} redirect has no location")
            tag_url = urllib.parse.urljoin(metadata_url, location)
            tag = _github_latest_tag(tag_url, repository=repository)
            if tag is None:
                raise ReleaseChannelError(f"{metadata_label} redirect escaped its repository")
            final_url = str(response.url) or metadata_url
            final_parsed = self._validate_transport_url(
                final_url,
                label=metadata_label,
                expected_origin=_origin(metadata_url),
            )
            if (
                final_parsed.hostname != GITHUB_HOST
                or final_parsed.path != metadata_parsed.path
                or final_parsed.query
                or final_parsed.fragment
            ):
                raise ReleaseChannelError(f"{metadata_label} changed its endpoint")
            _, resolved_tag = tag

        tagged_url = urllib.parse.urlunparse(
            urllib.parse.urlparse(policy.initial_url)._replace(
                path=(
                    f"{repository}/releases/download/"
                    f"{urllib.parse.quote(resolved_tag, safe='')}/"
                    f"{urllib.parse.quote(asset, safe='')}"
                ),
                query="",
                fragment="",
            )
        )
        tagged_route = _github_route(
            tagged_url,
            repository=repository,
            require_tag=True,
        )
        if tagged_route != (repository, resolved_tag, asset):
            raise ReleaseChannelError(f"{metadata_label} tag is invalid")
        return tagged_url

    def _validate_hop(
        self,
        url: str,
        *,
        label: str,
        policy: _TransportPolicy,
        pinned_logical_url: str | None,
        previous_url: str | None,
    ) -> urllib.parse.ParseResult:
        parsed = self._validate_transport_url(url, label=label)
        if policy.github_repo is None:
            if _origin(url) != policy.origin:
                raise ReleaseChannelError(f"{label} redirect changed origin")
            return parsed

        if parsed.hostname == GITHUB_HOST:
            if previous_url is not None and (
                urllib.parse.urlparse(previous_url).hostname or ""
            ).lower() == GITHUB_CDN_HOST:
                raise ReleaseChannelError(f"{label} CDN redirect returned to GitHub")
            route = _github_route(url, repository=policy.github_repo)
            if route is None:
                raise ReleaseChannelError(f"{label} escaped its GitHub release")
            if route[1] is None:
                if previous_url is not None or url != policy.initial_url:
                    raise ReleaseChannelError(f"{label} did not resolve its GitHub release")
            elif pinned_logical_url is not None:
                pinned = urllib.parse.urlparse(pinned_logical_url)
                if parsed.path != pinned.path:
                    raise ReleaseChannelError(f"{label} changed its pinned release")
            elif route[2] != policy.github_asset:
                raise ReleaseChannelError(f"{label} changed its GitHub asset")
            return parsed
        if parsed.hostname == GITHUB_CDN_HOST:
            if pinned_logical_url is None or previous_url is None:
                raise ReleaseChannelError(f"{label} CDN redirect is not release-pinned")
            previous_host = (urllib.parse.urlparse(previous_url).hostname or "").lower()
            if previous_host not in {GITHUB_HOST, GITHUB_CDN_HOST}:
                raise ReleaseChannelError(f"{label} CDN redirect is not allowed")
            if _effective_port(parsed) != 443:
                raise ReleaseChannelError(f"{label} CDN redirect has an invalid port")
            return parsed
        raise ReleaseChannelError(f"{label} redirect changed host")

    async def _fetch_bytes(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        limit: int,
        label: str,
        expected_logical_url: str | None = None,
        expected_size: int | None = None,
    ) -> _FetchResult:
        policy, pinned_logical_url = self._fetch_policy(
            url,
            label=label,
            expected_logical_url=expected_logical_url,
        )
        current = url
        previous: str | None = None
        for _ in range(MAX_REDIRECTS + 1):
            self._validate_hop(
                current,
                label=label,
                policy=policy,
                pinned_logical_url=pinned_logical_url,
                previous_url=previous,
            )
            async with client.stream("GET", current, follow_redirects=False) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ReleaseChannelError(f"{label} redirect has no location")
                    next_url = urllib.parse.urljoin(current, location)
                    next_parsed = self._validate_transport_url(next_url, label=label)
                    if (
                        policy.github_latest
                        and pinned_logical_url is None
                        and next_parsed.hostname == GITHUB_CDN_HOST
                    ):
                        pinned_logical_url = await self._resolve_github_latest(
                            client,
                            policy,
                            label=label,
                        )
                    next_parsed = self._validate_hop(
                        next_url,
                        label=label,
                        policy=policy,
                        pinned_logical_url=pinned_logical_url,
                        previous_url=current,
                    )
                    if policy.github_repo is not None and next_parsed.hostname == GITHUB_HOST:
                        route = _github_route(next_url, repository=policy.github_repo)
                        if route is None or route[1] is None:
                            raise ReleaseChannelError(f"{label} escaped its GitHub release")
                        if pinned_logical_url is None:
                            pinned_logical_url = urllib.parse.urlunparse(
                                next_parsed._replace(query="", fragment="")
                            )
                    previous, current = current, next_url
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    raise ReleaseChannelError(f"{label} request failed") from exc
                if expected_size is not None:
                    content_length = response.headers.get("content-length")
                    if content_length is not None:
                        try:
                            declared_length = int(content_length)
                        except ValueError as exc:
                            raise ReleaseChannelError(f"{label} content length is invalid") from exc
                        if declared_length != expected_size:
                            raise ReleaseChannelError(f"{label} size does not match manifest")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes(64 * 1024):
                    if chunk:
                        total += len(chunk)
                        if total > limit:
                            raise ReleaseChannelError(f"{label} exceeds {limit} byte limit")
                        chunks.append(chunk)
                final_url = str(response.url) or current
                self._validate_hop(
                    final_url,
                    label=label,
                    policy=policy,
                    pinned_logical_url=pinned_logical_url,
                    previous_url=previous,
                )
                if policy.github_repo is not None and pinned_logical_url is None:
                    raise ReleaseChannelError(
                        f"{label} latest URL did not resolve to an immutable release"
                    )
                logical_url = pinned_logical_url or final_url
                body = b"".join(chunks)
                if expected_size is not None and len(body) != expected_size:
                    raise ReleaseChannelError(f"{label} was truncated")
                return _FetchResult(logical_url, final_url, body)
        raise ReleaseChannelError(f"{label} has too many redirects")

    async def check_and_activate(
        self,
        current_version: str | None = None,
        *,
        defer_finalize: bool = False,
    ) -> ReleaseResult:
        """Check the public manifest and activate only a newer valid candidate."""
        transaction: PackActivationTransaction | None = None
        try:
            async with self._client_context() as client:
                manifest_fetch = await self._fetch_bytes(
                    client,
                    self.manifest_url,
                    limit=MANIFEST_MAX_BYTES,
                    label="release manifest",
                )
                logical_manifest_url = manifest_fetch.logical_url
                signature_url = _signature_url(logical_manifest_url)
                signature_fetch = await self._fetch_bytes(
                    client,
                    signature_url,
                    limit=SIGNATURE_MAX_BYTES,
                    label="release manifest signature",
                    expected_logical_url=signature_url
                    if _github_route(signature_url, require_tag=True)
                    else None,
                )
                raw_manifest = manifest_fetch.body
                raw_signature = signature_fetch.body
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
                release = _manifest(raw_manifest_json, logical_manifest_url)
                if not is_newer_version(release.pack_version, current_version):
                    return ReleaseResult(False, current_version, release.schema_version, "up-to-date")
                with tempfile.TemporaryDirectory(
                    prefix="bl-pack-",
                    dir=self.pack_store.storage_parent,
                ) as temporary:
                    temp_root = Path(temporary)
                    download = temp_root / "download"
                    await self._download(
                        client,
                        release.download_url,
                        download,
                        release.size,
                        expected_logical_url=release.download_url
                        if _github_route(release.download_url, require_tag=True)
                        else None,
                    )
                    if _read_sha256(download) != release.sha256:
                        raise ReleaseChannelError("release asset hash mismatch")
                    candidate = temp_root / "candidate"
                    _extract_candidate(
                        download,
                        candidate,
                    )
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
            reason = _sanitize_diagnostic(exc)
            log.warning("Findings Pack release check failed: %s", reason)
            return ReleaseResult(False, current_version, None, reason)

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
        expected_logical_url: str | None = None,
    ) -> None:
        if expected_size < 0 or expected_size > COMPRESSED_ASSET_MAX_BYTES:
            raise ReleaseChannelError("release asset size is outside the allowed limit")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            fetched = await self._fetch_bytes(
                client,
                url,
                limit=COMPRESSED_ASSET_MAX_BYTES,
                label="release asset",
                expected_logical_url=expected_logical_url,
                expected_size=expected_size,
            )
            target.write_bytes(fetched.body)
            if target.stat().st_size != expected_size:
                raise ReleaseChannelError("release asset was truncated")
        except Exception:
            target.unlink(missing_ok=True)
            raise

    def _activate(self, candidate: Path) -> PackActivationTransaction:
        """Publish an already-validated candidate as one immutable generation."""
        try:
            return self.pack_store.activate_candidate(candidate)
        except PackError as exc:
            raise ReleaseChannelError(str(exc)) from exc

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
    "PACK_FILENAME",
    "ReleaseChannel",
    "ReleaseChannelError",
    "ReleaseManifest",
    "ReleaseResult",
    "is_newer_version",
]

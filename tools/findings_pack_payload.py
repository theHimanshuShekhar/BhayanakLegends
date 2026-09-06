"""Build deterministic Findings Pack release payloads and manifests.

This module has no producer-side logic: it reads the already validated
consumer-side pack directory, preserves every file byte-for-byte, and derives
signed manifest metadata from the declarations in ``findings-pack.v2.json``.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import urllib.parse
import zipfile
from typing import Any

PACK_FILENAME = "findings-pack.v2.json"
SCHEMA_FILENAME = "pack.schema.json"
SHA256_HEX_LENGTH = 64


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(value: object, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or "" in path.parts
        or ":" in path.parts[0]
        or "\\" in value
    ):
        raise ValueError(f"{label} must remain inside the Findings Pack")
    return path


def read_pack(pack_dir: Path) -> tuple[bytes, dict[str, Any]]:
    """Read the exact pack JSON bytes and its object representation."""
    root = Path(pack_dir)
    path = root / PACK_FILENAME
    if not path.is_file():
        raise ValueError(f"Findings Pack is missing: {path}")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Findings Pack cannot be read: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Findings Pack root must be a JSON object")
    return raw, payload


def _files(pack_dir: Path) -> list[tuple[PurePosixPath, Path]]:
    root = Path(pack_dir)
    if not root.is_dir():
        raise ValueError(f"Findings Pack directory is missing: {root}")
    entries: list[tuple[PurePosixPath, Path]] = []
    try:
        paths = sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    except OSError as exc:
        raise ValueError(f"Findings Pack directory cannot be inspected: {root}") from exc
    for path in paths:
        if path.is_symlink():
            raise ValueError(f"Findings Pack cannot package symlink: {path}")
        relative = _relative_path(path.relative_to(root).as_posix(), label="pack file path")
        entries.append((relative, path))
    names = {relative.as_posix() for relative, _path in entries}
    for required in (PACK_FILENAME, SCHEMA_FILENAME):
        if required not in names:
            raise ValueError(f"Findings Pack payload is missing {required}")
    return entries


def archive_pack_directory(pack_dir: Path) -> bytes:
    """Return a byte-stable ZIP containing every pack file.

    Stored members and a fixed DOS timestamp avoid filesystem mtimes and
    compressor-version differences changing the signed release asset. Files
    are sorted by their POSIX path and retain their source bytes exactly.
    """
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative, path in _files(Path(pack_dir)):
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return output.getvalue()


def model_artifact_specs(pack_dir: Path, payload: dict[str, Any]) -> list[dict[str, object]]:
    """Derive manifest pins for every available model and its card."""
    root = Path(pack_dir)
    models = payload.get("models")
    if models is None:
        return []
    if not isinstance(models, dict):
        raise ValueError("Findings Pack models must be an object")
    result: list[dict[str, object]] = []
    for model_key in sorted(models):
        declaration = models[model_key]
        if not isinstance(declaration, dict):
            raise ValueError(f"Findings Pack model {model_key!r} must be an object")
        if declaration.get("release_status") != "available":
            continue
        artifact = declaration.get("artifact")
        card = declaration.get("model_card")
        if not isinstance(artifact, dict) or not isinstance(card, dict):
            raise ValueError(f"available Findings Pack model {model_key!r} has no artifact/card")
        artifact_path = _relative_path(artifact.get("path"), label="model artifact path")
        card_path = _relative_path(
            artifact.get("model_card_path"), label="model card path"
        )
        artifact_file = root.joinpath(*artifact_path.parts)
        card_file = root.joinpath(*card_path.parts)
        if not artifact_file.is_file():
            raise ValueError(f"model artifact is missing: {artifact_path.as_posix()}")
        if not card_file.is_file():
            raise ValueError(f"model card is missing: {card_path.as_posix()}")
        artifact_size = artifact_file.stat().st_size
        card_size = card_file.stat().st_size
        artifact_hash = _sha256_file(artifact_file)
        card_hash = _sha256_file(card_file)
        if artifact.get("size") != artifact_size or artifact.get("sha256") != artifact_hash:
            raise ValueError(f"model artifact declaration does not match bytes: {artifact_path}")
        if (
            artifact.get("model_card_size") != card_size
            or artifact.get("model_card_sha256") != card_hash
        ):
            raise ValueError(f"model card declaration does not match bytes: {card_path}")
        result.append(
            {
                "path": artifact_path.as_posix(),
                "sha256": artifact_hash,
                "size": artifact_size,
                "model_card_path": card_path.as_posix(),
                "model_card_sha256": card_hash,
                "model_card_size": card_size,
            }
        )
    return result


def _feature_contract_versions(payload: dict[str, Any]) -> dict[str, str]:
    contracts = payload.get("feature_contracts")
    if not isinstance(contracts, dict):
        raise ValueError("Findings Pack has no feature contracts")
    result: dict[str, str] = {}
    for key, value in contracts.items():
        if key == "models":
            if not isinstance(value, dict):
                raise ValueError("Findings Pack model contracts must be an object")
            for model_key, model_value in value.items():
                if not isinstance(model_key, str) or not model_key.strip():
                    raise ValueError("Findings Pack model contract key is invalid")
                if not isinstance(model_value, str) or not model_value.strip():
                    raise ValueError("Findings Pack model contract value is invalid")
                result[model_key.strip()] = model_value.strip()
            continue
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Findings Pack feature contract key is invalid")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Findings Pack feature contract value is invalid")
        result[key.strip()] = value.strip()
    if not result:
        raise ValueError("Findings Pack has no feature contract versions")
    return dict(sorted(result.items()))


def build_manifest(
    pack_dir: Path,
    asset: bytes,
    *,
    download_url: str = "findings-pack.v2.zip",
    min_app_version: str = "0.1.0",
    max_app_version: str | None = None,
) -> dict[str, object]:
    """Build deterministic manifest metadata for one exact pack asset."""
    _raw, payload = read_pack(pack_dir)
    if payload.get("schema_version") != 2:
        raise ValueError("Findings Pack schema_version must be 2")
    pack_version = payload.get("pack_version")
    if not isinstance(pack_version, str) or not pack_version.strip():
        raise ValueError("Findings Pack pack_version must be non-empty")
    if not isinstance(min_app_version, str) or not min_app_version.strip():
        raise ValueError("minimum application version must be non-empty")
    if max_app_version is not None and (
        not isinstance(max_app_version, str) or not max_app_version.strip()
    ):
        raise ValueError("maximum application version must be non-empty when supplied")
    parsed_url = urllib.parse.urlparse(download_url)
    if (
        not download_url
        or parsed_url.scheme
        or parsed_url.netloc
        or parsed_url.query
        or parsed_url.fragment
        or parsed_url.path.startswith(("/", "\\"))
        or "\\" in parsed_url.path
        or ".." in PurePosixPath(parsed_url.path).parts
    ):
        raise ValueError("release payload URL must be relative")
    versions = _feature_contract_versions(payload)
    primary = versions.get("population") or next(iter(versions.values()))
    manifest: dict[str, object] = {
        "pack_version": pack_version.strip(),
        "schema_version": 2,
        "feature_contract_version": primary,
        "feature_contract_versions": versions,
        "download_url": download_url,
        "sha256": _sha256_bytes(asset),
        "size": len(asset),
        "required_model_artifacts": model_artifact_specs(pack_dir, payload),
        "min_app_version": min_app_version.strip(),
    }
    if max_app_version is not None:
        manifest["max_app_version"] = max_app_version.strip()
    return manifest


def manifest_bytes(manifest: dict[str, object]) -> bytes:
    """Serialize a manifest exactly as the signer and channel consume it."""
    return (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


__all__ = [
    "PACK_FILENAME",
    "SCHEMA_FILENAME",
    "archive_pack_directory",
    "build_manifest",
    "manifest_bytes",
    "model_artifact_specs",
    "read_pack",
]

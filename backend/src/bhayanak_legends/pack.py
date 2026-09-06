"""Findings Pack loading, schema validation, and atomic active-store support."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from json import JSONDecodeError
from pathlib import Path
from typing import Iterable

import jsonschema
from pydantic import ValidationError

from .pack_v2 import FindingsPackV2, validate_pack_v2_semantics

PACK_FILENAME = "findings-pack.v2.json"
SCHEMA_FILENAME = "pack.schema.json"
MAX_MODEL_ARTIFACT_BYTES = 256 * 1024 * 1024


class PackError(Exception):
    """A pack cannot be safely loaded or activated."""


def _pack_path(directory: Path) -> Path:
    return directory / PACK_FILENAME


def _safe_relative_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or not candidate.parts or ".." in candidate.parts:
        raise PackError("Findings Pack artifact path must remain inside the active pack")
    if any(part in {"", "."} for part in candidate.parts):
        raise PackError("Findings Pack artifact path is not canonical")
    return candidate


def _artifact_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_artifact(
    root: Path,
    artifact_path: Path,
    expected_sha256: str | None,
    expected_size: int | None = None,
) -> None:
    try:
        resolved_root = root.resolve()
        resolved = artifact_path.resolve()
    except OSError as exc:
        raise PackError("Findings Pack model artifact path could not be resolved") from exc
    if resolved_root not in resolved.parents:
        raise PackError("Findings Pack model artifact path escapes the active pack")
    if not artifact_path.is_file():
        raise PackError(f"Findings Pack model artifact missing at {artifact_path}")
    try:
        size = artifact_path.stat().st_size
    except OSError as exc:
        raise PackError(f"Findings Pack model artifact could not be inspected: {artifact_path}") from exc
    if size <= 0 or size > MAX_MODEL_ARTIFACT_BYTES:
        raise PackError(f"Findings Pack model artifact exceeds size limits: {artifact_path}")
    if expected_size is not None and size != expected_size:
        raise PackError(f"Findings Pack model artifact size mismatch: {artifact_path}")
    if expected_sha256 and _artifact_digest(artifact_path) != expected_sha256.lower():
        raise PackError(f"Findings Pack model artifact hash mismatch: {artifact_path}")


def _validate_declared_v2_artifacts(directory: Path, pack: FindingsPackV2) -> None:
    declared: set[Path] = set()
    for model in (pack.models or {}).values():
        if model.release_status != "available":
            continue
        if model.artifact is None or model.model_card is None:
            raise PackError(f"Findings Pack model {model.model_id!r} has no executable declaration")
        artifact_rel = _safe_relative_path(model.artifact.path)
        card_rel = _safe_relative_path(model.artifact.model_card_path)
        artifact_path = directory / artifact_rel
        _validate_artifact(directory, artifact_path, model.artifact.sha256, model.artifact.size)
        declared.add(artifact_rel)
        # Cards are JSON data and are bounded independently of executable
        # artifacts.  The card is also embedded in the pack so consumers can
        # inspect it without opening arbitrary files; the path pins the file
        # included in the release archive.
        card_path = directory / card_rel
        if not card_path.is_file():
            raise PackError(f"Findings Pack model card missing at {card_path}")
        if card_path.stat().st_size <= 0 or card_path.stat().st_size > 1024 * 1024:
            raise PackError(f"Findings Pack model card exceeds size limits: {card_path}")
        try:
            card_payload = json.loads(card_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
            raise PackError(f"Findings Pack model card could not be read: {card_path}") from exc
        if card_payload != model.model_card.model_dump(mode="json"):
            raise PackError(f"Findings Pack model card does not match declaration: {card_path}")
        declared.add(card_rel)

    models_dir = directory / "models"
    if models_dir.is_dir():
        try:
            actual = {
                path.relative_to(directory)
                for path in models_dir.rglob("*")
                if path.is_file()
            }
        except OSError as exc:
            raise PackError("Findings Pack model directory could not be inspected") from exc
        extra = sorted(actual - declared)
        if extra:
            raise PackError(f"Findings Pack contains undeclared model artifacts: {extra[0]}")


def _validate_required_artifacts(
    directory: Path,
    required_model_artifacts: Iterable[tuple[Path, str | None]],
) -> None:
    for artifact_path, expected_sha256 in required_model_artifacts:
        _validate_artifact(directory, artifact_path, expected_sha256)


def validate_pack_directory(
    directory: Path,
    *,
    schema_path: Path | None = None,
    required_model_artifacts: Iterable[tuple[Path, str | None]] = (),
    require_schema: bool = True,
) -> dict:
    """Validate a staged Findings Pack v2 and every declared executable artifact."""
    root = Path(directory)
    path = _pack_path(root)
    selected_schema = schema_path or (root / SCHEMA_FILENAME)
    if not path.is_file():
        raise PackError(f"Findings Pack missing at {path}")
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
        raise PackError(f"Findings Pack could not be read: {exc}") from exc
    if not isinstance(pack, dict):
        raise PackError("Findings Pack must be a JSON object")
    if require_schema and not selected_schema.is_file():
        raise PackError(f"Findings Pack schema missing at {selected_schema}")
    if selected_schema.is_file():
        try:
            schema = json.loads(selected_schema.read_text(encoding="utf-8"))
            jsonschema.validate(pack, schema)
        except (OSError, UnicodeDecodeError, JSONDecodeError, jsonschema.SchemaError) as exc:
            raise PackError(f"Findings Pack schema could not be read: {exc}") from exc
        except jsonschema.ValidationError as exc:
            raise PackError(f"Findings Pack failed schema validation: {exc.message}") from exc

    try:
        parsed = FindingsPackV2.model_validate(pack)
        validate_pack_v2_semantics(parsed)
        _validate_declared_v2_artifacts(root, parsed)
    except (ValidationError, ValueError, TypeError) as exc:
        raise PackError(f"Findings Pack failed contract validation: {exc}") from exc
    _validate_required_artifacts(root, required_model_artifacts)
    return pack


class PackStore:
    """Durable active Findings Pack v2 store."""

    def __init__(self, pack_dir: Path, *, bundled_dir: Path | None = None) -> None:
        self.pack_dir = Path(pack_dir)
        self.bundled_dir = Path(bundled_dir) if bundled_dir is not None else None
        self._pack: dict | None = None

    def initialize(self) -> None:
        """Commit the bundled seed once, without ever writing to its directory."""
        active_pack = _pack_path(self.pack_dir)
        self.pack_dir.parent.mkdir(parents=True, exist_ok=True)
        if active_pack.is_file():
            return
        if self.bundled_dir is None:
            return
        if not self.bundled_dir.is_dir():
            raise PackError(f"bundled Findings Pack missing at {self.bundled_dir}")

        staging = Path(
            tempfile.mkdtemp(prefix=f".{self.pack_dir.name}-seed-", dir=self.pack_dir.parent)
        )
        try:
            shutil.copytree(self.bundled_dir, staging, dirs_exist_ok=True)
            validate_pack_directory(staging)
            if self.pack_dir.exists():
                shutil.rmtree(self.pack_dir)
            os.replace(staging, self.pack_dir)
        except PackError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        except (OSError, shutil.Error) as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise PackError(f"bundled Findings Pack could not be seeded: {exc}") from exc

    def load(self) -> dict:
        if self._pack is not None:
            return self._pack
        path = _pack_path(self.pack_dir)
        schema_path = self.pack_dir / SCHEMA_FILENAME
        if not path.is_file():
            raise PackError(f"Findings Pack missing at {path}")
        try:
            pack = validate_pack_directory(
                self.pack_dir,
                schema_path=schema_path if schema_path.exists() else None,
                require_schema=False,
            )
        except PackError:
            raise
        self._pack = pack
        return pack

    def version(self) -> str:
        pack = self.load()
        return str(pack.get("pack_version") or f"v{pack['schema_version']}")

    def schema_version(self) -> int:
        return int(self.load()["schema_version"])

    def reload(self) -> None:
        self._pack = None

    def active_path(self) -> Path:
        self.load()
        return _pack_path(self.pack_dir)

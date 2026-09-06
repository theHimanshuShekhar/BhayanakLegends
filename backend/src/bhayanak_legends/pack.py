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

from .model_runtime import ModelRuntimeError, validate_model_artifact
from .pack_v2 import FindingsPackV2, validate_pack_v2_semantics

PACK_FILENAME = "findings-pack.v2.json"
SCHEMA_FILENAME = "pack.schema.json"
MAX_MODEL_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_MODEL_CARD_BYTES = 1024 * 1024


class PackError(Exception):
    """A pack cannot be safely loaded or activated."""


def _pack_path(directory: Path) -> Path:
    return directory / PACK_FILENAME


def _safe_relative_path(path: str) -> Path:
    candidate = Path(path)
    normalized = path.replace("\\", "/")
    if (
        candidate.is_absolute()
        or not candidate.parts
        or "\\" in path
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
        or ":" in normalized.split("/")[0]
    ):
        raise PackError("Findings Pack artifact path must remain inside the active pack")
    return Path(*normalized.split("/"))


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
    *,
    label: str = "model artifact",
) -> None:
    try:
        resolved_root = root.resolve()
        resolved = artifact_path.resolve()
    except OSError as exc:
        raise PackError(f"Findings Pack {label} path could not be resolved") from exc
    if resolved_root not in resolved.parents:
        raise PackError(f"Findings Pack {label} path escapes the active pack")
    if not artifact_path.is_file():
        raise PackError(f"Findings Pack {label} is missing")
    try:
        size = artifact_path.stat().st_size
    except OSError as exc:
        raise PackError(f"Findings Pack {label} could not be inspected") from exc
    max_size = MAX_MODEL_CARD_BYTES if label == "model card" else MAX_MODEL_ARTIFACT_BYTES
    if size <= 0 or size > max_size:
        raise PackError(f"Findings Pack {label} exceeds size limits")
    if expected_size is not None and size != expected_size:
        raise PackError(f"Findings Pack {label} size mismatch")
    if expected_sha256 and _artifact_digest(artifact_path) != expected_sha256.lower():
        raise PackError(f"Findings Pack {label} hash mismatch")


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
        # artifacts.  The embedded card and the on-disk card must both match
        # the signed declaration, including their exact pinned digest/size.
        card_path = directory / card_rel
        _validate_artifact(
            directory,
            card_path,
            model.artifact.model_card_sha256,
            model.artifact.model_card_size,
            label="model card",
        )
        try:
            card_payload = json.loads(card_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
            raise PackError("Findings Pack model card could not be read") from exc
        if card_payload != model.model_card.model_dump(mode="json"):
            raise PackError("Findings Pack model card does not match its declaration")
        declared.add(card_rel)

        try:
            validate_model_artifact(artifact_path, model.model_card)
        except ModelRuntimeError as exc:
            raise PackError(f"Findings Pack model {model.model_id!r} failed runtime validation") from exc

    # A model directory is an executable payload boundary.  Every file below
    # it must be named by an available declaration (cards included); this
    # rejects undeclared model/pickle/joblib/skops payloads before activation.
    if not any(model.release_status == "available" for model in (pack.models or {}).values()):
        return
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
            raise PackError("Findings Pack contains undeclared model artifacts")


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
    except (ModelRuntimeError, ValidationError, ValueError, TypeError) as exc:
        raise PackError(f"Findings Pack failed contract validation: {exc}") from exc
    _validate_required_artifacts(root, required_model_artifacts)
    return pack


class PackStore:
    """Durable active Findings Pack v2 store with crash-safe recovery."""

    def __init__(self, pack_dir: Path, *, bundled_dir: Path | None = None) -> None:
        self.pack_dir = Path(pack_dir)
        self.bundled_dir = Path(bundled_dir) if bundled_dir is not None else None
        self._pack: dict | None = None

    @property
    def last_known_good_dir(self) -> Path:
        return self.pack_dir.parent / f".{self.pack_dir.name}-last-known-good"

    def _validate_existing(self, directory: Path) -> dict:
        schema_path = directory / SCHEMA_FILENAME
        return validate_pack_directory(
            directory,
            schema_path=schema_path if schema_path.exists() else None,
            require_schema=False,
        )

    def _snapshot_last_known_good(self) -> None:
        if not self.pack_dir.is_dir():
            return
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{self.pack_dir.name}-known-good-",
                dir=self.pack_dir.parent,
            )
        )
        try:
            shutil.copytree(self.pack_dir, staging, dirs_exist_ok=True)
            previous = self.last_known_good_dir
            if previous.exists():
                shutil.rmtree(previous)
            os.replace(staging, previous)
        except (OSError, shutil.Error) as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise PackError("Findings Pack last-known-good snapshot failed") from exc

    def _replace_active_from(self, source: Path, *, prefix: str) -> None:
        staging = Path(tempfile.mkdtemp(prefix=prefix, dir=self.pack_dir.parent))
        quarantine: Path | None = None
        try:
            shutil.copytree(source, staging, dirs_exist_ok=True)
            self._validate_existing(staging)
            if self.pack_dir.exists():
                quarantine = Path(
                    tempfile.mkdtemp(
                        prefix=f".{self.pack_dir.name}-corrupt-",
                        dir=self.pack_dir.parent,
                    )
                )
                quarantine.rmdir()
                os.replace(self.pack_dir, quarantine)
            os.replace(staging, self.pack_dir)
            if quarantine is not None:
                shutil.rmtree(quarantine, ignore_errors=True)
        except (OSError, shutil.Error, PackError) as exc:
            shutil.rmtree(staging, ignore_errors=True)
            if quarantine is not None and not self.pack_dir.exists():
                try:
                    os.replace(quarantine, self.pack_dir)
                except OSError:
                    pass
            if isinstance(exc, PackError):
                raise
            raise PackError("Findings Pack activation directory could not be replaced") from exc

    def initialize(self) -> None:
        """Validate the active pack and recover a known-good copy if needed."""
        self.pack_dir.parent.mkdir(parents=True, exist_ok=True)
        if self.pack_dir.exists():
            try:
                self._validate_existing(self.pack_dir)
            except PackError:
                pass
            else:
                self._snapshot_last_known_good()
                return

        known_good = self.last_known_good_dir
        if known_good.is_dir():
            try:
                self._replace_active_from(
                    known_good,
                    prefix=f".{self.pack_dir.name}-recover-",
                )
            except PackError:
                pass
            else:
                return

        if self.bundled_dir is None:
            if self.pack_dir.exists():
                raise PackError("active Findings Pack failed validation")
            return
        if not self.bundled_dir.is_dir():
            raise PackError("bundled Findings Pack is unavailable")
        self._replace_active_from(
            self.bundled_dir,
            prefix=f".{self.pack_dir.name}-seed-",
        )
        self._snapshot_last_known_good()

    def load(self) -> dict:
        if self._pack is not None:
            return self._pack
        try:
            pack = self._validate_existing(self.pack_dir)
        except PackError:
            raise
        self._pack = pack
        # A validated load is the commit point for the durable recovery copy.
        self._snapshot_last_known_good()
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

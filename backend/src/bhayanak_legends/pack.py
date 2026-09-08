"""Findings Pack loading, schema validation, and atomic active-store support."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
from contextlib import contextmanager
from json import JSONDecodeError
from pathlib import Path
from typing import Iterable, Iterator

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


class PackActivationTransaction:
    """Atomically switch between immutable active-pack generations."""

    def __init__(
        self,
        store: "PackStore",
        *,
        original_pointer: str | None,
        original_path: Path | None,
        original_pack: dict | None,
        previous_path: Path | None,
        current_path: Path,
        migrated_legacy: bool,
    ) -> None:
        self._store = store
        self._original_pointer = original_pointer
        self._original_path = original_path
        self._original_pack = original_pack
        self._previous_path = previous_path
        self._current_path = current_path
        self._migrated_legacy = migrated_legacy
        self._closed = False
        self._lock_held = True

    def finalize(self) -> None:
        if self._closed:
            return
        try:
            if (
                self._previous_path is not None
                and self._previous_path != self._current_path
                and self._store._is_generation_path(self._previous_path)
            ):
                shutil.rmtree(self._previous_path, ignore_errors=True)
            self._store._cleanup_generations(keep=self._current_path)
        except OSError:
            # The pointer is already committed. Windows may retain handles to
            # an older generation, so cleanup is explicitly best-effort.
            pass
        finally:
            self._closed = True
            if self._lock_held:
                self._lock_held = False
                self._store._activation_lock.release()

    def rollback(self) -> None:
        if self._closed:
            return
        first_error: OSError | None = None
        pointer_restored = False
        try:
            try:
                if self._original_pointer is not None:
                    self._store._write_pointer_name(self._original_pointer)
                    self._store._active_dir = self._original_path
                elif self._migrated_legacy:
                    self._store._remove_pointer()
                    self._store._active_dir = self._store._logical_dir
                    if self._previous_path is not None and self._previous_path.exists():
                        shutil.rmtree(self._previous_path, ignore_errors=True)
                else:
                    self._store._remove_pointer()
                    self._store._active_dir = self._original_path
                pointer_restored = True
            except OSError as exc:
                first_error = exc
            self._store._pack = self._original_pack if pointer_restored else None
            try:
                if self._current_path.exists() and self._current_path != self._store._active_dir:
                    shutil.rmtree(self._current_path, ignore_errors=False)
            except OSError as exc:
                first_error = first_error or exc
        finally:
            self._closed = True
            if self._lock_held:
                self._lock_held = False
                self._store._activation_lock.release()
        if first_error is not None:
            raise first_error


class PackStore:
    """Durable active Findings Pack v2 store with crash-safe recovery.

    Active releases are immutable generation directories selected through an
    atomically replaced pointer file. Readers that already hold the previous
    generation continue to see a complete old pack while new readers resolve
    the complete new generation; no model/card file is ever mutated in place.
    The re-entrant store lock is held across each inference read and across
    pointer replacement, runtime reload, and transaction finalization so a
    reader cannot straddle generations.
    """

    _GENERATION_PREFIX = ".active-generation-"
    _POINTER_MAX_BYTES = 128

    def __init__(self, pack_dir: Path, *, bundled_dir: Path | None = None) -> None:
        self._logical_dir = Path(pack_dir)
        self.bundled_dir = Path(bundled_dir) if bundled_dir is not None else None
        self._active_dir: Path | None = None
        self._pack: dict | None = None
        self._activation_lock = threading.RLock()

    @contextmanager
    def read_transaction(self) -> Iterator[None]:
        """Hold the shared pack snapshot while reading or executing a model."""
        with self._activation_lock:
            yield

    @property
    def pack_dir(self) -> Path:
        """Return the currently selected immutable generation directory."""
        self._sync_active_reference()
        return self._active_dir or self._logical_dir

    @property
    def storage_parent(self) -> Path:
        """Return the durable parent used for release staging and generations."""
        return self._logical_dir.parent

    @property
    def last_known_good_dir(self) -> Path:
        return self._logical_dir.parent / f".{self._logical_dir.name}-last-known-good"

    @property
    def _pointer_path(self) -> Path:
        return self._logical_dir.parent / f".{self._logical_dir.name}-pointer"

    def _is_generation_path(self, path: Path) -> bool:
        return (
            path.parent == self._logical_dir.parent
            and path.name.startswith(self._GENERATION_PREFIX)
            and path.name != self._GENERATION_PREFIX
            and not path.is_symlink()
        )

    def _read_pointer_name(self) -> str | None:
        try:
            raw = self._pointer_path.read_bytes()
        except OSError:
            return None
        if len(raw) > self._POINTER_MAX_BYTES:
            return None
        try:
            value = raw.decode("ascii").strip()
        except UnicodeDecodeError:
            return None
        candidate = self._logical_dir.parent / value
        if (
            not value
            or candidate.name != value
            or not self._is_generation_path(candidate)
        ):
            return None
        return value

    def _pointer_target(self) -> Path | None:
        name = self._read_pointer_name()
        if name is None:
            return None
        return self._logical_dir.parent / name

    def _sync_active_reference(self) -> None:
        target = self._pointer_target()
        if target is not None and target.is_dir():
            self._active_dir = target
        elif self._active_dir is None:
            self._active_dir = self._logical_dir

    def _write_pointer_name(self, name: str) -> None:
        target = self._logical_dir.parent / name
        if not self._is_generation_path(target):
            raise PackError("Findings Pack generation pointer is invalid")
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self._pointer_path.name}.tmp-",
            dir=self._logical_dir.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with temporary.open("w", encoding="ascii", newline="\n") as stream:
                stream.write(name)
                stream.write("\n")
                stream.flush()
                try:
                    os.fsync(stream.fileno())
                except OSError:
                    pass
            os.replace(temporary, self._pointer_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _remove_pointer(self) -> None:
        self._pointer_path.unlink(missing_ok=True)

    def _new_generation_path(self) -> Path:
        temporary = Path(
            tempfile.mkdtemp(
                prefix=self._GENERATION_PREFIX,
                dir=self._logical_dir.parent,
            )
        )
        temporary.rmdir()
        return temporary

    def _generation_paths(self) -> list[Path]:
        return sorted(
            (
                path
                for path in self._logical_dir.parent.glob(f"{self._GENERATION_PREFIX}*")
                if path.is_dir() and self._is_generation_path(path)
            ),
            key=lambda path: path.name,
        )

    def _cleanup_generations(self, *, keep: Path | None = None) -> None:
        for path in self._generation_paths():
            if keep is None or path != keep:
                shutil.rmtree(path, ignore_errors=True)

    def _validate_existing(self, directory: Path) -> dict:
        schema_path = directory / SCHEMA_FILENAME
        return validate_pack_directory(
            directory,
            schema_path=schema_path if schema_path.exists() else None,
            require_schema=False,
        )

    def _snapshot_last_known_good(self) -> None:
        active = self.pack_dir
        if not active.is_dir():
            return
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{self._logical_dir.name}-known-good-",
                dir=self._logical_dir.parent,
            )
        )
        try:
            shutil.copytree(active, staging, dirs_exist_ok=True)
            previous = self.last_known_good_dir
            if previous.exists():
                shutil.rmtree(previous)
            os.replace(staging, previous)
        except (OSError, shutil.Error) as exc:
            shutil.rmtree(staging, ignore_errors=True)
            raise PackError("Findings Pack last-known-good snapshot failed") from exc

    def _replace_active_from(self, source: Path, *, prefix: str) -> None:
        staging = Path(tempfile.mkdtemp(prefix=prefix, dir=self._logical_dir.parent))
        quarantine: Path | None = None
        try:
            shutil.copytree(source, staging, dirs_exist_ok=True)
            self._validate_existing(staging)
            if self._logical_dir.exists():
                quarantine = Path(
                    tempfile.mkdtemp(
                        prefix=f".{self._logical_dir.name}-corrupt-",
                        dir=self._logical_dir.parent,
                    )
                )
                quarantine.rmdir()
                os.replace(self._logical_dir, quarantine)
            os.replace(staging, self._logical_dir)
            if quarantine is not None:
                shutil.rmtree(quarantine, ignore_errors=True)
        except (OSError, shutil.Error, PackError) as exc:
            shutil.rmtree(staging, ignore_errors=True)
            if quarantine is not None and not self._logical_dir.exists():
                try:
                    os.replace(quarantine, self._logical_dir)
                except OSError:
                    pass
            if isinstance(exc, PackError):
                raise
            raise PackError("Findings Pack activation directory could not be replaced") from exc
        self._active_dir = self._logical_dir

    def _select_generation_after_restart(self) -> Path | None:
        pointer_target = self._pointer_target()
        if pointer_target is not None and pointer_target.is_dir():
            try:
                self._validate_existing(pointer_target)
            except PackError:
                pass
            else:
                return pointer_target
        return None

    def initialize(self) -> None:
        """Validate the active pack and recover a known-good copy if needed."""
        self._logical_dir.parent.mkdir(parents=True, exist_ok=True)
        selected = self._select_generation_after_restart()
        if selected is not None:
            self._active_dir = selected
            self._write_pointer_name(selected.name)
            self._cleanup_generations(keep=selected)
            self._snapshot_last_known_good()
            return
        self._remove_pointer()
        self._cleanup_generations()

        known_good = self.last_known_good_dir
        if known_good.is_dir():
            try:
                self._replace_active_from(
                    known_good,
                    prefix=f".{self._logical_dir.name}-recover-",
                )
            except PackError:
                pass
            else:
                return

        if self._logical_dir.exists():
            try:
                self._validate_existing(self._logical_dir)
            except PackError:
                pass
            else:
                self._active_dir = self._logical_dir
                self._snapshot_last_known_good()
                return


        if self.bundled_dir is None:
            if self._logical_dir.exists():
                raise PackError("active Findings Pack failed validation")
            self._active_dir = self._logical_dir
            return
        if not self.bundled_dir.is_dir():
            raise PackError("bundled Findings Pack is unavailable")
        self._replace_active_from(
            self.bundled_dir,
            prefix=f".{self._logical_dir.name}-seed-",
        )
        self._snapshot_last_known_good()

    def activate_candidate(self, candidate: Path) -> PackActivationTransaction:
        """Publish a validated candidate as one immutable active generation."""
        candidate = Path(candidate)
        if not candidate.is_dir():
            raise PackError("Findings Pack candidate directory is missing")
        active_schema = self.pack_dir / SCHEMA_FILENAME
        candidate_schema = candidate / SCHEMA_FILENAME
        if not candidate_schema.is_file() and active_schema.is_file():
            shutil.copy2(active_schema, candidate_schema)
        self._activation_lock.acquire()
        original_pointer: str | None = None
        original_path: Path | None = self._logical_dir
        original_pack: dict | None = self._pack
        previous_path: Path | None = None
        migrated_legacy = False
        current_path: Path | None = None
        try:
            self._sync_active_reference()
            original_pointer = self._read_pointer_name()
            original_path = self._active_dir or self._logical_dir
            previous_path = original_path if original_path.exists() else None
            if (
                original_pointer is None
                and original_path == self._logical_dir
                and previous_path is not None
            ):
                previous_path = self._new_generation_path()
                # Copy the legacy directory instead of renaming it: Windows
                # may keep model files open while a release is activated.
                shutil.copytree(self._logical_dir, previous_path, dirs_exist_ok=True)
                # Publish the fallback pointer before the candidate move, so a
                # restart can recover the complete old generation.
                self._write_pointer_name(previous_path.name)
                self._active_dir = previous_path
                migrated_legacy = True

            current_path = self._new_generation_path()
            os.replace(candidate, current_path)
            self._write_pointer_name(current_path.name)
            self._active_dir = current_path
            self._pack = None
            return PackActivationTransaction(
                self,
                original_pointer=original_pointer,
                original_path=original_path,
                original_pack=original_pack,
                previous_path=previous_path,
                current_path=current_path,
                migrated_legacy=migrated_legacy,
            )
        except Exception:
            if current_path is not None and current_path.exists():
                shutil.rmtree(current_path, ignore_errors=True)
            pointer_restored = False
            try:
                if original_pointer is not None:
                    self._write_pointer_name(original_pointer)
                    self._active_dir = original_path
                    pointer_restored = True
                elif migrated_legacy:
                    self._remove_pointer()
                    self._active_dir = self._logical_dir
                    pointer_restored = True
                    if previous_path is not None and previous_path.exists():
                        shutil.rmtree(previous_path, ignore_errors=True)
                else:
                    self._remove_pointer()
                    self._active_dir = original_path
                    pointer_restored = True
            except OSError:
                pass
            self._pack = original_pack if pointer_restored else None
            self._activation_lock.release()
            raise

    def load(self) -> dict:
        with self.read_transaction():
            return self._load_unlocked()

    def _load_unlocked(self) -> dict:
        if self._pack is not None:
            return self._pack
        self._sync_active_reference()
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
    def reload(self) -> None:
        with self.read_transaction():
            self._pack = None
            target = self._pointer_target()
            if target is not None and target.is_dir():
                self._active_dir = target

    def active_path(self) -> Path:
        with self.read_transaction():
            self._load_unlocked()
            return self.pack_dir / PACK_FILENAME

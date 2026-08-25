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

from .pack_contract import validate_pack_semantics

from .models import FindingsPack


class PackError(Exception):
    pass


def validate_pack_directory(
    directory: Path,
    *,
    schema_path: Path | None = None,
    required_model_artifacts: Iterable[tuple[Path, str | None]] = (),
    require_schema: bool = True,
) -> dict:
    """Validate a staged pack before it can become active."""
    path = Path(directory) / "findings-pack.v1.json"
    selected_schema = schema_path or (Path(directory) / "pack.schema.json")
    if not path.is_file():
        raise PackError(f"Findings Pack missing at {path}")
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError) as exc:
        raise PackError(f"Findings Pack could not be read: {exc}") from exc
    if not isinstance(pack, dict):
        raise PackError("Findings Pack must be a JSON object")
    if require_schema and not selected_schema.is_file():
        raise PackError(f"Findings Pack schema missing at {selected_schema}")
    if selected_schema.is_file():
        try:
            schema = json.loads(selected_schema.read_text(encoding="utf-8"))
            jsonschema.validate(pack, schema)
        except (OSError, JSONDecodeError, jsonschema.SchemaError) as exc:
            raise PackError(f"Findings Pack schema could not be read: {exc}") from exc
        except jsonschema.ValidationError as exc:
            raise PackError(f"Findings Pack failed schema validation: {exc.message}") from exc
    try:
        FindingsPack.model_validate(pack)
    except ValueError as exc:
        raise PackError(f"Findings Pack failed model validation: {exc}") from exc
    for artifact_path, expected_sha256 in required_model_artifacts:
        if not artifact_path.is_file():
            raise PackError(f"Findings Pack model artifact missing at {artifact_path}")
        if expected_sha256:
            digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            if digest != expected_sha256:
                raise PackError(f"Findings Pack model artifact hash mismatch: {artifact_path}")
    return pack


class PackStore:
    def __init__(self, pack_dir: Path, *, bundled_dir: Path | None = None) -> None:
        self.pack_dir = Path(pack_dir)
        self.bundled_dir = Path(bundled_dir) if bundled_dir is not None else None
        self._pack: dict | None = None

    def initialize(self) -> None:
        """Commit the bundled seed once, without ever writing to its directory."""
        active_pack = self.pack_dir / "findings-pack.v1.json"
        self.pack_dir.parent.mkdir(parents=True, exist_ok=True)
        if active_pack.exists():
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
            # Use the same schema validation as every active pack load before
            # making the staged copy visible as the active pack.
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
        path = self.pack_dir / "findings-pack.v1.json"
        schema_path = self.pack_dir / "pack.schema.json"
        if not path.exists():
            raise PackError(f"Findings Pack missing at {path}")
        try:
            pack = json.loads(path.read_text())
        except (OSError, JSONDecodeError) as e:
            raise PackError(f"Findings Pack could not be read: {e}") from e
        if not isinstance(pack, dict):
            raise PackError("Findings Pack must be a JSON object")
        if schema_path.exists():
            try:
                schema = json.loads(schema_path.read_text())
                jsonschema.validate(pack, schema)
            except (OSError, JSONDecodeError, jsonschema.SchemaError) as e:
                raise PackError(f"Findings Pack schema could not be read: {e}") from e
            except jsonschema.ValidationError as e:
                raise PackError(f"Findings Pack failed schema validation: {e.message}") from e
        try:
            validate_pack_semantics(pack)
        except ValueError as e:
            raise PackError(f"Findings Pack failed semantic validation: {e}") from e
        try:
            FindingsPack.model_validate(pack)
        except ValidationError as e:
            raise PackError("Findings Pack failed contract validation") from e
        if pack.get("schema_version") != 1:
            raise PackError(f"unsupported pack schema_version {pack.get('schema_version')}")
        self._pack = pack
        return pack

    def version(self) -> str:
        pack = self.load()
        return str(pack.get("pack_version") or f"v{pack['schema_version']}")

    def reload(self) -> None:
        self._pack = None

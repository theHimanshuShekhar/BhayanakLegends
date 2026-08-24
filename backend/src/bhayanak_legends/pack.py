import json
from pathlib import Path

import jsonschema


class PackError(Exception):
    pass


class PackStore:
    def __init__(self, pack_dir: Path) -> None:
        self.pack_dir = pack_dir
        self._pack: dict | None = None

    def load(self) -> dict:
        if self._pack is not None:
            return self._pack
        path = self.pack_dir / "findings-pack.v1.json"
        schema_path = self.pack_dir / "pack.schema.json"
        if not path.exists():
            raise PackError(f"Findings Pack missing at {path}")
        pack = json.loads(path.read_text())
        if schema_path.exists():
            schema = json.loads(schema_path.read_text())
            try:
                jsonschema.validate(pack, schema)
            except jsonschema.ValidationError as e:
                raise PackError(f"Findings Pack failed schema validation: {e.message}") from e
        if pack.get("schema_version") != 1:
            raise PackError(f"unsupported pack schema_version {pack.get('schema_version')}")
        self._pack = pack
        return pack

    def version(self) -> str:
        return f"v{self.load()['schema_version']}"

    def reload(self) -> None:
        self._pack = None

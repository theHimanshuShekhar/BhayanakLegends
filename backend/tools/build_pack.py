#!/usr/bin/env python3
"""Validate and copy the LoLTrends Findings Pack v2 artifact.

LoLTrends is the sole producer of population evidence.  Bhayanak Legends owns
only this consumer-side bridge: it validates an explicitly supplied exported
artifact against the established Pack v2 schema and copies it without
recomputing, renaming, or filling any population field.

Usage::

    uv run python tools/build_pack.py --artifact PATH [--out DIR]
    uv run python tools/build_pack.py --bootstrap [--out DIR]

``PATH`` may be the exported ``findings-pack.v2.json`` file or a directory
containing that file and any declared model artifacts.  ``--bootstrap`` copies
the checked-in diagnostic seed; it never derives values from local data.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import ValidationError as PydanticValidationError

from bhayanak_legends.pack import PackError, validate_pack_directory
from bhayanak_legends.pack_v2 import FindingsPackV2, validate_pack_v2_semantics

SCHEMA_FILENAME = "pack.schema.json"
PACK_FILENAME = "findings-pack.v2.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_SOURCE = REPO_ROOT / "pack"


class ArtifactContractError(ValueError):
    """Raised when an exported artifact cannot satisfy the consumer contract."""


def build_schema() -> dict[str, Any]:
    """Return the unchanged canonical JSON Schema consumed by the app."""
    schema = FindingsPackV2.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return schema


def _artifact_path(source: Path) -> Path:
    source = Path(source)
    if source.is_dir():
        source = source / PACK_FILENAME
    if not source.is_file():
        raise ArtifactContractError(f"Findings Pack artifact is missing: {source}")
    if source.name != PACK_FILENAME:
        raise ArtifactContractError(
            f"Findings Pack artifact must be named {PACK_FILENAME!r}; got {source.name!r}"
        )
    return source


def _format_path(path: object) -> str:
    if isinstance(path, (list, tuple)):
        return ".".join(str(part) for part in path) or "<root>"
    return str(path)


def _schema_failure(error: jsonschema.ValidationError) -> ArtifactContractError:
    path = _format_path(error.absolute_path)
    return ArtifactContractError(
        "cross-repo Pack v2 contract mismatch: supplied LoLTrends artifact does not "
        "satisfy Bhayanak's established consumer schema; "
        f"{path}: {error.message}. No translation is performed; LoLTrends must export "
        "the exact Bhayanak Pack v2 contract."
    )


def _pydantic_failure(error: PydanticValidationError) -> ArtifactContractError:
    details = []
    for item in error.errors()[:8]:
        location = _format_path(item.get("loc", ()))
        details.append(f"{location}: {item.get('msg', 'invalid value')}")
    suffix = "; ".join(details) or str(error)
    return ArtifactContractError(
        "cross-repo Pack v2 contract mismatch: supplied LoLTrends artifact does not "
        "satisfy Bhayanak's established consumer schema; "
        f"{suffix}. No translation is performed; LoLTrends must export the exact "
        "Bhayanak Pack v2 contract."
    )


def _read_artifact(source: Path) -> tuple[bytes, dict[str, Any]]:
    path = _artifact_path(source)
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
        raise ArtifactContractError(
            f"Findings Pack artifact could not be read: {path}: {exc}"
        ) from exc
    supplied_schema = path.parent / SCHEMA_FILENAME
    if supplied_schema.is_file():
        try:
            declared_schema = json.loads(supplied_schema.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, JSONDecodeError) as exc:
            raise ArtifactContractError(
                f"Findings Pack artifact schema could not be read: {supplied_schema}: {exc}"
            ) from exc
        if declared_schema != build_schema():
            raise ArtifactContractError(
                "cross-repo Pack v2 contract mismatch: supplied artifact "
                f"{SCHEMA_FILENAME} differs from Bhayanak's established consumer "
                "schema. No translation is performed; LoLTrends must publish the "
                "exact companion schema."
            )

    if not isinstance(payload, dict):
        raise ArtifactContractError(
            "cross-repo Pack v2 contract mismatch: supplied artifact root must be a JSON object; "
            "no translation is performed"
        )

    try:
        jsonschema.Draft202012Validator(build_schema()).validate(payload)
    except jsonschema.ValidationError as exc:
        raise _schema_failure(exc) from exc
    try:
        parsed = FindingsPackV2.model_validate(payload)
        validate_pack_v2_semantics(parsed)
    except PydanticValidationError as exc:
        raise _pydantic_failure(exc) from exc
    except (TypeError, ValueError) as exc:
        raise ArtifactContractError(
            "cross-repo Pack v2 contract mismatch: supplied LoLTrends artifact fails "
            f"Bhayanak semantic validation: {exc}. No translation is performed; "
            "LoLTrends must export the exact Bhayanak Pack v2 contract."
        ) from exc
    return raw, payload


def _copy_tree_contents(source_dir: Path, destination: Path) -> None:
    for child in source_dir.iterdir():
        if child.name == SCHEMA_FILENAME or child.name == PACK_FILENAME:
            continue
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def _write_schema(path: Path) -> None:
    path.write_text(
        json.dumps(build_schema(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def copy_pack(source: Path, output: Path) -> dict[str, Any]:
    """Validate and copy one exported artifact into a complete pack directory."""
    source = Path(source)
    artifact_file = _artifact_path(source)
    raw, payload = _read_artifact(source)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Stage before replacing the output so invalid or interrupted copies never
    # leave a half-written candidate.  The source bytes are copied verbatim;
    # this bridge does not normalize or reinterpret producer values.
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}-artifact-", dir=output.parent))
    try:
        if source.is_dir():
            _copy_tree_contents(source, staging)
        (staging / PACK_FILENAME).write_bytes(raw)
        _write_schema(staging / SCHEMA_FILENAME)
        try:
            validate_pack_directory(staging)
        except PackError as exc:
            raise ArtifactContractError(
                "cross-repo Pack v2 artifact bundle is incomplete or incompatible: "
                f"{exc}. No translation is performed."
            ) from exc

        resolved_output = output.resolve()
        resolved_source = source.resolve()
        if resolved_output == resolved_source or resolved_output == artifact_file.resolve().parent:
            # Bootstrap commonly targets the checked-in pack directory itself.
            # Keep that directory in place rather than deleting the source while
            # it is also the destination.
            for child in staging.iterdir():
                target = output / child.name
                if child.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(child, target)
                else:
                    os.replace(child, target)
            staging.rmdir()
        else:
            if output.exists():
                shutil.rmtree(output)
            os.replace(staging, output)
    except ArtifactContractError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except (OSError, shutil.Error) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise ArtifactContractError(f"Findings Pack artifact copy failed: {exc}") from exc
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--artifact",
        "--findings-pack",
        dest="artifact",
        type=Path,
        help="explicit LoLTrends-exported findings-pack.v2.json or artifact directory",
    )
    source.add_argument(
        "--bootstrap",
        action="store_true",
        help="copy the checked-in diagnostic seed directory and declared model assets",
    )
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "pack")
    args = parser.parse_args()

    input_path = BOOTSTRAP_SOURCE if args.bootstrap else args.artifact
    assert input_path is not None
    try:
        pack = copy_pack(input_path, args.out)
    except ArtifactContractError as exc:
        parser.error(str(exc))

    print("Findings Pack v2 artifact bridge")
    print(f"  source: {input_path}")
    print(f"  pack_version: {pack.get('pack_version')}")
    print(f"  schema_version: {pack.get('schema_version')}")
    print(f"  wrote: {Path(args.out) / PACK_FILENAME}")


if __name__ == "__main__":
    main()

"""Helpers for constructing complete Findings Pack release fixtures."""

from __future__ import annotations

import copy
import functools
import json
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = ROOT / "pack"
PACK_PATH = PACK_DIR / "findings-pack.v2.json"
SCHEMA_PATH = PACK_DIR / "pack.schema.json"

_MODEL_ARTIFACT_FIELDS = ("path", "model_card_path")
_MODEL_PIN_FIELDS = (
    "path",
    "sha256",
    "size",
    "model_card_path",
    "model_card_sha256",
    "model_card_size",
)


@functools.lru_cache(maxsize=1)
def _canonical_source() -> dict[str, Any]:
    return json.loads(PACK_PATH.read_text(encoding="utf-8"))


def canonical_pack() -> dict[str, Any]:
    """Load a fresh copy of the checked-in Findings Pack payload."""
    return copy.deepcopy(_canonical_source())


def minimal_pack(pack: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a small valid payload retaining canonical model declarations."""
    source = pack if pack is not None else _canonical_source()
    result = dict(source)
    for key in (
        "patch_range",
        "dataset",
        "feature_contracts",
        "provenance",
        "comeback_odds",
        "build_evidence",
        "models",
    ):
        result[key] = copy.deepcopy(source[key])
    result["findings"] = [
        copy.deepcopy(row)
        for row in source["findings"]
        if row.get("key") == "surrender_advisor"
    ]
    if not result["findings"]:
        raise AssertionError("canonical pack has no withheld Surrender Advisor finding")
    for key in (
        "habits",
        "objectives",
        "ban_context",
        "tier_list",
        "matchup_examples",
        "checkpoints",
        "route_archetypes",
    ):
        result[key] = []
    return result


def available_models(pack: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    """Yield available model declarations in their canonical pack order."""
    models = pack.get("models")
    if not isinstance(models, dict):
        return ()
    return (
        (key, model)
        for key, model in models.items()
        if isinstance(key, str)
        and isinstance(model, dict)
        and model.get("release_status") == "available"
    )


def declared_model_assets(
    pack: dict[str, Any],
    source_dir: Path,
    *,
    exclude_model_keys: Iterable[str] = (),
) -> dict[str, bytes]:
    """Read each available declaration's artifact and model-card bytes."""
    excluded = set(exclude_model_keys)
    assets: dict[str, bytes] = {}
    for model_key, model in available_models(pack):
        if model_key in excluded:
            continue
        artifact = model.get("artifact")
        if not isinstance(artifact, dict):
            raise AssertionError(f"available model {model_key!r} has no artifact")
        for field in _MODEL_ARTIFACT_FIELDS:
            relative = artifact.get(field)
            if not isinstance(relative, str):
                raise AssertionError(f"available model {model_key!r} has no {field}")
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts:
                raise AssertionError(f"unsafe model fixture path: {relative!r}")
            assets[relative] = (source_dir / path).read_bytes()
    return assets


def canonical_model_assets(
    pack: dict[str, Any] | None = None,
    *,
    exclude_model_keys: Iterable[str] = (),
) -> dict[str, bytes]:
    """Read all checked-in assets named by available canonical declarations."""
    return declared_model_assets(
        _canonical_source() if pack is None else pack,
        PACK_DIR,
        exclude_model_keys=exclude_model_keys,
    )


def model_manifest_pins(pack: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive release manifest pins from every available declaration."""
    pins: list[dict[str, Any]] = []
    for model_key, model in available_models(pack):
        artifact = model.get("artifact")
        if not isinstance(artifact, dict):
            raise AssertionError(f"available model {model_key!r} has no artifact")
        pin: dict[str, Any] = {}
        for field in _MODEL_PIN_FIELDS:
            value = artifact.get(field)
            if value is None:
                raise AssertionError(f"available model {model_key!r} has no {field}")
            pin[field] = value
        pins.append(pin)
    return pins


def write_assets(destination: Path, assets: dict[str, bytes]) -> None:
    """Write relative model assets below a fixture directory."""
    for relative, data in assets.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def write_canonical_pack(destination: Path, pack: dict[str, Any] | None = None) -> None:
    """Write the canonical payload, schema, and all canonical model assets."""
    pack = canonical_pack() if pack is None else pack
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "findings-pack.v2.json").write_text(
        json.dumps(pack, separators=(",", ":")),
        encoding="utf-8",
    )
    (destination / "pack.schema.json").write_bytes(SCHEMA_PATH.read_bytes())
    write_assets(destination, canonical_model_assets(pack))

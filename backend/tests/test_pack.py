"""Validate the canonical Findings Pack v2 bundle and producer boundary."""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from pydantic import ValidationError as PydanticValidationError

from bhayanak_legends.pack import PackError, PackStore
from bhayanak_legends.pack_v2 import FindingsPackV2
from pack_fixture_helpers import canonical_model_assets

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = REPO_ROOT / "pack"
SCHEMA = json.loads((PACK_DIR / "pack.schema.json").read_text(encoding="utf-8"))
PACK = json.loads((PACK_DIR / "findings-pack.v2.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location(
        "build_pack", REPO_ROOT / "backend" / "tools" / "build_pack.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pack_matches_canonical_schema_and_strict_model(generator):
    Draft202012Validator.check_schema(SCHEMA)
    Draft202012Validator(SCHEMA).validate(PACK)

    model = FindingsPackV2.model_validate(PACK)

    assert SCHEMA == generator.build_schema()
    assert model.schema_version == 2
    assert model.pack_version == "v2"
    assert model.dataset.eligible_matches > 0


def test_schema_rejects_unknown_root_and_row_fields():
    broken = copy.deepcopy(PACK)
    broken["future_table"] = {"new_metric": 1}
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(broken)

    broken = copy.deepcopy(PACK)
    broken["findings"][0]["future_metric"] = 1
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(broken)


def test_pack_store_wraps_unreadable_json_as_pack_error(tmp_path: Path):
    pack_dir = tmp_path / "active"
    pack_dir.mkdir()
    (pack_dir / "findings-pack.v2.json").write_bytes(b"\xff")

    with pytest.raises(PackError):
        PackStore(pack_dir).load()


def test_v2_comeback_rows_use_the_declared_team_state_contract():
    assert [
        (row["lower_bound"], row["upper_bound"])
        for row in PACK["comeback_odds"]
    ] == [(2000, 3000), (3000, 5000), (5000, None)]
    assert all(row["feature"] == "team_gold_diff_15m" for row in PACK["comeback_odds"])
    assert all(
        row["feature_contract_version"] == "loltrends-parity-v2"
        for row in PACK["comeback_odds"]
    )


def test_v2_semantics_reject_mismatched_comeback_contract():
    broken = copy.deepcopy(PACK)
    broken["comeback_odds"][0]["feature_contract_version"] = "wrong-contract"

    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)


def test_v2_semantics_require_withheld_findings_to_explain_release():
    broken = copy.deepcopy(PACK)
    finding = next(row for row in broken["findings"] if row["key"] == "surrender_advisor")
    finding.pop("release_reason", None)

    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)

def test_v2_semantics_pin_mastery_and_ban_release_values():
    broken = copy.deepcopy(PACK)
    next(row for row in broken["findings"] if row["key"] == "mastery_premium")["value"] = 1.95
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)

    broken = copy.deepcopy(PACK)
    next(row for row in broken["ban_context"] if row["metric_kind"] == "ban_rate_win_rate_correlation")["value"] = 0.07
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)


def test_v2_semantics_keep_objective_families_typed_and_diagnostic():
    broken = copy.deepcopy(PACK)
    row = next(
        row
        for row in broken["objectives"]
        if row["metric_kind"] == "before_time_rate"
    )
    row["window"] = {
        "kind": "full_match",
        "start_seconds": None,
        "end_seconds": None,
        "include_start": True,
        "include_end": True,
        "rule": "wrong window",
    }
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)

    broken = copy.deepcopy(PACK)
    broken["objectives"][0]["metric_kind"] = "matched_effect"
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)


def test_v2_semantics_reject_noncanonical_tier_and_matchup_rows():
    broken = copy.deepcopy(PACK)
    broken["tier_list"][0], broken["tier_list"][1] = broken["tier_list"][1], broken["tier_list"][0]
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)

    broken = copy.deepcopy(PACK)
    row = broken["matchup_examples"][0]
    row["estimate"] = row["interval"]["upper"] + 0.01
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)


def test_v2_semantics_bound_route_outcomes_and_comeback_sample_floor():
    broken = copy.deepcopy(PACK)
    broken["route_archetypes"][0]["observed_outcome"] = 1.01
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)

    broken = copy.deepcopy(PACK)
    broken["comeback_odds"][0]["sample"] = 199
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)


def test_every_evidence_row_references_matching_provenance():
    model = FindingsPackV2.model_validate(PACK)
    groups = (
        [model.dataset],
        model.findings,
        model.habits,
        model.objectives,
        model.comeback_odds,
        model.ban_context,
        model.tier_list,
        model.matchup_examples,
        model.checkpoints,
        model.route_archetypes,
        [model.build_evidence],
    )
    for rows in groups:
        for row in rows:
            provenance = model.provenance[row.provenance_key]
            assert row.source_document == provenance.source_document
            assert row.source_section == provenance.source_section
            assert row.source_ref == provenance.source_ref


def test_bootstrap_copies_checked_in_diagnostic_seed(tmp_path: Path):
    output_dir = tmp_path / "bootstrap"
    generator_path = REPO_ROOT / "backend" / "tools" / "build_pack.py"
    subprocess.run(
        [
            sys.executable,
            str(generator_path),
            "--bootstrap",
            "--out",
            str(output_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (output_dir / "findings-pack.v2.json").read_bytes() == (
        PACK_DIR / "findings-pack.v2.json"
    ).read_bytes()
    generated_schema = json.loads(
        (output_dir / "pack.schema.json").read_text(encoding="utf-8")
    )
    assert generated_schema == SCHEMA
    for relative, expected in canonical_model_assets(PACK).items():
        assert (output_dir / relative).read_bytes() == expected
    seed = json.loads((output_dir / "findings-pack.v2.json").read_text(encoding="utf-8"))
    assert seed["dataset"]["tracked_players"] > 0
    assert seed["dataset"]["patch_buckets"] == len(seed["dataset"]["patches"])
    assert seed["dataset"]["median_game_minutes"] != 0
    assert seed["dataset"]["surrender_rate"] is not None
    FindingsPackV2.model_validate(seed)


def test_generator_rejects_bare_json_with_available_models(tmp_path: Path):
    artifact = tmp_path / "findings-pack.v2.json"
    artifact_bytes = (PACK_DIR / "findings-pack.v2.json").read_bytes()
    artifact.write_bytes(artifact_bytes)
    output_dir = tmp_path / "output"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "backend" / "tools" / "build_pack.py"),
            "--artifact",
            str(artifact),
            "--out",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "artifact bundle is incomplete" in result.stderr
    assert not output_dir.exists()


def test_generator_copies_explicit_directory_without_recomputation(tmp_path: Path):
    artifact_dir = tmp_path / "artifact"
    shutil.copytree(PACK_DIR, artifact_dir)
    artifact_bytes = (artifact_dir / "findings-pack.v2.json").read_bytes()
    output_dir = tmp_path / "output"

    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "backend" / "tools" / "build_pack.py"),
            "--artifact",
            str(artifact_dir),
            "--out",
            str(output_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (output_dir / "findings-pack.v2.json").read_bytes() == artifact_bytes
    for relative, expected in canonical_model_assets(PACK).items():
        assert (output_dir / relative).read_bytes() == expected
    FindingsPackV2.model_validate(
        json.loads((output_dir / "findings-pack.v2.json").read_text(encoding="utf-8"))
    )


def test_generator_fails_closed_on_incompatible_upstream_shape(tmp_path: Path):
    artifact = tmp_path / "findings-pack.v2.json"
    broken = copy.deepcopy(PACK)
    broken["benchmarks"] = []
    artifact.write_text(json.dumps(broken), encoding="utf-8")
    output_dir = tmp_path / "output"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "backend" / "tools" / "build_pack.py"),
            "--artifact",
            str(artifact),
            "--out",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "cross-repo Pack v2 contract mismatch" in result.stderr
    assert "benchmarks" in result.stderr
    assert not output_dir.exists()


def test_header_and_release_contract_fields_are_v2_only():
    assert PACK["schema_version"] == 2
    assert PACK["pack_version"] == "v2"
    assert PACK["feature_contracts"]["personal_history"] == "loltrends-parity-v2"
    assert set(PACK) == {
        "schema_version",
        "pack_version",
        "generated_at",
        "patch_range",
        "dataset",
        "feature_contracts",
        "provenance",
        "findings",
        "habits",
        "objectives",
        "comeback_odds",
        "ban_context",
        "tier_list",
        "matchup_examples",
        "checkpoints",
        "route_archetypes",
        "build_evidence",
        "models",
    }


@pytest.mark.parametrize("field", ["schema_version", "pack_version"])
def test_v2_header_fields_cannot_be_downgraded(field: str):
    broken = copy.deepcopy(PACK)
    broken[field] = 1 if field == "schema_version" else ""

    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)

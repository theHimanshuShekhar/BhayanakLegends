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

from bhayanak_legends.pack import PackError, PackStore, validate_pack_directory
from bhayanak_legends.pack_v1 import FindingsPackV1
from bhayanak_legends.pack_v2 import FindingsPackV2
from pack_fixture_helpers import canonical_model_assets

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = REPO_ROOT / "pack"
SCHEMA = json.loads((PACK_DIR / "pack.schema.json").read_text(encoding="utf-8"))
PACK = json.loads((PACK_DIR / "findings-pack.v2.json").read_text(encoding="utf-8"))
PACK_V1_FIXTURE = Path(__file__).parent / "fixtures" / "findings-pack.v1.json"


def test_pack_checkout_attributes_pin_text_and_binary_assets():
    text_assets = (
        "pack/findings-pack.v2.json",
        "pack/pack.schema.json",
        "pack/models/live-wp-v2.model-card.json",
        "pack/models/personal-what-if-v2.model-card.json",
    )
    binary_assets = (
        "pack/models/live-wp-v2.onnx",
        "pack/models/personal-what-if-v2.onnx",
        "pack/findings-pack.v2.zip",
    )
    paths = text_assets + binary_assets
    result = subprocess.run(
        ["git", "check-attr", "text", "eol", "--", *paths],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    attributes = {}
    for line in result.stdout.splitlines():
        path, name, value = line.split(": ", 2)
        attributes[(path, name)] = value

    for path in text_assets:
        assert attributes[(path, "text")] == "set"
        assert attributes[(path, "eol")] == "lf"
        assert b"\r\n" not in (REPO_ROOT / path).read_bytes()
    for path in binary_assets:
        assert attributes[(path, "text")] == "unset"


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


def test_legacy_v1_pack_dispatch_preserves_historical_contract(tmp_path: Path):
    payload = json.loads(PACK_V1_FIXTURE.read_text(encoding="utf-8"))
    (tmp_path / "findings-pack.v1.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    loaded = validate_pack_directory(tmp_path)
    model = FindingsPackV1.model_validate(loaded)

    assert model.schema_version == 1
    assert model.comeback_feature_contract.feature == "gold_diff_15"
    assert [row.gold_deficit_at_15 for row in model.comeback_odds] == [-2000, -5000, -7000]


def test_v2_comeback_rows_pin_sign_eligibility_tier_and_population_provenance():
    rows = PACK["comeback_odds"]
    assert all(
        row["sign_convention"] == "own_team_total_gold_minus_enemy_team_total_gold"
        and row["eligibility"]
        == "non-surrendered Eligible Match; populated frame at/after 900s proves reachability; latest valid frame at/before 900s; exactly ten unique participants in two unambiguous five-player teams; finite gold for all ten"
        and row["tier"] == "diagnostic"
        for row in rows
    )
    assert PACK["feature_contracts"]["personal_history"] == "loltrends-parity-v2"
    assert PACK["feature_contracts"]["population"] == "loltrends-population-v2"
    assert PACK["provenance"]["comeback_odds"]["feature_contract_version"] == "loltrends-population-v2"


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


@pytest.mark.parametrize(
    "field",
    ["sign_convention", "eligibility", "tier"],
)
def test_v2_comeback_rows_reject_malformed_contract_declarations(field: str):
    broken = copy.deepcopy(PACK)
    broken["comeback_odds"][0][field] = "wrong"
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)


def test_v2_comeback_rows_reject_root_or_provenance_contract_mismatches():
    broken = copy.deepcopy(PACK)
    broken["feature_contracts"]["personal_history"] = "wrong"
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)

    broken = copy.deepcopy(PACK)
    broken["provenance"]["comeback_odds"]["feature_contract_version"] = "wrong"
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)


def test_v2_comeback_rows_reject_nonfinite_rates():
    broken = copy.deepcopy(PACK)
    broken["comeback_odds"][0]["rate"] = float("nan")
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)


def test_v2_comeback_rows_require_explicit_join_declarations():
    broken = copy.deepcopy(PACK)
    broken["comeback_odds"][0].pop("sign_convention")
    with pytest.raises(PydanticValidationError):
        FindingsPackV2.model_validate(broken)

def test_release_activation_rejects_legacy_v1_candidate(tmp_path: Path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "findings-pack.v1.json").write_bytes(PACK_V1_FIXTURE.read_bytes())
    with pytest.raises(PackError, match="v2-only"):
        PackStore(tmp_path / "active").activate_candidate(candidate)


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


def test_v2_comeback_release_accepts_future_producer_rates_and_samples() -> None:
    future = copy.deepcopy(PACK)
    for row, rate, sample in zip(
        future["comeback_odds"],
        (0.31, 0.21, 0.11),
        (201, 202, 203),
    ):
        row["rate"] = rate
        row["sample"] = sample
    FindingsPackV2.model_validate(future)


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

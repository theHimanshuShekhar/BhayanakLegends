"""Validate the canonical Findings Pack v2 bundle and producer boundary."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from pydantic import ValidationError as PydanticValidationError

from bhayanak_legends.pack import PackError, PackStore
from bhayanak_legends.pack_v2 import FindingsPackV2

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


def test_generator_reproduces_deterministically_from_declared_feature_store(tmp_path: Path):
    pd = pytest.importorskip("pandas")
    rows = [
        {
            "match_id": f"match-{role.lower()}",
            "champion_name": "Ahri",
            "opponent_champion_name": None,
            "role": role,
            "win": True,
            "patch": "16.16",
            "lane_minions_first_10m": 10,
        }
        for role in ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")
    ]
    feature_store = tmp_path / "feature_store"
    feature_store.mkdir()
    pd.DataFrame(rows).to_parquet(feature_store / "analysis_rows.parquet")
    pd.DataFrame(
        [{"match_id": row["match_id"], "champion_name": "Ahri"} for row in rows]
    ).to_parquet(feature_store / "champion_bans.parquet")

    outputs = []
    generator = REPO_ROOT / "backend" / "tools" / "build_pack.py"
    for index in (1, 2):
        output_dir = tmp_path / f"output-{index}"
        subprocess.run(
            [
                sys.executable,
                str(generator),
                "--feature-store",
                str(feature_store),
                "--out",
                str(output_dir),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        generated = json.loads(
            (output_dir / "findings-pack.v2.json").read_text(encoding="utf-8")
        )
        generated_schema = json.loads(
            (output_dir / "pack.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(generated_schema).validate(generated)
        FindingsPackV2.model_validate(generated)
        assert generated_schema == SCHEMA
        generated.pop("generated_at")
        outputs.append(generated)
    assert outputs[0] == outputs[1]


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

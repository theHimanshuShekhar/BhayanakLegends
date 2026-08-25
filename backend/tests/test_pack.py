"""Validate the shipped Findings Pack v1 against its schema and the research contract."""

import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from bhayanak_legends.models import FindingsPack
import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = REPO_ROOT / "pack"
SCHEMA = json.loads((PACK_DIR / "pack.schema.json").read_text())
PACK = json.loads((PACK_DIR / "findings-pack.v1.json").read_text())


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location(
        "build_pack", REPO_ROOT / "backend" / "tools" / "build_pack.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = REPO_ROOT / "pack"
SCHEMA = json.loads((PACK_DIR / "pack.schema.json").read_text())
PACK = json.loads((PACK_DIR / "findings-pack.v1.json").read_text())


def finding(key: str) -> dict:
    return next(f for f in PACK["findings"] if f["key"] == key)


# Imperative phrasing detector: a diagnostic statement containing any of these
# word stems is instructing the player, violating ADR-0003.
IMPERATIVE = re.compile(
    r"\b(ban|bans|banned|take|takes|play|plays|pick|picks|prioritize|prioritise|focus|"
    r"roam|roams|recall|recalls|buy|buys|build|builds|dodge|surrender|stack|contest|"
    r"contests|farm|ward|deny|steal|spend|skip|stop|target|consider|prefer|avoid|"
    r"recommend|choose|keep|grab|always|never|should)\b",
    re.IGNORECASE,
)




def test_schema_accepts_unknown_future_tables_only_as_objects():
    future = copy.deepcopy(PACK)
    future["future_table"] = {"new_metric": 1}
    Draft202012Validator(SCHEMA).validate(future)

    future["future_table"] = ["not", "a", "table"]
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(future)
def test_pack_matches_schema_and_strict_model():
    Draft202012Validator.check_schema(SCHEMA)
    Draft202012Validator(SCHEMA).validate(PACK)

    model = FindingsPack.model_validate(PACK)

    assert model.pack_version == "v1"


NUMERIC_TABLES = (
    "dataset",
    "findings",
    "habits",
    "objectives",
    "comeback_odds",
    "ban_advisor",
    "trap_picks",
    "tier_list",
    "matchup_examples",
    "benchmarks",
    "checkpoints",
)


def test_every_numeric_table_has_complete_provenance():
    assert set(PACK["provenance"]) == set(NUMERIC_TABLES)
    for table in NUMERIC_TABLES:
        provenance = PACK["provenance"][table]
        assert provenance["source_document"]
        assert provenance["source_section"]
        assert re.fullmatch(r"[0-9a-f]{64}", provenance["feature_store_manifest_sha256"])
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", provenance["generator_revision"])
        assert provenance["feature_contract_version"] == "loltrends-parity-v1"


@pytest.mark.parametrize(
    ("table", "field", "value"),
    [
        ("tier_list", "provenance", None),
        ("tier_list", "feature_store_manifest_sha256", "not-a-sha"),
        ("tier_list", "feature_contract_version", "loltrends-parity-v0"),
    ],
)
def test_schema_rejects_invalid_table_provenance(table, field, value):
    broken = copy.deepcopy(PACK)
    if field == "provenance":
        del broken["provenance"][table]
    else:
        broken["provenance"][table][field] = value
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(broken)


def test_generator_reproduces_from_declared_feature_store(tmp_path):
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
        generated = json.loads((output_dir / "findings-pack.v1.json").read_text())
        generated.pop("generated_at")
        outputs.append(generated)
    assert outputs[0] == outputs[1]


def test_header_fields():
    assert PACK["schema_version"] == 1
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", PACK["generated_at"])
    assert PACK["dataset"]["matches"] > 0
    assert PACK["dataset"]["player_games"] >= PACK["dataset"]["matches"]
    assert len(PACK["dataset"]["patches"]) == 2


def test_findings_pack_ignores_unknown_future_fields_and_tables():
    future = copy.deepcopy(PACK)
    future["pack_version"] = "v1"
    future["benchmarks"][0]["future_metric"] = 1
    future["benchmarks"][0]["feature_contract"]["future_feature"] = "future-v2"

    validated = FindingsPack.model_validate(future)

    assert validated.pack_version == "v1"
    assert not hasattr(validated, "future_table")
    assert not hasattr(validated.benchmarks[0], "future_metric")


@pytest.mark.parametrize("value", [None, 1, ""])
def test_findings_pack_rejects_invalid_pack_version(value):
    broken = copy.deepcopy(PACK)
    broken["pack_version"] = value

    with pytest.raises(PydanticValidationError):
        FindingsPack.model_validate(broken)


def test_findings_pack_defaults_missing_version_to_v1():
    legacy = copy.deepcopy(PACK)
    legacy.pop("pack_version", None)

    model = FindingsPack.model_validate(legacy)

    assert model.pack_version == "v1"


@pytest.mark.parametrize("value", [None, 1, ""])
def test_pack_feature_contract_rejects_missing_null_non_string_and_empty(value):
    broken = copy.deepcopy(PACK)
    if value is None:
        broken["benchmarks"][0]["feature_contract"].pop("cs10_median")
    else:
        broken["benchmarks"][0]["feature_contract"]["cs10_median"] = value

    with pytest.raises(PydanticValidationError):
        FindingsPack.model_validate(broken)


def test_every_finding_has_nonempty_statement_and_source_ref():
    for f in PACK["findings"]:
        assert f["statement"].strip(), f["key"]
        assert f["title"].strip(), f["key"]
        assert f["source_ref"].startswith("companion-app-content.md#"), f["key"]


def test_tier_discipline_diagnostic_never_instructs():
    offenders = []
    for f in PACK["findings"]:
        match = IMPERATIVE.search(f["statement"])
        if match and f["tier"] == "diagnostic":
            offenders.append(f"{f['key']}: imperative verb '{match.group(0)}'")
        if match is None:
            # statements with no imperative may be any tier; nothing to check
            continue
        if f["tier"] not in ("actionable", "a-lite"):
            offenders.append(f"{f['key']}: tier {f['tier']} with imperative phrasing")
    assert not offenders, "ADR-0003 violations:\n" + "\n".join(offenders)


def test_curated_mastery_premium():
    f = finding("mastery_premium")
    assert f["tier"] == "actionable"
    assert f["value"] == 3.7
    assert f["unit"] == "pp"


def test_curated_counterpick_honesty():
    f = finding("counterpick_honesty")
    assert f["tier"] == "diagnostic"
    assert f["value"] == 2.5


def test_curated_ban_waste_correlation():
    f = finding("ban_waste_correlation")
    assert f["tier"] == "actionable"
    assert f["value"] == 0.125


def test_curated_level_over_farm():
    f = finding("level_over_farm_signal")
    assert f["tier"] == "diagnostic"
    assert f["value"] == 0.43


def test_curated_smite_contest_trap():
    f = finding("smite_contest_trap")
    assert f["tier"] == "diagnostic"
    assert f["value"] == 0.57


def test_curated_duo_stacking_null():
    f = finding("duo_stacking_null")
    assert f["tier"] == "diagnostic"
    assert f["value"] == 48.4


def test_habits_are_exactly_the_four_surviving_keys():
    expected = {
        "recall_safety": 2.24,
        "fast_first_dragon": 0.83,
        "spend_before_backing": 0.88,
        "plates_by_14": 1.08,
    }
    habits = {h["key"]: h["effect_per_sd"] for h in PACK["habits"]}
    assert set(habits) == set(expected)
    assert len(PACK["habits"]) == 4
    for key, effect in expected.items():
        assert habits[key] == effect, key


def test_objectives_block_matches_doc():
    assert PACK["objectives"] == {
        "baron_pre25_win_rate": 0.814,
        "baron_comeback_lift_pp": 29.5,
        "dragon_denial_win_rate": 0.954,
        "first_dragon_pre20_win_rate": 0.603,
        "herald_pre20_win_rate": 0.666,
    }


def test_comeback_odds_rows_match_doc():
    assert [(r["gold_deficit_at_15"], r["win_rate"]) for r in PACK["comeback_odds"]] == [
        (-2000, 0.276),
        (-5000, 0.076),
        (-7000, 0.03),
    ]


def test_checkpoints_quartiles_match_doc():
    assert [(c["gold_diff_bucket"], c["win_rate"]) for c in PACK["checkpoints"]] == [
        ("bottom_quartile_@20m", 0.282),
        ("top_quartile_@20m", 0.718),
    ]


def test_ban_advisor_has_real_threat_entries():
    real_threat = [r for r in PACK["ban_advisor"] if r["recommendation"] == "real-threat"]
    assert len(real_threat) > 0
    for row in real_threat:
        assert row["win_rate"] >= 0.52
        assert row["ban_rate"] <= 0.03


def test_trap_picks_are_bottom_of_the_barrel():
    traps = PACK["trap_picks"]
    assert 0 < len(traps) <= 5
    win_rates = [t["win_rate"] for t in traps]
    assert win_rates == sorted(win_rates)
    assert all(wr < 0.45 for wr in win_rates)


def test_tier_list_minimum_sample():
    for entry in PACK["tier_list"]:
        assert entry["games"] >= 100, entry
    tiers = {"S", "A", "B", "C"}
    assert all(entry["tier"] in tiers for entry in PACK["tier_list"])

def test_matchup_rows_keep_direction_and_reject_self_rows(generator):
    pd = pytest.importorskip("pandas")
    rows = [
        {"champion_name": "Darius", "opponent_champion_name": "Darius", "role": "TOP", "win": True},
        {"champion_name": "Darius", "opponent_champion_name": "Garen", "role": "TOP", "win": True},
        {"champion_name": "Garen", "opponent_champion_name": "Darius", "role": "TOP", "win": False},
    ]

    matchups = generator.build_matchup_examples(pd.DataFrame(rows), wanted=10, min_games=1)

    assert {(row["champion"], row["opponent"], row["role"]) for row in matchups} == {
        ("Darius", "Garen", "TOP"),
        ("Garen", "Darius", "TOP"),
    }
    assert {row["champion"]: row["wr"] for row in matchups} == {"Darius": 1.0, "Garen": 0.0}


def test_matchup_validator_rejects_exact_duplicate_but_allows_reverse_and_role(generator):
    rows = [
        {"champion": "Darius", "opponent": "Garen", "role": "TOP"},
        {"champion": "Garen", "opponent": "Darius", "role": "TOP"},
        {"champion": "Darius", "opponent": "Garen", "role": "JUNGLE"},
    ]

    assert generator.validate_matchup_examples(rows) == rows
    with pytest.raises(ValueError, match="duplicate matchup direction"):
        generator.validate_matchup_examples([*rows, rows[0]])


def test_shipped_darius_garen_rows_are_independently_oriented():
    rows = {
        (row["champion"], row["opponent"], row["role"]): row["wr"]
        for row in PACK["matchup_examples"]
        if {row["champion"], row["opponent"]} == {"Darius", "Garen"}
    }
    assert rows[("Darius", "Garen", "TOP")] == 0.4098
    assert rows[("Garen", "Darius", "TOP")] == 0.5902


@pytest.mark.parametrize(
    "rows",
    [
        [{"role": "TOP", "sample": 1, "feature_contract": {"cs10_median": "cs10"}}],
        [{"role": "TOP", "sample": 1, "cs10_median": 60.0, "feature_contract": {}}],
        [{"role": "TOP", "sample": 1, "cs10_median": None, "feature_contract": {"cs10_median": "cs10"}}],
        [{"role": "TOP", "sample": 1, "cs10_median": float("nan"), "feature_contract": {"cs10_median": "cs10"}}],
    ],
)
def test_benchmark_validator_rejects_untruthful_sparse_pairs(generator, rows):
    with pytest.raises(ValueError):
        generator.validate_benchmarks(rows)


def test_benchmark_builder_omits_uncomputed_features_truthfully(generator):
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame(
        [
            {"role": "TOP", "lane_minions_first_10m": 60.0},
            {"role": "TOP", "lane_minions_first_10m": float("nan")},
            {"role": "JUNGLE", "lane_minions_first_10m": float("nan")},
        ]
    )

    benchmarks = generator.build_benchmarks(frame)

    assert benchmarks == [
        {
            "role": "TOP",
            "cs10_median": 60.0,
            "feature_contract": {"cs10_median": "lane_minions_first_10m"},
            "sample": 1,
        }
    ]


def test_sparse_schema_accepts_truthful_pair_and_rejects_unpaired_median():
    benchmark = {"role": "TOP", "cs10_median": 60.0, "feature_contract": {"cs10_median": "cs10"}, "sample": 1}
    sparse = {**PACK, "benchmarks": [benchmark]}
    Draft202012Validator(SCHEMA).validate(sparse)

    broken = {**sparse, "benchmarks": [{**benchmark, "feature_contract": {}}]}
    with pytest.raises(ValidationError):
        Draft202012Validator(SCHEMA).validate(broken)


def test_benchmarks_cover_all_roles_with_sample():
    roles = {b["role"]: b for b in PACK["benchmarks"]}
    assert set(roles) == {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}
    for bench in roles.values():
        assert bench["sample"] > 0


def test_benchmark_pack_fields_declare_only_computed_source_features():
    for bench in PACK["benchmarks"]:
        assert "level10_median" not in bench
        assert "gold_diff_10_median" not in bench
        assert bench["feature_contract"] == {"cs10_median": "lane_minions_first_10m"}
        assert isinstance(bench["cs10_median"], (int, float))

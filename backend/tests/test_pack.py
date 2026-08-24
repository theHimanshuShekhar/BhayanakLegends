"""Validate the shipped Findings Pack v1 against its schema and the research contract."""

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

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


def test_pack_matches_schema():
    Draft202012Validator.check_schema(SCHEMA)
    Draft202012Validator(SCHEMA).validate(PACK)


def test_header_fields():
    assert PACK["schema_version"] == 1
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", PACK["generated_at"])
    assert PACK["dataset"]["matches"] > 0
    assert PACK["dataset"]["player_games"] >= PACK["dataset"]["matches"]
    assert len(PACK["dataset"]["patches"]) == 2


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


def test_benchmarks_cover_all_roles_with_sample():
    roles = {b["role"]: b for b in PACK["benchmarks"]}
    assert set(roles) == {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}
    for bench in roles.values():
        assert bench["sample"] > 0


def test_benchmark_pack_fields_declare_exact_source_features():
    for bench in PACK["benchmarks"]:
        assert "gold10_median" not in bench
        assert bench["gold_diff_10_median"] is None
        assert bench["feature_contract"] == {
            "cs10_median": "lane_minions_first_10m",
            "level10_median": "level10",
            "gold_diff_10_median": "gold_diff_10",
        }

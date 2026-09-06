from __future__ import annotations

import json
from pathlib import Path

import pytest

from bhayanak_legends.extract import parse_match
from bhayanak_legends.extract_v2 import (
    PARITY_V2_VERSION,
    V2_FEATURE_ORDER,
    parse_personal_history_v2,
)

FIXTURES = Path(__file__).parent / "fixtures"
PUUID = "fixture-puuid-03"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_match_real_fixture():
    parsed = parse_match(load("SG2_170114893.json"), PUUID)

    assert parsed["match_id"] == "SG2_170114893"
    assert parsed["patch"] == "16.16"
    assert parsed["role"] in {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY", None}
    assert len(parsed["played_at"]) == 20
    assert parsed["duration_s"] > 0


def test_parse_personal_history_real_fixture_uses_only_v2_features():
    detail = load("SG2_170114893.json")
    timeline = load("SG2_170114893_timeline.json")
    participants = detail["info"]["participants"]

    parsed = parse_personal_history_v2(
        timeline,
        PUUID,
        participants,
        detail=detail,
    )

    assert parsed["feature_contract_version"] == PARITY_V2_VERSION
    assert set(parsed) >= {"feature_contract_version", *V2_FEATURE_ORDER}
    assert parsed["cs10"] is not None
    assert parsed["level10"] is not None
    assert parsed["gold_diff_10"] is not None
    assert "gold_diff_15" not in parsed
    assert "gold_diff_20" not in parsed
    assert parsed["team_state"]["feature"] == "team_gold_diff_15m"


def test_parse_personal_history_without_timeline_withholds_every_feature():
    detail = load("SG2_170114893.json")
    parsed = parse_personal_history_v2(
        None,
        PUUID,
        detail["info"]["participants"],
        detail=detail,
    )

    assert parsed["feature_contract_version"] == PARITY_V2_VERSION
    assert all(parsed[feature] is None for feature in V2_FEATURE_ORDER)
    assert parsed["team_state"]["team_gold_diff_15m"] is None
    assert parsed["team_state"]["observed_through_s"] is None


def test_parse_personal_history_unknown_participant_withholds_features():
    detail = load("SG2_170114893.json")
    timeline = load("SG2_170114893_timeline.json")
    parsed = parse_personal_history_v2(
        timeline,
        "not-present",
        detail["info"]["participants"],
        detail=detail,
    )

    assert all(parsed[feature] is None for feature in V2_FEATURE_ORDER)
    assert parsed["team_state"]["team_gold_diff_15m"] is None


def test_parse_match_unknown_puuid_raises():
    with pytest.raises(KeyError, match="not-here"):
        parse_match(load("SG2_170114893.json"), "not-here")

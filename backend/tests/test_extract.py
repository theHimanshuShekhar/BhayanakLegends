import json
from pathlib import Path

from bhayanak_legends.extract import parse_checkpoints, parse_match

FIXTURES = Path(__file__).parent / "fixtures"
PUUID = "Pi3CECbTWk32o-z4uYe4fr1gH6OEVeex3PHDFcZj3L5tIjrCq3-lqccb0p6oyrUQ0kFJRO349UK9IQ"
VALID_ROLES = {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_parse_match_real_fixture():
    parsed = parse_match(load("SG2_170114893.json"), PUUID)
    assert parsed["match_id"] == "SG2_170114893"
    assert parsed["patch"].startswith(("14.", "15.", "16."))
    assert parsed["duration_s"] > 300
    assert parsed["role"] in VALID_ROLES
    assert isinstance(parsed["win"], bool)
    assert parsed["champion"] == "Jinx"
    assert parsed["played_at"].endswith("Z")
    assert len(parsed["played_at"]) == 20


def test_parse_checkpoints_real_fixture():
    checkpoints = parse_checkpoints(load("SG2_170114893_timeline.json"), PUUID)
    assert set(checkpoints) == {
        "gold_diff_10",
        "gold_diff_15",
        "gold_diff_20",
        "cs10",
        "level10",
    }
    assert checkpoints["gold_diff_10"] is not None
    assert checkpoints["gold_diff_15"] is not None
    # Contract-v1 reuses the latest available snapshot for a later checkpoint.
    assert checkpoints["gold_diff_20"] is not None
    assert checkpoints["cs10"] > 0
    assert checkpoints["level10"] > 0


def test_parse_checkpoints_short_timeline_yields_nones():
    timeline = {
        "metadata": {"participants": [PUUID] + ["p" * 40] * 9},
        "info": {
            "frames": [
                {"timestamp": m * 60_000, "participantFrames": {}, "events": []}
                for m in range(5)
            ]
        },
    }
    checkpoints = parse_checkpoints(timeline, PUUID)
    assert all(v is None for v in checkpoints.values())


def test_parse_match_role_missing_becomes_none():
    detail = {
        "metadata": {"matchId": "SG2_1"},
        "info": {
            "gameEndTimestamp": 1775412226828,
            "gameDuration": 1800,
            "gameVersion": "16.7.760.9485",
            "participants": [
                {"puuid": "x", "teamPosition": "", "championName": "Yasuo", "win": True}
            ],
        },
    }
    parsed = parse_match(detail, "x")
    assert parsed["role"] is None
    assert parsed["win"] is True
    assert parsed["patch"] == "16.7"


def test_parse_match_unknown_puuid_raises():
    import pytest

    with pytest.raises(KeyError):
        parse_match(load("SG2_170114893.json"), "not-here")

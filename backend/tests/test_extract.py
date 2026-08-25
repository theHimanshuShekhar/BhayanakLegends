import json
from pathlib import Path

from bhayanak_legends.extract import parse_checkpoints, parse_match

FIXTURES = Path(__file__).parent / "fixtures"
PUUID = "fixture-puuid-03"
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


def test_parse_checkpoints_without_timeline_yields_nones():
    checkpoints = parse_checkpoints(None, PUUID)

    assert all(value is None for value in checkpoints.values())


def test_parse_checkpoints_without_participant_yields_nones():
    timeline = {
        "metadata": {"participants": ["opponent"]},
        "info": {
            "frames": [
                {
                    "timestamp": 600_000,
                    "participantFrames": {"1": {"totalGold": 1_000, "level": 8}},
                }
            ]
        },
    }

    checkpoints = parse_checkpoints(timeline, PUUID)

    assert all(value is None for value in checkpoints.values())


def test_parse_checkpoints_remake_before_ten_minutes_is_missing():
    timeline = {
        "metadata": {"participants": [PUUID, "opponent"]},
        "info": {
            "frames": [
                {
                    "timestamp": 599_999,
                    "participantFrames": {
                        "1": {
                            "totalGold": 1_200,
                            "level": 8,
                            "minionsKilled": 70,
                            "jungleMinionsKilled": 5,
                        },
                        "2": {"totalGold": 1_000, "level": 8},
                    },
                }
            ]
        },
    }

    checkpoints = parse_checkpoints(timeline, PUUID)

    assert checkpoints["cs10"] is None
    assert checkpoints["level10"] is None
    assert checkpoints["gold_diff_10"] is None


def test_parse_checkpoints_uses_last_pre_ten_frame_when_timeline_reaches_ten():
    timeline = {
        "metadata": {"participants": [PUUID, "opponent"]},
        "info": {
            "frames": [
                {
                    "timestamp": 599_000,
                    "participantFrames": {
                        "1": {
                            "totalGold": 1_200,
                            "level": 8,
                            "minionsKilled": 70,
                            "jungleMinionsKilled": 5,
                        },
                        "2": {"totalGold": 1_000, "level": 8},
                    },
                },
                {
                    "timestamp": 601_000,
                    "participantFrames": {"2": {"totalGold": 1_100, "level": 8}},
                },
            ]
        },
    }

    checkpoints = parse_checkpoints(timeline, PUUID)

    assert checkpoints["cs10"] == 75
    assert checkpoints["level10"] == 8
    assert checkpoints["gold_diff_10"] == 100.0


def test_parse_checkpoints_exact_ten_minute_frame_is_valid():
    timeline = {
        "metadata": {"participants": [PUUID, "opponent"]},
        "info": {
            "frames": [
                {
                    "timestamp": 600_000,
                    "participantFrames": {
                        "1": {
                            "totalGold": 1_200,
                            "level": 8,
                            "minionsKilled": 70,
                            "jungleMinionsKilled": 5,
                        },
                        "2": {"totalGold": 1_000, "level": 8},
                    },
                }
            ]
        },
    }

    checkpoints = parse_checkpoints(timeline, PUUID)

    assert checkpoints["cs10"] == 75
    assert checkpoints["level10"] == 8
    assert checkpoints["gold_diff_10"] == 100.0


def test_parse_checkpoints_selected_ten_minute_frame_without_participant_is_missing():
    timeline = {
        "metadata": {"participants": [PUUID, "opponent"]},
        "info": {
            "frames": [
                {
                    "timestamp": 599_000,
                    "participantFrames": {
                        "1": {
                            "totalGold": 1_200,
                            "level": 8,
                            "minionsKilled": 70,
                            "jungleMinionsKilled": 5,
                        },
                        "2": {"totalGold": 1_000, "level": 8},
                    },
                },
                {
                    "timestamp": 600_000,
                    "participantFrames": {"2": {"totalGold": 1_100, "level": 8}},
                },
            ]
        },
    }

    checkpoints = parse_checkpoints(timeline, PUUID)

    assert checkpoints["cs10"] is None
    assert checkpoints["level10"] is None
    assert checkpoints["gold_diff_10"] is None


def test_parse_checkpoints_empty_late_frame_does_not_prove_ten_minutes():
    timeline = {
        "metadata": {"participants": [PUUID, "opponent"]},
        "info": {
            "frames": [
                {
                    "timestamp": 599_000,
                    "participantFrames": {
                        "1": {
                            "totalGold": 1_200,
                            "level": 8,
                            "minionsKilled": 70,
                            "jungleMinionsKilled": 5,
                        },
                        "2": {"totalGold": 1_000, "level": 8},
                    },
                },
                {"timestamp": 601_000, "participantFrames": {}},
            ]
        },
    }

    checkpoints = parse_checkpoints(timeline, PUUID)

    assert checkpoints["cs10"] is None
    assert checkpoints["level10"] is None
    assert checkpoints["gold_diff_10"] is None


def test_parse_checkpoints_non_numeric_ten_minute_gold_is_missing():
    timeline = {
        "metadata": {"participants": [PUUID, "opponent"]},
        "info": {
            "frames": [
                {
                    "timestamp": 600_000,
                    "participantFrames": {
                        "1": {
                            "totalGold": "unknown",
                            "level": 8,
                            "minionsKilled": 70,
                            "jungleMinionsKilled": 5,
                        },
                        "2": {"totalGold": 1_000, "level": 8},
                    },
                }
            ]
        },
    }

    checkpoints = parse_checkpoints(timeline, PUUID)

    assert checkpoints["cs10"] == 75
    assert checkpoints["level10"] == 8
    assert checkpoints["gold_diff_10"] is None


def test_parse_checkpoints_ten_minute_guard_preserves_later_checkpoints():
    timeline = {
        "metadata": {"participants": [PUUID, "opponent"]},
        "info": {
            "frames": [
                {
                    "timestamp": 599_000,
                    "participantFrames": {
                        "1": {"totalGold": 1_200, "level": 8},
                        "2": {"totalGold": 1_000, "level": 8},
                    },
                },
                {
                    "timestamp": 890_000,
                    "participantFrames": {
                        "1": {"totalGold": 1_800, "level": 10},
                        "2": {"totalGold": 1_500, "level": 10},
                    },
                },
            ]
        },
    }

    checkpoints = parse_checkpoints(timeline, PUUID)

    assert checkpoints["gold_diff_10"] == 100.0
    assert checkpoints["gold_diff_15"] == 150.0
    assert checkpoints["gold_diff_20"] == 150.0


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

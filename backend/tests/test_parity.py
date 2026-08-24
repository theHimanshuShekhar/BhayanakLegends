"""Contract-v1 parity checks against the LoLTrends issue #29 fixture values."""

import json
from pathlib import Path

import pytest

from bhayanak_legends.extract import CHECKPOINT_FEATURES, parse_checkpoints

FIXTURES = Path(__file__).parent / "fixtures" / "parity"


def test_checkpoint_subset_matches_upstream_hand_computed_outputs() -> None:
    timeline = json.loads((FIXTURES / "companion_parity_timeline.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "companion_parity_expected.json").read_text(encoding="utf-8"))

    assert expected["contract_version"] == "loltrends-parity-v1"
    assert set(expected["features"]) == CHECKPOINT_FEATURES
    for puuid in timeline["metadata"]["participants"]:
        actual = parse_checkpoints(timeline, puuid)
        assert set(actual) == CHECKPOINT_FEATURES
        for feature, expected_by_puuid in expected["features"].items():
            assert actual[feature] == pytest.approx(expected_by_puuid[puuid]), (puuid, feature)


def test_checkpoint_subset_uses_latest_snapshot_at_or_before_checkpoint() -> None:
    timeline = json.loads((FIXTURES / "companion_parity_timeline.json").read_text(encoding="utf-8"))
    timeline["info"]["frames"] = [timeline["info"]["frames"][0]]

    actual = parse_checkpoints(timeline, "parity-puuid-01")

    assert actual == {
        "cs10": 75,
        "level10": 8,
        "gold_diff_10": 150.0,
        "gold_diff_15": 150.0,
        "gold_diff_20": 150.0,
    }

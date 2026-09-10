from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from bhayanak_legends.extract_v2 import parse_personal_history_v2, parse_recall_features_v2

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "personal_history_parity_v2.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
PARTICIPANTS = FIXTURE["participants"]
LOCAL_PUUID = FIXTURE["local_puuid"]


def timeline_for(name: str) -> dict[str, Any]:
    case = copy.deepcopy(FIXTURE["cases"][name])
    if "base_case" in case:
        base = timeline_for(case["base_case"])
        frames_by_timestamp = {frame["timestamp"]: frame for frame in base["info"]["frames"]}
        for timestamp, events in case.get("events_at_ms", {}).items():
            frames_by_timestamp[int(timestamp)]["events"] = events
        for timestamp, total_gold in case.get("total_gold_at_ms", {}).items():
            frame = frames_by_timestamp[int(timestamp)]
            if not isinstance(total_gold, list) or len(total_gold) != len(PARTICIPANTS):
                continue
            for index, participant in enumerate(PARTICIPANTS):
                participant_id = int(participant["participantId"])
                frame["participantFrames"][str(participant_id)]["totalGold"] = total_gold[index]
        for timestamp in case.get("empty_participant_frames_at_ms", []):
            frames_by_timestamp[int(timestamp)]["participantFrames"] = {}
        for timestamp, participant_ids in case.get("omit_participant_position_at_ms", {}).items():
            frame = frames_by_timestamp[int(timestamp)]
            for participant_id in participant_ids:
                frame["participantFrames"][str(participant_id)].pop("position", None)
        return base

    defaults = FIXTURE["defaults"]
    omitted_events = set(case.get("omit_events_at_ms", []))
    frames: list[dict[str, Any]] = []
    for spec in case["frames"]:
        timestamp = int(spec["timestamp_ms"])
        total_gold = spec.get("total_gold", defaults["total_gold"])
        minions = spec.get("minions_killed", defaults["minions_killed"])
        jungle_minions = spec.get("jungle_minions_killed", defaults["jungle_minions_killed"])
        levels = spec.get("levels", defaults["levels"])
        local_position = spec.get("local_position", defaults["position"])
        frame: dict[str, Any] = {"timestamp": timestamp, "participantFrames": {}}
        if timestamp not in omitted_events:
            frame["events"] = spec.get("events", [])
        for index, participant in enumerate(PARTICIPANTS):
            participant_id = int(participant["participantId"])
            position = (
                local_position
                if participant_id == 1
                else defaults["position"]
                if participant["teamId"] == 100
                else defaults["enemy_position"]
            )
            frame["participantFrames"][str(participant_id)] = {
                "position": {"x": position[0], "y": position[1]},
                "currentGold": spec.get("local_current_gold", 0) if participant_id == 1 else 0,
                "totalGold": total_gold[index],
                "minionsKilled": minions[index],
                "jungleMinionsKilled": jungle_minions[index],
                "level": levels[index],
            }
        frames.append(frame)
    return {"info": {"frameInterval": 60000, "frames": frames}}


def detail(
    *,
    early_surrender: bool = False,
    ordinary_surrender: bool = False,
    participant_overrides: dict[int, dict[str, object]] | None = None,
) -> dict[str, Any]:
    participants = []
    for participant in PARTICIPANTS:
        updated = {
            **participant,
            "gameEndedInEarlySurrender": early_surrender,
            "gameEndedInSurrender": ordinary_surrender,
        }
        updated.update((participant_overrides or {}).get(int(participant["participantId"]), {}))
        participants.append(updated)
    return {
        "info": {
            "gameMode": "CLASSIC",
            "mapId": 11,
            "queueId": 420,
            "gameDuration": 1800,
            "participants": participants,
        }
    }


def expected(name: str, key: str) -> object:
    return FIXTURE["cases"][name]["expected"].get(key)


@pytest.mark.parametrize(
    "name",
    ["regular", "irregular", "missing_events", "too_short", "latest_populated_before_checkpoint", "team_deficit", "team_ahead"],
)
def test_checkpoint_contract_uses_shared_populated_reachability(name: str) -> None:
    values = parse_personal_history_v2(
        timeline_for(name), LOCAL_PUUID, PARTICIPANTS, detail=detail()
    )
    for field, fixture_key in (
        ("cs10", "cs10"),
        ("level10", "level10"),
        ("gold_diff_10", "gold_diff_10"),
        ("team_gold_diff_15m", "team_gold_diff_15m"),
        ("timeline_observed_through_s", "observed_through_s"),
    ):
        assert values[field] == expected(name, fixture_key)


@pytest.mark.parametrize("name", ["regular", "irregular"])
def test_recall_contract_matches_shared_fixture(name: str) -> None:
    values = parse_recall_features_v2(timeline_for(name), 1, PARTICIPANTS)
    for field in (
        "recalls_before_15m",
        "avg_banked_gold_at_recall_by_15m",
        "avg_banked_gold_at_recall_by_20m",
        "unseen_recall_share_by_15m",
        "unseen_recall_share_by_20m",
    ):
        assert values[field] == expected(name, field)


@pytest.mark.parametrize(
    ("name", "withheld_fields"),
    [
        (
            "missing_events",
            (
                "recalls_before_15m",
                "avg_banked_gold_at_recall_by_15m",
                "avg_banked_gold_at_recall_by_20m",
                "unseen_recall_share_by_15m",
                "unseen_recall_share_by_20m",
            ),
        ),
        (
            "too_short",
            (
                "recalls_before_15m",
                "avg_banked_gold_at_recall_by_15m",
                "avg_banked_gold_at_recall_by_20m",
                "unseen_recall_share_by_15m",
                "unseen_recall_share_by_20m",
            ),
        ),
    ],
)
def test_recall_contract_withholds_unreachable_or_incomplete_cases(
    name: str, withheld_fields: tuple[str, ...]
) -> None:
    values = parse_personal_history_v2(
        timeline_for(name), LOCAL_PUUID, PARTICIPANTS, detail=detail()
    )
    assert all(values[field] is None for field in withheld_fields)


def test_recall_purchase_ambiguity_withholds_banked_gold_only() -> None:
    values = parse_recall_features_v2(timeline_for("recall_purchase_ambiguous"), 1, PARTICIPANTS)
    assert values["recalls_before_15m"] == 1
    assert values["avg_banked_gold_at_recall_by_15m"] is None
    assert values["avg_banked_gold_at_recall_by_20m"] is None
    assert values["unseen_recall_share_by_15m"] == 1
    assert values["unseen_recall_share_by_20m"] == 1


def test_recall_visibility_ambiguity_withholds_visibility_share_only() -> None:
    values = parse_recall_features_v2(timeline_for("recall_visibility_unknown"), 1, PARTICIPANTS)
    assert values["avg_banked_gold_at_recall_by_15m"] == 400
    assert values["avg_banked_gold_at_recall_by_20m"] == 550
    assert values["unseen_recall_share_by_15m"] is None
    assert values["unseen_recall_share_by_20m"] is None
def test_team_gold_withholds_ambiguous_teams_and_nonfinite_gold() -> None:
    ambiguous = copy.deepcopy(PARTICIPANTS)
    ambiguous[-1]["teamId"] = 100
    values = parse_personal_history_v2(
        timeline_for("regular"), LOCAL_PUUID, ambiguous, detail=detail()
    )
    assert values["team_gold_diff_15m"] is None

    nonfinite = timeline_for("regular")
    nonfinite["info"]["frames"][15]["participantFrames"]["10"]["totalGold"] = "NaN"
    values = parse_personal_history_v2(
        nonfinite, LOCAL_PUUID, PARTICIPANTS, detail=detail()
    )
    assert values["team_gold_diff_15m"] is None


def test_ordinary_surrender_marks_match_ineligible_and_team_state_surrendered() -> None:
    values = parse_personal_history_v2(
        timeline_for("regular"),
        LOCAL_PUUID,
        PARTICIPANTS,
        detail=detail(ordinary_surrender=True),
    )
    assert values["personal_history_eligibility"] == "ineligible"
    assert values["team_state"]["non_surrendered"] is False


def test_early_surrender_does_not_use_eligibility_as_team_state_evidence() -> None:
    values = parse_personal_history_v2(
        timeline_for("regular"),
        LOCAL_PUUID,
        PARTICIPANTS,
        detail=detail(early_surrender=True),
    )
    assert values["personal_history_eligibility"] == "ineligible"
    assert values["team_state"]["non_surrendered"] is True


@pytest.mark.parametrize(
    "overrides",
    [
        {10: {"gameEndedInSurrender": True}},
        {10: {"gameEndedInSurrender": None}},
    ],
)
def test_inconsistent_or_missing_participant_surrender_flags_are_unknown(
    overrides: dict[int, dict[str, object]],
) -> None:
    values = parse_personal_history_v2(
        timeline_for("regular"),
        LOCAL_PUUID,
        PARTICIPANTS,
        detail=detail(participant_overrides=overrides),
    )
    assert values["personal_history_eligibility"] == "unknown"
    assert values["team_state"]["non_surrendered"] is None

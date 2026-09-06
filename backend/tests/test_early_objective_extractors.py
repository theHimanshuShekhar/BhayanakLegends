from __future__ import annotations

from typing import Any

from bhayanak_legends.extract_v2 import (
    EVENTS_MISSING,
    FOURTEEN_MINUTE_MS,
    parse_early_fight_features_v2,
    parse_first_dragon_v2,
    parse_plates_v2,
)


LOCAL_ID = 1
OPPONENT_ID = 2
PARTICIPANTS = [
    {"participantId": LOCAL_ID, "teamId": 100, "teamPosition": "MIDDLE"},
    {"participantId": OPPONENT_ID, "teamId": 200, "teamPosition": "MIDDLE"},
]


def timeline(
    events: list[dict[str, Any]],
    *,
    end_ms: int = 1_200_000,
    include_events: bool = True,
    populated: bool = True,
) -> dict[str, Any]:
    frame: dict[str, Any] = {"timestamp": end_ms}
    if include_events:
        frame["events"] = events
    if populated:
        frame["participantFrames"] = {"1": {"totalGold": 1000}}
    return {"info": {"frames": [frame]}}


def kill(timestamp: int, *, killer: int = LOCAL_ID, victim: int = OPPONENT_ID, x: int = 100, y: int = 100) -> dict[str, Any]:
    return {
        "type": "CHAMPION_KILL",
        "timestamp": timestamp,
        "killerId": killer,
        "victimId": victim,
        "assistingParticipantIds": [],
        "position": {"x": x, "y": y},
    }


def dragon(timestamp: int, team: int) -> dict[str, Any]:
    return {
        "type": "ELITE_MONSTER_KILL",
        "timestamp": timestamp,
        "monsterType": "DRAGON",
        "killerTeamId": team,
        "killerId": LOCAL_ID if team == 100 else OPPONENT_ID,
    }


def plate(timestamp: int, killer: int = LOCAL_ID) -> dict[str, Any]:
    return {
        "type": "TURRET_PLATE_DESTROYED",
        "timestamp": timestamp,
        "killerId": killer,
        "teamId": 100 if killer == LOCAL_ID else 200,
        "position": {"x": 100, "y": 100},
    }


def test_early_fights_group_at_ten_seconds_and_stop_at_cutoff() -> None:
    events = [
        kill(839_999, killer=OPPONENT_ID),
        kill(840_000, killer=LOCAL_ID, x=10_000, y=10_000),
        kill(845_000, killer=OPPONENT_ID, x=10_000, y=10_000),
        kill(850_001, killer=LOCAL_ID, x=20_000, y=20_000),
    ]
    result = parse_early_fight_features_v2(timeline(events), LOCAL_ID, PARTICIPANTS)

    assert result["early_fights_total"] == 1
    assert result["early_fights_participated"] == 0
    assert result["early_fight_participation_rate"] == 0.0



def test_early_fight_excludes_kill_at_exact_fourteen_minute_cutoff() -> None:
    events = [kill(839_999, killer=OPPONENT_ID), kill(840_000, killer=LOCAL_ID)]

    result = parse_early_fight_features_v2(timeline(events), LOCAL_ID, PARTICIPANTS)

    assert result["early_fights_total"] == 1
    assert result["early_fights_participated"] == 0

def test_early_fight_duplicate_and_assist_attribution_are_deterministic() -> None:
    first = kill(120_000, killer=OPPONENT_ID)
    first["assistingParticipantIds"] = [LOCAL_ID, LOCAL_ID]
    events = [first, dict(first), kill(120_001, killer=OPPONENT_ID, x=100, y=100)]
    result = parse_early_fight_features_v2(timeline(events), LOCAL_ID, PARTICIPANTS)

    assert result["early_fights_total"] == 1
    assert result["early_fights_participated"] == 1
    assert result["early_fight_participation_rate"] == 1.0


def test_early_fight_short_or_missing_event_stream_is_unavailable() -> None:
    short = parse_early_fight_features_v2(
        timeline([kill(100_000)], end_ms=FOURTEEN_MINUTE_MS - 1), LOCAL_ID, PARTICIPANTS
    )
    assert short["early_fight_participation_rate"] is None

    missing = parse_early_fight_features_v2(
        timeline([kill(100_000)], include_events=False), LOCAL_ID, PARTICIPANTS
    )
    assert missing["early_fight_observation_status"] == EVENTS_MISSING
    assert missing["early_fight_participation_rate"] is None


def test_first_dragon_uses_local_team_first_event_and_inclusive_horizon() -> None:
    events = [dragon(100_000, 200), dragon(400_000, 100), dragon(400_000, 100), dragon(1_200_000, 100)]
    result = parse_first_dragon_v2(timeline(events), LOCAL_ID, PARTICIPANTS)

    assert result == 400.0


def test_first_dragon_never_attributes_opponent_and_withholds_malformed_events() -> None:
    only_opponent = parse_first_dragon_v2(timeline([dragon(400_000, 200)]), LOCAL_ID, PARTICIPANTS)
    assert only_opponent is None

    malformed = dragon(400_000, 100)
    malformed["killerTeamId"] = None
    assert parse_first_dragon_v2(timeline([malformed]), LOCAL_ID, PARTICIPANTS) is None

    too_short = parse_first_dragon_v2(
        timeline([dragon(400_000, 100)], end_ms=1_200_000 - 1), LOCAL_ID, PARTICIPANTS
    )
    assert too_short is None


def test_plates_include_exact_fourteen_minute_event_once_and_only_lane_roles() -> None:
    events = [plate(840_000), plate(840_000), plate(840_001), plate(850_000, killer=OPPONENT_ID)]
    result = parse_plates_v2(timeline(events, end_ms=840_000), LOCAL_ID, PARTICIPANTS)
    assert result == 1

    non_laner = [*PARTICIPANTS]
    non_laner[0] = {**non_laner[0], "teamPosition": "JUNGLE"}
    assert parse_plates_v2(timeline([plate(100_000)]), LOCAL_ID, non_laner) is None


def test_plates_with_malformed_or_mismatched_team_attribution_are_unavailable() -> None:
    mismatched = plate(100_000)
    mismatched["teamId"] = 200
    assert parse_plates_v2(timeline([mismatched]), LOCAL_ID, PARTICIPANTS) is None

    malformed = plate(100_000)
    malformed["timestamp"] = None
    assert parse_plates_v2(timeline([malformed]), LOCAL_ID, PARTICIPANTS) is None


def test_plates_short_or_unpopulated_fourteen_minute_window_is_unavailable() -> None:
    short = parse_plates_v2(
        timeline([plate(100_000)], end_ms=FOURTEEN_MINUTE_MS - 1), LOCAL_ID, PARTICIPANTS
    )
    assert short is None

    unpopulated = parse_plates_v2(
        timeline([plate(100_000)], end_ms=FOURTEEN_MINUTE_MS, populated=False),
        LOCAL_ID,
        PARTICIPANTS,
    )
    assert unpopulated is None

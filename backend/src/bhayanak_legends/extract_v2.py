"""Versioned Personal History extraction for ``loltrends-parity-v2``.

The v2 extractor is deliberately small and pure.  It consumes Riot match-v5
``detail``/``timeline`` payloads and returns only features in the Personal
History contract. It never reads the Findings Pack, and every emitted field
uses the current v2 definition for that feature.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Mapping
from typing import Any

PARITY_V2_VERSION = "loltrends-parity-v2"

# Persisted feature names match the cutoff-v2 model cards.
V2_FEATURE_ORDER = (
    "cs10",
    "level10",
    "gold_diff_10",
    "team_gold_diff_15m",
    "recalls_before_15m",
    "avg_banked_gold_at_recall_by_15m",
    "avg_banked_gold_at_recall_by_20m",
    "unseen_recall_share_by_15m",
    "unseen_recall_share_by_20m",
    "first_dragon_by_20m_s",
    "first_riftherald_by_20m_s",
    "first_baron_by_20m_s",
    "smite_contests_before_15m",
    "smite_contests_before_20m",
    "early_fight_participation_rate",
    "plates_taken_by_14m",
)
V2_CHECKPOINT_FEATURES = frozenset(
    {"cs10", "level10", "gold_diff_10", "team_gold_diff_15m"}
)
V2_LANE_ROLES = frozenset({"TOP", "MIDDLE", "BOTTOM"})
V2_ALL_ROLES = frozenset({"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"})

TEN_MINUTE_MS = 600_000
FIFTEEN_MINUTE_MS = 900_000
FOURTEEN_MINUTE_MS = 840_000
TWENTY_MINUTE_MS = 1_200_000

# Recall inference is necessarily conservative: Riot timelines do not expose
# a first-class recall event.  A transition from outside the fountain radius to
# inside it is an observation only when the adjacent frames are close enough
# that a death/teleport cannot be hidden between them.
FOUNTAIN_RADIUS = 2_200.0
FAR_FROM_FOUNTAIN = 4_000.0
ENEMY_PROXIMITY = 3_500.0
MIN_RECALL_FRAME_MS = 90_000
MAX_RECALL_FRAME_GAP_MS = 120_000

FIGHT_GAP_MS = 10_000
FIGHT_RADIUS_UNITS = 4_000.0
EARLY_FIGHT_CUTOFF_MS = FOURTEEN_MINUTE_MS

EVENTS_VALID_EMPTY = "valid_empty"
EVENTS_VALID = "valid_events"
EVENTS_MISSING = "missing"
EVENTS_UNUSABLE = "unusable"

V2_PRE20_FEATURES = frozenset(
    {
        "recalls_before_15m",
        "avg_banked_gold_at_recall_by_15m",
        "avg_banked_gold_at_recall_by_20m",
        "unseen_recall_share_by_15m",
        "unseen_recall_share_by_20m",
        "first_dragon_by_20m_s",
        "first_riftherald_by_20m_s",
        "first_baron_by_20m_s",
        "smite_contests_before_15m",
        "smite_contests_before_20m",
    }
)


def _finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _number(value: object) -> float | None:
    return float(value) if _finite(value) else None


def _positive_id(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and math.isfinite(value) and value.is_integer() and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _team_key(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
        return None
    text = str(value).strip()
    return text or None


def _position(value: object) -> tuple[float, float] | None:
    if not isinstance(value, Mapping):
        return None
    x = _number(value.get("x"))
    y = _number(value.get("y"))
    return (x, y) if x is not None and y is not None else None


def _distance(a: tuple[float, float] | None, b: tuple[float, float]) -> float:
    if a is None:
        return math.inf
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _frames(timeline: Mapping[str, Any] | None) -> list[tuple[float, int, dict[str, Any]]]:
    if not isinstance(timeline, Mapping):
        return []
    info = timeline.get("info")
    if not isinstance(info, Mapping):
        return []
    raw_frames = info.get("frames")
    if not isinstance(raw_frames, list):
        return []
    result: list[tuple[float, int, dict[str, Any]]] = []
    for order, frame in enumerate(raw_frames):
        if not isinstance(frame, dict):
            continue
        timestamp = _number(frame.get("timestamp"))
        if timestamp is None or timestamp < 0:
            continue
        result.append((timestamp, order, frame))
    return result


def _ordered_frames(timeline: Mapping[str, Any] | None) -> list[tuple[float, int, dict[str, Any]]]:
    return sorted(_frames(timeline), key=lambda row: (row[0], row[1]))


def _frame_at_or_before(
    timeline: Mapping[str, Any] | None, target_ms: int
) -> dict[str, Any] | None:
    chosen: tuple[float, int, dict[str, Any]] | None = None
    for timestamp, order, frame in _frames(timeline):
        if timestamp > target_ms:
            continue
        if chosen is None or (timestamp, order) > (chosen[0], chosen[1]):
            chosen = (timestamp, order, frame)
    return chosen[2] if chosen else None
def _populated_frame_at_or_before(
    timeline: Mapping[str, Any] | None, target_ms: int
) -> dict[str, Any] | None:
    """Return the latest frame at/before a checkpoint with participant data."""

    chosen: tuple[float, int, dict[str, Any]] | None = None
    for timestamp, order, frame in _frames(timeline):
        if timestamp > target_ms:
            continue
        snapshots = frame.get("participantFrames")
        if not isinstance(snapshots, Mapping) or not snapshots:
            continue
        if chosen is None or (timestamp, order) > (chosen[0], chosen[1]):
            chosen = (timestamp, order, frame)
    return chosen[2] if chosen else None



def _has_frame_at_or_after(timeline: Mapping[str, Any] | None, target_ms: int) -> bool:
    return any(timestamp >= target_ms for timestamp, _, _ in _frames(timeline))


def _has_populated_frame_at_or_after(
    timeline: Mapping[str, Any] | None, target_ms: int
) -> bool:
    for timestamp, _, frame in _frames(timeline):
        if timestamp < target_ms:
            continue
        snapshots = frame.get("participantFrames")
        if isinstance(snapshots, Mapping) and bool(snapshots):
            return True
    return False


def _snapshot(frame: Mapping[str, Any] | None, participant_id: int) -> Mapping[str, Any] | None:
    if not isinstance(frame, Mapping):
        return None
    snapshots = frame.get("participantFrames")
    if not isinstance(snapshots, Mapping):
        return None
    value = snapshots.get(str(participant_id))
    return value if isinstance(value, Mapping) else None


def _participant_records(
    participants: list[dict[str, Any]] | None,
) -> tuple[dict[int, dict[str, Any]], bool]:
    records: dict[int, dict[str, Any]] = {}
    if not isinstance(participants, list) or not participants:
        return records, False
    valid = True
    for participant in participants:
        if not isinstance(participant, dict):
            valid = False
            continue
        participant_id = _positive_id(participant.get("participantId"))
        if participant_id is None or participant_id in records:
            valid = False
            continue
        records[participant_id] = participant
    return records, valid


def _event_array_status(timeline: Mapping[str, Any] | None) -> str:
    """Classify event arrays without treating absent data as an empty stream."""
    frames = _frames(timeline)
    if not frames:
        return EVENTS_UNUSABLE
    saw_event = False
    for _, _, frame in frames:
        if "events" not in frame:
            return EVENTS_MISSING
        events = frame.get("events")
        if not isinstance(events, list):
            return EVENTS_UNUSABLE
        saw_event = saw_event or bool(events)
    return EVENTS_VALID if saw_event else EVENTS_VALID_EMPTY


def _dedupe_events(
    events: list[tuple[float, int, int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Sort events by source order and remove exact repeated timeline rows."""
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for _, _, _, event in sorted(events, key=lambda row: (row[0], row[1], row[2])):
        fingerprint = json.dumps(event, sort_keys=True, separators=(",", ":"))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        output.append(event)
    return output

def _checkpoint_values(
    timeline: Mapping[str, Any] | None,
    participant_id: int,
    participants: list[dict[str, Any]] | None,
) -> dict[str, float | int | None]:
    values: dict[str, float | int | None] = {
        "cs10": None,
        "level10": None,
        "gold_diff_10": None,
        "team_gold_diff_15m": None,
    }

    # A populated observation at/after ten minutes proves reachability; the
    # selected values still come only from the latest populated frame at/before 10m.
    if _has_populated_frame_at_or_after(timeline, TEN_MINUTE_MS):
        ten_frame = _populated_frame_at_or_before(timeline, TEN_MINUTE_MS)
        mine = _snapshot(ten_frame, participant_id)
        if mine is not None:
            minions = _number(mine.get("minionsKilled"))
            jungle_minions = _number(mine.get("jungleMinionsKilled"))
            if minions is None:
                minions = 0.0
            if jungle_minions is None:
                jungle_minions = 0.0
            if minions >= 0 and jungle_minions >= 0:
                values["cs10"] = int(minions + jungle_minions)

            level = _number(mine.get("level"))
            if level is None:
                level = 0.0
            if level >= 0:
                values["level10"] = int(level)

            gold = _number(mine.get("totalGold"))
            snapshots = ten_frame.get("participantFrames") if ten_frame else None
            if gold is not None and isinstance(snapshots, Mapping):
                pool = [
                    candidate
                    for entry in snapshots.values()
                    if isinstance(entry, Mapping)
                    for candidate in [_number(entry.get("totalGold"))]
                    if candidate is not None
                ]
                if pool:
                    values["gold_diff_10"] = gold - statistics.median(pool)

    # Team gold at 15m is intentionally a separate feature from the personal
    # median-relative gold_diff fields. All ten participants and both five-
    # player teams are required at the selected frame.
    if not _has_populated_frame_at_or_after(timeline, FIFTEEN_MINUTE_MS):
        return values
    records, records_valid = _participant_records(participants)
    if not records_valid or len(records) != 10 or participant_id not in records:
        return values

    teams: dict[str, list[int]] = {}
    for pid, participant in records.items():
        team = _team_key(participant.get("teamId"))
        if team is None:
            return values
        teams.setdefault(team, []).append(pid)
    if len(teams) != 2 or any(len(member_ids) != 5 for member_ids in teams.values()):
        return values

    own_team = _team_key(records[participant_id].get("teamId"))
    if own_team is None:
        return values
    enemy_teams = [team for team in teams if team != own_team]
    if len(enemy_teams) != 1:
        return values

    fifteen_frame = _populated_frame_at_or_before(timeline, FIFTEEN_MINUTE_MS)
    snapshots = fifteen_frame.get("participantFrames") if fifteen_frame else None
    if not isinstance(snapshots, Mapping):
        return values
    totals: dict[str, float] = {team: 0.0 for team in teams}
    for team, member_ids in teams.items():
        for pid in member_ids:
            snapshot = snapshots.get(str(pid))
            if not isinstance(snapshot, Mapping):
                return values
            gold = _number(snapshot.get("totalGold"))
            if gold is None:
                return values
            totals[team] += gold
    values["team_gold_diff_15m"] = totals[own_team] - totals[enemy_teams[0]]
    return values


def _fountain(team: object) -> tuple[float, float] | None:
    key = _team_key(team)
    if key == "100":
        return (600.0, 600.0)
    if key == "200":
        return (14_220.0, 14_220.0)
    return None


def _event_is_teleport(event: Mapping[str, Any]) -> bool:
    values = (
        event.get("type"),
        event.get("name"),
        event.get("spellName"),
        event.get("summonerSpell"),
    )
    return any("TELEPORT" in str(value).upper() for value in values if value is not None)


def _transition_has_respawn_or_teleport(
    frames: list[tuple[float, int, dict[str, Any]]],
    start_index: int,
    end_index: int,
    participant_id: int,
) -> bool:
    for _, _, frame in frames[start_index : end_index + 1]:
        events = frame.get("events")
        if not isinstance(events, list):
            return True
        for event in events:
            if not isinstance(event, Mapping):
                continue
            if _event_is_teleport(event):
                return True
            if event.get("type") == "CHAMPION_KILL":
                if _positive_id(event.get("victimId")) == participant_id:
                    return True
    return False


def _recall_observations(
    timeline: Mapping[str, Any] | None,
    participant_id: int,
    participants: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], bool, str]:
    """Infer conservative recall observations and their data status."""
    event_status = _event_array_status(timeline)
    if event_status in {EVENTS_MISSING, EVENTS_UNUSABLE}:
        return [], False, event_status
    # The contract evaluates early behavior only on matches whose timeline has
    # reached the 20-minute observation horizon.  No final-frame proxy is used.
    if not _has_populated_frame_at_or_after(timeline, TWENTY_MINUTE_MS):
        return [], False, EVENTS_UNUSABLE

    records, records_valid = _participant_records(participants)
    participant = records.get(participant_id)
    if not records_valid or participant is None:
        return [], False, EVENTS_UNUSABLE
    own_team = _team_key(participant.get("teamId"))
    fountain = _fountain(own_team)
    if own_team is None or fountain is None:
        return [], False, EVENTS_UNUSABLE

    enemy_ids = [
        pid
        for pid, entry in records.items()
        if pid != participant_id and _team_key(entry.get("teamId")) not in (None, own_team)
    ]
    if not enemy_ids:
        return [], False, EVENTS_UNUSABLE

    ordered = _ordered_frames(timeline)
    observations: list[dict[str, Any]] = []
    for index, (timestamp, _, frame) in enumerate(ordered):
        if index == 0 or timestamp < MIN_RECALL_FRAME_MS:
            continue
        previous_timestamp, _, previous_frame = ordered[index - 1]
        current = _snapshot(frame, participant_id)
        previous = _snapshot(previous_frame, participant_id)
        current_position = _position(current.get("position") if current else None)
        previous_position = _position(previous.get("position") if previous else None)
        if current_position is None or previous_position is None:
            continue
        if _distance(current_position, fountain) > FOUNTAIN_RADIUS:
            continue
        if _distance(previous_position, fountain) <= FAR_FROM_FOUNTAIN:
            continue
        if timestamp - previous_timestamp > MAX_RECALL_FRAME_GAP_MS:
            return [], False, EVENTS_UNUSABLE
        if _transition_has_respawn_or_teleport(ordered, index - 1, index, participant_id):
            return [], False, EVENTS_UNUSABLE

        enemy_positions: list[tuple[float, float]] = []
        for enemy_id in enemy_ids:
            enemy_snapshot = _snapshot(frame, enemy_id)
            position = _position(enemy_snapshot.get("position") if enemy_snapshot else None)
            if position is None:
                break
            enemy_positions.append(position)
        enemy_seen: bool | None = None
        if len(enemy_positions) == len(enemy_ids):
            enemy_seen = any(
                _distance(current_position, position) <= ENEMY_PROXIMITY
                for position in enemy_positions
            )

        # currentGold is the value observed on the arrival frame.  A purchase
        # transaction in that same frame has no ordering relative to arrival,
        # so the banked value is unavailable rather than guessed.
        banked_gold = _number(current.get("currentGold"))
        current_events = frame.get("events")
        if isinstance(current_events, list) and any(
            isinstance(event, Mapping)
            and str(event.get("type") or "").upper()
            in {"ITEM_PURCHASED", "ITEM_COMPLETED", "ITEM_SOLD", "ITEM_UNDO"}
            for event in current_events
        ):
            banked_gold = None
        observations.append(
            {
                "timestamp_ms": timestamp,
                "banked_gold": banked_gold,
                "enemy_seen": enemy_seen,
            }
        )
    return observations, True, event_status


def parse_recall_features_v2(
    timeline: Mapping[str, Any] | None,
    participant_id: int,
    participants: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    observations, usable, event_status = _recall_observations(
        timeline, participant_id, participants
    )
    values: dict[str, Any] = {
        "recalls_before_15m": None,
        "avg_banked_gold_at_recall_by_15m": None,
        "avg_banked_gold_at_recall_by_20m": None,
        "unseen_recall_share_by_15m": None,
        "unseen_recall_share_by_20m": None,
        "recall_observation_status": event_status,
    }
    if not usable:
        return values

    before_15m = [
        observation
        for observation in observations
        if observation["timestamp_ms"] < FIFTEEN_MINUTE_MS
    ]
    before_20m = [
        observation
        for observation in observations
        if observation["timestamp_ms"] < TWENTY_MINUTE_MS
    ]
    values["recalls_before_15m"] = len(before_15m)
    for suffix, selected in (("15m", before_15m), ("20m", before_20m)):
        if not selected:
            continue
        visibility = [observation["enemy_seen"] for observation in selected]
        if all(isinstance(item, bool) for item in visibility):
            values[f"unseen_recall_share_by_{suffix}"] = sum(
                not item for item in visibility
            ) / len(visibility)
        banked = [observation["banked_gold"] for observation in selected]
        if all(item is not None for item in banked):
            values[f"avg_banked_gold_at_recall_by_{suffix}"] = sum(
                float(item) for item in banked if item is not None
            ) / len(banked)
    return values


def _kill_events(timeline: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    events: list[tuple[float, int, int, dict[str, Any]]] = []
    for _, frame_order, frame in _ordered_frames(timeline):
        raw_events = frame.get("events")
        if not isinstance(raw_events, list):
            continue
        for event_order, event in enumerate(raw_events):
            if not isinstance(event, Mapping) or event.get("type") != "CHAMPION_KILL":
                continue
            timestamp = _number(event.get("timestamp"))
            victim = _positive_id(event.get("victimId"))
            if timestamp is None or timestamp < 0 or victim is None:
                continue
            killer = _positive_id(event.get("killerId"))
            assists: list[int] = []
            raw_assists = event.get("assistingParticipantIds")
            if isinstance(raw_assists, list):
                for assister in raw_assists:
                    parsed = _positive_id(assister)
                    if parsed is not None:
                        assists.append(parsed)
            normalized = {
                "timestamp": timestamp,
                "killerId": killer,
                "victimId": victim,
                "assistingParticipantIds": sorted(set(assists)),
                "position": _position(event.get("position")),
            }
            events.append((timestamp, frame_order, event_order, normalized))
    return _dedupe_events(events)


def _fight_groups(kills: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for kill in kills:
        if not current:
            current = [kill]
            continue
        previous = current[-1]
        close_in_time = kill["timestamp"] - previous["timestamp"] <= FIGHT_GAP_MS
        close_in_space = _distance(kill.get("position"), previous.get("position")) <= FIGHT_RADIUS_UNITS
        if close_in_time and close_in_space:
            current.append(kill)
        else:
            groups.append(current)
            current = [kill]
    if current:
        groups.append(current)
    return groups


def parse_early_fight_features_v2(
    timeline: Mapping[str, Any] | None,
    participant_id: int,
    participants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "early_fights_total": None,
        "early_fights_participated": None,
        "early_fight_participation_rate": None,
        "early_fight_observation_status": EVENTS_UNUSABLE,
    }
    if not _has_populated_frame_at_or_after(timeline, EARLY_FIGHT_CUTOFF_MS):
        return values
    status = _event_array_status(timeline)
    values["early_fight_observation_status"] = status
    if status in {EVENTS_MISSING, EVENTS_UNUSABLE}:
        return values

    records, records_valid = _participant_records(participants)
    if not records_valid or participant_id not in records:
        return values
    valid_ids = set(records)
    kills = [
        kill
        for kill in _kill_events(timeline)
        if kill["timestamp"] < EARLY_FIGHT_CUTOFF_MS
    ]
    early = _fight_groups(kills)
    if not early:
        values["early_fights_total"] = 0
        values["early_fights_participated"] = 0
        return values

    def participates(group: list[dict[str, Any]]) -> bool:
        for kill in group:
            actors = {
                kill.get("killerId"),
                kill.get("victimId"),
                *kill.get("assistingParticipantIds", []),
            }
            if valid_ids is not None:
                actors &= valid_ids
            if participant_id in actors:
                return True
        return False

    participated = sum(participates(group) for group in early)
    values["early_fights_total"] = len(early)
    values["early_fights_participated"] = participated
    values["early_fight_participation_rate"] = participated / len(early)
    return values


def _objective_events(
    timeline: Mapping[str, Any] | None,
    objective: str,
) -> tuple[list[dict[str, Any]], bool]:
    events: list[tuple[float, int, int, dict[str, Any]]] = []
    ambiguous = False
    objective = objective.upper()
    for _, frame_order, frame in _ordered_frames(timeline):
        raw_events = frame.get("events")
        if not isinstance(raw_events, list):
            continue
        for event_order, event in enumerate(raw_events):
            if not isinstance(event, Mapping) or event.get("type") != "ELITE_MONSTER_KILL":
                continue
            monster = str(event.get("monsterType") or "").upper()
            if monster != objective:
                continue
            timestamp = _number(event.get("timestamp"))
            if timestamp is None or timestamp < 0:
                ambiguous = True
                continue
            if timestamp > TWENTY_MINUTE_MS:
                continue
            team = _team_key(event.get("killerTeamId"))
            if team is None:
                ambiguous = True
                continue
            events.append(
                (
                    timestamp,
                    frame_order,
                    event_order,
                    {
                        "timestamp": timestamp,
                        "killerTeamId": team,
                        "killerId": _positive_id(event.get("killerId")),
                    },
                )
            )
    return _dedupe_events(events), ambiguous
def parse_first_objective_v2(
    timeline: Mapping[str, Any] | None,
    participant_id: int,
    participants: list[dict[str, Any]] | None,
    objective: str,
) -> float | None:
    if not _has_populated_frame_at_or_after(timeline, TWENTY_MINUTE_MS):
        return None
    status = _event_array_status(timeline)
    if status in {EVENTS_MISSING, EVENTS_UNUSABLE}:
        return None
    records, records_valid = _participant_records(participants)
    if not records_valid or participant_id not in records:
        return None
    local_team = _team_key(records[participant_id].get("teamId"))
    if local_team is None:
        return None
    events, ambiguous = _objective_events(timeline, objective)
    if ambiguous:
        return None
    for event in events:
        timestamp = _number(event.get("timestamp"))
        if (
            timestamp is not None
            and timestamp <= TWENTY_MINUTE_MS
            and event["killerTeamId"] == local_team
        ):
            return timestamp / 1000.0
    return None


def parse_first_dragon_v2(
    timeline: Mapping[str, Any] | None,
    participant_id: int,
    participants: list[dict[str, Any]] | None,
) -> float | None:
    return parse_first_objective_v2(timeline, participant_id, participants, "DRAGON")


def parse_first_riftherald_v2(
    timeline: Mapping[str, Any] | None,
    participant_id: int,
    participants: list[dict[str, Any]] | None,
) -> float | None:
    return parse_first_objective_v2(timeline, participant_id, participants, "RIFTHERALD")


def parse_first_baron_v2(
    timeline: Mapping[str, Any] | None,
    participant_id: int,
    participants: list[dict[str, Any]] | None,
) -> float | None:
    return parse_first_objective_v2(timeline, participant_id, participants, "BARON_NASHOR")


def _plate_events(timeline: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], bool]:
    events: list[tuple[float, int, int, dict[str, Any]]] = []
    ambiguous = False
    for _, frame_order, frame in _ordered_frames(timeline):
        raw_events = frame.get("events")
        if not isinstance(raw_events, list):
            continue
        for event_order, event in enumerate(raw_events):
            if not isinstance(event, Mapping) or event.get("type") != "TURRET_PLATE_DESTROYED":
                continue
            timestamp = _number(event.get("timestamp"))
            if timestamp is None or timestamp < 0:
                ambiguous = True
                continue
            if timestamp > FOURTEEN_MINUTE_MS:
                continue
            killer = _positive_id(event.get("killerId"))
            if killer is None:
                ambiguous = True
                continue
            events.append(
                (
                    timestamp,
                    frame_order,
                    event_order,
                    {
                        "timestamp": timestamp,
                        "killerId": killer,
                        "teamId": _team_key(event.get("teamId")),
                        "position": _position(event.get("position")),
                    },
                )
            )
    return _dedupe_events(events), ambiguous


def parse_plates_v2(
    timeline: Mapping[str, Any] | None,
    participant_id: int,
    participants: list[dict[str, Any]] | None,
) -> int | None:
    if not _has_populated_frame_at_or_after(timeline, FOURTEEN_MINUTE_MS):
        return None
    status = _event_array_status(timeline)
    if status in {EVENTS_MISSING, EVENTS_UNUSABLE}:
        return None
    records, records_valid = _participant_records(participants)
    participant = records.get(participant_id)
    if not records_valid or participant is None:
        return None
    role = str(participant.get("teamPosition") or "").strip().upper()
    if role not in V2_LANE_ROLES:
        return None
    local_team = _team_key(participant.get("teamId"))
    if local_team is None:
        return None
    events, ambiguous = _plate_events(timeline)
    if ambiguous:
        return None
    for event in events:
        if (
            event["killerId"] == participant_id
            and event["teamId"] is not None
            and event["teamId"] != local_team
        ):
            return None
    return sum(
        event["killerId"] == participant_id
        and event["teamId"] in (None, local_team)
        for event in events
    )


def _surrender_flags(
    detail: Mapping[str, Any] | None,
    participants: list[dict[str, Any]] | None = None,
) -> tuple[bool, bool] | None:
    """Return consistent participant-level early/ordinary surrender flags."""
    info = detail.get("info") if isinstance(detail, Mapping) else None
    detail_participants = info.get("participants") if isinstance(info, Mapping) else None
    candidates = participants
    if not isinstance(candidates, list) or not any(
        isinstance(participant, Mapping)
        and (
            "gameEndedInEarlySurrender" in participant
            or "gameEndedInSurrender" in participant
        )
        for participant in candidates
    ):
        candidates = detail_participants
    if not isinstance(candidates, list) or not candidates:
        return None

    early_values: set[bool] = set()
    ordinary_values: set[bool] = set()
    for participant in candidates:
        if not isinstance(participant, Mapping):
            return None
        early = participant.get("gameEndedInEarlySurrender")
        ordinary = participant.get("gameEndedInSurrender")
        if not isinstance(early, bool) or not isinstance(ordinary, bool):
            return None
        early_values.add(early)
        ordinary_values.add(ordinary)
    if len(early_values) != 1 or len(ordinary_values) != 1:
        return None
    return early_values.pop(), ordinary_values.pop()


def personal_history_eligibility(
    detail: Mapping[str, Any] | None,
    participants: list[dict[str, Any]] | None = None,
) -> str:
    """Return the explicit local-match eligibility used by consumers."""
    if not isinstance(detail, Mapping):
        return "unknown"
    info = detail.get("info")
    if not isinstance(info, Mapping):
        return "unknown"
    required = ("gameMode", "mapId", "queueId", "gameDuration")
    if any(key not in info for key in required):
        return "unknown"
    try:
        queue_id = int(info.get("queueId"))
        map_id = int(info.get("mapId"))
        duration = float(info.get("gameDuration"))
    except (TypeError, ValueError, OverflowError):
        return "unknown"
    surrender_flags = _surrender_flags(detail, participants)
    if surrender_flags is None:
        return "unknown"
    early_surrender, ordinary_surrender = surrender_flags
    eligible = (
        str(info.get("gameMode")) == "CLASSIC"
        and map_id == 11
        and queue_id in {400, 420, 440, 490, 700}
        and math.isfinite(duration)
        and duration >= 300
        and not early_surrender
        and not ordinary_surrender
    )
    return "eligible" if eligible else "ineligible"


def _participant_for_puuid(
    participants: list[dict[str, Any]], puuid: str,
) -> dict[str, Any] | None:
    for participant in participants:
        if isinstance(participant, dict) and participant.get("puuid") == puuid:
            return participant
    return None


def parse_personal_history_v2(
    timeline: Mapping[str, Any] | None,
    puuid: str,
    participants: list[dict[str, Any]] | None = None,
    *,
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract the v2 feature row for one local participant.

    ``detail`` contributes only match eligibility and, when ``participants`` is
    omitted, the participant list.  It never supplies fallback feature values.
    """
    participant_list = participants
    if participant_list is None and isinstance(detail, Mapping):
        info = detail.get("info")
        raw = info.get("participants") if isinstance(info, Mapping) else None
        if isinstance(raw, list):
            participant_list = [item for item in raw if isinstance(item, dict)]
    participant_list = participant_list or []
    local = _participant_for_puuid(participant_list, puuid)
    local_id = _positive_id(local.get("participantId")) if local else None

    surrender_flags = _surrender_flags(detail, participant_list)
    values: dict[str, Any] = {
        "feature_contract_version": PARITY_V2_VERSION,
        "personal_history_eligibility": personal_history_eligibility(
            detail, participant_list
        ),
        "timeline_observed_through_s": None,
        **{feature: None for feature in V2_FEATURE_ORDER},
        "team_state": {
            "feature": "team_gold_diff_15m",
            "feature_contract_version": PARITY_V2_VERSION,
            "team_gold_diff_15m": None,
            "observed_through_s": None,
            "non_surrendered": (
                not surrender_flags[1] if surrender_flags is not None else None
            ),
        },
    }

    observed = [
        timestamp
        for timestamp, _, frame in _frames(timeline)
        if isinstance(frame.get("participantFrames"), Mapping)
        and bool(frame.get("participantFrames"))
    ]
    if observed:
        observed_through = max(observed) / 1000.0
        values["timeline_observed_through_s"] = observed_through
        values["team_state"]["observed_through_s"] = observed_through
    if local_id is None:
        return values

    values.update(_checkpoint_values(timeline, local_id, participant_list))
    values.update(parse_recall_features_v2(timeline, local_id, participant_list))
    values.update(parse_early_fight_features_v2(timeline, local_id, participant_list))
    values["first_dragon_by_20m_s"] = parse_first_dragon_v2(
        timeline, local_id, participant_list
    )
    values["first_riftherald_by_20m_s"] = parse_first_riftherald_v2(
        timeline, local_id, participant_list
    )
    values["first_baron_by_20m_s"] = parse_first_baron_v2(
        timeline, local_id, participant_list
    )
    # Smite-contest provenance is not present in match-v5 timelines; keep both
    # bounded fields unavailable rather than infer contests from kills.
    values["smite_contests_before_15m"] = None
    values["smite_contests_before_20m"] = None
    values["plates_taken_by_14m"] = parse_plates_v2(timeline, local_id, participant_list)
    values["team_state"]["team_gold_diff_15m"] = values["team_gold_diff_15m"]
    return values

__all__ = [
    "EARLY_FIGHT_CUTOFF_MS",
    "EVENTS_MISSING",
    "EVENTS_UNUSABLE",
    "EVENTS_VALID",
    "EVENTS_VALID_EMPTY",
    "FOURTEEN_MINUTE_MS",
    "FIFTEEN_MINUTE_MS",
    "PARITY_V2_VERSION",
    "parse_first_baron_v2",
    "parse_first_objective_v2",
    "parse_first_riftherald_v2",
    "TEN_MINUTE_MS",
    "TWENTY_MINUTE_MS",
    "V2_ALL_ROLES",
    "V2_CHECKPOINT_FEATURES",
    "V2_FEATURE_ORDER",
    "V2_FEATURES",
    "V2_LANE_ROLES",
    "parse_early_fight_features_v2",
    "parse_first_dragon_v2",
    "parse_plates_v2",
    "parse_personal_history_v2",
    "parse_recall_features_v2",
    "personal_history_eligibility",
]

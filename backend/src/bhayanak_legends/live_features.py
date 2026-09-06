"""Exact Live WP feature contract and cross-source adapters.

The Live WP model deliberately has a smaller seam than the existing live
snapshot.  A training Timeline and an official Live Client Data snapshot are
accepted only when every value in the seam can be reconstructed without a
proxy.  In particular, the seam contains no gold or XP inputs: inventory
*value* means the versioned shop ``gold.total`` for each item, not an estimate
of a player's current gold.

The module is intentionally independent from :mod:`bhayanak_legends.live`.
That bridge owns polling and presentation; this module owns the immutable
training/live parity boundary consumed later by the model runtime.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any, Final


LIVE_WP_CONTRACT_VERSION: Final[str] = "live-wp-v2"
LIVE_POLL_INTERVAL_S: Final[float] = 2.0
MAX_CAPTURE_AGE_S: Final[float] = 5.0
TIMELINE_FRAME_INTERVAL_S: Final[float] = 60.0
SUPPORTED_MODE: Final[str] = "CLASSIC"
TEAM_IDS: Final[tuple[int, int]] = (100, 200)


@dataclass(frozen=True)
class LiveFeatureDefinition:
    """One ordered, signed model input and its source contract."""

    name: str
    unit: str
    formula: str
    source_fields: tuple[str, ...]
    side_orientation: str = "focal team minus opposing team"
    cadence_s: float = LIVE_POLL_INTERVAL_S
    max_staleness_s: float = MAX_CAPTURE_AGE_S
    missing_data_rule: str = "missing or non-finite input suppresses the complete vector"


FEATURE_REGISTRY: tuple[LiveFeatureDefinition, ...] = (
    LiveFeatureDefinition(
        "elapsed_time_s",
        "seconds",
        "game clock at the observation (Timeline frame timestamp / 1000)",
        ("info.frames[].timestamp", "gameData.gameTime"),
        side_orientation="side invariant",
    ),
    LiveFeatureDefinition(
        "team_kills_diff",
        "kills",
        "focal-side CHAMPION_KILL killer count through t minus opposing-side count",
        ("CHAMPION_KILL.killerId", "scores.kills"),
    ),
    LiveFeatureDefinition(
        "team_deaths_diff",
        "deaths",
        "focal-side CHAMPION_KILL victim count through t minus opposing-side count",
        ("CHAMPION_KILL.victimId", "scores.deaths"),
    ),
    LiveFeatureDefinition(
        "team_assists_diff",
        "assists",
        "focal-side assistingParticipantIds count through t minus opposing-side count",
        ("CHAMPION_KILL.assistingParticipantIds", "scores.assists"),
    ),
    LiveFeatureDefinition(
        "team_cs_diff",
        "minion kills",
        "sum(minionsKilled + jungleMinionsKilled) on focal side minus opposing side",
        ("participantFrames[].minionsKilled", "participantFrames[].jungleMinionsKilled", "scores.creepScore"),
    ),
    LiveFeatureDefinition(
        "team_levels_diff",
        "champion levels",
        "sum(level) on focal side minus opposing side",
        ("participantFrames[].level", "allPlayers[].level"),
    ),
    LiveFeatureDefinition(
        "team_inventory_value_diff",
        "gold",
        "sum(item count * version-matched Data Dragon items.data[item].gold.total) on focal side minus opposing side",
        ("participantFrames item events", "allPlayers[].items[]", "items.data[].gold.total"),
    ),
    LiveFeatureDefinition(
        "team_turrets_diff",
        "turrets",
        "count BUILDING_KILL tower events by killer side through t, signed by focal side",
        ("BUILDING_KILL.buildingType", "BUILDING_KILL.killerId", "TurretKilled.KillerName"),
    ),
    LiveFeatureDefinition(
        "team_dragons_diff",
        "dragons",
        "count DRAGON elite kills by killer side through t, signed by focal side",
        ("ELITE_MONSTER_KILL.monsterType", "ELITE_MONSTER_KILL.killerTeamId", "DragonKill.KillerName"),
    ),
    LiveFeatureDefinition(
        "team_heralds_diff",
        "Heralds",
        "count RIFTHERALD elite kills by killer side through t, signed by focal side",
        ("ELITE_MONSTER_KILL.monsterType", "ELITE_MONSTER_KILL.killerTeamId", "HeraldKill.KillerName"),
    ),
    LiveFeatureDefinition(
        "team_barons_diff",
        "Barons",
        "count BARON_NASHOR elite kills by killer side through t, signed by focal side",
        ("ELITE_MONSTER_KILL.monsterType", "ELITE_MONSTER_KILL.killerTeamId", "BaronKill.KillerName"),
    ),
)

FEATURE_ORDER: tuple[str, ...] = tuple(feature.name for feature in FEATURE_REGISTRY)


@dataclass(frozen=True)
class LiveFeatureRegistry:
    """Machine-readable registry metadata for model cards and parity tests."""

    version: str
    features: tuple[LiveFeatureDefinition, ...]
    live_poll_interval_s: float
    max_capture_age_s: float
    timeline_frame_interval_s: float
    side_orientation: str
    missing_data_policy: str
    patch_semantics: str

    @property
    def feature_order(self) -> tuple[str, ...]:
        return tuple(feature.name for feature in self.features)

    def as_dict(self) -> dict[str, Any]:
        """Return JSON-safe registry metadata without callable implementation details."""
        return {
            "contract_version": self.version,
            "feature_order": list(self.feature_order),
            "features": [
                {
                    "name": feature.name,
                    "unit": feature.unit,
                    "formula": feature.formula,
                    "source_fields": list(feature.source_fields),
                    "side_orientation": feature.side_orientation,
                    "cadence_s": feature.cadence_s,
                    "max_staleness_s": feature.max_staleness_s,
                    "missing_data_rule": feature.missing_data_rule,
                }
                for feature in self.features
            ],
            "live_poll_interval_s": self.live_poll_interval_s,
            "max_capture_age_s": self.max_capture_age_s,
            "timeline_frame_interval_s": self.timeline_frame_interval_s,
            "side_orientation": self.side_orientation,
            "missing_data_policy": self.missing_data_policy,
            "patch_semantics": self.patch_semantics,
        }


LIVE_FEATURE_REGISTRY = LiveFeatureRegistry(
    version=LIVE_WP_CONTRACT_VERSION,
    features=FEATURE_REGISTRY,
    live_poll_interval_s=LIVE_POLL_INTERVAL_S,
    max_capture_age_s=MAX_CAPTURE_AGE_S,
    timeline_frame_interval_s=TIMELINE_FRAME_INTERVAL_S,
    side_orientation="signed focal-side-minus-opponent; team 100/ORDER positive and team 200/CHAOS is the exact sign mirror",
    missing_data_policy=(
        "Suppress the complete vector for missing/non-finite required fields, unknown team mapping, "
        "unmatched patch/Data Dragon versions, unsupported item IDs, ambiguous event actors, or stale captures. "
        "Future events are ignored rather than read ahead."
    ),
    patch_semantics=(
        "Match gameVersion and Data Dragon version by numeric major.minor; retain the full Data Dragon version "
        "in the vector metadata. Official allgamedata normally omits gameVersion, so the live adapter requires "
        "an explicit patch (or an equivalent gameData.gameVersion supplied by its caller)."
    ),
)


@dataclass(frozen=True)
class DataDragonCatalog:
    """Immutable item-cost table loaded from one Data Dragon version."""

    version: str
    item_costs: Mapping[int, float]

    def __post_init__(self) -> None:
        version = self.version.strip() if isinstance(self.version, str) else ""
        if _patch_key(version) is None:
            raise ValueError("Data Dragon version must contain numeric major.minor")
        costs: dict[int, float] = {}
        for raw_id, raw_cost in self.item_costs.items():
            item_id = _strict_int(raw_id)
            cost = _finite_number(raw_cost)
            if item_id is None or item_id <= 0 or cost is None or cost < 0:
                raise ValueError("Data Dragon item costs must be finite non-negative values")
            costs[item_id] = cost
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "item_costs", costs)

    @classmethod
    def from_payload(cls, version: str, payload: Mapping[str, Any]) -> DataDragonCatalog:
        """Build a catalog from the official ``item.json`` response shape."""
        data = payload.get("data") if isinstance(payload, Mapping) else None
        if not isinstance(data, Mapping):
            raise ValueError("Data Dragon item payload must contain a data object")
        costs: dict[int, float] = {}
        for raw_id, raw_item in data.items():
            item_id = _strict_int(raw_id)
            if item_id is None or not isinstance(raw_item, Mapping):
                continue
            gold = raw_item.get("gold")
            if not isinstance(gold, Mapping):
                continue
            total = _finite_number(gold.get("total"))
            if total is not None and total >= 0:
                costs[item_id] = total
        return cls(version, costs)

    def cost(self, item_id: int) -> float | None:
        return self.item_costs.get(item_id)

    def matches_patch(self, patch: str) -> bool:
        return _patch_key(self.version) == _patch_key(patch)



@dataclass(frozen=True)
class LiveFeatureVector:
    """A complete, versioned model vector with auditable source metadata."""

    contract_version: str
    side: int
    observed_at_s: float
    patch: str
    data_dragon_version: str
    values: tuple[float, ...]

    @property
    def vector(self) -> tuple[float, ...]:
        return self.values

    def as_tuple(self) -> tuple[float, ...]:
        return self.values

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "side": self.side,
            "observed_at_s": self.observed_at_s,
            "patch": self.patch,
            "data_dragon_version": self.data_dragon_version,
            "features": dict(zip(FEATURE_ORDER, self.values, strict=True)),
        }


_ELITE_TO_FEATURE: Final[dict[str, str]] = {
    "DRAGON": "team_dragons_diff",
    "RIFTHERALD": "team_heralds_diff",
    "BARON_NASHOR": "team_barons_diff",
}
_LIVE_OBJECTIVE_NAMES: Final[dict[str, str]] = {
    "DragonKill": "team_dragons_diff",
    "HeraldKill": "team_heralds_diff",
    "BaronKill": "team_barons_diff",
    "TurretKilled": "team_turrets_diff",
}
_ITEM_EVENT_TYPES: Final[frozenset[str]] = frozenset(
    {"ITEM_PURCHASED", "ITEM_SOLD", "ITEM_UNDO", "ITEM_COMPLETED"}
)


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _strict_int(value: object) -> int | None:
    if isinstance(value, str):
        normalized = value.strip()
        return int(normalized) if normalized.isdecimal() else None
    number = _finite_number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _patch_key(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().split(".")
    if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    return int(parts[0]), int(parts[1])


def _patch_for(match_or_data: Mapping[str, Any], fallback: str | None = None) -> str | None:
    candidates: list[object] = []
    info = match_or_data.get("info")
    if isinstance(info, Mapping):
        candidates.append(info.get("gameVersion"))
    candidates.append(match_or_data.get("gameVersion"))
    candidates.append(fallback)
    for candidate in candidates:
        if isinstance(candidate, str) and _patch_key(candidate) is not None:
            return candidate.strip()
    return None


def _validate_patch(patch: str | None, catalog: DataDragonCatalog) -> str | None:
    if not isinstance(patch, str):
        return None
    normalized = patch.strip()
    if _patch_key(normalized) is None or not catalog.matches_patch(normalized):
        return None
    return normalized


def _side_difference(values: Mapping[int, float], side: int) -> float:
    other = TEAM_IDS[1] if side == TEAM_IDS[0] else TEAM_IDS[0]
    return float(values[side] - values[other])


def _vector(
    *,
    side: int,
    elapsed_s: float,
    patch: str,
    catalog: DataDragonCatalog,
    team_values: Mapping[str, Mapping[int, float]],
) -> LiveFeatureVector:
    values = (elapsed_s, *(_side_difference(team_values[name], side) for name in FEATURE_ORDER[1:]))
    return LiveFeatureVector(
        contract_version=LIVE_WP_CONTRACT_VERSION,
        side=side,
        observed_at_s=elapsed_s,
        patch=patch,
        data_dragon_version=catalog.version,
        values=tuple(float(value) for value in values),
    )


def _empty_team_values() -> dict[str, dict[int, float]]:
    return {
        name: {TEAM_IDS[0]: 0.0, TEAM_IDS[1]: 0.0}
        for name in FEATURE_ORDER[1:]
    }


def _valid_team_map(participants: Sequence[Mapping[str, Any]]) -> dict[int, int] | None:
    if len(participants) != 10:
        return None
    participant_team: dict[int, int] = {}
    counts = {TEAM_IDS[0]: 0, TEAM_IDS[1]: 0}
    for participant in participants:
        if not isinstance(participant, Mapping):
            return None
        participant_id = _strict_int(participant.get("participantId"))
        team_id = _strict_int(participant.get("teamId"))
        if participant_id is None or participant_id <= 0 or team_id not in counts:
            return None
        if participant_id in participant_team:
            return None
        participant_team[participant_id] = team_id
        counts[team_id] += 1
    return participant_team if counts == {TEAM_IDS[0]: 5, TEAM_IDS[1]: 5} else None


def _timeline_frames(timeline: Mapping[str, Any]) -> list[tuple[float, Mapping[str, Any]]] | None:
    info = timeline.get("info")
    if not isinstance(info, Mapping) or not isinstance(info.get("frames"), list):
        return None
    frames: list[tuple[float, Mapping[str, Any]]] = []
    previous = -1.0
    for raw_frame in info["frames"]:
        if not isinstance(raw_frame, Mapping):
            return None
        timestamp = _finite_number(raw_frame.get("timestamp"))
        if timestamp is None or timestamp < 0 or timestamp < previous:
            return None
        previous = timestamp
        frames.append((timestamp, raw_frame))
    return frames


def _event_time(raw_event: Mapping[str, Any], frame_timestamp: float) -> float | None:
    value = _finite_number(raw_event.get("timestamp"))
    if value is None:
        # Timeline event timestamps are required for this contract.  Falling
        # back to a frame boundary would silently move a state across an
        # observation and would make parity dependent on frame packing.
        return None
    return value if value >= 0 else None


def _selected_frame(
    frames: Sequence[tuple[float, Mapping[str, Any]]], target_ms: float
) -> Mapping[str, Any] | None:
    if not frames or frames[-1][0] < target_ms:
        return None
    chosen: Mapping[str, Any] | None = None
    for timestamp, frame in frames:
        if timestamp > target_ms:
            break
        chosen = frame
    return chosen


def _timeline_event_rows(
    frames: Sequence[tuple[float, Mapping[str, Any]]], target_ms: float
) -> list[tuple[float, Mapping[str, Any]]] | None:
    rows: list[tuple[float, Mapping[str, Any]]] = []
    for frame_timestamp, frame in frames:
        if frame_timestamp > target_ms:
            continue
        raw_events = frame.get("events")
        if raw_events is None:
            raw_events = []
        if not isinstance(raw_events, list):
            return None
        for raw_event in raw_events:
            if not isinstance(raw_event, Mapping):
                return None
            event_type = raw_event.get("type")
            if event_type not in {
                "CHAMPION_KILL",
                "BUILDING_KILL",
                "ELITE_MONSTER_KILL",
                *_ITEM_EVENT_TYPES,
            }:
                continue
            timestamp = _event_time(raw_event, frame_timestamp)
            if timestamp is None:
                return None
            if timestamp <= target_ms:
                rows.append((timestamp, raw_event))
    rows.sort(key=lambda row: row[0])
    return rows


def _item_cost(catalog: DataDragonCatalog, raw_id: object) -> tuple[int, float] | None:
    item_id = _strict_int(raw_id)
    if item_id is None or item_id <= 0:
        return None
    cost = catalog.cost(item_id)
    return (item_id, cost) if cost is not None and math.isfinite(cost) and cost >= 0 else None


def _timeline_inventory(
    rows: Sequence[tuple[float, Mapping[str, Any]]],
    participant_team: Mapping[int, int],
    catalog: DataDragonCatalog,
) -> dict[int, float] | None:
    inventory: dict[int, dict[int, int]] = {side: defaultdict(int) for side in TEAM_IDS}
    last_timestamp = -1.0
    for timestamp, event in rows:
        if timestamp < last_timestamp:
            return None
        last_timestamp = timestamp
        event_type = event.get("type")
        if event_type == "ITEM_COMPLETED":
            # Completion is informational in Timeline v2.  Purchases already
            # establish the inventory transition; counting it would duplicate
            # an item and diverge from Live Client Data.
            continue
        if event_type not in {"ITEM_PURCHASED", "ITEM_SOLD", "ITEM_UNDO"}:
            continue
        participant_id = _strict_int(event.get("participantId"))
        if participant_id is None or participant_id not in participant_team:
            return None
        team = participant_team[participant_id]
        if event_type == "ITEM_PURCHASED":
            item = _item_cost(catalog, event.get("itemId"))
            if item is None:
                return None
            item_id, _cost = item
            inventory[team][item_id] += 1
        elif event_type == "ITEM_SOLD":
            item = _item_cost(catalog, event.get("itemId"))
            if item is None:
                return None
            item_id, _cost = item
            if inventory[team][item_id] <= 0:
                return None
            inventory[team][item_id] -= 1
        elif event_type == "ITEM_UNDO":
            before = _strict_int(event.get("beforeId"))
            after = _strict_int(event.get("afterId"))
            before_item = _item_cost(catalog, before) if before else None
            after_item = _item_cost(catalog, after) if after else None
            if (before_item is None) == (after_item is None):
                return None
            item_id = before_item[0] if before_item is not None else after_item[0]
            if before_item is not None:
                if inventory[team][item_id] <= 0:
                    return None
                inventory[team][item_id] -= 1
            else:
                inventory[team][item_id] += 1
    totals = {side: 0.0 for side in TEAM_IDS}
    for side in TEAM_IDS:
        for item_id, count in inventory[side].items():
            cost = catalog.cost(item_id)
            if cost is None or count < 0:
                return None
            totals[side] += float(count) * cost
    return totals


def _timeline_event_features(
    rows: Sequence[tuple[float, Mapping[str, Any]]],
    participant_team: Mapping[int, int],
) -> dict[str, dict[int, float]] | None:
    values = _empty_team_values()
    for _timestamp, event in rows:
        event_type = event.get("type")
        if event_type == "CHAMPION_KILL":
            killer = _strict_int(event.get("killerId"))
            victim = _strict_int(event.get("victimId"))
            assists = event.get("assistingParticipantIds")
            if (
                killer is None
                or victim is None
                or killer not in participant_team
                or victim not in participant_team
                or not isinstance(assists, list)
            ):
                return None
            values["team_kills_diff"][participant_team[killer]] += 1
            values["team_deaths_diff"][participant_team[victim]] += 1
            for raw_assist in assists:
                assister = _strict_int(raw_assist)
                if assister is None or assister not in participant_team:
                    return None
                values["team_assists_diff"][participant_team[assister]] += 1
        elif event_type == "ELITE_MONSTER_KILL":
            feature = _ELITE_TO_FEATURE.get(str(event.get("monsterType")))
            if feature is None:
                continue
            killer_team = _strict_int(event.get("killerTeamId"))
            if killer_team not in TEAM_IDS:
                return None
            values[feature][killer_team] += 1
        elif event_type == "BUILDING_KILL" and event.get("buildingType") == "TOWER_BUILDING":
            killer = _strict_int(event.get("killerId"))
            if killer is None or killer not in participant_team:
                return None
            values["team_turrets_diff"][participant_team[killer]] += 1
    return values


def adapt_timeline_state(
    match: Mapping[str, Any] | None,
    timeline: Mapping[str, Any] | None,
    observed_at_s: float,
    side: int,
    data_dragon: DataDragonCatalog,
) -> LiveFeatureVector | None:
    """Extract one focal-side vector from an exact Riot match/timeline state.

    ``observed_at_s`` is game time, not wall-clock time.  A Timeline must have
    a frame at or after that time to prove coverage; the selected frame is the
    latest frame at or before it.  All event timestamps are filtered at the
    same boundary, so an event after the observation cannot leak into training.
    """
    if not isinstance(match, Mapping) or not isinstance(timeline, Mapping) or side not in TEAM_IDS:
        return None
    elapsed_s = _finite_number(observed_at_s)
    if elapsed_s is None or elapsed_s < 0:
        return None
    patch = _patch_for(match)
    if _validate_patch(patch, data_dragon) is None:
        return None
    info = match.get("info")
    participants = info.get("participants") if isinstance(info, Mapping) else None
    if not isinstance(participants, list):
        return None
    participant_team = _valid_team_map(participants)
    if participant_team is None:
        return None
    if isinstance(info, Mapping) and info.get("gameMode") not in (None, SUPPORTED_MODE):
        return None
    frames = _timeline_frames(timeline)
    if frames is None:
        return None
    target_ms = elapsed_s * 1000.0
    frame = _selected_frame(frames, target_ms)
    if frame is None:
        return None
    participant_frames = frame.get("participantFrames")
    if not isinstance(participant_frames, Mapping):
        return None
    team_values = _empty_team_values()
    seen: set[int] = set()
    for raw_id, raw_snapshot in participant_frames.items():
        participant_id = _strict_int(raw_id)
        if participant_id is None or participant_id not in participant_team or participant_id in seen:
            return None
        if not isinstance(raw_snapshot, Mapping):
            return None
        minions = _strict_int(raw_snapshot.get("minionsKilled"))
        jungle = _strict_int(raw_snapshot.get("jungleMinionsKilled"))
        level = _strict_int(raw_snapshot.get("level"))
        if minions is None or jungle is None or level is None or minions < 0 or jungle < 0 or level < 0:
            return None
        seen.add(participant_id)
        team = participant_team[participant_id]
        team_values["team_cs_diff"][team] += minions + jungle
        team_values["team_levels_diff"][team] += level
    if seen != set(participant_team):
        return None
    rows = _timeline_event_rows(frames, target_ms)
    if rows is None:
        return None
    event_values = _timeline_event_features(rows, participant_team)
    if event_values is None:
        return None
    inventory = _timeline_inventory(rows, participant_team, data_dragon)
    if inventory is None:
        return None
    for feature in ("team_kills_diff", "team_deaths_diff", "team_assists_diff", "team_turrets_diff", "team_dragons_diff", "team_heralds_diff", "team_barons_diff"):
        team_values[feature] = event_values[feature]
    team_values["team_inventory_value_diff"] = inventory
    return _vector(side=side, elapsed_s=elapsed_s, patch=patch, catalog=data_dragon, team_values=team_values)


def _canonical_live_team(raw: object) -> int | None:
    if not isinstance(raw, str):
        return None
    normalized = raw.strip().upper()
    return {"ORDER": 100, "CHAOS": 200}.get(normalized)


def _live_actor_side(raw: object, name_to_team: Mapping[str, int]) -> int | None:
    direct = _canonical_live_team(raw)
    if direct is not None:
        return direct
    if not isinstance(raw, str) or not raw.strip():
        return None
    return name_to_team.get(raw.strip())


def _capture_time(snapshot: Mapping[str, Any], explicit: float | None) -> float | None:
    if explicit is not None:
        return _finite_number(explicit)
    for key in ("observed_at_s", "observedAtS", "captured_at_s"):
        candidate = _finite_number(snapshot.get(key))
        if candidate is not None:
            return candidate
    return None


def adapt_live_client_state(
    snapshot: Mapping[str, Any] | None,
    patch: str | None,
    data_dragon: DataDragonCatalog,
    observed_at_s: float | None = None,
    now_s: float | None = None,
) -> LiveFeatureVector | None:
    """Extract the local-side vector from one official Live Client snapshot.

    ``patch`` is an explicit caller-supplied version because the official
    allgamedata response does not consistently include gameVersion.  When a
    wall-clock ``now_s`` is supplied, a capture timestamp must also be
    supplied (explicitly or in one of the private observation metadata keys),
    and captures older than :data:`MAX_CAPTURE_AGE_S` are suppressed.
    """
    if not isinstance(snapshot, Mapping):
        return None
    game_data = snapshot.get("gameData")
    active_player = snapshot.get("activePlayer")
    players = snapshot.get("allPlayers")
    if not isinstance(game_data, Mapping) or not isinstance(active_player, Mapping) or not isinstance(players, list):
        return None
    effective_patch = _patch_for(game_data, patch)
    if _validate_patch(effective_patch, data_dragon) is None:
        return None
    mode = game_data.get("gameMode")
    if mode not in (None, SUPPORTED_MODE):
        return None
    elapsed_s = _finite_number(game_data.get("gameTime"))
    if elapsed_s is None or elapsed_s < 0:
        return None
    capture_s = _capture_time(snapshot, observed_at_s)
    if now_s is not None:
        now = _finite_number(now_s)
        if now is None or capture_s is None or capture_s < 0 or now < capture_s or now - capture_s > MAX_CAPTURE_AGE_S:
            return None
    if capture_s is not None and capture_s < 0:
        return None

    local_name = active_player.get("summonerName")
    if not isinstance(local_name, str) or not local_name.strip():
        return None
    name_to_team: dict[str, int] = {}
    team_values = _empty_team_values()
    counts = {TEAM_IDS[0]: 0, TEAM_IDS[1]: 0}
    for raw_player in players:
        if not isinstance(raw_player, Mapping):
            return None
        name = raw_player.get("summonerName")
        team = _canonical_live_team(raw_player.get("team"))
        if not isinstance(name, str) or not name.strip() or team is None:
            return None
        name = name.strip()
        if name in name_to_team:
            return None
        name_to_team[name] = team
        counts[team] += 1
        level = _strict_int(raw_player.get("level"))
        scores = raw_player.get("scores")
        items = raw_player.get("items")
        if level is None or level < 0 or not isinstance(scores, Mapping) or not isinstance(items, list):
            return None
        kills = _strict_int(scores.get("kills"))
        deaths = _strict_int(scores.get("deaths"))
        assists = _strict_int(scores.get("assists"))
        cs = _strict_int(scores.get("creepScore"))
        if any(value is None or value < 0 for value in (kills, deaths, assists, cs)):
            return None
        team_values["team_kills_diff"][team] += kills
        team_values["team_deaths_diff"][team] += deaths
        team_values["team_assists_diff"][team] += assists
        team_values["team_cs_diff"][team] += cs
        team_values["team_levels_diff"][team] += level
        for raw_item in items:
            if not isinstance(raw_item, Mapping):
                return None
            item = _item_cost(data_dragon, raw_item.get("itemID"))
            count = _strict_int(raw_item.get("count"))
            if item is None or count is None or count <= 0:
                return None
            _item_id, cost = item
            team_values["team_inventory_value_diff"][team] += count * cost
    if counts != {TEAM_IDS[0]: 5, TEAM_IDS[1]: 5} or name_to_team.get(local_name.strip()) is None:
        return None
    local_side = name_to_team[local_name.strip()]

    events_container = snapshot.get("events")
    events = events_container.get("Events") if isinstance(events_container, Mapping) else None
    if not isinstance(events, list):
        return None
    for raw_event in events:
        if not isinstance(raw_event, Mapping):
            return None
        event_name = raw_event.get("EventName")
        feature = _LIVE_OBJECTIVE_NAMES.get(event_name) if isinstance(event_name, str) else None
        if feature is None:
            continue
        event_time = _finite_number(raw_event.get("EventTime"))
        if event_time is None or event_time < 0:
            return None
        if event_time > elapsed_s:
            continue
        actor = raw_event.get("KillerName")
        actor_side = _live_actor_side(actor, name_to_team)
        if actor_side not in TEAM_IDS:
            return None
        team_values[feature][actor_side] += 1
    return _vector(
        side=local_side,
        elapsed_s=elapsed_s,
        patch=effective_patch,
        catalog=data_dragon,
        team_values=team_values,
    )


__all__ = [
    "DataDragonCatalog",
    "FEATURE_ORDER",
    "FEATURE_REGISTRY",
    "LIVE_FEATURE_REGISTRY",
    "LIVE_POLL_INTERVAL_S",
    "LIVE_WP_CONTRACT_VERSION",
    "LiveFeatureDefinition",
    "LiveFeatureRegistry",
    "LiveFeatureVector",
    "MAX_CAPTURE_AGE_S",
    "TIMELINE_FRAME_INTERVAL_S",
    "adapt_live_client_state",
    "adapt_timeline_state",
]

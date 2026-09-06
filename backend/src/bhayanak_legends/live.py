"""Live Companion bridge v2: rich champ-select and in-game snapshots.

Polls the LCU (via an injected transport from :mod:`bhayanak_legends.lcu`) every
``poll_interval`` seconds; when the gameflow phase enters the in-game window it
also polls the Live Client Data API on 127.0.0.1:2999. Snapshot changes are
published over SSE as ``champselect.state`` / ``live.state``, plus a coarse
``live.status`` health frame. On platforms without a running League client
(e.g. Linux dev) every probe returns None → idle snapshots with ``last_error``
left None; expected absences are not errors.

COMPLIANCE (AGENTS.md): enemy summoner names are dropped at this service layer —
``theirTeam`` participants become name-less champion cells (name always null).
In-game ``allPlayers`` summoner names ARE official spectator data and are kept.
Enemy ability/ult timers remain out of scope entirely.
"""

from __future__ import annotations


import asyncio
import contextlib
from dataclasses import dataclass
import inspect
import logging
import math
import time
from typing import get_args

from pydantic import BaseModel, Field

from .live_features import LIVE_WP_CONTRACT_VERSION, LiveFeatureVector

from .models import (
    AllyCell,
    CellState,
    ChampSelectBan,
    ChampSelectSnapshot,
    ChampSelectStatus,
    CsBan,
    EnemyCell,
    GameMode,
    GameflowPhase,
    InGameStatus,
    LiveInferenceStatus,
    LiveEventDelta,
    LiveEventName,
    LiveInference,
    LiveStatus,
    LiveState,
)

log = logging.getLogger("bhayanak_legends.live")

CHAMP_SELECT_PHASE = "champselect"
IN_GAME_PHASES = {"gamestart", "inprogress"}
MAX_EVENTS = 40


_GAME_MODES = frozenset(get_args(GameMode))
_LIVE_EVENT_NAMES = frozenset(get_args(LiveEventName))




class ItemLive(BaseModel):
    id: int = 0
    count: int = 0


class PlayerLive(BaseModel):
    summoner: str
    champion: str | None = None
    level: int = 1
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    cs: int = 0
    ward_score: float = 0.0
    items: list[ItemLive] = Field(default_factory=list)


class LiveEvent(BaseModel):
    name: LiveEventName
    t_s: float = 0.0
    actor: str | None = None
    victim: str | None = None
    detail: str | None = None


class LiveTeams(BaseModel):
    order: list[PlayerLive] = Field(default_factory=list)
    chaos: list[PlayerLive] = Field(default_factory=list)

    def __getitem__(self, key: str) -> list[PlayerLive]:
        return getattr(self, key)


class InGameSnapshot(BaseModel):
    active: bool = False
    clock_s: float = 0.0
    mode: GameMode | None = None
    local_summoner: str | None = None
    local_champion: str | None = None
    teams: LiveTeams = Field(default_factory=LiveTeams)
    events: list[LiveEvent] = Field(default_factory=list)
    inference: LiveInference = Field(default_factory=LiveInference)
    event_deltas: list[LiveEventDelta] = Field(default_factory=list)

_ASSIGNED_ROLES = frozenset({"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"})


def _participant_state(participant: dict, *, locked: bool = False) -> CellState:
    if locked:
        return "locked"
    if participant.get("championId"):
        return "picked"
    if participant.get("championPickIntent"):
        return "intent"
    return "none"


def _assigned_role(participant: dict) -> str | None:
    raw_role = participant.get("assignedPosition")
    if not isinstance(raw_role, str):
        return None
    role = raw_role.strip().upper()
    return role if role in _ASSIGNED_ROLES else None


def _has_completed_local_pick(
    actions: object,
    local_cell: object,
    local_champion_id: int,
) -> bool:
    if not isinstance(local_cell, int) or isinstance(local_cell, bool) or not local_champion_id:
        return False
    if not isinstance(actions, list):
        return False
    groups = actions if any(isinstance(group, list) for group in actions) else [actions]
    for group in groups:
        if not isinstance(group, list):
            continue
        for action in group:
            if not isinstance(action, dict):
                continue
            action_cell = action.get("actorCellId")
            action_champion_id = action.get("championId")
            if (
                not isinstance(action_cell, int)
                or isinstance(action_cell, bool)
                or not isinstance(action_champion_id, int)
                or isinstance(action_champion_id, bool)
                or action_cell != local_cell
                or action_champion_id != local_champion_id
                or action_champion_id == 0
                or action.get("completed") is not True
                or str(action.get("type") or "").lower() != "pick"
            ):
                continue
            return True
    return False

def _cs_bans(raw_bans: dict | None, key: str, names: dict[int, str]) -> list[CsBan]:
    bans: list[CsBan] = []
    for entry in (raw_bans or {}).get(key) or []:
        champion_id = int(entry.get("championId") or 0)
        if not champion_id:
            continue  # pick turn not used yet
        bans.append(CsBan(champion_id=champion_id, champion=names.get(champion_id)))
    return bans


def build_champ_select_snapshot(
    session: dict | None,
    phase: GameflowPhase | None,
    names: dict[int, str],
) -> ChampSelectSnapshot:
    """Pure: LCU champ-select session payload → ChampSelectSnapshot."""
    if not session:
        return ChampSelectSnapshot(active=bool(phase), phase=phase)
    timer = session.get("timer") or {}
    local_cell = session.get("localTeamCellId")
    raw_bans = session.get("bans") or {}
    actions = session.get("actions")
    ally: list[AllyCell] = []
    local_assigned_role: str | None = None
    for participant in sorted(session.get("myTeam") or [], key=lambda p: p.get("cellId", 0)):
        champion_id = int(participant.get("championId") or 0)
        participant_cell = participant.get("cellId")
        is_local = (
            isinstance(local_cell, int)
            and not isinstance(local_cell, bool)
            and isinstance(participant_cell, int)
            and not isinstance(participant_cell, bool)
            and participant_cell == local_cell
        )
        if is_local:
            local_assigned_role = _assigned_role(participant)
        ally.append(
            AllyCell(
                cell_id=int(participant.get("cellId") or 0),
                champion_id=champion_id,
                champion=names.get(champion_id),
                name=participant.get("summonerName") or None,
                is_local=is_local,
                state=_participant_state(
                    participant,
                    locked=is_local and _has_completed_local_pick(actions, local_cell, champion_id),
                ),
            )
        )
    # COMPLIANCE: theirTeam summoner names are dropped here, before any consumer.
    enemy: list[EnemyCell] = []
    for participant in sorted(session.get("theirTeam") or [], key=lambda p: p.get("cellId", 0)):
        champion_id = int(participant.get("championId") or 0)
        enemy.append(
            EnemyCell(
                cell_id=int(participant.get("cellId") or 0),
                champion_id=champion_id,
                champion=names.get(champion_id),
                name=None,
                state=_participant_state(participant),
            )
        )
    return ChampSelectSnapshot(
        active=True,
        phase=phase,
        timer_sec=int(timer.get("adjustedTimeLeftInSec") or 0),
        local_assigned_role=local_assigned_role,
        bans_ally=_cs_bans(raw_bans, "myTeamBans", names),
        bans_enemy=_cs_bans(raw_bans, "theirTeamBans", names),
        ally=ally,
        enemy=enemy,
    )


def build_live_event(raw: dict) -> LiveEvent:
    return LiveEvent(
        name=str(raw.get("EventName") or "Unknown"),
        t_s=float(raw.get("EventTime") or 0.0),
        actor=raw.get("KillerName") or raw.get("CreatorName"),
        victim=raw.get("VictimName"),
        detail=raw.get("DragonType"),
    )


def _normalize_int(value: object, default: int | None = None) -> int | None:
    if value is _MISSING:
        return default
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _normalize_float(value: object, default: float | None = None) -> float | None:
    if value is _MISSING:
        return default
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


_MISSING = object()


def _build_live_player(raw: object) -> tuple[str, PlayerLive] | None:
    if not isinstance(raw, dict):
        return None
    summoner = raw.get("summonerName")
    if not isinstance(summoner, str) or not summoner.strip():
        return None
    champion = raw.get("championName")
    if champion is not None and not isinstance(champion, str):
        return None
    if "scores" not in raw:
        scores: dict = {}
    else:
        scores = raw["scores"]
        if not isinstance(scores, dict):
            return None

    numeric_fields = {
        "level": _normalize_int(raw.get("level", _MISSING), 1),
        "kills": _normalize_int(scores.get("kills", _MISSING), 0),
        "deaths": _normalize_int(scores.get("deaths", _MISSING), 0),
        "assists": _normalize_int(scores.get("assists", _MISSING), 0),
        "cs": _normalize_int(scores.get("creepScore", _MISSING), 0),
        "ward_score": _normalize_float(scores.get("wardScore", _MISSING), 0.0),
    }
    if any(value is None for value in numeric_fields.values()):
        return None

    items: list[ItemLive] = []
    for item in raw.get("items") or []:
        if not isinstance(item, dict):
            continue
        item_id = _normalize_int(item.get("itemID", _MISSING))
        if not item_id:
            continue
        count = _normalize_int(item.get("count", _MISSING), 0)
        if count is None:
            continue
        items.append(ItemLive(id=item_id, count=count))

    return (
        str(raw.get("team") or "").strip().lower(),
        PlayerLive(
            summoner=summoner,
            champion=champion,
            level=numeric_fields["level"],
            kills=numeric_fields["kills"],
            deaths=numeric_fields["deaths"],
            assists=numeric_fields["assists"],
            cs=numeric_fields["cs"],
            ward_score=numeric_fields["ward_score"],
            items=items,
        ),
    )


def _build_live_event_row(raw: object) -> LiveEvent | None:
    if not isinstance(raw, dict):
        return None
    name = raw.get("EventName")
    if not isinstance(name, str) or name not in _LIVE_EVENT_NAMES:
        return None
    event_time = _normalize_float(raw.get("EventTime", _MISSING), 0.0)
    if event_time is None:
        return None
    actor = raw.get("KillerName") or raw.get("CreatorName")
    victim = raw.get("VictimName")
    detail = raw.get("DragonType")
    if any(value is not None and not isinstance(value, str) for value in (actor, victim, detail)):
        return None
    return LiveEvent(name=name, t_s=event_time, actor=actor, victim=victim, detail=detail)
def build_ingame_snapshot(
    data: dict | None,
    *,
    inference: LiveInference | None = None,
    event_deltas: list[LiveEventDelta] | None = None,
) -> tuple[InGameSnapshot, int | None]:
    """Pure: /liveclientdata/allgamedata payload → (snapshot, game_id).

    Inference is supplied by the sidecar runtime only after its exact live
    feature adapter has accepted the same snapshot.  The default is an
    explicit suppressed state; no clock-only or approximate fallback exists.
    """
    if not data:
        return (
            InGameSnapshot(
                inference=inference or LiveInference(),
                event_deltas=event_deltas or [],
            ),
            None,
        )
    game_data = data.get("gameData") or {}
    active_player = data.get("activePlayer") or {}
    local_summoner = active_player.get("summonerName")
    teams: dict[str, list[PlayerLive]] = {"order": [], "chaos": []}
    local_champion: str | None = None
    for raw_player in data.get("allPlayers") or []:
        built_player = _build_live_player(raw_player)
        if built_player is None:
            continue
        side, row = built_player
        if side in teams:
            teams[side].append(row)
        if local_summoner is not None and row.summoner == local_summoner:
            local_champion = row.champion
    events: list[LiveEvent] = []
    for raw_event in ((data.get("events") or {}).get("Events") or []):
        event = _build_live_event_row(raw_event)
        if event is not None:
            events.append(event)
    events = events[-MAX_EVENTS:]
    clock = game_data.get("gameTime", game_data.get("gameClock")) or 0
    raw_mode = game_data.get("gameMode")
    mode = raw_mode if isinstance(raw_mode, str) and raw_mode in _GAME_MODES else None
    game_id = game_data.get("gameId")
    return (
        InGameSnapshot(
            active=True,
            clock_s=float(clock),
            mode=mode,
            local_summoner=local_summoner,
            local_champion=local_champion or active_player.get("championName"),
            teams=teams,
            events=events,
            inference=inference or LiveInference(observed_game_time_s=float(clock)),
            event_deltas=event_deltas or [],
        ),
        int(game_id) if game_id is not None else None,
    )


async def _resolve_names(source) -> dict[int, str]:
    if source is None:
        return {}
    if isinstance(source, dict):
        return source
    result = source()
    if inspect.isawaitable(result):
        result = await result
    return result or {}


def _truncate(text: str, limit: int = 200) -> str:
    return text[:limit]


_SUPPORTED_DELTA_EVENTS = frozenset({"DragonKill", "HeraldKill", "BaronKill", "TurretKilled"})


@dataclass(frozen=True)
class _ObservedInference:
    clock_s: float
    inference: LiveInference
    vector: LiveFeatureVector | None


@dataclass(frozen=True)
class _TrackedEvent:
    key: tuple[str, float, str | None, str | None, str | None]
    event_id: str
    source_order: int
    event: LiveEvent


class _LiveEventDeltaTracker:
    """Pair one causal pre/post observation for each supported live event.

    Live Client Data returns a cumulative event list.  This tracker never sorts
    or rewrites that list: event order is the source order, while an event is
    eligible only after a later observation crosses its timestamp.  A pending
    event that is first observed after its timestamp, a duplicate, or a
    changed event order is retained only as a suppressed annotation.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._seen: dict[tuple[str, float, str | None, str | None, str | None], _TrackedEvent] = {}
        self._pending: set[tuple[str, float, str | None, str | None, str | None]] = set()
        self._ordering_violations: set[tuple[str, float, str | None, str | None, str | None]] = set()
        self._reported_order_violations: set[tuple[str, float, str | None, str | None, str | None]] = set()
        self._history: list[LiveEventDelta] = []
        self._history_index: dict[str, int] = {}
        self._last: _ObservedInference | None = None
        self._max_event_time: float | None = None

    @staticmethod
    def _key(event: LiveEvent) -> tuple[str, float, str | None, str | None, str | None]:
        return (event.name, event.t_s, event.actor, event.victim, event.detail)

    @staticmethod
    def _event_id(event: LiveEvent, source_order: int) -> str:
        return f"{source_order}:{event.name}:{event.t_s!r}"

    @staticmethod
    def _probability(observation: _ObservedInference | None) -> float | None:
        if observation is None or observation.inference.status != "available":
            return None
        probability = observation.inference.probability
        return probability if probability is not None and math.isfinite(probability) else None

    @staticmethod
    def _observed_time(observation: _ObservedInference | None) -> float | None:
        if observation is None:
            return None
        value = observation.inference.observed_game_time_s
        return value if value is not None and math.isfinite(value) else None

    @staticmethod
    def _common_version(
        previous: _ObservedInference | None,
        current: _ObservedInference,
        field: str,
    ) -> str | None:
        if previous is None:
            return None
        before = getattr(previous.inference, field)
        after = getattr(current.inference, field)
        return before if before and before == after else None

    @classmethod
    def _delta(
        cls,
        tracked: _TrackedEvent,
        previous: _ObservedInference | None,
        current: _ObservedInference,
        vector_available: bool,
        reason: str | None = None,
    ) -> LiveEventDelta:
        baseline_probability = cls._probability(previous)
        event_probability = cls._probability(current)
        pre_time = cls._observed_time(previous)
        post_time = cls._observed_time(current)
        model_version = cls._common_version(previous, current, "model_version")
        pack_version = cls._common_version(previous, current, "pack_version")
        if reason is None:
            if previous is None:
                reason = "causal pre-event observation unavailable"
            elif not vector_available or previous.vector is None or current.vector is None:
                reason = "exact pre/post live vectors unavailable"
            elif previous.inference.status != "available" or current.inference.status != "available":
                reason = "pre/post live inference unavailable"
            elif baseline_probability is None or event_probability is None:
                reason = "pre/post probabilities unavailable"
            elif model_version is None or pack_version is None:
                reason = "pre/post model provenance differs"
            elif previous.clock_s >= current.clock_s or tracked.event.t_s <= previous.clock_s:
                reason = "event does not fall between causal observations"
            elif pre_time is None or post_time is None or pre_time >= post_time:
                reason = "observation times are not strictly causal"
        if reason is None:
            assert baseline_probability is not None and event_probability is not None
            delta_probability = event_probability - baseline_probability
            return LiveEventDelta(
                event_id=tracked.event_id,
                source_order=tracked.source_order,
                name=tracked.event.name,
                t_s=tracked.event.t_s,
                baseline_probability=baseline_probability,
                event_probability=event_probability,
                delta_probability=delta_probability,
                pre_observed_game_time_s=pre_time,
                post_observed_game_time_s=post_time,
                model_version=model_version,
                pack_version=pack_version,
                suppression_status="available",
                reason=None,
            )
        inferred_status: LiveInferenceStatus = "suppressed"
        for observation in (current, previous):
            if observation is not None and observation.inference.status != "available":
                inferred_status = observation.inference.status
                break
        return LiveEventDelta(
            event_id=tracked.event_id,
            source_order=tracked.source_order,
            name=tracked.event.name,
            t_s=tracked.event.t_s,
            baseline_probability=baseline_probability,
            event_probability=event_probability,
            delta_probability=None,
            pre_observed_game_time_s=pre_time,
            post_observed_game_time_s=post_time,
            model_version=model_version,
            pack_version=pack_version,
            suppression_status=inferred_status,
            reason=reason,
        )
    def _append(self, delta: LiveEventDelta) -> None:
        existing = self._history_index.get(delta.event_id)
        if existing is not None:
            self._history[existing] = delta
            return
        self._history_index[delta.event_id] = len(self._history)
        self._history.append(delta)
        if len(self._history) > MAX_EVENTS:
            del self._history[: len(self._history) - MAX_EVENTS]
            self._history_index = {item.event_id: index for index, item in enumerate(self._history)}

    def process(
        self,
        events: list[LiveEvent],
        *,
        clock_s: float,
        inference: LiveInference,
        vector: LiveFeatureVector | None,
    ) -> list[LiveEventDelta]:
        previous = self._last
        candidates: list[tuple[_TrackedEvent, bool]] = []
        source_time: float | None = None
        source_order = 0
        for event in events:
            if event.name not in _SUPPORTED_DELTA_EVENTS:
                continue
            eligible_order = source_order
            source_order += 1
            key = self._key(event)
            if source_time is not None and event.t_s < source_time:
                self._ordering_violations.add(key)
            source_time = event.t_s
            if self._max_event_time is not None and event.t_s < self._max_event_time:
                self._ordering_violations.add(key)
            tracked = self._seen.get(key)
            if tracked is not None and tracked.source_order != eligible_order:
                self._ordering_violations.add(key)
            if self._max_event_time is None or event.t_s > self._max_event_time:
                self._max_event_time = event.t_s
            if tracked is None:
                tracked = _TrackedEvent(
                    key=key,
                    event_id=self._event_id(event, eligible_order),
                    source_order=eligible_order,
                    event=event,
                )
                self._seen[key] = tracked
                if event.t_s > clock_s:
                    self._pending.add(key)
                else:
                    candidates.append((tracked, key in self._ordering_violations))
                continue
            if key in self._pending and event.t_s <= clock_s:
                self._pending.remove(key)
                candidates.append((tracked, key in self._ordering_violations))
        current = _ObservedInference(clock_s, inference, vector)
        for key in self._ordering_violations - self._reported_order_violations:
            tracked = self._seen.get(key)
            if tracked is None or tracked.event_id not in self._history_index:
                continue
            self._append(
                self._delta(
                    tracked,
                    previous,
                    current,
                    vector_available=False,
                    reason="event source ordering changed",
                )
            )
            self._reported_order_violations.add(key)


        if candidates:
            if len(candidates) > 1:
                for tracked, _invalid in candidates:
                    self._append(
                        self._delta(
                            tracked,
                            previous,
                            _ObservedInference(clock_s, inference, vector),
                            vector_available=False,
                            reason="multiple supported events crossed between observations",
                        )
                    )
            else:
                tracked, invalid_order = candidates[0]
                current = _ObservedInference(clock_s, inference, vector)
                if invalid_order:
                    self._append(
                        self._delta(
                            tracked,
                            previous,
                            current,
                            vector_available=False,
                            reason="event source ordering changed",
                        )
                    )
                elif previous is None:
                    self._append(
                        self._delta(
                            tracked,
                            previous,
                            current,
                            vector_available=False,
                            reason="event observed without a causal pre-event snapshot",
                        )
                    )
                elif clock_s < previous.clock_s or previous.clock_s >= tracked.event.t_s:
                    self._append(
                        self._delta(
                            tracked,
                            previous,
                            current,
                            vector_available=False,
                            reason="delayed or out-of-order event observation",
                        )
                    )
                else:
                    self._append(
                        self._delta(
                            tracked,
                            previous,
                            current,
                            vector_available=vector is not None,
                        )
                    )

        current = _ObservedInference(clock_s, inference, vector)
        if previous is None or clock_s >= previous.clock_s:
            self._last = current
        return list(self._history)


class LiveService:
    """Poll loop publishing typed snapshots on change.

    Transports are injected so tests replay fixtures without a League client:
    ``LiveService(lcu, ingame, hub, poll_interval)`` where both transports
    satisfy the protocols in :mod:`bhayanak_legends.lcu`. ``champion_names``
    may be a ready ``{id: name}`` dict or a (possibly async) zero-arg callable
    returning one (production passes ChampionDirectory.get).  The optional
    feature provider prepares one exact adapter before the runtime is called.
    """

    def __init__(
        self,
        lcu,
        ingame,
        hub,
        poll_interval: float = 2.0,
        champion_names=None,
        inference=None,
        feature_provider=None,
    ) -> None:
        self._lcu = lcu
        self._ingame = ingame
        self._hub = hub
        self._interval_s = poll_interval
        self._names_source = champion_names
        self._inference = inference
        self._feature_provider = feature_provider
        self._task: asyncio.Task | None = None
        self._session_dump: dict | None = None
        self._ingame_dump: dict | None = None
        self._status_dump: dict | None = None
        self._game_id: int | None = None
        self._event_delta_tracker = _LiveEventDeltaTracker()

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._poll(), name="bl-live")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        for transport in (self._lcu, self._ingame):
            closer = getattr(transport, "aclose", None)
            if closer is not None:
                with contextlib.suppress(Exception):
                    await closer()

    def session(self) -> dict:
        return self._session_dump or ChampSelectSnapshot().model_dump()

    def ingame(self) -> dict:
        return self._ingame_dump or InGameSnapshot().model_dump()

    def status(self) -> dict:
        return self._status_dump or self._coarse_status(ChampSelectSnapshot(), InGameSnapshot(), None).model_dump()

    def _coarse_status(
        self, champ_select: ChampSelectSnapshot, ingame: InGameSnapshot, last_error: str | None
    ) -> LiveStatus:
        return LiveStatus(
            champ_select=ChampSelectStatus(active=champ_select.active, phase=champ_select.phase),
            ingame=InGameStatus(
                active=ingame.active,
                game_id=self._game_id if ingame.active else None,
                mode=ingame.mode,
                clock_s=int(ingame.clock_s),
            ),
            last_error=last_error,
        )
    async def _live_inference(
        self,
        raw_game: dict | None,
        clock_s: float,
    ) -> tuple[LiveInference, LiveFeatureVector | None]:
        def suppressed(reason: str) -> tuple[LiveInference, LiveFeatureVector | None]:
            return (
                LiveInference(status="suppressed", observed_game_time_s=clock_s, reason=reason),
                None,
            )

        if self._inference is None:
            return suppressed("live model declaration unavailable")
        predictor = getattr(self._inference, "predict_live_snapshot", None)
        if predictor is None:
            return suppressed("exact live feature adapter unavailable")
        prepared = self._feature_provider
        if prepared is None:
            return suppressed("exact live feature adapter unavailable")
        prepare = getattr(prepared, "prepare", None)
        if prepare is not None:
            capture_s = time.time()
            try:
                prepared = prepare(raw_game, observed_at_s=capture_s, now_s=capture_s)
                if inspect.isawaitable(prepared):
                    prepared = await prepared
            except Exception:
                prepared = None
            if prepared is None:
                reason = getattr(self._feature_provider, "last_reason", None) or (
                    "exact live feature adapter unavailable"
                )
                return suppressed(reason)
        if not callable(prepared):
            return suppressed("exact live feature adapter unavailable")
        try:
            vector = prepared(raw_game)
        except Exception:
            vector = None
        if (
            not isinstance(vector, LiveFeatureVector)
            or vector.contract_version != LIVE_WP_CONTRACT_VERSION
            or vector.observed_at_s < 0
            or not math.isfinite(vector.observed_at_s)
        ):
            return suppressed("live feature vector unavailable")

        # Pin the exact vector captured above for this prediction.  The
        # runtime cannot accidentally re-adapt the snapshot against a later
        # catalog or a future event row.
        def exact_provider(_snapshot) -> LiveFeatureVector:
            return vector

        try:
            result = predictor(
                raw_game,
                observed_game_time_s=clock_s,
                feature_provider=exact_provider,
            )
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict):
                result = LiveInference.model_validate(result)
            if isinstance(result, LiveInference):
                if result.observed_game_time_s is None:
                    result = result.model_copy(update={"observed_game_time_s": clock_s})
                return result, vector
        except Exception as exc:
            log.debug("live inference suppressed: %s", exc)
        return suppressed("live inference could not evaluate the exact snapshot")


    async def _publish_changed(self, event: str, current: dict, attr: str) -> bool:
        previous = getattr(self, attr)
        if current == previous:
            return False
        setattr(self, attr, current)
        await self._hub.publish(event, current)
        return True

    async def tick(self) -> None:
        last_error: str | None = None
        try:
            phase = await self._lcu.gameflow_phase()
        except Exception as exc:
            phase, last_error = None, _truncate(str(exc))

        champ_select_active = bool(phase) and phase.lower() == CHAMP_SELECT_PHASE
        in_game_window = bool(phase) and phase.lower() in IN_GAME_PHASES

        champ_select = ChampSelectSnapshot()
        if champ_select_active:
            try:
                raw_session = await self._lcu.champ_select_session()
            except Exception as exc:
                raw_session, last_error = None, last_error or _truncate(str(exc))
            names = await _resolve_names(self._names_source)
            champ_select = build_champ_select_snapshot(raw_session, phase, names)

        ingame = InGameSnapshot()
        if in_game_window:
            try:
                raw_game = await self._ingame.allgamedata()
            except Exception as exc:
                raw_game, last_error = None, last_error or _truncate(str(exc))
            clock_value = 0.0
            if isinstance(raw_game, dict):
                game_data = raw_game.get("gameData")
                if isinstance(game_data, dict):
                    try:
                        clock_value = float(game_data.get("gameTime", game_data.get("gameClock")) or 0)
                    except (TypeError, ValueError, OverflowError):
                        clock_value = 0.0
            inference, vector = await self._live_inference(raw_game, clock_value)
            ingame, game_id = build_ingame_snapshot(raw_game, inference=inference)
            if game_id != self._game_id:
                self._event_delta_tracker.reset()
            self._game_id = game_id
            event_deltas = self._event_delta_tracker.process(
                ingame.events,
                clock_s=ingame.clock_s,
                inference=ingame.inference,
                vector=vector,
            )
            ingame = ingame.model_copy(update={"event_deltas": event_deltas})
        else:
            self._game_id = None
            self._event_delta_tracker.reset()

        await self._publish_changed("champselect.state", champ_select.model_dump(), "_session_dump")
        await self._publish_changed("live.state", ingame.model_dump(), "_ingame_dump")
        coarse = self._coarse_status(champ_select, ingame, last_error)
        await self._publish_changed("live.status", coarse.model_dump(), "_status_dump")

    async def _poll(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("live poll tick failed")
            await asyncio.sleep(self._interval_s)

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
import inspect
import logging
from typing import get_args

from pydantic import BaseModel, Field

from .models import (
    CellState,
    ChampSelectStatus,
    GameMode,
    GameflowPhase,
    InGameStatus,
    LiveEventName,
    LiveState,
    LiveStatus,
)

log = logging.getLogger("bhayanak_legends.live")

CHAMP_SELECT_PHASE = "champselect"
IN_GAME_PHASES = {"gamestart", "inprogress"}
MAX_EVENTS = 40


_GAME_MODES = frozenset(get_args(GameMode))
_LIVE_EVENT_NAMES = frozenset(get_args(LiveEventName))


class CsBan(BaseModel):
    champion_id: int = 0
    name: str | None = None


class AllyCell(BaseModel):
    cell_id: int = 0
    champion_id: int = 0
    champion: str | None = None  # Data Dragon display name; None → UI shows "Champion {id}"
    name: str | None = None
    is_local: bool = False
    state: CellState = "none"


class EnemyCell(BaseModel):
    cell_id: int = 0
    champion_id: int = 0
    champion: str | None = None
    name: str | None = None  # COMPLIANCE: always null — enemy summoner names never leave this module
    state: CellState = "none"


class ChampSelectSnapshot(BaseModel):
    active: bool = False
    phase: GameflowPhase | None = None
    timer_sec: int | None = None
    bans_ally: list[CsBan] = Field(default_factory=list)
    bans_enemy: list[CsBan] = Field(default_factory=list)
    ally: list[AllyCell] = Field(default_factory=list)
    enemy: list[EnemyCell] = Field(default_factory=list)


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

def _participant_state(participant: dict) -> CellState:
    if participant.get("championId"):
        return "picked"
    if participant.get("championPickIntent"):
        return "intent"
    return "none"

def _cs_bans(raw_bans: dict | None, key: str, names: dict[int, str]) -> list[CsBan]:
    bans: list[CsBan] = []
    for entry in (raw_bans or {}).get(key) or []:
        champion_id = int(entry.get("championId") or 0)
        if not champion_id:
            continue  # pick turn not used yet
        bans.append(CsBan(champion_id=champion_id, name=names.get(champion_id)))
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
    ally: list[AllyCell] = []
    for participant in sorted(session.get("myTeam") or [], key=lambda p: p.get("cellId", 0)):
        champion_id = int(participant.get("championId") or 0)
        ally.append(
            AllyCell(
                cell_id=int(participant.get("cellId") or 0),
                champion_id=champion_id,
                champion=names.get(champion_id),
                name=participant.get("summonerName") or None,
                is_local=local_cell is not None and participant.get("cellId") == local_cell,
                state=_participant_state(participant),
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


def build_ingame_snapshot(data: dict | None) -> tuple[InGameSnapshot, int | None]:
    """Pure: /liveclientdata/allgamedata payload → (snapshot, game_id)."""
    if not data:
        return InGameSnapshot(), None
    game_data = data.get("gameData") or {}
    active_player = data.get("activePlayer") or {}
    local_summoner = active_player.get("summonerName")
    teams: dict[str, list[PlayerLive]] = {"order": [], "chaos": []}
    local_champion: str | None = None
    for player in data.get("allPlayers") or []:
        side = str(player.get("team") or "").strip().lower()  # "ORDER"/"CHAOS" → order/chaos
        scores = player.get("scores") or {}
        items = [
            ItemLive(id=int(item.get("itemID") or 0), count=int(item.get("count") or 0))
            for item in player.get("items") or []
            if item.get("itemID")
        ]
        row = PlayerLive(
            summoner=str(player.get("summonerName") or ""),
            champion=player.get("championName"),
            level=int(player.get("level") or 1),
            kills=int(scores.get("kills") or 0),
            deaths=int(scores.get("deaths") or 0),
            assists=int(scores.get("assists") or 0),
            cs=int(scores.get("creepScore") or 0),
            ward_score=float(scores.get("wardScore") or 0.0),
            items=items,
        )
        if side in teams:
            teams[side].append(row)
        if local_summoner is not None and row.summoner == local_summoner:
            local_champion = row.champion
    events = sorted(
        (
            build_live_event(raw)
            for raw in ((data.get("events") or {}).get("Events") or [])
            if isinstance(raw.get("EventName"), str)
            and raw.get("EventName") in _LIVE_EVENT_NAMES
        ),
        key=lambda e: e.t_s,
    )[-MAX_EVENTS:]
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


class LiveService:
    """Poll loop publishing typed snapshots on change.

    Transports are injected so tests replay fixtures without a League client:
    ``LiveService(lcu, ingame, hub, poll_interval)`` where both transports
    satisfy the protocols in :mod:`bhayanak_legends.lcu`. ``champion_names``
    may be a ready ``{id: name}`` dict or a (possibly async) zero-arg callable
    returning one (production passes ChampionDirectory.get).
    """

    def __init__(self, lcu, ingame, hub, poll_interval: float = 2.0, champion_names=None) -> None:
        self._lcu = lcu
        self._ingame = ingame
        self._hub = hub
        self._interval_s = poll_interval
        self._names_source = champion_names
        self._task: asyncio.Task | None = None
        self._session_dump: dict | None = None
        self._ingame_dump: dict | None = None
        self._status_dump: dict | None = None
        self._game_id: int | None = None

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
            ingame, self._game_id = build_ingame_snapshot(raw_game)
        else:
            self._game_id = None

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

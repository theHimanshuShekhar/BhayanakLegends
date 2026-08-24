"""LCU bridge: lockfile discovery, Riot local-API transports, Data Dragon names.

Transports are deliberately injectable — on this Linux dev box no League client
runs, so tests drive ``LiveService`` through fake transports replaying fixtures
from ``backend/tests/fixtures/lcu/``. The HTTP implementations below mirror the
real client shapes so first-try correctness on Windows is plausible.

Riot endpoints used (all TLS with a self-signed cert → ``verify=False``):

* LCU  (https://127.0.0.1:{port}, basic auth ``("riot", password)`` from lockfile):
  - GET /lol-gameflow/v1/gameflow-phase → bare JSON string, one of
    ``"None" | "Lobby" | "Matchmaking" | "RankedGame" | "ChampSelect" |
    "GameStart" | "InProgress" | "WaitingForStats" | "EndOfGame"``
    (older builds omit ChampSelect; treat case-insensitively).
  - GET /lol-champ-select/v1/session → champ-select session:
    ::

      {
        "timer": {"phase": "BAN_PICK|FINALIZATION|...", "adjustedTimeLeftInSec": 23},
        "localTeamCellId": 2,
        "myTeam": [
          {"cellId": 0, "championId": 25, "championPickIntent": 0,
           "summonerName": "..."}       # summonerName absent/obfuscated in ranked
        ],
        "theirTeam": [ ... same participant shape ... ],
        "bans": {
          "myTeamBans": [{"championId": 25, "pickTurn": 1}],
          "theirTeamBans": [{"championId": 412, "pickTurn": 2}]
        }
      }

    championId 0 = no champion yet; championPickIntent > 0 with championId == 0
    is a hover/intent.
  - GET /lol-summoner/v1/current-summoner → local account info.

* Live Client Data API (in-game, https://127.0.0.1:2999, no auth):
  GET /liveclientdata/allgamedata →
  ::

    {
      "gameData": {"gameId": ..., "gameMode": "CLASSIC", "gameTime": 754.32},
      "activePlayer": {"summonerName": "...", "championName": "Viktor"},
      "allPlayers": [{
        "summonerName", "championName", "team": "ORDER|CHAOS", "level",
        "scores": {"kills","deaths","assists","creepScore","wardScore"},
        "items": [{"itemID","count","slot"}]
      }],
      "events": {"Events": [{
        "EventName": "GameStart|MinionsSpawning|FirstBrick|DragonKill|HeraldKill|
                      BaronKill|ChampionKill|TurretKilled|InhibKilled|GameEnd",
        "EventTime": 612.9,
        "KillerName": "...",          # kill/turret events
        "VictimName": "...",
        "DragonType": "Infernal"      # DragonKill only
      }]}
    }

* Data Dragon (public CDN): versions.json first entry = latest version;
  ``cdn/{v}/data/en_US/champion.json`` maps numeric key → display name.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Protocol

import httpx

log = logging.getLogger("bhayanak_legends.lcu")

GAMEFLOW_PHASE_PATH = "/lol-gameflow/v1/gameflow-phase"
CHAMP_SELECT_SESSION_PATH = "/lol-champ-select/v1/session"
CURRENT_SUMMONER_PATH = "/lol-summoner/v1/current-summoner"
LIVE_CLIENT_DATA_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
DD_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DD_CHAMPIONS_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"

DAY_S = 86_400

_UNREACHABLE = (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException)


class LockfileInfo:
    __slots__ = ("port", "token", "protocol")

    def __init__(self, port: int, token: str, protocol: str) -> None:
        self.port = port
        self.token = token
        self.protocol = protocol

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, LockfileInfo)
            and (self.port, self.token, self.protocol)
            == (other.port, other.token, other.protocol)
        )

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"LockfileInfo(port={self.port}, protocol={self.protocol})"


def parse_lockfile(text: str) -> LockfileInfo:
    """Parse ``process:pid:port:password:protocol`` lockfile contents."""
    parts = text.strip().split(":")
    if len(parts) != 5:
        raise ValueError("malformed lockfile")
    process, pid, port, password, protocol = parts
    if (
        not process
        or not pid.isdigit()
        or int(pid) <= 0
        or not port.isdigit()
        or not 1 <= int(port) <= 65_535
        or not password
        or protocol not in {"http", "https"}
    ):
        raise ValueError("malformed lockfile")
    return LockfileInfo(port=int(port), token=password, protocol=protocol)


def lockfile_candidates() -> list[Path]:
    """Common Windows and WSL lockfile locations, best-guess first."""
    candidates: list[Path] = []
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        candidates.append(
            Path(localappdata) / "Riot Games" / "League of Legends" / "lockfile"
        )
    candidates.append(Path("C:/Riot Games/League of Legends/lockfile"))
    candidates.append(Path("/mnt/c/Riot Games/League of Legends/lockfile"))
    return candidates


def find_lockfile(candidates: list[Path] | None = None) -> Path | None:
    for candidate in candidates if candidates is not None else lockfile_candidates():
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


class LcuTransport(Protocol):
    async def gameflow_phase(self) -> str | None: ...

    async def champ_select_session(self) -> dict[str, Any] | None: ...

    async def current_summoner(self) -> dict[str, Any] | None: ...


class IngameTransport(Protocol):
    async def allgamedata(self) -> dict[str, Any] | None: ...


class HttpxLcuConnection:
    """Production LCU transport. Re-reads the lockfile per call and rebuilds the
    underlying client whenever port/password/protocol rotate (client restarts mid-session)."""

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._key: tuple[int, str, str] | None = None

    def _ensure_client(self) -> bool:
        path = find_lockfile()
        if path is None:
            return False
        try:
            info = parse_lockfile(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        key = (info.port, info.token, info.protocol)
        if self._client is not None and key != self._key:
            self._drop()
        if self._client is None:
            self._key = key
            self._client = httpx.AsyncClient(
                base_url=f"{info.protocol}://127.0.0.1:{info.port}",
                auth=("riot", info.token),
                verify=False,
                timeout=httpx.Timeout(2.0),
            )
        return True

    def _drop(self) -> None:
        if self._client is not None:
            self._client = None
            self._key = None

    async def _get_json(self, path: str) -> dict[str, Any] | None:
        if not self._ensure_client():
            return None
        assert self._client is not None
        try:
            response = await self._client.get(path)
        except _UNREACHABLE:
            self._drop()
            return None
        response.raise_for_status()
        return response.json()

    async def gameflow_phase(self) -> str | None:
        if not self._ensure_client():
            return None
        assert self._client is not None
        try:
            response = await self._client.get(GAMEFLOW_PHASE_PATH)
        except _UNREACHABLE:
            self._drop()
            return None
        response.raise_for_status()
        try:
            phase = response.json()
        except ValueError:
            phase = response.text.strip().strip('"')
        return str(phase).strip().strip('"') or None

    async def champ_select_session(self) -> dict[str, Any] | None:
        return await self._get_json(CHAMP_SELECT_SESSION_PATH)

    async def current_summoner(self) -> dict[str, Any] | None:
        return await self._get_json(CURRENT_SUMMONER_PATH)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._drop()


class HttpxIngameTransport:
    """Live Client Data API on 127.0.0.1:2999; unreachable while out of game."""

    def __init__(self, url: str = LIVE_CLIENT_DATA_URL) -> None:
        self._url = url
        self._client = httpx.AsyncClient(verify=False, timeout=httpx.Timeout(2.0))

    async def allgamedata(self) -> dict[str, Any] | None:
        try:
            response = await self._client.get(self._url)
        except _UNREACHABLE:
            return None
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()


def champion_map_from_ddragon(payload: dict[str, Any]) -> dict[int, str]:
    """Pure: champion.json payload → {numeric key: display name}."""
    mapping: dict[int, str] = {}
    for entry in (payload.get("data") or {}).values():
        try:
            mapping[int(entry["key"])] = str(entry["name"])
        except (KeyError, TypeError, ValueError):
            continue
    return mapping


async def _fetch_versions_default() -> list[str]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        response = await client.get(DD_VERSIONS_URL)
        response.raise_for_status()
        return response.json()


async def _fetch_champions_default(version: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        response = await client.get(DD_CHAMPIONS_URL.format(version=version))
        response.raise_for_status()
        return response.json()


class ChampionDirectory:
    """Champion id→name map: memory cache, disk cache under data_dir/ddragon.json
    refreshed daily; every failure degrades to an empty map (UI shows
    "Champion {id}") or the stale disk copy."""

    def __init__(
        self,
        data_dir: Path | None = None,
        *,
        fetch_versions=None,
        fetch_champions=None,
        clock=time.time,
    ) -> None:
        self._data_dir = data_dir
        self._fetch_versions = fetch_versions or _fetch_versions_default
        self._fetch_champions = fetch_champions or _fetch_champions_default
        self._clock = clock
        self._memory: dict[int, str] | None = None

    @property
    def disk_path(self) -> Path | None:
        return self._data_dir / "ddragon.json" if self._data_dir else None

    def _read_disk(self) -> tuple[float, dict[int, str]] | None:
        path = self.disk_path
        if path is None:
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            fetched_at = float(record["fetched_at"])
            champions = {int(k): str(v) for k, v in record["champions"].items()}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
        return fetched_at, champions

    def _write_disk(self, champions: dict[int, str]) -> None:
        path = self.disk_path
        if path is None or not champions:
            return
        record = {"fetched_at": self._clock(), "champions": {str(k): v for k, v in champions.items()}}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record), encoding="utf-8")
        except OSError:
            log.warning("ddragon disk cache write failed at %s", path)

    async def get(self) -> dict[int, str]:
        if self._memory is not None:
            return self._memory
        disk = self._read_disk()
        if disk is not None and self._clock() - disk[0] < DAY_S:
            self._memory = disk[1]
            return self._memory
        try:
            versions = await self._fetch_versions()
            version = versions[0]
            payload = await self._fetch_champions(version)
            champions = champion_map_from_ddragon(payload)
        except Exception as exc:
            log.warning("ddragon fetch failed (%s); using fallback map", exc)
            champions = disk[1] if disk is not None else {}
        self._write_disk(champions)
        self._memory = champions
        return self._memory

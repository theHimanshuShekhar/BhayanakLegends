"""Live Companion detection: LCU gameflow phase + Live Client Data polling.

On platforms without a running League client (e.g. Linux dev) every probe
fails to connect and the service reports an idle LiveStatus with
``last_error`` left None; expected absences are not errors.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from pathlib import Path

import httpx

from .models import LiveState, LiveStatus

log = logging.getLogger("bhayanak_legends.live")

LIVE_CLIENT_DATA_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
GAMEFLOW_PHASE_PATH = "/lol-gameflow/v1/gameflow-phase"
CHAMP_SELECT_PHASE = "champselect"


def lockfile_candidates() -> list[Path]:
    """Common Windows and WSL lockfile locations, best-guess first."""
    candidates: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "Riot Games" / "League of Legends" / "lockfile")
    candidates.append(Path("C:/Riot Games/League of Legends/lockfile"))
    candidates.extend(
        sorted(Path("/mnt").glob("*/Users/*/AppData/Local/Riot Games/League of Legends/lockfile"))
    )
    return candidates


def _truncate(text: str, limit: int = 200) -> str:
    return text[:limit]


class LiveService:
    """Polls local Riot endpoints on an interval and publishes state changes."""

    def __init__(self, hub, interval_s: float = 3.0) -> None:
        self._hub = hub
        self._interval_s = interval_s
        self._task: asyncio.Task | None = None
        self._client: httpx.AsyncClient | None = None
        self._last: dict | None = None

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._client = httpx.AsyncClient(verify=False, timeout=httpx.Timeout(2.0))
        self._task = asyncio.create_task(self._poll(), name="bl-live")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def status(self) -> dict:
        if self._last is not None:
            return self._last
        return LiveStatus(champ_select=LiveState(), ingame=LiveState()).model_dump()

    async def _poll(self) -> None:
        assert self._client is not None
        while True:
            status = await detect_once(self._client)
            if status != self._last:
                self._last = status
                await self._hub.publish("live.state", status)
            await asyncio.sleep(self._interval_s)


async def detect_once(client: httpx.AsyncClient) -> dict:
    """Run one detection pass and return the LiveStatus dict."""
    champ_select = LiveState()
    ingame = LiveState()
    last_error: str | None = None

    lockfile = _find_lockfile()
    if lockfile is not None:
        try:
            phase = await _lcu_phase(client, lockfile)
            active = bool(phase) and phase.lower() == CHAMP_SELECT_PHASE
            champ_select = LiveState(active=active, phase=phase)
        except Exception as exc:
            last_error = _truncate(str(exc))

    try:
        response = await client.get(LIVE_CLIENT_DATA_URL, timeout=1.0)
        payload = response.json().get("gameData", {})
        ingame = LiveState(
            active=True,
            game_id=payload.get("gameId"),
            mode=payload.get("gameMode"),
            clock_s=int(payload.get("gameClock") or 0),
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        pass
    except Exception as exc:
        if last_error is None:
            last_error = _truncate(str(exc))

    return LiveStatus(champ_select=champ_select, ingame=ingame, last_error=last_error).model_dump()


def _find_lockfile() -> Path | None:
    for candidate in lockfile_candidates():
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


async def _lcu_phase(client: httpx.AsyncClient, lockfile: Path) -> str | None:
    parts = lockfile.read_text(encoding="utf-8").strip().split(":")
    if len(parts) < 4:
        raise ValueError(f"malformed lockfile at {lockfile}")
    _name, port, token, _protocol = parts[:4]
    url = f"https://127.0.0.1:{port}{GAMEFLOW_PHASE_PATH}"
    response = await client.get(url, auth=("riot", token))
    response.raise_for_status()
    try:
        return str(response.json())
    except ValueError:
        return response.text.strip().strip('"') or None

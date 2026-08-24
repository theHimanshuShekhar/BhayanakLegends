"""Riot API client for match-v5/account-v5 over a regional route.

Temporary standalone mirror of loltrends' ``RiotSeedingClient`` semantics
(dual-window rate limiting, 429 Retry-After backoff, NotFound handling);
see docs/adr/0001-reuse-loltrends-as-extraction-library.md. This module
exists only until loltrends publishes an importable wheel that does not
drag streamlit/pandas into the sidecar; replace it wholesale then.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote

import httpx

USER_AGENT = "BhayanakLegends/0.1"

MAX_REQUESTS_PER_120S = 90
RATE_LIMIT_MIN_INTERVAL_S = 0.06

REGION_HOSTS: dict[str, str] = {
    "sea": "sea.api.riotgames.com",
    "americas": "americas.api.riotgames.com",
    "europe": "europe.api.riotgames.com",
    "asia": "asia.api.riotgames.com",
}

MATCH_IDS_PATH = "/lol/match/v5/matches/by-puuid/{puuid}/ids"
MATCH_PATH = "/lol/match/v5/matches/{match_id}"
TIMELINE_PATH = "/lol/match/v5/matches/{match_id}/timeline"
ACCOUNT_BY_RIOT_ID_PATH = "/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"


class RiotError(RuntimeError):
    pass


class RiotNotFound(RiotError):
    """HTTP 404 from a Riot endpoint (e.g. missing timeline)."""


class RiotForbidden(RiotError):
    """HTTP 403 from a Riot endpoint (bad key or WAF block)."""


class RiotRateLimited(RiotError):
    """HTTP 429 persisting past the retry budget."""

    def __init__(self, retry_after_s: float | None = None) -> None:
        super().__init__(f"rate limited (retry-after={retry_after_s})")
        self.retry_after_s = retry_after_s


class RateLimiter:
    """Rolling-window pacer: max 90 requests/120s plus 60ms spacing.

    :meth:`acquire` returns the seconds the caller must wait before sending
    and records a slot at the intended send time; pure w.r.t. the injected
    clock so tests can assert timing without sleeping.
    """

    def __init__(
        self,
        *,
        max_per_120s: int = MAX_REQUESTS_PER_120S,
        min_interval_s: float = RATE_LIMIT_MIN_INTERVAL_S,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_per_120s = max_per_120s
        self.min_interval_s = min_interval_s
        self.monotonic = monotonic
        self._window: deque[float] = deque()
        self._last: float | None = None

    def acquire(self) -> float:
        now = self.monotonic()
        while self._window and self._window[0] <= now - 120.0:
            self._window.popleft()
        wait = 0.0
        if self._last is not None:
            wait = max(wait, self._last + self.min_interval_s - now)
        if len(self._window) >= self.max_per_120s:
            wait = max(wait, self._window[0] + 120.0 - now)
        stamp = now + wait
        self._window.append(stamp)
        self._last = stamp
        return wait


class RiotClient:
    """Async match-v5/account-v5 client bound to one regional route."""

    def __init__(
        self,
        api_key: str,
        region_route: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        max_retries: int = 3,
    ) -> None:
        host = REGION_HOSTS.get(region_route)
        if host is None:
            raise ValueError(f"unknown region route {region_route!r}; expected one of {sorted(REGION_HOSTS)}")
        self._client = http_client or httpx.AsyncClient(
            base_url=f"https://{host}",
            headers={"X-Riot-Token": api_key, "User-Agent": USER_AGENT},
            timeout=30.0,
        )
        self._sleep = sleep or asyncio.sleep
        self._limiter = RateLimiter(monotonic=monotonic)
        self.max_retries = max_retries

    async def account_by_riot_id(self, riot_id: str) -> dict[str, Any]:
        """Resolve ``GameName#TAG`` to the account-v5 payload (puuid inside)."""
        game_name, sep, tag_line = riot_id.partition("#")
        if not sep or not game_name or not tag_line:
            raise ValueError(f"riot_id must be 'GameName#TAG', got {riot_id!r}")
        path = ACCOUNT_BY_RIOT_ID_PATH.format(
            game_name=quote(game_name, safe=""), tag_line=quote(tag_line, safe="")
        )
        return await self._get_json(path)

    async def match_ids(self, puuid: str, total: int, page_size: int = 100) -> list[str]:
        """Walk by-puuid match history newest-first with start/count pagination."""
        collected: list[str] = []
        while len(collected) < total:
            start = len(collected)
            count = min(page_size, total - start)
            page = await self._get_json(
                MATCH_IDS_PATH.format(puuid=puuid),
                params={"start": start, "count": count},
            )
            if not page:
                break
            collected.extend(str(match_id) for match_id in page)
            if len(page) < count:
                break
        return collected[:total]

    async def match(self, match_id: str) -> dict[str, Any]:
        return await self._get_json(MATCH_PATH.format(match_id=match_id))

    async def timeline(self, match_id: str) -> dict[str, Any]:
        return await self._get_json(TIMELINE_PATH.format(match_id=match_id))

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        last_rate_limit: RiotRateLimited | None = None
        for attempt in range(self.max_retries + 1):
            wait = self._limiter.acquire()
            if wait > 0:
                await self._sleep(wait)
            response = await self._client.get(path, params=params)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429:
                raw = response.headers.get("Retry-After")
                retry_after = float(raw) if raw else 2.0**attempt
                last_rate_limit = RiotRateLimited(retry_after)
                await self._sleep(retry_after)
                continue
            if response.status_code == 404:
                raise RiotNotFound(f"404 for {path}")
            if response.status_code == 403:
                raise RiotForbidden(f"403 for {path}")
            response.raise_for_status()
        raise last_rate_limit if last_rate_limit else RiotError("retry budget exhausted")

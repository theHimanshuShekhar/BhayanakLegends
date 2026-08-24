"""Backfill sync service: era-first Riot download and local-folder import.

Both modes drain the same resumable ``sync_queue`` (newest matches first via
priority = enqueue index) through the same extractor, publishing
``sync.progress``/``sync.done`` SSE envelopes from worker threads onto the
asyncio loop captured at wiring time.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from .extract import parse_checkpoints, parse_match

try:
    from .riot_client import RiotClient, RiotNotFound
except ImportError:  # pragma: no cover - optional dep guard

    class RiotClient:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("riot_client unavailable")

    class RiotNotFound(Exception):  # type: ignore[no-redef]
        pass

log = logging.getLogger("bhayanak_legends.sync")

BACKFILL_TOTAL = 1000


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class SyncService:
    """Runs Personal History backfill on a daemon thread; status per contract."""

    def __init__(
        self,
        store,
        hub,
        get_settings_fn: Callable[[], dict[str, Any]],
        *,
        client_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.store = store
        self.hub = hub
        self._get_settings = get_settings_fn
        self._client_factory = client_factory or self._default_client_factory
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._status: dict[str, Any] = {
            "state": "idle",
            "mode": "era_first",
            "total_queued": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "current_match_id": None,
            "started_at": None,
        }

    @staticmethod
    def _default_client_factory(api_key: str, region_route: str) -> Any:
        return RiotClient(api_key, region_route)

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the app's asyncio loop so worker threads can publish SSE."""
        self._loop = loop

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def cancel(self) -> dict[str, Any]:
        self._cancel.set()
        with self._lock:
            if self._status["state"] == "running":
                self._status["state"] = "cancelled"
                self._status["current_match_id"] = None
        return self.status()

    def shutdown(self, timeout: float = 2.0) -> None:
        self.cancel()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)

    def start(self) -> dict[str, Any]:
        """Kick the era-first Backfill (no-op when already running)."""
        if self._thread is not None and self._thread.is_alive():
            return self.status()
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        settings = self._get_settings()
        if not settings.get("riot_key"):
            with self._lock:
                self._status.update(state="error", mode="era_first", started_at=None)
            self._publish("sync.done")
            return self.status()
        self._begin_run("era_first")
        self.store.reset_running_items()
        self._thread = threading.Thread(
            target=self._run_riot, args=(settings,), name="bl-sync", daemon=True
        )
        self._thread.start()
        return self.status()

    def import_from_dir(
        self, dir: Path, loop: asyncio.AbstractEventLoop | None = None
    ) -> dict[str, Any]:
        """Enqueue a LoLTrends-layout folder and ingest it locally (no API key).

        Reads ``fetch_state.json`` for the puuid, enqueues every match detail
        JSON (newest first) tagged ``mode:"import"``, then drains the queue to
        completion in the calling thread. Blocking.
        """
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        if loop is not None:
            self.attach_loop(loop)
        fetch_state_path = Path(dir) / "fetch_state.json"
        state = json.loads(fetch_state_path.read_text(encoding="utf-8"))
        puuid = str(state["puuid"])
        self.store.set_setting("sync_mode", "import")
        self.store.set_setting("import_dir", str(dir))
        self.store.set_setting("puuid", puuid)

        detail_paths = [
            p
            for p in sorted(Path(dir).glob("*.json"), reverse=True)
            if not p.name.endswith("_timeline.json") and p.name != "fetch_state.json"
        ]
        self.store.reset_running_items()
        self._begin_run("import")
        added = 0
        for priority, path in enumerate(detail_paths):
            added += self.store.enqueue([path.stem], priority=priority)
        with self._lock:
            self._status["total_queued"] = added
        log.info("import queued %d matches from %s", added, dir)
        asyncio.run(self._process(self._file_fetcher(Path(dir)), puuid))
        return self.status()

    # -- internals ------------------------------------------------------

    def _begin_run(self, mode: str) -> None:
        self._cancel.clear()
        with self._lock:
            self._status.update(
                state="running",
                mode=mode,
                total_queued=0,
                downloaded=0,
                skipped=0,
                failed=0,
                current_match_id=None,
                started_at=_now_iso(),
            )
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

    def _run_riot(self, settings: dict[str, Any]) -> None:
        try:
            asyncio.run(self._riot_flow(settings))
        except Exception:
            log.exception("era-first backfill crashed")
            with self._lock:
                self._status.update(state="error", current_match_id=None)
            self._publish("sync.done")

    async def _riot_flow(self, settings: dict[str, Any]) -> None:
        client = self._client_factory(str(settings["riot_key"]), str(settings.get("region_route") or "sea"))
        try:
            puuid = self.store.get_setting("puuid")
            if not puuid:
                riot_id = settings.get("riot_id")
                account = await client.account_by_riot_id(str(riot_id))
                puuid = str(account["puuid"])
                self.store.set_setting("puuid", puuid)
            ids = await client.match_ids(str(puuid), BACKFILL_TOTAL)
            added = 0
            for priority, match_id in enumerate(ids):
                added += self.store.enqueue([match_id], priority=priority)
            with self._lock:
                self._status["total_queued"] = added
            self._publish("sync.progress")
            await self._process(self._http_fetcher(client), str(puuid))
        finally:
            await client.aclose()

    async def _process(self, fetch_pair: Callable[[str], Awaitable[tuple[Any, Any]]], puuid: str) -> None:
        while not self._cancel.is_set():
            item = self.store.next_pending()
            if item is None:
                break
            match_id = str(item["match_id"])
            with self._lock:
                self._status["current_match_id"] = match_id
            try:
                detail, timeline = await fetch_pair(match_id)
                parsed = parse_match(detail, puuid)
                checkpoints = parse_checkpoints(timeline, puuid)
                self.store.upsert_match(
                    parsed["match_id"],
                    parsed["played_at"],
                    parsed["patch"],
                    parsed["role"],
                    parsed["champion"],
                    parsed["win"],
                    parsed["duration_s"],
                    json.dumps(checkpoints),
                )
                self.store.mark_queue_item(match_id, "done")
                self._bump("downloaded")
            except (FileNotFoundError, RiotNotFound):
                self.store.mark_queue_item(match_id, "done")
                self._bump("skipped")
            except Exception:
                log.exception("failed processing %s", match_id)
                self.store.mark_queue_item(match_id, "failed", bump_attempts=True)
                self._bump("failed")
            self._publish("sync.progress")
        with self._lock:
            self._status.update(
                state="cancelled" if self._cancel.is_set() else "idle",
                current_match_id=None,
            )
        self._publish("sync.done")

    def _http_fetcher(self, client: Any) -> Callable[[str], Awaitable[tuple[Any, Any]]]:
        async def fetch(match_id: str) -> tuple[Any, Any]:
            detail = await client.match(match_id)
            try:
                timeline = await client.timeline(match_id)
            except Exception:
                log.warning("timeline unavailable for %s", match_id)
                timeline = None
            return detail, timeline

        return fetch

    @staticmethod
    def _file_fetcher(dir: Path) -> Callable[[str], Awaitable[tuple[Any, Any]]]:
        async def fetch(match_id: str) -> tuple[Any, Any]:
            detail = json.loads((dir / f"{match_id}.json").read_text(encoding="utf-8"))
            timeline_path = dir / f"{match_id}_timeline.json"
            timeline = (
                json.loads(timeline_path.read_text(encoding="utf-8"))
                if timeline_path.exists()
                else None
            )
            return detail, timeline

        return fetch

    def _bump(self, counter: str) -> None:
        with self._lock:
            self._status[counter] += 1

    def _publish(self, type_: str) -> None:
        status = self.status()
        loop = self._loop
        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.hub.publish(type_, status), loop)

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
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

from .extract import parse_checkpoints, parse_match
from .import_paths import canonical_import_directory

try:
    from .riot_client import (
        RiotClient,
        RiotForbidden,
        RiotNotFound,
        RiotRateLimited,
        RiotRecoverableError,
    )
except ImportError:  # pragma: no cover - optional dep guard

    class RiotClient:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("riot_client unavailable")

    class RiotForbidden(Exception):  # type: ignore[no-redef]
        pass

    class RiotNotFound(Exception):  # type: ignore[no-redef]
        pass

    class RiotRateLimited(Exception):  # type: ignore[no-redef]
        pass

    class RiotRecoverableError(Exception):  # type: ignore[no-redef]
        pass

log = logging.getLogger("bhayanak_legends.sync")


class _Cancelled(Exception):
    """Internal: cancellation observed between an await and its mutations."""

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
        import_roots: Iterable[Path] = (),
        client_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.store = store
        self.hub = hub
        self._get_settings = get_settings_fn
        self._import_roots = tuple(Path(root) for root in import_roots)
        self._client_factory = client_factory or self._default_client_factory
        self._cancel = threading.Event()
        self._run_generation = 0
        self._finalized_generation = -1
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
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
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            if self._loop is None:
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass
            settings = self._get_settings()
            if not settings.get("riot_key"):
                generation = self._begin_run("era_first")
                self._finalize_run(generation, "error")
                return self.status()
            generation = self._begin_run("era_first")
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
        canonical_dir = canonical_import_directory(dir, self._import_roots)
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        if loop is not None:
            self.attach_loop(loop)
        fetch_state_path = canonical_dir / "fetch_state.json"
        state = json.loads(fetch_state_path.read_text(encoding="utf-8"))
        puuid = str(state["puuid"])
        if self._cancel.is_set():
            return self.status()
        self.store.set_setting("sync_mode", "import")
        self.store.set_setting("import_dir", str(canonical_dir))
        self.store.set_setting("puuid", puuid)

        detail_paths = [
            p
            for p in sorted(canonical_dir.glob("*.json"), reverse=True)
            if not p.name.endswith("_timeline.json") and p.name != "fetch_state.json"
        ]
        self.store.reset_running_items()
        generation = self._begin_run("import")
        added = 0
        try:
            for priority, path in enumerate(detail_paths):
                if self._cancel.is_set():
                    raise _Cancelled()
                added += self.store.enqueue([path.stem], priority=priority)
            with self._lock:
                self._status["total_queued"] = added
            log.info("import queued %d matches from %s", added, canonical_dir)
            asyncio.run(self._process(self._file_fetcher(canonical_dir), puuid))
        except _Cancelled:
            log.warning("import cancelled mid-enqueue; enqueued rows remain resumable")
            self._finalize_run(generation, "cancelled")
        return self.status()

    # -- internals ------------------------------------------------------

    def _begin_run(self, mode: str) -> int:
        with self._lock:
            self._run_generation += 1
            generation = self._run_generation
        self._cancel.clear()
        self._finalized_generation = generation - 1
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
        return generation

    def _finalize_run(self, generation: int, state: str) -> None:
        """Single idempotent run exit: one status, one terminal event."""
        with self._lock:
            if generation <= self._finalized_generation:
                return
            self._finalized_generation = generation
            self._status.update(state=state, current_match_id=None)
        self._publish("sync.done")

    def _run_riot(self, settings: dict[str, Any]) -> None:
        generation = self._run_generation
        try:
            asyncio.run(self._riot_flow(settings))
        except _Cancelled:
            log.warning("backfill cancelled; uncommitted work restored to pending")
            self._finalize_run(generation, "cancelled")
        except Exception:
            log.exception("era-first backfill crashed")
            self._finalize_run(generation, "error")
        else:
            self._finalize_run(generation, "idle")

    async def _riot_flow(self, settings: dict[str, Any]) -> None:
        region_route = str(settings.get("region_route") or "sea")
        riot_id = str(settings.get("riot_id") or "").strip()
        client = self._client_factory(str(settings["riot_key"]), region_route)
        try:
            puuid = self.store.get_setting("puuid")
            cached_identity = self.store.get_setting("puuid_identity")
            cached_region = self.store.get_setting("puuid_region")
            if puuid and (cached_identity != riot_id or cached_region != region_route):
                if self._cancel.is_set():
                    raise _Cancelled()
                self.store.delete_raw_setting("puuid")
                puuid = None
            if not puuid:
                account = await client.account_by_riot_id(riot_id)
                if self._cancel.is_set():
                    raise _Cancelled()
                puuid = str(account["puuid"])
                self.store.set_setting("puuid", puuid)
                self.store.set_setting("puuid_identity", riot_id)
                self.store.set_setting("puuid_region", region_route)
            ids = await client.match_ids(str(puuid), BACKFILL_TOTAL)
            if self._cancel.is_set():
                raise _Cancelled()
            for priority, match_id in enumerate(ids):
                if self._cancel.is_set():
                    raise _Cancelled()
                self.store.enqueue([match_id], priority=priority)
            with self._lock:
                self._status["total_queued"] = self.store.queue_stats()["pending"]
            self._publish("sync.progress")
            await self._process(self._http_fetcher(client), str(puuid))
        finally:
            await client.aclose()

    async def _process(
        self, fetch_pair: Callable[[str], Awaitable[tuple[Any, Any]]], puuid: str
    ) -> None:
        # Process each item that was pending at run start at most once. A
        # recoverable item is returned to pending, but must wait for a later
        # session rather than being retried indefinitely in this one.
        remaining = self.store.queue_stats()["pending"]
        recoverable_failure = False
        deferred: set[str] = set()
        while not self._cancel.is_set() and remaining:
            item = self.store.claim_next_pending(deferred)
            if item is None:
                break
            remaining -= 1
            match_id = str(item["match_id"])
            with self._lock:
                self._status["current_match_id"] = match_id
            try:
                detail, timeline = await fetch_pair(match_id)
                if self._cancel.is_set():
                    # Cancelled during the fetch: undo nothing, commit nothing.
                    # The claim returns to pending with its attempt count kept,
                    # so a later session can finish it.
                    self.store.recover_queue_item(match_id, bump_attempts=False)
                    break
                parsed = parse_match(detail, puuid)
                checkpoints = parse_checkpoints(timeline, puuid)
                completed = self.store.complete_match(
                    parsed["match_id"],
                    parsed["played_at"],
                    parsed["patch"],
                    parsed["role"],
                    parsed["champion"],
                    parsed["win"],
                    parsed["duration_s"],
                    json.dumps(checkpoints),
                )
                if completed:
                    self._bump("downloaded")
            except (FileNotFoundError, RiotNotFound):
                self.store.fail_queue_item(match_id)
                self._bump("skipped")
            except (RiotRecoverableError, RiotRateLimited):
                log.warning("recoverable failure processing %s", match_id)
                self.store.recover_queue_item(match_id)
                deferred.add(match_id)
                recoverable_failure = True
                self._bump("failed")
            except RiotForbidden:
                log.warning("forbidden input while processing %s", match_id)
                self.store.fail_queue_item(match_id)
                self._bump("failed")
            except Exception:
                log.exception("failed processing %s", match_id)
                self.store.fail_queue_item(match_id)
                self._bump("failed")
            finally:
                with self._lock:
                    self._status["current_match_id"] = None
            self._publish("sync.progress")
        state = "cancelled" if self._cancel.is_set() else "idle"
        if recoverable_failure and state != "cancelled":
            state = "error"
        self._finalize_run(self._run_generation, state)

    def _http_fetcher(self, client: Any) -> Callable[[str], Awaitable[tuple[Any, Any]]]:
        async def fetch(match_id: str) -> tuple[Any, Any]:
            detail = await client.match(match_id)
            timeline = await client.timeline(match_id)
            return detail, timeline

        return fetch

    @staticmethod
    def _file_fetcher(dir: Path) -> Callable[[str], Awaitable[tuple[Any, Any]]]:
        async def fetch(match_id: str) -> tuple[Any, Any]:
            detail = json.loads((dir / f"{match_id}.json").read_text(encoding="utf-8"))
            timeline = json.loads(
                (dir / f"{match_id}_timeline.json").read_text(encoding="utf-8")
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

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

from .extract import parse_match
from .extract_v2 import PARITY_V2_VERSION, V2_FEATURE_ORDER, parse_personal_history_v2
from .import_paths import canonical_import_directory
from .store import StaleOwnerGeneration

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

# Account-v1 lookup is route-sensitive: sea.api.riotgames.com rejects valid
# keys/IDs with 403 while the same identity resolves on asia. Match-v5
# discovery must stay on the user-selected route (SEA holds SEA matches),
# so account resolution tries the selected route first then falls back.
ACCOUNT_FALLBACK_ORDER = ("asia", "americas", "europe", "sea")


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
        self._resolution_lock = threading.Lock()
        self._resolution_generations: set[int] = set()
        self._resolution_threads: set[threading.Thread] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._run_owner_key: str | None = None
        self._run_owner_generation = self.store.capture_owner_scope()["generation"]
        self._run_owner_state = self.store.capture_owner_scope()["owner_state"]
        self._run_puuid: str | None = None
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

    @staticmethod
    def _account_route_order(selected: str) -> list[str]:
        order = [selected] if selected else []
        for route in ACCOUNT_FALLBACK_ORDER:
            if route not in order:
                order.append(route)
        return order

    async def _account_by_riot_id_with_fallback(
        self, api_key: str, riot_id: str, region_route: str
    ) -> dict[str, Any]:
        """Resolve Riot ID, falling back across regional routes.

        Only RiotForbidden/RiotNotFound trigger fallback: a 404 proves the
        key was accepted, so a later 404 means the ID is the problem.
        Rate-limit/transport errors propagate without fan-out.
        """
        last_forbidden: Exception | None = None
        seen_not_found: Exception | None = None
        for route in self._account_route_order(region_route):
            client: Any | None = None
            try:
                client = self._client_factory(api_key, route)
                result = await client.account_by_riot_id(riot_id)
                if route != region_route:
                    log.info("Riot account resolved via fallback route %s", route)
                return result
            except RiotNotFound as exc:
                seen_not_found = exc
                continue
            except RiotForbidden as exc:
                last_forbidden = exc
                continue
            finally:
                if client is not None:
                    try:
                        await client.aclose()
                    except Exception:
                        log.warning("Riot account resolver client close failed")
        if seen_not_found is not None:
            raise seen_not_found
        if last_forbidden is not None:
            raise last_forbidden
        raise RiotNotFound("Riot resource was not found")

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the app's asyncio loop so worker threads can publish SSE."""
        self._loop = loop

    def resolve_owner(self, generation: int) -> None:
        """Resolve the current settings owner without starting Backfill."""
        generation = int(generation)
        scope = self.store.capture_owner_scope()
        if (
            int(scope["generation"]) != generation
            or scope["owner_state"] != "resolving"
        ):
            return
        thread = threading.Thread(
            target=self._run_owner_resolution,
            args=(generation,),
            name="bl-owner-resolution",
            daemon=True,
        )
        with self._resolution_lock:
            if generation in self._resolution_generations:
                return
            self._resolution_generations.add(generation)
            self._resolution_threads.add(thread)
        try:
            thread.start()
        except Exception:
            with self._resolution_lock:
                self._resolution_generations.discard(generation)
                self._resolution_threads.discard(thread)
            raise

    @staticmethod
    def _scope_fields(scope: dict[str, Any]) -> dict[str, Any]:
        return {
            "owner_key": scope.get("owner_key"),
            "generation": int(scope.get("generation") or 0),
            "owner_state": scope.get("owner_state") or "unassigned",
            "owner_error": scope.get("owner_error"),
        }

    @staticmethod
    def _empty_status(scope: dict[str, Any]) -> dict[str, Any]:
        return {
            "state": "idle",
            "mode": "era_first",
            "total_queued": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "current_match_id": None,
            "started_at": None,
            **SyncService._scope_fields(scope),
        }

    def _run_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self._status,
                "owner_key": self._run_owner_key,
                "generation": self._run_owner_generation,
                "owner_state": self._run_owner_state,
                "owner_error": None,
            }

    def status(self) -> dict[str, Any]:
        """Return status for the currently active owner generation only."""
        scope = self.store.capture_owner_scope()
        with self._lock:
            same_generation = (
                self._run_owner_generation == int(scope["generation"])
                and self._run_owner_key == scope["owner_key"]
            )
            if not same_generation:
                return self._empty_status(scope)
            current = dict(self._status)
        return {**current, **self._scope_fields(scope)}

    def cancel(self, *, wait: bool = False) -> dict[str, Any]:
        """Request cancellation; terminal state is published by the worker."""
        self._cancel.set()
        if wait:
            self.quiesce()
        return self.status()

    def quiesce(self, timeout: float = 5.0) -> bool:
        """Cancel and wait for the current worker before an owner transition."""
        self._cancel.set()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout)
        if thread is None or not thread.is_alive():
            with self._lock:
                owner_key = self._run_owner_key
            if owner_key:
                self.store.reset_running_items(owner_key)
            return True
        return False

    def shutdown(self, timeout: float = 2.0) -> None:
        self.cancel(wait=True)
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)
        with self._resolution_lock:
            resolution_threads = tuple(self._resolution_threads)
        for thread in resolution_threads:
            if thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout)

    def _run_owner_resolution(self, generation: int) -> None:
        thread = threading.current_thread()
        try:
            asyncio.run(self._resolve_owner(generation))
        except StaleOwnerGeneration:
            return
        except RiotNotFound:
            self.store.set_owner_error(generation, "Riot ID could not be resolved")
        except RiotForbidden:
            self.store.set_owner_error(generation, "Riot API key was rejected")
        except (RiotRecoverableError, RiotRateLimited):
            self.store.set_owner_error(
                generation, "Riot identity is temporarily unavailable"
            )
        except ValueError as exc:
            if "API key" in str(exc):
                self.store.set_owner_error(generation, "Riot API key required")
            else:
                log.warning("Riot account resolution failed")
                self.store.set_owner_error(generation, "Riot identity is unavailable")
        except Exception:
            log.warning("Riot account resolution failed")
            self.store.set_owner_error(generation, "Riot identity is unavailable")
        finally:
            with self._resolution_lock:
                self._resolution_generations.discard(generation)
                self._resolution_threads.discard(thread)

    async def _resolve_owner(self, generation: int) -> None:
        settings = self._get_settings()
        scope = self.store.capture_owner_scope()
        if (
            int(scope["generation"]) != generation
            or scope["owner_state"] != "resolving"
        ):
            raise StaleOwnerGeneration("identity transition superseded")
        riot_id = str(settings.get("riot_id") or "").strip()
        riot_key = settings.get("riot_key")
        if not riot_id or not isinstance(riot_key, str) or not riot_key.strip():
            raise ValueError("Riot identity requires a Riot ID and API key")
        region_route = str(settings.get("region_route") or "sea")
        account = await self._account_by_riot_id_with_fallback(
            riot_key, riot_id, region_route
        )
        scope = self.store.capture_owner_scope()
        if (
            int(scope["generation"]) != generation
            or scope["owner_state"] != "resolving"
        ):
            raise StaleOwnerGeneration("identity transition superseded")
        puuid = str(account.get("puuid") or "").strip()
        if not puuid:
            raise ValueError("identity response missing puuid")
        self.store.activate_owner(puuid, riot_id, region_route, generation)

    def start(self) -> dict[str, Any]:
        """Kick era-first Backfill for one captured owner generation."""
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            if self._loop is None:
                try:
                    self._loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass
            settings = self._get_settings()
            scope = self.store.capture_owner_scope()
            if not settings.get("riot_key"):
                generation = self._begin_run("era_first", scope)
                self._finalize_run(generation, "error")
                return self.status()
            if scope["owner_state"] != "active":
                if scope["owner_state"] != "resolving":
                    self.store.begin_owner_transition("resolving")
                    scope = self.store.capture_owner_scope()
            elif not scope.get("owner_key") or not self.store._puuid_for_owner(scope["owner_key"]):
                self.store.begin_owner_transition("resolving")
                scope = self.store.capture_owner_scope()
            generation = self._begin_run("era_first", scope)
            if scope.get("owner_key"):
                self.store.reset_running_items(scope["owner_key"])
            self._thread = threading.Thread(
                target=self._run_riot,
                args=(settings, int(scope["generation"]), scope.get("owner_key")),
                name="bl-sync",
                daemon=True,
            )
            self._thread.start()
            return self.status()

    def import_from_dir(
        self, dir: Path, loop: asyncio.AbstractEventLoop | None = None
    ) -> dict[str, Any]:
        """Ingest a directory while making it visible to transition barriers."""
        worker = threading.current_thread()
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive() and self._thread is not worker:
                raise RuntimeError("Backfill is already running")
            self._cancel.clear()
            self._thread = worker
        try:
            return self._import_from_dir(dir, loop)
        finally:
            with self._start_lock:
                if self._thread is worker:
                    self._thread = None

    def _import_from_dir(
        self, dir: Path, loop: asyncio.AbstractEventLoop | None = None
    ) -> dict[str, Any]:
        """Ingest a LoLTrends-layout folder into its resolved owner namespace."""
        canonical_dir = canonical_import_directory(dir, self._import_roots)
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        if loop is not None:
            self.attach_loop(loop)
        state = json.loads(
            (canonical_dir / "fetch_state.json").read_text(encoding="utf-8")
        )
        puuid = str(state.get("puuid") or "").strip()
        if not puuid:
            raise ValueError("import fetch state is missing puuid")
        settings = self._get_settings()
        scope = self.store.capture_owner_scope()
        if self._cancel.is_set():
            return self._cancelled_status(scope)
        if (
            scope["owner_state"] != "active"
            or self.store._puuid_for_owner(scope.get("owner_key") or "") != puuid
        ):
            if (
                self._thread is not threading.current_thread()
                and not self.quiesce()
            ):
                raise RuntimeError("previous Backfill did not quiesce")
            generation = self.store.begin_owner_transition("resolving")
            scope = self.store.capture_owner_scope()
            owner_key = self.store.activate_owner(
                puuid,
                settings.get("riot_id"),
                str(settings.get("region_route") or "sea"),
                generation,
            )
            scope = self.store.capture_owner_scope()
        else:
            owner_key = str(scope["owner_key"])
            generation = int(scope["generation"])
        if self._cancel.is_set():
            return self._cancelled_status(scope)
        self.store.set_setting("sync_mode", "import")
        self.store.set_setting("import_dir", str(canonical_dir))
        detail_paths = [
            p
            for p in sorted(canonical_dir.glob("*.json"), reverse=True)
            if not p.name.endswith("_timeline.json") and p.name != "fetch_state.json"
        ]
        self.store.reset_running_items(owner_key)
        run_generation = self._begin_run("import", scope)
        added = 0
        try:
            for priority, path in enumerate(detail_paths):
                if self._cancel.is_set():
                    raise _Cancelled()
                added += self.store.enqueue(
                    [path.stem],
                    priority=priority,
                    owner_key=owner_key,
                    region_route=str(settings.get("region_route") or "sea"),
                )
            with self._lock:
                self._status["total_queued"] = added
            log.info("import queued %d matches", added)
            asyncio.run(
                self._process(
                    self._file_fetcher(canonical_dir),
                    puuid,
                    owner_key=owner_key,
                    owner_generation=generation,
                )
            )
        except _Cancelled:
            log.warning("import cancelled; enqueued rows remain resumable")
            self._finalize_run(run_generation, "cancelled")
        return self.status()

    # -- internals ------------------------------------------------------

    def _begin_run(self, mode: str, scope: dict[str, Any] | None = None) -> int:
        scope = scope or self.store.capture_owner_scope()
        with self._lock:
            self._run_generation += 1
            generation = self._run_generation
            self._run_owner_key = scope.get("owner_key")
            self._run_owner_generation = int(scope.get("generation") or 0)
            self._run_owner_state = str(scope.get("owner_state") or "unassigned")
            self._run_puuid = (
                self.store._puuid_for_owner(str(scope["owner_key"]))
                if scope.get("owner_key")
                else None
            )
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
            self._finalized_generation = generation - 1
        self._cancel.clear()
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        return generation

    def _set_run_owner(
        self, owner_key: str, puuid: str, owner_generation: int, state: str = "active"
    ) -> None:
        with self._lock:
            self._run_owner_key = owner_key
            self._run_puuid = puuid
            self._run_owner_generation = owner_generation
            self._run_owner_state = state

    def _finalize_run(self, generation: int, state: str) -> None:
        """Single idempotent run exit: one status, one terminal event."""
        with self._lock:
            if generation <= self._finalized_generation:
                return
            self._finalized_generation = generation
            self._status.update(state=state, current_match_id=None)
        self._publish("sync.done")

    def _run_riot(
        self, settings: dict[str, Any], owner_generation: int, owner_key: str | None
    ) -> None:
        with self._lock:
            generation = self._run_generation
        try:
            asyncio.run(self._riot_flow(settings, owner_generation, owner_key))
        except _Cancelled:
            log.warning("backfill cancelled; uncommitted work restored to pending")
            self._finalize_run(generation, "cancelled")
        except StaleOwnerGeneration:
            self._finalize_run(generation, "cancelled")
        except Exception:
            log.exception("era-first backfill crashed")
            self._finalize_run(generation, "error")
        else:
            self._finalize_run(generation, "idle")

    async def _riot_flow(
        self,
        settings: dict[str, Any],
        owner_generation: int,
        owner_key: str | None,
    ) -> None:
        region_route = str(settings.get("region_route") or "sea")
        riot_id = str(settings.get("riot_id") or "").strip()
        api_key = str(settings["riot_key"])
        client = self._client_factory(api_key, region_route)
        clients: dict[str, Any] = {region_route: client}

        async def fetch_item(item: dict[str, Any]) -> tuple[Any, Any]:
            item_route = str(item.get("region_route") or region_route)
            item_client = clients.get(item_route)
            if item_client is None:
                item_client = self._client_factory(api_key, item_route)
                clients[item_route] = item_client
            detail = await item_client.match(str(item["match_id"]))
            timeline = await item_client.timeline(str(item["match_id"]))
            return detail, timeline

        try:
            puuid = (
                self.store._puuid_for_owner(owner_key)
                if owner_key
                else None
            )
            if not puuid:
                account = await self._account_by_riot_id_with_fallback(
                    api_key, riot_id, region_route
                )
                if self._cancel.is_set():
                    raise _Cancelled()
                scope = self.store.capture_owner_scope()
                if int(scope["generation"]) != owner_generation:
                    raise StaleOwnerGeneration("identity transition superseded")
                puuid = str(account.get("puuid") or "").strip()
                if not puuid:
                    raise ValueError("identity response missing puuid")
                owner_key = self.store.activate_owner(
                    puuid, riot_id, region_route, owner_generation
                )
                self._set_run_owner(owner_key, puuid, owner_generation)
            else:
                self._set_run_owner(owner_key, puuid, owner_generation)
            self.store.reset_running_items(owner_key)
            ids = await client.match_ids(puuid, BACKFILL_TOTAL)
            if self._cancel.is_set():
                raise _Cancelled()
            scope = self.store.capture_owner_scope()
            if int(scope["generation"]) != owner_generation:
                raise StaleOwnerGeneration("identity transition superseded")
            for priority, match_id in enumerate(ids):
                if self._cancel.is_set():
                    raise _Cancelled()
                self.store.enqueue(
                    [match_id],
                    priority=priority,
                    owner_key=owner_key,
                    region_route=region_route,
                )
            with self._lock:
                self._status["total_queued"] = self.store.queue_stats(owner_key)["pending"]
            self._publish("sync.progress")
            await self._process(
                self._http_fetcher(client),
                puuid,
                owner_key=owner_key,
                owner_generation=owner_generation,
                fetch_item=fetch_item,
            )
        except _Cancelled:
            raise
        except StaleOwnerGeneration:
            raise
        except RiotNotFound:
            self.store.set_owner_error(owner_generation, "Riot ID could not be resolved")
            raise
        except RiotForbidden:
            self.store.set_owner_error(owner_generation, "Riot API key was rejected")
            raise
        except (RiotRecoverableError, RiotRateLimited):
            self.store.set_owner_error(
                owner_generation, "Riot identity is temporarily unavailable"
            )
            raise
        except Exception:
            self.store.set_owner_error(owner_generation, "Riot identity is unavailable")
            raise
        finally:
            for item_client in clients.values():
                try:
                    await item_client.aclose()
                except Exception:
                    log.warning("Riot client close failed")

    def _cancelled_status(self, scope: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._run_owner_key = scope.get("owner_key")
            self._run_owner_generation = int(scope.get("generation") or 0)
            self._run_owner_state = scope.get("owner_state") or "unassigned"
            self._status.update(state="cancelled", current_match_id=None)
        return self.status()


    async def _process(
        self,
        fetch_pair: Callable[[str], Awaitable[tuple[Any, Any]]],
        puuid: str,
        *,
        owner_key: str | None = None,
        owner_generation: int | None = None,
        fetch_item: Callable[[dict[str, Any]], Awaitable[tuple[Any, Any]]] | None = None,
    ) -> None:
        if not owner_key:
            raise RuntimeError("owner-scoped processing requires an active owner namespace")
        key = owner_key
        generation = self._run_generation
        remaining = self.store.queue_stats(key)["pending"]
        recoverable_failure = False
        deferred: set[str] = set()
        while not self._cancel.is_set() and remaining:
            item = self.store.claim_next_pending(deferred, owner_key=key)
            if item is None:
                break
            remaining -= 1
            match_id = str(item["match_id"])
            with self._lock:
                self._status["current_match_id"] = match_id
            try:
                detail, timeline = await (
                    fetch_item(item) if fetch_item is not None else fetch_pair(match_id)
                )
                if self._cancel.is_set() or (
                    owner_generation is not None
                    and int(self.store.capture_owner_scope()["generation"])
                    != owner_generation
                ):
                    self.store.recover_queue_item(
                        match_id, bump_attempts=False, owner_key=key
                    )
                    break
                parsed = parse_match(detail, puuid)
                info = detail.get("info") if isinstance(detail, dict) else None
                participants = info.get("participants") if isinstance(info, dict) else None
                v2 = parse_personal_history_v2(
                    timeline,
                    puuid,
                    participants if isinstance(participants, list) else None,
                    detail=detail if isinstance(detail, dict) else None,
                )
                v2_features = {
                    key: v2.get(key)
                    for key in V2_FEATURE_ORDER
                }
                feature_payload = {
                    "feature_contract_version": PARITY_V2_VERSION,
                    "personal_history_eligibility": v2["personal_history_eligibility"],
                    "features": v2_features,
                    "feature_status": {
                        key: "available" if value is not None else "unavailable"
                        for key, value in v2_features.items()
                    },
                    "team_state": v2["team_state"],
                }
                completed = self.store.complete_match(
                    parsed["match_id"],
                    parsed["played_at"],
                    parsed["patch"],
                    parsed["role"],
                    parsed["champion"],
                    parsed["win"],
                    parsed["duration_s"],
                    json.dumps(feature_payload, allow_nan=False),
                    owner_key=key,
                )
                if completed:
                    self._bump("downloaded")
            except (FileNotFoundError, RiotNotFound):
                self.store.fail_queue_item(match_id, owner_key=key)
                self._bump("skipped")
            except (RiotRecoverableError, RiotRateLimited):
                log.warning("recoverable failure processing %s", match_id)
                self.store.recover_queue_item(match_id, owner_key=key)
                deferred.add(match_id)
                recoverable_failure = True
                self._bump("failed")
            except RiotForbidden:
                log.warning("forbidden input while processing %s", match_id)
                self.store.fail_queue_item(match_id, owner_key=key)
                self._bump("failed")
            except Exception:
                log.exception("failed processing %s", match_id)
                self.store.fail_queue_item(match_id, owner_key=key)
                self._bump("failed")
            finally:
                with self._lock:
                    self._status["current_match_id"] = None
            self._publish("sync.progress")
        state = "cancelled" if self._cancel.is_set() else "idle"
        if recoverable_failure and state != "cancelled":
            state = "error"
        self._finalize_run(generation, state)

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

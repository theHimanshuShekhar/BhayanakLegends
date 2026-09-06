from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.riot_client import (
    RiotForbidden,
    RiotNotFound,
    RiotRateLimited,
    RiotRecoverableError,
)
from bhayanak_legends.sse import Hub
from bhayanak_legends.store import Store
from bhayanak_legends.sync import SyncService

REPO = Path(__file__).resolve().parents[2]
DEV_DIR = REPO / "data" / "dev-import" / "FixturePlayer03-BL03"
requires_dev_import = pytest.mark.skipif(
    not (DEV_DIR / "fetch_state.json").exists(),
    reason="requires gitignored data/dev-import real-match fixtures",
)
AUTH = {
    "X-BL-Token": "local-sidecar-development-token-32chars",
    "Host": "127.0.0.1:23110",
}
FIRST_FIVE = [
    "SG2_140646556",
    "SG2_140997685",
    "SG2_141207901",
    "SG2_141232486",
    "SG2_141401951",
]
PUUID = "fixture-puuid-03"


def make_import_dir(tmp_path: Path) -> Path:
    target = tmp_path / "import"
    target.mkdir()
    shutil.copy(DEV_DIR / "fetch_state.json", target / "fetch_state.json")
    for match_id in FIRST_FIVE:
        shutil.copy(DEV_DIR / f"{match_id}.json", target / f"{match_id}.json")
        timeline = DEV_DIR / f"{match_id}_timeline.json"
        if timeline.exists():
            shutil.copy(timeline, target / f"{match_id}_timeline.json")
    return target


def build_app(tmp_path: Path):
    config = SidecarConfig(
        port=23110,
        token="local-sidecar-development-token-32chars",
        data_dir=tmp_path / "data",
        pack_dir=REPO / "pack" if (REPO / "pack").exists() else None,
        allow_import=True,
        import_roots=[tmp_path],
    )
    app = create_app(config)
    return app, TestClient(app)


def activate_owner(store: Store, puuid: str = "sync-test-puuid") -> str:
    generation = store.begin_owner_transition("resolving")
    return store.activate_owner(puuid, "SyncTester#1234", "sea", generation)


def prepared_store(tmp_path: Path) -> tuple[Store, str]:
    store = Store(tmp_path / "app.db")
    return store, activate_owner(store)


def service_for(store: Store, owner_key: str) -> SyncService:
    service = SyncService(store, Hub(), lambda: {})
    scope = store.capture_owner_scope()
    assert scope["owner_key"] == owner_key
    service._begin_run("import", scope)
    return service


async def drain(queue: asyncio.Queue) -> list[dict]:
    await asyncio.sleep(0)
    events = []
    while not queue.empty():
        frame = queue.get_nowait()
        events.append(json.loads(frame.removeprefix("data: ")))
    return events


@requires_dev_import
async def test_import_from_dir_end_to_end(tmp_path: Path):
    app, client = build_app(tmp_path)
    svc = app.state.sync_service
    hub = app.state.hub
    queue = hub.subscribe()

    status = await asyncio.to_thread(
        svc.import_from_dir, make_import_dir(tmp_path), asyncio.get_running_loop()
    )

    owner_key = app.state.store.active_owner_key()
    assert owner_key is not None
    assert app.state.store.match_count(owner_key=owner_key) == 5
    assert status["state"] == "idle"
    assert status["mode"] == "import"
    assert status["total_queued"] == 5
    assert status["downloaded"] == 5
    assert status["failed"] == 0
    assert app.state.store.get_setting("sync_mode") == "import"

    envelopes = await drain(queue)
    types = [e["type"] for e in envelopes]
    assert "sync.progress" in types
    assert types[-1] == "sync.done"
    assert envelopes[-1]["data"]["downloaded"] == 5

    with client:
        res = client.get("/history/summary", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["matches"] == 5


@requires_dev_import
async def test_import_is_idempotent_on_rerun(tmp_path: Path):
    app, _client = build_app(tmp_path)
    svc = app.state.sync_service
    directory = make_import_dir(tmp_path)

    await asyncio.to_thread(svc.import_from_dir, directory, asyncio.get_running_loop())
    second = await asyncio.to_thread(svc.import_from_dir, directory, asyncio.get_running_loop())

    owner_key = app.state.store.active_owner_key()
    assert owner_key is not None
    assert app.state.store.match_count(owner_key=owner_key) == 5
    assert second["total_queued"] == 0
    assert second["downloaded"] == 0


@requires_dev_import
def test_dev_import_endpoint_guarded(tmp_path: Path):
    app, client = build_app(tmp_path)
    app.state.config.allow_import = False
    body = {"dir": str(make_import_dir(tmp_path))}
    with client:
        res = client.post("/dev/import", json=body, headers=AUTH)
    assert res.status_code == 403
    assert res.json()["detail"] == "dev import disabled"


class FakeRiotClient:
    def __init__(self, detail: dict, timeline: dict) -> None:
        self.detail = detail
        self.timeline_payload = timeline
        self.account_requests: list[str] = []
        self.match_id_requests: list[tuple[str, int]] = []
        self.detail_requests: list[str] = []
        self.timeline_requests: list[str] = []
        self.closed = False

    async def account_by_riot_id(self, riot_id: str) -> dict[str, str]:
        self.account_requests.append(riot_id)
        return {"puuid": PUUID}

    async def match_ids(self, puuid: str, total: int) -> list[str]:
        self.match_id_requests.append((puuid, total))
        return ["SG2_170114893"]

    async def match(self, match_id: str) -> dict:
        self.detail_requests.append(match_id)
        return self.detail

    async def timeline(self, match_id: str) -> dict:
        self.timeline_requests.append(match_id)
        return self.timeline_payload

    async def aclose(self) -> None:
        self.closed = True


def test_http_fetcher_factory_is_callable(tmp_path: Path):
    service = SyncService(Store(tmp_path / "app.db"), Hub(), lambda: {})
    assert callable(service._http_fetcher(object()))


def test_start_is_idempotent_while_backfill_worker_is_running(tmp_path: Path):
    service = SyncService(
        Store(tmp_path / "app.db"),
        Hub(),
        lambda: {"riot_key": "test-key", "riot_id": "Player#1234", "region_route": "sea"},
    )
    entered = threading.Event()
    release = threading.Event()

    def blocked_run(_settings: dict, _generation: int, _owner_key: str | None) -> None:
        entered.set()
        release.wait(1.0)

    service._run_riot = blocked_run  # type: ignore[method-assign]
    first = service.start()
    assert entered.wait(1.0)
    second = service.start()
    release.set()
    service.shutdown()

    assert first["state"] == "running"
    assert second["state"] == "running"


async def test_riot_backfill_resolves_and_persists_match(tmp_path: Path):
    fixture_dir = Path(__file__).parent / "fixtures"
    fake_client = FakeRiotClient(
        json.loads((fixture_dir / "SG2_170114893.json").read_text()),
        json.loads((fixture_dir / "SG2_170114893_timeline.json").read_text()),
    )
    store = Store(tmp_path / "app.db")
    hub = Hub()
    queue = hub.subscribe()
    settings = {
        "riot_key": "test-key",
        "riot_id": "FixturePlayer03#BL03",
        "region_route": "sea",
    }
    service = SyncService(store, hub, lambda: settings, client_factory=lambda key, route: fake_client)
    service.attach_loop(asyncio.get_running_loop())

    service.start()
    assert service._thread is not None
    await asyncio.to_thread(service._thread.join, 2.0)
    status = service.status()

    owner_key = store.active_owner_key()
    assert owner_key is not None
    assert not service._thread.is_alive()
    assert fake_client.account_requests == ["FixturePlayer03#BL03"]
    assert fake_client.match_id_requests == [(PUUID, 1000)]
    assert fake_client.detail_requests == ["SG2_170114893"]
    assert fake_client.timeline_requests == ["SG2_170114893"]
    assert fake_client.closed
    assert store.match_count(owner_key=owner_key) == 1
    assert store.all_matches(owner_key=owner_key)[0]["match_id"] == "SG2_170114893"
    assert status["state"] == "idle"
    assert status["total_queued"] == 1
    assert status["downloaded"] == 1
    assert status["skipped"] == 0
    assert status["failed"] == 0

    events = await drain(queue)
    assert events[-1]["type"] == "sync.done"
    assert events[-1]["data"] == status


def test_stale_owner_resolution_cannot_activate_after_a_to_b_to_a(
    tmp_path: Path,
):
    store = Store(tmp_path / "app.db")
    store.set_setting("riot_id", "PlayerA#0001")
    store.set_setting("region_route", "sea")
    release_a = threading.Event()
    release_b = threading.Event()
    started_a = threading.Event()
    started_b = threading.Event()
    calls: dict[str, int] = {}

    def settings() -> dict[str, str | None]:
        return {
            "riot_key": "test-key",
            "riot_id": store.get_setting("riot_id"),
            "region_route": str(store.get_setting("region_route") or "sea"),
        }

    class FakeResolverClient:
        def __init__(self, riot_id: str) -> None:
            self.riot_id = riot_id

        async def account_by_riot_id(self, riot_id: str) -> dict[str, str]:
            calls[riot_id] = calls.get(riot_id, 0) + 1
            if riot_id == "PlayerA#0001" and calls[riot_id] == 1:
                started_a.set()
                await asyncio.to_thread(release_a.wait)
            elif riot_id == "PlayerB#0002":
                started_b.set()
                await asyncio.to_thread(release_b.wait)
            return {"puuid": f"puuid:{riot_id}"}

        async def aclose(self) -> None:
            return None

    service = SyncService(
        store,
        Hub(),
        settings,
        client_factory=lambda _key, riot_id: FakeResolverClient(riot_id),
    )
    generation_a = store.begin_owner_transition("resolving")
    service.resolve_owner(generation_a)
    assert started_a.wait(1.0)

    store.set_setting("riot_id", "PlayerB#0002")
    generation_b = store.begin_owner_transition("resolving")
    service.resolve_owner(generation_b)
    assert started_b.wait(1.0)

    store.set_setting("riot_id", "PlayerA#0001")
    generation_a_again = store.begin_owner_transition("resolving")
    service.resolve_owner(generation_a_again)
    owner_a = store.owner_key_for_puuid("puuid:PlayerA#0001")
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        scope = store.capture_owner_scope()
        if (
            scope["owner_key"] == owner_a
            and scope["generation"] == generation_a_again
            and scope["owner_state"] == "active"
        ):
            break
        time.sleep(0.01)

    release_a.set()
    release_b.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with service._resolution_lock:
            if not service._resolution_threads:
                break
        time.sleep(0.01)

    assert store.capture_owner_scope()["owner_key"] == owner_a
    assert store.capture_owner_scope()["generation"] == generation_a_again
    assert store.capture_owner_scope()["owner_state"] == "active"


def test_store_initializes_owner_scoped_schema_v2(tmp_path: Path):
    store = Store(tmp_path / "app.db")
    with store._lock:
        version = store._conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in store._conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert version == 2
    assert tables == {"settings", "matches", "sync_queue", "owner_namespaces"}



@pytest.mark.parametrize("version", [1, 3])
def test_store_rejects_unsupported_schema_version(tmp_path: Path, version: int):
    path = tmp_path / f"schema-{version}.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="unsupported database schema version"):
        Store(path)


def test_queue_claim_and_match_completion_are_atomic(tmp_path: Path):
    path = tmp_path / "queue.db"
    first = Store(path)
    owner_key = activate_owner(first)
    second = Store(path)
    first.enqueue(["match-1"], owner_key=owner_key)
    claimed: list[dict] = []

    def claim(store: Store) -> None:
        row = store.claim_next_pending(owner_key=owner_key)
        if row is not None:
            claimed.append(row)

    left = threading.Thread(target=claim, args=(first,))
    right = threading.Thread(target=claim, args=(second,))
    left.start()
    right.start()
    left.join()
    right.join()

    assert len(claimed) == 1
    assert claimed[0]["state"] == "running"
    assert first.claim_next_pending(owner_key=owner_key) is None
    assert first.complete_match(
        "match-1", "2026-01-01", "14.1", "TOP", "Aatrox", True, 1800, "{}", owner_key=owner_key
    )
    assert not first.complete_match(
        "match-1", "2026-01-01", "14.1", "TOP", "Aatrox", True, 1800, "{}", owner_key=owner_key
    )
    assert first.all_matches(owner_key=owner_key)[0]["match_id"] == "match-1"
    assert first.queue_stats(owner_key=owner_key)["done"] == 1


def test_match_completion_rolls_back_match_and_queue_together(tmp_path: Path):
    store, owner_key = prepared_store(tmp_path)
    store.enqueue(["match-1"], owner_key=owner_key)
    assert store.claim_next_pending(owner_key=owner_key) is not None

    with pytest.raises(sqlite3.ProgrammingError):
        store.complete_match(
            "match-1", "2026-01-01", "14.1", "TOP", "Aatrox", True, 1800,
            object(),  # type: ignore[arg-type]
            owner_key=owner_key,
        )

    assert store.match_count(owner_key=owner_key) == 0
    assert queue_row(store, "match-1", owner_key)["state"] == "running"


async def test_timeline_failure_never_completes_match(tmp_path: Path):
    fixture_dir = Path(__file__).parent / "fixtures"
    detail = json.loads((fixture_dir / "SG2_170114893.json").read_text())
    store, owner_key = prepared_store(tmp_path)
    store.enqueue(["match-timeline-failure"], owner_key=owner_key)
    service = service_for(store, owner_key)

    async def fetch(_match_id: str) -> tuple[dict, dict]:
        return detail, (_ for _ in ()).throw(ValueError("timeline parse failed"))

    await service._process(fetch, PUUID, owner_key=owner_key)
    assert store.match_count(owner_key=owner_key) == 0
    assert store.queue_stats(owner_key=owner_key)["done"] == 0


def queue_row(store: Store, match_id: str, owner_key: str) -> dict:
    with store._lock:
        row = store._conn.execute(
            "SELECT state, attempts FROM sync_queue WHERE owner_key = ? AND match_id = ?",
            (owner_key, match_id),
        ).fetchone()
    assert row is not None
    return dict(row)


@pytest.mark.parametrize(
    ("error", "state", "skipped", "failed"),
    [
        (RiotNotFound(), "failed", 1, 0),
        (RiotForbidden(), "failed", 0, 1),
        (RiotRecoverableError("transport"), "pending", 0, 1),
        (RiotRateLimited(), "pending", 0, 1),
    ],
)
async def test_queue_failure_classes_have_distinct_outcomes(
    tmp_path: Path, error: Exception, state: str, skipped: int, failed: int
):
    match_id = "classified-failure"
    store, owner_key = prepared_store(tmp_path)
    store.enqueue([match_id], owner_key=owner_key)
    service = service_for(store, owner_key)

    async def fetch(_match_id: str) -> tuple[dict, dict]:
        raise error

    await service._process(fetch, PUUID, owner_key=owner_key)
    assert queue_row(store, match_id, owner_key) == {"state": state, "attempts": 1}
    status = service.status()
    assert status["skipped"] == skipped
    assert status["failed"] == failed
    assert status["state"] == ("error" if state == "pending" else "idle")


async def test_recoverable_failure_requeues_for_next_session(tmp_path: Path):
    detail = json.loads((Path(__file__).parent / "fixtures" / "SG2_170114893.json").read_text())
    timeline = json.loads((Path(__file__).parent / "fixtures" / "SG2_170114893_timeline.json").read_text())
    match_id = str(detail["metadata"]["matchId"])
    store, owner_key = prepared_store(tmp_path)
    store.enqueue([match_id], owner_key=owner_key)
    service = service_for(store, owner_key)

    async def fetch(_match_id: str) -> tuple[dict, dict]:
        raise RiotRecoverableError("5xx for matches", status_code=503)

    await service._process(fetch, PUUID, owner_key=owner_key)
    assert queue_row(store, match_id, owner_key) == {"state": "pending", "attempts": 1}
    assert service.status()["state"] == "error"

    service2 = service_for(store, owner_key)

    async def fetch_ok(_match_id: str) -> tuple[dict, dict]:
        return detail, timeline

    await service2._process(fetch_ok, PUUID, owner_key=owner_key)
    assert queue_row(store, match_id, owner_key)["state"] == "done"
    assert store.match_count(owner_key=owner_key) == 1


@pytest.mark.parametrize("endpoint", ["detail", "timeline"])
async def test_detail_or_timeline_404_is_terminal_skip(tmp_path: Path, endpoint: str):
    detail = json.loads((Path(__file__).parent / "fixtures" / "SG2_170114893.json").read_text())
    match_id = f"404-{endpoint}"
    store, owner_key = prepared_store(tmp_path)
    store.enqueue([match_id], owner_key=owner_key)
    service = service_for(store, owner_key)

    async def fetch(_match_id: str) -> tuple[dict, dict]:
        if endpoint == "detail":
            raise RiotNotFound()
        return detail, (_ for _ in ()).throw(RiotNotFound())

    await service._process(fetch, PUUID, owner_key=owner_key)
    assert queue_row(store, match_id, owner_key) == {"state": "failed", "attempts": 1}
    assert service.status()["skipped"] == 1
    assert service.status()["failed"] == 0


async def test_missing_import_input_is_terminal_skip(tmp_path: Path):
    match_id = "missing-input"
    import_dir = tmp_path / "import"
    import_dir.mkdir()
    store, owner_key = prepared_store(tmp_path)
    store.enqueue([match_id], owner_key=owner_key)
    service = service_for(store, owner_key)

    await service._process(service._file_fetcher(import_dir), PUUID, owner_key=owner_key)
    assert queue_row(store, match_id, owner_key) == {"state": "failed", "attempts": 1}
    assert service.status()["skipped"] == 1
    assert service.status()["downloaded"] == 0


async def test_recoverable_item_requeues_while_valid_item_completes(tmp_path: Path):
    fixture_dir = Path(__file__).parent / "fixtures"
    detail = json.loads((fixture_dir / "SG2_170114893.json").read_text())
    timeline = json.loads((fixture_dir / "SG2_170114893_timeline.json").read_text())
    retry_id = "recoverable-first"
    valid_id = "valid-second"
    store, owner_key = prepared_store(tmp_path)
    store.enqueue([retry_id], priority=0, owner_key=owner_key)
    store.enqueue([valid_id], priority=1, owner_key=owner_key)
    service = service_for(store, owner_key)

    async def fetch(match_id: str) -> tuple[dict, dict]:
        if match_id == retry_id:
            raise RiotRecoverableError("temporary")
        valid_detail = dict(detail)
        valid_detail["metadata"] = dict(detail["metadata"], matchId=valid_id)
        return valid_detail, timeline

    await service._process(fetch, PUUID, owner_key=owner_key)
    assert queue_row(store, retry_id, owner_key) == {"state": "pending", "attempts": 1}
    assert queue_row(store, valid_id, owner_key) == {"state": "done", "attempts": 0}
    assert store.match_count(owner_key=owner_key) == 1
    assert service.status()["downloaded"] == 1
    assert service.status()["failed"] == 1
    assert service.status()["state"] == "error"


async def test_cancelled_inflight_match_resumes_after_restart_without_partial_commit(tmp_path: Path):
    store, owner_key = prepared_store(tmp_path)
    detail = json.loads((Path(__file__).parent / "fixtures" / "SG2_170114893.json").read_text())
    timeline = json.loads((Path(__file__).parent / "fixtures" / "SG2_170114893_timeline.json").read_text())
    match_id = str(detail["metadata"]["matchId"])
    store.enqueue([match_id], owner_key=owner_key)

    service = service_for(store, owner_key)
    terminal_queue = service.hub.subscribe()

    async def fetch(_match_id: str):
        service.cancel()
        return detail, timeline

    await service._process(fetch, PUUID, owner_key=owner_key)
    row = queue_row(store, match_id, owner_key)
    assert row == {"state": "pending", "attempts": 0}
    assert store.match_count(owner_key=owner_key) == 0
    await asyncio.sleep(0.05)
    drained = []
    while not terminal_queue.empty():
        drained.append(json.loads(terminal_queue.get_nowait())["type"])
    assert drained.count("sync.done") == 1

    service2 = service_for(store, owner_key)

    async def fetch_ok(_match_id: str):
        return detail, timeline

    await service2._process(fetch_ok, PUUID, owner_key=owner_key)
    assert queue_row(store, match_id, owner_key)["state"] == "done"
    assert store.match_count(owner_key=owner_key) == 1


async def test_sync_done_is_exactly_once_and_survives_full_subscriber_queue():
    hub = Hub()
    queue = hub.subscribe()
    total = queue.maxsize + 8
    for index in range(total):
        await hub.publish("sync.progress", {"downloaded": index})
    await hub.publish("sync.done", {"state": "idle"})

    frames = []
    while not queue.empty():
        frames.append(json.loads(queue.get_nowait())["type"])
    assert frames[-1] == "sync.done"
    assert frames.count("sync.done") == 1

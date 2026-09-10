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
def test_import_worker_is_quiesced_before_owner_transition(tmp_path: Path):
    fixture_dir = Path(__file__).parent / "fixtures"
    detail = json.loads((fixture_dir / "SG2_170114893.json").read_text())
    timeline = json.loads((fixture_dir / "SG2_170114893_timeline.json").read_text())
    import_dir = tmp_path / "import"
    import_dir.mkdir()
    (import_dir / "fetch_state.json").write_text(
        json.dumps({"puuid": PUUID}), encoding="utf-8"
    )
    (import_dir / "SG2_170114893.json").write_text("{}", encoding="utf-8")

    store = Store(tmp_path / "app.db")
    service = SyncService(store, Hub(), lambda: {}, import_roots=[tmp_path])
    entered = threading.Event()
    release = threading.Event()

    async def fetch(_match_id: str) -> tuple[dict, dict]:
        entered.set()
        await asyncio.to_thread(release.wait)
        return detail, timeline

    service._file_fetcher = lambda _dir: fetch  # type: ignore[method-assign]
    worker = threading.Thread(target=service.import_from_dir, args=(import_dir,))
    worker.start()
    assert entered.wait(1.0)
    assert service.quiesce(timeout=0.01) is False
    release.set()
    worker.join(2.0)
    assert not worker.is_alive()



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

def test_backfill_uses_each_queue_items_captured_region_route(tmp_path: Path):
    fixture_dir = Path(__file__).parent / "fixtures"
    detail = json.loads((fixture_dir / "SG2_170114893.json").read_text())
    timeline = json.loads((fixture_dir / "SG2_170114893_timeline.json").read_text())
    store = Store(tmp_path / "app.db")
    owner_key = activate_owner(store, PUUID)
    match_id = str(detail["metadata"]["matchId"])
    store.enqueue([match_id], owner_key=owner_key, region_route="americas")
    routes: list[str] = []
    fetched_routes: list[str] = []

    class RoutedClient:
        def __init__(self, route: str) -> None:
            self.route = route
            routes.append(route)

        async def match_ids(self, _puuid: str, _total: int) -> list[str]:
            return []

        async def match(self, _match_id: str) -> dict:
            fetched_routes.append(self.route)
            return detail

        async def timeline(self, _match_id: str) -> dict:
            return timeline

        async def aclose(self) -> None:
            return None

    service = SyncService(
        store,
        Hub(),
        lambda: {
            "riot_key": "test-key",
            "riot_id": "Player#1234",
            "region_route": "europe",
        },
        client_factory=lambda _key, route: RoutedClient(route),
    )
    service.start()
    assert service._thread is not None
    service._thread.join(2.0)

    assert routes == ["europe", "americas"]
    assert fetched_routes == ["americas"]
    assert store.queue_stats(owner_key=owner_key)["done"] == 1


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



@pytest.mark.parametrize("version", [3])
def test_store_rejects_unsupported_schema_version(tmp_path: Path, version: int):
    path = tmp_path / f"schema-{version}.db"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="unsupported database schema version"):
        Store(path)
def make_legacy_v1_database(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE matches (
            match_id TEXT PRIMARY KEY,
            played_at TEXT,
            patch TEXT,
            role TEXT,
            champion TEXT,
            win INTEGER,
            duration_s INTEGER,
            features_json TEXT
        );
        CREATE TABLE sync_queue (
            match_id TEXT PRIMARY KEY,
            priority INTEGER NOT NULL DEFAULT 100,
            state TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            added_at TEXT
        );
        INSERT INTO settings (key, value) VALUES
            ('riot_id', 'Legacy#0001'),
            ('owner_key', 'must-not-attribute'),
            ('owner_state', 'active');
        INSERT INTO matches VALUES
            ('legacy-a', '2026-01-01T00:00:00Z', '16.1', 'TOP', 'Aatrox', 1, 1800, '{}'),
            ('legacy-b', '2026-01-02T00:00:00Z', '16.1', 'BOTTOM', 'Jinx', 0, 1500, '{"mixed":true}');
        INSERT INTO sync_queue VALUES
            ('legacy-a', 0, 'done', 1, '2026-01-01T00:00:00Z'),
            ('legacy-c', 1, 'pending', 0, '2026-01-02T00:00:00Z');
        PRAGMA user_version = 1;
        """
    )
    conn.commit()
    conn.close()


def test_legacy_rows_are_quarantined_without_owner_attribution(tmp_path: Path):
    path = tmp_path / "legacy.db"
    make_legacy_v1_database(path)

    store = Store(path)
    with store._lock:
        version = store._conn.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        legacy_matches = store._conn.execute(
            "SELECT match_id, champion, features_json FROM legacy_matches ORDER BY match_id"
        ).fetchall()
        legacy_queue = store._conn.execute(
            "SELECT match_id, state, attempts FROM legacy_sync_queue ORDER BY match_id"
        ).fetchall()

    assert version == 2
    assert {"matches", "sync_queue", "legacy_matches", "legacy_sync_queue"} <= tables
    assert [tuple(row) for row in legacy_matches] == [
        ("legacy-a", "Aatrox", "{}"),
        ("legacy-b", "Jinx", '{"mixed":true}'),
    ]
    assert [tuple(row) for row in legacy_queue] == [
        ("legacy-a", "done", 1),
        ("legacy-c", "pending", 0),
    ]
    assert store.match_count(store.owner_key_for_puuid("legacy-puuid")) == 0
    scope = store.capture_owner_scope()
    assert scope["owner_key"] is None
    assert scope["owner_state"] == "unassigned"

    store.close()
    retry = Store(path)
    with retry._lock:
        assert retry._conn.execute("SELECT COUNT(*) FROM legacy_matches").fetchone()[0] == 2
        assert retry._conn.execute("SELECT COUNT(*) FROM legacy_sync_queue").fetchone()[0] == 2


def test_legacy_quarantine_rolls_back_and_retries_after_interruption(
    tmp_path: Path, monkeypatch
):
    path = tmp_path / "legacy-interrupted.db"
    make_legacy_v1_database(path)
    original = Store._quarantine_legacy_tables

    def interrupted(store: Store) -> bool:
        original(store)
        raise RuntimeError("simulated migration interruption")

    monkeypatch.setattr(Store, "_quarantine_legacy_tables", interrupted)
    with pytest.raises(RuntimeError, match="simulated migration interruption"):
        Store(path)

    monkeypatch.setattr(Store, "_quarantine_legacy_tables", original)
    store = Store(path)
    with store._lock:
        assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert store._conn.execute("SELECT COUNT(*) FROM legacy_matches").fetchone()[0] == 2
        assert store._conn.execute("SELECT COUNT(*) FROM legacy_sync_queue").fetchone()[0] == 2


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


async def test_deferred_old_owner_response_is_requeued_during_identity_switch(
    tmp_path: Path,
):
    store, owner_a = prepared_store(tmp_path)
    match_id = "deferred-switch"
    store.enqueue([match_id], owner_key=owner_a)
    service = service_for(store, owner_a)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def fetch(_match_id: str) -> tuple[dict, dict]:
        entered.set()
        await release.wait()
        return {}, {}

    processing = asyncio.create_task(
        service._process(
            fetch,
            PUUID,
            owner_key=owner_a,
            owner_generation=store.capture_owner_scope()["generation"],
        )
    )
    await entered.wait()
    generation_b = store.begin_owner_transition("resolving")
    service.cancel()
    release.set()
    await processing

    assert store.match_count(owner_key=owner_a) == 0
    assert queue_row(store, match_id, owner_a) == {"state": "pending", "attempts": 0}
    assert store.capture_owner_scope()["generation"] == generation_b
    assert store.capture_owner_scope()["owner_key"] is None

def test_restart_recovers_persisted_owner_resolution_transition(tmp_path: Path):
    path = tmp_path / "restart.db"
    store = Store(path)
    store.set_setting("riot_id", "Restart#0001")
    generation = store.begin_owner_transition("resolving")
    store.close()

    restarted = Store(path)
    scope = restarted.capture_owner_scope()
    assert scope["generation"] == generation
    assert scope["owner_key"] is None
    assert scope["owner_state"] == "unassigned"

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


class _RouteRecorderClient:
    def __init__(self, route: str, behavior: dict[str, Exception | dict]) -> None:
        self.route = route
        self._behavior = behavior
        self.closed = False

    async def account_by_riot_id(self, riot_id: str) -> dict:
        outcome = self._behavior.get(self.route)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, dict)
        return outcome

    async def aclose(self) -> None:
        self.closed = True


def _fallback_service(tmp_path: Path, behavior: dict[str, Exception | dict]):
    store = Store(tmp_path / "app.db")
    tried: list[str] = []

    def factory(_key: str, route: str):
        tried.append(route)
        return _RouteRecorderClient(route, behavior)

    service = SyncService(store, Hub(), lambda: {}, client_factory=factory)
    return service, store, tried


async def test_account_fallback_sea_forbidden_then_asia_succeeds(tmp_path: Path):
    service, _, tried = _fallback_service(
        tmp_path,
        {
            "sea": RiotForbidden("Riot API key was rejected"),
            "asia": {"puuid": "fallback-puuid"},
            "americas": {"puuid": "fallback-puuid"},
            "europe": {"puuid": "fallback-puuid"},
        },
    )
    account = await service._account_by_riot_id_with_fallback(
        "key", "SeaPlayer#SEA01", "sea"
    )
    assert account["puuid"] == "fallback-puuid"
    assert tried[:2] == ["sea", "asia"]


async def test_account_fallback_all_forbidden_raises_forbidden(tmp_path: Path):
    service, _, tried = _fallback_service(
        tmp_path,
        {
            "sea": RiotForbidden("Riot API key was rejected"),
            "asia": RiotForbidden("Riot API key was rejected"),
            "americas": RiotForbidden("Riot API key was rejected"),
            "europe": RiotForbidden("Riot API key was rejected"),
        },
    )
    with pytest.raises(RiotForbidden):
        await service._account_by_riot_id_with_fallback("key", "Player#1234", "sea")
    assert tried[0] == "sea"
    assert set(tried) == {"sea", "asia", "americas", "europe"}


async def test_account_fallback_forbidden_then_notfound_raises_notfound(tmp_path: Path):
    service, _, _ = _fallback_service(
        tmp_path,
        {
            "sea": RiotForbidden("Riot API key was rejected"),
            "asia": RiotNotFound("Riot resource was not found"),
            "americas": RiotNotFound("Riot resource was not found"),
            "europe": RiotNotFound("Riot resource was not found"),
        },
    )
    with pytest.raises(RiotNotFound):
        await service._account_by_riot_id_with_fallback("key", "Missing#0000", "sea")


async def test_account_fallback_does_not_fan_out_on_rate_limit(tmp_path: Path):
    service, _, tried = _fallback_service(
        tmp_path,
        {"sea": RiotRateLimited(1.0)},
    )
    with pytest.raises(RiotRateLimited):
        await service._account_by_riot_id_with_fallback("key", "Player#1234", "sea")
    assert tried == ["sea"]


async def test_resolve_owner_uses_fallback_and_keeps_selected_route(tmp_path: Path):
    store = Store(tmp_path / "app.db")
    tried: list[str] = []

    def factory(_key: str, route: str):
        tried.append(route)
        behavior: dict[str, Exception | dict] = (
            {"puuid": "sea-fallback-puuid"}
            if route == "asia"
            else RiotForbidden("Riot API key was rejected")
        )
        if isinstance(behavior, dict):
            return _RouteRecorderClient(route, {route: behavior})
        return _RouteRecorderClient(
            route,
            {"sea": behavior, "americas": behavior, "europe": behavior, route: behavior},
        )

    settings = {"riot_key": "key", "riot_id": "SeaPlayer#SEA01", "region_route": "sea"}
    service = SyncService(store, Hub(), lambda: settings, client_factory=factory)
    generation = store.begin_owner_transition("resolving")
    await service._resolve_owner(generation)
    scope = store.capture_owner_scope()
    assert scope["owner_state"] == "active"
    assert store._puuid_for_owner(scope["owner_key"]) == "sea-fallback-puuid"
    assert store.get_setting("region_route") in (None, "sea")
    assert tried[:2] == ["sea", "asia"]

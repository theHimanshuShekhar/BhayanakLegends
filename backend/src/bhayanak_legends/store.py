from __future__ import annotations

from collections.abc import Collection
import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = 2
_OWNER_KEY_PREFIX = b"bhayanak-legends-owner-v2:\0"

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS owner_namespaces (
        owner_key TEXT PRIMARY KEY,
        puuid TEXT NOT NULL UNIQUE,
        last_riot_id TEXT,
        last_region_route TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matches (
        owner_key TEXT NOT NULL,
        match_id TEXT NOT NULL,
        played_at TEXT,
        patch TEXT,
        role TEXT,
        champion TEXT,
        win INTEGER,
        duration_s INTEGER,
        features_json TEXT,
        PRIMARY KEY (owner_key, match_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_queue (
        owner_key TEXT NOT NULL,
        match_id TEXT NOT NULL,
        region_route TEXT NOT NULL DEFAULT 'sea',
        priority INTEGER NOT NULL DEFAULT 100,
        state TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        added_at TEXT,
        PRIMARY KEY (owner_key, match_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_matches_owner_played ON matches(owner_key, played_at)",
    "CREATE INDEX IF NOT EXISTS idx_queue_owner_state ON sync_queue(owner_key, state, priority, match_id)",
)


class StaleOwnerGeneration(RuntimeError):
    """Raised when an async owner activation crosses a newer transition."""


class Store:
    """Thread-safe SQLite state with immutable owner namespaces.

    ``owner_key`` is a one-way namespace derived from a resolved PUUID. The
    PUUID itself remains local in ``owner_namespaces`` and is never returned by
    this class's public account/status helpers.
    """


    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout = 30000")
        self._lock = threading.RLock()
        self._initialize_schema()

    @staticmethod
    def owner_key_for_puuid(puuid: str) -> str:
        """Return a stable, opaque namespace for one immutable PUUID."""
        if not isinstance(puuid, str) or not puuid.strip():
            raise ValueError("resolved PUUID is required")
        return hashlib.sha256(_OWNER_KEY_PREFIX + puuid.strip().encode("utf-8")).hexdigest()


    def _initialize_schema(self) -> None:
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if version not in {0, _SCHEMA_VERSION}:
            raise RuntimeError(
                f"unsupported database schema version {version}; "
                f"this build supports schema {_SCHEMA_VERSION}"
            )
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in _SCHEMA_STATEMENTS:
                    self._conn.execute(statement)
                if version == 0:
                    self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _begin_immediate(self) -> None:
        self._conn.execute("BEGIN IMMEDIATE")

    def _rollback(self) -> None:
        if self._conn.in_transaction:
            self._conn.rollback()

    # -- settings -------------------------------------------------------
    def get_setting(self, key: str) -> str | bytes | None:
        return self.get_raw_setting(key)

    def _raw_setting_unlocked(self, key: str) -> str | bytes | None:
        row = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def get_raw_setting(self, key: str) -> str | bytes | None:
        with self._lock:
            return self._raw_setting_unlocked(key)

    def has_setting(self, key: str) -> bool:
        with self._lock:
            return self._conn.execute(
                "SELECT 1 FROM settings WHERE key = ?", (key,)
            ).fetchone() is not None

    def set_raw_setting(self, key: str, value: str | bytes | None) -> None:
        with self._lock, self._conn:
            if value is None:
                self._conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                self._conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    def delete_raw_setting(self, key: str) -> None:
        self.set_raw_setting(key, None)

    def set_setting(self, key: str, value: str | bytes | None) -> None:
        self.set_raw_setting(key, value)

    @staticmethod
    def _parse_generation(value: object) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def _owner_context_unlocked(self) -> dict[str, Any]:
        owner_key = self._raw_setting_unlocked("owner_key")
        raw_state = self._raw_setting_unlocked("owner_state")
        generation = self._parse_generation(
            self._raw_setting_unlocked("owner_generation")
        )
        state = str(raw_state or ("active" if owner_key else "unassigned"))
        if state not in {"unassigned", "resolving", "active", "error"}:
            state = "unassigned"
        if state != "active":
            owner_key = None
        error = self._raw_setting_unlocked("owner_error") if state == "error" else None
        return {
            "owner_key": str(owner_key) if owner_key else None,
            "generation": generation,
            "owner_state": state,
            "owner_error": str(error) if error else None,
        }

    def capture_owner_scope(self) -> dict[str, Any]:
        """Capture one immutable owner/generation snapshot for a data query.

        The returned ``read_owner_key`` is non-null only for an active owner.
        Callers must pass that exact key to every Personal History query; they
        must not read the current settings again after starting the query.
        """
        with self._lock:
            context = self._owner_context_unlocked()
            return {**context, "read_owner_key": context["owner_key"]}

    def owner_context(self) -> dict[str, Any]:
        """Return public owner state without exposing the resolved PUUID."""
        return {
            key: value
            for key, value in self.capture_owner_scope().items()
            if key != "read_owner_key"
        }


    def active_owner_key(self) -> str | None:
        """Return the opaque owner namespace only while identity is active."""
        return self.capture_owner_scope()["read_owner_key"]

    def _puuid_for_owner(self, owner_key: str) -> str | None:
        """Resolve an owner namespace for backend sync code only."""
        with self._lock:
            row = self._conn.execute(
                "SELECT puuid FROM owner_namespaces WHERE owner_key = ?",
                (owner_key,),
            ).fetchone()
            return str(row["puuid"]) if row else None

    def _current_generation_unlocked(self) -> int:
        return self._parse_generation(self._raw_setting_unlocked("owner_generation"))

    def begin_owner_transition(
        self, state: str = "unassigned", error: str | None = None
    ) -> int:
        """Clear the active owner and advance the serialized generation."""
        if state not in {"unassigned", "resolving", "error"}:
            raise ValueError("invalid owner transition state")
        with self._lock:
            self._begin_immediate()
            try:
                generation = self._current_generation_unlocked() + 1
                values = {
                    "owner_key": None,
                    "owner_state": state,
                    "owner_generation": str(generation),
                    "owner_error": error[:240] if error else None,
                }
                for key, value in values.items():
                    if value is None:
                        self._conn.execute(
                            "DELETE FROM settings WHERE key = ?", (key,)
                        )
                    else:
                        self._conn.execute(
                            "INSERT INTO settings (key, value) VALUES (?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                            (key, value),
                        )
                self._conn.commit()
                return generation
            except Exception:
                self._rollback()
                raise

    def register_owner(self, puuid: str, riot_id: str | None, region_route: str) -> str:
        owner_key = self.owner_key_for_puuid(puuid)
        now = _now_iso()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO owner_namespaces "
                "(owner_key, puuid, last_riot_id, last_region_route, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(owner_key) DO UPDATE SET last_riot_id = excluded.last_riot_id, "
                "last_region_route = excluded.last_region_route, resolved_at = excluded.resolved_at",
                (owner_key, puuid, riot_id, region_route, now, now),
            )
        return owner_key

    def activate_owner(
        self,
        puuid: str,
        riot_id: str | None,
        region_route: str,
        generation: int,
    ) -> str:
        """Activate a resolved namespace iff its transition is still current."""
        owner_key = self.owner_key_for_puuid(puuid)
        now = _now_iso()
        with self._lock:
            self._begin_immediate()
            try:
                if self._current_generation_unlocked() != int(generation):
                    raise StaleOwnerGeneration(
                        f"owner generation {generation} is no longer current"
                    )
                self._conn.execute(
                    "INSERT INTO owner_namespaces "
                    "(owner_key, puuid, last_riot_id, last_region_route, created_at, resolved_at) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(owner_key) DO UPDATE SET last_riot_id = excluded.last_riot_id, "
                    "last_region_route = excluded.last_region_route, resolved_at = excluded.resolved_at",
                    (owner_key, puuid, riot_id, region_route, now, now),
                )
                for key, value in {
                    "owner_key": owner_key,
                    "owner_state": "active",
                    "owner_generation": str(max(0, int(generation))),
                    "owner_ever_activated": "1",
                    "owner_error": None,
                }.items():
                    if value is None:
                        self._conn.execute("DELETE FROM settings WHERE key = ?", (key,))
                    else:
                        self._conn.execute(
                            "INSERT INTO settings (key, value) VALUES (?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                            (key, value),
                        )
                self._conn.commit()
            except Exception:
                self._rollback()
                raise
        return owner_key

    def set_owner_error(self, generation: int, error: str) -> bool:
        """Publish a bounded resolution error only for the current generation."""
        with self._lock, self._conn:
            if self._current_generation_unlocked() != int(generation):
                return False
            bounded = str(error).replace("\n", " ").strip()[:240] or "identity unavailable"
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES ('owner_state', 'error') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES ('owner_generation', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(max(0, int(generation))),),
            )
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES ('owner_error', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (bounded,),
            )
            self._conn.execute("DELETE FROM settings WHERE key = 'owner_key'")
            return True


    def _resolve_owner_key(self, owner_key: str | None) -> str:
        if not isinstance(owner_key, str) or not owner_key.strip():
            raise ValueError("owner key is required for Personal History storage")
        return owner_key.strip()

    def upsert_match(
        self,
        match_id: str,
        played_at: str,
        patch: str,
        role: str,
        champion: str,
        win: bool,
        duration_s: int,
        features_json: str,
        owner_key: str | None = None,
    ) -> None:
        key = self._resolve_owner_key(owner_key)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO matches (owner_key, match_id, played_at, patch, role, champion, win,"
                " duration_s, features_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(owner_key, match_id) DO UPDATE SET played_at = excluded.played_at,"
                " patch = excluded.patch, role = excluded.role, champion = excluded.champion,"
                " win = excluded.win, duration_s = excluded.duration_s,"
                " features_json = excluded.features_json",
                (
                    key,
                    match_id,
                    played_at,
                    patch,
                    role,
                    champion,
                    int(win),
                    duration_s,
                    features_json,
                ),
            )

    def complete_match(
        self,
        match_id: str,
        played_at: str,
        patch: str,
        role: str,
        champion: str,
        win: bool,
        duration_s: int,
        features_json: str,
        owner_key: str | None = None,
    ) -> bool:
        """Persist a complete match and finish its scoped queue row atomically."""
        key = self._resolve_owner_key(owner_key)
        with self._lock:
            self._begin_immediate()
            try:
                queue = self._conn.execute(
                    "SELECT state FROM sync_queue WHERE owner_key = ? AND match_id = ?",
                    (key, match_id),
                ).fetchone()
                if queue is None:
                    raise KeyError(f"unknown queue item {match_id}")
                if queue["state"] == "done":
                    self._conn.commit()
                    return False
                if queue["state"] != "running":
                    raise RuntimeError(
                        f"cannot complete queue item {match_id} in state {queue['state']!r}"
                    )
                self._conn.execute(
                    "INSERT INTO matches (owner_key, match_id, played_at, patch, role, champion, win,"
                    " duration_s, features_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(owner_key, match_id) DO UPDATE SET played_at = excluded.played_at,"
                    " patch = excluded.patch, role = excluded.role, champion = excluded.champion,"
                    " win = excluded.win, duration_s = excluded.duration_s,"
                    " features_json = excluded.features_json",
                    (
                        key,
                        match_id,
                        played_at,
                        patch,
                        role,
                        champion,
                        int(win),
                        duration_s,
                        features_json,
                    ),
                )
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'done' "
                    "WHERE owner_key = ? AND match_id = ? AND state = 'running'",
                    (key, match_id),
                ).rowcount
                if updated != 1:
                    raise RuntimeError(f"queue item {match_id} was not running")
                self._conn.commit()
                return True
            except Exception:
                self._rollback()
                raise

    def all_matches(self, owner_key: str | None = None) -> list[dict]:
        key = self._resolve_owner_key(owner_key)
        with self._lock:
            rows = self._conn.execute(
                "SELECT owner_key, match_id, played_at, patch, role, champion, win, "
                "duration_s, features_json FROM matches WHERE owner_key = ? "
                "ORDER BY played_at, match_id",
                (key,),
            ).fetchall()
        return [dict(r) for r in rows]

    def match_count(self, owner_key: str | None = None) -> int:
        key = self._resolve_owner_key(owner_key)
        with self._lock:
            return int(
                self._conn.execute(
                    "SELECT COUNT(*) c FROM matches WHERE owner_key = ?", (key,)
                ).fetchone()["c"]
            )

    # -- sync queue -----------------------------------------------------
    def enqueue(
        self,
        match_ids: list[str],
        priority: int = 100,
        *,
        owner_key: str | None = None,
        region_route: str = "sea",
    ) -> int:
        key = self._resolve_owner_key(owner_key)
        added = 0
        now = _now_iso()
        with self._lock, self._conn:
            for mid in match_ids:
                known = self._conn.execute(
                    "SELECT 1 FROM matches WHERE owner_key = ? AND match_id = ?",
                    (key, mid),
                ).fetchone()
                if known:
                    continue
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO sync_queue "
                    "(owner_key, match_id, region_route, priority, state, added_at) "
                    "VALUES (?, ?, ?, ?, 'pending', ?)",
                    (key, mid, region_route, priority, now),
                )
                added += cur.rowcount
        return added

    def claim_next_pending(
        self,
        exclude_match_ids: Collection[str] = (),
        *,
        owner_key: str | None = None,
    ) -> dict | None:
        """Atomically claim the highest-priority pending scoped item."""
        key = self._resolve_owner_key(owner_key)
        excluded = tuple(exclude_match_ids)
        with self._lock:
            self._begin_immediate()
            try:
                query = (
                    "SELECT match_id FROM sync_queue "
                    "WHERE owner_key = ? AND state = 'pending'"
                )
                params: tuple[Any, ...] = (key,)
                if excluded:
                    placeholders = ", ".join("?" for _ in excluded)
                    query += f" AND match_id NOT IN ({placeholders})"
                    params += excluded
                query += " ORDER BY priority, match_id LIMIT 1"
                row = self._conn.execute(query, params).fetchone()
                if row is None:
                    self._conn.commit()
                    return None
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'running' "
                    "WHERE owner_key = ? AND match_id = ? AND state = 'pending'",
                    (key, row["match_id"]),
                ).rowcount
                if updated != 1:
                    self._conn.commit()
                    return None
                claimed = self._conn.execute(
                    "SELECT * FROM sync_queue WHERE owner_key = ? AND match_id = ?",
                    (key, row["match_id"]),
                ).fetchone()
                self._conn.commit()
                return dict(claimed)
            except Exception:
                self._rollback()
                raise

    def fail_queue_item(
        self, match_id: str, bump_attempts: bool = True, *, owner_key: str | None = None
    ) -> bool:
        """Transition a claimed scoped item to terminal failure exactly once."""
        key = self._resolve_owner_key(owner_key)
        with self._lock, self._conn:
            if bump_attempts:
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'failed', attempts = attempts + 1 "
                    "WHERE owner_key = ? AND match_id = ? AND state = 'running'",
                    (key, match_id),
                ).rowcount
            else:
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'failed' "
                    "WHERE owner_key = ? AND match_id = ? AND state = 'running'",
                    (key, match_id),
                ).rowcount
        return updated == 1

    def recover_queue_item(
        self, match_id: str, bump_attempts: bool = True, *, owner_key: str | None = None
    ) -> bool:
        """Return a claimed scoped item to pending after a recoverable failure."""
        key = self._resolve_owner_key(owner_key)
        with self._lock, self._conn:
            if bump_attempts:
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'pending', attempts = attempts + 1 "
                    "WHERE owner_key = ? AND match_id = ? AND state = 'running'",
                    (key, match_id),
                ).rowcount
            else:
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'pending' "
                    "WHERE owner_key = ? AND match_id = ? AND state = 'running'",
                    (key, match_id),
                ).rowcount
        return updated == 1

    def reset_running_items(self, owner_key: str | None = None) -> int:
        """Return only one owner's claimed rows to pending."""
        key = self._resolve_owner_key(owner_key)
        with self._lock, self._conn:
            return self._conn.execute(
                "UPDATE sync_queue SET state = 'pending' "
                "WHERE owner_key = ? AND state = 'running'",
                (key,),
            ).rowcount

    def queue_stats(self, owner_key: str | None = None) -> dict:
        key = self._resolve_owner_key(owner_key)
        with self._lock:
            rows = self._conn.execute(
                "SELECT state, COUNT(*) c FROM sync_queue WHERE owner_key = ? GROUP BY state",
                (key,),
            ).fetchall()
        stats = {r["state"]: r["c"] for r in rows}
        return {
            "pending": stats.get("pending", 0),
            "done": stats.get("done", 0),
            "failed": stats.get("failed", 0),
        }


def _now_iso() -> str:
    import time

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

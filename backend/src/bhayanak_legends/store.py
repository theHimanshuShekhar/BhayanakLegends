from collections.abc import Collection
import sqlite3
import threading
from pathlib import Path

_SCHEMA_VERSION = 1
_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matches (
        match_id TEXT PRIMARY KEY,
        played_at TEXT,
        patch TEXT,
        role TEXT,
        champion TEXT,
        win INTEGER,
        duration_s INTEGER,
        features_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_queue (
        match_id TEXT PRIMARY KEY,
        priority INTEGER NOT NULL DEFAULT 100,
        state TEXT NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        added_at TEXT
    )
    """,
)


class Store:
    """Small thread-safe SQLite wrapper for app state and Personal History."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            path, check_same_thread=False, timeout=30.0
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout = 30000")
        self._lock = threading.RLock()
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
        if version > _SCHEMA_VERSION:
            raise RuntimeError(
                f"unsupported database schema version {version}; "
                f"this build supports up to {_SCHEMA_VERSION}"
            )
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                if version == 0:
                    for statement in _SCHEMA_STATEMENTS:
                        self._conn.execute(statement)
                    self._conn.execute(
                        """
                        UPDATE sync_queue
                        SET state = 'pending'
                        WHERE state IN ('running', 'failed')
                           OR (
                               state = 'done'
                               AND NOT EXISTS (
                                   SELECT 1 FROM matches
                                   WHERE matches.match_id = sync_queue.match_id
                               )
                           )
                        """
                    )
                    self._conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _begin_immediate(self) -> None:
        self._conn.execute("BEGIN IMMEDIATE")

    def _rollback(self) -> None:
        if self._conn.in_transaction:
            self._conn.rollback()

    # -- settings -------------------------------------------------------
    def get_setting(self, key: str) -> str | bytes | None:
        return self.get_raw_setting(key)

    def get_raw_setting(self, key: str) -> str | bytes | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row else None

    def has_setting(self, key: str) -> bool:
        with self._lock:
            return (
                self._conn.execute(
                    "SELECT 1 FROM settings WHERE key = ?", (key,)
                ).fetchone()
                is not None
            )

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


    # -- matches --------------------------------------------------------
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
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO matches (match_id, played_at, patch, role, champion, win,"
                " duration_s, features_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(match_id) DO UPDATE SET features_json = excluded.features_json",
                (
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
    ) -> bool:
        """Persist a complete match and mark its claimed queue item done atomically."""
        with self._lock:
            self._begin_immediate()
            try:
                queue = self._conn.execute(
                    "SELECT state FROM sync_queue WHERE match_id = ?", (match_id,)
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
                    "INSERT INTO matches (match_id, played_at, patch, role, champion, win,"
                    " duration_s, features_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(match_id) DO UPDATE SET played_at = excluded.played_at,"
                    " patch = excluded.patch, role = excluded.role, champion = excluded.champion,"
                    " win = excluded.win, duration_s = excluded.duration_s,"
                    " features_json = excluded.features_json",
                    (
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
                    "WHERE match_id = ? AND state = 'running'",
                    (match_id,),
                ).rowcount
                if updated != 1:
                    raise RuntimeError(f"queue item {match_id} was not running")
                self._conn.commit()
                return True
            except Exception:
                self._rollback()
                raise

    def all_matches(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM matches ORDER BY played_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def match_count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"]

    # -- sync queue -----------------------------------------------------
    def enqueue(self, match_ids: list[str], priority: int = 100) -> int:
        added = 0
        now = _now_iso()
        with self._lock, self._conn:
            for mid in match_ids:
                known = self._conn.execute(
                    "SELECT 1 FROM matches WHERE match_id = ?", (mid,)
                ).fetchone()
                if known:
                    continue
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO sync_queue (match_id, priority, state, added_at)"
                    " VALUES (?, ?, 'pending', ?)",
                    (mid, priority, now),
                )
                added += cur.rowcount
        return added

    def claim_next_pending(
        self, exclude_match_ids: Collection[str] = ()
    ) -> dict | None:
        """Atomically claim the highest-priority pending item not excluded."""
        excluded = tuple(exclude_match_ids)
        with self._lock:
            self._begin_immediate()
            try:
                query = "SELECT match_id FROM sync_queue WHERE state = 'pending'"
                params: tuple[str, ...] = ()
                if excluded:
                    placeholders = ", ".join("?" for _ in excluded)
                    query += f" AND match_id NOT IN ({placeholders})"
                    params = excluded
                query += " ORDER BY priority, match_id LIMIT 1"
                row = self._conn.execute(query, params).fetchone()
                if row is None:
                    self._conn.commit()
                    return None
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'running' "
                    "WHERE match_id = ? AND state = 'pending'",
                    (row["match_id"],),
                ).rowcount
                if updated != 1:
                    self._conn.commit()
                    return None
                claimed = self._conn.execute(
                    "SELECT * FROM sync_queue WHERE match_id = ?", (row["match_id"],)
                ).fetchone()
                self._conn.commit()
                return dict(claimed)
            except Exception:
                self._rollback()
                raise

    def fail_queue_item(self, match_id: str, bump_attempts: bool = True) -> bool:
        """Transition a claimed item to terminal failure exactly once."""
        with self._lock, self._conn:
            if bump_attempts:
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'failed', attempts = attempts + 1 "
                    "WHERE match_id = ? AND state = 'running'",
                    (match_id,),
                ).rowcount
            else:
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'failed' "
                    "WHERE match_id = ? AND state = 'running'",
                    (match_id,),
                ).rowcount
        return updated == 1

    def recover_queue_item(self, match_id: str, bump_attempts: bool = True) -> bool:
        """Return a claimed item to pending after a recoverable failure."""
        with self._lock, self._conn:
            if bump_attempts:
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'pending', attempts = attempts + 1 "
                    "WHERE match_id = ? AND state = 'running'",
                    (match_id,),
                ).rowcount
            else:
                updated = self._conn.execute(
                    "UPDATE sync_queue SET state = 'pending' "
                    "WHERE match_id = ? AND state = 'running'",
                    (match_id,),
                ).rowcount
        return updated == 1

    def reset_running_items(self) -> int:
        """Return claimed rows to pending after a restart or run finalization."""
        with self._lock, self._conn:
            return self._conn.execute(
                "UPDATE sync_queue SET state = 'pending' WHERE state = 'running'"
            ).rowcount

    def queue_stats(self) -> dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT state, COUNT(*) c FROM sync_queue GROUP BY state"
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

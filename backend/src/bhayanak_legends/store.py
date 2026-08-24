import json
import sqlite3
import threading
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    played_at TEXT,
    patch TEXT,
    role TEXT,
    champion TEXT,
    win INTEGER,
    duration_s INTEGER,
    features_json TEXT
);
CREATE TABLE IF NOT EXISTS sync_queue (
    match_id TEXT PRIMARY KEY,
    priority INTEGER NOT NULL DEFAULT 100,
    state TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    added_at TEXT
);
"""


class Store:
    """Small thread-safe SQLite wrapper for app state and Personal History."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)

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

    def next_pending(self) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sync_queue WHERE state = 'pending'"
                " ORDER BY priority, match_id LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def mark_queue_item(self, match_id: str, state: str, bump_attempts: bool = False) -> None:
        with self._lock, self._conn:
            if bump_attempts:
                self._conn.execute(
                    "UPDATE sync_queue SET state = ?, attempts = attempts + 1 WHERE match_id = ?",
                    (state, match_id),
                )
            else:
                self._conn.execute(
                    "UPDATE sync_queue SET state = ? WHERE match_id = ?", (state, match_id)
                )

    def reset_running_items(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE sync_queue SET state = 'pending' WHERE state = 'running'")

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

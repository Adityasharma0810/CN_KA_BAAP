"""Offline observation buffer.

When the cloud control plane is unavailable, observations are persisted locally
and replayed once connectivity is restored. This keeps the data plane
operational offline.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

MAX_BUFFER_ENTRIES = 100_000


class OfflineBuffer:
    """Append-only SQLite buffer for observations collected while offline."""

    def __init__(self, path: str) -> None:
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gateway_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload TEXT NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_buffer_gateway_sent ON buffer(gateway_id, sent)"
        )
        self._conn.commit()

    def add(self, gateway_id: str, observations: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps({"timestamp": now, "observations": observations})
        with self._lock:
            self._conn.execute(
                "INSERT INTO buffer (gateway_id, timestamp, payload, sent) VALUES (?, ?, ?, 0)",
                (gateway_id, now, payload),
            )
            # Bound the buffer size.
            self._conn.execute(
                "DELETE FROM buffer WHERE id IN ("
                "SELECT id FROM buffer WHERE sent=0 ORDER BY id DESC LIMIT -1 OFFSET ?"
                ")",
                (MAX_BUFFER_ENTRIES,),
            )
            self._conn.commit()

    def unsent(self, gateway_id: str, limit: int = 500) -> list[tuple[int, str]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, payload FROM buffer WHERE gateway_id=? AND sent=0 ORDER BY id ASC LIMIT ?",
                (gateway_id, limit),
            )
            return list(cur.fetchall())

    def mark_sent(self, ids: list[int]) -> None:
        if not ids:
            return
        with self._lock:
            self._conn.executemany("UPDATE buffer SET sent=1 WHERE id=?", [(i,) for i in ids])
            self._conn.commit()

    def count_unsent(self, gateway_id: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "SELECT COUNT(*) FROM buffer WHERE gateway_id=? AND sent=0", (gateway_id,)
            )
            return cur.fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

"""Optional SQLite persistence for the demo, one row per shop.

Off by default (the demo keeps state in memory). Set `ASK_FIRST_DB=/path/shop.sqlite` (and
optionally `ASK_FIRST_SHOP=<id>`) and a restart keeps: the conversations and bookings, the
mandates the agent asked for, the owner's signed approvals, the set of mandates already USED
(so a restart can never reopen a replay), the declines, the paired owner key, the fake
provider's orders and holds, and the PayPal webhook event ids already handled (so a redelivery
after a restart is still a duplicate). The hash-chained ledger stays a JSON-lines file; with a
store it lives next to the database.

One database file can hold many shops (`shop_id`); one demo process serves one of them.
Standard library only (`sqlite3`).
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  shop_id TEXT PRIMARY KEY,
  data    TEXT NOT NULL,
  updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS webhook_events (
  shop_id    TEXT NOT NULL,
  event_id   TEXT NOT NULL,
  event_type TEXT NOT NULL,
  outcome    TEXT NOT NULL,
  received   REAL NOT NULL,
  PRIMARY KEY (shop_id, event_id)
);
"""


class SqliteStore:
    def __init__(self, path: str | Path, shop_id: str = "default") -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(shop_id)):
            raise ValueError("shop_id: 1-64 letters, digits, '_' or '-'")   # it also names the ledger file
        self.path, self.shop_id = str(path), str(shop_id)
        self._lock = threading.Lock()
        with self._connect() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        """One short connection per operation: committed on success, rolled back on error,
        always closed (safe across uvicorn's threads)."""
        c = sqlite3.connect(self.path, timeout=10)
        try:
            with c:
                yield c
        finally:
            c.close()

    @property
    def ledger_path(self) -> str:
        return f"{self.path}.{self.shop_id}.ledger.jsonl"

    def load(self) -> dict | None:
        with self._lock, self._connect() as c:
            row = c.execute("SELECT data FROM snapshots WHERE shop_id = ?", (self.shop_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, snapshot: dict) -> None:
        data = json.dumps(snapshot, separators=(",", ":"))
        with self._lock, self._connect() as c:
            c.execute("INSERT INTO snapshots (shop_id, data, updated) VALUES (?, ?, ?) "
                      "ON CONFLICT(shop_id) DO UPDATE SET data = excluded.data, updated = excluded.updated",
                      (self.shop_id, data, time.time()))

    def seen_event(self, event_id: str) -> bool:
        with self._lock, self._connect() as c:
            return c.execute("SELECT 1 FROM webhook_events WHERE shop_id = ? AND event_id = ?",
                             (self.shop_id, event_id)).fetchone() is not None

    def remember_event(self, event_id: str, event_type: str, outcome: str) -> None:
        with self._lock, self._connect() as c:
            c.execute("INSERT OR IGNORE INTO webhook_events VALUES (?, ?, ?, ?, ?)",
                      (self.shop_id, event_id, event_type, str(outcome), time.time()))

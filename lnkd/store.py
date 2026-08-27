"""
store.py — durable local state (SQLite).

Two jobs:
  1. Action log — every LinkedIn touch is recorded here. safety.Guard reads
     this to enforce daily/weekly caps that survive restarts.
  2. Outbox / dedup — so you never re-invite or re-message the same person,
     even across sessions.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo


SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,            -- ISO8601 UTC
    action  TEXT NOT NULL,
    target  TEXT,                     -- profile urn / public id
    ok      INTEGER NOT NULL DEFAULT 1,
    note    TEXT
);
CREATE INDEX IF NOT EXISTS idx_actions_action_ts ON actions(action, ts);

CREATE TABLE IF NOT EXISTS contacted (
    target   TEXT NOT NULL,
    action   TEXT NOT NULL,
    ts       TEXT NOT NULL,
    PRIMARY KEY (target, action)
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        self.db.commit()

    @staticmethod
    def _utc_now() -> dt.datetime:
        return dt.datetime.now(ZoneInfo("UTC"))

    def log_action(self, action: str, target: str = "", ok: bool = True,
                   note: str = "") -> None:
        self.db.execute(
            "INSERT INTO actions (ts, action, target, ok, note) VALUES (?,?,?,?,?)",
            (self._utc_now().isoformat(), action, target, int(ok), note),
        )
        self.db.commit()

    def count_since(self, action: str, since: dt.datetime) -> int:
        since_utc = since.astimezone(ZoneInfo("UTC")).isoformat()
        row = self.db.execute(
            "SELECT COUNT(*) FROM actions WHERE action=? AND ok=1 AND ts>=?",
            (action, since_utc),
        ).fetchone()
        return row[0] if row else 0

    def last_action_time(self, action: str):
        row = self.db.execute(
            "SELECT ts FROM actions WHERE action=? ORDER BY ts DESC LIMIT 1",
            (action,),
        ).fetchone()
        if not row:
            return None
        return dt.datetime.fromisoformat(row[0])

    def already_contacted(self, target: str, action: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM contacted WHERE target=? AND action=?",
            (target, action),
        ).fetchone()
        return row is not None

    def mark_contacted(self, target: str, action: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO contacted (target, action, ts) VALUES (?,?,?)",
            (target, action, self._utc_now().isoformat()),
        )
        self.db.commit()

    def recent(self, limit: int = 25):
        return self.db.execute(
            "SELECT ts, action, target, ok, note FROM actions "
            "ORDER BY id DESC LIMIT ?", (limit,),
        ).fetchall()

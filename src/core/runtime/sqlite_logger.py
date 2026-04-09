from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from pathlib import Path
from typing import Any

from .messages import Message


class SQLiteEventLogger:
    """Append-only event ledger for successful runtime dispatches."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    def ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self._db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dispatch_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    target TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    dispatched_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def log_dispatch(self, message: Message, response: dict[str, Any]) -> None:
        self.ensure_schema()
        with closing(sqlite3.connect(self._db_path)) as connection:
            connection.execute(
                """
                INSERT INTO dispatch_events (
                    sender,
                    target,
                    action,
                    payload_json,
                    response_json,
                    dispatched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.sender,
                    message.target,
                    message.action,
                    json.dumps(message.payload, sort_keys=True),
                    json.dumps(response, sort_keys=True),
                    message.timestamp.isoformat(),
                ),
            )
            connection.commit()

    def event_count(self) -> int:
        self.ensure_schema()
        with closing(sqlite3.connect(self._db_path)) as connection:
            row = connection.execute("SELECT COUNT(*) FROM dispatch_events").fetchone()
        return int(row[0]) if row else 0

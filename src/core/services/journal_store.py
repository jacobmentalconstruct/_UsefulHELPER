from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4


VALID_TASK_STATUSES = {"pending", "in_progress", "completed"}


@dataclass(frozen=True, slots=True)
class TaskItem:
    text: str
    status: str


class JournalStore:
    """SQLite-backed builder-memory surface with markdown mirrors."""

    def __init__(
        self,
        db_path: Path,
        entries_dir: Path,
        backlog_path: Path,
        tasklist_path: Path,
    ) -> None:
        self._db_path = db_path
        self._entries_dir = entries_dir
        self._backlog_path = backlog_path
        self._tasklist_path = tasklist_path

    def ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries_dir.mkdir(parents=True, exist_ok=True)
        self._backlog_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._backlog_path.exists():
            self._backlog_path.write_text("# Backlog\n\n", encoding="utf-8")
        if not self._tasklist_path.exists():
            self._tasklist_path.write_text("# Current Tasklist\n\n", encoding="utf-8")

        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS journal_entries (
                    entry_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    files_changed_json TEXT NOT NULL,
                    notes_json TEXT NOT NULL,
                    testing_json TEXT NOT NULL,
                    backlog_json TEXT NOT NULL,
                    mirror_path TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasklist_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def append_entry(
        self,
        title: str,
        summary: str,
        files_changed: list[str],
        notes: list[str],
        testing: list[str],
        backlog: list[str],
    ) -> dict[str, str]:
        self.ensure_schema()
        timestamp = datetime.now().astimezone()
        entry_id = f"{timestamp.strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        mirror_name = f"{timestamp.strftime('%Y-%m-%d_%H%M%S')}_{entry_id}.md"
        mirror_path = self._entries_dir / mirror_name

        mirror_content = self._render_entry_markdown(
            entry_id=entry_id,
            created_at=timestamp.isoformat(),
            title=title,
            summary=summary,
            files_changed=files_changed,
            notes=notes,
            testing=testing,
            backlog=backlog,
        )
        mirror_path.write_text(mirror_content, encoding="utf-8")

        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO journal_entries (
                    entry_id,
                    created_at,
                    title,
                    summary,
                    files_changed_json,
                    notes_json,
                    testing_json,
                    backlog_json,
                    mirror_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    timestamp.isoformat(),
                    title,
                    summary,
                    json.dumps(files_changed),
                    json.dumps(notes),
                    json.dumps(testing),
                    json.dumps(backlog),
                    str(mirror_path),
                ),
            )

        if backlog:
            with self._backlog_path.open("a", encoding="utf-8") as handle:
                handle.write(f"\n## {timestamp.isoformat()} | {title}\n\n")
                for item in backlog:
                    handle.write(f"- {item}\n")

        return {
            "entry_id": entry_id,
            "created_at": timestamp.isoformat(),
            "mirror_path": str(mirror_path),
        }

    def replace_tasklist(self, items: list[TaskItem]) -> dict[str, object]:
        self.ensure_schema()
        in_progress_count = sum(1 for item in items if item.status == "in_progress")
        if in_progress_count > 1:
            raise ValueError("At most one tasklist item may be marked in_progress.")

        for item in items:
            if item.status not in VALID_TASK_STATUSES:
                raise ValueError(f"Unsupported task status '{item.status}'.")

        updated_at = datetime.now().astimezone().isoformat()

        with sqlite3.connect(self._db_path) as connection:
            connection.execute("DELETE FROM tasklist_items")
            for position, item in enumerate(items, start=1):
                connection.execute(
                    """
                    INSERT INTO tasklist_items (position, text, status, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (position, item.text, item.status, updated_at),
                )

        self._tasklist_path.write_text(
            self._render_tasklist_markdown(items, updated_at),
            encoding="utf-8",
        )

        return {
            "updated_at": updated_at,
            "item_count": len(items),
            "mirror_path": str(self._tasklist_path),
        }

    def read_tasklist(self) -> dict[str, object]:
        self.ensure_schema()
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT position, text, status, updated_at
                FROM tasklist_items
                ORDER BY position ASC
                """
            ).fetchall()

        items = [
            {
                "position": row[0],
                "text": row[1],
                "status": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]
        return {
            "items": items,
            "item_count": len(items),
            "mirror_path": str(self._tasklist_path),
        }

    def _render_entry_markdown(
        self,
        entry_id: str,
        created_at: str,
        title: str,
        summary: str,
        files_changed: list[str],
        notes: list[str],
        testing: list[str],
        backlog: list[str],
    ) -> str:
        lines = [
            f"# Journal Entry: {created_at} | ID {entry_id}",
            "",
            f"## Title",
            "",
            title,
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Files Changed",
            "",
        ]

        lines.extend(f"- {path}" for path in files_changed or ["(none recorded)"])
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {item}" for item in notes or ["(none)"])
        lines.extend(["", "## Testing", ""])
        lines.extend(f"- {item}" for item in testing or ["(not recorded)"])
        lines.extend(["", "## Backlog", ""])
        lines.extend(f"- {item}" for item in backlog or ["(none)"])
        lines.append("")
        return "\n".join(lines)

    def _render_tasklist_markdown(self, items: list[TaskItem], updated_at: str) -> str:
        lines = [
            "# Current Tasklist",
            "",
            f"Updated: {updated_at}",
            "",
        ]
        if not items:
            lines.append("- No active items.")
        else:
            for item in items:
                lines.append(f"- [{item.status}] {item.text}")
        lines.append("")
        return "\n".join(lines)

from __future__ import annotations

from ..services.journal_store import JournalStore, TaskItem


class BuilderMemoryComponent:
    """Owns builder-memory tasklist and journal operations."""

    def __init__(self, journal_store: JournalStore) -> None:
        self._journal_store = journal_store

    def append_journal(
        self,
        title: str,
        summary: str,
        files_changed: list[str],
        notes: list[str],
        testing: list[str],
        backlog: list[str],
    ) -> dict[str, str]:
        return self._journal_store.append_entry(
            title=title,
            summary=summary,
            files_changed=files_changed,
            notes=notes,
            testing=testing,
            backlog=backlog,
        )

    def replace_tasklist(self, items: list[dict[str, str]]) -> dict[str, object]:
        parsed_items = [
            TaskItem(
                text=item["text"],
                status=item["status"],
            )
            for item in items
        ]
        return self._journal_store.replace_tasklist(parsed_items)

    def view_tasklist(self) -> dict[str, object]:
        return self._journal_store.read_tasklist()

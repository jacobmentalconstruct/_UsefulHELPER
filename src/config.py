from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Central configuration for the UsefulHELPER worker."""

    project_root: Path
    workspace_root: Path
    source_root: Path
    server_name: str = "usefulhelper-worker"
    server_version: str = "0.1.0"
    runtime_db_name: str = "runtime_events.sqlite3"
    journal_db_name: str = "app_journal.sqlite3"

    @property
    def runtime_data_dir(self) -> Path:
        return self.project_root / "data" / "runtime"

    @property
    def runtime_db_path(self) -> Path:
        return self.runtime_data_dir / self.runtime_db_name

    @property
    def sandbox_data_dir(self) -> Path:
        return self.project_root / "data" / "sandbox"

    @property
    def sandbox_db_path(self) -> Path:
        return self.sandbox_data_dir / "project_sandbox.sqlite3"

    @property
    def parts_data_dir(self) -> Path:
        return self.project_root / "data" / "parts"

    @property
    def parts_db_path(self) -> Path:
        return self.parts_data_dir / "parts_catalog.sqlite3"

    @property
    def journal_dir(self) -> Path:
        return self.project_root / "_docs" / "_AppJOURNAL"

    @property
    def journal_entries_dir(self) -> Path:
        return self.journal_dir / "entries"

    @property
    def journal_backlog_path(self) -> Path:
        return self.journal_dir / "BACKLOG.md"

    @property
    def journal_tasklist_path(self) -> Path:
        return self.journal_dir / "CURRENT_TASKLIST.md"

    @property
    def journal_db_path(self) -> Path:
        return self.project_root / "_docs" / "_journalDB" / self.journal_db_name

    @property
    def log_dir(self) -> Path:
        return self.project_root / "logs"

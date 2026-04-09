from __future__ import annotations

from pathlib import Path

from ..managers.ui_manager import UiManager


class UiOrchestrator:
    """UI-side coordination entry point."""

    def __init__(self, manager: UiManager | None = None) -> None:
        self._manager = manager or UiManager()

    def present_startup_banner(
        self,
        server_name: str,
        server_version: str,
        workspace_root: Path,
        transport_mode: str,
    ) -> str:
        return self._manager.render_startup_banner(
            server_name=server_name,
            server_version=server_version,
            workspace_root=workspace_root,
            transport_mode=transport_mode,
        )

    def present_monitor(
        self,
        *,
        server_name: str,
        server_version: str,
        project_root: Path,
        workspace_root: Path,
        runtime_db_path: Path,
        log_path: Path,
    ) -> int:
        return self._manager.run_monitor(
            server_name=server_name,
            server_version=server_version,
            project_root=project_root,
            workspace_root=workspace_root,
            runtime_db_path=runtime_db_path,
            log_path=log_path,
        )

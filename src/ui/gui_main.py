from __future__ import annotations

from pathlib import Path

from .orchestrators.ui_orchestrator import UiOrchestrator


class GuiMain:
    """Minimal headless UI shell."""

    def __init__(self) -> None:
        self._orchestrator = UiOrchestrator()

    def render_startup_banner(
        self,
        server_name: str,
        server_version: str,
        workspace_root: Path,
        transport_mode: str,
    ) -> str:
        return self._orchestrator.present_startup_banner(
            server_name=server_name,
            server_version=server_version,
            workspace_root=workspace_root,
            transport_mode=transport_mode,
        )

    def run_monitor(
        self,
        *,
        server_name: str,
        server_version: str,
        project_root: Path,
        workspace_root: Path,
        runtime_db_path: Path,
        log_path: Path,
    ) -> int:
        return self._orchestrator.present_monitor(
            server_name=server_name,
            server_version=server_version,
            project_root=project_root,
            workspace_root=workspace_root,
            runtime_db_path=runtime_db_path,
            log_path=log_path,
        )

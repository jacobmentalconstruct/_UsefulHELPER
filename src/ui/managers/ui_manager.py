from __future__ import annotations

from pathlib import Path

from ...core.services.ollama_service import OllamaService
from ..adapters.runtime_monitor_adapter import RuntimeMonitorAdapter
from ..components.monitor_window import MonitorWindow
from ..components.status_panel import StatusPanel, StatusPanelModel
from ..helpers.monitor_helper_service import MonitorHelperService
from ..helpers.monitor_settings_store import MonitorSettingsStore


class UiManager:
    """Coordinates UI-only presentation behavior."""

    def __init__(
        self,
        status_panel: StatusPanel | None = None,
        monitor_window: MonitorWindow | None = None,
    ) -> None:
        self._status_panel = status_panel or StatusPanel()
        self._monitor_window = monitor_window

    def render_startup_banner(
        self,
        server_name: str,
        server_version: str,
        workspace_root: Path,
        transport_mode: str,
    ) -> str:
        model = StatusPanelModel(
            title=f"{server_name} {server_version}",
            body=(
                f"transport={transport_mode}\n"
                f"workspace_root={workspace_root}"
            ),
            footer="Worker ready for MCP-style requests.",
        )
        return self._status_panel.render(model)

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
        adapter = RuntimeMonitorAdapter(runtime_db_path, log_path)
        settings_store = MonitorSettingsStore(runtime_db_path.parent / "monitor_settings.json")
        monitor_window = self._monitor_window or MonitorWindow(
            helper_service=MonitorHelperService(OllamaService()),
            settings_store=settings_store,
        )
        return monitor_window.run(
            title=f"{server_name} {server_version} Monitor",
            snapshot_provider=adapter.fetch_snapshot,
        )

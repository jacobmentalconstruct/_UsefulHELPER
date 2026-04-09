from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .app_state import AppState
from .config import AppConfig
from .core.engine import ApplicationEngine
from .logging_config import configure_logging
from .ui.gui_main import GuiMain


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Application:
    """Composition root for the worker process."""

    config: AppConfig
    state: AppState
    engine: ApplicationEngine
    gui: GuiMain

    def run(self, transport_mode: str, ui_mode: str = "headless") -> int:
        if ui_mode == "monitor":
            self.engine.event_logger.ensure_schema()
            self.state.lifecycle_state = "monitoring"
            return self.gui.run_monitor(
                server_name=self.config.server_name,
                server_version=self.config.server_version,
                project_root=self.config.project_root,
                workspace_root=self.config.workspace_root,
                runtime_db_path=self.config.runtime_db_path,
                log_path=self.config.log_dir / "app.log",
            )

        self.state.lifecycle_state = "starting"
        self.engine.start()

        status_text = self.gui.render_startup_banner(
            server_name=self.config.server_name,
            server_version=self.config.server_version,
            workspace_root=self.config.workspace_root,
            transport_mode=transport_mode,
        )
        LOGGER.info("%s", status_text)

        self.state.lifecycle_state = "running"
        self.state.active_transport = transport_mode
        request_count = self.engine.serve(
            stdin_stream=sys.stdin.buffer,
            stdout_stream=sys.stdout.buffer,
            transport_mode=transport_mode,
        )
        self.state.request_count = request_count
        self.state.lifecycle_state = "stopped"
        return 0


def build_application(
    project_root: Path | None = None,
    workspace_root: Path | None = None,
) -> Application:
    """Build the application object graph."""

    resolved_project_root = project_root or Path(__file__).resolve().parents[1]
    resolved_workspace_root = workspace_root or resolved_project_root
    resolved_source_root = Path(__file__).resolve().parents[1]
    config = AppConfig(
        project_root=resolved_project_root,
        workspace_root=resolved_workspace_root,
        source_root=resolved_source_root,
    )
    configure_logging(config.log_dir)
    state = AppState(boot_id=uuid4().hex)
    engine = ApplicationEngine(config)
    gui = GuiMain()
    return Application(config=config, state=state, engine=engine, gui=gui)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="Run the UsefulHELPER worker.")
    parser.add_argument(
        "--transport",
        choices=("auto", "ndjson", "content-length"),
        default="auto",
        help="Transport framing mode for stdin/stdout.",
    )
    parser.add_argument(
        "--ui",
        choices=("headless", "monitor"),
        default="headless",
        help="UI mode. 'monitor' opens the operator monitor over the worker runtime DB and log.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Override the worker project root.",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=None,
        help="Override the target workspace root that tools may touch.",
    )
    args = parser.parse_args(argv)

    application = build_application(
        project_root=args.project_root,
        workspace_root=args.workspace_root,
    )
    return application.run(transport_mode=args.transport, ui_mode=args.ui)


if __name__ == "__main__":
    raise SystemExit(main())

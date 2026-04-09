from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .root_guard import RootGuard


class PythonRuntimeService:
    """Runs tightly allowlisted Python helper commands inside the workspace root."""

    def __init__(self, root_guard: RootGuard) -> None:
        self._root_guard = root_guard

    def run_unittest(
        self,
        start_dir: str,
        pattern: str,
        top_level_dir: str | None,
        timeout_seconds: int,
    ) -> dict[str, object]:
        start_path = self._root_guard.resolve_path(start_dir)
        command = [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            self._root_guard.relative_path(start_path),
            "-p",
            pattern,
        ]
        if top_level_dir is not None:
            top_level_path = self._root_guard.resolve_path(top_level_dir)
            command.extend(["-t", self._root_guard.relative_path(top_level_path)])

        return self._run_command(
            command=command,
            timeout_seconds=timeout_seconds,
            command_name="python.run_unittest",
        )

    def run_compileall(
        self,
        paths: list[str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        relative_paths = [
            self._root_guard.relative_path(self._root_guard.resolve_path(path))
            for path in paths
        ]
        command = [sys.executable, "-m", "compileall", *relative_paths]
        return self._run_command(
            command=command,
            timeout_seconds=timeout_seconds,
            command_name="python.run_compileall",
        )

    def _run_command(
        self,
        command: list[str],
        timeout_seconds: int,
        command_name: str,
    ) -> dict[str, object]:
        result = subprocess.run(
            command,
            cwd=self._root_guard.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "command_name": command_name,
            "command": command,
            "cwd": str(self._root_guard.workspace_root),
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "succeeded": result.returncode == 0,
        }

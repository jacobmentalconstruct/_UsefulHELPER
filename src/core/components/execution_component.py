from __future__ import annotations

from ..services.python_runtime_service import PythonRuntimeService
from ..services.sysops_service import SysopsService


class ExecutionComponent:
    """Owns bounded allowlisted Python execution helpers."""

    def __init__(
        self,
        python_runtime_service: PythonRuntimeService,
        sysops_service: SysopsService,
    ) -> None:
        self._python_runtime_service = python_runtime_service
        self._sysops_service = sysops_service

    def run_unittest(
        self,
        start_dir: str = ".",
        pattern: str = "test*.py",
        top_level_dir: str | None = None,
        timeout_seconds: int = 120,
    ) -> dict[str, object]:
        return self._python_runtime_service.run_unittest(
            start_dir=start_dir,
            pattern=pattern,
            top_level_dir=top_level_dir,
            timeout_seconds=timeout_seconds,
        )

    def run_compileall(
        self,
        paths: list[str] | None = None,
        timeout_seconds: int = 120,
    ) -> dict[str, object]:
        return self._python_runtime_service.run_compileall(
            paths=paths or ["."],
            timeout_seconds=timeout_seconds,
        )

    def git_status(
        self,
        path: str = ".",
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        return self._sysops_service.git_status(
            path=path,
            timeout_seconds=timeout_seconds,
        )

    def git_diff_summary(
        self,
        path: str = ".",
        cached: bool = False,
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        return self._sysops_service.git_diff_summary(
            path=path,
            cached=cached,
            timeout_seconds=timeout_seconds,
        )

    def git_repo_summary(
        self,
        path: str = ".",
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        return self._sysops_service.git_repo_summary(
            path=path,
            timeout_seconds=timeout_seconds,
        )

    def git_recent_commits(
        self,
        path: str = ".",
        limit: int = 10,
        ref: str = "HEAD",
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        return self._sysops_service.git_recent_commits(
            path=path,
            limit=limit,
            ref=ref,
            timeout_seconds=timeout_seconds,
        )

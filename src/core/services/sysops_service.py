from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .root_guard import RootGuard


class SysopsService:
    """Runs tightly allowlisted read-only sysops helpers inside the workspace root."""

    def __init__(self, root_guard: RootGuard) -> None:
        self._root_guard = root_guard

    def git_status(
        self,
        path: str = ".",
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        repo_path = self._root_guard.resolve_path(path)
        if not self._git_available():
            return self._unavailable_result("sysops.git_status", repo_path, "git executable not found")

        repo_info = self._git_repo_info(repo_path, timeout_seconds)
        if not repo_info["repo_detected"]:
            return {
                "command_name": "sysops.git_status",
                "cwd": str(self._root_guard.workspace_root),
                "requested_path": self._root_guard.relative_path(repo_path),
                **repo_info,
                "command": [],
                "stdout": "",
                "stderr": repo_info["stderr"],
                "succeeded": False,
            }

        command = ["git", "-C", str(repo_path), "status", "--short", "--branch"]
        result = subprocess.run(
            command,
            cwd=self._root_guard.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "command_name": "sysops.git_status",
            "command": command,
            "cwd": str(self._root_guard.workspace_root),
            "requested_path": self._root_guard.relative_path(repo_path),
            **repo_info,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "succeeded": result.returncode == 0,
        }

    def git_diff_summary(
        self,
        path: str = ".",
        cached: bool = False,
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        repo_path = self._root_guard.resolve_path(path)
        if not self._git_available():
            return self._unavailable_result(
                "sysops.git_diff_summary",
                repo_path,
                "git executable not found",
            )

        repo_info = self._git_repo_info(repo_path, timeout_seconds)
        if not repo_info["repo_detected"]:
            return {
                "command_name": "sysops.git_diff_summary",
                "cwd": str(self._root_guard.workspace_root),
                "requested_path": self._root_guard.relative_path(repo_path),
                "cached": cached,
                **repo_info,
                "command": [],
                "stdout": "",
                "stderr": repo_info["stderr"],
                "succeeded": False,
            }

        command = ["git", "-C", str(repo_path), "diff", "--stat"]
        if cached:
            command.append("--cached")
        result = subprocess.run(
            command,
            cwd=self._root_guard.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        name_only_command = ["git", "-C", str(repo_path), "diff", "--name-only"]
        if cached:
            name_only_command.append("--cached")
        name_only_result = subprocess.run(
            name_only_command,
            cwd=self._root_guard.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        changed_files = [
            line.strip()
            for line in name_only_result.stdout.splitlines()
            if line.strip()
        ]
        return {
            "command_name": "sysops.git_diff_summary",
            "command": command,
            "cwd": str(self._root_guard.workspace_root),
            "requested_path": self._root_guard.relative_path(repo_path),
            "cached": cached,
            **repo_info,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "changed_files": changed_files,
            "succeeded": result.returncode == 0 and name_only_result.returncode == 0,
        }

    def git_repo_summary(
        self,
        path: str = ".",
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        repo_path = self._root_guard.resolve_path(path)
        if not self._git_available():
            return self._unavailable_result(
                "sysops.git_repo_summary",
                repo_path,
                "git executable not found",
            )

        repo_info = self._git_repo_info(repo_path, timeout_seconds)
        if not repo_info["repo_detected"]:
            return {
                "command_name": "sysops.git_repo_summary",
                "cwd": str(self._root_guard.workspace_root),
                "requested_path": self._root_guard.relative_path(repo_path),
                **repo_info,
                "command": [],
                "stdout": "",
                "stderr": repo_info["stderr"],
                "succeeded": False,
            }

        branch_result = self._run_git(
            repo_path,
            ["rev-parse", "--abbrev-ref", "HEAD"],
            timeout_seconds,
        )
        head_result = self._run_git(
            repo_path,
            ["log", "-1", "--format=%H%n%h%n%s%n%an%n%aI"],
            timeout_seconds,
        )
        status_result = self._run_git(
            repo_path,
            ["status", "--short"],
            timeout_seconds,
        )

        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None
        head_lines = [line.strip() for line in head_result.stdout.splitlines()]
        dirty_paths = [line.strip() for line in status_result.stdout.splitlines() if line.strip()]
        succeeded = (
            branch_result.returncode == 0
            and head_result.returncode == 0
            and status_result.returncode == 0
        )
        return {
            "command_name": "sysops.git_repo_summary",
            "command": ["git", "-C", str(repo_path), "rev-parse/log/status"],
            "cwd": str(self._root_guard.workspace_root),
            "requested_path": self._root_guard.relative_path(repo_path),
            **repo_info,
            "branch": branch,
            "head_commit": head_lines[0] if len(head_lines) >= 1 else None,
            "head_short_commit": head_lines[1] if len(head_lines) >= 2 else None,
            "head_subject": head_lines[2] if len(head_lines) >= 3 else None,
            "head_author": head_lines[3] if len(head_lines) >= 4 else None,
            "head_author_date": head_lines[4] if len(head_lines) >= 5 else None,
            "dirty_file_count": len(dirty_paths),
            "dirty_paths": dirty_paths,
            "stdout": "\n".join(filter(None, [branch_result.stdout, head_result.stdout, status_result.stdout])),
            "stderr": "".join([branch_result.stderr, head_result.stderr, status_result.stderr]),
            "succeeded": succeeded,
        }

    def git_recent_commits(
        self,
        path: str = ".",
        limit: int = 10,
        ref: str = "HEAD",
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        if limit < 1:
            raise ValueError("limit must be at least 1.")

        repo_path = self._root_guard.resolve_path(path)
        if not self._git_available():
            return self._unavailable_result(
                "sysops.git_recent_commits",
                repo_path,
                "git executable not found",
            )

        repo_info = self._git_repo_info(repo_path, timeout_seconds)
        if not repo_info["repo_detected"]:
            return {
                "command_name": "sysops.git_recent_commits",
                "cwd": str(self._root_guard.workspace_root),
                "requested_path": self._root_guard.relative_path(repo_path),
                "limit": limit,
                "ref": ref,
                **repo_info,
                "command": [],
                "stdout": "",
                "stderr": repo_info["stderr"],
                "commits": [],
                "commit_count": 0,
                "succeeded": False,
            }

        format_string = "%H%x1f%h%x1f%s%x1f%an%x1f%aI"
        result = self._run_git(
            repo_path,
            ["log", f"-n{limit}", f"--format={format_string}", ref],
            timeout_seconds,
        )
        commits: list[dict[str, object]] = []
        for line in result.stdout.splitlines():
            parts = line.split("\x1f")
            if len(parts) != 5:
                continue
            commits.append(
                {
                    "commit": parts[0],
                    "short_commit": parts[1],
                    "subject": parts[2],
                    "author": parts[3],
                    "author_date": parts[4],
                }
            )

        return {
            "command_name": "sysops.git_recent_commits",
            "command": ["git", "-C", str(repo_path), "log", f"-n{limit}", ref],
            "cwd": str(self._root_guard.workspace_root),
            "requested_path": self._root_guard.relative_path(repo_path),
            "limit": limit,
            "ref": ref,
            **repo_info,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "commits": commits,
            "commit_count": len(commits),
            "succeeded": result.returncode == 0,
        }

    def _git_available(self) -> bool:
        return shutil.which("git") is not None

    def _git_repo_info(self, repo_path: Path, timeout_seconds: int) -> dict[str, object]:
        result = self._run_git(repo_path, ["rev-parse", "--show-toplevel"], timeout_seconds)
        if result.returncode != 0:
            return {
                "git_available": True,
                "repo_detected": False,
                "repo_root": None,
                "stderr": result.stderr,
            }

        repo_root_path = Path(result.stdout.strip()).resolve()
        repo_root_relative = None
        try:
            repo_root_relative = self._root_guard.relative_path(repo_root_path)
        except ValueError:
            repo_root_relative = str(repo_root_path)
        return {
            "git_available": True,
            "repo_detected": True,
            "repo_root": repo_root_relative,
            "stderr": result.stderr,
        }

    def _unavailable_result(
        self,
        command_name: str,
        repo_path: Path,
        reason: str,
    ) -> dict[str, object]:
        return {
            "command_name": command_name,
            "command": [],
            "cwd": str(self._root_guard.workspace_root),
            "requested_path": self._root_guard.relative_path(repo_path),
            "git_available": False,
            "repo_detected": False,
            "repo_root": None,
            "stdout": "",
            "stderr": reason,
            "succeeded": False,
        }

    def _run_git(
        self,
        repo_path: Path,
        args: list[str],
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo_path), *args],
            cwd=self._root_guard.workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

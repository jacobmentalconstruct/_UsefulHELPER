from __future__ import annotations

from pathlib import Path


class RootGuard:
    """Confines file effects to one explicit workspace root."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, raw_path: str) -> Path:
        if not raw_path:
            raise ValueError("Path values must not be empty.")

        candidate = Path(raw_path)
        if candidate.is_absolute():
            raise ValueError(
                "Absolute paths are not accepted. All tool paths must be relative to the session workspace root."
            )

        resolved = (self.workspace_root / candidate).resolve()

        try:
            resolved.relative_to(self.workspace_root)
        except ValueError as error:
            raise ValueError(
                f"Path '{raw_path}' resolves outside the workspace root '{self.workspace_root}'."
            ) from error

        return resolved

    def relative_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.workspace_root).as_posix()

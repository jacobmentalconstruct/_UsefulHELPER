from __future__ import annotations

import re
from pathlib import Path

from ..services.root_guard import RootGuard


class FilesystemComponent:
    """Owns bounded workspace filesystem operations."""

    def __init__(self, root_guard: RootGuard) -> None:
        self._root_guard = root_guard

    def list_tree(
        self,
        path: str = ".",
        max_depth: int = 4,
    ) -> dict[str, object]:
        target = self._root_guard.resolve_path(path)
        if not target.exists():
            raise FileNotFoundError(f"Path '{path}' does not exist.")

        entries: list[dict[str, object]] = []
        base_depth = len(target.parts)

        def walk(current: Path) -> None:
            depth = len(current.parts) - base_depth
            if depth > max_depth:
                return

            if current != target:
                entries.append(
                    {
                        "path": self._root_guard.relative_path(current),
                        "type": "directory" if current.is_dir() else "file",
                    }
                )

            if current.is_dir() and depth < max_depth:
                for child in sorted(current.iterdir(), key=lambda item: item.name.lower()):
                    walk(child)

        walk(target)
        return {
            "root": self._root_guard.relative_path(target)
            if target != self._root_guard.workspace_root
            else ".",
            "entries": entries,
            "entry_count": len(entries),
        }

    def make_tree(self, directories: list[str]) -> dict[str, object]:
        created: list[str] = []
        for directory in directories:
            resolved = self._root_guard.resolve_path(directory)
            resolved.mkdir(parents=True, exist_ok=True)
            created.append(self._root_guard.relative_path(resolved))
        return {
            "created_directories": created,
            "count": len(created),
        }

    def read_files(self, paths: list[str], max_chars_per_file: int = 20000) -> dict[str, object]:
        files: list[dict[str, object]] = []
        for raw_path in paths:
            resolved = self._root_guard.resolve_path(raw_path)
            if not resolved.exists():
                raise FileNotFoundError(f"Path '{raw_path}' does not exist.")
            if resolved.is_dir():
                raise IsADirectoryError(f"Path '{raw_path}' is a directory.")

            content = resolved.read_text(encoding="utf-8")
            truncated = len(content) > max_chars_per_file
            files.append(
                {
                    "path": self._root_guard.relative_path(resolved),
                    "content": content[:max_chars_per_file],
                    "truncated": truncated,
                    "size_chars": len(content),
                }
            )
        return {"files": files, "count": len(files)}

    def write_files(self, files: list[dict[str, str]], mode: str = "overwrite") -> dict[str, object]:
        if mode not in {"overwrite", "create_only"}:
            raise ValueError("Mode must be either 'overwrite' or 'create_only'.")

        created: list[str] = []
        updated: list[str] = []
        skipped: list[str] = []

        for item in files:
            raw_path = item["path"]
            content = item["content"]
            resolved = self._root_guard.resolve_path(raw_path)
            resolved.parent.mkdir(parents=True, exist_ok=True)

            if mode == "create_only" and resolved.exists():
                skipped.append(self._root_guard.relative_path(resolved))
                continue

            existed = resolved.exists()
            resolved.write_text(content, encoding="utf-8")
            relative = self._root_guard.relative_path(resolved)
            if existed:
                updated.append(relative)
            else:
                created.append(relative)

        return {
            "created_files": created,
            "updated_files": updated,
            "skipped_files": skipped,
        }

    def patch_text(self, changes: list[dict[str, object]]) -> dict[str, object]:
        patched: list[str] = []

        for change in changes:
            raw_path = str(change["path"])
            operation = str(change["operation"])
            resolved = self._root_guard.resolve_path(raw_path)
            if not resolved.exists():
                raise FileNotFoundError(f"Path '{raw_path}' does not exist.")
            if resolved.is_dir():
                raise IsADirectoryError(f"Path '{raw_path}' is a directory.")

            original = resolved.read_text(encoding="utf-8")
            updated = original

            if operation == "replace_text":
                old_text = str(change["old_text"])
                new_text = str(change["new_text"])
                count = int(change.get("count", 1))
                if old_text not in updated:
                    raise ValueError(
                        f"Expected text not found in '{raw_path}' for replace_text."
                    )
                updated = updated.replace(old_text, new_text, count)
            elif operation == "append_text":
                updated = updated + str(change["text"])
            elif operation == "prepend_text":
                updated = str(change["text"]) + updated
            else:
                raise ValueError(f"Unsupported patch operation '{operation}'.")

            resolved.write_text(updated, encoding="utf-8")
            patched.append(self._root_guard.relative_path(resolved))

        return {"patched_files": patched, "count": len(patched)}

    def search_text(
        self,
        pattern: str,
        paths: list[str] | None = None,
        max_results: int = 100,
        case_sensitive: bool = False,
    ) -> dict[str, object]:
        if not pattern:
            raise ValueError("Search pattern must not be empty.")

        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(pattern, flags)
        search_roots = paths or ["."]
        matches: list[dict[str, object]] = []

        for raw_path in search_roots:
            resolved = self._root_guard.resolve_path(raw_path)
            if resolved.is_dir():
                candidates = sorted(
                    file_path
                    for file_path in resolved.rglob("*")
                    if file_path.is_file() and "__pycache__" not in file_path.parts
                )
            else:
                candidates = [resolved]

            for candidate in candidates:
                if len(matches) >= max_results:
                    return {
                        "pattern": pattern,
                        "matches": matches,
                        "match_count": len(matches),
                        "truncated": True,
                    }
                try:
                    content = candidate.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue

                for lineno, line in enumerate(content.splitlines(), start=1):
                    if compiled.search(line):
                        matches.append(
                            {
                                "path": self._root_guard.relative_path(candidate),
                                "lineno": lineno,
                                "line": line,
                            }
                        )
                        if len(matches) >= max_results:
                            return {
                                "pattern": pattern,
                                "matches": matches,
                                "match_count": len(matches),
                                "truncated": True,
                            }

        return {
            "pattern": pattern,
            "matches": matches,
            "match_count": len(matches),
            "truncated": False,
        }

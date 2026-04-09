from __future__ import annotations

import ast
import difflib
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .root_guard import RootGuard


@dataclass(frozen=True, slots=True)
class HeadRecord:
    path: str
    content: str
    revision_id: str
    content_hash: str
    updated_at: str
    source_mtime: str | None
    size_chars: int


class SandboxStore:
    """SQLite-backed sandbox workbench with HEAD state, revisions, diffs, and symbols."""

    _IGNORED_DIR_NAMES = {
        "__pycache__",
        ".git",
        ".venv",
        "node_modules",
    }
    _IGNORED_RELATIVE_PREFIXES = (
        "data/runtime/",
        "data/sandbox/",
        "logs/",
        "_docs/_journalDB/",
    )
    _IGNORED_SUFFIXES = {
        ".db",
        ".pyc",
        ".pyo",
        ".sqlite",
        ".sqlite3",
    }

    def __init__(self, db_path: Path, root_guard: RootGuard) -> None:
        self._db_path = db_path
        self._root_guard = root_guard

    def initialize(self, reset: bool = False) -> dict[str, object]:
        self.ensure_schema()
        with sqlite3.connect(self._db_path) as connection:
            if reset:
                connection.execute("DELETE FROM symbol_index")
                connection.execute("DELETE FROM exports")
                connection.execute("DELETE FROM file_head")
                connection.execute("DELETE FROM file_revisions")
                connection.execute("DELETE FROM content_blobs")
                connection.execute("DELETE FROM sandbox_meta")

            initialized_at = datetime.now().astimezone().isoformat()
            connection.execute(
                """
                INSERT INTO sandbox_meta (meta_key, meta_value)
                VALUES (?, ?)
                ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                """,
                ("workspace_root", str(self._root_guard.workspace_root)),
            )
            connection.execute(
                """
                INSERT INTO sandbox_meta (meta_key, meta_value)
                VALUES (?, ?)
                ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                """,
                ("initialized_at", initialized_at),
            )

        return {
            "db_path": str(self._db_path),
            "workspace_root": str(self._root_guard.workspace_root),
            "initialized_at": initialized_at,
            "reset": reset,
            "head_file_count": self._count_rows("file_head"),
            "revision_count": self._count_rows("file_revisions"),
            "export_count": self._count_rows("exports"),
        }

    def ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sandbox_meta (
                    meta_key TEXT PRIMARY KEY,
                    meta_value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS content_blobs (
                    content_hash TEXT PRIMARY KEY,
                    content_text TEXT NOT NULL,
                    size_chars INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS file_revisions (
                    revision_id TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    parent_revision_id TEXT,
                    created_at TEXT NOT NULL,
                    source_kind TEXT NOT NULL,
                    diff_text TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS file_head (
                    path TEXT PRIMARY KEY,
                    revision_id TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source_mtime TEXT,
                    size_chars INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS symbol_index (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    revision_id TEXT NOT NULL,
                    path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    lineno INTEGER NOT NULL,
                    end_lineno INTEGER,
                    details_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS exports (
                    export_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    target_dir TEXT NOT NULL,
                    file_count INTEGER NOT NULL,
                    exported_paths_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_file_revisions_path_created_at ON file_revisions (path, created_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbol_index_revision ON symbol_index (revision_id)"
            )

    def ingest_workspace(
        self,
        paths: list[str] | None = None,
        max_files: int = 1000,
    ) -> dict[str, object]:
        self.ensure_schema()
        candidates = self._collect_workspace_files(paths or ["."], max_files=max_files)
        created_files: list[str] = []
        updated_files: list[str] = []
        unchanged_files: list[str] = []
        skipped_binary_files: list[str] = []

        for file_path in candidates:
            relative_path = self._root_guard.relative_path(file_path)
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                skipped_binary_files.append(relative_path)
                continue

            existed = self._get_head_record(relative_path)
            revision_id = self._upsert_head(
                path=relative_path,
                content=content,
                source_kind="ingest_workspace",
                source_mtime=datetime.fromtimestamp(file_path.stat().st_mtime).astimezone().isoformat(),
            )
            if revision_id is None:
                unchanged_files.append(relative_path)
            elif existed is None:
                created_files.append(relative_path)
            else:
                updated_files.append(relative_path)

        return {
            "db_path": str(self._db_path),
            "workspace_root": str(self._root_guard.workspace_root),
            "requested_paths": paths or ["."],
            "scanned_file_count": len(candidates),
            "created_files": created_files,
            "updated_files": updated_files,
            "unchanged_files": unchanged_files,
            "skipped_binary_files": skipped_binary_files,
            "head_file_count": self._count_rows("file_head"),
            "revision_count": self._count_rows("file_revisions"),
        }

    def read_head(
        self,
        paths: list[str],
        max_chars_per_file: int = 20000,
    ) -> dict[str, object]:
        self.ensure_schema()
        files: list[dict[str, object]] = []
        for path in paths:
            record = self._require_head_record(path)
            files.append(
                {
                    "path": path,
                    "content": record.content[:max_chars_per_file],
                    "truncated": len(record.content) > max_chars_per_file,
                    "size_chars": record.size_chars,
                    "revision_id": record.revision_id,
                    "content_hash": record.content_hash,
                    "updated_at": record.updated_at,
                }
            )
        return {"files": files, "count": len(files)}

    def search_head(
        self,
        pattern: str,
        paths: list[str] | None = None,
        max_results: int = 100,
        case_sensitive: bool = False,
    ) -> dict[str, object]:
        import re

        self.ensure_schema()
        if not pattern:
            raise ValueError("Search pattern must not be empty.")

        flags = 0 if case_sensitive else re.IGNORECASE
        compiled = re.compile(pattern, flags)
        matches: list[dict[str, object]] = []

        for record in self._iter_head_records(paths=paths):
            for lineno, line in enumerate(record.content.splitlines(), start=1):
                if compiled.search(line):
                    matches.append(
                        {
                            "path": record.path,
                            "lineno": lineno,
                            "line": line,
                            "revision_id": record.revision_id,
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

    def stage_diff(self, changes: list[dict[str, object]]) -> dict[str, object]:
        self.ensure_schema()
        created_files: list[str] = []
        updated_files: list[str] = []
        skipped_files: list[str] = []
        revision_ids: list[str] = []

        for change in changes:
            path = str(change["path"])
            operation = str(change["operation"])
            current_record = self._get_head_record(path)
            current_content = "" if current_record is None else current_record.content
            updated_content = self._apply_text_operation(
                current_content=current_content,
                operation=operation,
                change=change,
            )
            if updated_content == current_content:
                skipped_files.append(path)
                continue

            revision_id = self._upsert_head(
                path=path,
                content=updated_content,
                source_kind="stage_diff",
                source_mtime=None,
            )
            if revision_id is None:
                skipped_files.append(path)
                continue

            revision_ids.append(revision_id)
            if current_record is None:
                created_files.append(path)
            else:
                updated_files.append(path)

        return {
            "created_files": created_files,
            "updated_files": updated_files,
            "skipped_files": skipped_files,
            "revision_ids": revision_ids,
            "head_file_count": self._count_rows("file_head"),
            "revision_count": self._count_rows("file_revisions"),
        }

    def export_head(
        self,
        target_dir: str,
        paths: list[str] | None = None,
        mode: str = "overwrite",
    ) -> dict[str, object]:
        self.ensure_schema()
        if mode not in {"overwrite", "create_only"}:
            raise ValueError("Mode must be either 'overwrite' or 'create_only'.")

        export_root = self._root_guard.resolve_path(target_dir)
        export_root.mkdir(parents=True, exist_ok=True)
        selected_records = list(self._iter_head_records(paths=paths))
        created_files: list[str] = []
        updated_files: list[str] = []
        skipped_files: list[str] = []

        for record in selected_records:
            destination = export_root / Path(record.path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination_relative = self._root_guard.relative_path(destination)
            if mode == "create_only" and destination.exists():
                skipped_files.append(destination_relative)
                continue

            existed = destination.exists()
            destination.write_text(record.content, encoding="utf-8")
            if existed:
                updated_files.append(destination_relative)
            else:
                created_files.append(destination_relative)

        export_id = uuid4().hex[:12]
        created_at = datetime.now().astimezone().isoformat()
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT INTO exports (export_id, created_at, target_dir, file_count, exported_paths_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    export_id,
                    created_at,
                    self._root_guard.relative_path(export_root),
                    len(created_files) + len(updated_files),
                    json.dumps(created_files + updated_files),
                ),
            )

        return {
            "export_id": export_id,
            "created_at": created_at,
            "target_dir": self._root_guard.relative_path(export_root),
            "selected_file_count": len(selected_records),
            "created_files": created_files,
            "updated_files": updated_files,
            "skipped_files": skipped_files,
        }

    def history_for_file(self, path: str, limit: int = 20) -> dict[str, object]:
        self.ensure_schema()
        head_record = self._require_head_record(path)
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT revision_id, content_hash, parent_revision_id, created_at, source_kind, diff_text
                FROM file_revisions
                WHERE path = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (path, limit),
            ).fetchall()

        revisions = [
            {
                "revision_id": row[0],
                "content_hash": row[1],
                "parent_revision_id": row[2],
                "created_at": row[3],
                "source_kind": row[4],
                "diff_preview": self._preview_diff(row[5]),
            }
            for row in rows
        ]
        return {
            "path": path,
            "head": {
                "revision_id": head_record.revision_id,
                "content_hash": head_record.content_hash,
                "updated_at": head_record.updated_at,
                "size_chars": head_record.size_chars,
            },
            "revisions": revisions,
            "revision_count": len(revisions),
        }

    def query_symbols(
        self,
        paths: list[str] | None = None,
        kinds: list[str] | None = None,
        name_contains: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
        self.ensure_schema()
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT s.path, s.kind, s.name, s.lineno, s.end_lineno, s.details_json, s.revision_id
                FROM symbol_index AS s
                INNER JOIN file_head AS h
                    ON h.revision_id = s.revision_id
                ORDER BY s.path ASC, s.lineno ASC
                """
            ).fetchall()

        normalized_paths = self._normalize_filter_paths(paths)
        normalized_kinds = {kind.lower() for kind in kinds or []}
        needle = (name_contains or "").lower().strip()
        symbols: list[dict[str, object]] = []

        for row in rows:
            path = str(row[0])
            kind = str(row[1])
            name = str(row[2])
            if normalized_paths and not any(
                path == prefix or path.startswith(f"{prefix}/") for prefix in normalized_paths
            ):
                continue
            if normalized_kinds and kind.lower() not in normalized_kinds:
                continue
            if needle and needle not in name.lower():
                continue

            symbols.append(
                {
                    "path": path,
                    "kind": kind,
                    "name": name,
                    "lineno": row[3],
                    "end_lineno": row[4],
                    "details": json.loads(row[5]),
                    "revision_id": row[6],
                }
            )
            if len(symbols) >= limit:
                break

        return {
            "symbols": symbols,
            "symbol_count": len(symbols),
        }

    def _count_rows(self, table_name: str) -> int:
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0]) if row is not None else 0

    def _collect_workspace_files(self, paths: list[str], max_files: int) -> list[Path]:
        collected: list[Path] = []
        seen: set[str] = set()

        for raw_path in paths:
            resolved = self._root_guard.resolve_path(raw_path)
            if resolved.is_dir():
                for candidate in sorted(resolved.rglob("*")):
                    if not candidate.is_file():
                        continue
                    relative = self._root_guard.relative_path(candidate)
                    if relative in seen or self._should_skip_workspace_file(candidate, relative):
                        continue
                    collected.append(candidate)
                    seen.add(relative)
                    if len(collected) >= max_files:
                        return collected
            else:
                relative = self._root_guard.relative_path(resolved)
                if relative not in seen and not self._should_skip_workspace_file(resolved, relative):
                    collected.append(resolved)
                    seen.add(relative)
                    if len(collected) >= max_files:
                        return collected

        return collected

    def _should_skip_workspace_file(self, file_path: Path, relative_path: str) -> bool:
        if any(part in self._IGNORED_DIR_NAMES for part in file_path.parts):
            return True
        if any(relative_path.startswith(prefix) for prefix in self._IGNORED_RELATIVE_PREFIXES):
            return True
        return file_path.suffix.lower() in self._IGNORED_SUFFIXES

    def _upsert_head(
        self,
        path: str,
        content: str,
        source_kind: str,
        source_mtime: str | None,
    ) -> str | None:
        previous = self._get_head_record(path)
        content_hash = self._hash_content(content)
        updated_at = datetime.now().astimezone().isoformat()

        if previous is not None and previous.content_hash == content_hash:
            with sqlite3.connect(self._db_path) as connection:
                connection.execute(
                    """
                    UPDATE file_head
                    SET updated_at = ?, source_mtime = ?, size_chars = ?
                    WHERE path = ?
                    """,
                    (updated_at, source_mtime, len(content), path),
                )
            return None

        revision_id = uuid4().hex
        parent_revision_id = None if previous is None else previous.revision_id
        diff_text = self._build_diff(
            path=path,
            previous_content="" if previous is None else previous.content,
            updated_content=content,
        )

        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO content_blobs (content_hash, content_text, size_chars, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (content_hash, content, len(content), updated_at),
            )
            connection.execute(
                """
                INSERT INTO file_revisions (
                    revision_id,
                    path,
                    content_hash,
                    parent_revision_id,
                    created_at,
                    source_kind,
                    diff_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id,
                    path,
                    content_hash,
                    parent_revision_id,
                    updated_at,
                    source_kind,
                    diff_text,
                ),
            )
            connection.execute(
                """
                INSERT INTO file_head (path, revision_id, content_hash, updated_at, source_mtime, size_chars)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    revision_id = excluded.revision_id,
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at,
                    source_mtime = excluded.source_mtime,
                    size_chars = excluded.size_chars
                """,
                (path, revision_id, content_hash, updated_at, source_mtime, len(content)),
            )
            self._replace_symbols_for_revision(
                connection=connection,
                path=path,
                revision_id=revision_id,
                content=content,
            )

        return revision_id

    def _get_head_record(self, path: str) -> HeadRecord | None:
        normalized_path = self._normalize_relative_path(path)
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT h.path, b.content_text, h.revision_id, h.content_hash, h.updated_at, h.source_mtime, h.size_chars
                FROM file_head AS h
                INNER JOIN content_blobs AS b
                    ON b.content_hash = h.content_hash
                WHERE h.path = ?
                """,
                (normalized_path,),
            ).fetchone()
        if row is None:
            return None
        return HeadRecord(
            path=str(row[0]),
            content=str(row[1]),
            revision_id=str(row[2]),
            content_hash=str(row[3]),
            updated_at=str(row[4]),
            source_mtime=None if row[5] is None else str(row[5]),
            size_chars=int(row[6]),
        )

    def _require_head_record(self, path: str) -> HeadRecord:
        record = self._get_head_record(path)
        if record is None:
            raise FileNotFoundError(f"Sandbox HEAD does not contain '{path}'.")
        return record

    def _iter_head_records(self, paths: list[str] | None = None) -> list[HeadRecord]:
        normalized_paths = self._normalize_filter_paths(paths)
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT h.path, b.content_text, h.revision_id, h.content_hash, h.updated_at, h.source_mtime, h.size_chars
                FROM file_head AS h
                INNER JOIN content_blobs AS b
                    ON b.content_hash = h.content_hash
                ORDER BY h.path ASC
                """
            ).fetchall()

        records: list[HeadRecord] = []
        for row in rows:
            path = str(row[0])
            if normalized_paths and not any(
                path == prefix or path.startswith(f"{prefix}/") for prefix in normalized_paths
            ):
                continue
            records.append(
                HeadRecord(
                    path=path,
                    content=str(row[1]),
                    revision_id=str(row[2]),
                    content_hash=str(row[3]),
                    updated_at=str(row[4]),
                    source_mtime=None if row[5] is None else str(row[5]),
                    size_chars=int(row[6]),
                )
            )
        return records

    def _normalize_filter_paths(self, paths: list[str] | None) -> list[str]:
        if not paths:
            return []
        normalized: list[str] = []
        for raw_path in paths:
            candidate = self._root_guard.resolve_path(raw_path)
            relative = self._root_guard.relative_path(candidate)
            if relative == ".":
                return []
            normalized.append(relative)
        return normalized

    def _normalize_relative_path(self, path: str) -> str:
        candidate = self._root_guard.resolve_path(path)
        return self._root_guard.relative_path(candidate)

    def _apply_text_operation(
        self,
        current_content: str,
        operation: str,
        change: dict[str, object],
    ) -> str:
        if operation == "set_text":
            return str(change.get("text", ""))
        if operation == "replace_text":
            old_text = str(change["old_text"])
            new_text = str(change["new_text"])
            count = int(change.get("count", 1))
            if old_text not in current_content:
                raise ValueError(
                    f"Expected text not found in sandbox HEAD for '{change['path']}'."
                )
            return current_content.replace(old_text, new_text, count)
        if operation == "append_text":
            return current_content + str(change["text"])
        if operation == "prepend_text":
            return str(change["text"]) + current_content
        raise ValueError(f"Unsupported sandbox diff operation '{operation}'.")

    def _hash_content(self, content: str) -> str:
        return hashlib.sha3_256(content.encode("utf-8")).hexdigest()

    def _build_diff(self, path: str, previous_content: str, updated_content: str) -> str:
        diff_lines = difflib.unified_diff(
            previous_content.splitlines(),
            updated_content.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
        return "\n".join(diff_lines)

    def _preview_diff(self, diff_text: str, max_lines: int = 16) -> str:
        if not diff_text:
            return ""
        lines = diff_text.splitlines()
        preview = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            preview += "\n..."
        return preview

    def _replace_symbols_for_revision(
        self,
        connection: sqlite3.Connection,
        path: str,
        revision_id: str,
        content: str,
    ) -> None:
        connection.execute("DELETE FROM symbol_index WHERE revision_id = ?", (revision_id,))
        if not path.endswith(".py"):
            return

        try:
            tree = ast.parse(content, filename=path)
        except SyntaxError:
            return

        symbol_rows: list[tuple[str, str, int, int | None, str]] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbol_rows.append(
                    (
                        "function",
                        node.name,
                        node.lineno,
                        getattr(node, "end_lineno", node.lineno),
                        json.dumps({"args": [arg.arg for arg in node.args.args]}),
                    )
                )
            elif isinstance(node, ast.ClassDef):
                symbol_rows.append(
                    (
                        "class",
                        node.name,
                        node.lineno,
                        getattr(node, "end_lineno", node.lineno),
                        json.dumps(
                            {
                                "methods": [
                                    child.name
                                    for child in node.body
                                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                                ]
                            }
                        ),
                    )
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    symbol_rows.append(
                        (
                            "import",
                            alias.name,
                            getattr(node, "lineno", 1),
                            getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                            json.dumps({"alias": alias.asname}),
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                symbol_rows.append(
                    (
                        "import_from",
                        module,
                        getattr(node, "lineno", 1),
                        getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                        json.dumps({"names": [alias.name for alias in node.names]}),
                    )
                )

        for kind, name, lineno, end_lineno, details_json in symbol_rows:
            connection.execute(
                """
                INSERT INTO symbol_index (
                    revision_id, path, kind, name, lineno, end_lineno, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (revision_id, path, kind, name, lineno, end_lineno, details_json),
            )

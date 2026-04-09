from __future__ import annotations

import ast
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from .root_guard import RootGuard


@dataclass(frozen=True, slots=True)
class PartRecord:
    part_id: str
    relative_path: str
    name: str
    kind: str
    layer: str
    extension: str
    content_hash: str
    size_chars: int
    symbol_count: int
    built_at: str
    summary: str
    content: str


class PartsCatalogStore:
    """SQLite-backed local parts catalog for reusable worker-facing code and docs."""

    _CANONICAL_DOC_ROLES = {
        "readme",
        "architecture",
        "tools",
        "onboarding",
        "testing",
        "contract",
        "micro_contract",
    }
    _HISTORY_QUERY_TERMS = {
        "audit",
        "dev",
        "devlog",
        "history",
        "journal",
        "log",
        "record",
        "timeline",
    }
    _TASK_QUERY_TERMS = {
        "backlog",
        "task",
        "tasklist",
        "todo",
    }
    _BLUEPRINT_QUERY_TERMS = {
        "blueprint",
        "bundle",
        "export",
        "manifest",
        "scaffold",
        "schema",
        "tool",
    }
    _IGNORED_DIR_NAMES = {
        "__pycache__",
        ".git",
        ".venv",
        "node_modules",
    }
    _IGNORED_RELATIVE_PREFIXES = (
        "data/runtime/",
        "data/sandbox/",
        "data/parts/",
        "logs/",
        "_docs/_journalDB/",
    )
    _IGNORED_SUFFIXES = {
        ".db",
        ".pyc",
        ".pyo",
        ".sqlite",
        ".sqlite3",
        ".zip",
    }

    def __init__(self, db_path: Path, root_guard: RootGuard) -> None:
        self._db_path = db_path
        self._root_guard = root_guard

    def build_catalog(
        self,
        paths: list[str] | None = None,
        reset: bool = True,
        max_files: int = 2000,
    ) -> dict[str, object]:
        self.ensure_schema()
        if reset:
            self._reset_catalog()

        requested_paths = paths or ["src", "_docs", "tests"]
        candidates = self._collect_workspace_files(requested_paths, max_files=max_files)
        created_parts: list[str] = []
        skipped_binary_files: list[str] = []
        built_at = datetime.now().astimezone().isoformat()

        with sqlite3.connect(self._db_path) as connection:
            for file_path in candidates:
                relative_path = self._root_guard.relative_path(file_path)
                try:
                    content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    skipped_binary_files.append(relative_path)
                    continue

                content_hash = self._hash_content(content)
                metadata = self._classify_part(relative_path)
                summary = self._summarize_content(content)
                symbols = self._extract_symbols(relative_path, content)
                part_id = relative_path

                connection.execute(
                    """
                    INSERT OR IGNORE INTO source_blobs (content_hash, content_text, size_chars, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (content_hash, content, len(content), built_at),
                )
                connection.execute(
                    """
                    INSERT INTO parts (
                        part_id,
                        relative_path,
                        name,
                        kind,
                        layer,
                        extension,
                        content_hash,
                        size_chars,
                        symbol_count,
                        built_at,
                        summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(part_id) DO UPDATE SET
                        name = excluded.name,
                        kind = excluded.kind,
                        layer = excluded.layer,
                        extension = excluded.extension,
                        content_hash = excluded.content_hash,
                        size_chars = excluded.size_chars,
                        symbol_count = excluded.symbol_count,
                        built_at = excluded.built_at,
                        summary = excluded.summary
                    """,
                    (
                        part_id,
                        relative_path,
                        metadata["name"],
                        metadata["kind"],
                        metadata["layer"],
                        metadata["extension"],
                        content_hash,
                        len(content),
                        len(symbols),
                        built_at,
                        summary,
                    ),
                )
                connection.execute("DELETE FROM part_symbols WHERE part_id = ?", (part_id,))
                for symbol in symbols:
                    connection.execute(
                        """
                        INSERT INTO part_symbols (
                            part_id,
                            symbol_kind,
                            symbol_name,
                            lineno,
                            end_lineno,
                            details_json
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            part_id,
                            symbol["symbol_kind"],
                            symbol["symbol_name"],
                            symbol["lineno"],
                            symbol["end_lineno"],
                            json.dumps(symbol["details"]),
                        ),
                    )
                if self._fts_enabled(connection):
                    connection.execute(
                        """
                        INSERT INTO parts_fts (
                            part_id,
                            relative_path,
                            name,
                            kind,
                            layer,
                            summary,
                            content,
                            symbols
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            part_id,
                            relative_path,
                            metadata["name"],
                            metadata["kind"],
                            metadata["layer"],
                            summary,
                            content,
                            " ".join(symbol["symbol_name"] for symbol in symbols),
                        ),
                    )
                created_parts.append(part_id)

            connection.execute(
                """
                INSERT INTO catalog_meta (meta_key, meta_value)
                VALUES (?, ?)
                ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                """,
                ("workspace_root", str(self._root_guard.workspace_root)),
            )
            connection.execute(
                """
                INSERT INTO catalog_meta (meta_key, meta_value)
                VALUES (?, ?)
                ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                """,
                ("last_built_at", built_at),
            )

        return {
            "db_path": str(self._db_path),
            "workspace_root": str(self._root_guard.workspace_root),
            "requested_paths": requested_paths,
            "built_at": built_at,
            "part_count": self._count_rows("parts"),
            "symbol_count": self._count_rows("part_symbols"),
            "created_parts": created_parts,
            "skipped_binary_files": skipped_binary_files,
        }

    def search_parts(
        self,
        query: str,
        kinds: list[str] | None = None,
        layers: list[str] | None = None,
        path_prefixes: list[str] | None = None,
        intent_target: str = "auto",
        prefer_code: bool = False,
        prefer_docs: bool = False,
        limit: int = 50,
    ) -> dict[str, object]:
        self.ensure_schema()
        query_text = query.strip().lower()
        if not query_text:
            raise ValueError("Search query must not be empty.")
        query_tokens = self._tokenize_query(query_text)
        if not query_tokens:
            raise ValueError("Search query must include at least one searchable token.")
        normalized_intent = self._normalize_intent_target(intent_target)

        normalized_prefixes = self._normalize_filter_paths(path_prefixes)
        kind_set = {item.lower() for item in kinds or []}
        layer_set = {item.lower() for item in layers or []}

        with sqlite3.connect(self._db_path) as connection:
            fts_scores = self._read_fts_matches(connection, query_tokens)
            symbol_rows = connection.execute(
                """
                SELECT part_id, symbol_kind, symbol_name
                FROM part_symbols
                ORDER BY part_id ASC, lineno ASC, symbol_name ASC
                """
            ).fetchall()
            rows = connection.execute(
                """
                SELECT p.part_id, p.relative_path, p.name, p.kind, p.layer, p.extension,
                       p.size_chars, p.symbol_count, p.summary, b.content_text
                FROM parts AS p
                INNER JOIN source_blobs AS b
                    ON b.content_hash = p.content_hash
                ORDER BY p.relative_path ASC
                """
            ).fetchall()

        symbol_map: dict[str, list[dict[str, str]]] = {}
        for symbol_row in symbol_rows:
            symbol_map.setdefault(str(symbol_row[0]), []).append(
                {
                    "symbol_kind": str(symbol_row[1]),
                    "symbol_name": str(symbol_row[2]),
                }
            )

        scored_results: list[tuple[int, dict[str, object]]] = []
        for row in rows:
            part_id = str(row[0])
            relative_path = str(row[1])
            kind = str(row[3])
            layer = str(row[4])
            if normalized_prefixes and not any(
                relative_path == prefix or relative_path.startswith(f"{prefix}/")
                for prefix in normalized_prefixes
            ):
                continue
            if kind_set and kind.lower() not in kind_set:
                continue
            if layer_set and layer.lower() not in layer_set:
                continue

            name = str(row[2])
            summary = str(row[8])
            content = str(row[9])
            symbol_entries = symbol_map.get(part_id, [])
            symbol_names = [entry["symbol_name"] for entry in symbol_entries]
            document_role = self._classify_document_role(relative_path, kind)
            score, matched_tokens = self._score_part_match(
                query_text=query_text,
                query_tokens=query_tokens,
                relative_path=relative_path,
                name=name,
                kind=kind,
                layer=layer,
                summary=summary,
                content=content,
                symbol_names=symbol_names,
                fts_rank=fts_scores.get(part_id),
                intent_target=normalized_intent,
                prefer_code=prefer_code,
                prefer_docs=prefer_docs,
                document_role=document_role,
            )
            if score <= 0 or matched_tokens <= 0:
                continue

            scored_results.append(
                (
                    score,
                    {
                        "part_id": part_id,
                        "relative_path": relative_path,
                        "name": name,
                        "kind": kind,
                        "layer": layer,
                        "extension": str(row[5]),
                        "size_chars": int(row[6]),
                        "symbol_count": int(row[7]),
                        "summary": summary,
                        "snippet": self._build_snippet(content, query_text, query_tokens),
                        "score": score,
                        "matched_token_count": matched_tokens,
                        "fts_rank": fts_scores.get(part_id),
                        "top_symbols": self._select_anchor_symbols(symbol_entries),
                        "document_role": document_role,
                    },
                )
            )

        scored_results.sort(
            key=lambda item: (
                -item[0],
                item[1]["relative_path"],
            )
        )
        results = [item[1] for item in scored_results[:limit]]
        shelf_items = [
            self._build_shelf_item(rank=index, result=result, query_tokens=query_tokens)
            for index, result in enumerate(results, start=1)
        ]
        shelf_summary = self._build_shelf_summary(
            query=query,
            items=shelf_items,
            total_ranked_candidates=len(scored_results),
        )

        return {
            "query": query,
            "query_tokens": query_tokens,
            "intent_target": normalized_intent,
            "prefer_code": prefer_code,
            "prefer_docs": prefer_docs,
            "shelf_summary": shelf_summary,
            "items": shelf_items,
            "item_count": len(shelf_items),
            "total_ranked_candidates": len(scored_results),
            "location_index": [item["location"] for item in shelf_items],
            "location_records": [
                {
                    "rank": int(item["rank"]),
                    "location": str(item["location"]),
                    "kind": str(item["kind"]),
                    "layer": str(item["layer"]),
                    "document_role": str(item.get("document_role", "none")),
                }
                for item in shelf_items
            ],
            "results": results,
            "result_count": len(results),
        }

    def get_parts(
        self,
        part_ids: list[str],
        max_chars_per_part: int = 20000,
    ) -> dict[str, object]:
        self.ensure_schema()
        parts: list[dict[str, object]] = []
        for part_id in part_ids:
            record = self._require_part_record(part_id)
            symbols = self._read_symbols_for_part(record.part_id)
            parts.append(
                {
                    "part_id": record.part_id,
                    "relative_path": record.relative_path,
                    "name": record.name,
                    "kind": record.kind,
                    "layer": record.layer,
                    "extension": record.extension,
                    "size_chars": record.size_chars,
                    "symbol_count": record.symbol_count,
                    "built_at": record.built_at,
                    "summary": record.summary,
                    "content": record.content[:max_chars_per_part],
                    "truncated": len(record.content) > max_chars_per_part,
                    "symbols": symbols,
                }
            )
        return {
            "parts": parts,
            "count": len(parts),
        }

    def export_selection(
        self,
        part_ids: list[str],
        target_dir: str,
        mode: str = "overwrite",
    ) -> dict[str, object]:
        self.ensure_schema()
        if mode not in {"overwrite", "create_only"}:
            raise ValueError("Mode must be either 'overwrite' or 'create_only'.")

        export_root = self._root_guard.resolve_path(target_dir)
        export_root.mkdir(parents=True, exist_ok=True)

        created_files: list[str] = []
        updated_files: list[str] = []
        skipped_files: list[str] = []

        for part_id in part_ids:
            record = self._require_part_record(part_id)
            destination = (export_root / Path(record.relative_path)).resolve()
            try:
                destination.relative_to(export_root.resolve())
            except ValueError as error:
                raise ValueError(
                    f"Catalog part '{part_id}' resolves outside the export root."
                ) from error

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

        return {
            "target_dir": self._root_guard.relative_path(export_root),
            "created_files": created_files,
            "updated_files": updated_files,
            "skipped_files": skipped_files,
            "exported_part_count": len(created_files) + len(updated_files),
        }

    def ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS catalog_meta (
                    meta_key TEXT PRIMARY KEY,
                    meta_value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS source_blobs (
                    content_hash TEXT PRIMARY KEY,
                    content_text TEXT NOT NULL,
                    size_chars INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS parts (
                    part_id TEXT PRIMARY KEY,
                    relative_path TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    size_chars INTEGER NOT NULL,
                    symbol_count INTEGER NOT NULL,
                    built_at TEXT NOT NULL,
                    summary TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS part_symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    part_id TEXT NOT NULL,
                    symbol_kind TEXT NOT NULL,
                    symbol_name TEXT NOT NULL,
                    lineno INTEGER NOT NULL,
                    end_lineno INTEGER,
                    details_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_parts_kind_layer ON parts (kind, layer)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_part_symbols_part_id ON part_symbols (part_id)"
            )
            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS parts_fts USING fts5(
                        part_id UNINDEXED,
                        relative_path,
                        name,
                        kind,
                        layer,
                        summary,
                        content,
                        symbols
                    )
                    """
                )
            except sqlite3.OperationalError:
                connection.execute(
                    """
                    INSERT INTO catalog_meta (meta_key, meta_value)
                    VALUES (?, ?)
                    ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                    """,
                    ("fts_enabled", "false"),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO catalog_meta (meta_key, meta_value)
                    VALUES (?, ?)
                    ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value
                    """,
                    ("fts_enabled", "true"),
                )

    def _reset_catalog(self) -> None:
        with sqlite3.connect(self._db_path) as connection:
            connection.execute("DELETE FROM part_symbols")
            connection.execute("DELETE FROM parts")
            connection.execute("DELETE FROM source_blobs")
            if self._fts_enabled(connection):
                connection.execute("DELETE FROM parts_fts")
            connection.execute(
                "DELETE FROM catalog_meta WHERE meta_key NOT IN ('fts_enabled')"
            )

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

    def _classify_part(self, relative_path: str) -> dict[str, str]:
        pure_path = PurePosixPath(relative_path)
        extension = pure_path.suffix.lower()
        parts = pure_path.parts
        name = pure_path.stem or pure_path.name

        layer = "root"
        kind = "file"

        if relative_path.startswith("src/core/"):
            layer = "core"
        elif relative_path.startswith("src/ui/"):
            layer = "ui"
        elif relative_path.startswith("_docs/"):
            layer = "docs"
        elif relative_path.startswith("tests/"):
            layer = "tests"
        elif relative_path.startswith("data/"):
            layer = "data"

        if "orchestrators" in parts:
            kind = "orchestrator"
        elif "managers" in parts:
            kind = "manager"
        elif "components" in parts:
            kind = "component"
        elif "services" in parts:
            kind = "service"
        elif "runtime" in parts:
            kind = "runtime"
        elif relative_path.startswith("_docs/"):
            kind = "doc"
        elif relative_path.startswith("tests/"):
            kind = "test"
        elif extension == ".json":
            kind = "manifest"
        elif extension in {".md", ".txt"}:
            kind = "doc"

        return {
            "name": name,
            "kind": kind,
            "layer": layer,
            "extension": extension,
        }

    def _extract_symbols(self, relative_path: str, content: str) -> list[dict[str, object]]:
        if not relative_path.endswith(".py"):
            return []

        try:
            tree = ast.parse(content, filename=relative_path)
        except SyntaxError:
            return []

        symbols: list[dict[str, object]] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(
                    {
                        "symbol_kind": "function",
                        "symbol_name": node.name,
                        "lineno": node.lineno,
                        "end_lineno": getattr(node, "end_lineno", node.lineno),
                        "details": {"args": [arg.arg for arg in node.args.args]},
                    }
                )
            elif isinstance(node, ast.ClassDef):
                symbols.append(
                    {
                        "symbol_kind": "class",
                        "symbol_name": node.name,
                        "lineno": node.lineno,
                        "end_lineno": getattr(node, "end_lineno", node.lineno),
                        "details": {
                            "methods": [
                                child.name
                                for child in node.body
                                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                            ]
                        },
                    }
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    symbols.append(
                        {
                            "symbol_kind": "import",
                            "symbol_name": alias.name,
                            "lineno": getattr(node, "lineno", 1),
                            "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                            "details": {"alias": alias.asname},
                        }
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                symbols.append(
                    {
                        "symbol_kind": "import_from",
                        "symbol_name": module,
                        "lineno": getattr(node, "lineno", 1),
                        "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                        "details": {"names": [alias.name for alias in node.names]},
                    }
                )
        return symbols

    def _summarize_content(self, content: str, max_chars: int = 160) -> str:
        for line in content.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:max_chars]
        return ""

    def _build_snippet(
        self,
        content: str,
        query_text: str,
        query_tokens: list[str],
        max_chars: int = 200,
    ) -> str:
        lowered = content.lower()
        index = lowered.find(query_text)
        if index == -1:
            for token in query_tokens:
                index = lowered.find(token)
                if index != -1:
                    break
        if index == -1:
            return self._summarize_content(content, max_chars=max_chars)
        start = max(0, index - 60)
        end = min(len(content), index + len(query_text) + 120)
        snippet = content[start:end].replace("\n", " ")
        return snippet[:max_chars]

    def _tokenize_query(self, query_text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9_]+", query_text.lower())
        return [token for token in tokens if len(token) >= 2]

    def _score_part_match(
        self,
        query_text: str,
        query_tokens: list[str],
        relative_path: str,
        name: str,
        kind: str,
        layer: str,
        summary: str,
        content: str,
        symbol_names: list[str],
        fts_rank: float | None = None,
        intent_target: str = "auto",
        prefer_code: bool = False,
        prefer_docs: bool = False,
        document_role: str = "none",
    ) -> tuple[int, int]:
        path_text = relative_path.lower()
        name_text = name.lower()
        kind_text = kind.lower()
        layer_text = layer.lower()
        summary_text = summary.lower()
        content_text = content.lower()
        symbols_text = " ".join(symbol_names).lower()

        score = 0
        matched_tokens: set[str] = set()

        if query_text in path_text:
            score += 160
        if query_text in name_text:
            score += 180
        if query_text in summary_text:
            score += 100
        if query_text in content_text:
            score += 60
        if query_text in symbols_text:
            score += 120
        if fts_rank is not None:
            score += self._fts_rank_bonus(fts_rank)

        for token in query_tokens:
            token_matched = False
            if token in name_text:
                score += 90
                token_matched = True
            if token in path_text:
                score += 70
                token_matched = True
            if token == kind_text or token in kind_text:
                score += 55
                token_matched = True
            if token == layer_text or token in layer_text:
                score += 45
                token_matched = True
            if token in symbols_text:
                score += 50
                token_matched = True
            if token in summary_text:
                score += 35
                token_matched = True
            if token in content_text:
                score += 12
                token_matched = True

            if token_matched:
                matched_tokens.add(token)

        if matched_tokens:
            score += len(matched_tokens) * 10
        if len(matched_tokens) == len(query_tokens):
            score += 80
        elif len(matched_tokens) >= max(1, min(2, len(query_tokens))):
            score += 25

        score += self._intent_bonus(
            intent_target=intent_target,
            kind=kind_text,
            layer=layer_text,
            relative_path=path_text,
            query_text=query_text,
            summary_text=summary_text,
            content_text=content_text,
            symbols_text=symbols_text,
            fts_rank=fts_rank,
        )
        score += self._preference_bonus(
            prefer_code=prefer_code,
            prefer_docs=prefer_docs,
            kind=kind_text,
            layer=layer_text,
        )
        score += self._document_role_bonus(
            document_role=document_role,
            query_tokens=query_tokens,
            prefer_docs=prefer_docs,
            intent_target=intent_target,
        )

        return score, len(matched_tokens)

    def _normalize_intent_target(self, intent_target: str) -> str:
        normalized = intent_target.strip().lower() or "auto"
        allowed = {"auto", "structural", "verbatim", "semantic", "relational"}
        if normalized not in allowed:
            raise ValueError(
                f"Unsupported intent_target '{intent_target}'. Expected one of: {', '.join(sorted(allowed))}."
            )
        return normalized

    def _intent_bonus(
        self,
        intent_target: str,
        kind: str,
        layer: str,
        relative_path: str,
        query_text: str,
        summary_text: str,
        content_text: str,
        symbols_text: str,
        fts_rank: float | None,
    ) -> int:
        if intent_target == "auto":
            return 0

        bonus = 0
        is_code = kind in {"component", "service", "manager", "orchestrator", "runtime", "test"}
        is_doc = kind == "doc"

        if intent_target == "structural":
            if is_code:
                bonus += 120
            if kind in {"component", "service", "manager", "orchestrator"}:
                bonus += 80
            if symbols_text:
                bonus += 70
            if "route" in content_text or "dispatch" in content_text or "class " in content_text:
                bonus += 40
            if is_doc:
                bonus -= 35

        elif intent_target == "verbatim":
            if query_text in content_text:
                bonus += 120
            if query_text in summary_text:
                bonus += 70
            if fts_rank is not None:
                bonus += 40
            if is_doc:
                bonus += 10

        elif intent_target == "semantic":
            if fts_rank is not None:
                bonus += 80
            if query_text in summary_text:
                bonus += 40
            if layer in {"docs", "core"}:
                bonus += 10

        elif intent_target == "relational":
            if is_code:
                bonus += 70
            if "import" in content_text or "from " in content_text:
                bonus += 50
            if "depends" in content_text or "route" in content_text or "dispatch" in content_text:
                bonus += 40
            if "reference" in relative_path or "manifest" in relative_path:
                bonus += 20

        return bonus

    def _preference_bonus(
        self,
        prefer_code: bool,
        prefer_docs: bool,
        kind: str,
        layer: str,
    ) -> int:
        bonus = 0
        is_code = kind in {"component", "service", "manager", "orchestrator", "runtime", "test"}
        is_doc = kind == "doc" or layer == "docs"

        if prefer_code:
            if is_code:
                bonus += 140
            if is_doc:
                bonus -= 80

        if prefer_docs:
            if is_doc:
                bonus += 140
            if is_code:
                bonus -= 80

        return bonus

    def _classify_document_role(self, relative_path: str, kind: str) -> str:
        if kind != "doc":
            return "none"

        if relative_path == "README.md":
            return "readme"
        if relative_path == "_docs/ARCHITECTURE.md":
            return "architecture"
        if relative_path == "_docs/TOOLS.md":
            return "tools"
        if relative_path == "_docs/ONBOARDING.md":
            return "onboarding"
        if relative_path == "_docs/TESTING.md":
            return "testing"
        if relative_path == "_docs/TODO.md":
            return "todo"
        if relative_path == "_docs/dev_log.md":
            return "dev_log"
        if relative_path == "_docs/builder_constraint_contract.md":
            return "contract"
        if relative_path == "_docs/WORKER_MICRO_CONTRACT.md":
            return "micro_contract"
        if relative_path.startswith("_docs/tool_blueprints/"):
            return "tool_blueprint"
        if relative_path == "_docs/_AppJOURNAL/BACKLOG.md":
            return "journal_backlog"
        if relative_path == "_docs/_AppJOURNAL/CURRENT_TASKLIST.md":
            return "journal_tasklist"
        if relative_path.startswith("_docs/_AppJOURNAL/entries/"):
            return "journal_entry"
        if relative_path.startswith("_docs/_AppJOURNAL/"):
            return "journal_doc"
        return "doc"

    def _document_role_bonus(
        self,
        document_role: str,
        query_tokens: list[str],
        prefer_docs: bool,
        intent_target: str,
    ) -> int:
        if document_role == "none":
            return 0

        token_set = set(query_tokens)
        wants_history = bool(token_set & self._HISTORY_QUERY_TERMS)
        wants_tasks = bool(token_set & self._TASK_QUERY_TERMS)
        wants_blueprints = bool(token_set & self._BLUEPRINT_QUERY_TERMS)
        bonus = 0

        if document_role in self._CANONICAL_DOC_ROLES:
            bonus += 70
            if prefer_docs:
                bonus += 40
            if intent_target in {"semantic", "verbatim"}:
                bonus += 20
            if wants_history:
                bonus -= 95
            if wants_tasks:
                bonus -= 45

        elif document_role == "tool_blueprint":
            bonus += 15
            if wants_blueprints:
                bonus += 65

        elif document_role == "todo":
            if wants_tasks:
                bonus += 95
            else:
                bonus += 10

        elif document_role in {"journal_backlog", "journal_tasklist"}:
            if wants_tasks:
                bonus += 75
            else:
                bonus -= 10

        elif document_role == "dev_log":
            if wants_history:
                bonus += 145
            else:
                bonus -= 10

        elif document_role in {"journal_entry", "journal_doc"}:
            if wants_history:
                bonus += 175
            else:
                bonus -= 210 if not prefer_docs else 175

        return bonus

    def _fts_enabled(self, connection: sqlite3.Connection) -> bool:
        row = connection.execute(
            """
            SELECT meta_value
            FROM catalog_meta
            WHERE meta_key = ?
            """,
            ("fts_enabled",),
        ).fetchone()
        if row is not None:
            return str(row[0]).lower() == "true"
        table_row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'parts_fts'
            """
        ).fetchone()
        return table_row is not None

    def _read_fts_matches(
        self,
        connection: sqlite3.Connection,
        query_tokens: list[str],
    ) -> dict[str, float]:
        if not self._fts_enabled(connection):
            return {}

        match_query = " AND ".join(f'"{token}"' for token in query_tokens)
        try:
            rows = connection.execute(
                """
                SELECT part_id, bm25(parts_fts)
                FROM parts_fts
                WHERE parts_fts MATCH ?
                ORDER BY bm25(parts_fts) ASC
                LIMIT 500
                """,
                (match_query,),
            ).fetchall()
        except sqlite3.OperationalError:
            return {}

        return {
            str(row[0]): float(row[1])
            for row in rows
        }

    def _fts_rank_bonus(self, fts_rank: float) -> int:
        if fts_rank <= -20:
            return 220
        if fts_rank <= -12:
            return 180
        if fts_rank <= -8:
            return 140
        if fts_rank <= -4:
            return 100
        if fts_rank <= 0:
            return 80
        if fts_rank < 1:
            return 60
        if fts_rank < 5:
            return 45
        return 60

    def _hash_content(self, content: str) -> str:
        return hashlib.sha3_256(content.encode("utf-8")).hexdigest()

    def _build_shelf_item(
        self,
        rank: int,
        result: dict[str, object],
        query_tokens: list[str],
    ) -> dict[str, object]:
        item = dict(result)
        item["rank"] = rank
        item["location"] = str(result["relative_path"])
        item["item_summary"] = self._build_item_summary(result)
        item["why_matched"] = self._build_match_reasons(result, query_tokens)
        return item

    def _build_item_summary(self, result: dict[str, object]) -> str:
        kind = str(result["kind"])
        layer = str(result["layer"])
        relative_path = str(result["relative_path"])
        summary = str(result.get("summary", "")).strip()
        symbol_count = int(result.get("symbol_count", 0))
        top_symbols = [str(symbol) for symbol in result.get("top_symbols", [])]
        document_role = str(result.get("document_role", "none"))
        if self._is_low_signal_summary(summary):
            summary = ""

        if kind in {"component", "service", "manager", "orchestrator", "runtime"}:
            detail = f"{kind} in the {layer} layer at {relative_path}"
            if symbol_count > 0:
                detail += f" with {symbol_count} indexed symbols"
            if top_symbols:
                detail += f"; anchor symbols: {', '.join(top_symbols[:3])}"
            if summary:
                return f"{detail}. Summary: {summary}"
            return detail + "."

        if kind == "doc":
            label = self._document_role_label(document_role)
            if summary:
                return f"{label} at {relative_path}. Summary: {summary}"
            return f"{label} at {relative_path}."

        if kind == "test":
            if summary:
                return f"Test asset at {relative_path}. Summary: {summary}"
            return f"Test asset at {relative_path}."

        if summary:
            return f"{kind.title()} entry at {relative_path}. Summary: {summary}"
        return f"{kind.title()} entry at {relative_path}."

    def _build_match_reasons(
        self,
        result: dict[str, object],
        query_tokens: list[str],
    ) -> list[str]:
        reasons: list[str] = []
        relative_path = str(result["relative_path"]).lower()
        name = str(result["name"]).lower()
        kind = str(result["kind"]).lower()
        layer = str(result["layer"]).lower()
        summary = str(result.get("summary", "")).lower()
        snippet = str(result.get("snippet", "")).lower()

        score = int(result.get("score", 0))
        matched_token_count = int(result.get("matched_token_count", 0))
        if matched_token_count:
            reasons.append(f"matched {matched_token_count} query tokens")
        if result.get("fts_rank") is not None:
            reasons.append("matched SQLite FTS index")
        matched_specific_tokens = [
            token
            for token in query_tokens
            if token in relative_path or token in name or token in summary or token in snippet
        ]
        if matched_specific_tokens:
            reasons.append(
                "token evidence: " + ", ".join(matched_specific_tokens[:3])
            )
        if "component" in kind:
            reasons.append("classified as a reusable component")
        elif "service" in kind:
            reasons.append("classified as a reusable service")
        elif "manager" in kind or "orchestrator" in kind:
            reasons.append("classified as a coordination layer part")
        elif "doc" in kind:
            reasons.append("contains supporting documentation")
            label = self._document_role_label(str(result.get("document_role", "doc"))).lower()
            if label != "documentation entry":
                reasons.append(f"classified as {label}")
        if "sidecar" in relative_path or "sidecar" in name or "sidecar" in summary or "sidecar" in snippet:
            reasons.append("contains sidecar-related evidence")
        if "export" in relative_path or "export" in name or "export" in summary or "export" in snippet:
            reasons.append("contains export-related evidence")
        if score >= 350:
            reasons.append("high combined ranking score")
        return reasons[:4]

    def _build_shelf_summary(
        self,
        query: str,
        items: list[dict[str, object]],
        total_ranked_candidates: int,
    ) -> str:
        if not items:
            return f"No evidence shelf items were returned for '{query}'."

        kind_counts: dict[str, int] = {}
        for item in items:
            kind = str(item["kind"])
            kind_counts[kind] = kind_counts.get(kind, 0) + 1

        top_kind = str(items[0]["kind"])
        top_layer = str(items[0]["layer"])
        top_item = items[0]
        top_location = str(top_item["location"])
        kind_mix = ", ".join(
            f"{count} {kind}"
            for kind, count in sorted(kind_counts.items(), key=lambda item: (-item[1], item[0]))
        )

        return (
            f"Returned {len(items)} evidence shelf items for '{query}' from "
            f"{total_ranked_candidates} ranked candidates. The top anchor is a "
            f"{top_kind} in the {top_layer} layer at {top_location}. "
            f"Returned shelf mix: {kind_mix}."
        )

    def _document_role_label(self, document_role: str) -> str:
        labels = {
            "readme": "README entry",
            "architecture": "Architecture document",
            "tools": "Tool catalog entry",
            "onboarding": "Onboarding guide",
            "testing": "Testing guide",
            "todo": "TODO document",
            "dev_log": "Development log entry",
            "contract": "Builder contract document",
            "micro_contract": "Worker micro-contract document",
            "tool_blueprint": "Tool blueprint document",
            "journal_backlog": "Journal backlog entry",
            "journal_tasklist": "Journal tasklist entry",
            "journal_entry": "Journal entry",
            "journal_doc": "Journal document",
            "doc": "Documentation entry",
            "none": "Documentation entry",
        }
        return labels.get(document_role, "Documentation entry")

    def _is_low_signal_summary(self, summary: str) -> bool:
        lowered = summary.strip().lower()
        return (
            not lowered
            or lowered.startswith("from __future__ import")
            or lowered.startswith("import ")
        )

    def _select_anchor_symbols(self, symbol_entries: list[dict[str, str]]) -> list[str]:
        if not symbol_entries:
            return []

        primary_kinds = ["class", "function"]
        selected: list[str] = []
        for kind in primary_kinds:
            for entry in symbol_entries:
                if entry["symbol_kind"] != kind:
                    continue
                name = entry["symbol_name"]
                if name and name not in selected:
                    selected.append(name)
                if len(selected) >= 5:
                    return selected
        if selected:
            return selected[:5]

        for fallback_kind in ["import_from", "import"]:
            for entry in symbol_entries:
                if entry["symbol_kind"] != fallback_kind:
                    continue
                name = entry["symbol_name"]
                if name and name not in selected:
                    selected.append(name)
                if len(selected) >= 5:
                    return selected
        return selected[:5]

    def _count_rows(self, table_name: str) -> int:
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
        return int(row[0]) if row is not None else 0

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

    def _require_part_record(self, part_id: str) -> PartRecord:
        with sqlite3.connect(self._db_path) as connection:
            row = connection.execute(
                """
                SELECT p.part_id, p.relative_path, p.name, p.kind, p.layer, p.extension,
                       p.content_hash, p.size_chars, p.symbol_count, p.built_at, p.summary,
                       b.content_text
                FROM parts AS p
                INNER JOIN source_blobs AS b
                    ON b.content_hash = p.content_hash
                WHERE p.part_id = ?
                """,
                (part_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Parts catalog does not contain '{part_id}'.")
        return PartRecord(
            part_id=str(row[0]),
            relative_path=str(row[1]),
            name=str(row[2]),
            kind=str(row[3]),
            layer=str(row[4]),
            extension=str(row[5]),
            content_hash=str(row[6]),
            size_chars=int(row[7]),
            symbol_count=int(row[8]),
            built_at=str(row[9]),
            summary=str(row[10]),
            content=str(row[11]),
        )

    def _read_symbols_for_part(self, part_id: str) -> list[dict[str, object]]:
        with sqlite3.connect(self._db_path) as connection:
            rows = connection.execute(
                """
                SELECT symbol_kind, symbol_name, lineno, end_lineno, details_json
                FROM part_symbols
                WHERE part_id = ?
                ORDER BY lineno ASC, symbol_name ASC
                """,
                (part_id,),
            ).fetchall()
        return [
            {
                "symbol_kind": str(row[0]),
                "symbol_name": str(row[1]),
                "lineno": int(row[2]),
                "end_lineno": int(row[3]) if row[3] is not None else None,
                "details": json.loads(row[4]),
            }
            for row in rows
        ]

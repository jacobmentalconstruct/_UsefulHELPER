from __future__ import annotations

import ast
from pathlib import Path

from ..services.root_guard import RootGuard


class AstComponent:
    """Owns Python AST scanning for bounded workspace paths."""

    def __init__(self, root_guard: RootGuard) -> None:
        self._root_guard = root_guard

    def scan_python(
        self,
        paths: list[str],
        max_files: int = 100,
        max_symbols_per_file: int = 100,
    ) -> dict[str, object]:
        files_to_scan = self._collect_python_files(paths, max_files=max_files)
        modules: list[dict[str, object]] = []

        for path in files_to_scan:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            imports = self._extract_imports(tree)
            functions = self._extract_functions(tree, max_symbols_per_file)
            classes = self._extract_classes(tree, max_symbols_per_file)
            modules.append(
                {
                    "path": self._root_guard.relative_path(path),
                    "imports": imports,
                    "functions": functions,
                    "classes": classes,
                }
            )

        return {
            "files_scanned": len(modules),
            "modules": modules,
        }

    def _collect_python_files(self, paths: list[str], max_files: int) -> list[Path]:
        collected: list[Path] = []
        for raw_path in paths:
            resolved = self._root_guard.resolve_path(raw_path)
            if resolved.is_dir():
                for file_path in sorted(resolved.rglob("*.py")):
                    collected.append(file_path)
                    if len(collected) >= max_files:
                        return collected
            elif resolved.suffix == ".py":
                collected.append(resolved)
                if len(collected) >= max_files:
                    return collected
        return collected

    def _extract_imports(self, tree: ast.AST) -> list[str]:
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(module)
        return sorted({item for item in imports if item})

    def _extract_functions(self, tree: ast.Module, limit: int) -> list[dict[str, object]]:
        functions: list[dict[str, object]] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(
                    {
                        "name": node.name,
                        "lineno": node.lineno,
                        "end_lineno": getattr(node, "end_lineno", node.lineno),
                        "args": [arg.arg for arg in node.args.args],
                    }
                )
                if len(functions) >= limit:
                    break
        return functions

    def _extract_classes(self, tree: ast.Module, limit: int) -> list[dict[str, object]]:
        classes: list[dict[str, object]] = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = [
                    child.name
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                classes.append(
                    {
                        "name": node.name,
                        "lineno": node.lineno,
                        "end_lineno": getattr(node, "end_lineno", node.lineno),
                        "methods": methods[:limit],
                    }
                )
                if len(classes) >= limit:
                    break
        return classes

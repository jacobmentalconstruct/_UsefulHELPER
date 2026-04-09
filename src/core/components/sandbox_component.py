from __future__ import annotations

from ..services.sandbox_store import SandboxStore


class SandboxComponent:
    """Owns the bounded project sandbox workbench behavior."""

    def __init__(self, sandbox_store: SandboxStore) -> None:
        self._sandbox_store = sandbox_store

    def initialize(self, reset: bool = False) -> dict[str, object]:
        return self._sandbox_store.initialize(reset=reset)

    def ingest_workspace(
        self,
        paths: list[str] | None = None,
        max_files: int = 1000,
    ) -> dict[str, object]:
        return self._sandbox_store.ingest_workspace(paths=paths, max_files=max_files)

    def read_head(
        self,
        paths: list[str],
        max_chars_per_file: int = 20000,
    ) -> dict[str, object]:
        return self._sandbox_store.read_head(
            paths=paths,
            max_chars_per_file=max_chars_per_file,
        )

    def search_head(
        self,
        pattern: str,
        paths: list[str] | None = None,
        max_results: int = 100,
        case_sensitive: bool = False,
    ) -> dict[str, object]:
        return self._sandbox_store.search_head(
            pattern=pattern,
            paths=paths,
            max_results=max_results,
            case_sensitive=case_sensitive,
        )

    def stage_diff(self, changes: list[dict[str, object]]) -> dict[str, object]:
        return self._sandbox_store.stage_diff(changes=changes)

    def export_head(
        self,
        target_dir: str,
        paths: list[str] | None = None,
        mode: str = "overwrite",
    ) -> dict[str, object]:
        return self._sandbox_store.export_head(
            target_dir=target_dir,
            paths=paths,
            mode=mode,
        )

    def history_for_file(self, path: str, limit: int = 20) -> dict[str, object]:
        return self._sandbox_store.history_for_file(path=path, limit=limit)

    def query_symbols(
        self,
        paths: list[str] | None = None,
        kinds: list[str] | None = None,
        name_contains: str | None = None,
        limit: int = 200,
    ) -> dict[str, object]:
        return self._sandbox_store.query_symbols(
            paths=paths,
            kinds=kinds,
            name_contains=name_contains,
            limit=limit,
        )

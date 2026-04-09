from __future__ import annotations

from ..services.parts_catalog_store import PartsCatalogStore


class PartsCatalogComponent:
    """Owns reusable local parts catalog behavior."""

    def __init__(self, parts_catalog_store: PartsCatalogStore) -> None:
        self._parts_catalog_store = parts_catalog_store

    def build_catalog(
        self,
        paths: list[str] | None = None,
        reset: bool = True,
        max_files: int = 2000,
    ) -> dict[str, object]:
        return self._parts_catalog_store.build_catalog(
            paths=paths,
            reset=reset,
            max_files=max_files,
        )

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
        return self._parts_catalog_store.search_parts(
            query=query,
            kinds=kinds,
            layers=layers,
            path_prefixes=path_prefixes,
            intent_target=intent_target,
            prefer_code=prefer_code,
            prefer_docs=prefer_docs,
            limit=limit,
        )

    def get_parts(
        self,
        part_ids: list[str],
        max_chars_per_part: int = 20000,
    ) -> dict[str, object]:
        return self._parts_catalog_store.get_parts(
            part_ids=part_ids,
            max_chars_per_part=max_chars_per_part,
        )

    def export_selection(
        self,
        part_ids: list[str],
        target_dir: str,
        mode: str = "overwrite",
    ) -> dict[str, object]:
        return self._parts_catalog_store.export_selection(
            part_ids=part_ids,
            target_dir=target_dir,
            mode=mode,
        )

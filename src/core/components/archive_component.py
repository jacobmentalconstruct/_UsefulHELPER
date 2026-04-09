from __future__ import annotations

from ..services.archive_service import ArchiveService


class ArchiveComponent:
    """Owns bounded archive inspection and extraction behavior."""

    def __init__(self, archive_service: ArchiveService) -> None:
        self._archive_service = archive_service

    def inspect_zip(
        self,
        archive_path: str,
        max_entries: int = 500,
    ) -> dict[str, object]:
        return self._archive_service.inspect_zip(
            archive_path=archive_path,
            max_entries=max_entries,
        )

    def extract_zip(
        self,
        archive_path: str,
        target_dir: str,
        mode: str = "create_only",
    ) -> dict[str, object]:
        return self._archive_service.extract_zip(
            archive_path=archive_path,
            target_dir=target_dir,
            mode=mode,
        )

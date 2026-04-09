from __future__ import annotations

from ..services.archive_intake_service import ArchiveIntakeService


class IntakeComponent:
    """Owns bounded intake flows that normalize external bundles into sandbox state."""

    def __init__(self, archive_intake_service: ArchiveIntakeService) -> None:
        self._archive_intake_service = archive_intake_service

    def ingest_zip_to_sandbox(
        self,
        archive_path: str,
        target_dir: str,
        mode: str = "overwrite",
        reset_sandbox: bool = False,
        max_files: int = 1000,
        inspect_max_entries: int = 500,
    ) -> dict[str, object]:
        return self._archive_intake_service.ingest_zip_to_sandbox(
            archive_path=archive_path,
            target_dir=target_dir,
            mode=mode,
            reset_sandbox=reset_sandbox,
            max_files=max_files,
            inspect_max_entries=inspect_max_entries,
        )

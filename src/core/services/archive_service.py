from __future__ import annotations

import zipfile
from pathlib import Path, PurePosixPath

from .root_guard import RootGuard


class ArchiveService:
    """Owns bounded archive inspection and extraction helpers."""

    def __init__(self, root_guard: RootGuard) -> None:
        self._root_guard = root_guard

    def inspect_zip(
        self,
        archive_path: str,
        max_entries: int = 500,
    ) -> dict[str, object]:
        archive_file = self._resolve_archive_file(archive_path)
        entries: list[dict[str, object]] = []
        unsafe_entries: list[dict[str, object]] = []

        with zipfile.ZipFile(archive_file, "r") as archive:
            info_list = archive.infolist()
            for info in info_list[:max_entries]:
                member_path, reason = self._normalize_member_path(info.filename)
                entry = {
                    "name": info.filename,
                    "normalized_path": member_path,
                    "is_dir": info.is_dir(),
                    "file_size": info.file_size,
                    "compress_size": info.compress_size,
                    "is_safe": reason is None,
                }
                if reason is not None:
                    entry["unsafe_reason"] = reason
                    unsafe_entries.append(entry)
                entries.append(entry)

        return {
            "archive_path": self._root_guard.relative_path(archive_file),
            "entry_count": len(entries),
            "entries": entries,
            "unsafe_entries": unsafe_entries,
            "unsafe_entry_count": len(unsafe_entries),
            "truncated": len(entries) == max_entries and len(entries) < self._zip_entry_count(archive_file),
        }

    def extract_zip(
        self,
        archive_path: str,
        target_dir: str,
        mode: str = "create_only",
    ) -> dict[str, object]:
        if mode not in {"overwrite", "create_only"}:
            raise ValueError("Mode must be either 'overwrite' or 'create_only'.")

        archive_file = self._resolve_archive_file(archive_path)
        destination_root = self._root_guard.resolve_path(target_dir)
        destination_root.mkdir(parents=True, exist_ok=True)

        created_files: list[str] = []
        updated_files: list[str] = []
        skipped_files: list[str] = []
        created_directories: list[str] = []
        unsafe_entries: list[dict[str, object]] = []

        with zipfile.ZipFile(archive_file, "r") as archive:
            info_list = archive.infolist()
            normalized_members: list[tuple[zipfile.ZipInfo, str]] = []
            for info in info_list:
                normalized_path, reason = self._normalize_member_path(info.filename)
                if reason is not None:
                    unsafe_entries.append(
                        {
                            "name": info.filename,
                            "unsafe_reason": reason,
                        }
                    )
                    continue
                normalized_members.append((info, normalized_path))

            if unsafe_entries:
                raise ValueError(
                    f"Archive contains unsafe member paths and will not be extracted: {unsafe_entries}"
                )

            for info, normalized_path in normalized_members:
                destination_path = destination_root / Path(normalized_path)
                resolved_destination = destination_path.resolve()
                try:
                    resolved_destination.relative_to(destination_root.resolve())
                except ValueError as error:
                    raise ValueError(
                        f"Archive member '{info.filename}' resolves outside the target directory."
                    ) from error

                if info.is_dir():
                    if not resolved_destination.exists():
                        resolved_destination.mkdir(parents=True, exist_ok=True)
                        created_directories.append(
                            self._root_guard.relative_path(resolved_destination)
                        )
                    continue

                resolved_destination.parent.mkdir(parents=True, exist_ok=True)
                destination_relative = self._root_guard.relative_path(resolved_destination)
                if mode == "create_only" and resolved_destination.exists():
                    skipped_files.append(destination_relative)
                    continue

                existed = resolved_destination.exists()
                with archive.open(info, "r") as source_handle:
                    resolved_destination.write_bytes(source_handle.read())

                if existed:
                    updated_files.append(destination_relative)
                else:
                    created_files.append(destination_relative)

        return {
            "archive_path": self._root_guard.relative_path(archive_file),
            "target_dir": self._root_guard.relative_path(destination_root),
            "mode": mode,
            "created_directories": created_directories,
            "created_files": created_files,
            "updated_files": updated_files,
            "skipped_files": skipped_files,
            "file_count": len(created_files) + len(updated_files),
        }

    def _resolve_archive_file(self, archive_path: str) -> Path:
        archive_file = self._root_guard.resolve_path(archive_path)
        if not archive_file.exists():
            raise FileNotFoundError(f"Archive path '{archive_path}' does not exist.")
        if archive_file.is_dir():
            raise IsADirectoryError(f"Archive path '{archive_path}' is a directory.")
        if archive_file.suffix.lower() != ".zip":
            raise ValueError("Only .zip archives are supported in the current tranche.")
        return archive_file

    def _normalize_member_path(self, raw_name: str) -> tuple[str, str | None]:
        normalized = raw_name.replace("\\", "/").strip()
        if not normalized or normalized == ".":
            return "", "empty member path"

        path = PurePosixPath(normalized)
        if path.is_absolute():
            return normalized, "absolute member path"

        if any(part in {"", ".", ".."} for part in path.parts):
            return normalized, "path traversal or invalid segment"

        first_part = path.parts[0]
        if ":" in first_part:
            return normalized, "drive-qualified member path"

        return path.as_posix(), None

    def _zip_entry_count(self, archive_file: Path) -> int:
        with zipfile.ZipFile(archive_file, "r") as archive:
            return len(archive.infolist())

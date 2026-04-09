from __future__ import annotations

import json
from pathlib import Path

from .archive_service import ArchiveService
from .root_guard import RootGuard
from .sandbox_store import SandboxStore


class ArchiveIntakeService:
    """Owns one-call bounded archive intake into the sandbox workbench."""

    _SUMMARY_FILE_NAMES = {
        "app_manifest.json",
        "tool_manifest.json",
        "manifest.json",
        "package.json",
        "pyproject.toml",
        "README.md",
        "CONTRACT.md",
        "VENDORING.md",
        "requirements.txt",
        "settings.json",
        "ui_schema.json",
    }
    _ENTRYPOINT_NAME_PRIORITY = (
        "mcp_server.py",
        "app.py",
        "main.py",
        "server.py",
        "backend.py",
        "ui.py",
        "smoke_test.py",
    )

    def __init__(
        self,
        archive_service: ArchiveService,
        sandbox_store: SandboxStore,
        root_guard: RootGuard,
    ) -> None:
        self._archive_service = archive_service
        self._sandbox_store = sandbox_store
        self._root_guard = root_guard

    def ingest_zip_to_sandbox(
        self,
        archive_path: str,
        target_dir: str,
        mode: str = "overwrite",
        reset_sandbox: bool = False,
        max_files: int = 1000,
        inspect_max_entries: int = 500,
    ) -> dict[str, object]:
        if max_files < 1:
            raise ValueError("max_files must be at least 1.")
        if inspect_max_entries < 1:
            raise ValueError("inspect_max_entries must be at least 1.")

        initialization = self._sandbox_store.initialize(reset=reset_sandbox)
        inspection = self._archive_service.inspect_zip(
            archive_path=archive_path,
            max_entries=inspect_max_entries,
        )
        extraction = self._archive_service.extract_zip(
            archive_path=archive_path,
            target_dir=target_dir,
            mode=mode,
        )
        ingestion = self._sandbox_store.ingest_workspace(
            paths=[target_dir],
            max_files=max_files,
        )
        bundle_summary = self._build_bundle_summary(
            target_dir=extraction["target_dir"],
            inspection=inspection,
        )
        likely_entrypoints = self._detect_likely_entrypoints(
            target_dir=extraction["target_dir"],
            inspection=inspection,
        )

        return {
            "archive_path": inspection["archive_path"],
            "target_dir": extraction["target_dir"],
            "reset_sandbox": reset_sandbox,
            "initialization": initialization,
            "inspection": inspection,
            "extraction": extraction,
            "ingestion": ingestion,
            "unsafe_entry_count": inspection["unsafe_entry_count"],
            "extracted_file_count": extraction["file_count"],
            "sandbox_head_file_count": ingestion["head_file_count"],
            "sandbox_revision_count": ingestion["revision_count"],
            "bundle_summary": bundle_summary,
            "likely_entrypoints": likely_entrypoints,
        }

    def _build_bundle_summary(
        self,
        target_dir: str,
        inspection: dict[str, object],
    ) -> dict[str, object]:
        safe_paths = [
            str(entry["normalized_path"])
            for entry in inspection.get("entries", [])
            if bool(entry.get("is_safe")) and not bool(entry.get("is_dir"))
        ]
        summary_files = [
            path for path in safe_paths if Path(path).name in self._SUMMARY_FILE_NAMES
        ]
        top_level_items = sorted({Path(path).parts[0] for path in safe_paths if Path(path).parts})
        top_level_python_files = sorted(
            {
                path
                for path in safe_paths
                if len(Path(path).parts) == 1 and path.endswith(".py")
            }
        )

        manifest_details: list[dict[str, object]] = []
        for relative_path in summary_files[:10]:
            detail = self._read_manifest_detail(target_dir=target_dir, relative_path=relative_path)
            if detail is not None:
                manifest_details.append(detail)

        return {
            "top_level_items": top_level_items[:20],
            "top_level_python_files": top_level_python_files[:10],
            "summary_files": summary_files[:20],
            "manifest_details": manifest_details,
        }

    def _detect_likely_entrypoints(
        self,
        target_dir: str,
        inspection: dict[str, object],
    ) -> list[dict[str, object]]:
        safe_paths = [
            str(entry["normalized_path"])
            for entry in inspection.get("entries", [])
            if bool(entry.get("is_safe")) and not bool(entry.get("is_dir"))
        ]
        candidates: list[dict[str, object]] = []
        seen_paths: set[str] = set()

        for manifest_path in safe_paths:
            path_name = Path(manifest_path).name
            if path_name not in {"app_manifest.json", "tool_manifest.json", "package.json"}:
                continue
            for candidate in self._entrypoints_from_manifest(
                target_dir=target_dir,
                manifest_path=manifest_path,
            ):
                candidate_path = str(candidate["path"])
                if candidate_path in seen_paths:
                    continue
                seen_paths.add(candidate_path)
                candidates.append(candidate)

        for candidate_name in self._ENTRYPOINT_NAME_PRIORITY:
            for relative_path in safe_paths:
                if Path(relative_path).name != candidate_name:
                    continue
                if relative_path in seen_paths:
                    continue
                seen_paths.add(relative_path)
                candidates.append(
                    {
                        "path": relative_path,
                        "reason": f"matched common entrypoint name '{candidate_name}'",
                        "confidence": "medium",
                    }
                )

        return candidates[:12]

    def _read_manifest_detail(
        self,
        target_dir: str,
        relative_path: str,
    ) -> dict[str, object] | None:
        file_path = self._root_guard.resolve_path(f"{target_dir}/{relative_path}")
        if not file_path.exists() or not file_path.is_file():
            return None

        file_name = file_path.name
        detail: dict[str, object] = {"path": relative_path, "kind": file_name}

        if file_path.suffix.lower() == ".json":
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return detail

            if isinstance(payload, dict):
                for key in (
                    "name",
                    "version",
                    "description",
                    "mcp_entrypoint",
                    "self_test_entrypoint",
                    "human_guide",
                    "protocol_guide",
                    "vendoring_guide",
                ):
                    if key in payload:
                        detail[key] = payload[key]
            return detail

        try:
            content = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return detail

        first_lines = [
            line.strip()
            for line in content.splitlines()
            if line.strip()
        ]
        if first_lines:
            detail["preview"] = first_lines[0][:160]
        return detail

    def _entrypoints_from_manifest(
        self,
        target_dir: str,
        manifest_path: str,
    ) -> list[dict[str, object]]:
        file_path = self._root_guard.resolve_path(f"{target_dir}/{manifest_path}")
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return []
        if not isinstance(payload, dict):
            return []

        candidates: list[dict[str, object]] = []
        for key, reason in (
            ("mcp_entrypoint", "declared as MCP entrypoint in manifest"),
            ("self_test_entrypoint", "declared as self-test entrypoint in manifest"),
            ("human_guide", "declared as human guide in manifest"),
            ("protocol_guide", "declared as protocol guide in manifest"),
            ("vendoring_guide", "declared as vendoring guide in manifest"),
            ("main", "declared as main entrypoint in manifest"),
        ):
            value = payload.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            candidates.append(
                {
                    "path": value.strip().replace("\\", "/"),
                    "reason": reason,
                    "confidence": "high",
                }
            )

        if isinstance(payload.get("bin"), str):
            candidates.append(
                {
                    "path": str(payload["bin"]).strip().replace("\\", "/"),
                    "reason": "declared as binary entrypoint in manifest",
                    "confidence": "high",
                }
            )

        return candidates

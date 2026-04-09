from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ...config import AppConfig
from ..services.root_guard import RootGuard


@dataclass(frozen=True)
class SidecarFileSpec:
    relative_path: Path
    content: str
    generated: bool


class SidecarComponent:
    """Owns vendorable sidecar bundle export from the worker source tree."""

    _ROOT_FILE_ALLOWLIST = (
        ".gitignore",
        "README.md",
        "LICENSE.md",
        "requirements.txt",
        "setup_env.bat",
        "run.bat",
    )
    _DOC_FILE_ALLOWLIST = (
        "_docs/builder_constraint_contract.md",
        "_docs/ARCHITECTURE.md",
        "_docs/ONBOARDING.md",
        "_docs/TOOLS.md",
        "_docs/TODO.md",
        "_docs/WORKER_MICRO_CONTRACT.md",
        "_docs/TESTING.md",
        "_docs/dev_log.md",
        "_docs/tool_blueprints/ollama_chat_json.json",
        "_docs/tool_blueprints/ollama_chat_json.md",
        "_docs/_AppJOURNAL/README.md",
        "_docs/_AppJOURNAL/BACKLOG.md",
        "_docs/_AppJOURNAL/CURRENT_TASKLIST.md",
    )
    _TREE_ALLOWLIST = ("src",)
    _TEXT_SUFFIX_ALLOWLIST = {
        ".py",
        ".md",
        ".bat",
        ".txt",
        ".json",
    }
    _BUNDLE_NAME = "usefulhelper-sidecar"
    _MANIFEST_SCHEMA_VERSION = 2

    def __init__(self, config: AppConfig, root_guard: RootGuard) -> None:
        self._config = config
        self._root_guard = root_guard

    def export_bundle(
        self,
        target_dir: str,
        include_tests: bool = False,
        overwrite: bool = False,
        dry_run: bool = False,
        reinstall: bool = False,
    ) -> dict[str, object]:
        export_root = self._root_guard.resolve_path(target_dir)
        export_root_relative = self._root_guard.relative_path(export_root)
        plan = self._build_install_plan(
            export_root=export_root,
            export_root_relative=export_root_relative,
            include_tests=include_tests,
        )

        if dry_run:
            return self._build_result(
                plan=plan,
                overwrite=overwrite,
                dry_run=True,
                reinstall=reinstall,
                created_files=[],
                overwritten_files=[],
                applied=False,
            )

        self._validate_install_request(
            plan=plan,
            overwrite=overwrite,
            reinstall=reinstall,
        )
        if not plan["planned_created_files"] and not plan["planned_updated_files"]:
            return self._build_result(
                plan=plan,
                overwrite=overwrite,
                dry_run=False,
                reinstall=reinstall,
                created_files=[],
                overwritten_files=[],
                applied=False,
            )

        export_root.mkdir(parents=True, exist_ok=True)
        created_files, overwritten_files = self._apply_plan(
            export_root=export_root,
            desired_files=plan["desired_files"],
            planned_created_files=plan["planned_created_files"],
            planned_updated_files=plan["planned_updated_files"],
        )
        return self._build_result(
            plan=plan,
            overwrite=overwrite,
            dry_run=False,
            reinstall=reinstall,
            created_files=created_files,
            overwritten_files=overwritten_files,
            applied=True,
        )

    def _collect_source_files(self, include_tests: bool) -> list[Path]:
        collected: list[Path] = []
        seen: set[str] = set()

        def add_path(relative_path: Path) -> None:
            normalized = relative_path.as_posix()
            if normalized not in seen:
                seen.add(normalized)
                collected.append(relative_path)

        for file_name in self._ROOT_FILE_ALLOWLIST:
            add_path(Path(file_name))

        for file_name in self._DOC_FILE_ALLOWLIST:
            add_path(Path(file_name))

        for tree_name in self._TREE_ALLOWLIST:
            tree_root = self._config.source_root / tree_name
            for file_path in sorted(tree_root.rglob("*")):
                if file_path.is_file() and self._is_exportable_source_file(file_path):
                    add_path(file_path.relative_to(self._config.source_root))

        if include_tests:
            test_root = self._config.source_root / "tests"
            if test_root.exists():
                for file_path in sorted(test_root.rglob("*")):
                    if file_path.is_file() and self._is_exportable_source_file(file_path):
                        add_path(file_path.relative_to(self._config.source_root))

        return collected

    def _is_exportable_source_file(self, file_path: Path) -> bool:
        if "__pycache__" in file_path.parts:
            return False
        if file_path.name.startswith(".") and file_path.name != ".gitignore":
            return False
        return file_path.suffix.lower() in self._TEXT_SUFFIX_ALLOWLIST or file_path.name == ".gitignore"

    def _build_generated_file_specs(
        self,
        export_root_relative: str,
        include_tests: bool,
    ) -> list[SidecarFileSpec]:
        relative_app_root = self._relative_path_to_workspace_root(export_root_relative)
        managed_files = self._collect_managed_file_relatives(include_tests=include_tests)
        generated_specs = [
            SidecarFileSpec(
                relative_path=Path("run_for_app.bat"),
                content=self._render_run_for_app(relative_app_root),
                generated=True,
            ),
            SidecarFileSpec(
                relative_path=Path("sidecar_manifest.json"),
                content=self._render_sidecar_manifest(
                    export_root_relative=export_root_relative,
                    relative_app_root=relative_app_root,
                    include_tests=include_tests,
                    managed_files=managed_files,
                ),
                generated=True,
            ),
            SidecarFileSpec(
                relative_path=Path("_docs/SIDECAR.md"),
                content=self._render_sidecar_readme(
                    export_root_relative=export_root_relative,
                    relative_app_root=relative_app_root,
                ),
                generated=True,
            ),
        ]
        return generated_specs

    def _collect_desired_files(
        self,
        export_root_relative: str,
        include_tests: bool,
    ) -> list[SidecarFileSpec]:
        desired_files: list[SidecarFileSpec] = []
        for relative_source_path in self._collect_source_files(include_tests=include_tests):
            source_path = self._config.source_root / relative_source_path
            desired_files.append(
                SidecarFileSpec(
                    relative_path=relative_source_path,
                    content=source_path.read_text(encoding="utf-8"),
                    generated=False,
                )
            )
        desired_files.extend(
            self._build_generated_file_specs(
                export_root_relative=export_root_relative,
                include_tests=include_tests,
            )
        )
        return sorted(desired_files, key=lambda item: item.relative_path.as_posix())

    def _collect_managed_file_relatives(self, include_tests: bool) -> list[str]:
        managed = {
            relative_path.as_posix()
            for relative_path in self._collect_source_files(include_tests=include_tests)
        }
        managed.update(
            {
                "run_for_app.bat",
                "sidecar_manifest.json",
                "_docs/SIDECAR.md",
            }
        )
        return sorted(managed)

    def _build_install_plan(
        self,
        export_root: Path,
        export_root_relative: str,
        include_tests: bool,
    ) -> dict[str, object]:
        desired_files = self._collect_desired_files(
            export_root_relative=export_root_relative,
            include_tests=include_tests,
        )
        desired_by_relative = {
            item.relative_path.as_posix(): item for item in desired_files
        }

        target_exists = export_root.exists()
        target_non_empty = target_exists and any(export_root.iterdir())
        existing_file_relatives = (
            sorted(
                path.relative_to(export_root).as_posix()
                for path in export_root.rglob("*")
                if path.is_file()
            )
            if target_exists
            else []
        )

        existing_manifest, recognized_existing_sidecar = self._read_existing_manifest(export_root)
        install_state = self._classify_install_state(
            target_exists=target_exists,
            target_non_empty=target_non_empty,
            recognized_existing_sidecar=recognized_existing_sidecar,
        )

        planned_created_files: list[str] = []
        planned_updated_files: list[str] = []
        unchanged_files: list[str] = []

        for relative_path, file_spec in desired_by_relative.items():
            destination_path = export_root / file_spec.relative_path
            if not destination_path.exists():
                planned_created_files.append(relative_path)
                continue
            existing_content = destination_path.read_text(encoding="utf-8")
            if existing_content == file_spec.content:
                unchanged_files.append(relative_path)
            else:
                planned_updated_files.append(relative_path)

        desired_relative_set = set(desired_by_relative)
        unmanaged_existing_files = sorted(
            relative_path
            for relative_path in existing_file_relatives
            if relative_path not in desired_relative_set
        )
        stale_managed_files = self._collect_stale_managed_files(
            existing_manifest=existing_manifest,
            desired_relative_set=desired_relative_set,
            existing_file_relatives=existing_file_relatives,
        )

        generated_relative_set = {
            item.relative_path.as_posix()
            for item in desired_files
            if item.generated
        }
        return {
            "target_dir": export_root_relative,
            "source_project_root": str(self._config.source_root),
            "workspace_root": str(self._config.workspace_root),
            "include_tests": include_tests,
            "install_state": install_state,
            "target_exists": target_exists,
            "target_non_empty": target_non_empty,
            "recognized_existing_sidecar": recognized_existing_sidecar,
            "existing_manifest": existing_manifest,
            "desired_files": desired_files,
            "managed_files": sorted(desired_relative_set),
            "generated_files": sorted(generated_relative_set),
            "planned_created_files": planned_created_files,
            "planned_updated_files": planned_updated_files,
            "unchanged_files": unchanged_files,
            "unmanaged_existing_files": unmanaged_existing_files,
            "stale_managed_files": stale_managed_files,
            "existing_file_count": len(existing_file_relatives),
        }

    def _read_existing_manifest(self, export_root: Path) -> tuple[dict[str, object] | None, bool]:
        manifest_path = export_root / "sidecar_manifest.json"
        if not manifest_path.exists():
            return None, False
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, False
        recognized = payload.get("bundle_name") == self._BUNDLE_NAME
        return payload, recognized

    def _classify_install_state(
        self,
        target_exists: bool,
        target_non_empty: bool,
        recognized_existing_sidecar: bool,
    ) -> str:
        if not target_exists:
            return "missing_target"
        if not target_non_empty:
            return "empty_target"
        if recognized_existing_sidecar:
            return "existing_sidecar"
        return "occupied_non_sidecar"

    def _collect_stale_managed_files(
        self,
        existing_manifest: dict[str, object] | None,
        desired_relative_set: set[str],
        existing_file_relatives: list[str],
    ) -> list[str]:
        if existing_manifest is None:
            return []
        previous_managed = existing_manifest.get("managed_files")
        if not isinstance(previous_managed, list):
            return []
        existing_file_set = set(existing_file_relatives)
        return sorted(
            relative_path
            for relative_path in previous_managed
            if isinstance(relative_path, str)
            and relative_path not in desired_relative_set
            and relative_path in existing_file_set
        )

    def _validate_install_request(
        self,
        plan: dict[str, object],
        overwrite: bool,
        reinstall: bool,
    ) -> None:
        install_state = str(plan["install_state"])
        planned_created_files = list(plan["planned_created_files"])
        planned_updated_files = list(plan["planned_updated_files"])
        target_non_empty = bool(plan["target_non_empty"])

        if install_state == "occupied_non_sidecar":
            raise ValueError(
                "Target export directory already contains files that are not a recognized UsefulHELPER sidecar. "
                "Run with dry_run=true to inspect the managed diff, then choose an empty directory or a recognized sidecar target."
            )

        if install_state == "existing_sidecar":
            if planned_created_files or planned_updated_files:
                if not overwrite or not reinstall:
                    raise ValueError(
                        "Target export directory already contains a UsefulHELPER sidecar. "
                        "Review the diff with dry_run=true, then rerun with overwrite=true and reinstall=true to apply the update."
                    )
            return

        if target_non_empty and not overwrite:
            raise ValueError(
                "Target export directory is not empty. Pass overwrite=true only when creating into a known empty or disposable target."
            )

    def _apply_plan(
        self,
        export_root: Path,
        desired_files: list[SidecarFileSpec],
        planned_created_files: list[str],
        planned_updated_files: list[str],
    ) -> tuple[list[str], list[str]]:
        created_files: list[str] = []
        overwritten_files: list[str] = []
        writable_paths = set(planned_created_files) | set(planned_updated_files)
        for file_spec in desired_files:
            relative_path = file_spec.relative_path.as_posix()
            if relative_path not in writable_paths:
                continue
            destination_path = export_root / file_spec.relative_path
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            existed = destination_path.exists()
            destination_path.write_text(file_spec.content, encoding="utf-8")
            destination_relative = self._root_guard.relative_path(destination_path)
            if existed:
                overwritten_files.append(destination_relative)
            else:
                created_files.append(destination_relative)
        return created_files, overwritten_files

    def _build_result(
        self,
        plan: dict[str, object],
        overwrite: bool,
        dry_run: bool,
        reinstall: bool,
        created_files: list[str],
        overwritten_files: list[str],
        applied: bool,
    ) -> dict[str, object]:
        return {
            "target_dir": plan["target_dir"],
            "source_project_root": plan["source_project_root"],
            "workspace_root": plan["workspace_root"],
            "include_tests": plan["include_tests"],
            "overwrite": overwrite,
            "dry_run": dry_run,
            "reinstall": reinstall,
            "applied": applied,
            "install_state": plan["install_state"],
            "recognized_existing_sidecar": plan["recognized_existing_sidecar"],
            "existing_manifest": plan["existing_manifest"],
            "managed_file_count": len(plan["managed_files"]),
            "generated_file_count": len(plan["generated_files"]),
            "existing_file_count": plan["existing_file_count"],
            "planned_created_files": plan["planned_created_files"],
            "planned_updated_files": plan["planned_updated_files"],
            "planned_change_count": len(plan["planned_created_files"]) + len(plan["planned_updated_files"]),
            "unchanged_files": plan["unchanged_files"],
            "unmanaged_existing_files": plan["unmanaged_existing_files"],
            "stale_managed_files": plan["stale_managed_files"],
            "created_files": created_files,
            "overwritten_files": overwritten_files,
        }

    def _relative_path_to_workspace_root(self, export_root_relative: str) -> str:
        relative_path = PurePosixPath(export_root_relative)
        parts = [part for part in relative_path.parts if part not in (".", "")]
        if not parts:
            return "."
        return "\\".join(".." for _ in parts)

    def _render_run_for_app(self, relative_app_root: str) -> str:
        workspace_expr = "%~dp0" if relative_app_root == "." else f"%~dp0{relative_app_root}"
        return (
            "@echo off\n"
            "setlocal\n\n"
            f'set "APP_ROOT={workspace_expr}"\n'
            'set "SIDECAR_ROOT=%~dp0"\n\n'
            'if not exist "%SIDECAR_ROOT%\\.venv\\Scripts\\python.exe" (\n'
            "    echo Virtual environment not found. Run setup_env.bat first.\n"
            "    exit /b 1\n"
            ")\n\n"
            'call "%SIDECAR_ROOT%\\.venv\\Scripts\\activate.bat"\n'
            'python -m src.app --project-root "%SIDECAR_ROOT%" --workspace-root "%APP_ROOT%" %*\n'
            "set EXIT_CODE=%ERRORLEVEL%\n\n"
            "endlocal & exit /b %EXIT_CODE%\n"
        )

    def _render_sidecar_manifest(
        self,
        export_root_relative: str,
        relative_app_root: str,
        include_tests: bool,
        managed_files: list[str],
    ) -> str:
        payload = {
            "bundle_name": self._BUNDLE_NAME,
            "manifest_schema_version": self._MANIFEST_SCHEMA_VERSION,
            "server_name": self._config.server_name,
            "server_version": self._config.server_version,
            "bundle_layout_version": self._config.server_version,
            "source_project_root": str(self._config.source_root),
            "export_root_relative": export_root_relative,
            "relative_app_root_from_sidecar": relative_app_root,
            "include_tests": include_tests,
            "managed_files": managed_files,
            "guardrails": {
                "single_workspace_root_per_session": True,
                "absolute_paths_allowed": False,
                "raw_shell_enabled": False,
            },
        }
        return json.dumps(payload, indent=2) + "\n"

    def _render_sidecar_readme(
        self,
        export_root_relative: str,
        relative_app_root: str,
    ) -> str:
        return "\n".join(
            [
                "# Vendored UsefulHELPER Sidecar",
                "",
                f"- Export root: `{export_root_relative}`",
                f"- Relative app root from this sidecar: `{relative_app_root}`",
                "",
                "## Usage",
                "",
                "1. Run `setup_env.bat` inside this sidecar folder.",
                "2. Run `run_for_app.bat --transport ndjson` or `run_for_app.bat --transport content-length`.",
                "3. The sidecar will treat the parent app root as its workspace root for tool calls.",
                "4. Use `sidecar.export_bundle` with `dry_run=true` before reinstalling into an existing sidecar target.",
                "5. If the target is a recognized existing sidecar, rerun with `overwrite=true` and `reinstall=true` after reviewing the diff.",
                "6. Read `_docs/ONBOARDING.md` and `_docs/TODO.md` before extending the vendored copy.",
                "",
                "## Guardrails",
                "",
                "- writes remain bounded to the app root used as the workspace root",
                "- absolute tool paths are rejected",
                "- this bundle does not expose a raw shell tool",
                "- overwrite writes are blocked for non-sidecar populated targets",
                "- unmanaged files inside an existing sidecar target are reported and preserved",
                "- the vendored copy carries its own contract, onboarding, TODO, and dev-log mirrors",
                "",
            ]
        ) + "\n"

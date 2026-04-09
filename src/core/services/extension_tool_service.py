from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from ..models.tooling import ToolRoute


def _snake_case(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_").lower()
    return cleaned or "tool"


@dataclass(frozen=True, slots=True)
class LoadedExtensionTool:
    route: ToolRoute
    manifest_path: str
    component_module: str
    component_class: str
    method_name: str
    status: str
    component_instance: object


class ExtensionToolService:
    """Loads validated extension-tool blueprints and invokes them through a bounded dispatch lane."""

    _ALLOWED_MANAGERS = {"workspace", "memory"}
    _ALLOWED_COMPONENT_PREFIX = "src.core.components.extensions."
    _DEFAULT_INPUT_SCHEMA: dict[str, Any] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }

    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._blueprint_dir = project_root / "_docs" / "tool_blueprints"
        self._loaded_tools: dict[str, LoadedExtensionTool] = {}

    def refresh_extensions(
        self,
        reserved_tool_names: set[str],
    ) -> tuple[list[ToolRoute], dict[str, object]]:
        self._blueprint_dir.mkdir(parents=True, exist_ok=True)
        loaded_tools: dict[str, LoadedExtensionTool] = {}
        routes: list[ToolRoute] = []
        loaded: list[dict[str, object]] = []
        skipped: list[dict[str, object]] = []
        errors: list[dict[str, object]] = []

        for manifest_file in sorted(self._blueprint_dir.glob("*.json")):
            manifest_path = manifest_file.resolve()
            relative_manifest_path = manifest_path.relative_to(self._project_root).as_posix()
            try:
                manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                errors.append(
                    {
                        "manifest_path": relative_manifest_path,
                        "error": f"Manifest could not be parsed: {error}",
                    }
                )
                continue

            validation_error = self._validate_manifest(manifest, relative_manifest_path)
            if validation_error is not None:
                skipped.append(
                    {
                        "manifest_path": relative_manifest_path,
                        "reason": validation_error,
                    }
                )
                continue

            tool_name = str(manifest["tool_name"])
            if tool_name in reserved_tool_names:
                skipped.append(
                    {
                        "manifest_path": relative_manifest_path,
                        "tool_name": tool_name,
                        "reason": "tool name already belongs to a statically registered route",
                    }
                )
                continue

            status = str(manifest.get("status", "draft")).strip().lower() or "draft"
            if status in {"disabled", "archived"}:
                skipped.append(
                    {
                        "manifest_path": relative_manifest_path,
                        "tool_name": tool_name,
                        "reason": f"manifest status '{status}' is not loadable",
                    }
                )
                continue

            try:
                loaded_tool = self._load_tool_from_manifest(
                    manifest=manifest,
                    manifest_path=relative_manifest_path,
                    status=status,
                )
            except Exception as error:  # noqa: BLE001
                errors.append(
                    {
                        "manifest_path": relative_manifest_path,
                        "tool_name": tool_name,
                        "error": str(error),
                    }
                )
                continue

            loaded_tools[tool_name] = loaded_tool
            routes.append(loaded_tool.route)
            loaded.append(
                {
                    "tool_name": tool_name,
                    "manifest_path": relative_manifest_path,
                    "manager": loaded_tool.route.manager,
                    "component_module": loaded_tool.component_module,
                    "component_class": loaded_tool.component_class,
                    "method_name": loaded_tool.method_name,
                    "status": status,
                }
            )

        removed_tool_names = sorted(set(self._loaded_tools) - set(loaded_tools))
        self._loaded_tools = loaded_tools
        result = {
            "manifest_dir": self._blueprint_dir.as_posix(),
            "manifest_count": len(list(self._blueprint_dir.glob("*.json"))),
            "loaded_count": len(loaded),
            "loaded_tools": loaded,
            "skipped_count": len(skipped),
            "skipped": skipped,
            "error_count": len(errors),
            "errors": errors,
            "removed_tool_names": removed_tool_names,
        }
        return routes, result

    def invoke_tool(self, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        if tool_name not in self._loaded_tools:
            raise KeyError(f"Extension tool '{tool_name}' is not loaded.")
        loaded_tool = self._loaded_tools[tool_name]
        method = getattr(loaded_tool.component_instance, loaded_tool.method_name, None)
        if method is None or not callable(method):
            raise AttributeError(
                f"Extension tool '{tool_name}' is missing callable method '{loaded_tool.method_name}'."
            )
        result = method(arguments)
        if not isinstance(result, dict):
            raise TypeError(
                f"Extension tool '{tool_name}' returned {type(result).__name__}; expected dict."
            )
        return result

    def loaded_tool_names(self) -> list[str]:
        return sorted(self._loaded_tools)

    def _validate_manifest(
        self,
        manifest: object,
        manifest_path: str,
    ) -> str | None:
        if not isinstance(manifest, dict):
            return "manifest root must be a JSON object"

        required_fields = {
            "tool_name",
            "description",
            "manager",
            "action",
            "component_module",
            "component_class",
        }
        missing = sorted(field for field in required_fields if field not in manifest)
        if missing:
            return f"manifest is missing required field(s): {', '.join(missing)}"

        manager = str(manifest["manager"])
        if manager not in self._ALLOWED_MANAGERS:
            return (
                f"manager '{manager}' is not hot-reloadable in the current tranche; "
                f"expected one of: {', '.join(sorted(self._ALLOWED_MANAGERS))}"
            )

        component_module = str(manifest["component_module"])
        if not component_module.startswith(self._ALLOWED_COMPONENT_PREFIX):
            return (
                f"component_module '{component_module}' is outside the allowed extension package "
                f"'{self._ALLOWED_COMPONENT_PREFIX}'"
            )

        if not self._manifest_module_file(component_module).exists():
            return f"component module file for '{component_module}' does not exist"

        input_schema = manifest.get("input_schema")
        if input_schema is not None and not isinstance(input_schema, dict):
            return "input_schema must be a JSON object when provided"

        return None

    def _load_tool_from_manifest(
        self,
        manifest: dict[str, object],
        manifest_path: str,
        status: str,
    ) -> LoadedExtensionTool:
        tool_name = str(manifest["tool_name"])
        component_module_name = str(manifest["component_module"])
        component_class_name = str(manifest["component_class"])
        action = str(manifest["action"])
        method_name = str(manifest.get("method_name") or _snake_case(action))
        input_schema = manifest.get("input_schema")
        if not isinstance(input_schema, dict):
            input_schema = dict(self._DEFAULT_INPUT_SCHEMA)

        module = self._import_extension_module(component_module_name)
        component_class = getattr(module, component_class_name, None)
        if component_class is None:
            raise AttributeError(
                f"Component class '{component_class_name}' was not found in '{component_module_name}'."
            )
        component_instance = component_class()
        if not hasattr(component_instance, method_name):
            raise AttributeError(
                f"Component '{component_class_name}' does not expose method '{method_name}'."
            )

        route = ToolRoute(
            name=tool_name,
            description=str(manifest["description"]),
            input_schema=input_schema,
            manager=str(manifest["manager"]),
            action="extension.run",
        )
        return LoadedExtensionTool(
            route=route,
            manifest_path=manifest_path,
            component_module=component_module_name,
            component_class=component_class_name,
            method_name=method_name,
            status=status,
            component_instance=component_instance,
        )

    def _import_extension_module(self, component_module_name: str) -> ModuleType:
        module = importlib.import_module(component_module_name)
        return importlib.reload(module)

    def _manifest_module_file(self, component_module_name: str) -> Path:
        return self._project_root / Path(component_module_name.replace(".", "/")).with_suffix(".py")

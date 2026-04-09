from __future__ import annotations

from ..models.tooling import ToolRoute
from ..services.extension_tool_service import ExtensionToolService


class ExtensionToolComponent:
    """Owns validated extension-tool refresh and generic dispatch behavior."""

    def __init__(self, extension_tool_service: ExtensionToolService) -> None:
        self._extension_tool_service = extension_tool_service

    def refresh_extensions(
        self,
        reserved_tool_names: set[str],
    ) -> tuple[list[ToolRoute], dict[str, object]]:
        return self._extension_tool_service.refresh_extensions(
            reserved_tool_names=reserved_tool_names
        )

    def invoke_tool(self, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
        return self._extension_tool_service.invoke_tool(
            tool_name=tool_name,
            arguments=arguments,
        )

    def loaded_tool_names(self) -> list[str]:
        return self._extension_tool_service.loaded_tool_names()

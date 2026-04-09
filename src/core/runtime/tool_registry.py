from __future__ import annotations

from typing import Any

from ..models.tooling import ToolRoute


class ToolRegistry:
    """Stores the worker's tool metadata and routing rules."""

    def __init__(self) -> None:
        self._routes: dict[str, ToolRoute] = {}

    def register(self, route: ToolRoute) -> None:
        if route.name in self._routes:
            raise ValueError(f"Tool '{route.name}' is already registered.")
        self._routes[route.name] = route

    def get(self, name: str) -> ToolRoute:
        if name not in self._routes:
            raise KeyError(name)
        return self._routes[name]

    def unregister(self, name: str) -> None:
        if name in self._routes:
            del self._routes[name]

    def list_tools(self) -> list[dict[str, Any]]:
        return [route.to_mcp_tool() for route in self._routes.values()]

    def tool_names(self) -> list[str]:
        return sorted(self._routes)

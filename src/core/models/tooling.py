from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolRoute:
    """Metadata and routing data for a registered worker tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    manager: str
    action: str

    def to_mcp_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }

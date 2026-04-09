from __future__ import annotations

from ..runtime.tool_registry import ToolRegistry
from ...config import AppConfig


class CapabilityComponent:
    """Owns worker self-description and capability reporting."""

    def __init__(self, config: AppConfig, registry: ToolRegistry) -> None:
        self._config = config
        self._registry = registry

    def describe_capabilities(self) -> dict[str, object]:
        tool_names = self._registry.tool_names()
        return {
            "server_name": self._config.server_name,
            "server_version": self._config.server_version,
            "source_root": str(self._config.source_root),
            "project_root": str(self._config.project_root),
            "workspace_root": str(self._config.workspace_root),
            "workspace_guardrails": {
                "single_root_per_session": True,
                "absolute_paths_allowed": False,
                "raw_shell_enabled": False,
            },
            "tool_count": len(tool_names),
            "tool_names": tool_names,
            "local_model_support": {
                "status": "planned",
                "note": "Deterministic self-extension tooling is implemented first; Ollama integration is deferred.",
            },
        }

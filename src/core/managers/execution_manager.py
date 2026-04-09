from __future__ import annotations

from ..components.execution_component import ExecutionComponent
from ..runtime.messages import Message
from ..runtime.nodes import GraphNode


class ExecutionManager(GraphNode):
    """Coordinates bounded allowlisted execution helpers."""

    def __init__(self, execution_component: ExecutionComponent) -> None:
        super().__init__(node_id="core.execution_manager", node_type="manager")
        self._execution_component = execution_component

    def receive(self, message: Message) -> dict[str, object]:
        arguments = message.payload.get("arguments", {})
        self.local_state["last_action"] = message.action

        if message.action == "python.run_unittest":
            result = self._execution_component.run_unittest(
                start_dir=str(arguments.get("start_dir", ".")),
                pattern=str(arguments.get("pattern", "test*.py")),
                top_level_dir=(
                    None
                    if arguments.get("top_level_dir") is None
                    else str(arguments.get("top_level_dir"))
                ),
                timeout_seconds=int(arguments.get("timeout_seconds", 120)),
            )
        elif message.action == "python.run_compileall":
            result = self._execution_component.run_compileall(
                paths=list(arguments.get("paths", ["."])),
                timeout_seconds=int(arguments.get("timeout_seconds", 120)),
            )
        elif message.action == "sysops.git_status":
            result = self._execution_component.git_status(
                path=str(arguments.get("path", ".")),
                timeout_seconds=int(arguments.get("timeout_seconds", 30)),
            )
        elif message.action == "sysops.git_diff_summary":
            result = self._execution_component.git_diff_summary(
                path=str(arguments.get("path", ".")),
                cached=bool(arguments.get("cached", False)),
                timeout_seconds=int(arguments.get("timeout_seconds", 30)),
            )
        elif message.action == "sysops.git_repo_summary":
            result = self._execution_component.git_repo_summary(
                path=str(arguments.get("path", ".")),
                timeout_seconds=int(arguments.get("timeout_seconds", 30)),
            )
        elif message.action == "sysops.git_recent_commits":
            result = self._execution_component.git_recent_commits(
                path=str(arguments.get("path", ".")),
                limit=int(arguments.get("limit", 10)),
                ref=str(arguments.get("ref", "HEAD")),
                timeout_seconds=int(arguments.get("timeout_seconds", 30)),
            )
        else:
            raise ValueError(f"Unsupported execution action '{message.action}'.")

        return {
            "text": f"Execution action '{message.action}' completed.",
            "structured_content": result,
            "is_error": False,
        }

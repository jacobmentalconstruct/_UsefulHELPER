from __future__ import annotations

from ..components.builder_memory_component import BuilderMemoryComponent
from ..components.extension_tool_component import ExtensionToolComponent
from ..runtime.messages import Message
from ..runtime.nodes import GraphNode


class MemoryManager(GraphNode):
    """Coordinates builder-memory journal and tasklist behavior."""

    def __init__(
        self,
        builder_memory_component: BuilderMemoryComponent,
        extension_tool_component: ExtensionToolComponent,
    ) -> None:
        super().__init__(node_id="core.memory_manager", node_type="manager")
        self._builder_memory_component = builder_memory_component
        self._extension_tool_component = extension_tool_component

    def receive(self, message: Message) -> dict[str, object]:
        arguments = message.payload.get("arguments", {})
        self.local_state["last_action"] = message.action

        if message.action == "journal.append":
            result = self._builder_memory_component.append_journal(
                title=str(arguments["title"]),
                summary=str(arguments["summary"]),
                files_changed=list(arguments.get("files_changed", [])),
                notes=list(arguments.get("notes", [])),
                testing=list(arguments.get("testing", [])),
                backlog=list(arguments.get("backlog", [])),
            )
        elif message.action == "tasklist.replace":
            result = self._builder_memory_component.replace_tasklist(
                items=list(arguments.get("items", []))
            )
        elif message.action == "tasklist.view":
            result = self._builder_memory_component.view_tasklist()
        elif message.action == "extension.run":
            result = self._extension_tool_component.invoke_tool(
                tool_name=str(message.payload["route_name"]),
                arguments=dict(arguments),
            )
        else:
            raise ValueError(f"Unsupported memory action '{message.action}'.")

        return {
            "text": f"Memory action '{message.action}' completed.",
            "structured_content": result,
            "is_error": False,
        }

from __future__ import annotations

from typing import Any

from .messages import Message
from .nodes import GraphNode
from .sqlite_logger import SQLiteEventLogger


class GraphEngine:
    """Central routing authority for the runtime graph."""

    def __init__(self, event_logger: SQLiteEventLogger) -> None:
        self._event_logger = event_logger
        self._nodes: dict[str, GraphNode] = {}
        self._allowed_routes: set[tuple[str, str]] = set()
        self.global_state: dict[str, Any] = {}

    def register_node(self, node: GraphNode) -> None:
        if node.node_id in self._nodes:
            raise ValueError(f"Node '{node.node_id}' is already registered.")
        self._nodes[node.node_id] = node

    def allow_route(self, sender: str, target: str) -> None:
        self._allowed_routes.add((sender, target))

    def dispatch(self, message: Message) -> dict[str, Any]:
        if message.target not in self._nodes:
            raise KeyError(f"Target node '{message.target}' is not registered.")

        if (message.sender, message.target) not in self._allowed_routes:
            raise PermissionError(
                f"Route '{message.sender}' -> '{message.target}' is not permitted."
            )

        response = self._nodes[message.target].receive(message)
        self._event_logger.log_dispatch(message, response)
        return response

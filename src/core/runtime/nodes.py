from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .messages import Message


class GraphNode(ABC):
    """Abstract base for graph nodes with isolated local state."""

    def __init__(self, node_id: str, node_type: str) -> None:
        self.node_id = node_id
        self.node_type = node_type
        self.local_state: dict[str, Any] = {}

    @abstractmethod
    def receive(self, message: Message) -> dict[str, Any]:
        """Handle a routed runtime message."""

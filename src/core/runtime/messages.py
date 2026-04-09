from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class Message:
    """Serializable runtime message."""

    sender: str
    target: str
    action: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_record(self) -> dict[str, Any]:
        return {
            "sender": self.sender,
            "target": self.target,
            "action": self.action,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }

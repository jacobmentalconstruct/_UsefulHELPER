from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class AppState:
    """Root-owned lifecycle state."""

    boot_id: str
    lifecycle_state: str = "created"
    active_transport: str | None = None
    request_count: int = 0

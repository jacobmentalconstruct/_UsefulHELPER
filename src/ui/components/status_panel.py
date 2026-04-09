from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StatusPanelModel:
    title: str
    body: str
    footer: str


class StatusPanel:
    """Owned UI component for textual status output."""

    def render(self, model: StatusPanelModel) -> str:
        return "\n".join(
            [
                model.title,
                "=" * len(model.title),
                model.body,
                model.footer,
            ]
        )

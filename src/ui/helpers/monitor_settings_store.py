from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MonitorActionSettings:
    model: str
    instructions: str


@dataclass(frozen=True, slots=True)
class MonitorSettings:
    summarize: MonitorActionSettings
    ask_about: MonitorActionSettings


class MonitorSettingsStore:
    """Persists monitor helper settings under runtime data."""

    def __init__(self, settings_path: Path) -> None:
        self._settings_path = settings_path

    @property
    def settings_path(self) -> Path:
        return self._settings_path

    def load(self) -> MonitorSettings:
        if not self._settings_path.exists():
            return self.default_settings()
        try:
            raw = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return self.default_settings()
        return MonitorSettings(
            summarize=self._coerce_action(
                raw.get("summarize"),
                self.default_settings().summarize,
            ),
            ask_about=self._coerce_action(
                raw.get("ask_about"),
                self.default_settings().ask_about,
            ),
        )

    def save(self, settings: MonitorSettings) -> None:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(settings)
        self._settings_path.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )

    def default_settings(self) -> MonitorSettings:
        return MonitorSettings(
            summarize=MonitorActionSettings(
                model="qwen2.5:0.5b",
                instructions=(
                    "You are a concise operator assistant. Summarize the provided structured monitor "
                    "context packet for a human operator. Focus on what happened, what matters, and "
                    "any obvious follow-up. Ground the answer in the packet instead of guessing."
                ),
            ),
            ask_about=MonitorActionSettings(
                model="qwen2.5:4b",
                instructions=(
                    "You are a concise operator assistant. Answer the user's question using only "
                    "the provided structured monitor context packet. If the answer is uncertain "
                    "from the packet, say that directly instead of guessing."
                ),
            ),
        )

    def _coerce_action(
        self,
        raw_value: object,
        fallback: MonitorActionSettings,
    ) -> MonitorActionSettings:
        if not isinstance(raw_value, dict):
            return fallback
        model = str(raw_value.get("model", fallback.model)).strip() or fallback.model
        instructions = (
            str(raw_value.get("instructions", fallback.instructions)).strip()
            or fallback.instructions
        )
        return MonitorActionSettings(model=model, instructions=instructions)

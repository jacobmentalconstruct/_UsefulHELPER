from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol


InferenceResponseFormat = Literal["json", "text"]


@dataclass(frozen=True, slots=True)
class InferenceLoopRequest:
    """Normalized request passed into a reusable inference loop cartridge."""

    loop_name: str
    model: str
    messages: list[dict[str, str]]
    response_format: InferenceResponseFormat
    temperature: float
    max_tokens: int
    timeout_seconds: int
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class InferenceLoopResult:
    """Structured result returned by a reusable inference loop cartridge."""

    loop_name: str
    provider: str
    model: str
    response_format: InferenceResponseFormat
    raw_content: str
    parsed_json: dict[str, Any] | None
    done: bool
    prompt_eval_count: object
    eval_count: object
    total_duration: object
    turn_count: int
    metadata: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "loop_name": self.loop_name,
            "provider": self.provider,
            "model": self.model,
            "response_format": self.response_format,
            "raw_content": self.raw_content,
            "done": self.done,
            "prompt_eval_count": self.prompt_eval_count,
            "eval_count": self.eval_count,
            "total_duration": self.total_duration,
            "turn_count": self.turn_count,
            "metadata": dict(self.metadata),
        }
        if self.parsed_json is not None:
            payload["parsed_json"] = self.parsed_json
        else:
            payload["content"] = self.raw_content
        return payload


class InferenceLoopCartridge(Protocol):
    """Protocol implemented by pluggable inference loop cartridges."""

    loop_name: str
    provider: str
    description: str
    supported_formats: tuple[InferenceResponseFormat, ...]

    def run(self, request: InferenceLoopRequest) -> InferenceLoopResult:
        ...

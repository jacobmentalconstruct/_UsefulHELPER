from __future__ import annotations

from ...models.inference import (
    InferenceLoopRequest,
    InferenceLoopResult,
    InferenceResponseFormat,
)
from ...services.ollama_service import OllamaService


class OllamaSingleTurnLoopCartridge:
    """Reusable one-turn Ollama-backed inference loop cartridge."""

    loop_name = "ollama.single_turn"
    provider = "ollama"
    description = "Single-turn local Ollama chat loop for text or JSON responses."
    supported_formats: tuple[InferenceResponseFormat, ...] = ("json", "text")

    def __init__(self, ollama_service: OllamaService) -> None:
        self._ollama_service = ollama_service

    def run(self, request: InferenceLoopRequest) -> InferenceLoopResult:
        if request.response_format == "json":
            response = self._ollama_service.chat_json(
                model=request.model,
                messages=request.messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout_seconds=request.timeout_seconds,
            )
            return InferenceLoopResult(
                loop_name=request.loop_name,
                provider=self.provider,
                model=str(response["model"]),
                response_format="json",
                raw_content=str(response["raw_content"]),
                parsed_json=dict(response["parsed_json"]),
                done=bool(response["done"]),
                prompt_eval_count=response.get("prompt_eval_count"),
                eval_count=response.get("eval_count"),
                total_duration=response.get("total_duration"),
                turn_count=1,
                metadata=dict(request.metadata),
            )

        response = self._ollama_service.chat_text(
            model=request.model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            timeout_seconds=request.timeout_seconds,
        )
        return InferenceLoopResult(
            loop_name=request.loop_name,
            provider=self.provider,
            model=str(response["model"]),
            response_format="text",
            raw_content=str(response["content"]),
            parsed_json=None,
            done=bool(response["done"]),
            prompt_eval_count=response.get("prompt_eval_count"),
            eval_count=response.get("eval_count"),
            total_duration=response.get("total_duration"),
            turn_count=1,
            metadata=dict(request.metadata),
        )

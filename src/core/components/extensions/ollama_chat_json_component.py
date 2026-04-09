from __future__ import annotations

import json
from typing import Any

from ...services.ollama_service import OllamaService


class OllamaChatJsonComponent:
    """Bounded JSON-only chat helper backed by the local Ollama API."""

    def __init__(self, ollama_service: OllamaService) -> None:
        self._ollama_service = ollama_service

    def ollama_chat_json(self, arguments: dict[str, object]) -> dict[str, object]:
        """Run a local Ollama chat request and parse the JSON object response."""

        model = str(arguments.get("model", "qwen3.5:4b"))
        temperature = float(arguments.get("temperature", 0.2))
        max_tokens = int(arguments.get("max_tokens", 600))
        timeout_seconds = int(arguments.get("timeout_seconds", 90))
        messages = self._build_messages(arguments)

        response = self._ollama_service.chat_json(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )
        return {
            "model": response["model"],
            "parsed_json": response["parsed_json"],
            "raw_content": response["raw_content"],
            "done": response["done"],
            "prompt_eval_count": response["prompt_eval_count"],
            "eval_count": response["eval_count"],
            "total_duration": response["total_duration"],
            "message_count": len(messages),
        }

    def ollama_list_models(self, arguments: dict[str, object]) -> dict[str, object]:
        """List locally available Ollama models."""

        timeout_seconds = int(arguments.get("timeout_seconds", 10))
        models = self._ollama_service.list_models(timeout_seconds=timeout_seconds)
        return {
            "models": models,
            "model_count": len(models),
        }

    def _build_messages(self, arguments: dict[str, object]) -> list[dict[str, str]]:
        json_schema = arguments.get("json_schema")
        system = str(arguments.get("system", "")).strip()
        user = str(arguments.get("user", "")).strip()
        raw_messages = arguments.get("messages")

        messages: list[dict[str, str]] = []
        if isinstance(raw_messages, list):
            for item in raw_messages:
                if not isinstance(item, dict):
                    raise ValueError("Each message entry must be an object with role and content.")
                role = str(item.get("role", "")).strip()
                content = str(item.get("content", "")).strip()
                if not role or not content:
                    raise ValueError("Each message entry must include role and content.")
                messages.append({"role": role, "content": content})

        if not messages:
            if not user:
                raise ValueError("Either 'messages' or 'user' must be provided.")
            if system:
                messages.append({"role": "system", "content": system})
            if json_schema is not None:
                schema_text = json.dumps(json_schema, indent=2, sort_keys=True)
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Return only a single JSON object that matches this schema as closely as possible:\n"
                            f"{schema_text}"
                        ),
                    }
                )
            messages.append({"role": "user", "content": user})

        return messages

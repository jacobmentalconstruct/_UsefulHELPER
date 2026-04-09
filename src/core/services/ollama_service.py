from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


class OllamaService:
    """Owns local HTTP interactions with the Ollama API."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434") -> None:
        self._base_url = base_url.rstrip("/")

    def chat_json(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        response_payload = self._post_json("/api/chat", payload, timeout_seconds)
        message = response_payload.get("message", {})
        content = str(message.get("content", ""))
        parsed_json = self._parse_json_content(content)
        return {
            "model": str(response_payload.get("model", model)),
            "parsed_json": parsed_json,
            "raw_content": content,
            "done": bool(response_payload.get("done", False)),
            "prompt_eval_count": response_payload.get("prompt_eval_count"),
            "eval_count": response_payload.get("eval_count"),
            "total_duration": response_payload.get("total_duration"),
        }

    def chat_text(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        response_payload = self._post_json("/api/chat", payload, timeout_seconds)
        message = response_payload.get("message", {})
        content = str(message.get("content", ""))
        return {
            "model": str(response_payload.get("model", model)),
            "content": content,
            "done": bool(response_payload.get("done", False)),
            "prompt_eval_count": response_payload.get("prompt_eval_count"),
            "eval_count": response_payload.get("eval_count"),
            "total_duration": response_payload.get("total_duration"),
        }

    def list_models(self, timeout_seconds: int = 10) -> list[str]:
        response_payload = self._post_json("/api/tags", None, timeout_seconds, method="GET")
        return [
            str(item.get("name"))
            for item in response_payload.get("models", [])
            if item.get("name")
        ]

    def _post_json(
        self,
        route: str,
        payload: dict[str, Any] | None,
        timeout_seconds: int,
        method: str = "POST",
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url=f"{self._base_url}{route}",
            data=body,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except URLError as error:
            raise RuntimeError(f"Ollama request failed: {error}") from error

    def _parse_json_content(self, content: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            stripped = stripped.removeprefix("json").strip()

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as error:
            raise ValueError("Ollama response was not valid JSON.") from error

        if not isinstance(parsed, dict):
            raise ValueError("Ollama JSON response must be a JSON object.")
        return parsed

from __future__ import annotations

import unittest

from src.core.components.extensions.ollama_chat_json_component import OllamaChatJsonComponent


class FakeOllamaService:
    def chat_json(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
    ) -> dict[str, object]:
        return {
            "model": model,
            "parsed_json": {"status": "ok", "message_count": len(messages)},
            "raw_content": '{"status":"ok"}',
            "done": True,
            "prompt_eval_count": 10,
            "eval_count": 20,
            "total_duration": 30,
        }


class OllamaChatJsonComponentTests(unittest.TestCase):
    def test_component_returns_parsed_json_payload(self) -> None:
        component = OllamaChatJsonComponent(FakeOllamaService())

        result = component.ollama_chat_json(
            {
                "model": "qwen2.5:0.5b",
                "system": "Return JSON only.",
                "user": "Return a simple object.",
            }
        )

        self.assertEqual(result["parsed_json"]["status"], "ok")
        self.assertEqual(result["model"], "qwen2.5:0.5b")

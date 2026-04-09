from __future__ import annotations

import unittest

from src.core.models.inference import InferenceLoopRequest, InferenceLoopResult
from src.core.services.inference_loop_service import InferenceLoopService


class _FakeLoopCartridge:
    loop_name = "fake.loop"
    provider = "fake-provider"
    description = "Fake loop for tests."
    supported_formats = ("json", "text")

    def __init__(self) -> None:
        self.calls: list[InferenceLoopRequest] = []

    def run(self, request: InferenceLoopRequest) -> InferenceLoopResult:
        self.calls.append(request)
        parsed_json = {"status": "ok"} if request.response_format == "json" else None
        raw_content = '{"status":"ok"}' if parsed_json is not None else "plain text answer"
        return InferenceLoopResult(
            loop_name=request.loop_name,
            provider=self.provider,
            model=request.model,
            response_format=request.response_format,
            raw_content=raw_content,
            parsed_json=parsed_json,
            done=True,
            prompt_eval_count=11,
            eval_count=22,
            total_duration=33,
            turn_count=1,
            metadata=dict(request.metadata),
        )


class InferenceLoopServiceTests(unittest.TestCase):
    def test_build_request_includes_schema_prompt_and_default_loop(self) -> None:
        service = InferenceLoopService()
        fake = _FakeLoopCartridge()
        service.register_cartridge(fake, is_default=True)

        request = service.build_request(
            {
                "system": "Return JSON only.",
                "user": "Return a status object.",
                "json_schema": {"type": "object", "properties": {"status": {"type": "string"}}},
            },
            response_format="json",
            default_model="qwen3.5:4b",
        )

        self.assertEqual(request.loop_name, "fake.loop")
        self.assertEqual(request.model, "qwen3.5:4b")
        self.assertEqual(request.messages[0]["role"], "system")
        self.assertIn("Return JSON only.", request.messages[0]["content"])
        self.assertIn("matches this schema", request.messages[1]["content"])
        self.assertEqual(request.messages[-1]["content"], "Return a status object.")

    def test_run_from_arguments_uses_registered_loop_slot(self) -> None:
        service = InferenceLoopService()
        fake = _FakeLoopCartridge()
        service.register_cartridge(fake, is_default=True)

        result = service.run_from_arguments(
            {
                "model": "qwen3.5:14b",
                "messages": [{"role": "user", "content": "Say hello"}],
            },
            response_format="text",
            default_model="qwen3.5:4b",
        )

        self.assertEqual(result["loop_name"], "fake.loop")
        self.assertEqual(result["provider"], "fake-provider")
        self.assertEqual(result["model"], "qwen3.5:14b")
        self.assertEqual(result["content"], "plain text answer")
        self.assertEqual(fake.calls[0].metadata["message_count"], 1)

    def test_describe_loops_reports_default_slot(self) -> None:
        service = InferenceLoopService()
        fake = _FakeLoopCartridge()
        service.register_cartridge(fake, is_default=True)

        result = service.describe_loops()

        self.assertEqual(result["default_loop_name"], "fake.loop")
        self.assertEqual(result["loop_count"], 1)
        self.assertTrue(result["loops"][0]["is_default"])


if __name__ == "__main__":
    unittest.main()

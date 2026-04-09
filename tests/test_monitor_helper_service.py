from __future__ import annotations

import unittest

from src.ui.helpers.monitor_helper_service import MonitorHelperService
from src.ui.helpers.monitor_settings_store import MonitorActionSettings


class _FakeOllamaService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.response_content = "stub response"

    def chat_text(
        self,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {
            "model": model,
            "content": self.response_content,
            "prompt_eval_count": 10,
            "eval_count": 20,
            "total_duration": 30,
        }

    def list_models(self, timeout_seconds: int = 10) -> list[str]:
        return ["qwen2.5:0.5b", "qwen3.5:4b"]


class MonitorHelperServiceTests(unittest.TestCase):
    def test_build_context_packet_parses_log_records(self) -> None:
        helper = MonitorHelperService(_FakeOllamaService())

        log_text = (
            "2026-04-08 08:57:04,763 | INFO | __main__ | usefulhelper-worker 0.1.0\n"
            "transport=ndjson\n"
            "workspace_root=C:\\repo\\UsefulHELPER\n"
            "Worker ready for MCP-style requests.\n"
        )
        packet = helper.build_context_packet(
            context_label="log panel",
            context_text=log_text,
            context_type="log_panel",
            full_visible_text=log_text,
        )

        self.assertEqual(packet.derived_facts["transport"], "ndjson")
        self.assertEqual(packet.derived_facts["event_count"], 1)
        self.assertEqual(packet.structured_records[0]["level"], "INFO")

    def test_summarize_uses_supplied_settings(self) -> None:
        fake_service = _FakeOllamaService()
        helper = MonitorHelperService(fake_service)
        packet = helper.build_context_packet(
            context_label="detail",
            context_text="Event detail text",
            context_type="text_panel",
            full_visible_text="Event detail text",
        )

        result = helper.summarize(
            context_label="detail",
            context_text="Event detail text",
            settings=MonitorActionSettings(
                model="qwen2.5:0.5b",
                instructions="Summarize the context tightly.",
            ),
            context_packet=packet,
        )

        self.assertEqual(result.model, "qwen2.5:0.5b")
        self.assertEqual(result.content, "stub response")
        self.assertEqual(fake_service.calls[0]["model"], "qwen2.5:0.5b")
        self.assertIn("Summarize the context tightly.", fake_service.calls[0]["messages"][0]["content"])
        self.assertIn("Structured context packet", fake_service.calls[0]["messages"][1]["content"])

    def test_ask_about_includes_question_and_context(self) -> None:
        fake_service = _FakeOllamaService()
        helper = MonitorHelperService(fake_service)
        packet = helper.build_context_packet(
            context_label="inference",
            context_text="Prompt and response history",
            context_type="text_panel",
            full_visible_text="Prompt and response history",
        )

        helper.ask_about(
            context_label="inference",
            context_text="Prompt and response history",
            question="What happened here?",
            settings=MonitorActionSettings(
                model="qwen2.5:4b",
                instructions="Answer carefully from context.",
            ),
            context_packet=packet,
        )

        user_message = fake_service.calls[0]["messages"][1]["content"]
        self.assertIn("Question: What happened here?", user_message)
        self.assertIn("Prompt and response history", user_message)
        self.assertIn("Intent hint: answer", user_message)

    def test_empty_model_response_uses_fallback_answer(self) -> None:
        fake_service = _FakeOllamaService()
        fake_service.response_content = ""
        helper = MonitorHelperService(fake_service)
        packet = helper.build_context_packet(
            context_label="detail panel",
            context_text=(
                "action: sysops.git_recent_commits\n"
                "summary: sysops.git_recent_commits | .\n"
            ),
            context_type="text_panel",
            full_visible_text=(
                "action: sysops.git_recent_commits\n"
                "summary: sysops.git_recent_commits | .\n"
            ),
        )

        result = helper.ask_about(
            context_label="detail panel",
            context_text=(
                "action: sysops.git_recent_commits\n"
                "summary: sysops.git_recent_commits | .\n"
            ),
            question="What is this about?",
            settings=MonitorActionSettings(
                model="qwen3.5:4b",
                instructions="Answer carefully from context.",
            ),
            context_packet=packet,
        )

        self.assertIn("sysops.git_recent_commits", result.content)

    def test_log_event_question_fallback_lists_visible_events(self) -> None:
        fake_service = _FakeOllamaService()
        fake_service.response_content = ""
        helper = MonitorHelperService(fake_service)
        log_text = (
            "2026-04-08 08:57:04,763 | INFO | __main__ | usefulhelper-worker 0.1.0\n"
            "transport=ndjson\n"
            "2026-04-08 09:00:14,668 | INFO | __main__ | Worker ready for MCP-style requests.\n"
        )
        packet = helper.build_context_packet(
            context_label="log panel",
            context_text=log_text,
            context_type="log_panel",
            full_visible_text=log_text,
        )

        result = helper.ask_about(
            context_label="log panel",
            context_text=log_text,
            question="can you list the events you see here in this log?",
            settings=MonitorActionSettings(
                model="qwen3.5:4b",
                instructions="Answer carefully from context.",
            ),
            context_packet=packet,
        )

        self.assertIn("- 2026-04-08 08:57:04,763 | INFO |", result.content)
        self.assertIn("usefulhelper-worker 0.1.0", result.content)

    def test_log_enumeration_question_uses_mechanical_answer(self) -> None:
        fake_service = _FakeOllamaService()
        helper = MonitorHelperService(fake_service)
        log_text = (
            "2026-04-08 09:00:14,668 | INFO | __main__ | usefulhelper-worker 0.1.0\n"
            "2026-04-08 09:11:21,187 | INFO | __main__ | Worker ready for MCP-style requests.\n"
        )
        packet = helper.build_context_packet(
            context_label="log panel",
            context_text=log_text,
            context_type="log_panel",
            full_visible_text=log_text,
        )

        result = helper.ask_about(
            context_label="log panel",
            context_text=log_text,
            question="Please list the logs with a description of 8 words or less for each log in a bulleted list.",
            settings=MonitorActionSettings(
                model="qwen3.5:4b",
                instructions="Answer carefully from context.",
            ),
            context_packet=packet,
        )

        self.assertEqual(result.model, "mechanical::enumerate")
        self.assertEqual(len(fake_service.calls), 0)
        self.assertIn("- 2026-04-08 09:00:14,668 | INFO |", result.content)
        self.assertIn("Worker ready for MCP requests", result.content)

    def test_event_explain_question_uses_mechanical_answer(self) -> None:
        fake_service = _FakeOllamaService()
        helper = MonitorHelperService(fake_service)
        detail_text = (
            "id: 494\n"
            "time: 2026-04-09T14:57:03.642723+00:00\n"
            "group: requests\n"
            "action: rpc.request\n"
            "sender: app\n"
            "target: core.mcp_orchestrator\n"
            "summary: tools/call demo.echo_runtime_probe\n"
            "is_error: False\n\n"
            "payload:\n"
            "{\n"
            '  "request": {\n'
            '    "method": "tools/call"\n'
            "  }\n"
            "}\n\n"
            "response:\n"
            "{\n"
            '  "result": {\n'
            '    "ok": true\n'
            "  }\n"
            "}\n"
        )
        packet = helper.build_context_packet(
            context_label="detail panel",
            context_text=detail_text,
            context_type="text_panel",
            full_visible_text=detail_text,
        )

        result = helper.ask_about(
            context_label="detail panel",
            context_text=detail_text,
            question="What exactly is happening here in this event?",
            settings=MonitorActionSettings(
                model="qwen3.5:4b",
                instructions="Answer carefully from context.",
            ),
            context_packet=packet,
        )

        self.assertEqual(result.model, "mechanical::explain")
        self.assertEqual(len(fake_service.calls), 0)
        self.assertIn("`rpc.request`", result.content)
        self.assertIn("`app` to `core.mcp_orchestrator`", result.content)

    def test_roll_conversation_window_summarizes_older_turns(self) -> None:
        helper = MonitorHelperService(_FakeOllamaService())

        summary, turns = helper.roll_conversation_window(
            conversation_summary="",
            recent_turns=[
                {"question": "What happened first?", "answer": "The worker initialized cleanly."},
                {"question": "What happened next?", "answer": "It listed the tools."},
                {"question": "What happened after that?", "answer": "It ran the inference loop."},
            ],
            keep_recent_turns=2,
            max_recent_chars=1000,
            max_summary_chars=400,
        )

        self.assertIn("What happened first?", summary)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["question"], "What happened next?")

    def test_prompt_echo_is_replaced_with_try_larger_model_message(self) -> None:
        fake_service = _FakeOllamaService()
        fake_service.response_content = "Can you elaborate on this? Can you elaborate on this?"
        helper = MonitorHelperService(fake_service)
        detail_text = (
            "action: rpc.request\n"
            "summary: tools/call demo.echo_runtime_probe\n"
        )
        packet = helper.build_context_packet(
            context_label="detail panel",
            context_text=detail_text,
            context_type="text_panel",
            full_visible_text=detail_text,
        )

        result = helper.ask_about(
            context_label="detail panel",
            context_text=detail_text,
            question="Can you elaborate on this?",
            settings=MonitorActionSettings(
                model="qwen2.5:0.5b",
                instructions="Answer carefully from context.",
            ),
            context_packet=packet,
        )

        self.assertEqual(
            result.content,
            "That's a bit complex, so you may want to try a larger model for this one.",
        )

    def test_list_models_reads_from_ollama_service(self) -> None:
        fake_service = _FakeOllamaService()
        helper = MonitorHelperService(fake_service)

        models = helper.list_models()
        self.assertEqual(models, ["qwen2.5:0.5b", "qwen3.5:4b"])


if __name__ == "__main__":
    unittest.main()

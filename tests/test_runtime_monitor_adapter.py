from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from src.core.runtime.messages import Message
from src.core.runtime.sqlite_logger import SQLiteEventLogger
from src.ui.adapters.runtime_monitor_adapter import RuntimeMonitorAdapter


class RuntimeMonitorAdapterTests(unittest.TestCase):
    def test_adapter_groups_recent_events_and_reads_log_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            db_path = temp_root / "runtime_events.sqlite3"
            log_path = temp_root / "app.log"
            logger = SQLiteEventLogger(db_path)
            logger.ensure_schema()

            request_message = Message(
                sender="app",
                target="core.mcp_orchestrator",
                action="rpc.request",
                payload={
                    "request": {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "fs.write_files", "arguments": {}},
                    }
                },
                timestamp=datetime.fromisoformat("2026-04-08T09:00:00+00:00"),
            )
            logger.log_dispatch(
                request_message,
                {"rpc_response": {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}},
            )

            inference_message = Message(
                sender="core.mcp_orchestrator",
                target="core.inference_manager",
                action="ollama.chat_json",
                payload={
                    "arguments": {
                        "model": "qwen2.5:0.5b",
                        "user": "Return a compact JSON answer about the monitor.",
                    }
                },
                timestamp=datetime.fromisoformat("2026-04-08T09:00:01+00:00"),
            )
            logger.log_dispatch(
                inference_message,
                {
                    "text": "Inference action completed.",
                    "structured_content": {
                        "model": "qwen2.5:0.5b",
                        "parsed_json": {"status": "ok"},
                    },
                    "is_error": False,
                },
            )

            log_path.write_text("line one\nline two\nline three\n", encoding="utf-8")

            adapter = RuntimeMonitorAdapter(db_path, log_path)
            snapshot = adapter.fetch_snapshot(limit_per_group=10, log_line_count=2)

            self.assertEqual(snapshot.total_event_count, 2)
            self.assertEqual(snapshot.latest_event_id, 2)
            self.assertEqual(snapshot.log_tail, ["line two", "line three"])

            request_records = snapshot.events_by_group["requests"]
            self.assertEqual(len(request_records), 1)
            self.assertEqual(request_records[0].summary, "tools/call fs.write_files")

            inference_records = snapshot.events_by_group["inference"]
            self.assertEqual(len(inference_records), 1)
            self.assertIn("qwen2.5:0.5b", inference_records[0].summary)
            self.assertEqual(snapshot.registry[0].group, "requests")


if __name__ == "__main__":
    unittest.main()

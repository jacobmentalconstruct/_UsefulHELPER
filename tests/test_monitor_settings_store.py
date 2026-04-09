from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.ui.helpers.monitor_settings_store import (
    MonitorActionSettings,
    MonitorSettings,
    MonitorSettingsStore,
)


class MonitorSettingsStoreTests(unittest.TestCase):
    def test_store_round_trip_persists_models_and_instructions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "monitor_settings.json"
            store = MonitorSettingsStore(settings_path)

            settings = MonitorSettings(
                summarize=MonitorActionSettings(
                    model="qwen2.5:0.5b",
                    instructions="Summarize tightly.",
                ),
                ask_about=MonitorActionSettings(
                    model="qwen2.5:4b",
                    instructions="Answer with context discipline.",
                ),
            )
            store.save(settings)

            reloaded = store.load()
            self.assertEqual(reloaded.summarize.model, "qwen2.5:0.5b")
            self.assertEqual(reloaded.ask_about.instructions, "Answer with context discipline.")


if __name__ == "__main__":
    unittest.main()

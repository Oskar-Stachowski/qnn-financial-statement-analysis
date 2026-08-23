"""Static tests for the single-import v1.1.2 launcher."""

from __future__ import annotations

from pathlib import Path
import unittest

from src.modeling.secondary_analysis_execution_v1_1_1 import (
    DEFAULT_CONFIG,
    load_execution_config,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_secondary_analyses_v1_1_2.sh"


class SecondaryAnalysisLauncherTests(unittest.TestCase):
    def test_launcher_imports_v1_1_1_exactly_once(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("python -c", source)
        self.assertIn(
            "from src.modeling.secondary_analysis_execution_v1_1_1 import main",
            source,
        )
        self.assertNotIn(
            "python -m src.modeling.secondary_analysis_execution_v1_1_1",
            source,
        )

    def test_real_modes_require_committed_launcher_verification(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "verify_secondary_analysis_launcher_v1_1_2(require_committed=True)",
            source,
        )

    def test_launcher_does_not_change_v1_1_1_configuration(self) -> None:
        config = load_execution_config(DEFAULT_CONFIG)
        section = config["secondary_development_execution"]
        self.assertEqual(section["version"], "1.1.1")
        self.assertEqual(section["frozen_schedule"]["task_count"], 96)
        self.assertFalse(section["input_key_amendment"]["methodology_changed"])


if __name__ == "__main__":
    unittest.main()

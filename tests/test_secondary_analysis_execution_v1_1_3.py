"""Static/synthetic tests for the v1.1.3 signal-source amendment."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling.secondary_analysis_execution_v1_1_3 import (
    DEFAULT_CONFIG,
    load_execution_config,
    synthetic_smoke_isolated,
    verify_amendment_authority,
)
from src.modeling.verify_secondary_analysis_execution_v1_1_1 import (
    verify_secondary_analysis_execution_v1_1_1,
)


ROOT = Path(__file__).resolve().parents[1]


class SecondaryExecutionSignalSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_execution_config(DEFAULT_CONFIG)

    def test_signal_source_is_existing_frozen_production_target(self) -> None:
        section = self.config["secondary_development_execution"]
        runner = yaml.safe_load(
            (ROOT / "configs/production_experiment_runner_v1_0_1_lightning.yaml").read_text(
                encoding="utf-8"
            )
        )
        configured = section["authority"]["robustness_signal_source"]
        frozen = runner["data"]["frozen_train_inputs"]["target_application_train"]
        self.assertEqual(configured, frozen)
        self.assertFalse(
            section["signal_source_amendment"][
                "additional_interim_target_deserialization"
            ]
        )

    def test_amendment_preserves_scientific_identity(self) -> None:
        amendment = self.config["secondary_development_execution"][
            "signal_source_amendment"
        ]
        for field in (
            "target_values_changed",
            "sample_membership_changed",
            "fold_policy_changed",
            "task_roster_changed",
            "methodology_changed",
        ):
            self.assertFalse(amendment[field])

    def test_base_amendment_and_v1_1_3_authority_pass(self) -> None:
        self.assertEqual(verify_secondary_analysis_execution_v1_1_1()["status"], "PASS")
        self.assertEqual(len(verify_amendment_authority(self.config)), 4)

    def test_exact_96_task_roster_is_unchanged(self) -> None:
        schedule, tasks = base.frozen_schedule(self.config)
        self.assertEqual(len(tasks), 96)
        self.assertEqual(schedule["counts"]["total_planned_tasks"], 96)

    def test_synthetic_smoke_remains_data_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = synthetic_smoke_isolated(DEFAULT_CONFIG, Path(directory))
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["project_data_read"])
        self.assertFalse(result["project_model_fit_performed"])
        self.assertFalse(result["protected_feature_years_opened"])

    def test_launcher_uses_single_import(self) -> None:
        source = (ROOT / "scripts/run_secondary_analyses_v1_1_3.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -c", source)
        self.assertNotIn(
            "python -m src.modeling.secondary_analysis_execution_v1_1_3", source
        )


if __name__ == "__main__":
    unittest.main()

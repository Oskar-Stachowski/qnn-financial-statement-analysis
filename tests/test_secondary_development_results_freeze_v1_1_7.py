"""Tests for the secondary-development v1.1.7 result freeze."""

from __future__ import annotations

from pathlib import Path
import unittest

from src.modeling.build_secondary_development_results_freeze_inventory_v1_1_7 import (
    collect_inventory,
)
from src.modeling.verify_secondary_development_results_freeze_v1_1_7 import (
    verify_secondary_development_results_freeze_v1_1_7,
)


ROOT = Path(__file__).resolve().parents[1]


class SecondaryDevelopmentResultsFreezeTests(unittest.TestCase):
    def test_full_frozen_bundle(self) -> None:
        result = verify_secondary_development_results_freeze_v1_1_7(
            ROOT
            / "configs/secondary_development_v1_1_7_results_freeze_manifest.yaml"
        )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["task_results"], 96)
        self.assertEqual(result["complete_tasks"], 96)
        self.assertEqual(result["prediction_artifacts"], 84)
        self.assertEqual(result["checkpoint_files"], 30)
        self.assertEqual(result["qnn_attempts"], 24)
        self.assertFalse(result["protected_feature_years_opened"])

    def test_inventory_is_deterministic_and_complete(self) -> None:
        inventory = collect_inventory()
        self.assertEqual(inventory["status"], "COMPLETE")
        self.assertEqual(inventory["file_count"], 585)
        self.assertEqual(len(inventory["files"]), inventory["file_count"])
        self.assertEqual(len(inventory["roots"]), 2)
        self.assertFalse(inventory["project_data_deserialized"])
        self.assertFalse(inventory["project_model_fit_performed"])
        self.assertFalse(inventory["protected_feature_years_opened"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

import yaml

from src.modeling import protected_period_extension as protected


ROOT = Path(__file__).resolve().parents[1]


class ProtectedPeriodHoldoutEvaluationRepairTests(unittest.TestCase):
    def test_same_basename_is_partitioned_by_prediction_year(self) -> None:
        first = protected._labeled_prediction_output_path(
            {"year": 2023, "prediction_path": "blind/duplicate.json"}
        )
        second = protected._labeled_prediction_output_path(
            {"year": 2024, "prediction_path": "blind/duplicate.json"}
        )

        self.assertNotEqual(first, second)
        self.assertEqual(first.parent.name, "prediction_2023")
        self.assertEqual(second.parent.name, "prediction_2024")
        self.assertEqual(first.name, second.name)

    def test_repair_uses_a_new_one_shot_namespace(self) -> None:
        self.assertEqual(
            protected.HOLDOUT_EVALUATION_RUN_ROOT.name,
            "holdout_evaluation_v1_0_1",
        )
        self.assertEqual(
            protected.HOLDOUT_EVALUATION_EVIDENCE_PATH.name,
            "protected_period_holdout_evaluation_v1_0_1_result.json",
        )

    def test_repair_authority_freezes_scientific_contract(self) -> None:
        repair = yaml.safe_load(protected.HOLDOUT_EVALUATION_REPAIR_PATH.read_text())
        identity = repair["holdout_evaluation_repair"]
        failure = repair["failure"]
        runner_hash = hashlib.sha256(
            (ROOT / "src/modeling/protected_period_extension.py").read_bytes()
        ).hexdigest()

        self.assertFalse(identity["methodology_changed"])
        self.assertFalse(identity["metric_contract_changed"])
        self.assertFalse(identity["blind_predictions_changed"])
        self.assertFalse(failure["metric_computation_started_before_failure"])
        self.assertEqual(repair["repair"]["repaired_runner_sha256"], runner_hash)
        protected._verify_frozen_implementation(
            yaml.safe_load(
                (ROOT / "configs/protected_period_execution_contract_v1_0_0.yaml").read_text()
            )
        )


if __name__ == "__main__":
    unittest.main()

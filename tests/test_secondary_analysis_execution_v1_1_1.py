"""Static and synthetic tests for the v1.1.1 input-key amendment."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from src.modeling import secondary_analysis_execution as base
from src.modeling.secondary_analysis_execution_v1_1_1 import (
    DEFAULT_CONFIG,
    canonical_company_year_id,
    load_execution_config,
    verify_amendment_authority,
)
from src.modeling.verify_secondary_analysis_execution_package import (
    verify_secondary_analysis_execution_package,
)


class SecondaryExecutionInputKeyAmendmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_execution_config(DEFAULT_CONFIG)

    def test_only_join_key_interface_is_amended(self) -> None:
        section = self.config["secondary_development_execution"]
        amendment = section["input_key_amendment"]
        self.assertEqual(section["version"], "1.1.1")
        self.assertEqual(amendment["scope"], "robustness_target_join_key_only")
        self.assertFalse(amendment["target_values_changed"])
        self.assertFalse(amendment["sample_membership_changed"])
        self.assertFalse(amendment["fold_policy_changed"])
        self.assertFalse(amendment["task_roster_changed"])
        self.assertFalse(amendment["methodology_changed"])

    def test_canonical_key_matches_frozen_company_year_shape(self) -> None:
        self.assertEqual(canonical_company_year_id("880460", 2013), "0000880460-2013")
        self.assertEqual(canonical_company_year_id("0000880460", "2020"), "0000880460-2020")
        with self.assertRaises(base.SecondaryExecutionIntegrityError):
            canonical_company_year_id("880460", 2021)
        with self.assertRaises(base.SecondaryExecutionIntegrityError):
            canonical_company_year_id("not-a-cik", 2019)

    def test_amendment_preserves_exact_96_task_roster(self) -> None:
        schedule, tasks = base.frozen_schedule(self.config)
        self.assertEqual(len(tasks), 96)
        self.assertEqual(schedule["counts"]["total_planned_tasks"], 96)
        self.assertEqual(schedule["counts"]["pca_matched_control_fold_fits"], 12)
        self.assertEqual(schedule["counts"]["global_winner_robustness_fold_fits"], 48)
        self.assertEqual(schedule["counts"]["qnn_structural_robustness_fold_fits"], 24)

    def test_base_freeze_and_amendment_authority_are_exact(self) -> None:
        base_report = verify_secondary_analysis_execution_package()
        authority = verify_amendment_authority(self.config)
        self.assertEqual(base_report["status"], "PASS")
        self.assertEqual(len(authority), 3)

    def test_synthetic_smoke_remains_project_data_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = base.synthetic_smoke(DEFAULT_CONFIG, Path(directory))
        self.assertEqual(report["status"], "PASS")
        self.assertFalse(report["project_data_read"])
        self.assertFalse(report["project_model_fit_performed"])
        self.assertFalse(report["protected_feature_years_opened"])


if __name__ == "__main__":
    unittest.main()

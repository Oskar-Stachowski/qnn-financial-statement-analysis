from __future__ import annotations

import copy
import tempfile
from pathlib import Path
import unittest

from src.modeling.secondary_analysis_runner import create_plan, package_status
from src.modeling.secondary_analysis_schemas import (
    DEFAULT_CONFIG,
    SecondaryAnalysisIntegrityError,
    load_config,
    validate_config,
    validate_plan,
)
from src.modeling.secondary_analysis_smoke import run_smoke
from src.modeling.verify_secondary_analysis_package import (
    verify_secondary_analysis_package,
)


ROOT = Path(__file__).resolve().parents[1]


class SecondaryAnalysisPackageTest(unittest.TestCase):
    def test_config_and_authority_are_exact(self) -> None:
        result = package_status(DEFAULT_CONFIG)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["verified_authority_files"], 18)
        self.assertEqual(
            result["planned_fit_counts"],
            {
                "pca_matched_control_fold_fits": 12,
                "global_winner_robustness_fold_fits": 48,
                "qnn_structural_fold_fits": 24,
            },
        )
        self.assertFalse(result["project_data_read"])
        self.assertFalse(result["protected_feature_years_opened"])

    def test_plan_is_deterministic_and_contains_exact_task_roster(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = create_plan(DEFAULT_CONFIG, output)
            second = create_plan(DEFAULT_CONFIG, output)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "PLAN_ONLY_NO_PROJECT_DATA_ACCESS")
        self.assertEqual(first["task_counts"]["total_planned_tasks"], 96)
        self.assertEqual(first["task_counts"]["pca_matched_control_fold_fits"], 12)
        self.assertEqual(first["task_counts"]["global_winner_robustness_fold_fits"], 48)
        self.assertEqual(first["task_counts"]["qnn_structural_robustness_fold_fits"], 24)
        self.assertFalse(first["result_magnitudes_used_for_schedule"])
        self.assertFalse(first["project_data_read"])
        self.assertFalse(first["project_model_fit_performed"])
        self.assertFalse(first["protected_feature_years_opened"])
        identities = [task["task_identity_sha256"] for task in first["tasks"]]
        self.assertEqual(len(identities), len(set(identities)))
        validate_plan(first, load_config(DEFAULT_CONFIG))

    def test_synthetic_smoke_uses_no_project_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = run_smoke(
                DEFAULT_CONFIG,
                Path(directory) / "secondary_analysis_synthetic_smoke.json",
            )
        self.assertEqual(result["status"], "PASS")
        self.assertGreaterEqual(len(result["checks"]), 7)
        self.assertFalse(result["project_data_read"])
        self.assertFalse(result["project_model_fit_performed"])
        self.assertFalse(result["protected_feature_years_opened"])

    def test_protected_access_permission_fails_closed(self) -> None:
        config = copy.deepcopy(load_config(DEFAULT_CONFIG))
        config["secondary_development_analyses"]["pre_execution_boundary"][
            "this_package_may_read_project_data"
        ] = True
        with self.assertRaises(SecondaryAnalysisIntegrityError):
            validate_config(config)

    def test_frozen_package_is_hash_exact(self) -> None:
        result = verify_secondary_analysis_package()
        self.assertEqual(
            result["verdict"],
            "SECONDARY_DEVELOPMENT_V1_0_0_PACKAGE_INTEGRITY_PASS",
        )
        self.assertEqual(result["verified_package_files"], 8)
        self.assertEqual(result["verified_authority_files"], 18)
        self.assertFalse(result["project_data_read"])
        self.assertFalse(result["project_model_fit_performed"])
        self.assertFalse(result["protected_feature_years_opened"])


if __name__ == "__main__":
    unittest.main()

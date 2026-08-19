from __future__ import annotations

import hashlib
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs/data_access_policy_v1_1_0.yaml"
MANIFEST_PATH = ROOT / "configs/data_access_policy_v1_1_0_freeze_manifest.yaml"
PIPELINE_AMENDMENT_PATH = ROOT / "configs/supervised_ml_pipeline_v1_1_0_access_amendment.yaml"
MODEL_AMENDMENT_PATH = ROOT / "configs/model_stage_v1_1_0_access_amendment.yaml"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise AssertionError(f"Expected mapping in {path}")
    return payload


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DataAccessPolicyV110Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_yaml(POLICY_PATH)
        cls.manifest = load_yaml(MANIFEST_PATH)
        cls.pipeline_amendment = load_yaml(PIPELINE_AMENDMENT_PATH)
        cls.model_amendment = load_yaml(MODEL_AMENDMENT_PATH)

    def test_corrected_period_status_is_unambiguous(self) -> None:
        policy = self.policy["data_access_policy"]
        self.assertEqual(policy["version"], "1.1.0")
        self.assertFalse(policy["historical_frozen_artifacts_modified"])
        self.assertFalse(policy["model_training_performed_for_this_amendment"])

        periods = self.policy["periods"]
        spent = periods["spent_development_2021_2022"]
        self.assertEqual(spent["status"], "design_exposed_spent_development_period")
        self.assertTrue(spent["external_validation_opened_analytically"])
        self.assertFalse(spent["independent_one_shot_external_validation"])
        self.assertEqual(spent["prior_exposure"]["class_distribution"], "exposed")
        self.assertEqual(spent["prior_exposure"]["missingness"], "exposed")
        self.assertEqual(spent["prior_exposure"]["feature_statistics"], "exposed")
        self.assertEqual(spent["prior_exposure"]["model_performance"], "not_exposed")

        holdout = periods["temporal_holdout_2023_2024"]
        self.assertFalse(holdout["fully_unseen_holdout"])
        self.assertTrue(holdout["model_performance_holdout"])
        self.assertEqual(
            holdout["prior_exposure"]["aggregate_target_statistics"], "exposed"
        )
        self.assertEqual(holdout["prior_exposure"]["feature_level_analysis"], "not_exposed")
        self.assertEqual(holdout["prior_exposure"]["model_performance"], "not_exposed")

    def test_forward_lock_and_three_gates_are_frozen(self) -> None:
        lock = self.policy["forward_access_lock"]
        self.assertTrue(lock["effective_immediately"])
        self.assertEqual(lock["protected_feature_years"], [2021, 2022, 2023, 2024])
        self.assertFalse(lock["row_counts_or_schema_summaries_for_2021_2024_allowed_before_gate"])
        self.assertIn("target_values", lock["prohibited_before_applicable_gate"])
        self.assertIn("feature_values", lock["prohibited_before_applicable_gate"])
        self.assertIn("coverage_or_distribution_statistics", lock["prohibited_before_applicable_gate"])
        self.assertEqual(
            set(self.policy["gates"]),
            {
                "DATA_ACCESS_GATE_2021_2022_REOPEN_V1",
                "DATA_ACCESS_GATE_2023_2024_FEATURE_APPLICATION_V1",
                "DATA_ACCESS_GATE_2023_2024_LABEL_REVEAL_V1",
            },
        )

    def test_layer_amendments_use_corrected_status(self) -> None:
        for amendment in (self.pipeline_amendment, self.model_amendment):
            metadata = amendment["access_amendment"]
            self.assertEqual(metadata["version"], "1.1.0")
            self.assertFalse(metadata["modifies_historical_v1_artifacts"])
            corrected = amendment["corrected_access_status"]
            self.assertTrue(corrected["years_2021_2022"]["external_validation_opened_analytically"])
            self.assertFalse(
                corrected["years_2021_2022"]["independent_one_shot_external_validation"]
            )
            self.assertTrue(
                corrected["years_2023_2024"]["aggregate_target_statistics_previously_exposed"]
            )
            self.assertFalse(
                corrected["years_2023_2024"]["feature_level_analysis_previously_exposed"]
            )
            self.assertFalse(
                corrected["years_2023_2024"]["model_performance_previously_exposed"]
            )

    def test_historical_frozen_files_remain_byte_identical(self) -> None:
        supersession = self.policy["supersession"]
        self.assertTrue(supersession["historical_files_remain_immutable"])
        for item in supersession["superseded_declarations"]:
            self.assertEqual(sha256(ROOT / item["path"]), item["sha256"])

    def test_new_protected_components_match_manifest(self) -> None:
        manifest = self.manifest["data_access_policy_freeze"]
        self.assertEqual(manifest["version"], "1.1.0")
        for item in self.manifest["protected_components"]:
            self.assertEqual(sha256(ROOT / item["path"]), item["sha256"])

    def test_human_specifications_state_the_correction(self) -> None:
        for relative in (
            "docs/09_1_data_access_policy_v1_1_0.md",
            "docs/07_2_supervised_ml_pipeline_v1_1_0_access_amendment.md",
            "docs/08_2_model_stage_v1_1_0_access_amendment.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("external_validation_opened_analytically = true", text)
            self.assertIn("independent_one_shot_external_validation = false", text)
            self.assertIn("2023–2024", text)


if __name__ == "__main__":
    unittest.main()

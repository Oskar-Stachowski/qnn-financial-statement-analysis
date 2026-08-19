from __future__ import annotations

import csv
import hashlib
import unittest
from pathlib import Path

import pandas as pd
import yaml

from src.modeling.preprocessing import (
    FEATURE_BLOCKS,
    FROZEN_BLOCK_COMPARISONS,
    PreprocessingPolicy,
)
from src.modeling.temporal_cv import MAIN_EXPANDING_WINDOW_FOLDS


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "configs/supervised_ml_pipeline_v1_freeze_manifest.yaml"
POLICY_PATH = ROOT / "configs/supervised_ml_pipeline_v1.yaml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_data_rows(path: Path) -> int:
    with path.open("rb") as stream:
        return max(sum(1 for _ in stream) - 1, 0)


def csv_columns(path: Path) -> int:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return len(next(csv.reader(stream)))


def membership_sha256(values: pd.Series) -> str:
    payload = "".join(f"{value}\n" for value in sorted(values.astype(str)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_development_index(path: Path, usecols: list[str]) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        path,
        usecols=usecols,
        chunksize=10_000,
        low_memory=False,
    ):
        years = pd.to_numeric(chunk["feature_year"], errors="coerce")
        parts.append(chunk.loc[years.between(2011, 2022)].copy())
    return pd.concat(parts, ignore_index=True)


class FrozenSupervisedMlPipelineV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))

    def test_manifest_identifies_frozen_pipeline_and_exact_boundary(self) -> None:
        frozen = self.manifest["supervised_ml_pipeline"]
        self.assertEqual(frozen["id"], "supervised_ml_pipeline")
        self.assertEqual(frozen["version"], "1.0.0")
        self.assertEqual(frozen["status"], "frozen")
        for key in (
            "pipeline_policy_frozen",
            "supervised_sample_frozen",
            "preprocessing_frozen",
            "feature_blocks_frozen",
            "temporal_cv_frozen",
            "metric_aggregation_frozen",
            "clustered_inference_frozen",
            "mandatory_ablations_and_robustness_frozen",
            "external_validation_policy_frozen",
            "test_access_policy_frozen",
        ):
            self.assertTrue(frozen[key], key)
        self.assertFalse(frozen["predictive_models_trained"])
        self.assertFalse(frozen["model_family_frozen"])
        self.assertFalse(frozen["model_hyperparameters_frozen"])
        self.assertFalse(frozen["model_stage_fully_frozen"])

    def test_supervised_sample_policy_counts_and_membership_hashes(self) -> None:
        sample = self.policy["supervised_sample"]
        self.assertEqual(sample["required_membership_status"], "eligible")
        self.assertEqual(sample["required_target_status"], "available")
        self.assertEqual(
            sample["allowed_x_t_statuses"],
            ["available_core", "partially_available"],
        )
        self.assertFalse(sample["missing_financial_feature_drops_main_row"])
        self.assertEqual(sample["development_n"], 23_218)
        self.assertEqual(sample["train_n"], 19_671)
        self.assertEqual(sample["external_validation_n"], 3_547)

        x_path = ROOT / self.policy["upstream_frozen_inputs"]["raw_x_t"]["artifact"]
        target_application_path = (
            ROOT
            / "data/processed/research_universe_pit_v1_1_0_target_pit_b_v1_0_0.csv"
        )
        x_frame = read_development_index(
            x_path,
            [
                "research_universe_company_year_id",
                "feature_year",
                "split",
                "membership_status",
                "x_t_status",
            ],
        )
        target_frame = read_development_index(
            target_application_path,
            [
                "research_universe_company_year_id",
                "feature_year",
                "target_status",
            ],
        ).rename(columns={"feature_year": "target_feature_year"})
        selected = x_frame.merge(
            target_frame,
            on="research_universe_company_year_id",
            how="left",
            validate="one_to_one",
        )
        selected = selected.loc[
            selected["membership_status"].eq("eligible")
            & selected["target_status"].eq("available")
            & selected["x_t_status"].isin(
                ["available_core", "partially_available"]
            )
        ].copy()
        self.assertTrue(
            selected["feature_year"].eq(selected["target_feature_year"]).all()
        )
        self.assertTrue(selected["research_universe_company_year_id"].is_unique)

        subsets = {
            "development": selected,
            "train": selected.loc[selected["split"].eq("train")],
            "external_validation": selected.loc[
                selected["split"].eq("validation")
            ],
        }
        expected_counts = {
            "development": 23_218,
            "train": 19_671,
            "external_validation": 3_547,
        }
        fingerprints = sample["membership_fingerprint"]
        self.assertEqual(
            fingerprints["algorithm"],
            "sha256_utf8_lf_sorted_unique_research_universe_company_year_id",
        )
        for name, frame in subsets.items():
            with self.subTest(sample=name):
                self.assertEqual(len(frame), expected_counts[name])
                self.assertEqual(
                    membership_sha256(
                        frame["research_universe_company_year_id"]
                    ),
                    fingerprints[name],
                )

    def test_feature_blocks_and_main_preprocessing_are_exact(self) -> None:
        blocks = self.policy["feature_blocks"]
        self.assertEqual(blocks["L"], list(FEATURE_BLOCKS["L"]))
        self.assertEqual(blocks["D"], list(FEATURE_BLOCKS["D"]))
        self.assertEqual(blocks["R"], list(FEATURE_BLOCKS["R"]))
        self.assertEqual(
            blocks["frozen_comparisons"],
            [list(comparison) for comparison in FROZEN_BLOCK_COMPARISONS],
        )
        self.assertTrue(blocks["same_main_sample_for_all_comparisons"])
        self.assertFalse(blocks["missing_r_feature_drops_main_row"])
        self.assertFalse(blocks["economic_group_id_is_predictor"])

        main = self.policy["preprocessing"]["main_variant"]
        self.assertEqual(main["id"], "C")
        self.assertEqual(main["fit_scope"], "train_partition_only")
        self.assertEqual(main["cv_fit_scope"], "fold_train_partition_only")
        self.assertEqual(main["validation_operation"], "transform_only")
        self.assertTrue(main["fresh_instance_per_fold_and_feature_block"])
        self.assertEqual(
            main["financial_branch_order"],
            ["winsorize", "median_impute", "standard_scale"],
        )
        self.assertEqual(main["winsorization"]["lower_quantile"], 0.01)
        self.assertEqual(main["winsorization"]["upper_quantile"], 0.99)
        self.assertEqual(main["imputation"]["method"], "median")
        self.assertFalse(main["imputation"]["drops_rows"])
        self.assertEqual(main["scaling"]["implementation"], "StandardScaler")
        self.assertEqual(main["scaling"]["ddof"], 0)
        self.assertTrue(main["scaling"]["financial_features_only"])
        indicators = main["missing_indicators"]
        self.assertTrue(indicators["enabled"])
        self.assertTrue(indicators["one_per_input_financial_feature"])
        self.assertEqual(indicators["source"], "raw_pre_imputation_missingness")
        self.assertEqual(indicators["values"], [0, 1])
        self.assertFalse(indicators["winsorized"])
        self.assertFalse(indicators["scaled"])

        implementation_policy = PreprocessingPolicy()
        self.assertEqual(
            implementation_policy.lower_quantile,
            main["winsorization"]["lower_quantile"],
        )
        self.assertEqual(
            implementation_policy.upper_quantile,
            main["winsorization"]["upper_quantile"],
        )
        self.assertEqual(
            implementation_policy.add_missing_indicators,
            indicators["enabled"],
        )
        self.assertEqual(
            implementation_policy.indicator_suffix,
            indicators["suffix"],
        )

    def test_temporal_cv_is_the_exact_pit_safe_six_fold_policy(self) -> None:
        temporal = self.policy["temporal_cv"]
        self.assertTrue(temporal["expanding_window"])
        self.assertEqual(temporal["label_embargo_years"], 1)
        self.assertFalse(temporal["future_year_in_training_allowed"])
        self.assertEqual(
            temporal["target_availability_rule"],
            "target_available_at <= min(prediction_timestamp_in_validation_fold)",
        )
        self.assertTrue(temporal["preprocessing_refit_from_zero_inside_each_fold"])
        self.assertFalse(temporal["validation_statistics_may_affect_preprocessing"])

        configured = temporal["folds"]
        self.assertEqual(len(configured), 6)
        self.assertEqual(len(MAIN_EXPANDING_WINDOW_FOLDS), 6)
        expected_safe_train = [6_470, 8_761, 11_089, 13_221, 14_784, 16_280]
        expected_validation = [2_241, 2_133, 1_549, 1_511, 1_638, 1_688]
        for position, (item, fold) in enumerate(
            zip(configured, MAIN_EXPANDING_WINDOW_FOLDS, strict=True)
        ):
            with self.subTest(fold=item["id"]):
                self.assertEqual(item["id"], fold.name)
                self.assertEqual(
                    item["train_feature_years"],
                    [fold.train_start, fold.train_end],
                )
                self.assertEqual(
                    item["validation_feature_years"],
                    [fold.validation_start, fold.validation_end],
                )
                self.assertEqual(
                    item["embargo_feature_years"],
                    [fold.train_end + 1, fold.validation_start - 1],
                )
                self.assertEqual(item["pit_safe_train_n"], expected_safe_train[position])
                self.assertEqual(item["validation_n"], expected_validation[position])
                self.assertEqual(
                    item["base_train_n"] - item["late_labels_excluded_n"],
                    item["pit_safe_train_n"],
                )

    def test_ranking_inference_and_all_mandatory_robustness_are_locked(self) -> None:
        metrics = self.policy["metric_aggregation"]
        self.assertEqual(
            metrics["primary_ranking"]["name"], "pooled_oof_pr_auc"
        )
        self.assertEqual(
            metrics["primary_ranking"]["oof_validation_feature_years"],
            [2015, 2020],
        )
        self.assertEqual(
            metrics["required_additional_reporting"]["per_fold_metric"],
            "pr_auc",
        )
        self.assertEqual(
            metrics["required_additional_reporting"]["standard_deviation_ddof"],
            1,
        )
        self.assertFalse(metrics["secondary_metrics_may_change_primary_ranking"])

        inference = self.policy["inference"]
        self.assertEqual(inference["method"], "clustered_bootstrap")
        self.assertEqual(inference["cluster_column"], "economic_group_id")
        self.assertFalse(inference["cluster_column_is_predictor"])
        self.assertEqual(inference["replicates"], 2_000)
        self.assertEqual(inference["interval"], "percentile")
        self.assertEqual(inference["confidence_level"], 0.95)
        self.assertEqual(inference["lower_quantile"], 0.025)
        self.assertEqual(inference["upper_quantile"], 0.975)
        self.assertEqual(inference["random_seed"], 20260818)
        self.assertFalse(inference["row_level_bootstrap_allowed_as_primary_ci"])

        checks = self.policy["mandatory_ablations_and_robustness"]
        self.assertEqual(
            set(checks),
            {
                "B_without_missing_indicators",
                "complete_case",
                "no_winsorization",
                "purged_economic_group_cv",
                "sparse_row",
            },
        )
        self.assertFalse(
            checks["B_without_missing_indicators"]["missing_indicators_enabled"]
        )
        self.assertTrue(checks["complete_case"]["block_specific"])
        self.assertFalse(checks["no_winsorization"]["winsorization_enabled"])
        self.assertTrue(
            checks["purged_economic_group_cv"][
                "remove_from_fold_train_groups_present_in_fold_validation"
            ]
        )
        sparse = checks["sparse_row"]
        self.assertEqual(sparse["feature_count_total"], 17)
        self.assertEqual(sparse["exclusion_rule"], "available_feature_count <= 10")
        self.assertEqual(sparse["retention_rule"], "available_feature_count >= 11")
        self.assertTrue(
            sparse["apply_to_train_and_evaluation_partitions_in_robustness_rerun"]
        )
        self.assertTrue(sparse["main_supervised_sample_unchanged"])
        self.assertFalse(sparse["alternative_main_sample_policy"])
        self.assertFalse(sparse["may_replace_primary_ranking"])
        self.assertFalse(sparse["test_results_may_select_or_activate_this_policy"])
        for check in checks.values():
            self.assertFalse(check["may_replace_primary_ranking"])

    def test_ipw_external_validation_test_and_model_boundaries_are_locked(self) -> None:
        ipw = self.policy["selection_bias_policy"]["ipw"]
        self.assertEqual(ipw["status"], "diagnostic_evaluated_and_rejected")
        self.assertFalse(ipw["ipw_weighted_predictive_metrics_allowed"])

        validation = self.policy["external_validation"]
        self.assertEqual(validation["feature_years"], [2021, 2022])
        self.assertEqual(validation["n"], 3_547)
        self.assertEqual(
            validation["role"], "one_shot_no_tune_external_development_validation"
        )
        self.assertFalse(validation["may_be_opened_before_full_model_stage_lock"])
        self.assertFalse(
            validation[
                "pipeline_or_models_may_be_tuned_after_results_and_retain_independent_status"
            ]
        )

        test = self.policy["test_policy"]
        self.assertEqual(test["feature_years"], [2023, 2024])
        self.assertFalse(test["used_in_this_freeze"])
        self.assertFalse(test["may_be_opened_before_full_model_stage_freeze"])
        self.assertFalse(
            test[
                "may_select_sample_preprocessing_blocks_cv_metrics_inference_or_robustness"
            ]
        )
        boundary = self.policy["model_stage_boundary"]
        self.assertFalse(boundary["predictive_model_training_performed"])
        for key in (
            "model_families",
            "hyperparameters",
            "class_imbalance_strategy",
            "training_budget_and_seeds",
            "threshold_and_calibration",
            "final_refit_policy",
        ):
            self.assertEqual(boundary[key], "outside_this_freeze")

    def test_versioned_component_hashes_match_manifest(self) -> None:
        for component_group in self.manifest["versioned_components"].values():
            for component in component_group:
                path = ROOT / component["path"]
                with self.subTest(path=component["path"]):
                    self.assertTrue(path.is_file())
                    self.assertEqual(sha256(path), component["sha256"])

    def test_upstream_frozen_inputs_and_generated_artifacts_are_unchanged(self) -> None:
        for upstream in self.manifest["upstream_frozen_inputs"].values():
            manifest_path = ROOT / upstream["manifest"]
            artifact_path = ROOT / upstream["artifact"]
            with self.subTest(upstream=upstream["id"]):
                self.assertEqual(sha256(manifest_path), upstream["manifest_sha256"])
                self.assertEqual(artifact_path.stat().st_size, upstream["artifact_bytes"])
                self.assertEqual(csv_data_rows(artifact_path), upstream["artifact_rows"])
                self.assertEqual(csv_columns(artifact_path), upstream["artifact_columns"])
                self.assertEqual(sha256(artifact_path), upstream["artifact_sha256"])
                self.assertFalse(upstream["changed_by_pipeline_freeze"])

        for artifact in self.manifest["non_versioned_reproduction_checks"]:
            path = ROOT / artifact["path"]
            with self.subTest(artifact=artifact["id"]):
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_size, artifact["bytes"])
                self.assertEqual(csv_data_rows(path), artifact["data_rows"])
                self.assertEqual(csv_columns(path), artifact["columns"])
                self.assertEqual(sha256(path), artifact["sha256"])

    def test_manifest_avoids_self_reference_and_records_only_sparse_addition(self) -> None:
        frozen_paths = {
            component["path"]
            for group in self.manifest["versioned_components"].values()
            for component in group
        }
        self.assertNotIn(
            "configs/supervised_ml_pipeline_v1_freeze_manifest.yaml",
            frozen_paths,
        )
        self.assertNotIn(
            "tests/test_supervised_ml_pipeline_v1_freeze.py",
            frozen_paths,
        )
        sparse = self.manifest["sparse_row_robustness_added_before_freeze"]
        self.assertEqual(sparse["status"], "frozen_mandatory_robustness")
        self.assertFalse(sparse["main_supervised_sample_changed"])
        self.assertFalse(sparse["alternative_main_sample_policy"])
        self.assertFalse(sparse["may_change_primary_ranking"])
        self.assertFalse(sparse["test_results_may_select_or_activate_policy"])
        self.assertEqual(sparse["audited_main_train_rows_excluded_if_run"], 474)
        self.assertEqual(sparse["audited_main_train_rows_retained_if_run"], 19_197)


if __name__ == "__main__":
    unittest.main()

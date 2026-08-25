from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import yaml

from src.modeling.posthoc_exploratory_comparison_v1_0_0 import _zero_relation


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/posthoc_exploratory_comparison_v1_0_0.yaml"
REPORT = ROOT / "reports/posthoc_exploratory_comparison_v1_0_0"


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_config_is_strictly_development_only_and_no_fit() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    analysis = config["analysis"]
    assert analysis["status"] == "AUTHOR_AUTHORIZED_POST_HOC_EXPLORATORY"
    assert analysis["development_feature_years"] == [2015, 2016, 2017, 2018, 2019, 2020]
    assert analysis["forbidden_feature_years"] == [2021, 2022, 2023, 2024]
    for field in (
        "project_model_fit_permitted",
        "prediction_generation_permitted",
        "hyperparameter_search_permitted",
        "additional_seeds_permitted",
        "protected_or_holdout_content_permitted",
    ):
        assert analysis[field] is False


def test_manifest_closes_access_and_experiment_boundaries() -> None:
    manifest = json.loads((REPORT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert manifest["analysis_role"] == "POST_HOC_EXPLORATORY_CONDITIONAL_ON_SELECTION"
    assert manifest["observed_validation_feature_years"] == [2015, 2016, 2017, 2018, 2019, 2020]
    assert manifest["rows"] == 10_760
    assert manifest["positive_n"] == 1_986
    assert manifest["economic_group_count"] == 3_340
    assert manifest["comparison_count"] == 4
    for field in (
        "project_model_fit_performed",
        "prediction_generation_performed",
        "hyperparameter_search_performed",
        "additional_seeds_used",
        "protected_feature_years_opened",
        "holdout_or_test_rows_opened",
    ):
        assert manifest[field] is False


def test_exact_requested_comparison_rows_and_claim_boundaries() -> None:
    tree = _csv(REPORT / "tables/01_paired_clustered_bootstrap_tree_models.csv")
    qnn = _csv(REPORT / "tables/02_seed_matched_qnn_vs_pca_controls.csv")
    assert [row["comparison_id"] for row in tree] == [
        "xgboost_minus_hist_gradient_boosting",
        "xgboost_minus_random_forest",
    ]
    assert [row["comparison_id"] for row in qnn] == [
        "qnn_minus_pca_matched_mlp",
        "qnn_minus_pca_matched_fixed_l2_logistic",
    ]
    for row in tree + qnn:
        assert row["rows"] == "10760"
        assert row["positive_n"] == "1986"
        assert row["economic_group_count"] == "3340"
        assert row["bootstrap_replicates_requested"] == "2000"
        assert row["bootstrap_replicates_valid"] == "2000"
        assert row["bootstrap_replicates_invalid"] == "0"
        assert row["selection_adjusted"] == "False"
        assert row["analysis_role"] == "POST_HOC_EXPLORATORY_CONDITIONAL_ON_SELECTION"


def test_reported_intervals_reproduce_from_saved_bootstrap_draws() -> None:
    summaries = _csv(REPORT / "tables/01_paired_clustered_bootstrap_tree_models.csv")
    summaries += _csv(REPORT / "tables/02_seed_matched_qnn_vs_pca_controls.csv")
    draws = _csv(REPORT / "tables/08_bootstrap_replicates.csv")
    by_comparison: dict[str, list[dict[str, str]]] = {}
    for row in draws:
        by_comparison.setdefault(row["comparison_id"], []).append(row)

    for summary in summaries:
        current = by_comparison[summary["comparison_id"]]
        assert len(current) == 2_000
        assert {row["status"] for row in current} == {"VALID"}
        ap = np.asarray([float(row["delta_ap_a_minus_b"]) for row in current])
        roc = np.asarray([float(row["delta_roc_auc_a_minus_b"]) for row in current])
        ap_ci = np.percentile(ap, [2.5, 50.0, 97.5], method="linear")
        roc_ci = np.percentile(roc, [2.5, 50.0, 97.5], method="linear")
        assert np.allclose(
            ap_ci,
            [
                float(summary["delta_ap_ci_lower"]),
                float(summary["delta_ap_ci_median"]),
                float(summary["delta_ap_ci_upper"]),
            ],
            atol=1e-15,
        )
        assert np.allclose(
            roc_ci,
            [
                float(summary["delta_roc_auc_ci_lower"]),
                float(summary["delta_roc_auc_ci_median"]),
                float(summary["delta_roc_auc_ci_upper"]),
            ],
            atol=1e-15,
        )


def test_seed_matched_alignment_and_fixed_l2_scope_decision() -> None:
    rows = {
        row["comparison_id"]: row
        for row in _csv(REPORT / "tables/05_alignment_checks.csv")
    }
    for comparison_id in (
        "qnn_minus_pca_matched_mlp",
        "qnn_minus_pca_matched_fixed_l2_logistic",
    ):
        row = rows[comparison_id]
        assert row["oof_key_set_same"] == "True"
        assert row["labels_groups_folds_years_same"] == "True"
        assert row["training_seed_protocol_same"] == "True"
        assert row["pca_sha256_same_all_folds"] == "True"
        assert row["preprocessing_sha256_same_all_folds"] == "True"
        assert row["train_membership_sha256_same_all_folds"] == "True"
        assert row["validation_membership_sha256_same_all_folds"] == "True"
        assert row["alignment_status"] == "PASS_SEED_AND_PCA_MATCHED"

    qnn = _csv(REPORT / "tables/02_seed_matched_qnn_vs_pca_controls.csv")
    fixed_l2 = next(
        row
        for row in qnn
        if row["comparison_id"] == "qnn_minus_pca_matched_fixed_l2_logistic"
    )
    assert fixed_l2["request_mapping"] == (
        "EXISTING_FIXED_L2_LOGISTIC_CONTROL_NOT_FIXED_L2_MLP"
    )


def test_source_provenance_contains_no_protected_or_holdout_path() -> None:
    rows = _csv(REPORT / "tables/07_source_provenance.csv")
    assert len(rows) >= 30
    for row in rows:
        lowered = row["source_path"].lower()
        assert "protected_period" not in lowered
        assert "holdout" not in lowered
        assert "test_predictions" not in lowered


def test_existing_variants_and_seed_stability_are_bounded() -> None:
    variants = _csv(REPORT / "tables/03_existing_qnn_variants_descriptive.csv")
    stability = _csv(REPORT / "tables/04_existing_seed_stability.csv")
    assert len(variants) == 4
    assert {row["training_seed"] for row in variants} == {"20260818"}
    assert {row["inferential_role"] for row in variants} == {
        "DESCRIPTIVE_ONLY_NO_NEW_BOOTSTRAP"
    }
    assert {row["family"] for row in stability} == {
        "xgboost",
        "hist_gradient_boosting",
        "random_forest",
        "qnn",
    }
    assert {row["seed_count"] for row in stability} == {"3"}
    assert {row["status"] for row in stability} == {
        "DESCRIPTIVE_ONLY_N3_NOT_CONFIDENCE_INTERVAL"
    }


def test_zero_relation_helper() -> None:
    assert _zero_relation(0.1, 0.2) == "ENTIRELY_ABOVE_ZERO"
    assert _zero_relation(-0.2, -0.1) == "ENTIRELY_BELOW_ZERO"
    assert _zero_relation(-0.1, 0.2) == "INCLUDES_ZERO"

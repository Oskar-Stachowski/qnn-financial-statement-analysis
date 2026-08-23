"""Fail-closed schemas for preregistered secondary development analyses.

This module contains no project-data loading and no estimator execution.  It
validates the frozen pre-execution package and its compact planning artifacts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/secondary_development_analyses_v1_0_0.yaml"


class SecondaryAnalysisIntegrityError(RuntimeError):
    """Raised when a frozen secondary-analysis invariant does not match."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SecondaryAnalysisIntegrityError(message)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), "Secondary-analysis config must be a mapping.")
    require(payload.get("schema_version") == 1, "Unsupported config schema version.")
    section = payload.get("secondary_development_analyses")
    require(isinstance(section, dict), "Missing secondary_development_analyses section.")
    return payload


def require_fields(
    payload: Mapping[str, Any], required: Sequence[str], *, label: str
) -> None:
    missing = [field for field in required if field not in payload]
    require(not missing, f"{label} is missing required fields: {missing}")


def validate_config(config: Mapping[str, Any]) -> dict[str, int]:
    section = config["secondary_development_analyses"]
    require(section["id"] == "secondary_development_analyses_v1_0_0", "Wrong ID.")
    require(section["version"] == "1.0.0", "Wrong version.")
    require(
        section["status"] == "pre_execution_package_frozen_before_project_data_analysis",
        "Package is not in its frozen pre-execution state.",
    )

    role = section["scientific_role"]
    require(role["oof_validation_years"] == list(range(2015, 2021)), "OOF years changed.")
    require(role["permitted_feature_year_bounds"] == [2011, 2020], "Years changed.")
    require(role["protected_feature_years"] == [2021, 2022, 2023, 2024], "Protected years changed.")
    for field in (
        "may_change_primary_ranking",
        "may_change_roster",
        "may_change_ansatz",
        "may_change_hyperparameters",
        "may_change_preprocessing_or_target_definition",
        "may_change_calibration_or_threshold",
        "quantum_advantage_claim_allowed",
    ):
        require(role[field] is False, f"Forbidden scientific permission enabled: {field}")

    expected_stage_order = [
        "pca_matched_controls",
        "interpretability",
        "robustness",
        "compact_report",
        "results_freeze",
    ]
    require(section["stage_order"] == expected_stage_order, "Stage order changed.")

    controls = section["pca_matched_controls"]
    folds = controls["required_folds"]
    require(len(folds) == 6 and len(set(folds)) == 6, "PCA control folds changed.")
    require(len(controls["controls_ordered"]) == 2, "PCA control roster changed.")
    pca_fit_count = len(folds) * len(controls["controls_ordered"])
    require(pca_fit_count == controls["maximum_fold_fits"] == 12, "PCA budget mismatch.")
    require(controls["may_enter_primary_ranking"] is False, "PCA controls may rank.")

    robustness = section["robustness"]
    expected_pipeline = [
        "B_without_missing_indicators",
        "complete_case",
        "no_winsorization",
        "purged_economic_group_cv",
        "sparse_row_available_features_at_least_11_of_17",
    ]
    expected_labels = [
        "deterioration_score_at_least_2",
        "deterioration_score_at_least_4",
        "operating_performance_max_D1_D2_alternative_score_at_least_3",
    ]
    expected_qnn = [
        "replace_entangling_gates_with_identity",
        "first_nonselected_ansatz_in_Q1_registry_order_at_fixed_final_settings",
        "second_nonselected_ansatz_in_Q1_registry_order_at_fixed_final_settings",
        "swap_4_and_6_qubit_PCA_at_fixed_other_settings",
    ]
    require(robustness["pipeline_runs_ordered"] == expected_pipeline, "Pipeline robustness changed.")
    require(robustness["label_runs_ordered"] == expected_labels, "Label robustness changed.")
    require(robustness["qnn_structural_runs_ordered"] == expected_qnn, "QNN robustness changed.")
    robust_folds = robustness["required_folds"]
    global_fits = (len(expected_pipeline) + len(expected_labels)) * len(robust_folds)
    qnn_fits = len(expected_qnn) * len(robust_folds)
    require(global_fits == robustness["expected_global_winner_fold_fits"] == 48, "Winner robustness budget mismatch.")
    require(qnn_fits == robustness["expected_qnn_structural_fold_fits_if_feasible"] == 24, "QNN robustness budget mismatch.")
    require(robustness["retuning_allowed"] is False, "Robustness retuning enabled.")

    interpretation = section["interpretability"]
    require(interpretation["common_grouped_permutation"]["repetitions"] == 20, "Permutation repetitions changed.")
    require(interpretation["common_grouped_permutation"]["permutation_seed"] == 20260818, "Permutation seed changed.")
    limits = interpretation["sampling_limits"]
    require(limits == {
        "tree_background_train_rows_max": 512,
        "tree_oof_rows_per_fold_max": 500,
        "mlp_oof_rows_per_fold_max": 200,
        "mlp_integrated_gradients_steps": 64,
        "qnn_oof_rows_per_fold_max": 100,
    }, "Interpretability sampling limits changed.")

    resources = section["resource_policy"]
    require(resources["pca_matched_control_fit_cap"] == 12, "PCA resource cap changed.")
    require(resources["global_winner_robustness_fit_cap"] == 48, "Winner resource cap changed.")
    require(resources["qnn_structural_fit_cap"] == 24, "QNN resource cap changed.")
    require(resources["automatic_raw_data_restore_allowed"] is False, "Automatic raw restore enabled.")

    boundary = section["pre_execution_boundary"]
    require(boundary["this_package_may_read_project_data"] is False, "Project-data read enabled.")
    require(boundary["this_package_may_fit_project_models"] is False, "Project fit enabled.")
    require(boundary["protected_period_access_authorized"] is False, "Protected access enabled.")

    return {
        "pca_matched_control_fold_fits": pca_fit_count,
        "global_winner_robustness_fold_fits": global_fits,
        "qnn_structural_fold_fits": qnn_fits,
    }


def verify_authority(config: Mapping[str, Any], root: Path = ROOT) -> dict[str, str]:
    authority = config["secondary_development_analyses"]["authority"]
    verified: dict[str, str] = {}
    for name, item in authority.items():
        path = (root / str(item["path"])).resolve()
        require(path.is_relative_to(root.resolve()), f"Authority escapes repository: {name}")
        require(path.is_file(), f"Missing authority file: {path}")
        actual = file_sha256(path)
        require(actual == str(item["sha256"]), f"Authority SHA-256 mismatch: {name}")
        verified[name] = actual
    return verified


def validate_plan(plan: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    required = config["secondary_development_analyses"]["output_schemas"]["plan"]["required_fields"]
    require_fields(plan, required, label="secondary-analysis plan")
    require(plan["status"] == "PLAN_ONLY_NO_PROJECT_DATA_ACCESS", "Plan status changed.")
    require(plan["protected_feature_years_opened"] is False, "Plan opened protected years.")
    require(plan["project_data_read"] is False, "Plan read project data.")
    require(plan["project_model_fit_performed"] is False, "Plan fit a model.")
    tasks = plan.get("tasks") or []
    identities = [str(task["task_identity_sha256"]) for task in tasks]
    require(len(identities) == len(set(identities)), "Plan contains duplicate task identities.")
    for task in tasks:
        require(canonical_sha256(task["task_identity"]) == task["task_identity_sha256"], "Task identity hash mismatch.")


def validate_synthetic_smoke(payload: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    required = config["secondary_development_analyses"]["output_schemas"]["synthetic_smoke"]["required_fields"]
    require_fields(payload, required, label="synthetic smoke")
    require(payload["status"] == "PASS", "Synthetic smoke did not pass.")
    require(payload["protected_feature_years_opened"] is False, "Smoke opened protected years.")
    require(payload["project_data_read"] is False, "Smoke read project data.")
    checks = payload["checks"]
    require(isinstance(checks, list) and checks, "Synthetic smoke checks are empty.")
    require(all(item.get("status") == "PASS" for item in checks), "Synthetic check failed.")

"""Build a thesis-ready report from frozen secondary-development results.

This module is reporting-only. It reads completed development artifacts for
OOF years 2015--2020, never constructs or fits a model, and never opens the
protected 2021--2024 period.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
import yaml  # noqa: E402

from src.modeling.secondary_analysis_schemas import canonical_sha256, file_sha256
from src.modeling.verify_post_coarse_results_freeze import (
    verify_post_coarse_results_freeze,
)
from src.modeling.verify_secondary_development_results_freeze_v1_1_7 import (
    verify_secondary_development_results_freeze_v1_1_7,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    ROOT / "configs/secondary_development_thesis_reporting_v1_0_0.yaml"
)
DEFAULT_OUTPUT = ROOT / "reports/secondary_development_thesis_v1_0_0"
EXECUTION_ROOT = ROOT / "data/model_runs/secondary_development_v1_1_6"
REPORT_ROOT = ROOT / "data/model_runs/secondary_development_v1_1_7"
FOLD_IDS = tuple(f"fold_{year}" for year in range(2015, 2021))
PROTECTED_YEARS = {2021, 2022, 2023, 2024}
PACKAGE_FILES = (
    "configs/secondary_development_thesis_reporting_v1_0_0.yaml",
    "src/modeling/secondary_development_thesis_reporting_v1_0_0.py",
    "src/modeling/verify_secondary_development_thesis_report_v1_0_0.py",
    "scripts/run_secondary_development_thesis_report_v1_0_0.sh",
    "tests/test_secondary_development_thesis_reporting_v1_0_0.py",
    "docs/12_9_secondary_development_thesis_reporting_v1_0_0.md",
)

FAMILY_LABELS = {
    "fixed_l2_logistic": "Logistic fixed L2",
    "elastic_net_logistic": "Logistic Elastic Net",
    "rbf_svm": "SVM RBF",
    "random_forest": "Random Forest",
    "hist_gradient_boosting": "HistGradientBoosting",
    "xgboost": "XGBoost",
    "pytorch_mlp": "MLP",
    "qnn": "QNN",
}
VARIANT_LABELS = {
    "fixed_l2_logistic_same_qnn_representation": "Logistic fixed L2 — PCA QNN",
    "pytorch_mlp_same_qnn_representation": "MLP — PCA QNN",
    "B_without_missing_indicators": "Bez wskaźników braków",
    "complete_case": "Complete case",
    "no_winsorization": "Bez winsoryzacji",
    "purged_economic_group_cv": "Purged economic-group CV",
    "sparse_row_available_features_at_least_11_of_17": "Wiersze ≥11/17 cech",
    "deterioration_score_at_least_2": "Target: score ≥2",
    "deterioration_score_at_least_4": "Target: score ≥4",
    "operating_performance_max_D1_D2_alternative_score_at_least_3": (
        "Target: max(D1,D2)+D3+D4+D5 ≥3"
    ),
    "replace_entangling_gates_with_identity": "Brak splątania (identity)",
    "first_nonselected_ansatz_in_Q1_registry_order_at_fixed_final_settings": (
        "RY_RZ_CZ_BRICKWORK"
    ),
    "second_nonselected_ansatz_in_Q1_registry_order_at_fixed_final_settings": (
        "RY_CRX_RING"
    ),
    "swap_4_and_6_qubit_PCA_at_fixed_other_settings": "PCA 6 qubitów",
}


class SecondaryThesisReportingError(RuntimeError):
    """Raised when a frozen reporting invariant is violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SecondaryThesisReportingError(message)


def _load_json(path: Path) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), f"Missing JSON source: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"Expected a JSON object: {path}")
    return payload


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise SecondaryThesisReportingError(
            result.stderr.strip() or "Reporting-package Git gate failed."
        )
    return result.stdout.strip()


def verify_reporting_package(
    config_path: Path = DEFAULT_CONFIG, *, require_committed: bool = False
) -> dict[str, Any]:
    config_path = config_path.resolve()
    _require(config_path == DEFAULT_CONFIG.resolve(), "Only the canonical config is valid.")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    _require(isinstance(config, dict), "Reporting config must be a mapping.")
    section = config.get("secondary_development_thesis_reporting") or {}
    _require(
        section.get("id") == "secondary_development_thesis_reporting_v1_0_0"
        and str(section.get("version")) == "1.0.0"
        and section.get("status") == "REPORTING_ONLY",
        "Unexpected reporting-package identity.",
    )
    _require(section.get("project_model_fit_permitted") is False, "Fit is permitted.")
    _require(
        section.get("protected_feature_years_permitted") is False,
        "Protected years are permitted.",
    )
    source_entries = config.get("source_authority") or []
    _require(len(source_entries) == 6, "Unexpected source-authority cardinality.")
    for entry in source_entries:
        path = (ROOT / str(entry["path"])).resolve()
        _require(path.is_relative_to(ROOT), f"Authority path escapes repository: {path}")
        _require(path.is_file() and not path.is_symlink(), f"Missing authority: {path}")
        _require(file_sha256(path) == entry["sha256"], f"Authority hash changed: {path}")

    secondary = verify_secondary_development_results_freeze_v1_1_7(
        require_committed=True
    )
    post_coarse = verify_post_coarse_results_freeze()
    _require(secondary["status"] == post_coarse["status"] == "PASS", "Source freeze failed.")

    package_git_index_sha256 = "NOT_REQUIRED_FOR_READ_ONLY_VERIFY"
    if require_committed:
        for path in PACKAGE_FILES:
            _git("ls-files", "--error-unmatch", "--", path)
        dirty = _git("status", "--porcelain", "--", *PACKAGE_FILES)
        _require(not dirty, "Reporting package is uncommitted or modified:\n" + dirty)
        rows = _git("ls-files", "-s", "--", *PACKAGE_FILES).splitlines()
        _require(len(rows) == len(PACKAGE_FILES), "Reporting Git cardinality mismatch.")
        package_git_index_sha256 = canonical_sha256(sorted(rows))
    return {
        "status": "PASS",
        "package_git_index_sha256": package_git_index_sha256,
        "secondary_freeze_verdict": secondary["verdict"],
        "post_coarse_freeze_verdict": post_coarse["verdict"],
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def _load_tasks() -> list[dict[str, Any]]:
    paths = sorted((EXECUTION_ROOT / "task_results").glob("*.json"))
    _require(len(paths) == 96, "Expected exactly 96 frozen task results.")
    tasks: list[dict[str, Any]] = []
    for path in paths:
        payload = _load_json(path)
        _require(payload.get("status") == "COMPLETE", f"Incomplete task: {path}")
        _require(payload.get("failure_code") is None, f"Failed task: {path}")
        _require(
            payload.get("protected_feature_years_opened") is False,
            f"Task opened a protected year: {path}",
        )
        payload["_source_path"] = str(path.relative_to(ROOT))
        tasks.append(payload)
    return tasks


def _prediction_rows(task: Mapping[str, Any]) -> list[dict[str, Any]]:
    relative = task.get("prediction_artifact")
    _require(isinstance(relative, str), "Prediction artifact is missing.")
    path = (EXECUTION_ROOT / relative).resolve()
    _require(path.is_relative_to(EXECUTION_ROOT), f"Prediction path escaped: {path}")
    _require(
        file_sha256(path) == task.get("prediction_artifact_sha256"),
        f"Prediction artifact changed: {path}",
    )
    payload = _load_json(path)
    rows = payload.get("rows") or []
    _require(isinstance(rows, list) and rows, f"Empty prediction artifact: {path}")
    fold_id = str((task.get("task_identity") or {}).get("fold_id"))
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for row in rows:
        identity = str(row.get("research_universe_company_year_id"))
        _require(identity not in seen, f"Duplicate prediction identity: {path}")
        seen.add(identity)
        year = int(row.get("validation_feature_year", -1))
        _require(year in range(2015, 2021), f"Protected/invalid prediction year: {path}")
        _require(year not in PROTECTED_YEARS, f"Protected prediction year: {path}")
        _require(row.get("fold_id") == fold_id, f"Prediction fold mismatch: {path}")
        score = float(row["raw_score"])
        _require(math.isfinite(score), f"Non-finite prediction: {path}")
        _require(
            float.fromhex(str(row["raw_score_float64_hex"])) == score,
            f"Prediction float identity mismatch: {path}",
        )
        label = int(row["target_label"])
        _require(label in (0, 1), f"Invalid target label: {path}")
        normalized.append(
            {
                "identity": identity,
                "fold_id": fold_id,
                "year": year,
                "label": label,
                "score": score,
            }
        )
    _require(len(rows) == int(task.get("validation_rows", -1)), f"Row count mismatch: {path}")
    return normalized


def _metric_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    _require(bool(rows), "Cannot summarize empty predictions.")
    identities = [str(row["identity"]) for row in rows]
    _require(len(identities) == len(set(identities)), "Duplicate pooled prediction identity.")
    labels = np.asarray([int(row["label"]) for row in rows], dtype=np.int64)
    scores = np.asarray([float(row["score"]) for row in rows], dtype=np.float64)
    _require(set(np.unique(labels).tolist()) == {0, 1}, "Pooled labels lack both classes.")
    fold_pr_auc: list[float] = []
    fold_roc_auc: list[float] = []
    for fold_id in FOLD_IDS:
        selected = [row for row in rows if row["fold_id"] == fold_id]
        _require(selected, f"Missing predictions for {fold_id}.")
        fold_labels = np.asarray([int(row["label"]) for row in selected])
        fold_scores = np.asarray([float(row["score"]) for row in selected])
        _require(set(np.unique(fold_labels).tolist()) == {0, 1}, f"Single-class {fold_id}.")
        fold_pr_auc.append(float(average_precision_score(fold_labels, fold_scores)))
        fold_roc_auc.append(float(roc_auc_score(fold_labels, fold_scores)))
    return {
        "n": int(labels.size),
        "positive_n": int(labels.sum()),
        "positive_share": float(labels.mean()),
        "pooled_oof_pr_auc": float(average_precision_score(labels, scores)),
        "pooled_oof_roc_auc": float(roc_auc_score(labels, scores)),
        "fold_pr_auc_mean": float(np.mean(fold_pr_auc)),
        "fold_pr_auc_sample_sd": float(np.std(fold_pr_auc, ddof=1)),
        "fold_roc_auc_mean": float(np.mean(fold_roc_auc)),
        "fold_roc_auc_sample_sd": float(np.std(fold_roc_auc, ddof=1)),
    }


def _reference_row(
    reference_id: str, values: Mapping[str, Any], comparison_note: str
) -> dict[str, Any]:
    positive_n = int(values["positive_n"])
    n = int(values["n"])
    return {
        "analysis_id": reference_id,
        "display_label": "Zamrożona referencja (średnia 3 seedów)",
        "family": values["family"],
        "variant_kind": "frozen_reference",
        "training_seed": "AVERAGED_20260818_20260819_20260820",
        "n": n,
        "positive_n": positive_n,
        "positive_share": positive_n / n,
        "pooled_oof_pr_auc": float(values["pooled_oof_pr_auc"]),
        "pooled_oof_roc_auc": float(values["pooled_oof_roc_auc"]),
        "descriptive_delta_pr_auc_vs_frozen_reference": 0.0,
        "descriptive_delta_roc_auc_vs_frozen_reference": 0.0,
        "direct_seed_matched_comparison": False,
        "comparison_note": comparison_note,
    }


def _variant_kind(analysis_id: str, family: str) -> str:
    if family == "qnn":
        return "qnn_structural"
    if analysis_id.startswith("deterioration_score") or analysis_id.startswith(
        "operating_performance"
    ):
        return "label_definition"
    if "same_qnn_representation" in analysis_id:
        return "pca_matched_control"
    return "pipeline_robustness"


def _build_variant_tables(
    tasks: Sequence[Mapping[str, Any]], config: Mapping[str, Any]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    selected = [
        task
        for task in tasks
        if (task.get("task_identity") or {}).get("stage")
        in {"pca_matched_controls", "robustness"}
    ]
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    fold_rows: list[dict[str, Any]] = []
    for task in selected:
        identity = task["task_identity"]
        key = (str(identity["analysis_id"]), str(identity["family"]))
        groups.setdefault(key, []).append(task)
        prediction_rows = _prediction_rows(task)
        labels = np.asarray([row["label"] for row in prediction_rows])
        scores = np.asarray([row["score"] for row in prediction_rows])
        fold_rows.append(
            {
                "analysis_id": key[0],
                "display_label": VARIANT_LABELS[key[0]],
                "family": key[1],
                "variant_kind": _variant_kind(*key),
                "fold_id": identity["fold_id"],
                "training_seed": identity.get("training_seed"),
                "train_rows": int(task["train_rows"]),
                "validation_rows": len(prediction_rows),
                "positive_n": int(labels.sum()),
                "positive_share": float(labels.mean()),
                "pr_auc": float(average_precision_score(labels, scores)),
                "roc_auc": float(roc_auc_score(labels, scores)),
                "status": task["status"],
            }
        )
    _require(len(groups) == 14 and len(fold_rows) == 84, "Variant roster changed.")

    references = config["frozen_references"]
    rows: list[dict[str, Any]] = []
    for (analysis_id, family), group_tasks in sorted(groups.items()):
        ordered = sorted(
            group_tasks,
            key=lambda task: FOLD_IDS.index(str(task["task_identity"]["fold_id"])),
        )
        _require(
            tuple(str(task["task_identity"]["fold_id"]) for task in ordered)
            == FOLD_IDS,
            f"Variant fold roster changed: {analysis_id}",
        )
        pooled: list[dict[str, Any]] = []
        for task in ordered:
            pooled.extend(_prediction_rows(task))
        metrics = _metric_summary(pooled)
        reference_key = (
            "qnn_three_seed_average" if family in {"qnn", "pytorch_mlp", "fixed_l2_logistic"}
            else "xgboost_three_seed_average"
        )
        reference = references[reference_key]
        rows.append(
            {
                "analysis_id": analysis_id,
                "display_label": VARIANT_LABELS[analysis_id],
                "family": family,
                "variant_kind": _variant_kind(analysis_id, family),
                "training_seed": 20260818,
                **metrics,
                "descriptive_delta_pr_auc_vs_frozen_reference": (
                    metrics["pooled_oof_pr_auc"] - float(reference["pooled_oof_pr_auc"])
                ),
                "descriptive_delta_roc_auc_vs_frozen_reference": (
                    metrics["pooled_oof_roc_auc"] - float(reference["pooled_oof_roc_auc"])
                ),
                "direct_seed_matched_comparison": False,
                "comparison_note": (
                    "Single-seed secondary variant versus frozen three-seed average; "
                    "delta is descriptive and does not authorize reranking."
                ),
            }
        )
    variants = pd.DataFrame(rows)
    pca = variants[variants["variant_kind"] == "pca_matched_control"].copy()
    pca = pd.concat(
        [
            pd.DataFrame(
                [
                    _reference_row(
                        "frozen_qnn_three_seed_reference",
                        references["qnn_three_seed_average"],
                        "Frozen QNN L+D+R reference; not seed-matched to controls.",
                    )
                ]
            ),
            pca,
        ],
        ignore_index=True,
    )
    classical = variants[
        (variants["family"] == "xgboost")
        & (variants["variant_kind"].isin({"pipeline_robustness", "label_definition"}))
    ].copy()
    classical = pd.concat(
        [
            pd.DataFrame(
                [
                    _reference_row(
                        "frozen_xgboost_three_seed_reference",
                        references["xgboost_three_seed_average"],
                        "Frozen XGBoost L+D+R reference; not seed-matched to variants.",
                    )
                ]
            ),
            classical,
        ],
        ignore_index=True,
    )
    qnn = variants[variants["family"] == "qnn"].copy()
    qnn = pd.concat(
        [
            pd.DataFrame(
                [
                    _reference_row(
                        "frozen_qnn_three_seed_reference",
                        references["qnn_three_seed_average"],
                        "Frozen QNN L+D+R reference; not seed-matched to variants.",
                    )
                ]
            ),
            qnn,
        ],
        ignore_index=True,
    )
    return pca, classical, qnn, pd.DataFrame(fold_rows)


def _interpretability_tasks(
    tasks: Sequence[Mapping[str, Any]], analysis_id: str
) -> list[Mapping[str, Any]]:
    return [
        task
        for task in tasks
        if (task.get("task_identity") or {}).get("analysis_id") == analysis_id
    ]


def _build_common_permutation(tasks: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    common = _interpretability_tasks(tasks, "common_grouped_permutation")
    _require(len(common) == 8, "Common permutation family roster changed.")
    records: list[dict[str, Any]] = []
    for task in common:
        family = str(task["task_identity"]["family"])
        folds = task.get("fold_results") or []
        _require(len(folds) == 6, f"Permutation fold count changed: {family}")
        for fold_id, fold in zip(FOLD_IDS, folds, strict=True):
            _require(fold.get("status") == "COMPLETE", f"Permutation fold failed: {family}")
            _require(
                fold.get("protected_feature_years_opened") is False,
                f"Permutation opened protected year: {family}",
            )
            for feature in fold.get("feature_results") or []:
                records.append(
                    {
                        "family": family,
                        "family_label": FAMILY_LABELS[family],
                        "fold_id": fold_id,
                        "feature_name": feature["feature_name"],
                        "mean_pr_auc_decrease": float(feature["mean_decrease"]),
                        "repeat_sample_sd": float(feature["sample_sd"]),
                        "baseline_pr_auc": float(fold["baseline_pr_auc"]),
                        "validation_economic_groups": int(
                            fold["validation_economic_groups"]
                        ),
                        "duplicate_rows_dropped": int(fold["duplicate_rows_dropped"]),
                    }
                )
    detail = pd.DataFrame(records)
    _require(len(detail) == 8 * 6 * 17, "Permutation feature cardinality changed.")
    rows: list[dict[str, Any]] = []
    for (family, feature), group in detail.groupby(["family", "feature_name"], sort=True):
        values = group["mean_pr_auc_decrease"].to_numpy(dtype=float)
        rows.append(
            {
                "family": family,
                "family_label": FAMILY_LABELS[str(family)],
                "feature_name": feature,
                "mean_pr_auc_decrease_across_folds": float(np.mean(values)),
                "fold_sample_sd": float(np.std(values, ddof=1)),
                "min_fold_decrease": float(np.min(values)),
                "max_fold_decrease": float(np.max(values)),
                "positive_fold_count": int(np.sum(values > 0)),
                "mean_repeat_sample_sd": float(group["repeat_sample_sd"].mean()),
                "mean_fold_baseline_pr_auc": float(group["baseline_pr_auc"].mean()),
                "duplicate_rows_dropped_total": int(
                    group["duplicate_rows_dropped"].sum()
                ),
            }
        )
    result = pd.DataFrame(rows)
    result["rank_within_family"] = result.groupby("family")[
        "mean_pr_auc_decrease_across_folds"
    ].rank(method="first", ascending=False)
    result["rank_within_family"] = result["rank_within_family"].astype(int)
    return result.sort_values(["family", "rank_within_family"]).reset_index(drop=True)


def _vector_task_table(
    task: Mapping[str, Any], *, method: str, value_key: str, signed: bool
) -> pd.DataFrame:
    folds = task.get("fold_results") or []
    _require(len(folds) == 6, f"Detailed interpretation fold count changed: {method}")
    names = list(folds[0]["feature_names"])
    values: list[list[float]] = []
    stability: list[list[float]] = []
    for fold in folds:
        _require(list(fold["feature_names"]) == names, f"Feature roster changed: {method}")
        vector = [float(value) for value in fold[value_key]]
        _require(len(vector) == len(names), f"Interpretation vector changed: {method}")
        values.append(vector)
        if "sign_stability" in fold:
            stability.append([float(value) for value in fold["sign_stability"]])
    array = np.asarray(values, dtype=float)
    rows: list[dict[str, Any]] = []
    for index, feature in enumerate(names):
        mean_value = float(np.mean(array[:, index]))
        rows.append(
            {
                "family": task["task_identity"]["family"],
                "method": method,
                "feature_name": feature,
                "mean_value_across_folds": mean_value,
                "mean_abs_value_across_folds": float(np.mean(np.abs(array[:, index]))),
                "fold_sample_sd": float(np.std(array[:, index], ddof=1)),
                "direction": (
                    "positive" if signed and mean_value > 0 else "negative" if signed and mean_value < 0 else "unsigned"
                ),
                "mean_within_fold_sign_stability": (
                    float(np.mean(np.asarray(stability)[:, index])) if stability else None
                ),
            }
        )
    result = pd.DataFrame(rows)
    result["rank_within_method"] = result["mean_abs_value_across_folds"].rank(
        method="first", ascending=False
    ).astype(int)
    return result.sort_values("rank_within_method").reset_index(drop=True)


def _build_detailed_interpretability(
    tasks: Sequence[Mapping[str, Any]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    specs = (
        (
            "standardized_coefficients_odds_ratios_sign_fold_seed_stability",
            "Elastic Net standardized coefficient",
            "mean_coefficient",
            True,
        ),
        (
            "interventional_TreeSHAP_seed_20260818_models",
            "XGBoost interventional TreeSHAP",
            "mean_abs_shap",
            False,
        ),
        (
            "Integrated_Gradients_on_logit_seed_20260818_models",
            "MLP Integrated Gradients",
            "mean_abs_integrated_gradients",
            False,
        ),
    )
    frames: list[pd.DataFrame] = []
    for analysis_id, method, value_key, signed in specs:
        matching = _interpretability_tasks(tasks, analysis_id)
        _require(len(matching) == 1, f"Detailed method roster changed: {analysis_id}")
        frames.append(
            _vector_task_table(
                matching[0], method=method, value_key=value_key, signed=signed
            )
        )
    detailed = pd.concat(frames, ignore_index=True)

    qnn_tasks = _interpretability_tasks(
        tasks, "PCA_loadings_explained_variance_encoded_sensitivity_fold_seed_stability"
    )
    _require(len(qnn_tasks) == 1, "QNN interpretation roster changed.")
    qnn_task = qnn_tasks[0]
    folds = qnn_task.get("fold_results") or []
    _require(len(folds) == 6, "QNN interpretation fold count changed.")
    component_names = list(folds[0]["encoded_feature_names"])
    feature_names = list(
        _interpretability_tasks(
            tasks, "Integrated_Gradients_on_logit_seed_20260818_models"
        )[0]["fold_results"][0]["feature_names"]
    )
    sensitivity = np.asarray(
        [fold["mean_abs_encoded_sensitivity"] for fold in folds], dtype=float
    )
    eigenvalues = np.asarray([fold["pca_explained_variance"] for fold in folds], dtype=float)
    components = np.asarray([fold["pca_components"] for fold in folds], dtype=float)
    _require(
        sensitivity.shape == eigenvalues.shape == (6, 4)
        and components.shape == (6, 4, 34),
        "QNN interpretation tensor shape changed.",
    )
    qnn_sensitivity = pd.DataFrame(
        [
            {
                "component": component,
                "mean_abs_encoded_sensitivity_across_folds": float(
                    np.mean(sensitivity[:, index])
                ),
                "fold_sample_sd": float(np.std(sensitivity[:, index], ddof=1)),
                "mean_pca_eigenvalue_across_folds": float(
                    np.mean(eigenvalues[:, index])
                ),
                "evaluation_rows_per_fold": int(folds[0]["evaluation_rows"]),
            }
            for index, component in enumerate(component_names)
        ]
    )
    qnn_sensitivity["sensitivity_rank"] = qnn_sensitivity[
        "mean_abs_encoded_sensitivity_across_folds"
    ].rank(method="first", ascending=False).astype(int)

    loading_rows: list[dict[str, Any]] = []
    for component_index, component in enumerate(component_names):
        for feature_index, feature in enumerate(feature_names):
            values = components[:, component_index, feature_index]
            loading_rows.append(
                {
                    "component": component,
                    "feature_name": feature,
                    "mean_loading_across_folds": float(np.mean(values)),
                    "mean_abs_loading_across_folds": float(np.mean(np.abs(values))),
                    "fold_sample_sd": float(np.std(values, ddof=1)),
                }
            )
    loadings = pd.DataFrame(loading_rows)
    loadings["rank_within_component"] = loadings.groupby("component")[
        "mean_abs_loading_across_folds"
    ].rank(method="first", ascending=False).astype(int)
    return detailed, qnn_sensitivity.sort_values("sensitivity_rank"), loadings.sort_values(
        ["component", "rank_within_component"]
    )


def _phase_completeness() -> pd.DataFrame:
    phases = (
        ("pca_matched_controls", 12),
        ("interpretability", 12),
        ("robustness_classical", 48),
        ("robustness_qnn", 24),
    )
    rows: list[dict[str, Any]] = []
    for phase, expected in phases:
        payload = _load_json(EXECUTION_ROOT / "phase_manifests" / f"{phase}.json")
        rows.append(
            {
                "phase": phase,
                "status": payload["status"],
                "planned_tasks": int(payload["planned_tasks"]),
                "complete_tasks": int(payload["complete_tasks"]),
                "failed_tasks": int(payload["failed_tasks"]),
                "expected_tasks": expected,
                "protected_feature_years_opened": payload[
                    "protected_feature_years_opened"
                ],
            }
        )
    return pd.DataFrame(rows)


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format="%.12g", lineterminator="\n")


def _style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "#F7F8FA",
            "axes.edgecolor": "#D1D5DB",
            "axes.grid": True,
            "grid.color": "#E5E7EB",
            "grid.linewidth": 0.7,
            "axes.axisbelow": True,
            "font.size": 10,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "svg.hashsalt": "secondary-development-thesis-v1.0.0",
        }
    )


def _save_figure(figure: plt.Figure, base_path: Path) -> list[Path]:
    png = base_path.with_suffix(".png")
    svg = base_path.with_suffix(".svg")
    figure.savefig(
        png,
        dpi=180,
        bbox_inches="tight",
        metadata={"Software": "secondary-development-thesis-v1.0.0"},
    )
    figure.savefig(
        svg,
        bbox_inches="tight",
        metadata={"Date": None, "Creator": "secondary-development-thesis-v1.0.0"},
    )
    plt.close(figure)
    return [png, svg]


def _metric_bar_figure(
    frame: pd.DataFrame, title: str, color_map: Mapping[str, str]
) -> plt.Figure:
    plot = frame.iloc[::-1].reset_index(drop=True)
    figure, axis = plt.subplots(figsize=(9.2, max(3.4, 0.55 * len(plot) + 1.4)))
    colors = [color_map.get(str(kind), "#2563EB") for kind in plot["variant_kind"]]
    bars = axis.barh(plot["display_label"], plot["pooled_oof_pr_auc"], color=colors)
    axis.set_title(title, loc="left")
    axis.set_xlabel("Pooled OOF PR-AUC (2015–2020)")
    lower = max(0.0, float(plot["pooled_oof_pr_auc"].min()) - 0.025)
    upper = min(1.0, float(plot["pooled_oof_pr_auc"].max()) + 0.03)
    axis.set_xlim(lower, upper)
    for bar, value in zip(bars, plot["pooled_oof_pr_auc"], strict=True):
        axis.text(
            float(value) + 0.001,
            bar.get_y() + bar.get_height() / 2,
            f"{float(value):.4f}",
            va="center",
            fontsize=9,
        )
    axis.grid(axis="y", visible=False)
    figure.tight_layout()
    return figure


def _build_figures(
    figures_dir: Path,
    pca: pd.DataFrame,
    classical: pd.DataFrame,
    qnn: pd.DataFrame,
    common: pd.DataFrame,
    detailed: pd.DataFrame,
    qnn_sensitivity: pd.DataFrame,
) -> list[Path]:
    figures_dir.mkdir(parents=True, exist_ok=True)
    _style()
    generated: list[Path] = []
    generated.extend(
        _save_figure(
            _metric_bar_figure(
                pca,
                "PCA-matched controls względem zamrożonej referencji QNN",
                {"frozen_reference": "#111827", "pca_matched_control": "#2563EB"},
            ),
            figures_dir / "01_pca_matched_controls_pr_auc",
        )
    )
    generated.extend(
        _save_figure(
            _metric_bar_figure(
                classical,
                "Robustness globalnego zwycięzcy XGBoost",
                {
                    "frozen_reference": "#111827",
                    "pipeline_robustness": "#2563EB",
                    "label_definition": "#D97706",
                },
            ),
            figures_dir / "02_xgboost_robustness_pr_auc",
        )
    )
    generated.extend(
        _save_figure(
            _metric_bar_figure(
                qnn,
                "Strukturalna robustness QNN",
                {"frozen_reference": "#111827", "qnn_structural": "#7C3AED"},
            ),
            figures_dir / "03_qnn_structural_robustness_pr_auc",
        )
    )

    family_order = list(FAMILY_LABELS)
    feature_order = (
        common.groupby("feature_name")["mean_pr_auc_decrease_across_folds"]
        .mean()
        .sort_values(ascending=False)
        .head(10)
        .index.tolist()
    )
    matrix = (
        common.pivot(
            index="feature_name",
            columns="family",
            values="mean_pr_auc_decrease_across_folds",
        )
        .reindex(index=feature_order, columns=family_order)
        .to_numpy(dtype=float)
    )
    figure, axis = plt.subplots(figsize=(11.5, 6.4))
    bound = max(abs(float(np.nanmin(matrix))), abs(float(np.nanmax(matrix))))
    image = axis.imshow(matrix, aspect="auto", cmap="RdBu_r", vmin=-bound, vmax=bound)
    axis.set_title("Wspólna permutation importance — średni spadek PR-AUC", loc="left")
    axis.set_xticks(range(len(family_order)), [FAMILY_LABELS[item] for item in family_order])
    axis.set_yticks(range(len(feature_order)), feature_order)
    axis.tick_params(axis="x", rotation=38)
    for row_index in range(matrix.shape[0]):
        for column_index in range(matrix.shape[1]):
            value = matrix[row_index, column_index]
            axis.text(
                column_index,
                row_index,
                f"{value:.3f}",
                ha="center",
                va="center",
                fontsize=7,
                color="white" if abs(value) > 0.55 * bound else "#111827",
            )
    figure.colorbar(image, ax=axis, label="Mean PR-AUC decrease")
    axis.grid(False)
    figure.tight_layout()
    generated.extend(
        _save_figure(figure, figures_dir / "04_common_permutation_importance_heatmap")
    )

    methods = list(detailed["method"].drop_duplicates())
    figure, axes = plt.subplots(1, len(methods), figsize=(15.2, 5.8), squeeze=False)
    for axis, method in zip(axes[0], methods, strict=True):
        top = detailed[detailed["method"] == method].nsmallest(8, "rank_within_method")
        top = top.iloc[::-1]
        axis.barh(top["feature_name"], top["mean_abs_value_across_folds"], color="#2563EB")
        axis.set_title(method, loc="left", fontsize=10)
        axis.set_xlabel("Mean absolute value")
        axis.grid(axis="y", visible=False)
    figure.suptitle("Szczegółowa interpretowalność — najważniejsze cechy", x=0.02, ha="left")
    figure.tight_layout()
    generated.extend(
        _save_figure(figure, figures_dir / "05_detailed_feature_importance")
    )

    ordered = qnn_sensitivity.sort_values("sensitivity_rank")
    figure, axis = plt.subplots(figsize=(7.8, 4.6))
    axis.bar(
        ordered["component"],
        ordered["mean_abs_encoded_sensitivity_across_folds"],
        yerr=ordered["fold_sample_sd"],
        capsize=4,
        color="#7C3AED",
    )
    axis.set_title("QNN — czułość zakodowanych komponentów PCA", loc="left")
    axis.set_ylabel("Mean absolute sensitivity across folds")
    axis.set_xlabel("Zakodowany komponent")
    axis.grid(axis="x", visible=False)
    figure.tight_layout()
    generated.extend(
        _save_figure(figure, figures_dir / "06_qnn_encoded_sensitivity")
    )
    return generated


def _format(value: Any) -> str:
    return f"{float(value):.6f}"


def _top_features(frame: pd.DataFrame, method: str, count: int = 5) -> str:
    selected = frame[frame["method"] == method].nsmallest(count, "rank_within_method")
    return ", ".join(str(value) for value in selected["feature_name"])


def _build_summary(
    pca: pd.DataFrame,
    classical: pd.DataFrame,
    qnn: pd.DataFrame,
    common: pd.DataFrame,
    detailed: pd.DataFrame,
    qnn_sensitivity: pd.DataFrame,
) -> str:
    pca_actual = pca[pca["variant_kind"] == "pca_matched_control"].sort_values(
        "pooled_oof_pr_auc", ascending=False
    )
    classical_actual = classical[classical["variant_kind"] != "frozen_reference"].sort_values(
        "pooled_oof_pr_auc", ascending=False
    )
    qnn_actual = qnn[qnn["variant_kind"] == "qnn_structural"].sort_values(
        "pooled_oof_pr_auc", ascending=False
    )
    xgb_top = common[common["family"] == "xgboost"].nsmallest(5, "rank_within_family")
    qnn_top = common[common["family"] == "qnn"].nsmallest(5, "rank_within_family")
    qnn_pc = qnn_sensitivity.nsmallest(1, "sensitivity_rank").iloc[0]
    lines = [
        "# Secondary development — raport wyników do pracy magisterskiej",
        "",
        "Raport jest wyłącznie opisową analizą zamrożonych wyników OOF 2015–2020. "
        "Nie uruchamia modeli, nie otwiera lat 2021–2024 i nie zmienia rankingu głównego.",
        "",
        "## Kompletność",
        "",
        "Wszystkie **96/96** prerejestrowanych zadań zakończyły się statusem "
        "`COMPLETE`: 12 PCA-matched controls, 12 zadań interpretowalności, "
        "48 klasycznych fitów robustness i 24 fitów strukturalnych QNN.",
        "",
        "## PCA-matched controls",
        "",
    ]
    for _, row in pca_actual.iterrows():
        lines.append(
            f"- **{row['display_label']}**: PR-AUC **{_format(row['pooled_oof_pr_auc'])}**, "
            f"ROC-AUC **{_format(row['pooled_oof_roc_auc'])}**."
        )
    lines.extend(
        [
            "",
            "Zamrożona trzyseedowa referencja QNN L+D+R ma PR-AUC "
            f"**{_format(pca.iloc[0]['pooled_oof_pr_auc'])}**. Kontrole są jednoseedowe; "
            "różnice są opisowe i nie stanowią bezpośredniego testu seed-matched.",
            "",
            "## Robustness XGBoost",
            "",
            f"Najwyższy opisowy PR-AUC uzyskał wariant **{classical_actual.iloc[0]['display_label']}** "
            f"({_format(classical_actual.iloc[0]['pooled_oof_pr_auc'])}), a najniższy "
            f"**{classical_actual.iloc[-1]['display_label']}** "
            f"({_format(classical_actual.iloc[-1]['pooled_oof_pr_auc'])}).",
            "",
            "Warianty definicji targetu zmieniają etykietę i częstość klasy dodatniej, "
            "dlatego ich PR-AUC nie jest bezpośrednio porównywalne z bazowym targetem. "
            "Żaden wariant nie aktywuje reselekcji.",
            "",
            "## Robustness strukturalna QNN",
            "",
        ]
    )
    for _, row in qnn_actual.iterrows():
        lines.append(
            f"- **{row['display_label']}**: PR-AUC **{_format(row['pooled_oof_pr_auc'])}**, "
            f"ROC-AUC **{_format(row['pooled_oof_roc_auc'])}**."
        )
    lines.extend(
        [
            "",
            "Wyniki pochodzą z symulatora analitycznego i nie wspierają twierdzenia "
            "o przewadze kwantowej.",
            "",
            "## Interpretowalność",
            "",
            "Najwyżej sklasyfikowane cechy wspólnej permutation importance:",
            "",
            "- XGBoost: " + ", ".join(xgb_top["feature_name"].astype(str)) + ".",
            "- QNN: " + ", ".join(qnn_top["feature_name"].astype(str)) + ".",
            "",
            "Najważniejsze cechy według metod szczegółowych:",
            "",
            "- Elastic Net: "
            + _top_features(detailed, "Elastic Net standardized coefficient")
            + ".",
            "- XGBoost TreeSHAP: "
            + _top_features(detailed, "XGBoost interventional TreeSHAP")
            + ".",
            "- MLP Integrated Gradients: "
            + _top_features(detailed, "MLP Integrated Gradients")
            + ".",
            "",
            f"Najwyższą średnią czułość QNN ma **{qnn_pc['component']}** "
            f"({_format(qnn_pc['mean_abs_encoded_sensitivity_across_folds'])}). "
            "Czułość komponentu nie jest bezpośrednią atrybucją ekonomiczną cechy; "
            "interpretację należy łączyć z tabelą loadings PCA.",
            "",
            "## Granice wnioskowania",
            "",
            "- Wyniki są development-only i nie są niezależnym testem temporalnym.",
            "- Delt jednoseedowych wariantów względem trzyseedowych referencji nie należy "
            "interpretować jako testów istotności.",
            "- Secondary results nie zmieniają modelu głównego, ansatzu, parametrów, "
            "preprocessingu, kalibracji ani progów.",
            "- Lata 2021–2024 pozostają zamknięte.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_manifest(
    output_dir: Path,
    config: Mapping[str, Any],
    package: Mapping[str, Any],
    tables: Mapping[str, pd.DataFrame],
    figures: Sequence[Path],
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
        files.append(
            {
                "path": str(path.relative_to(output_dir)),
                "bytes": int(path.stat().st_size),
                "sha256": file_sha256(path),
            }
        )
    source_report = _load_json(REPORT_ROOT / "secondary_development_report.json")
    manifest = {
        "schema_version": 1,
        "id": "secondary_development_thesis_report_v1_0_0",
        "status": "COMPLETE",
        "source_execution_id": "secondary_development_execution_v1_1_6",
        "source_report_id": "secondary_development_execution_v1_1_7",
        "source_git_commit": _git("rev-parse", "HEAD"),
        "reporting_package_git_index_sha256": package["package_git_index_sha256"],
        "source_task_result_inventory_sha256": source_report[
            "source_task_result_inventory_sha256"
        ],
        "source_authority": config["source_authority"],
        "task_results": 96,
        "prediction_artifacts_read": 84,
        "generated_tables": [f"tables/{name}.csv" for name in tables],
        "generated_figures": [str(path.relative_to(output_dir)) for path in figures],
        "generated_files": files,
        "generated_files_sha256": canonical_sha256(files),
        "descriptive_deltas_only": True,
        "primary_selection_changed": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }
    (output_dir / "analysis_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def generate_report(
    config_path: Path = DEFAULT_CONFIG,
    output_dir: Path = DEFAULT_OUTPUT,
    *,
    require_committed: bool = False,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    output_dir = output_dir.resolve()
    _require(output_dir.is_relative_to(ROOT), "Report output escapes repository.")
    _require(not output_dir.exists(), f"Report output already exists: {output_dir}")
    package = verify_reporting_package(
        config_path, require_committed=require_committed
    )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    tasks = _load_tasks()
    pca, classical, qnn, fold_metrics = _build_variant_tables(tasks, config)
    common = _build_common_permutation(tasks)
    common_top = common[common["rank_within_family"] <= 5].copy()
    detailed, qnn_sensitivity, qnn_loadings = _build_detailed_interpretability(tasks)
    completeness = _phase_completeness()
    _require(
        completeness["complete_tasks"].sum() == 96
        and completeness["failed_tasks"].sum() == 0,
        "Phase completeness changed.",
    )
    tables = {
        "01_execution_completeness": completeness,
        "02_pca_matched_controls": pca,
        "03_xgboost_robustness": classical,
        "04_qnn_structural_robustness": qnn,
        "05_variant_fold_metrics": fold_metrics.sort_values(
            ["variant_kind", "analysis_id", "fold_id"]
        ),
        "06_common_permutation_importance": common,
        "07_common_permutation_top5_by_family": common_top,
        "08_detailed_feature_importance": detailed,
        "09_qnn_encoded_sensitivity": qnn_sensitivity,
        "10_qnn_pca_loadings": qnn_loadings,
    }

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".secondary_thesis_v1_0_0.", dir=output_dir.parent
    ) as staging_raw:
        staging = Path(staging_raw)
        table_dir = staging / "tables"
        for name, frame in tables.items():
            _write_csv(table_dir / f"{name}.csv", frame)
        figures = _build_figures(
            staging / "figures", pca, classical, qnn, common, detailed, qnn_sensitivity
        )
        summary = _build_summary(pca, classical, qnn, common, detailed, qnn_sensitivity)
        (staging / "summary.md").write_text(summary, encoding="utf-8")
        manifest = _write_manifest(staging, config, package, tables, figures)
        os.replace(staging, output_dir)

    return {
        "schema_version": 1,
        "status": manifest["status"],
        "output_dir": str(output_dir.relative_to(ROOT)),
        "tables": len(tables),
        "figure_files": len(figures),
        "generated_files": len(manifest["generated_files"]) + 1,
        "task_results": 96,
        "prediction_artifacts_read": 84,
        "primary_selection_changed": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-committed", action="store_true")
    parser.add_argument("--verify-package", action="store_true")
    args = parser.parse_args()
    if args.verify_package:
        result = verify_reporting_package(
            args.config, require_committed=args.require_committed
        )
    else:
        result = generate_report(
            args.config,
            args.output_dir,
            require_committed=args.require_committed,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

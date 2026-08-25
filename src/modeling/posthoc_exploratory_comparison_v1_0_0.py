"""Development-only post-hoc paired comparisons from frozen OOF predictions.

This module performs no model fitting, prediction generation, thresholding,
calibration, selection or protected-period access. It reads only the exact
development OOF and compact reporting artifacts listed in the versioned config.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import ticker as mticker
import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score
import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/posthoc_exploratory_comparison_v1_0_0.yaml"
DEFAULT_REPORT_DIR = ROOT / "reports/posthoc_exploratory_comparison_v1_0_0"
EXPECTED_YEARS = {2015, 2016, 2017, 2018, 2019, 2020}
KEY_FIELDS = ("validation_feature_year", "research_universe_company_year_id")
ALIGNMENT_FIELDS = (
    "validation_feature_year",
    "research_universe_company_year_id",
    "fold_id",
    "target_label",
    "economic_group_id",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    resolved = path.resolve() if path.is_absolute() else (ROOT / path).resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Source escapes project root: {raw}") from exc
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


class SourceTracker:
    def __init__(self) -> None:
        self._roles: dict[Path, set[str]] = {}

    def record(self, path: Path, role: str) -> None:
        path = path.resolve()
        self._roles.setdefault(path, set()).add(role)

    def read_json(self, raw: str | Path, role: str) -> Any:
        path = _resolve(raw)
        self.record(path, role)
        return json.loads(path.read_text(encoding="utf-8"))

    def read_csv(self, raw: str | Path, role: str) -> list[dict[str, str]]:
        path = _resolve(raw)
        self.record(path, role)
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def read_yaml(self, raw: str | Path, role: str) -> dict[str, Any]:
        path = _resolve(raw)
        self.record(path, role)
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise RuntimeError(f"Expected YAML mapping: {path}")
        return value

    def provenance_rows(self) -> list[dict[str, Any]]:
        rows = []
        for path in sorted(self._roles, key=lambda item: _relative(item).encode("utf-8")):
            rows.append(
                {
                    "source_path": _relative(path),
                    "source_role": ";".join(sorted(self._roles[path])),
                    "sha256": file_sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        return rows


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _canonical_key(row: Mapping[str, Any]) -> tuple[int, str]:
    return int(row[KEY_FIELDS[0]]), str(row[KEY_FIELDS[1]])


def _ordered_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    ordered = [dict(row) for row in rows]
    ordered.sort(
        key=lambda row: (
            _canonical_key(row)[0],
            _canonical_key(row)[1].encode("utf-8"),
        )
    )
    keys = [_canonical_key(row) for row in ordered]
    if len(keys) != len(set(keys)):
        raise RuntimeError("Duplicate canonical OOF key")
    return ordered


def _validate_development_rows(
    rows: Sequence[Mapping[str, Any]], *, expected_rows: int, expected_positive_n: int
) -> None:
    if len(rows) != expected_rows:
        raise RuntimeError(f"Unexpected OOF row count: {len(rows)} != {expected_rows}")
    years = {int(row["validation_feature_year"]) for row in rows}
    if years != EXPECTED_YEARS:
        raise RuntimeError(f"Forbidden or missing validation years: {sorted(years)}")
    positive_n = sum(int(row["target_label"]) for row in rows)
    if positive_n != expected_positive_n:
        raise RuntimeError(
            f"Unexpected positive count: {positive_n} != {expected_positive_n}"
        )
    for row in rows:
        score = float(row["raw_score"])
        if not math.isfinite(score):
            raise RuntimeError("Non-finite raw score")
        if int(row["target_label"]) not in {0, 1}:
            raise RuntimeError("Non-binary target label")
        if not str(row["economic_group_id"]):
            raise RuntimeError("Missing economic_group_id")


def _align_to_base(
    base_rows: Sequence[Mapping[str, Any]], other_rows: Sequence[Mapping[str, Any]]
) -> np.ndarray:
    other_by_key = {_canonical_key(row): row for row in other_rows}
    base_keys = {_canonical_key(row) for row in base_rows}
    if set(other_by_key) != base_keys:
        raise RuntimeError("OOF key sets differ")
    scores: list[float] = []
    for base in base_rows:
        other = other_by_key[_canonical_key(base)]
        for field in ALIGNMENT_FIELDS:
            if str(other[field]) != str(base[field]):
                raise RuntimeError(f"OOF alignment mismatch for {field}")
        scores.append(float(other["raw_score"]))
    return np.asarray(scores, dtype=np.float64)


def _metric_pair(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    if set(np.unique(labels).tolist()) != {0, 1}:
        raise ValueError("Degenerate labels")
    return (
        float(average_precision_score(labels, scores)),
        float(roc_auc_score(labels, scores)),
    )


def _interval(values: Sequence[float]) -> tuple[float, float, float]:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0:
        raise RuntimeError("Cannot calculate interval from zero values")
    lower, median, upper = np.percentile(
        array, [2.5, 50.0, 97.5], method="linear"
    )
    return float(lower), float(median), float(upper)


def _zero_relation(lower: float, upper: float) -> str:
    if lower > 0.0:
        return "ENTIRELY_ABOVE_ZERO"
    if upper < 0.0:
        return "ENTIRELY_BELOW_ZERO"
    return "INCLUDES_ZERO"


def _load_seed_averaged_tree_models(
    config: Mapping[str, Any], tracker: SourceTracker
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    identities: dict[str, dict[str, Any]] = {}
    model_rows: dict[str, list[dict[str, Any]]] = {}
    sources = config["sources"]["tree_seed_averaged_oof"]
    expected_ids = {
        "xgboost": "model_stage_v1__coarse__xgboost__004",
        "hist_gradient_boosting": "model_stage_v1__coarse__hist_gradient_boosting__007",
        "random_forest": "model_stage_v1__coarse__random_forest__003",
    }
    for family, expected_configuration_id in expected_ids.items():
        payload = tracker.read_json(sources[family], f"tree_oof::{family}")
        identity = dict(payload.get("identity") or {})
        if identity != {
            "configuration_id": expected_configuration_id,
            "family": family,
            "feature_block": "L+D+R",
        }:
            raise RuntimeError(f"Unexpected seed-averaged identity for {family}")
        if payload.get("seed_order") != [20260818, 20260819, 20260820]:
            raise RuntimeError(f"Unexpected seed order for {family}")
        rows = _ordered_rows(payload.get("rows") or [])
        identities[family] = {
            **identity,
            "training_seed": "AVERAGED_20260818_20260819_20260820",
            "representation": "standard_family_pipeline",
        }
        model_rows[family] = rows
    return identities, model_rows


def _load_qnn_seed(
    config: Mapping[str, Any], tracker: SourceTracker
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    source = config["sources"]["qnn_seed_20260818"]
    candidate = tracker.read_json(
        source["q2_candidate_manifest"], "qnn_seed_20260818_candidate"
    )
    candidate_row = dict(candidate.get("candidate") or {})
    expected = {
        "family": "qnn",
        "stage": "qnn_q2",
        "feature_block": "L+D+R",
        "configuration_id": "model_stage_v1__qnn_q2__t0",
        "training_seed": 20260818,
        "status": "COMPLETE",
        "selected_ansatz_id": "ROT_CNOT_RING",
    }
    for field, value in expected.items():
        if candidate_row.get(field) != value:
            raise RuntimeError(f"Unexpected QNN candidate {field}")

    expected_fold_hashes = {
        str(row["identity"]["fold_id"]): str(row["oof_prediction_artifact_sha256"])
        for row in candidate.get("fold_manifests") or []
    }
    rows: list[dict[str, Any]] = []
    for raw_path in source["q2_prediction_files"]:
        path = _resolve(raw_path)
        fold_id = path.parent.name
        if fold_id not in expected_fold_hashes:
            raise RuntimeError(f"Unexpected QNN fold file: {fold_id}")
        if file_sha256(path) != expected_fold_hashes[fold_id]:
            raise RuntimeError(f"QNN fold prediction hash mismatch: {fold_id}")
        payload = tracker.read_json(path, f"qnn_seed_20260818_oof::{fold_id}")
        fold_rows = payload.get("rows") or []
        if any(str(row.get("fold_id")) != fold_id for row in fold_rows):
            raise RuntimeError(f"QNN fold label mismatch: {fold_id}")
        rows.extend(dict(row) for row in fold_rows)

    identities: dict[str, dict[str, Any]] = {}
    for raw_path in source["q1_identity_manifests"]:
        payload = tracker.read_json(raw_path, "qnn_q1_identity_manifest")
        task = dict(payload.get("task_identity") or {})
        fold_id = str(task.get("fold_id"))
        if task.get("training_seed") != 20260818 or task.get("feature_block") != "L+D+R":
            raise RuntimeError(f"Unexpected QNN identity for {fold_id}")
        if task.get("selected_ansatz_id") != "ROT_CNOT_RING":
            raise RuntimeError(f"Unexpected QNN ansatz for {fold_id}")
        identities[fold_id] = task
    if set(identities) != {f"fold_{year}" for year in sorted(EXPECTED_YEARS)}:
        raise RuntimeError("Incomplete QNN identity manifests")

    return (
        {
            "family": "qnn",
            "stage": "qnn_q2",
            "feature_block": "L+D+R",
            "configuration_id": "model_stage_v1__qnn_q2__t0",
            "training_seed": 20260818,
            "representation": "fold_fitted_qnn_pca_4_components",
            "selected_ansatz_id": "ROT_CNOT_RING",
        },
        _ordered_rows(rows),
        identities,
    )


def _load_pca_controls(
    config: Mapping[str, Any], tracker: SourceTracker
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, dict[str, dict[str, Any]]],
]:
    source = config["sources"]["pca_matched_controls"]
    phase = tracker.read_json(source["phase_manifest"], "pca_controls_phase_manifest")
    if phase.get("status") != "COMPLETE" or phase.get("protected_feature_years_opened") is not False:
        raise RuntimeError("PCA-matched phase is not a safe COMPLETE development artifact")
    references = list(phase.get("task_result_references") or [])
    allowed = list(source["allowed_task_result_references"])
    if references != allowed or len(references) != 12:
        raise RuntimeError("PCA-matched task references differ from exact allowlist")

    execution_root = (ROOT / source["execution_root"]).resolve()
    rows_by_analysis: dict[str, list[dict[str, Any]]] = {
        "fixed_l2_logistic_same_qnn_representation": [],
        "pytorch_mlp_same_qnn_representation": [],
    }
    identity_by_analysis: dict[str, dict[str, dict[str, Any]]] = {
        key: {} for key in rows_by_analysis
    }
    for reference in references:
        task_path = execution_root / reference
        task = tracker.read_json(task_path, "pca_control_task_result")
        if task.get("status") != "COMPLETE" or task.get("protected_feature_years_opened") is not False:
            raise RuntimeError(f"Unsafe PCA control task: {reference}")
        task_identity = dict(task.get("task_identity") or {})
        analysis_id = str(task_identity.get("analysis_id"))
        if analysis_id not in rows_by_analysis:
            raise RuntimeError(f"Unexpected PCA control analysis: {analysis_id}")
        if task_identity.get("training_seed") != 20260818:
            raise RuntimeError("PCA control is not seed-matched")
        fold_id = str(task_identity.get("fold_id"))
        artifact_path = execution_root / str(task["prediction_artifact"])
        if file_sha256(artifact_path) != str(task["prediction_artifact_sha256"]):
            raise RuntimeError(f"PCA control prediction hash mismatch: {reference}")
        artifact = tracker.read_json(
            artifact_path, f"pca_control_oof::{analysis_id}::{fold_id}"
        )
        fold_rows = artifact.get("rows") or []
        if any(str(row.get("fold_id")) != fold_id for row in fold_rows):
            raise RuntimeError(f"PCA control fold mismatch: {reference}")
        rows_by_analysis[analysis_id].extend(dict(row) for row in fold_rows)
        identity_by_analysis[analysis_id][fold_id] = dict(
            task.get("execution_identity") or {}
        )

    model_identity = {
        "fixed_l2_logistic_same_qnn_representation": {
            "family": "fixed_l2_logistic",
            "stage": "secondary::pca_matched_controls",
            "feature_block": "L+D+R",
            "configuration_id": "model_stage_v1__coarse__fixed_l2_logistic__002",
            "training_seed": 20260818,
            "representation": "same_fold_fitted_qnn_pca_4_components",
        },
        "pytorch_mlp_same_qnn_representation": {
            "family": "pytorch_mlp",
            "stage": "secondary::pca_matched_controls",
            "feature_block": "L+D+R",
            "configuration_id": "model_stage_v1__coarse__pytorch_mlp__epochs_200__003",
            "training_seed": 20260818,
            "representation": "same_fold_fitted_qnn_pca_4_components",
        },
    }
    return (
        model_identity,
        {key: _ordered_rows(value) for key, value in rows_by_analysis.items()},
        identity_by_analysis,
    )


def _validate_qnn_control_identity(
    qnn_by_fold: Mapping[str, Mapping[str, Any]],
    control_by_fold: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    folds = {f"fold_{year}" for year in sorted(EXPECTED_YEARS)}
    if set(qnn_by_fold) != folds or set(control_by_fold) != folds:
        raise RuntimeError("Incomplete fold identities for seed-matched comparison")
    fields = {
        "training_seed_same": "training_seed",
        "feature_block_same": "feature_block",
        "pca_sha256_same": "pca_sha256_if_applicable",
        "preprocessing_sha256_same": "preprocessing_sha256",
        "train_membership_sha256_same": "train_membership_sha256",
        "validation_membership_sha256_same": "validation_membership_sha256",
        "software_environment_sha256_same": "software_environment_sha256",
    }
    result: dict[str, Any] = {}
    for output_name, field in fields.items():
        values = []
        for fold_id in sorted(folds):
            qnn_identity = dict(qnn_by_fold[fold_id])
            control_identity = dict(control_by_fold[fold_id])
            qnn_checkpoint = dict(qnn_identity.get("checkpoint_identity") or {})
            control_checkpoint = dict(control_identity.get("checkpoint_identity") or {})
            qnn_value = qnn_identity.get(field, qnn_checkpoint.get(field))
            control_value = control_identity.get(field, control_checkpoint.get(field))
            values.append(qnn_value == control_value)
        result[output_name] = all(values)
    return result


def _bootstrap(
    *,
    labels: np.ndarray,
    groups: np.ndarray,
    scores: Mapping[str, np.ndarray],
    comparisons: Sequence[Mapping[str, str]],
    replicates: int,
    seed: int,
    minimum_valid: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, tuple[float, float]]]:
    point_metrics = {name: _metric_pair(labels, values) for name, values in scores.items()}
    ordered_groups = sorted(set(groups.tolist()), key=lambda value: str(value).encode("utf-8"))
    group_indices = {
        group: np.flatnonzero(groups == group).astype(np.int64)
        for group in ordered_groups
    }
    if len(ordered_groups) < 2:
        raise RuntimeError("Too few economic groups")

    draw_values: dict[str, dict[str, list[float]]] = {
        str(comp["comparison_id"]): {
            "delta_ap": [],
            "delta_roc": [],
        }
        for comp in comparisons
    }
    replicate_rows: list[dict[str, Any]] = []
    invalid = 0
    rng = np.random.default_rng(seed)
    group_count = len(ordered_groups)
    for replicate in range(1, replicates + 1):
        sampled_positions = rng.integers(0, group_count, size=group_count)
        sampled_indices = np.concatenate(
            [group_indices[ordered_groups[int(position)]] for position in sampled_positions]
        )
        sampled_labels = labels[sampled_indices]
        if set(np.unique(sampled_labels).tolist()) != {0, 1}:
            invalid += 1
            for comparison in comparisons:
                replicate_rows.append(
                    {
                        "comparison_id": comparison["comparison_id"],
                        "replicate": replicate,
                        "status": "DEGENERATE_LABELS",
                    }
                )
            continue
        sampled_metrics = {
            name: _metric_pair(sampled_labels, values[sampled_indices])
            for name, values in scores.items()
        }
        for comparison in comparisons:
            model_a = comparison["model_a"]
            model_b = comparison["model_b"]
            ap_a, roc_a = sampled_metrics[model_a]
            ap_b, roc_b = sampled_metrics[model_b]
            delta_ap = ap_a - ap_b
            delta_roc = roc_a - roc_b
            draw_values[comparison["comparison_id"]]["delta_ap"].append(delta_ap)
            draw_values[comparison["comparison_id"]]["delta_roc"].append(delta_roc)
            replicate_rows.append(
                {
                    "comparison_id": comparison["comparison_id"],
                    "replicate": replicate,
                    "status": "VALID",
                    "model_a_ap": ap_a,
                    "model_b_ap": ap_b,
                    "delta_ap_a_minus_b": delta_ap,
                    "model_a_roc_auc": roc_a,
                    "model_b_roc_auc": roc_b,
                    "delta_roc_auc_a_minus_b": delta_roc,
                }
            )

    valid = replicates - invalid
    if valid < minimum_valid:
        raise RuntimeError(f"Too few valid bootstrap replicates: {valid}/{replicates}")

    summary_rows: list[dict[str, Any]] = []
    for comparison in comparisons:
        comparison_id = str(comparison["comparison_id"])
        model_a = str(comparison["model_a"])
        model_b = str(comparison["model_b"])
        ap_a, roc_a = point_metrics[model_a]
        ap_b, roc_b = point_metrics[model_b]
        ap_lower, ap_median, ap_upper = _interval(
            draw_values[comparison_id]["delta_ap"]
        )
        roc_lower, roc_median, roc_upper = _interval(
            draw_values[comparison_id]["delta_roc"]
        )
        summary_rows.append(
            {
                **comparison,
                "point_ap_model_a": ap_a,
                "point_ap_model_b": ap_b,
                "point_delta_ap_a_minus_b": ap_a - ap_b,
                "delta_ap_ci_lower": ap_lower,
                "delta_ap_ci_median": ap_median,
                "delta_ap_ci_upper": ap_upper,
                "delta_ap_ci_zero_relation": _zero_relation(ap_lower, ap_upper),
                "point_roc_auc_model_a": roc_a,
                "point_roc_auc_model_b": roc_b,
                "point_delta_roc_auc_a_minus_b": roc_a - roc_b,
                "delta_roc_auc_ci_lower": roc_lower,
                "delta_roc_auc_ci_median": roc_median,
                "delta_roc_auc_ci_upper": roc_upper,
                "delta_roc_auc_ci_zero_relation": _zero_relation(
                    roc_lower, roc_upper
                ),
                "bootstrap_replicates_requested": replicates,
                "bootstrap_replicates_valid": valid,
                "bootstrap_replicates_invalid": invalid,
                "interval_method": "paired_cluster_percentile_95_linear",
                "selection_adjusted": False,
                "analysis_role": "POST_HOC_EXPLORATORY_CONDITIONAL_ON_SELECTION",
            }
        )
    return summary_rows, replicate_rows, point_metrics


SUMMARY_FIELDS = (
    "comparison_id",
    "display_label",
    "comparison_group",
    "model_a",
    "model_a_label",
    "model_a_seed",
    "model_b",
    "model_b_label",
    "model_b_seed",
    "feature_block",
    "representation",
    "request_mapping",
    "rows",
    "positive_n",
    "economic_group_count",
    "point_ap_model_a",
    "point_ap_model_b",
    "point_delta_ap_a_minus_b",
    "delta_ap_ci_lower",
    "delta_ap_ci_median",
    "delta_ap_ci_upper",
    "delta_ap_ci_zero_relation",
    "point_roc_auc_model_a",
    "point_roc_auc_model_b",
    "point_delta_roc_auc_a_minus_b",
    "delta_roc_auc_ci_lower",
    "delta_roc_auc_ci_median",
    "delta_roc_auc_ci_upper",
    "delta_roc_auc_ci_zero_relation",
    "bootstrap_replicates_requested",
    "bootstrap_replicates_valid",
    "bootstrap_replicates_invalid",
    "interval_method",
    "selection_adjusted",
    "analysis_role",
)


def _comparison_specs(config: Mapping[str, Any]) -> list[dict[str, str]]:
    labels = {
        "xgboost": "XGBoost — średnia 3 seedów",
        "hist_gradient_boosting": "HistGradientBoosting — średnia 3 seedów",
        "random_forest": "Random Forest — średnia 3 seedów",
        "qnn_seed_20260818": "QNN — seed 20260818",
        "pca_matched_mlp_seed_20260818": "PCA-matched MLP — seed 20260818",
        "pca_matched_fixed_l2_logistic_seed_20260818": (
            "PCA-matched fixed-L2 logistic — seed 20260818"
        ),
    }
    rows: list[dict[str, str]] = []
    for group_name, raw_rows in config["comparisons"].items():
        for raw in raw_rows:
            model_a = str(raw["model_a"])
            model_b = str(raw["model_b"])
            rows.append(
                {
                    "comparison_id": str(raw["id"]),
                    "comparison_group": str(group_name),
                    "model_a": model_a,
                    "model_a_label": labels[model_a],
                    "model_a_seed": (
                        "AVERAGED_20260818_20260819_20260820"
                        if group_name == "tree_models"
                        else "20260818"
                    ),
                    "model_b": model_b,
                    "model_b_label": labels[model_b],
                    "model_b_seed": (
                        "AVERAGED_20260818_20260819_20260820"
                        if group_name == "tree_models"
                        else "20260818"
                    ),
                    "feature_block": "L+D+R",
                    "representation": (
                        "standard_family_pipelines_same_oof_membership"
                        if group_name == "tree_models"
                        else "same_fold_fitted_qnn_pca_4_components"
                    ),
                    "request_mapping": str(
                        raw.get("request_mapping", "EXACT_REQUESTED_COMPARISON")
                    ),
                }
            )
    return rows


def _plot_forest(
    rows: Sequence[Mapping[str, Any]], *, output_base: Path, title: str
) -> None:
    short_labels = {
        "XGBoost − HistGradientBoosting": "XGBoost − HistGB",
        "XGBoost − Random Forest": "XGBoost − RF",
        "QNN − PCA-matched MLP": "QNN − PCA MLP",
        "QNN − PCA-matched fixed-L2 logistic": "QNN − PCA fixed-L2 logistic",
    }
    labels = [short_labels[str(row["display_label"])] for row in rows]
    y = np.arange(len(rows), dtype=float)
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.2))
    fig.subplots_adjust(left=0.20, right=0.98, top=0.82, bottom=0.25, wspace=0.62)
    specs = (
        (
            axes[0],
            "point_delta_ap_a_minus_b",
            "delta_ap_ci_lower",
            "delta_ap_ci_upper",
            "Różnica AP (model A − model B)",
        ),
        (
            axes[1],
            "point_delta_roc_auc_a_minus_b",
            "delta_roc_auc_ci_lower",
            "delta_roc_auc_ci_upper",
            "Różnica ROC-AUC (model A − model B)",
        ),
    )
    for axis, point_field, lower_field, upper_field, xlabel in specs:
        points = np.asarray([float(row[point_field]) for row in rows])
        lower = np.asarray([float(row[lower_field]) for row in rows])
        upper = np.asarray([float(row[upper_field]) for row in rows])
        errors = np.vstack((points - lower, upper - points))
        axis.errorbar(
            points,
            y,
            xerr=errors,
            fmt="o",
            color="#1F4E78",
            ecolor="#5B9BD5",
            elinewidth=2.2,
            capsize=5,
            markersize=7,
            zorder=3,
        )
        axis.axvline(0.0, color="#A61C3C", linewidth=1.3, linestyle="--")
        axis.grid(axis="x", color="#D9E2F3", linewidth=0.8)
        axis.set_xlabel(xlabel, labelpad=9)
        axis.xaxis.set_major_locator(mticker.MaxNLocator(nbins=5))
        axis.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.3f"))
        axis.set_yticks(y)
        axis.set_yticklabels(labels)
        axis.invert_yaxis()
        axis.spines[["top", "right", "left"]].set_visible(False)
        axis.tick_params(axis="x", labelsize=9)
        axis.tick_params(axis="y", length=0)
        for position, point in enumerate(points):
            axis.annotate(
                f"{point:+.4f}",
                (point, position),
                xytext=(0, 10),
                textcoords="offset points",
                ha="center",
                fontsize=9,
                color="#17365D",
            )
    fig.suptitle(
        title, fontsize=13, fontweight="bold", color="#17365D", y=0.95
    )
    fig.text(
        0.5,
        0.045,
        "95% percentile CI; 2 000 wspólnych losowań economic_group_id.\n"
        "Post-hoc exploratory; CI warunkowe względem wcześniejszej selekcji.",
        ha="center",
        fontsize=9,
        color="#595959",
    )
    output_base.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output_base.with_suffix(".png"),
        dpi=180,
        bbox_inches="tight",
        metadata={"Software": "posthoc_exploratory_comparison_v1_0_0"},
    )
    matplotlib.rcParams["svg.hashsalt"] = "posthoc_exploratory_comparison_v1_0_0"
    fig.savefig(
        output_base.with_suffix(".svg"),
        bbox_inches="tight",
        metadata={"Date": None, "Creator": "posthoc_exploratory_comparison_v1_0_0"},
    )
    plt.close(fig)


def _build_qnn_variant_rows(
    source_rows: Sequence[Mapping[str, str]],
    *,
    qnn_seed_metrics: tuple[float, float],
) -> list[dict[str, Any]]:
    qnn_ap, qnn_roc = qnn_seed_metrics
    rows: list[dict[str, Any]] = []
    for source in source_rows:
        if source.get("variant_kind") != "qnn_structural":
            continue
        ap = float(source["pooled_oof_pr_auc"])
        roc = float(source["pooled_oof_roc_auc"])
        rows.append(
            {
                "analysis_id": source["analysis_id"],
                "display_label": source["display_label"],
                "training_seed": source["training_seed"],
                "pooled_oof_ap": ap,
                "pooled_oof_roc_auc": roc,
                "qnn_seed_20260818_ap": qnn_ap,
                "qnn_seed_20260818_roc_auc": qnn_roc,
                "descriptive_delta_ap_vs_qnn_seed_20260818": ap - qnn_ap,
                "descriptive_delta_roc_auc_vs_qnn_seed_20260818": roc - qnn_roc,
                "status": "EXISTING_PREDEFINED_VARIANT_NO_NEW_FIT",
                "inferential_role": "DESCRIPTIVE_ONLY_NO_NEW_BOOTSTRAP",
            }
        )
    return rows


def _build_seed_stability_rows(
    source_rows: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    selected = {"xgboost", "hist_gradient_boosting", "random_forest", "qnn"}
    fields = (
        "model_label",
        "family",
        "feature_block",
        "configuration_id",
        "seed_protocol",
        "seed_count",
        "pooled_oof_pr_auc_seed_mean",
        "pooled_oof_pr_auc_seed_sample_sd",
        "pooled_oof_pr_auc_seed_min",
        "pooled_oof_pr_auc_seed_max",
        "pooled_oof_pr_auc_score_averaged_ensemble",
        "pooled_oof_roc_auc_seed_mean",
        "pooled_oof_roc_auc_seed_sample_sd",
        "pooled_oof_roc_auc_seed_min",
        "pooled_oof_roc_auc_seed_max",
        "pooled_oof_roc_auc_score_averaged_ensemble",
    )
    rows = []
    for source in source_rows:
        if source.get("family") not in selected:
            continue
        row = {field: source.get(field) for field in fields}
        row["status"] = "DESCRIPTIVE_ONLY_N3_NOT_CONFIDENCE_INTERVAL"
        rows.append(row)
    return rows


def _disclosure_rows() -> list[dict[str, str]]:
    return [
        {
            "topic": "analysis_role",
            "disclosure": "Post-hoc exploratory development-only analysis; not preregistered confirmatory inference.",
        },
        {
            "topic": "selection_conditioning",
            "disclosure": "All paired CIs are conditional on previously selected configurations and are not selection-adjusted.",
        },
        {
            "topic": "multiplicity",
            "disclosure": "Intervals are pointwise 95% percentile intervals with no multiplicity adjustment.",
        },
        {
            "topic": "resampling",
            "disclosure": "economic_group_id clusters are sampled with replacement; each replicate uses identical cluster draws for every model.",
        },
        {
            "topic": "metrics",
            "disclosure": "AP means average precision; ROC-AUC is secondary. Delta direction is model A minus model B.",
        },
        {
            "topic": "fixed_l2_request",
            "disclosure": "No fixed-L2 MLP artifact exists. The only existing fixed-L2 PCA-matched control is logistic regression; no new model was fitted.",
        },
        {
            "topic": "qnn_variants",
            "disclosure": "Existing pre-defined QNN variants are shown descriptively without new tuning, reranking or inferential claims.",
        },
        {
            "topic": "seed_stability",
            "disclosure": "Seed mean, sample SD and range are descriptive statistics from exactly three existing seeds, not confidence intervals.",
        },
        {
            "topic": "protected_boundary",
            "disclosure": "Only OOF validation years 2015-2020 are read. No 2021-2024 row, prediction, feature, target, holdout or test artifact is opened.",
        },
        {
            "topic": "experiment_boundary",
            "disclosure": "No model fit, refit, prediction generation, new seed, tuning, ensemble, split change, calibration or threshold change is performed.",
        },
    ]


def _summary_markdown(
    tree_rows: Sequence[Mapping[str, Any]],
    qnn_rows: Sequence[Mapping[str, Any]],
) -> str:
    def table(rows: Sequence[Mapping[str, Any]]) -> str:
        lines = [
            "| Porównanie (A − B) | ΔAP | 95% CI | ΔROC-AUC | 95% CI |",
            "|---|---:|---:|---:|---:|",
        ]
        for row in rows:
            lines.append(
                "| {label} | {dap:.6f} | [{alo:.6f}; {ahi:.6f}] | "
                "{droc:.6f} | [{rlo:.6f}; {rhi:.6f}] |".format(
                    label=row["display_label"],
                    dap=float(row["point_delta_ap_a_minus_b"]),
                    alo=float(row["delta_ap_ci_lower"]),
                    ahi=float(row["delta_ap_ci_upper"]),
                    droc=float(row["point_delta_roc_auc_a_minus_b"]),
                    rlo=float(row["delta_roc_auc_ci_lower"]),
                    rhi=float(row["delta_roc_auc_ci_upper"]),
                )
            )
        return "\n".join(lines)

    return (
        "# Post-hoc exploratory comparisons v1.0.0\n\n"
        "Status: **COMPLETE — DEVELOPMENT ONLY**\n\n"
        "Pakiet jest technicznym zestawieniem dowodów, nie tekstem pracy ani "
        "analizą confirmatory. Wszystkie CI są warunkowe względem wcześniejszej "
        "selekcji konfiguracji, bez korekty selekcji i wielokrotności.\n\n"
        "## Sparowane porównania modeli drzewiastych\n\n"
        + table(tree_rows)
        + "\n\n## Seed-matched QNN i kontrole PCA\n\n"
        + table(qnn_rows)
        + "\n\nKontrola określona w prośbie jako fixed-L2 MLP nie istnieje w artefaktach. "
        "Wykorzystano istniejącą PCA-matched regresję logistyczną fixed-L2; nie "
        "wykonano nowego fitu.\n\n"
        "## Granice\n\n"
        "- wyłącznie OOF 2015–2020;\n"
        "- 2 000 sparowanych losowań klastrów `economic_group_id`;\n"
        "- AP = average precision;\n"
        "- brak p-value i brak formalnego twierdzenia o przewadze;\n"
        "- brak dostępu do danych chronionych i brak zmian głównego rankingu.\n"
    )


def generate_package(
    *, config_path: Path = DEFAULT_CONFIG, report_dir: Path = DEFAULT_REPORT_DIR
) -> dict[str, Any]:
    tracker = SourceTracker()
    config = tracker.read_yaml(config_path, "analysis_config")
    tracker.record(Path(__file__), "generator_source")
    analysis = config["analysis"]
    if analysis["status"] != "AUTHOR_AUTHORIZED_POST_HOC_EXPLORATORY":
        raise RuntimeError("Unexpected analysis authorization status")
    forbidden_flags = (
        "project_model_fit_permitted",
        "prediction_generation_permitted",
        "hyperparameter_search_permitted",
        "additional_seeds_permitted",
        "protected_or_holdout_content_permitted",
    )
    if any(bool(analysis[field]) for field in forbidden_flags):
        raise RuntimeError("Config permits a forbidden operation")
    if set(analysis["development_feature_years"]) != EXPECTED_YEARS:
        raise RuntimeError("Unexpected development years")
    if set(analysis["forbidden_feature_years"]) != {2021, 2022, 2023, 2024}:
        raise RuntimeError("Unexpected protected-year boundary")

    policy = tracker.read_yaml(config["sources"]["bootstrap_policy"], "bootstrap_policy")
    frozen_policy = policy["post_coarse_execution"]["inference"]
    configured_bootstrap = config["bootstrap"]
    for field in (
        "resampling_unit",
        "paired_cluster_draws_across_models",
        "replicates",
        "minimum_valid_replicates",
        "seed",
        "selection_adjusted",
    ):
        if frozen_policy[field] != configured_bootstrap[field]:
            raise RuntimeError(f"Bootstrap policy mismatch for {field}")

    _tree_identity, rows_by_model = _load_seed_averaged_tree_models(config, tracker)
    _qnn_identity, qnn_rows, qnn_fold_identity = _load_qnn_seed(config, tracker)
    _control_identity, control_rows, control_fold_identity = _load_pca_controls(
        config, tracker
    )
    rows_by_model["qnn_seed_20260818"] = qnn_rows
    rows_by_model["pca_matched_mlp_seed_20260818"] = control_rows[
        "pytorch_mlp_same_qnn_representation"
    ]
    rows_by_model["pca_matched_fixed_l2_logistic_seed_20260818"] = control_rows[
        "fixed_l2_logistic_same_qnn_representation"
    ]

    expected_rows = int(analysis["expected_rows"])
    expected_positive_n = int(analysis["expected_positive_n"])
    for rows in rows_by_model.values():
        _validate_development_rows(
            rows,
            expected_rows=expected_rows,
            expected_positive_n=expected_positive_n,
        )

    base_rows = rows_by_model["xgboost"]
    labels = np.asarray([int(row["target_label"]) for row in base_rows], dtype=np.int64)
    groups = np.asarray([str(row["economic_group_id"]) for row in base_rows], dtype=object)
    scores = {
        name: _align_to_base(base_rows, rows) for name, rows in rows_by_model.items()
    }
    economic_group_count = int(len(np.unique(groups)))

    ranking_rows = tracker.read_csv(
        config["sources"]["final_development_ranking"], "final_development_ranking"
    )
    ranking = {row["family"]: row for row in ranking_rows}
    for family in ("xgboost", "hist_gradient_boosting", "random_forest"):
        point = _metric_pair(labels, scores[family])
        if not math.isclose(
            point[0], float(ranking[family]["pooled_oof_pr_auc"]), abs_tol=1e-12
        ) or not math.isclose(
            point[1], float(ranking[family]["pooled_oof_roc_auc"]), abs_tol=1e-12
        ):
            raise RuntimeError(f"Recomputed tree metric mismatch: {family}")

    pca_summary_rows = tracker.read_csv(
        config["sources"]["existing_pca_controls_summary"],
        "existing_pca_controls_summary",
    )
    pca_summary = {row["analysis_id"]: row for row in pca_summary_rows}
    pca_model_mapping = {
        "pca_matched_mlp_seed_20260818": "pytorch_mlp_same_qnn_representation",
        "pca_matched_fixed_l2_logistic_seed_20260818": (
            "fixed_l2_logistic_same_qnn_representation"
        ),
    }
    for model_name, analysis_id in pca_model_mapping.items():
        point = _metric_pair(labels, scores[model_name])
        source = pca_summary[analysis_id]
        if not math.isclose(
            point[0], float(source["pooled_oof_pr_auc"]), abs_tol=1e-12
        ) or not math.isclose(
            point[1], float(source["pooled_oof_roc_auc"]), abs_tol=1e-12
        ):
            raise RuntimeError(f"Recomputed PCA control metric mismatch: {model_name}")

    qnn_point = _metric_pair(labels, scores["qnn_seed_20260818"])
    qnn_candidate = tracker.read_json(
        config["sources"]["qnn_seed_20260818"]["q2_candidate_manifest"],
        "qnn_seed_20260818_candidate_validation",
    )["candidate"]
    if not math.isclose(
        qnn_point[0], float(qnn_candidate["pooled_oof_pr_auc"]), abs_tol=1e-12
    ):
        raise RuntimeError("Recomputed QNN AP mismatch")

    comparisons = _comparison_specs(config)
    bootstrap_rows, replicate_rows, point_metrics = _bootstrap(
        labels=labels,
        groups=groups,
        scores=scores,
        comparisons=comparisons,
        replicates=int(configured_bootstrap["replicates"]),
        seed=int(configured_bootstrap["seed"]),
        minimum_valid=int(configured_bootstrap["minimum_valid_replicates"]),
    )
    for row in bootstrap_rows:
        row["rows"] = expected_rows
        row["positive_n"] = expected_positive_n
        row["economic_group_count"] = economic_group_count
        row["display_label"] = (
            "XGBoost − HistGradientBoosting"
            if row["comparison_id"] == "xgboost_minus_hist_gradient_boosting"
            else "XGBoost − Random Forest"
            if row["comparison_id"] == "xgboost_minus_random_forest"
            else "QNN − PCA-matched MLP"
            if row["comparison_id"] == "qnn_minus_pca_matched_mlp"
            else "QNN − PCA-matched fixed-L2 logistic"
        )

    tree_results = [
        row for row in bootstrap_rows if row["comparison_group"] == "tree_models"
    ]
    qnn_results = [
        row
        for row in bootstrap_rows
        if row["comparison_group"] == "seed_matched_qnn_controls"
    ]

    alignment_rows: list[dict[str, Any]] = []
    for row in tree_results:
        alignment_rows.append(
            {
                "comparison_id": row["comparison_id"],
                "oof_key_set_same": True,
                "labels_groups_folds_years_same": True,
                "training_seed_protocol_same": True,
                "pca_sha256_same_all_folds": "NOT_APPLICABLE",
                "preprocessing_sha256_same_all_folds": "NOT_ASSERTED_FAMILY_SPECIFIC",
                "train_membership_sha256_same_all_folds": "NOT_ASSERTED_FROM_OOF_ONLY",
                "validation_membership_sha256_same_all_folds": "OOF_KEYS_AND_METADATA_MATCH",
                "software_environment_sha256_same_all_folds": "NOT_ASSERTED",
                "alignment_status": "PASS_PAIRED_OOF_ALIGNMENT",
            }
        )
    control_map = {
        "qnn_minus_pca_matched_mlp": "pytorch_mlp_same_qnn_representation",
        "qnn_minus_pca_matched_fixed_l2_logistic": (
            "fixed_l2_logistic_same_qnn_representation"
        ),
    }
    for row in qnn_results:
        identity_check = _validate_qnn_control_identity(
            qnn_fold_identity, control_fold_identity[control_map[row["comparison_id"]]]
        )
        required_same = (
            identity_check["training_seed_same"],
            identity_check["feature_block_same"],
            identity_check["pca_sha256_same"],
            identity_check["preprocessing_sha256_same"],
            identity_check["train_membership_sha256_same"],
            identity_check["validation_membership_sha256_same"],
        )
        if not all(required_same):
            raise RuntimeError(f"Seed-matched identity check failed: {row['comparison_id']}")
        alignment_rows.append(
            {
                "comparison_id": row["comparison_id"],
                "oof_key_set_same": True,
                "labels_groups_folds_years_same": True,
                "training_seed_protocol_same": identity_check["training_seed_same"],
                "pca_sha256_same_all_folds": identity_check["pca_sha256_same"],
                "preprocessing_sha256_same_all_folds": identity_check[
                    "preprocessing_sha256_same"
                ],
                "train_membership_sha256_same_all_folds": identity_check[
                    "train_membership_sha256_same"
                ],
                "validation_membership_sha256_same_all_folds": identity_check[
                    "validation_membership_sha256_same"
                ],
                "software_environment_sha256_same_all_folds": identity_check[
                    "software_environment_sha256_same"
                ],
                "alignment_status": "PASS_SEED_AND_PCA_MATCHED",
            }
        )

    variant_source = tracker.read_csv(
        config["sources"]["existing_qnn_variants"], "existing_qnn_variants"
    )
    variant_rows = _build_qnn_variant_rows(
        variant_source, qnn_seed_metrics=point_metrics["qnn_seed_20260818"]
    )
    seed_source = tracker.read_csv(
        config["sources"]["existing_seed_stability"], "existing_seed_stability"
    )
    seed_rows = _build_seed_stability_rows(seed_source)
    disclosure_rows = _disclosure_rows()

    if report_dir.exists():
        shutil.rmtree(report_dir)
    tables_dir = report_dir / "tables"
    figures_dir = report_dir / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    _write_csv(
        tables_dir / "01_paired_clustered_bootstrap_tree_models.csv",
        tree_results,
        SUMMARY_FIELDS,
    )
    _write_csv(
        tables_dir / "02_seed_matched_qnn_vs_pca_controls.csv",
        qnn_results,
        SUMMARY_FIELDS,
    )
    _write_csv(
        tables_dir / "03_existing_qnn_variants_descriptive.csv",
        variant_rows,
        (
            "analysis_id",
            "display_label",
            "training_seed",
            "pooled_oof_ap",
            "pooled_oof_roc_auc",
            "qnn_seed_20260818_ap",
            "qnn_seed_20260818_roc_auc",
            "descriptive_delta_ap_vs_qnn_seed_20260818",
            "descriptive_delta_roc_auc_vs_qnn_seed_20260818",
            "status",
            "inferential_role",
        ),
    )
    seed_fields = list(seed_rows[0].keys()) if seed_rows else []
    _write_csv(
        tables_dir / "04_existing_seed_stability.csv", seed_rows, seed_fields
    )
    _write_csv(
        tables_dir / "05_alignment_checks.csv",
        alignment_rows,
        (
            "comparison_id",
            "oof_key_set_same",
            "labels_groups_folds_years_same",
            "training_seed_protocol_same",
            "pca_sha256_same_all_folds",
            "preprocessing_sha256_same_all_folds",
            "train_membership_sha256_same_all_folds",
            "validation_membership_sha256_same_all_folds",
            "software_environment_sha256_same_all_folds",
            "alignment_status",
        ),
    )
    _write_csv(
        tables_dir / "06_methodological_disclosures.csv",
        disclosure_rows,
        ("topic", "disclosure"),
    )
    _write_csv(
        tables_dir / "07_source_provenance.csv",
        tracker.provenance_rows(),
        ("source_path", "source_role", "sha256", "size_bytes"),
    )
    _write_csv(
        tables_dir / "08_bootstrap_replicates.csv",
        replicate_rows,
        (
            "comparison_id",
            "replicate",
            "status",
            "model_a_ap",
            "model_b_ap",
            "delta_ap_a_minus_b",
            "model_a_roc_auc",
            "model_b_roc_auc",
            "delta_roc_auc_a_minus_b",
        ),
    )
    compact_rows = []
    for row in bootstrap_rows:
        compact_rows.append(
            {
                "comparison": row["display_label"],
                "delta_ap": row["point_delta_ap_a_minus_b"],
                "delta_ap_95_ci": (
                    f"[{float(row['delta_ap_ci_lower']):.4f}; "
                    f"{float(row['delta_ap_ci_upper']):.4f}]"
                ),
                "delta_roc_auc": row["point_delta_roc_auc_a_minus_b"],
                "delta_roc_auc_95_ci": (
                    f"[{float(row['delta_roc_auc_ci_lower']):.4f}; "
                    f"{float(row['delta_roc_auc_ci_upper']):.4f}]"
                ),
                "status": "post-hoc exploratory; conditional on selection",
            }
        )
    _write_csv(
        tables_dir / "09_thesis_compact.csv",
        compact_rows,
        (
            "comparison",
            "delta_ap",
            "delta_ap_95_ci",
            "delta_roc_auc",
            "delta_roc_auc_95_ci",
            "status",
        ),
    )

    _plot_forest(
        tree_results,
        output_base=figures_dir / "01_tree_model_paired_differences",
        title="Modele drzewiaste: sparowane różnice na development OOF 2015–2020",
    )
    _plot_forest(
        qnn_results,
        output_base=figures_dir / "02_qnn_seed_matched_paired_differences",
        title="QNN seed 20260818: porównania z kontrolami PCA-matched",
    )

    (report_dir / "summary.md").write_text(
        _summary_markdown(tree_results, qnn_results), encoding="utf-8"
    )
    (report_dir / "README.md").write_text(
        "# Post-hoc exploratory comparison v1.0.0\n\n"
        "Development-only reporting package generated from existing OOF "
        "predictions. No model fit or protected-period access is performed.\n\n"
        "- `summary.md`: compact numerical summary and claim boundaries;\n"
        "- `tables/01_*`: paired XGBoost comparisons;\n"
        "- `tables/02_*`: seed-matched QNN comparisons;\n"
        "- `tables/03_*`: existing pre-defined QNN variants;\n"
        "- `tables/04_*`: existing three-seed descriptive stability;\n"
        "- `tables/05_*`: alignment evidence;\n"
        "- `tables/06_*`: mandatory methodological disclosures;\n"
        "- `tables/07_*`: exact source provenance;\n"
        "- `tables/08_*`: auditable bootstrap replicates;\n"
        "- `tables/09_*`: compact chapter-ready numerical table;\n"
        "- `figures/`: forest plots in PNG and SVG.\n",
        encoding="utf-8",
    )

    files = []
    for path in sorted(
        (item for item in report_dir.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(report_dir).as_posix().encode("utf-8"),
    ):
        files.append(
            {
                "path": path.relative_to(report_dir).as_posix(),
                "sha256": file_sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    manifest = {
        "schema_version": 1,
        "id": analysis["id"],
        "version": analysis["version"],
        "status": "PASS",
        "analysis_role": "POST_HOC_EXPLORATORY_CONDITIONAL_ON_SELECTION",
        "project_model_fit_performed": False,
        "prediction_generation_performed": False,
        "hyperparameter_search_performed": False,
        "additional_seeds_used": False,
        "protected_feature_years_opened": False,
        "holdout_or_test_rows_opened": False,
        "observed_validation_feature_years": sorted(EXPECTED_YEARS),
        "rows": expected_rows,
        "positive_n": expected_positive_n,
        "economic_group_count": economic_group_count,
        "comparison_count": len(bootstrap_rows),
        "bootstrap": {
            "replicates_requested": int(configured_bootstrap["replicates"]),
            "minimum_valid_replicates": int(
                configured_bootstrap["minimum_valid_replicates"]
            ),
            "seed": int(configured_bootstrap["seed"]),
            "resampling_unit": "economic_group_id",
            "paired_cluster_draws_across_models": True,
            "interval": "95_percent_percentile_linear",
            "selection_adjusted": False,
        },
        "scope_decisions": {
            "fixed_l2_mlp": "NOT_AVAILABLE_NO_NEW_FIT",
            "executed_existing_fixed_l2_control": "PCA_MATCHED_FIXED_L2_LOGISTIC",
            "qnn_variants": "EXISTING_PREDEFINED_RESULTS_DESCRIPTIVE_ONLY",
            "seed_stability": "EXISTING_THREE_SEED_DESCRIPTIVE_TABLE_REUSED",
        },
        "output_files_excluding_manifest": files,
    }
    _write_json(report_dir / "manifest.json", manifest)
    return manifest


def verify_package(
    *, config_path: Path = DEFAULT_CONFIG, report_dir: Path = DEFAULT_REPORT_DIR
) -> dict[str, Any]:
    manifest_path = report_dir / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError("Missing report manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "PASS":
        raise RuntimeError("Report manifest is not PASS")
    for flag in (
        "project_model_fit_performed",
        "prediction_generation_performed",
        "hyperparameter_search_performed",
        "additional_seeds_used",
        "protected_feature_years_opened",
        "holdout_or_test_rows_opened",
    ):
        if manifest.get(flag) is not False:
            raise RuntimeError(f"Unsafe manifest flag: {flag}")
    if set(manifest.get("observed_validation_feature_years") or []) != EXPECTED_YEARS:
        raise RuntimeError("Manifest year boundary mismatch")
    expected_files = {
        str(row["path"]): (str(row["sha256"]), int(row["size_bytes"]))
        for row in manifest["output_files_excluding_manifest"]
    }
    actual_files = {
        path.relative_to(report_dir).as_posix()
        for path in report_dir.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual_files != set(expected_files):
        raise RuntimeError("Report file set mismatch")
    for relative_path, (expected_hash, expected_size) in expected_files.items():
        path = report_dir / relative_path
        if file_sha256(path) != expected_hash or path.stat().st_size != expected_size:
            raise RuntimeError(f"Report output mismatch: {relative_path}")

    with tempfile.TemporaryDirectory(prefix="posthoc_exploratory_verify_") as raw:
        regenerated = Path(raw) / "report"
        generate_package(config_path=config_path, report_dir=regenerated)
        regenerated_files = {
            path.relative_to(regenerated).as_posix(): file_sha256(path)
            for path in regenerated.rglob("*")
            if path.is_file()
        }
        current_files = {
            path.relative_to(report_dir).as_posix(): file_sha256(path)
            for path in report_dir.rglob("*")
            if path.is_file()
        }
        if regenerated_files != current_files:
            raise RuntimeError("Package is not deterministically reproducible")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("generate", "verify"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()
    if args.command == "generate":
        manifest = generate_package(
            config_path=args.config.resolve(), report_dir=args.report_dir.resolve()
        )
    else:
        manifest = verify_package(
            config_path=args.config.resolve(), report_dir=args.report_dir.resolve()
        )
    print(
        json.dumps(
            {
                "status": manifest["status"],
                "id": manifest["id"],
                "rows": manifest["rows"],
                "comparison_count": manifest["comparison_count"],
                "protected_feature_years_opened": manifest[
                    "protected_feature_years_opened"
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

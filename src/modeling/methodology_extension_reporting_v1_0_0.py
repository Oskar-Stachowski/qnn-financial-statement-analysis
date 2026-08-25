"""Build the extended seed-stability and computational-cost thesis report.

This module is reporting-only. It reads frozen development OOF predictions and
recorded worker runtimes. It never constructs or fits a model and it rejects
any prediction row outside development years 2015--2020.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

_MPLCONFIGDIR = Path(tempfile.gettempdir()) / "qnn_methodology_extension_matplotlib"
_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPLCONFIGDIR))
os.environ.setdefault("XDG_CACHE_HOME", str(_MPLCONFIGDIR / "xdg_cache"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import average_precision_score, roc_auc_score  # noqa: E402
import yaml  # noqa: E402

from src.modeling.verify_post_coarse_results_freeze import (  # noqa: E402
    verify_post_coarse_results_freeze,
)

matplotlib.rcParams["svg.hashsalt"] = "methodology_extension_v1_0_0"


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/methodology_extension_reporting_v1_0_0.yaml"
DEFAULT_OUTPUT = ROOT / "reports/methodology_extension_v1_0_0"
POST_ROOT = ROOT / "data/model_runs/post_coarse_v1_3_0"
COARSE_ROOT = ROOT / "data/model_runs/classical_mlp_coarse_v1"
DEVELOPMENT_YEARS = tuple(range(2015, 2021))
PROTECTED_YEARS = {2021, 2022, 2023, 2024}
SEEDS = (20260818, 20260819, 20260820)

FAMILY_LABELS = {
    "xgboost": "XGBoost",
    "hist_gradient_boosting": "HistGradientBoosting",
    "random_forest": "Random Forest",
    "pytorch_mlp": "MLP",
    "rbf_svm": "SVM RBF",
    "qnn": "QNN",
    "elastic_net_logistic": "Logistic Elastic Net",
    "fixed_l2_logistic": "Logistic fixed L2",
    "dummy_prior": "Dummy prior",
}


class MethodologyExtensionError(RuntimeError):
    """Raised when a reporting invariant is violated."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise MethodologyExtensionError(message)


def _load_json(path: Path) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), f"Missing JSON source: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"Expected JSON object: {path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def _output_manifest_path(path: Path, output_dir: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved.relative_to(output_dir.resolve()))


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _require(bool(rows), f"Refusing to write an empty table: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _feature_token(feature_block: str) -> str:
    return feature_block.replace("+", "_")


def _metric_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    _require(bool(rows), "Prediction rows are empty.")
    identifiers: set[str] = set()
    years: set[int] = set()
    normalized: list[tuple[str, int, int, float]] = []
    for row in rows:
        identifier = str(row.get("research_universe_company_year_id"))
        _require(identifier not in identifiers, f"Duplicate OOF identity: {identifier}")
        identifiers.add(identifier)
        year = int(row.get("validation_feature_year", -1))
        _require(year in DEVELOPMENT_YEARS, f"Invalid/protected prediction year: {year}")
        _require(year not in PROTECTED_YEARS, f"Protected prediction year opened: {year}")
        years.add(year)
        target = int(row["target_label"])
        score = float(row["raw_score"])
        _require(target in {0, 1}, f"Non-binary target for {identifier}")
        _require(math.isfinite(score), f"Non-finite score for {identifier}")
        normalized.append((identifier, year, target, score))
    _require(years == set(DEVELOPMENT_YEARS), f"Unexpected OOF years: {sorted(years)}")
    normalized.sort(key=lambda item: (item[1], item[0]))
    targets = np.asarray([item[2] for item in normalized], dtype=np.int8)
    scores = np.asarray([item[3] for item in normalized], dtype=np.float64)
    fold_ap: list[float] = []
    for year in DEVELOPMENT_YEARS:
        mask = np.asarray([item[1] == year for item in normalized], dtype=bool)
        fold_ap.append(float(average_precision_score(targets[mask], scores[mask])))
    return {
        "n": int(targets.size),
        "positive_n": int(targets.sum()),
        "positive_share": float(targets.mean()),
        "pooled_oof_pr_auc": float(average_precision_score(targets, scores)),
        "pooled_oof_roc_auc": float(roc_auc_score(targets, scores)),
        "fold_pr_auc_mean": float(np.mean(fold_ap)),
        "fold_pr_auc_sample_sd": float(np.std(fold_ap, ddof=1)),
        "fold_pr_auc_min": float(np.min(fold_ap)),
        "fold_pr_auc_max": float(np.max(fold_ap)),
    }


def _rows_from_prediction_file(path: Path, expected_sha256: str | None = None) -> list[dict[str, Any]]:
    if expected_sha256 is not None:
        _require(_sha256(path) == expected_sha256, f"Prediction hash changed: {path}")
    payload = _load_json(path)
    rows = payload.get("rows") or []
    _require(isinstance(rows, list) and rows, f"Empty prediction file: {path}")
    return [dict(row) for row in rows]


def _rows_from_fold_manifests(
    candidate_manifest: Mapping[str, Any], *, base_root: Path
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fold_manifests = candidate_manifest.get("fold_manifests") or []
    _require(len(fold_manifests) == 6, "Expected six fold manifests.")
    for fold in fold_manifests:
        relative = fold.get("oof_prediction_artifact")
        _require(isinstance(relative, str), "Fold prediction path is missing.")
        path = (base_root / relative).resolve()
        _require(path.is_relative_to(base_root.resolve()), f"Prediction escaped root: {path}")
        rows.extend(
            _rows_from_prediction_file(path, str(fold["oof_prediction_artifact_sha256"]))
        )
    return rows


def _runtime_from_fold_manifests(candidate_manifest: Mapping[str, Any]) -> dict[str, Any]:
    folds = candidate_manifest.get("fold_manifests") or []
    _require(len(folds) == 6, "Expected six runtime fold manifests.")
    attempts = [attempt for fold in folds for attempt in (fold.get("attempts") or [])]
    _require(attempts, "No recorded runtime attempts.")
    runtime = float(sum(float(attempt["runtime_seconds"]) for attempt in attempts))
    completed = sum(attempt.get("outcome") == "COMPLETE" for attempt in attempts)
    return {
        "runtime_seconds": runtime,
        "fold_executions": len(folds),
        "attempts": len(attempts),
        "completed_attempts": completed,
        "retries_or_interruptions": len(attempts) - completed,
    }


def _coarse_family_manifest(family: str) -> Path:
    return COARSE_ROOT / "coarse_results" / family / "result_manifest.json"


def _coarse_candidate(family: str, configuration_id: str, feature_block: str) -> dict[str, Any]:
    path = _coarse_family_manifest(family)
    payload = _load_json(path)
    matches = [
        row
        for row in payload.get("candidate_results") or []
        if row.get("configuration_id") == configuration_id
        and row.get("feature_block") == feature_block
        and int(row.get("training_seed")) == SEEDS[0]
    ]
    _require(len(matches) == 1, f"Expected one coarse candidate: {family}/{configuration_id}/{feature_block}")
    row = dict(matches[0])
    row["_family_manifest"] = path
    return row


def _post_candidate_path(
    *, stage: str, family: str, configuration_id: str, feature_block: str, seed: int
) -> Path:
    path = (
        POST_ROOT
        / "candidate_results"
        / stage
        / family
        / configuration_id
        / _feature_token(feature_block)
        / f"seed_{seed}"
        / "candidate_manifest.json"
    )
    _require(path.is_file(), f"Missing post-coarse candidate: {path}")
    return path


def _seed_record(rep: Mapping[str, Any], seed: int, role: str, label: str) -> dict[str, Any]:
    family = str(rep["family"])
    configuration_id = str(rep["configuration_id"])
    feature_block = str(rep["feature_block"])
    stage = str(rep["stage"])
    if seed == SEEDS[0] and family != "qnn":
        source = _coarse_candidate(family, configuration_id, feature_block)
        prediction_path = (COARSE_ROOT / str(source["canonical_oof_predictions"])).resolve()
        rows = _rows_from_prediction_file(
            prediction_path, str(source["canonical_oof_predictions_sha256"])
        )
        runtime = {
            "runtime_seconds": float(source["runtime_seconds"]),
            "fold_executions": len(source.get("per_fold") or []),
            "attempts": len(source.get("per_fold") or []),
            "completed_attempts": len(source.get("per_fold") or []),
            "retries_or_interruptions": 0,
        }
        metric_source = Path(source["_family_manifest"])
        runtime_source = metric_source
        expected_ap = float(source["pooled_oof_pr_auc"])
    else:
        candidate_path = _post_candidate_path(
            stage=stage,
            family=family,
            configuration_id=configuration_id,
            feature_block=feature_block,
            seed=seed,
        )
        candidate_manifest = _load_json(candidate_path)
        metric_candidate = candidate_manifest
        runtime_candidate = candidate_manifest
        runtime_source = candidate_path
        if family == "qnn" and not any(
            fold.get("attempts") for fold in candidate_manifest.get("fold_manifests") or []
        ):
            reuse = (candidate_manifest.get("candidate") or {}).get("reuse_source") or {}
            source_configuration = str(reuse.get("configuration_id"))
            _require(source_configuration, "QNN reuse source is missing.")
            runtime_source = _post_candidate_path(
                stage=str(reuse.get("stage")),
                family="qnn",
                configuration_id=source_configuration,
                feature_block=feature_block,
                seed=seed,
            )
            runtime_candidate = _load_json(runtime_source)
            rows = _rows_from_fold_manifests(runtime_candidate, base_root=POST_ROOT)
        else:
            rows = _rows_from_fold_manifests(metric_candidate, base_root=POST_ROOT)
        runtime = _runtime_from_fold_manifests(runtime_candidate)
        metric_source = candidate_path
        expected_ap = float((metric_candidate.get("candidate") or {})["pooled_oof_pr_auc"])
    metrics = _metric_summary(rows)
    _require(
        math.isclose(metrics["pooled_oof_pr_auc"], expected_ap, abs_tol=1e-12),
        f"Recomputed AP differs from source for {label}, seed {seed}",
    )
    environment_role = "qnn_mlp" if family in {"qnn", "pytorch_mlp"} else "classical"
    return {
        "report_role": role,
        "model_label": label,
        "family": family,
        "stage": stage,
        "feature_block": feature_block,
        "configuration_id": configuration_id,
        "record_type": "SEED",
        "training_seed": seed,
        "stability_status": "DESCRIPTIVE_ONLY_N3",
        **metrics,
        **runtime,
        "runtime_minutes": runtime["runtime_seconds"] / 60.0,
        "runtime_hours": runtime["runtime_seconds"] / 3600.0,
        "software_environment_role": environment_role,
        "metric_source": _relative(metric_source),
        "runtime_source": _relative(runtime_source),
    }


def _ensemble_record(rep: Mapping[str, Any], role: str, label: str) -> dict[str, Any]:
    path_value = rep.get("oof_prediction_artifact") or rep.get("prediction_artifact")
    _require(isinstance(path_value, str), f"Missing ensemble path for {label}")
    path = Path(path_value)
    prediction_path = path if path.is_absolute() else (ROOT / path if str(path).startswith("data/") else POST_ROOT / path)
    expected_hash = rep.get("oof_prediction_artifact_sha256") or rep.get("prediction_artifact_sha256")
    rows = _rows_from_prediction_file(prediction_path.resolve(), str(expected_hash))
    metrics = _metric_summary(rows)
    source_ap = rep.get("pooled_oof_pr_auc")
    if source_ap is None and isinstance(rep.get("metric_summary"), Mapping):
        source_ap = rep["metric_summary"].get("pooled_oof_pr_auc")
    if source_ap is None and isinstance(rep.get("row"), Mapping):
        source_ap = rep["row"].get("pooled_oof_pr_auc")
    _require(source_ap is not None, f"Missing ensemble AP for {label}")
    _require(
        math.isclose(metrics["pooled_oof_pr_auc"], float(source_ap), abs_tol=1e-12),
        f"Recomputed ensemble AP differs for {label}",
    )
    return {
        "report_role": role,
        "model_label": label,
        "family": rep["family"],
        "stage": rep["stage"],
        "feature_block": rep["feature_block"],
        "configuration_id": rep["configuration_id"],
        "record_type": "SCORE_AVERAGED_ENSEMBLE",
        "training_seed": "AVERAGED_20260818_20260819_20260820",
        "stability_status": "DESCRIPTIVE_ONLY_N3",
        **metrics,
        "runtime_seconds": None,
        "runtime_minutes": None,
        "runtime_hours": None,
        "fold_executions": None,
        "attempts": None,
        "completed_attempts": None,
        "retries_or_interruptions": None,
        "software_environment_role": (
            "qnn_mlp" if rep["family"] in {"qnn", "pytorch_mlp"} else "classical"
        ),
        "metric_source": _relative(prediction_path),
        "runtime_source": "NOT_APPLICABLE",
    }


def _representatives() -> list[dict[str, Any]]:
    ranking = _load_json(POST_ROOT / "final_primary_development_ranking.json")
    primary = ranking.get("family_representatives") or []
    _require(len(primary) == 9, "Expected nine final primary family representatives.")
    records: list[dict[str, Any]] = []
    for rep in primary:
        item = dict(rep)
        item["report_role"] = "PRIMARY_FAMILY_REPRESENTATIVE"
        item["model_label"] = FAMILY_LABELS[str(item["family"])]
        records.append(item)
    confirmation = _load_json(POST_ROOT / "confirmation_phase_manifest.json")
    comparator_ref = confirmation.get("supplemental_mlp_confirmed_result_reference") or {}
    comparator = dict(comparator_ref.get("row") or {})
    _require(comparator.get("family") == "pytorch_mlp", "Missing title-aligned MLP comparator.")
    comparator["prediction_artifact"] = comparator_ref["prediction_artifact"]
    comparator["prediction_artifact_sha256"] = comparator_ref["prediction_artifact_sha256"]
    comparator["report_role"] = "SECONDARY_TITLE_ALIGNED_NEURAL_COMPARATOR"
    comparator["model_label"] = "MLP (title-aligned comparator)"
    records.append(comparator)
    return records


def _build_seed_tables() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    detailed: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for rep in _representatives():
        role = str(rep["report_role"])
        label = str(rep["model_label"])
        is_averaged = str(rep.get("training_seed", "")).startswith("AVERAGED_")
        seed_rows: list[dict[str, Any]] = []
        if is_averaged:
            for seed in SEEDS:
                seed_rows.append(_seed_record(rep, seed, role, label))
            ensemble = _ensemble_record(rep, role, label)
            detailed.extend(seed_rows)
            detailed.append(ensemble)
            ap = np.asarray([row["pooled_oof_pr_auc"] for row in seed_rows], dtype=float)
            roc = np.asarray([row["pooled_oof_roc_auc"] for row in seed_rows], dtype=float)
            status = "DESCRIPTIVE_ONLY_N3"
            protocol = "THREE_SEEDS_PLUS_RAW_SCORE_AVERAGE"
            seed_count = 3
            seed_mean = float(np.mean(ap))
            seed_sd = float(np.std(ap, ddof=1))
            seed_min = float(np.min(ap))
            seed_max = float(np.max(ap))
            seed_range = seed_max - seed_min
            roc_mean = float(np.mean(roc))
            roc_sd = float(np.std(roc, ddof=1))
            roc_min = float(np.min(roc))
            roc_max = float(np.max(roc))
            roc_range = roc_max - roc_min
        else:
            seed = int(rep["training_seed"])
            single = _seed_record(rep, seed, role, label)
            single["stability_status"] = "NOT_APPLICABLE_DETERMINISTIC_SINGLE_RUN"
            detailed.append(single)
            ensemble = single
            status = "NOT_APPLICABLE_DETERMINISTIC_SINGLE_RUN"
            protocol = "SINGLE_DETERMINISTIC_RUN"
            seed_count = 1
            seed_mean = single["pooled_oof_pr_auc"]
            seed_sd = None
            seed_min = seed_max = seed_mean
            seed_range = 0.0
            roc_mean = single["pooled_oof_roc_auc"]
            roc_sd = None
            roc_min = roc_max = roc_mean
            roc_range = 0.0
        summary.append(
            {
                "report_role": role,
                "model_label": label,
                "family": rep["family"],
                "stage": rep["stage"],
                "feature_block": rep["feature_block"],
                "configuration_id": rep["configuration_id"],
                "seed_protocol": protocol,
                "seed_count": seed_count,
                "stability_status": status,
                "pooled_oof_pr_auc_seed_mean": seed_mean,
                "pooled_oof_pr_auc_seed_sample_sd": seed_sd,
                "pooled_oof_pr_auc_seed_min": seed_min,
                "pooled_oof_pr_auc_seed_max": seed_max,
                "pooled_oof_pr_auc_seed_range": seed_range,
                "pooled_oof_pr_auc_score_averaged_ensemble": ensemble["pooled_oof_pr_auc"],
                "pooled_oof_roc_auc_seed_mean": roc_mean,
                "pooled_oof_roc_auc_seed_sample_sd": roc_sd,
                "pooled_oof_roc_auc_seed_min": roc_min,
                "pooled_oof_roc_auc_seed_max": roc_max,
                "pooled_oof_roc_auc_seed_range": roc_range,
                "pooled_oof_roc_auc_score_averaged_ensemble": ensemble["pooled_oof_roc_auc"],
                "ensemble_fold_pr_auc_mean": ensemble["fold_pr_auc_mean"],
                "ensemble_fold_pr_auc_sample_sd": ensemble["fold_pr_auc_sample_sd"],
                "interpretation": (
                    "Descriptive dispersion only; n=3 seeds is not an inferential interval."
                    if seed_count == 3
                    else "Seed dispersion is not applicable to the frozen deterministic single run."
                ),
            }
        )
    summary.sort(key=lambda row: (row["report_role"], -float(row["pooled_oof_pr_auc_score_averaged_ensemble"])))
    detailed.sort(key=lambda row: (row["report_role"], row["model_label"], str(row["training_seed"])))
    return summary, detailed


def _build_cost_tables(
    seed_summary: Sequence[Mapping[str, Any]], seed_detailed: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    per_seed = [dict(row) for row in seed_detailed if row["record_type"] == "SEED"]
    xgb_times = [
        float(row["runtime_seconds"])
        for row in per_seed
        if row["report_role"] == "PRIMARY_FAMILY_REPRESENTATIVE"
        and row["family"] == "xgboost"
    ]
    _require(len(xgb_times) == 3, "Expected three XGBoost runtime observations.")
    xgb_median = float(np.median(xgb_times))
    summary_lookup = {
        (row["report_role"], row["family"], row["feature_block"], row["configuration_id"]): row
        for row in seed_summary
    }
    final: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = {}
    for row in per_seed:
        key = (
            str(row["report_role"]),
            str(row["model_label"]),
            str(row["family"]),
            str(row["feature_block"]),
            str(row["configuration_id"]),
        )
        grouped.setdefault(key, []).append(row)
    for (role, label, family, block, configuration), rows in grouped.items():
        runtimes = np.asarray([float(row["runtime_seconds"]) for row in rows], dtype=float)
        stable = summary_lookup[(role, family, block, configuration)]
        environment_role = str(rows[0]["software_environment_role"])
        final.append(
            {
                "report_role": role,
                "model_label": label,
                "family": family,
                "feature_block": block,
                "configuration_id": configuration,
                "software_environment_role": environment_role,
                "seed_count_with_runtime": len(rows),
                "folds_per_seed": 6,
                "worker_runtime_seconds_median": float(np.median(runtimes)),
                "worker_runtime_seconds_min": float(np.min(runtimes)),
                "worker_runtime_seconds_max": float(np.max(runtimes)),
                "worker_runtime_minutes_median": float(np.median(runtimes) / 60.0),
                "worker_runtime_hours_median": float(np.median(runtimes) / 3600.0),
                "runtime_multiple_vs_xgboost_median": float(np.median(runtimes) / xgb_median),
                "pooled_oof_pr_auc_for_plot": stable["pooled_oof_pr_auc_score_averaged_ensemble"],
                "performance_basis": (
                    "RAW_SCORE_AVERAGED_ENSEMBLE"
                    if int(stable["seed_count"]) == 3
                    else "SINGLE_DETERMINISTIC_RUN"
                ),
                "runtime_basis": "SUM_OF_RECORDED_WORKER_ATTEMPT_SECONDS_ACROSS_SIX_TEMPORAL_FOLDS",
                "controlled_hardware_benchmark": False,
                "comparability_note": (
                    "Recorded development worker runtime; environments and execution dates differ. "
                    "Use descriptively, not as a controlled hardware benchmark."
                ),
            }
        )
    final.sort(key=lambda row: float(row["worker_runtime_seconds_median"]))
    per_seed.sort(key=lambda row: (row["report_role"], row["model_label"], int(row["training_seed"])))
    return final, per_seed


def _candidate_tree_runtime(paths: Iterable[Path]) -> dict[str, Any]:
    total = 0.0
    candidates = 0
    folds = 0
    attempts = 0
    completed = 0
    interruptions = 0
    for path in sorted(paths):
        payload = _load_json(path)
        runtime = _runtime_from_fold_manifests(payload)
        total += float(runtime["runtime_seconds"])
        candidates += 1
        folds += int(runtime["fold_executions"])
        attempts += int(runtime["attempts"])
        completed += int(runtime["completed_attempts"])
        interruptions += int(runtime["retries_or_interruptions"])
    return {
        "runtime_seconds": total,
        "candidate_configurations": candidates,
        "fold_executions": folds,
        "attempts": attempts,
        "completed_attempts": completed,
        "interrupted_or_retry_attempts": interruptions,
    }


def _build_program_cost_table() -> list[dict[str, Any]]:
    coarse_total = 0.0
    coarse_candidates = 0
    coarse_folds = 0
    for path in sorted((COARSE_ROOT / "coarse_results").glob("*/result_manifest.json")):
        payload = _load_json(path)
        rows = payload.get("candidate_results") or []
        coarse_total += sum(float(row["runtime_seconds"]) for row in rows)
        coarse_candidates += len(rows)
        coarse_folds += sum(len(row.get("per_fold") or []) for row in rows)
    refinement_paths = sorted(
        (POST_ROOT / "candidate_results/refinement").glob("**/candidate_manifest.json")
    )
    refinement = _candidate_tree_runtime(
        path for path in refinement_paths if "seed_20260818" in path.parts
    )
    confirmation_paths = sorted(
        (POST_ROOT / "candidate_results/coarse").glob("**/candidate_manifest.json")
    ) + [path for path in refinement_paths if "seed_20260818" not in path.parts]
    confirmation = _candidate_tree_runtime(confirmation_paths)
    refinement_seconds = float(refinement["runtime_seconds"])
    confirmation_seconds = float(confirmation["runtime_seconds"])
    qnn_base_path = POST_ROOT / "qnn_resource_ledger.json"
    qnn_full_path = POST_ROOT / "qnn_confirmation_resource_ledger.json"
    qnn_base = _load_json(qnn_base_path)
    qnn_full = _load_json(qnn_full_path)
    qnn_base_seconds = float(qnn_base["total_runtime_seconds"])
    qnn_full_seconds = float(qnn_full["total_runtime_seconds"])
    qnn_increment = qnn_full_seconds - qnn_base_seconds
    _require(qnn_increment > 0.0, "QNN confirmation runtime increment must be positive.")
    rows = [
        {
            "program_group": "CLASSICAL_AND_MLP",
            "stage": "COARSE_SEARCH_SEED_20260818",
            "row_type": "ADDITIVE_COMPONENT",
            "candidate_configurations": coarse_candidates,
            "fold_executions": coarse_folds,
            "attempts": coarse_folds,
            "completed_attempts": coarse_folds,
            "interrupted_or_retry_attempts": 0,
            "worker_runtime_seconds": coarse_total,
            "worker_runtime_hours": coarse_total / 3600.0,
            "source": "data/model_runs/classical_mlp_coarse_v1/coarse_results/*/result_manifest.json",
            "comparability_note": "Search breadth is protocol-specific; do not compare directly with one final fit.",
        },
        {
            "program_group": "CLASSICAL_AND_MLP",
            "stage": "POST_COARSE_REFINEMENT_SEED_20260818",
            "row_type": "ADDITIVE_COMPONENT",
            **{key: value for key, value in refinement.items() if key != "runtime_seconds"},
            "worker_runtime_seconds": refinement_seconds,
            "worker_runtime_hours": None,
            "source": "data/model_runs/post_coarse_v1_3_0/candidate_results/refinement/**/candidate_manifest.json",
            "comparability_note": "Search breadth is protocol-specific; do not compare directly with one final fit.",
        },
        {
            "program_group": "CLASSICAL_AND_MLP",
            "stage": "CONFIRMATION_EXTRA_SEEDS_20260819_20260820",
            "row_type": "ADDITIVE_COMPONENT",
            **{key: value for key, value in confirmation.items() if key != "runtime_seconds"},
            "worker_runtime_seconds": confirmation_seconds,
            "worker_runtime_hours": None,
            "source": "data/model_runs/post_coarse_v1_3_0/candidate_results/coarse/**/candidate_manifest.json",
            "comparability_note": "Recorded confirmation breadth; comparator reuse prevents double counting.",
        },
        {
            "program_group": "QNN",
            "stage": "Q1_Q2_THROUGH_SEED_20260818",
            "row_type": "ADDITIVE_COMPONENT",
            "candidate_configurations": None,
            "fold_executions": None,
            "attempts": int(qnn_base["started_attempts"]),
            "completed_attempts": int(qnn_base["completed_attempts"]),
            "interrupted_or_retry_attempts": int(qnn_base["interrupted_attempts"]),
            "worker_runtime_seconds": qnn_base_seconds,
            "worker_runtime_hours": qnn_base_seconds / 3600.0,
            "source": _relative(qnn_base_path),
            "comparability_note": "Cumulative QNN research-path ledger, including one controller restart.",
        },
        {
            "program_group": "QNN",
            "stage": "CONFIRMATION_INCREMENT_EXTRA_SEEDS",
            "row_type": "ADDITIVE_COMPONENT",
            "candidate_configurations": None,
            "fold_executions": None,
            "attempts": int(qnn_full["started_attempts"]) - int(qnn_base["started_attempts"]),
            "completed_attempts": int(qnn_full["completed_attempts"]) - int(qnn_base["completed_attempts"]),
            "interrupted_or_retry_attempts": int(qnn_full["interrupted_attempts"]) - int(qnn_base["interrupted_attempts"]),
            "worker_runtime_seconds": qnn_increment,
            "worker_runtime_hours": qnn_increment / 3600.0,
            "source": f"difference({_relative(qnn_full_path)}, {_relative(qnn_base_path)})",
            "comparability_note": "Difference of cumulative ledgers; no model execution performed by this report.",
        },
    ]
    for row in rows:
        if row["worker_runtime_hours"] is None:
            row["worker_runtime_hours"] = float(row["worker_runtime_seconds"]) / 3600.0
    classical_total = coarse_total + refinement_seconds + confirmation_seconds
    rows.extend(
        [
            {
                "program_group": "CLASSICAL_AND_MLP",
                "stage": "TOTAL_RECORDED_DEVELOPMENT_PROGRAM",
                "row_type": "NON_ADDITIVE_SUMMARY",
                "candidate_configurations": coarse_candidates
                + int(refinement["candidate_configurations"])
                + int(confirmation["candidate_configurations"]),
                "fold_executions": coarse_folds
                + int(refinement["fold_executions"])
                + int(confirmation["fold_executions"]),
                "attempts": coarse_folds + int(refinement["attempts"]) + int(confirmation["attempts"]),
                "completed_attempts": coarse_folds
                + int(refinement["completed_attempts"])
                + int(confirmation["completed_attempts"]),
                "interrupted_or_retry_attempts": int(refinement["interrupted_or_retry_attempts"])
                + int(confirmation["interrupted_or_retry_attempts"]),
                "worker_runtime_seconds": classical_total,
                "worker_runtime_hours": classical_total / 3600.0,
                "source": "sum of CLASSICAL_AND_MLP additive components",
                "comparability_note": "Descriptive total only; candidate count and model complexity differ from QNN.",
            },
            {
                "program_group": "QNN",
                "stage": "TOTAL_RECORDED_Q1_Q2_CONFIRMATION_PROGRAM",
                "row_type": "NON_ADDITIVE_SUMMARY",
                "candidate_configurations": None,
                "fold_executions": None,
                "attempts": int(qnn_full["started_attempts"]),
                "completed_attempts": int(qnn_full["completed_attempts"]),
                "interrupted_or_retry_attempts": int(qnn_full["interrupted_attempts"]),
                "worker_runtime_seconds": qnn_full_seconds,
                "worker_runtime_hours": qnn_full_seconds / 3600.0,
                "source": _relative(qnn_full_path),
                "comparability_note": "Descriptive total only; not an apples-to-apples speed ratio versus a single classical configuration.",
            },
        ]
    )
    return rows


def _runtime_environments() -> list[dict[str, Any]]:
    runtime = _load_json(POST_ROOT / "runtime_metadata.json")
    qnn_smoke = _load_json(POST_ROOT / "qnn_resource_smoke.json")
    host = ((qnn_smoke.get("environment") or {}).get("host") or {})
    rows: list[dict[str, Any]] = []
    for role in ("classical", "qnn_mlp"):
        env = (runtime.get("workers") or {}).get(role) or {}
        packages = env.get("main_library_versions") or {}
        rows.append(
            {
                "software_environment_role": role,
                "python_version": env.get("python_version"),
                "numpy_version": packages.get("numpy"),
                "pandas_version": packages.get("pandas"),
                "scikit_learn_version": packages.get("scikit-learn"),
                "xgboost_version": packages.get("xgboost"),
                "torch_version": packages.get("torch"),
                "pennylane_version": packages.get("PennyLane"),
                "pennylane_lightning_version": packages.get("pennylane-lightning"),
                "host_platform_observed_by_qnn_smoke": host.get("platform"),
                "host_architecture_observed_by_qnn_smoke": host.get("architecture"),
                "logical_cpu_count_observed_by_qnn_smoke": host.get("logical_cpu_count"),
                "ram_bytes_observed_by_qnn_smoke": host.get("ram_bytes"),
                "runtime_interpretation": "Recorded historical environment; report generation does not rerun benchmarks.",
            }
        )
    device = qnn_smoke.get("device") or {}
    case = next(
        item
        for item in qnn_smoke.get("cases") or []
        if item.get("ansatz") == "ROT_CNOT_RING" and item.get("qubits") == 4
    )
    rows.append(
        {
            "software_environment_role": "qnn_final_model_details",
            "python_version": (qnn_smoke.get("environment") or {}).get("expected_python"),
            "numpy_version": None,
            "pandas_version": None,
            "scikit_learn_version": None,
            "xgboost_version": None,
            "torch_version": None,
            "pennylane_version": None,
            "pennylane_lightning_version": None,
            "host_platform_observed_by_qnn_smoke": host.get("platform"),
            "host_architecture_observed_by_qnn_smoke": host.get("architecture"),
            "logical_cpu_count_observed_by_qnn_smoke": host.get("logical_cpu_count"),
            "ram_bytes_observed_by_qnn_smoke": host.get("ram_bytes"),
            "qnn_device": device.get("name"),
            "qnn_execution": "analytic",
            "qnn_shots": device.get("shots"),
            "qnn_interface": device.get("interface"),
            "qnn_differentiation": device.get("differentiation"),
            "qnn_dtype": device.get("dtype"),
            "qnn_ansatz": case.get("ansatz"),
            "qnn_qubits": case.get("qubits"),
            "qnn_layers": case.get("layers"),
            "qnn_trainable_parameters": case.get("trainable_parameters"),
            "runtime_interpretation": "Simulator runtime only; no quantum-hardware or quantum-advantage claim is permitted.",
        }
    )
    return rows


def _disclosures() -> list[dict[str, Any]]:
    return [
        {
            "topic": "seed_dispersion",
            "disclosure": "Seed SD and range are descriptive statistics from exactly three seeds, not confidence intervals and not inferential evidence.",
            "thesis_placement": "Methods limitation and note below the seed-stability table",
        },
        {
            "topic": "fold_vs_seed_variability",
            "disclosure": "Temporal-fold SD measures year-to-year validation variability; seed SD measures training-initialization variability. They must be reported separately.",
            "thesis_placement": "Methods and table definitions",
        },
        {
            "topic": "ensemble_metric",
            "disclosure": "The final ensemble AP is calculated after row-wise averaging of raw scores and therefore is not the arithmetic mean of seed-level AP values.",
            "thesis_placement": "Methods and results table note",
        },
        {
            "topic": "runtime_scope",
            "disclosure": "Final-representative cost sums recorded worker-attempt seconds across six development folds. Program-stage cost includes different search breadths and must be shown separately.",
            "thesis_placement": "Computational methods",
        },
        {
            "topic": "runtime_comparability",
            "disclosure": "Runtimes were recorded on historical executions in different Python/software environments and on different dates; this is not a controlled hardware benchmark.",
            "thesis_placement": "Limitations",
        },
        {
            "topic": "qnn_backend",
            "disclosure": "QNN used the analytic lightning.qubit simulator with shots=None, adjoint differentiation and float64; reported time is not quantum-hardware latency.",
            "thesis_placement": "QNN implementation details",
        },
        {
            "topic": "claim_boundary",
            "disclosure": "Simulator-only results do not support a quantum-advantage claim.",
            "thesis_placement": "Discussion and limitations",
        },
        {
            "topic": "data_boundary",
            "disclosure": "All metrics in this extension use development OOF years 2015--2020. Protected years 2021--2024 are neither opened nor reported.",
            "thesis_placement": "Methods and data split",
        },
    ]


def _format_human_runtime(seconds: float) -> str:
    if seconds < 60.0:
        return f"{seconds:.2f} s"
    if seconds < 3600.0:
        return f"{seconds / 60.0:.2f} min"
    return f"{seconds / 3600.0:.2f} h"


def _compact_seed_table(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    display_labels = {
        "MLP (title-aligned comparator)": "MLP (porównanie tytułowe)",
        "Logistic Elastic Net": "Regresja logistyczna Elastic Net",
        "Logistic fixed L2": "Regresja logistyczna fixed L2",
    }
    for row in rows:
        n = int(row["seed_count"])
        if n == 3:
            seed_stat = (
                f"{float(row['pooled_oof_pr_auc_seed_mean']):.4f} ± "
                f"{float(row['pooled_oof_pr_auc_seed_sample_sd']):.4f}"
            )
            seed_range = (
                f"{float(row['pooled_oof_pr_auc_seed_min']):.4f}–"
                f"{float(row['pooled_oof_pr_auc_seed_max']):.4f}"
            )
            status = "opisowo, n=3"
        else:
            seed_stat = "nie dotyczy"
            seed_range = "nie dotyczy"
            status = "model deterministyczny"
        compact.append(
            {
                "Rola": (
                    "główna"
                    if row["report_role"] == "PRIMARY_FAMILY_REPRESENTATIVE"
                    else "porównanie tytułowe"
                ),
                "Model": display_labels.get(str(row["model_label"]), row["model_label"]),
                "Blok cech": row["feature_block"],
                "AP końcowe": f"{float(row['pooled_oof_pr_auc_score_averaged_ensemble']):.4f}",
                "AP seed: średnia ± SD": seed_stat,
                "AP seed: min–max": seed_range,
                "Status": status,
            }
        )
    return compact


def _compact_cost_table(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    display_labels = {
        "MLP (title-aligned comparator)": "MLP (porównanie tytułowe)",
        "Logistic Elastic Net": "Regresja logistyczna Elastic Net",
        "Logistic fixed L2": "Regresja logistyczna fixed L2",
    }
    for row in rows:
        minimum = float(row["worker_runtime_seconds_min"])
        maximum = float(row["worker_runtime_seconds_max"])
        compact.append(
            {
                "Rola": (
                    "główna"
                    if row["report_role"] == "PRIMARY_FAMILY_REPRESENTATIVE"
                    else "porównanie tytułowe"
                ),
                "Model": display_labels.get(str(row["model_label"]), row["model_label"]),
                "Blok cech": row["feature_block"],
                "AP": f"{float(row['pooled_oof_pr_auc_for_plot']):.4f}",
                "Mediana czasu / 6 foldów": _format_human_runtime(
                    float(row["worker_runtime_seconds_median"])
                ),
                "Zakres czasu": (
                    _format_human_runtime(minimum)
                    if math.isclose(minimum, maximum, abs_tol=1e-12)
                    else f"{_format_human_runtime(minimum)}–{_format_human_runtime(maximum)}"
                ),
                "Mnożnik vs XGBoost": f"{float(row['runtime_multiple_vs_xgboost_median']):.1f}×",
                "Status benchmarku": "opisowy, niekontrolowany",
            }
        )
    return compact


def _plot_seed_stability(path_base: Path, summary: Sequence[Mapping[str, Any]], detailed: Sequence[Mapping[str, Any]]) -> None:
    stochastic = [row for row in summary if int(row["seed_count"]) == 3]
    stochastic.sort(key=lambda row: float(row["pooled_oof_pr_auc_score_averaged_ensemble"]))
    fig, ax = plt.subplots(figsize=(10.2, 5.8))
    colors = {"qnn": "#C84B31", "pytorch_mlp": "#496A9C"}
    for index, row in enumerate(stochastic):
        selected = [
            item
            for item in detailed
            if item["report_role"] == row["report_role"]
            and item["family"] == row["family"]
            and item["feature_block"] == row["feature_block"]
            and item["configuration_id"] == row["configuration_id"]
            and item["record_type"] == "SEED"
        ]
        values = [float(item["pooled_oof_pr_auc"]) for item in selected]
        color = colors.get(str(row["family"]), "#667085")
        ax.hlines(index, min(values), max(values), color=color, linewidth=2.2, alpha=0.85)
        ax.scatter(values, [index] * len(values), s=34, color=color, edgecolor="white", linewidth=0.6, zorder=3)
        ax.scatter(
            [float(row["pooled_oof_pr_auc_score_averaged_ensemble"])],
            [index],
            marker="D",
            s=50,
            facecolor="white",
            edgecolor=color,
            linewidth=1.6,
            zorder=4,
        )
    ax.set_yticks(range(len(stochastic)))
    display_labels = {
        "MLP (title-aligned comparator)": "MLP (porównanie tytułowe)",
        "Logistic Elastic Net": "Regresja logistyczna Elastic Net",
    }
    ax.set_yticklabels(
        [
            f"{display_labels.get(str(row['model_label']), row['model_label'])} · {row['feature_block']}"
            for row in stochastic
        ]
    )
    ax.set_xlabel("Pooled OOF PR-AUC (2015–2020)")
    fig.suptitle(
        "Stabilność wyników względem seedu",
        x=0.08,
        y=0.985,
        ha="left",
        fontweight="bold",
        fontsize=15,
    )
    fig.text(
        0.08,
        0.935,
        "Punkty: 3 seedy · odcinek: min–max · romb: wynik po uśrednieniu raw score",
        ha="left",
        fontsize=9,
        color="#475467",
    )
    ax.grid(axis="x", color="#E4E7EC", linewidth=0.8)
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    path_base.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path_base.with_suffix(".png"),
        dpi=220,
        bbox_inches="tight",
        metadata={"Software": "methodology_extension_reporting_v1_0_0"},
    )
    fig.savefig(path_base.with_suffix(".svg"), bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)


def _plot_runtime(path_base: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(10.2, 6.2))
    short_labels = {
        "Logistic Elastic Net": "Elastic Net",
        "Logistic fixed L2": "Fixed L2",
        "HistGradientBoosting": "HistGB",
        "MLP (title-aligned comparator)": "MLP L+D (comparator)",
    }
    offsets = {
        "Elastic Net": (5, -12),
        "XGBoost": (5, 10),
        "HistGB": (5, 1),
        "Dummy prior": (5, 6),
        "Fixed L2": (5, -28),
        "MLP L+D (comparator)": (5, 16),
        "MLP": (5, -18),
        "SVM RBF": (5, 4),
        "Random Forest": (5, 6),
        "QNN": (5, 7),
    }
    for row in rows:
        family = str(row["family"])
        is_secondary = row["report_role"] != "PRIMARY_FAMILY_REPRESENTATIVE"
        color = "#C84B31" if family == "qnn" else ("#496A9C" if family == "pytorch_mlp" else "#667085")
        marker = "s" if is_secondary else "o"
        ax.scatter(
            float(row["worker_runtime_seconds_median"]),
            float(row["pooled_oof_pr_auc_for_plot"]),
            s=62,
            marker=marker,
            color=color,
            edgecolor="white",
            linewidth=0.7,
            zorder=3,
        )
        short = short_labels.get(str(row["model_label"]), str(row["model_label"]))
        ax.annotate(
            short,
            (float(row["worker_runtime_seconds_median"]), float(row["pooled_oof_pr_auc_for_plot"])),
            xytext=offsets.get(short, (5, 5)),
            textcoords="offset points",
            fontsize=8,
        )
    ax.set_xscale("log")
    ax.set_xlabel("Mediana zarejestrowanego worker-runtime dla 6 foldów [s] · skala log")
    ax.set_ylabel("Pooled OOF PR-AUC (ensemble lub pojedynczy run deterministyczny)")
    fig.suptitle(
        "Jakość predykcyjna a koszt obliczeniowy",
        x=0.08,
        y=0.985,
        ha="left",
        fontweight="bold",
        fontsize=15,
    )
    fig.text(
        0.08,
        0.935,
        "Porównanie opisowe; wykonania nie stanowią kontrolowanego benchmarku sprzętowego",
        ha="left",
        fontsize=9,
        color="#475467",
    )
    ax.grid(color="#E4E7EC", linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    path_base.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path_base.with_suffix(".png"),
        dpi=220,
        bbox_inches="tight",
        metadata={"Software": "methodology_extension_reporting_v1_0_0"},
    )
    fig.savefig(path_base.with_suffix(".svg"), bbox_inches="tight", metadata={"Date": None})
    plt.close(fig)


def _source_provenance(paths: Iterable[Path]) -> list[dict[str, Any]]:
    unique = sorted({path.resolve() for path in paths})
    return [
        {
            "source_path": _relative(path),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for path in unique
    ]


def _summary_markdown(
    seed_summary: Sequence[Mapping[str, Any]],
    cost_summary: Sequence[Mapping[str, Any]],
    program_cost: Sequence[Mapping[str, Any]],
) -> str:
    xgb = next(row for row in cost_summary if row["family"] == "xgboost" and row["report_role"] == "PRIMARY_FAMILY_REPRESENTATIVE")
    qnn = next(row for row in cost_summary if row["family"] == "qnn")
    qnn_stability = next(row for row in seed_summary if row["family"] == "qnn")
    qnn_total = next(
        row for row in program_cost if row["stage"] == "TOTAL_RECORDED_Q1_Q2_CONFIRMATION_PROGRAM"
    )
    return "\n".join(
        [
            "# Stabilność seedów i koszt obliczeniowy — raport rozszerzony v1.0.0",
            "",
            "Raport powstał wyłącznie z zamrożonych artefaktów development OOF 2015–2020. "
            "Nie przeprowadzono treningu, nie uruchomiono benchmarku i nie otwarto lat chronionych 2021–2024.",
            "",
            "To techniczny arkusz dowodowy, nie tekst pracy. Autor samodzielnie tworzy opis, interpretację i wnioski.",
            "",
            "## Najważniejsze wyniki",
            "",
            f"- QNN: średnia AP między seedami {float(qnn_stability['pooled_oof_pr_auc_seed_mean']):.6f}, "
            f"SD {float(qnn_stability['pooled_oof_pr_auc_seed_sample_sd']):.6f}, zakres "
            f"{float(qnn_stability['pooled_oof_pr_auc_seed_min']):.6f}–{float(qnn_stability['pooled_oof_pr_auc_seed_max']):.6f}; "
            f"ensemble AP {float(qnn_stability['pooled_oof_pr_auc_score_averaged_ensemble']):.6f}.",
            f"- Mediana worker-runtime końcowego QNN dla sześciu foldów: {float(qnn['worker_runtime_hours_median']):.3f} h; "
            f"XGBoost: {float(xgb['worker_runtime_seconds_median']):.3f} s. Opisowy mnożnik: "
            f"{float(qnn['runtime_multiple_vs_xgboost_median']):.1f}×.",
            f"- Pełna zarejestrowana ścieżka QNN Q1/Q2/confirmation: {float(qnn_total['worker_runtime_hours']):.3f} h. "
            "Nie jest to wartość porównywalna z czasem pojedynczego fitu XGBoost.",
            "",
            "## Granice interpretacji",
            "",
            "- Statystyki z trzech seedów są opisowe i nie są przedziałami ufności.",
            "- SD między seedami i SD między foldami czasowymi opisują różne źródła zmienności.",
            "- Ensemble AP policzono po uśrednieniu raw score; nie jest średnią AP z seedów.",
            "- Czasy pochodzą z historycznych wykonań w różnych środowiskach i nie są kontrolowanym benchmarkiem sprzętowym.",
            "- QNN działał na analitycznym symulatorze lightning.qubit, nie na sprzęcie kwantowym.",
            "",
        ]
    )


def generate_report(
    output_dir: Path = DEFAULT_OUTPUT, config_path: Path = DEFAULT_CONFIG
) -> dict[str, Any]:
    freeze = verify_post_coarse_results_freeze()
    _require(freeze.get("status") == "PASS", "Post-coarse source freeze verification failed.")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    section = config.get("methodology_extension_reporting") or {}
    _require(section.get("status") == "REPORTING_ONLY", "Config is not reporting-only.")
    _require(section.get("project_model_fit_permitted") is False, "Model fit is permitted by config.")
    _require(
        section.get("protected_feature_years_permitted") is False,
        "Protected years are permitted by config.",
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    table_dir = output_dir / "tables"
    figure_dir = output_dir / "figures"

    seed_summary, seed_detailed = _build_seed_tables()
    cost_summary, cost_per_seed = _build_cost_tables(seed_summary, seed_detailed)
    program_cost = _build_program_cost_table()
    environments = _runtime_environments()
    disclosures = _disclosures()
    compact_seed = _compact_seed_table(seed_summary)
    compact_cost = _compact_cost_table(cost_summary)

    _write_csv(table_dir / "01_seed_stability_summary.csv", seed_summary)
    _write_csv(table_dir / "02_seed_stability_detailed.csv", seed_detailed)
    _write_csv(table_dir / "03_compute_cost_final_representatives.csv", cost_summary)
    _write_csv(table_dir / "04_compute_cost_per_seed.csv", cost_per_seed)
    _write_csv(table_dir / "05_compute_cost_program_stages.csv", program_cost)
    _write_csv(table_dir / "06_runtime_environments.csv", environments)
    _write_csv(table_dir / "07_methodological_disclosures.csv", disclosures)

    _plot_seed_stability(figure_dir / "01_seed_stability_pr_auc", seed_summary, seed_detailed)
    _plot_runtime(figure_dir / "02_pr_auc_vs_runtime", cost_summary)

    core_sources = [
        config_path,
        POST_ROOT / "final_primary_development_ranking.json",
        POST_ROOT / "confirmation_phase_manifest.json",
        COARSE_ROOT / "classical_mlp_coarse_search_manifest.json",
        POST_ROOT / "runtime_metadata.json",
        POST_ROOT / "qnn_resource_ledger.json",
        POST_ROOT / "qnn_confirmation_resource_ledger.json",
        POST_ROOT / "qnn_resource_smoke.json",
        ROOT / "configs/model_execution_contract_v1_2_1_lightning_amendment.yaml",
    ]
    for row in seed_detailed:
        for key in ("metric_source", "runtime_source"):
            value = row.get(key)
            if isinstance(value, str) and value != "NOT_APPLICABLE":
                core_sources.append(ROOT / value)
    core_sources.extend(sorted((COARSE_ROOT / "coarse_results").glob("*/result_manifest.json")))
    core_sources.extend(
        sorted((POST_ROOT / "candidate_results/refinement").glob("**/candidate_manifest.json"))
    )
    core_sources.extend(
        sorted((POST_ROOT / "candidate_results/coarse").glob("**/candidate_manifest.json"))
    )
    provenance = _source_provenance(core_sources)
    _write_csv(table_dir / "08_source_provenance.csv", provenance)
    _write_csv(table_dir / "09_seed_stability_thesis_compact.csv", compact_seed)
    _write_csv(table_dir / "10_compute_cost_thesis_compact.csv", compact_cost)

    summary_text = _summary_markdown(seed_summary, cost_summary, program_cost)
    (output_dir / "README.md").write_text(summary_text, encoding="utf-8")
    generated_files = sorted(
        path for path in output_dir.rglob("*") if path.is_file() and path.name != "manifest.json"
    )
    manifest = {
        "schema_version": 1,
        "id": "methodology_extension_v1_0_0",
        "status": "PASS",
        "source_freeze_verdict": freeze["verdict"],
        "reporting_only": True,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
        "development_feature_years": list(DEVELOPMENT_YEARS),
        "seed_summary_rows": len(seed_summary),
        "seed_detailed_rows": len(seed_detailed),
        "cost_summary_rows": len(cost_summary),
        "cost_per_seed_rows": len(cost_per_seed),
        "program_cost_rows": len(program_cost),
        "files": [
            {
                "path": _output_manifest_path(path, output_dir),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in generated_files
        ],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    manifest = generate_report(args.output.resolve(), args.config.resolve())
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

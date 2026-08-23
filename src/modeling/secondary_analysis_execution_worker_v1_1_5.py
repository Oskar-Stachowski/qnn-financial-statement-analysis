"""Numeric-worker amendment for economic-group permutation in v1.1.5.

The frozen sample can contain more than one company-year row for one economic
group in a validation year.  Common permutation importance therefore operates
on one deterministic, observed row per economic group: the first row in the
already frozen canonical validation order.  Labels must agree within every
group; no feature aggregation or synthetic row construction is permitted.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from src.modeling import secondary_analysis_execution_worker as base_worker


POLICY_ID = "canonical_first_row_per_economic_group_v1"


def canonical_economic_group_indices(
    cluster_codes: np.ndarray, labels: np.ndarray
) -> np.ndarray:
    """Return first-occurrence indices after validating cluster labels."""
    clusters = np.asarray(cluster_codes, dtype=np.int64).reshape(-1)
    targets = np.asarray(labels, dtype=np.int64).reshape(-1)
    if len(clusters) == 0 or len(clusters) != len(targets):
        raise ValueError("Economic-group arrays are empty or misaligned.")
    if np.any(clusters < 0):
        raise ValueError("Economic-group identity is missing in validation fold.")

    first_indices: list[int] = []
    label_by_cluster: dict[int, int] = {}
    for index, (cluster, label) in enumerate(zip(clusters, targets, strict=True)):
        cluster_id = int(cluster)
        target = int(label)
        if cluster_id not in label_by_cluster:
            label_by_cluster[cluster_id] = target
            first_indices.append(index)
        elif label_by_cluster[cluster_id] != target:
            raise ValueError("Target label differs within an economic group.")
    return np.asarray(first_indices, dtype=np.int64)


def grouped_permutation(
    task: Mapping[str, Any], arrays: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    """Compute deterministic importance on canonical economic-group rows."""
    from sklearn.metrics import average_precision_score

    if task.get("economic_group_duplicate_policy") != POLICY_ID:
        raise ValueError("Unknown economic-group duplicate policy.")

    full_validation = np.asarray(arrays["x_validation_base"], dtype=np.float64)
    full_labels = np.asarray(arrays["y_validation"], dtype=np.int64).reshape(-1)
    clusters = np.asarray(arrays["cluster_codes"], dtype=np.int64).reshape(-1)
    if len(full_validation) != len(full_labels):
        raise ValueError("Validation predictors and labels are misaligned.")
    canonical_indices = canonical_economic_group_indices(clusters, full_labels)
    base_validation = full_validation[canonical_indices]
    labels = full_labels[canonical_indices]

    _models, predictors = base_worker._models_and_predictors(task, arrays)
    model_validation = base_worker._model_matrix(arrays, base_validation)
    baseline_scores = np.mean(
        np.vstack([predict(model_validation) for predict in predictors]), axis=0
    )
    baseline = float(average_precision_score(labels, baseline_scores))
    results: list[dict[str, Any]] = []
    groups = [list(map(int, group)) for group in task["feature_groups"]]
    repetitions = int(task["repetitions"])
    for group_index, columns in enumerate(groups):
        decreases: list[float] = []
        for repetition in range(repetitions):
            rng = np.random.default_rng(
                int(task["permutation_seed"]) + group_index * 100003 + repetition
            )
            group_order = rng.permutation(len(base_validation))
            permuted = base_validation.copy()
            permuted[:, columns] = base_validation[group_order][:, columns]
            model_permuted = base_worker._model_matrix(arrays, permuted)
            scores = np.mean(
                np.vstack([predict(model_permuted) for predict in predictors]), axis=0
            )
            decreases.append(
                baseline - float(average_precision_score(labels, scores))
            )
        results.append(
            {
                "feature_name": str(task["feature_names"][group_index]),
                "decreases": decreases,
                "mean_decrease": float(np.mean(decreases)),
                "sample_sd": float(np.std(decreases, ddof=1)),
            }
        )
    return {
        "status": "COMPLETE",
        "baseline_pr_auc": baseline,
        "validation_rows_original": len(full_labels),
        "validation_rows": len(labels),
        "validation_economic_groups": len(labels),
        "duplicate_rows_dropped": len(full_labels) - len(labels),
        "economic_group_duplicate_policy": POLICY_ID,
        "feature_results": results,
    }


def main() -> None:
    base_worker.INTERPRETATION_ACTIONS["grouped_permutation"] = grouped_permutation
    base_worker.main()


if __name__ == "__main__":
    main()

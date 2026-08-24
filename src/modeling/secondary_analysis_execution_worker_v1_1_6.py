"""TreeSHAP/XGBoost compatibility amendment for secondary execution v1.1.6."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import numpy as np

from src.modeling import secondary_analysis_execution_worker as base_worker
from src.modeling import secondary_analysis_execution_worker_v1_1_5 as v115_worker


TREE_SHAP_POLICY_ID = "numeric_xgboost_interventional_all_canonical_background_v1"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def detailed_tree_shap(
    task: Mapping[str, Any], arrays: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    """Run interventional TreeSHAP without changing the fitted numeric booster."""
    if task.get("family") != "xgboost":
        raise ValueError("TreeSHAP compatibility policy is XGBoost-only.")
    if int(task.get("background_rows_max", -1)) != 512:
        raise ValueError("TreeSHAP background limit changed.")
    if int(task.get("oof_rows_max", -1)) != 500:
        raise ValueError("TreeSHAP evaluation limit changed.")

    import shap

    models, _predictors = base_worker._models_and_predictors(task, arrays)
    train = base_worker._model_matrix(arrays, arrays["x_train_base"])
    validation = base_worker._model_matrix(arrays, arrays["x_validation_base"])
    background = train[: int(task["background_rows_max"])]
    evaluation = validation[: int(task["oof_rows_max"])]
    if len(background) == 0 or len(evaluation) == 0:
        raise ValueError("TreeSHAP background or evaluation sample is empty.")

    per_seed: list[list[float]] = []
    seed_audits: list[dict[str, Any]] = []
    for seed, model in zip(task["seeds"], models, strict=True):
        booster = model.get_booster()
        if booster.feature_types is not None:
            raise ValueError("XGBoost booster contains typed or categorical features.")
        booster_before = booster.save_raw(raw_format="ubj")
        raw_before = np.asarray(
            model.predict(evaluation, output_margin=True), dtype=np.float64
        )

        # XGBoost 3.4 reports enable_categorical=True as estimator metadata even
        # for a purely numeric booster. SHAP 0.52 rejects that metadata before
        # inspecting the booster. Changing it after fit leaves the booster and
        # its predictions byte-for-byte unchanged.
        model.set_params(enable_categorical=False)
        booster_after = booster.save_raw(raw_format="ubj")
        raw_after = np.asarray(
            model.predict(evaluation, output_margin=True), dtype=np.float64
        )
        if booster_before != booster_after or not np.array_equal(raw_before, raw_after):
            raise RuntimeError("TreeSHAP metadata normalization changed the fitted model.")

        masker = shap.maskers.Independent(
            background, max_samples=len(background)
        )
        if len(masker.data) != len(background):
            raise RuntimeError("TreeSHAP masker subsampled canonical background rows.")
        explainer = shap.TreeExplainer(
            model,
            data=masker,
            feature_perturbation="interventional",
            model_output="raw",
        )
        values = np.asarray(explainer.shap_values(evaluation), dtype=np.float64)
        if values.ndim == 3:
            values = values[..., -1]
        if values.shape != evaluation.shape or not np.isfinite(values).all():
            raise RuntimeError("TreeSHAP returned invalid attribution values.")
        expected_value = np.asarray(explainer.expected_value, dtype=np.float64)
        reconstructed = values.sum(axis=1) + expected_value
        additivity_max_abs = float(np.max(np.abs(reconstructed - raw_after)))
        if not np.isfinite(additivity_max_abs) or additivity_max_abs > 1e-4:
            raise RuntimeError("TreeSHAP additivity check failed.")
        per_seed.append(np.mean(np.abs(values), axis=0).tolist())
        seed_audits.append(
            {
                "seed": int(seed),
                "booster_sha256": _sha256_bytes(booster_before),
                "raw_score_sha256": _sha256_bytes(raw_before.tobytes(order="C")),
                "booster_unchanged": True,
                "raw_scores_unchanged": True,
                "additivity_max_abs": additivity_max_abs,
            }
        )
    return {
        "status": "COMPLETE",
        "feature_names": list(task["model_feature_names"]),
        "background_rows": len(background),
        "evaluation_rows": len(evaluation),
        "mean_abs_shap_by_seed": per_seed,
        "mean_abs_shap": np.mean(np.asarray(per_seed), axis=0).tolist(),
        "tree_shap_policy": TREE_SHAP_POLICY_ID,
        "feature_perturbation": "interventional",
        "model_output": "raw",
        "background_masker": "Independent",
        "background_subsampled": False,
        "xgboost_numeric_booster_required": True,
        "estimator_metadata_normalized_after_fit": True,
        "seed_audits": seed_audits,
    }


def main() -> None:
    base_worker.INTERPRETATION_ACTIONS[
        "grouped_permutation"
    ] = v115_worker.grouped_permutation
    base_worker.INTERPRETATION_ACTIONS["detailed_tree_shap"] = detailed_tree_shap
    base_worker.main()


if __name__ == "__main__":
    main()

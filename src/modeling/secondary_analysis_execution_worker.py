"""Numeric-only worker for frozen secondary development analyses.

The worker never opens project CSV files.  It receives already validated numeric
arrays and frozen task identities from the controller.  Ordinary model fits are
delegated to the production worker; this module only adds the preregistered QNN
identity-entangler ablation and interpretation operations.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
from typing import Any, Callable, Mapping, Sequence
import warnings

import numpy as np

from src.modeling import production_worker
from src.modeling.model_execution_contract import canonical_sha256


def _patch_identity_ansatz(task: Mapping[str, Any]) -> None:
    if task.get("selected_ansatz_id") != "ROT_IDENTITY":
        return

    original_shape = production_worker.qnn_parameter_shape

    def parameter_shape(
        ansatz: str, layers: int, qubits: int
    ) -> tuple[int, int, int]:
        if ansatz == "ROT_IDENTITY":
            return layers, qubits, 3
        return original_shape(ansatz, layers, qubits)

    original_apply = production_worker.apply_ansatz

    def apply_ansatz(
        qml: Any, ansatz: str, theta: Any, layer: int, qubits: int
    ) -> None:
        if ansatz == "ROT_IDENTITY":
            for wire in range(qubits):
                qml.Rot(*theta[layer, wire], wires=wire)
            return
        original_apply(qml, ansatz, theta, layer, qubits)

    production_worker.qnn_parameter_shape = parameter_shape
    production_worker.apply_ansatz = apply_ansatz


def run_model_fit(payload: Mapping[str, Any]) -> dict[str, Any]:
    _patch_identity_ansatz(payload["task"])
    return production_worker.run_task(payload)


def _probability_logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probability, dtype=np.float64), 1e-15, 1 - 1e-15)
    return np.log(clipped / (1.0 - clipped))


def _fit_classical(
    *,
    family: str,
    parameters: Mapping[str, Any],
    seed: int,
    stage: str,
    x_train: np.ndarray,
    y_train: np.ndarray,
    sample_weight: np.ndarray,
) -> tuple[Any, Callable[[np.ndarray], np.ndarray]]:
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import SVC

    random.seed(seed)
    np.random.seed(seed % (2**32))
    if family == "fixed_l2_logistic":
        model = LogisticRegression(
            C=float(parameters["C"]), l1_ratio=0.0, dual=False, tol=1e-6,
            fit_intercept=True, class_weight=None, random_state=None,
            solver="lbfgs", max_iter=2000,
        )
    elif family == "elastic_net_logistic":
        model = LogisticRegression(
            C=float(parameters["C"]), l1_ratio=float(parameters["l1_ratio"]),
            dual=False, tol=1e-4, fit_intercept=True, class_weight=None,
            random_state=seed, solver="saga", max_iter=5000,
        )
    elif family == "rbf_svm":
        model = SVC(
            C=float(parameters["C"]), kernel="rbf", gamma=parameters["gamma"],
            shrinking=True, probability=False, tol=1e-3, cache_size=1024,
            class_weight=None, max_iter=100000, random_state=None,
        )
    elif family == "random_forest":
        model = RandomForestClassifier(
            n_estimators=800 if stage == "refinement" else 600,
            criterion=str(parameters["criterion"]),
            max_depth=parameters["max_depth"], min_samples_split=2,
            min_samples_leaf=int(parameters["min_samples_leaf"]),
            max_features=parameters["max_features"], bootstrap=True,
            n_jobs=1, random_state=seed, class_weight=None,
            max_samples=float(parameters["max_samples"]),
        )
    elif family == "hist_gradient_boosting":
        model = HistGradientBoostingClassifier(
            loss="log_loss", learning_rate=float(parameters["learning_rate"]),
            max_iter=int(parameters["max_iter"]),
            max_leaf_nodes=int(parameters["max_leaf_nodes"]), max_depth=None,
            min_samples_leaf=int(parameters["min_samples_leaf"]),
            l2_regularization=float(parameters["l2_regularization"]),
            max_features=float(parameters["max_features"]), max_bins=255,
            early_stopping=False, validation_fraction=None, tol=1e-7,
            random_state=seed, class_weight=None,
        )
    elif family == "xgboost":
        from xgboost import XGBClassifier

        model = XGBClassifier(
            n_estimators=int(parameters["n_estimators"]),
            max_depth=int(parameters["max_depth"]),
            learning_rate=float(parameters["learning_rate"]),
            min_child_weight=float(parameters["min_child_weight"]),
            gamma=float(parameters["gamma"]), subsample=float(parameters["subsample"]),
            colsample_bytree=float(parameters["colsample_bytree"]),
            reg_alpha=float(parameters["reg_alpha"]),
            reg_lambda=float(parameters["reg_lambda"]), objective="binary:logistic",
            tree_method="hist", eval_metric="logloss", random_state=seed,
            n_jobs=1, scale_pos_weight=1.0, verbosity=0,
        )
    else:
        raise ValueError(f"Unsupported interpretation family: {family}")
    model.fit(x_train, y_train, sample_weight=sample_weight)

    def predict(values: np.ndarray) -> np.ndarray:
        if family in {
            "fixed_l2_logistic", "elastic_net_logistic", "rbf_svm",
            "hist_gradient_boosting",
        }:
            scores = model.decision_function(values)
        elif family == "xgboost":
            scores = model.predict(values, output_margin=True)
        else:
            classes = list(model.classes_)
            scores = _probability_logit(
                model.predict_proba(values)[:, classes.index(1)]
            )
        return np.asarray(scores, dtype=np.float64).reshape(-1)

    return model, predict


def _model_matrix(arrays: Mapping[str, np.ndarray], base: np.ndarray) -> np.ndarray:
    if "pca_components" not in arrays:
        return np.asarray(base, dtype=np.float64)
    centered = np.asarray(base, dtype=np.float64) - arrays["pca_mean"]
    components = centered @ arrays["pca_components"].T
    scaled = (components - arrays["pca_scaler_mean"]) / arrays["pca_scaler_scale"]
    return float(arrays["angle_multiplier"][0]) * np.clip(scaled, -3.0, 3.0)


def _load_torch_models(
    task: Mapping[str, Any], arrays: Mapping[str, np.ndarray]
) -> tuple[list[Any], Callable[[Any, np.ndarray], np.ndarray], Any]:
    import torch

    torch = production_worker.torch_configuration()
    family = str(task["family"])
    models: list[Any] = []
    paths = [Path(value) for value in task["checkpoint_paths"]]
    expected_hashes = list(task["checkpoint_task_identity_sha256"])
    seeds = [int(value) for value in task["seeds"]]
    if not (len(paths) == len(expected_hashes) == len(seeds)):
        raise ValueError("Checkpoint/seed cardinality mismatch.")
    input_dim = _model_matrix(arrays, arrays["x_train_base"]).shape[1]
    for path, expected, seed in zip(paths, expected_hashes, seeds, strict=True):
        checkpoint = torch.load(path, map_location="cpu", weights_only=False)
        if checkpoint.get("task_identity_sha256") != expected:
            raise RuntimeError("CHECKPOINT_IDENTITY_MISMATCH")
        if family == "pytorch_mlp":
            model = production_worker.build_mlp(
                torch, input_dim, task["parameters"], seed
            )
        elif family == "qnn":
            _patch_identity_ansatz(task)
            model = production_worker.build_qnn(
                torch, task["parameters"], str(task["selected_ansatz_id"]), seed,
                device_name=str(task["device_name"]),
            )
        else:
            raise ValueError(f"Unsupported torch family: {family}")
        model.load_state_dict(checkpoint["model_state"])
        model.eval()
        models.append(model)

    def predict(model: Any, values: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            tensor = torch.as_tensor(values, dtype=torch.float64)
            scores = model(tensor)
            if scores.ndim == 2 and scores.shape[-1] == 1:
                scores = scores.squeeze(-1)
        return scores.detach().cpu().numpy().astype(np.float64).reshape(-1)

    return models, predict, torch


def _models_and_predictors(
    task: Mapping[str, Any], arrays: Mapping[str, np.ndarray]
) -> tuple[list[Any], list[Callable[[np.ndarray], np.ndarray]]]:
    family = str(task["family"])
    seeds = [int(value) for value in task["seeds"]]
    if family in {"pytorch_mlp", "qnn"}:
        models, predict, _torch = _load_torch_models(task, arrays)
        return models, [lambda values, model=model: predict(model, values) for model in models]
    x_train = _model_matrix(arrays, arrays["x_train_base"])
    models: list[Any] = []
    predictors: list[Callable[[np.ndarray], np.ndarray]] = []
    for seed in seeds:
        model, predict = _fit_classical(
            family=family, parameters=task["parameters"], seed=seed,
            stage=str(task["source_stage"]), x_train=x_train,
            y_train=arrays["y_train"].astype(np.int64),
            sample_weight=arrays["sample_weight"].astype(np.float64),
        )
        models.append(model)
        predictors.append(predict)
    return models, predictors


def grouped_permutation(
    task: Mapping[str, Any], arrays: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    from sklearn.metrics import average_precision_score

    _models, predictors = _models_and_predictors(task, arrays)
    base_validation = np.asarray(arrays["x_validation_base"], dtype=np.float64)
    labels = arrays["y_validation"].astype(np.int64)
    clusters = arrays["cluster_codes"].astype(np.int64)
    if len(np.unique(clusters)) != len(clusters):
        raise ValueError("Economic group is not unique within validation fold.")
    model_validation = _model_matrix(arrays, base_validation)
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
            row_order = rng.permutation(len(base_validation))
            permuted = base_validation.copy()
            permuted[:, columns] = base_validation[row_order][:, columns]
            model_permuted = _model_matrix(arrays, permuted)
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
        "validation_rows": len(labels),
        "feature_results": results,
    }


def detailed_linear(
    task: Mapping[str, Any], arrays: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    models, _predictors = _models_and_predictors(task, arrays)
    coefficient_rows = []
    for seed, model in zip(task["seeds"], models, strict=True):
        coefficients = np.asarray(model.coef_, dtype=np.float64).reshape(-1)
        coefficient_rows.append(
            {
                "seed": int(seed),
                "coefficients": coefficients.tolist(),
                "odds_ratios": np.exp(coefficients).tolist(),
            }
        )
    matrix = np.asarray(
        [row["coefficients"] for row in coefficient_rows], dtype=np.float64
    )
    return {
        "status": "COMPLETE",
        "feature_names": list(task["model_feature_names"]),
        "seed_results": coefficient_rows,
        "mean_coefficient": matrix.mean(axis=0).tolist(),
        "sign_stability": np.maximum(
            np.mean(matrix > 0, axis=0), np.mean(matrix < 0, axis=0)
        ).tolist(),
    }


def detailed_tree_shap(
    task: Mapping[str, Any], arrays: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    import shap

    models, _predictors = _models_and_predictors(task, arrays)
    train = _model_matrix(arrays, arrays["x_train_base"])
    validation = _model_matrix(arrays, arrays["x_validation_base"])
    background = train[: int(task["background_rows_max"])]
    evaluation = validation[: int(task["oof_rows_max"])]
    per_seed: list[list[float]] = []
    for model in models:
        explainer = shap.TreeExplainer(
            model, data=background, feature_perturbation="interventional",
            model_output="raw",
        )
        values = np.asarray(explainer.shap_values(evaluation), dtype=np.float64)
        if values.ndim == 3:
            values = values[..., -1]
        per_seed.append(np.mean(np.abs(values), axis=0).tolist())
    return {
        "status": "COMPLETE",
        "feature_names": list(task["model_feature_names"]),
        "background_rows": len(background),
        "evaluation_rows": len(evaluation),
        "mean_abs_shap_by_seed": per_seed,
        "mean_abs_shap": np.mean(np.asarray(per_seed), axis=0).tolist(),
    }


def detailed_mlp_ig(
    task: Mapping[str, Any], arrays: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    from captum.attr import IntegratedGradients

    models, _predictors, torch = _load_torch_models(task, arrays)
    train = _model_matrix(arrays, arrays["x_train_base"])
    validation = _model_matrix(arrays, arrays["x_validation_base"])
    evaluation = validation[: int(task["oof_rows_max"])]
    baseline = np.mean(train, axis=0, keepdims=True)
    per_seed: list[list[float]] = []
    for model in models:
        ig = IntegratedGradients(model)
        inputs = torch.as_tensor(evaluation, dtype=torch.float64)
        baselines = torch.as_tensor(
            np.repeat(baseline, len(evaluation), axis=0), dtype=torch.float64
        )
        attributes = ig.attribute(
            inputs, baselines=baselines, n_steps=int(task["steps"])
        )
        per_seed.append(
            attributes.detach().abs().mean(dim=0).cpu().numpy().tolist()
        )
    return {
        "status": "COMPLETE",
        "feature_names": list(task["model_feature_names"]),
        "evaluation_rows": len(evaluation),
        "mean_abs_integrated_gradients_by_seed": per_seed,
        "mean_abs_integrated_gradients": np.mean(
            np.asarray(per_seed), axis=0
        ).tolist(),
    }


def detailed_qnn_sensitivity(
    task: Mapping[str, Any], arrays: Mapping[str, np.ndarray]
) -> dict[str, Any]:
    models, _predictors, torch = _load_torch_models(task, arrays)
    validation = _model_matrix(arrays, arrays["x_validation_base"])
    evaluation = validation[: int(task["oof_rows_max"])]
    per_seed: list[list[float]] = []
    for model in models:
        inputs = torch.as_tensor(evaluation, dtype=torch.float64).clone().requires_grad_(True)
        output = model(inputs)
        gradient = torch.autograd.grad(output.sum(), inputs)[0]
        per_seed.append(gradient.detach().abs().mean(dim=0).cpu().numpy().tolist())
    return {
        "status": "COMPLETE",
        "encoded_feature_names": list(task["model_feature_names"]),
        "evaluation_rows": len(evaluation),
        "mean_abs_encoded_sensitivity_by_seed": per_seed,
        "mean_abs_encoded_sensitivity": np.mean(np.asarray(per_seed), axis=0).tolist(),
        "pca_components": arrays["pca_components"].tolist(),
        "pca_explained_variance": arrays["pca_explained_variance"].tolist(),
    }


INTERPRETATION_ACTIONS = {
    "grouped_permutation": grouped_permutation,
    "detailed_linear": detailed_linear,
    "detailed_tree_shap": detailed_tree_shap,
    "detailed_mlp_ig": detailed_mlp_ig,
    "detailed_qnn_sensitivity": detailed_qnn_sensitivity,
}


def run_interpretation(payload: Mapping[str, Any]) -> dict[str, Any]:
    task = payload["interpretation_task"]
    if canonical_sha256(task) != payload["interpretation_task_sha256"]:
        raise ValueError("Interpretation task identity mismatch.")
    with np.load(Path(payload["arrays_path"]), allow_pickle=False) as loaded:
        arrays = {name: np.asarray(loaded[name]) for name in loaded.files}
    action = str(task["action"])
    if action not in INTERPRETATION_ACTIONS:
        raise ValueError(f"Unknown interpretation action: {action}")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = INTERPRETATION_ACTIONS[action](task, arrays)
    result.update(
        {
            "schema_version": 1,
            "interpretation_task_sha256": payload["interpretation_task_sha256"],
            "project_data_loaded_by_worker": False,
            "protected_feature_years_opened": False,
        }
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.task.read_text(encoding="utf-8"))
    try:
        if payload.get("worker_mode") == "interpretation":
            result = run_interpretation(payload)
        else:
            result = run_model_fit(payload)
    except Exception as error:
        identity = payload.get("task_identity_sha256") or payload.get(
            "interpretation_task_sha256"
        )
        result = {
            "schema_version": 1,
            "task_identity_sha256": identity,
            "interpretation_task_sha256": identity,
            "status": "EXCEPTION_INVALID",
            "failure_code": "DETERMINISTIC_LIBRARY_EXCEPTION",
            "exception_type": type(error).__name__,
            "project_data_loaded_by_worker": False,
            "protected_feature_years_opened": False,
        }
    production_worker.atomic_json(Path(payload["result_path"]), result)
    raise SystemExit(0)


if __name__ == "__main__":
    main()

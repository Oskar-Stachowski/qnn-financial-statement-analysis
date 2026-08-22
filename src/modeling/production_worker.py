"""Numeric-only estimator worker for :mod:`production_runner`.

The worker has no project-data loader.  Its entire input is a frozen task JSON
and an NPZ containing one fold's already-preprocessed numeric matrices.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import random
import tempfile
import time
from typing import Any, Mapping
import warnings

import numpy as np

from src.modeling.environment_audit import environment_report
from src.modeling.model_execution_contract import canonical_sha256, file_sha256


# Every classical estimator is frozen to one CPU.  Declaring the same bound to
# loky prevents its macOS physical-core probe from emitting a non-model warning
# that the execution contract would otherwise (correctly) treat as terminal.
os.environ["LOKY_MAX_CPU_COUNT"] = "1"


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def probability_logit(probability: np.ndarray) -> np.ndarray:
    clipped = np.clip(np.asarray(probability, dtype=np.float64), 1e-7, 1.0 - 1e-7)
    return np.log(clipped / (1.0 - clipped))


def validate_arrays(arrays: Mapping[str, np.ndarray]) -> None:
    required = {"x_train", "y_train", "x_validation", "sample_weight"}
    if set(arrays) != required:
        raise ValueError("Worker NPZ key set mismatch.")
    x_train = np.asarray(arrays["x_train"])
    x_validation = np.asarray(arrays["x_validation"])
    y_train = np.asarray(arrays["y_train"])
    sample_weight = np.asarray(arrays["sample_weight"])
    if x_train.ndim != 2 or x_validation.ndim != 2:
        raise ValueError("Worker matrices must be two-dimensional.")
    if x_train.shape[1] != x_validation.shape[1]:
        raise ValueError("Train/validation predictor dimensions differ.")
    if y_train.shape != (len(x_train),) or sample_weight.shape != (len(x_train),):
        raise ValueError("Worker train vector shape mismatch.")
    if not all(np.isfinite(value).all() for value in (x_train, x_validation, sample_weight)):
        raise FloatingPointError("NAN_OR_INF_INPUT")
    if set(np.asarray(y_train, dtype=int)) - {0, 1}:
        raise ValueError("Worker labels are not binary.")


def classical_fit_predict(task: Mapping[str, Any], arrays: Mapping[str, np.ndarray]) -> np.ndarray:
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import SVC

    family = str(task["family"])
    parameters = dict(task["parameters"])
    seed = int(task["training_seed"])
    random.seed(seed)
    np.random.seed(seed % (2**32))
    x_train = np.asarray(arrays["x_train"], dtype=np.float64)
    y_train = np.asarray(arrays["y_train"], dtype=np.int64)
    x_validation = np.asarray(arrays["x_validation"], dtype=np.float64)
    sample_weight = np.asarray(arrays["sample_weight"], dtype=np.float64)
    if family == "dummy_prior":
        prior = min(max(float(np.mean(y_train)), 1e-7), 1.0 - 1e-7)
        return np.full(len(x_validation), math.log(prior / (1.0 - prior)))
    if family == "fixed_l2_logistic":
        estimator = LogisticRegression(
            C=float(parameters["C"]),
            l1_ratio=0.0,
            dual=False,
            tol=1e-6,
            fit_intercept=True,
            intercept_scaling=1,
            class_weight=None,
            random_state=None,
            solver="lbfgs",
            max_iter=2000,
            verbose=0,
            warm_start=False,
        )
    elif family == "elastic_net_logistic":
        estimator = LogisticRegression(
            C=float(parameters["C"]),
            l1_ratio=float(parameters["l1_ratio"]),
            dual=False,
            tol=1e-4,
            fit_intercept=True,
            intercept_scaling=1,
            class_weight=None,
            random_state=seed,
            solver="saga",
            max_iter=5000,
            verbose=0,
            warm_start=False,
        )
    elif family == "rbf_svm":
        estimator = SVC(
            C=float(parameters["C"]),
            kernel="rbf",
            degree=3,
            gamma=parameters["gamma"],
            coef0=0.0,
            shrinking=True,
            probability=False,
            tol=1e-3,
            cache_size=1024,
            class_weight=None,
            verbose=False,
            max_iter=100000,
            decision_function_shape="ovr",
            break_ties=False,
            random_state=None,
        )
    elif family == "random_forest":
        estimator = RandomForestClassifier(
            n_estimators=800 if task["stage"] == "refinement" else 600,
            criterion=str(parameters["criterion"]),
            max_depth=parameters["max_depth"],
            min_samples_split=2,
            min_samples_leaf=int(parameters["min_samples_leaf"]),
            min_weight_fraction_leaf=0.0,
            max_features=parameters["max_features"],
            max_leaf_nodes=None,
            min_impurity_decrease=0.0,
            bootstrap=True,
            oob_score=False,
            n_jobs=1,
            random_state=seed,
            verbose=0,
            warm_start=False,
            class_weight=None,
            ccp_alpha=0.0,
            max_samples=float(parameters["max_samples"]),
            monotonic_cst=None,
        )
    elif family == "hist_gradient_boosting":
        estimator = HistGradientBoostingClassifier(
            loss="log_loss",
            learning_rate=float(parameters["learning_rate"]),
            max_iter=int(parameters["max_iter"]),
            max_leaf_nodes=int(parameters["max_leaf_nodes"]),
            max_depth=None,
            min_samples_leaf=int(parameters["min_samples_leaf"]),
            l2_regularization=float(parameters["l2_regularization"]),
            max_features=float(parameters["max_features"]),
            max_bins=255,
            categorical_features=None,
            monotonic_cst=None,
            interaction_cst=None,
            warm_start=False,
            early_stopping=False,
            scoring="loss",
            validation_fraction=None,
            n_iter_no_change=10,
            tol=1e-7,
            verbose=0,
            random_state=seed,
            class_weight=None,
        )
    elif family == "xgboost":
        from xgboost import XGBClassifier

        estimator = XGBClassifier(
            n_estimators=int(parameters["n_estimators"]),
            max_depth=int(parameters["max_depth"]),
            learning_rate=float(parameters["learning_rate"]),
            min_child_weight=float(parameters["min_child_weight"]),
            gamma=float(parameters["gamma"]),
            subsample=float(parameters["subsample"]),
            colsample_bytree=float(parameters["colsample_bytree"]),
            reg_alpha=float(parameters["reg_alpha"]),
            reg_lambda=float(parameters["reg_lambda"]),
            objective="binary:logistic",
            tree_method="hist",
            eval_metric="logloss",
            random_state=seed,
            n_jobs=1,
            scale_pos_weight=1.0,
            verbosity=0,
        )
    else:
        raise ValueError(f"Unsupported classical family: {family}")
    estimator.fit(x_train, y_train, sample_weight=sample_weight)
    if family in {
        "fixed_l2_logistic",
        "elastic_net_logistic",
        "rbf_svm",
        "hist_gradient_boosting",
    }:
        score = estimator.decision_function(x_validation)
    elif family == "xgboost":
        score = estimator.predict(x_validation, output_margin=True)
    else:
        classes = list(estimator.classes_)
        if 1 not in classes:
            raise ValueError("Positive class is absent from estimator.classes_.")
        score = probability_logit(estimator.predict_proba(x_validation)[:, classes.index(1)])
    return np.asarray(score, dtype=np.float64).reshape(-1)


def torch_configuration() -> Any:
    import torch

    torch.set_default_dtype(torch.float64)
    torch.set_num_threads(1)
    if torch.get_num_interop_threads() != 1:
        torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True
    return torch


def build_mlp(torch: Any, input_dim: int, parameters: Mapping[str, Any], seed: int) -> Any:
    torch.manual_seed(seed)
    activation = str(parameters["activation"])
    widths = [input_dim, *[int(value) for value in parameters["hidden_layer_sizes"]], 1]
    layers: list[Any] = []
    for index, (left, right) in enumerate(zip(widths[:-1], widths[1:], strict=True)):
        layer = torch.nn.Linear(left, right, bias=True, dtype=torch.float64)
        gain = torch.nn.init.calculate_gain(activation) if index < len(widths) - 2 else 1.0
        torch.nn.init.xavier_uniform_(layer.weight, gain=gain)
        torch.nn.init.zeros_(layer.bias)
        layers.append(layer)
        if index < len(widths) - 2:
            layers.append(torch.nn.ReLU() if activation == "relu" else torch.nn.Tanh())
    return torch.nn.Sequential(*layers)


def qnn_parameter_shape(ansatz: str, layers: int, qubits: int) -> tuple[int, int, int]:
    return layers, qubits, 3 if ansatz == "ROT_CNOT_RING" else 2


def apply_ansatz(qml: Any, ansatz: str, theta: Any, layer: int, qubits: int) -> None:
    if ansatz == "ROT_CNOT_RING":
        for wire in range(qubits):
            qml.Rot(*theta[layer, wire], wires=wire)
        for control in range(qubits):
            qml.CNOT(wires=[control, (control + 1) % qubits])
    elif ansatz == "RY_RZ_CZ_BRICKWORK":
        for wire in range(qubits):
            qml.RY(theta[layer, wire, 0], wires=wire)
            qml.RZ(theta[layer, wire, 1], wires=wire)
        offset = layer % 2
        for start in range(offset, qubits, 2):
            qml.CZ(wires=[start, (start + 1) % qubits])
    elif ansatz == "RY_CRX_RING":
        for wire in range(qubits):
            qml.RY(theta[layer, wire, 0], wires=wire)
        for control in range(qubits):
            qml.CRX(theta[layer, control, 1], wires=[control, (control + 1) % qubits])
    else:
        raise ValueError(f"Unknown ansatz: {ansatz}")


def build_qnn(
    torch: Any,
    parameters: Mapping[str, Any],
    ansatz: str,
    seed: int,
    *,
    device_name: str,
) -> Any:
    import pennylane as qml

    qubits = int(parameters["qubits_pca"])
    layers = int(parameters["layers"])

    class QNN(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            generator = torch.Generator(device="cpu").manual_seed(seed)
            theta = torch.empty(
                qnn_parameter_shape(ansatz, layers, qubits), dtype=torch.float64
            )
            theta.uniform_(-0.1, 0.1, generator=generator)
            self.theta = torch.nn.Parameter(theta)
            self.head = torch.nn.Linear(qubits, 1, bias=True, dtype=torch.float64)
            torch.nn.init.xavier_uniform_(self.head.weight, gain=1.0, generator=generator)
            torch.nn.init.zeros_(self.head.bias)
            device = qml.device(device_name, wires=qubits, shots=None)

            @qml.qnode(device, interface="torch", diff_method="adjoint")
            def circuit(inputs: Any, trainable: Any) -> list[Any]:
                for wire in range(qubits):
                    qml.RY(inputs[..., wire], wires=wire)
                for layer in range(layers):
                    apply_ansatz(qml, ansatz, trainable, layer, qubits)
                return [qml.expval(qml.PauliZ(wire)) for wire in range(qubits)]

            self.circuit = circuit

        def forward(self, inputs: Any) -> Any:
            expectations = torch.stack(self.circuit(inputs, self.theta), dim=-1)
            return self.head(expectations).squeeze(-1)

    return QNN()


def atomic_torch_checkpoint(torch: Any, path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save(dict(state), temporary)
    os.replace(temporary, path)


def torch_fit_predict(
    task: Mapping[str, Any],
    arrays: Mapping[str, np.ndarray],
    *,
    checkpoint_path: Path,
    resume: bool,
    task_identity_sha256: str,
) -> np.ndarray:
    torch = torch_configuration()
    family = str(task["family"])
    parameters = dict(task["parameters"])
    seed = int(task["training_seed"])
    random.seed(seed)
    np.random.seed(seed % (2**32))
    x_train = torch.as_tensor(np.asarray(arrays["x_train"]), dtype=torch.float64)
    y_train = torch.as_tensor(np.asarray(arrays["y_train"]), dtype=torch.float64)
    x_validation = torch.as_tensor(
        np.asarray(arrays["x_validation"]), dtype=torch.float64
    )
    if family == "pytorch_mlp":
        model = build_mlp(torch, x_train.shape[1], parameters, seed)
        epochs = int(parameters["epochs"])
    elif family == "qnn":
        ansatz = str(task["selected_ansatz_id"])
        device_identity = task["checkpoint_identity"]["device_identity"]
        if not isinstance(device_identity, Mapping):
            raise ValueError("QNN device identity must be a mapping.")
        device_name = str(device_identity["name"])
        model = build_qnn(
            torch,
            parameters,
            ansatz,
            seed,
            device_name=device_name,
        )
        epochs = int(parameters["epochs"])
    else:
        raise ValueError(f"Unsupported torch family: {family}")
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=float(parameters["learning_rate"]),
        betas=(0.9, 0.999),
        eps=1e-8,
        weight_decay=float(parameters["weight_decay"]),
        amsgrad=False,
        foreach=False,
        fused=False,
    )
    labels = np.asarray(arrays["y_train"], dtype=int)
    negative = int(np.sum(labels == 0))
    positive = int(np.sum(labels == 1))
    positive_weight = (
        math.sqrt(negative / positive) if parameters.get("imbalance") == "sqrt" else 1.0
    )
    loss_function = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([positive_weight], dtype=torch.float64), reduction="mean"
    )
    batch_generator = torch.Generator(device="cpu").manual_seed(
        seed * 10000 + int(task["validation_feature_year"])
    )
    first_epoch = 0
    cumulative_wall_seconds = 0.0
    if resume:
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        if checkpoint.get("task_identity_sha256") != task_identity_sha256:
            raise RuntimeError("CHECKPOINT_IDENTITY_MISMATCH")
        model.load_state_dict(checkpoint["model_state"])
        optimizer.load_state_dict(checkpoint["optimizer_state"])
        first_epoch = int(checkpoint["completed_epoch"])
        torch.set_rng_state(checkpoint["rng_states"]["torch_cpu"])
        batch_generator.set_state(checkpoint["rng_states"]["batch_generator"])
        random.setstate(checkpoint["rng_states"]["python_random"])
        np.random.set_state(checkpoint["rng_states"]["numpy_random"])
        cumulative_wall_seconds = float(checkpoint["cumulative_wall_seconds"])
    started = time.monotonic()
    batch_size = int(parameters["batch_size"])
    for epoch in range(first_epoch, epochs):
        order = torch.randperm(len(x_train), generator=batch_generator)
        model.train()
        for start in range(0, len(x_train), batch_size):
            indices = order[start : start + batch_size]
            optimizer.zero_grad(set_to_none=True)
            logits = model(x_train[indices])
            if logits.ndim == 2 and logits.shape[-1] == 1:
                logits = logits.squeeze(-1)
            loss = loss_function(logits, y_train[indices])
            if not torch.isfinite(loss):
                raise FloatingPointError("NAN_OR_INF_PARAMETER")
            loss.backward()
            if any(
                parameter.grad is None or not torch.isfinite(parameter.grad).all()
                for parameter in model.parameters()
            ):
                raise FloatingPointError("NAN_OR_INF_PARAMETER")
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            if any(not torch.isfinite(parameter).all() for parameter in model.parameters()):
                raise FloatingPointError("NAN_OR_INF_PARAMETER")
        completed_epoch = epoch + 1
        if completed_epoch % 5 == 0:
            atomic_torch_checkpoint(
                torch,
                checkpoint_path,
                {
                    "task_identity_sha256": task_identity_sha256,
                    "checkpoint_identity": task["checkpoint_identity"],
                    "model_state": model.state_dict(),
                    "optimizer_state": optimizer.state_dict(),
                    "completed_epoch": completed_epoch,
                    "rng_states": {
                        "torch_cpu": torch.get_rng_state(),
                        "batch_generator": batch_generator.get_state(),
                        "python_random": random.getstate(),
                        "numpy_random": np.random.get_state(),
                    },
                    "cumulative_wall_seconds": cumulative_wall_seconds
                    + time.monotonic()
                    - started,
                },
            )
    model.eval()
    with torch.no_grad():
        scores = model(x_validation)
        if scores.ndim == 2 and scores.shape[-1] == 1:
            scores = scores.squeeze(-1)
    return scores.detach().cpu().numpy().astype(np.float64).reshape(-1)


def run_task(payload: Mapping[str, Any]) -> dict[str, Any]:
    task = payload["task"]
    identity_sha = str(payload["task_identity_sha256"])
    if canonical_sha256(task) != identity_sha:
        raise ValueError("Task JSON identity hash mismatch.")
    role = str(task["software_environment_role"])
    contract_path = Path(str(payload["contract_path"]))
    environment = environment_report(
        role,
        smoke_imports=False,
        contract_path=contract_path,
    )
    if environment["status"] != "READY":
        return {
            "task_identity_sha256": identity_sha,
            "status": "EXCEPTION_INVALID",
            "failure_code": "SOFTWARE_ENVIRONMENT_MISMATCH",
            "software_environment_sha256": environment[
                "software_environment_sha256"
            ],
            "device_identity": task["checkpoint_identity"]["device_identity"],
        }
    if environment["software_environment_sha256"] != task["checkpoint_identity"][
        "software_environment_sha256"
    ]:
        raise ValueError("Runtime environment hash differs from checkpoint identity.")
    arrays_file = np.load(Path(payload["arrays_path"]), allow_pickle=False)
    arrays = {name: arrays_file[name] for name in arrays_file.files}
    try:
        validate_arrays(arrays)
    except FloatingPointError as error:
        return {
            "task_identity_sha256": identity_sha,
            "status": "NUMERICAL_INVALID",
            "failure_code": str(error),
            "software_environment_sha256": environment[
                "software_environment_sha256"
            ],
            "device_identity": task["checkpoint_identity"]["device_identity"],
        }
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            if task["family"] in {"pytorch_mlp", "qnn"}:
                scores = torch_fit_predict(
                    task,
                    arrays,
                    checkpoint_path=Path(payload["checkpoint_path"]),
                    resume=bool(payload["resume"]),
                    task_identity_sha256=identity_sha,
                )
            else:
                scores = classical_fit_predict(task, arrays)
        except FloatingPointError as error:
            return {
                "task_identity_sha256": identity_sha,
                "status": "NUMERICAL_INVALID",
                "failure_code": str(error),
                "software_environment_sha256": environment[
                    "software_environment_sha256"
                ],
                "device_identity": task["checkpoint_identity"]["device_identity"],
            }
        except RuntimeError as error:
            if str(error) == "CHECKPOINT_IDENTITY_MISMATCH":
                status, code = "CHECKPOINT_INVALID", "CHECKPOINT_IDENTITY_MISMATCH"
            else:
                status, code = "EXCEPTION_INVALID", "DETERMINISTIC_LIBRARY_EXCEPTION"
            return {
                "task_identity_sha256": identity_sha,
                "status": status,
                "failure_code": code,
                "exception_type": type(error).__name__,
                "software_environment_sha256": environment[
                    "software_environment_sha256"
                ],
                "device_identity": task["checkpoint_identity"]["device_identity"],
            }
        except Exception as error:
            return {
                "task_identity_sha256": identity_sha,
                "status": "EXCEPTION_INVALID",
                "failure_code": "DETERMINISTIC_LIBRARY_EXCEPTION",
                "exception_type": type(error).__name__,
                "software_environment_sha256": environment[
                    "software_environment_sha256"
                ],
                "device_identity": task["checkpoint_identity"]["device_identity"],
            }
    if caught:
        from sklearn.exceptions import ConvergenceWarning

        if any(issubclass(item.category, ConvergenceWarning) for item in caught):
            status, code = "CONVERGENCE_INVALID", "CONVERGENCE_WARNING"
        elif any(issubclass(item.category, RuntimeWarning) for item in caught):
            status, code = "NUMERICAL_INVALID", "NUMERICAL_RUNTIME_WARNING"
        else:
            status, code = "EXCEPTION_INVALID", "UNEXPECTED_WARNING"
        return {
            "task_identity_sha256": identity_sha,
            "status": status,
            "failure_code": code,
            "warning_types": sorted({item.category.__name__ for item in caught}),
            "software_environment_sha256": environment[
                "software_environment_sha256"
            ],
            "device_identity": task["checkpoint_identity"]["device_identity"],
        }
    scores = np.asarray(scores, dtype=np.float64).reshape(-1)
    if scores.shape != (len(arrays["x_validation"]),) or not np.isfinite(scores).all():
        return {
            "task_identity_sha256": identity_sha,
            "status": "NUMERICAL_INVALID",
            "failure_code": "NAN_OR_INF_RAW_SCORE",
            "software_environment_sha256": environment[
                "software_environment_sha256"
            ],
            "device_identity": task["checkpoint_identity"]["device_identity"],
        }
    score_path = Path(payload["raw_scores_path"])
    score_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(score_path, scores, allow_pickle=False)
    return {
        "task_identity_sha256": identity_sha,
        "status": "COMPLETE",
        "failure_code": None,
        "raw_scores_file_sha256": file_sha256(score_path),
        "software_environment_sha256": environment["software_environment_sha256"],
        "device_identity": task["checkpoint_identity"]["device_identity"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.task.read_text(encoding="utf-8"))
    try:
        result = run_task(payload)
    except Exception as error:  # fail-closed worker envelope
        result = {
            "task_identity_sha256": payload.get("task_identity_sha256"),
            "status": "EXCEPTION_INVALID",
            "failure_code": "DETERMINISTIC_LIBRARY_EXCEPTION",
            "exception_type": type(error).__name__,
        }
    atomic_json(Path(payload["result_path"]), result)
    raise SystemExit(0)


if __name__ == "__main__":
    main()

"""Synthetic-only smoke tests for the model-stage freeze gate.

No project dataset is imported or read.  The script validates pinned imports,
constructor/score APIs, deterministic PyTorch behavior, QNN circuits, Captum
Integrated Gradients, and checkpoint round trips on generated arrays only.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import resource
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

for variable in (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
):
    os.environ[variable] = "1"


def distribution_versions(names: list[str]) -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in names}


def sqrt_sample_weights(y: Any) -> tuple[Any, float]:
    import numpy as np

    labels = np.asarray(y, dtype=int)
    negative = int((labels == 0).sum())
    positive = int((labels == 1).sum())
    if negative == 0 or positive == 0:
        raise ValueError("Synthetic class-weight smoke requires both classes.")
    positive_weight = math.sqrt(negative / positive)
    weights = np.where(labels == 1, positive_weight, 1.0)
    return weights, positive_weight


def probability_logit(probability: Any) -> Any:
    import numpy as np

    clipped = np.clip(np.asarray(probability, dtype=float), 1e-7, 1.0 - 1e-7)
    return np.log(clipped / (1.0 - clipped))


def peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def classical_smoke() -> dict[str, Any]:
    started = time.perf_counter()
    import numpy as np
    from sklearn.dummy import DummyClassifier
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import SVC
    from xgboost import XGBClassifier

    rng = np.random.default_rng(20260818)
    x = rng.normal(size=(96, 8))
    y = np.array([0] * 72 + [1] * 24, dtype=int)
    permutation = rng.permutation(len(y))
    x, y = x[permutation], y[permutation]
    weights, positive_weight = sqrt_sample_weights(y)

    models = {
        "fixed_l2_logistic": LogisticRegression(
            penalty="l2", C=1.0, l1_ratio=0.0, dual=False, tol=1e-6,
            fit_intercept=True, intercept_scaling=1, class_weight=None,
            random_state=None, solver="lbfgs", max_iter=2000, verbose=0,
            warm_start=False, n_jobs=1,
        ),
        "elastic_net_logistic": LogisticRegression(
            penalty="elasticnet", C=1.0, l1_ratio=0.5, dual=False, tol=1e-4,
            fit_intercept=True, intercept_scaling=1, class_weight=None,
            random_state=20260818, solver="saga", max_iter=5000, verbose=0,
            warm_start=False, n_jobs=1,
        ),
        "rbf_svm": SVC(
            C=1.0, kernel="rbf", degree=3, gamma="scale", coef0=0.0,
            shrinking=True, probability=False, tol=1e-3, cache_size=1024,
            class_weight=None, verbose=False, max_iter=100000,
            decision_function_shape="ovr", break_ties=False, random_state=None,
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            loss="log_loss", learning_rate=0.1, max_iter=5,
            max_leaf_nodes=7, max_depth=None, min_samples_leaf=5,
            l2_regularization=0.0, max_features=1.0, max_bins=255,
            categorical_features=None, monotonic_cst=None, interaction_cst=None,
            warm_start=False, early_stopping=False, scoring="loss",
            validation_fraction=None, n_iter_no_change=10, tol=1e-7,
            verbose=0, random_state=20260818, class_weight=None,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=10, criterion="gini", max_depth=4,
            min_samples_split=2, min_samples_leaf=1,
            min_weight_fraction_leaf=0.0, max_features="sqrt",
            max_leaf_nodes=None, min_impurity_decrease=0.0, bootstrap=True,
            oob_score=False, n_jobs=1, random_state=20260818, verbose=0,
            warm_start=False, class_weight=None, ccp_alpha=0.0,
            max_samples=1.0, monotonic_cst=None,
        ),
        "xgboost": XGBClassifier(
            n_estimators=5, max_depth=2, learning_rate=0.1,
            min_child_weight=1, gamma=0.0, subsample=1.0,
            colsample_bytree=1.0, reg_alpha=0.0, reg_lambda=1.0,
            objective="binary:logistic", tree_method="hist",
            eval_metric="logloss", random_state=20260818, n_jobs=1,
            scale_pos_weight=1.0, verbosity=0,
        ),
        "dummy_prior": DummyClassifier(strategy="prior", random_state=None),
    }

    raw_scores: dict[str, Any] = {}
    for name, model in models.items():
        if name == "dummy_prior":
            model.fit(x, y)
        else:
            model.fit(x, y, sample_weight=weights)
        if name in {"fixed_l2_logistic", "elastic_net_logistic", "rbf_svm", "hist_gradient_boosting"}:
            score = model.decision_function(x)
        elif name == "xgboost":
            score = model.predict(x, output_margin=True)
        else:
            score = probability_logit(model.predict_proba(x)[:, 1])
        score = np.asarray(score, dtype=float).reshape(-1)
        if score.shape != (len(y),) or not np.isfinite(score).all():
            raise AssertionError(f"Invalid raw score interface for {name}.")
        raw_scores[name] = {
            "shape": list(score.shape),
            "finite": True,
            "minimum": float(score.min()),
            "maximum": float(score.max()),
        }

    return {
        "stack": "classical",
        "status": "passed",
        "synthetic_only": True,
        "versions": distribution_versions([
            "numpy", "scipy", "pandas", "scikit-learn", "xgboost", "shap", "joblib", "threadpoolctl"
        ]),
        "thread_environment": {key: os.environ[key] for key in (
            "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"
        )},
        "sqrt_positive_weight": positive_weight,
        "synthetic_smoke_wall_seconds": time.perf_counter() - started,
        "peak_rss_bytes": peak_rss_bytes(),
        "raw_score_interfaces": raw_scores,
    }


def qnn_smoke() -> dict[str, Any]:
    started = time.perf_counter()
    import numpy as np
    import pennylane as qml
    import torch
    from captum.attr import IntegratedGradients

    torch.set_default_dtype(torch.float64)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.use_deterministic_algorithms(True)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True

    class FrozenMLP(torch.nn.Module):
        def __init__(self, input_dim: int, hidden: tuple[int, ...], activation: str, seed: int) -> None:
            super().__init__()
            torch.manual_seed(seed)
            widths = (input_dim, *hidden, 1)
            layers: list[torch.nn.Module] = []
            for index, (left, right) in enumerate(zip(widths[:-1], widths[1:])):
                linear = torch.nn.Linear(left, right, bias=True, dtype=torch.float64)
                gain = torch.nn.init.calculate_gain(activation) if index < len(widths) - 2 else 1.0
                torch.nn.init.xavier_uniform_(linear.weight, gain=gain)
                torch.nn.init.zeros_(linear.bias)
                layers.append(linear)
                if index < len(widths) - 2:
                    layers.append(torch.nn.ReLU() if activation == "relu" else torch.nn.Tanh())
            self.network = torch.nn.Sequential(*layers)

        def forward(self, inputs: torch.Tensor) -> torch.Tensor:
            return self.network(inputs).squeeze(-1)

    def parameter_shape(ansatz: str, layers: int, qubits: int) -> tuple[int, int, int]:
        return (layers, qubits, 3 if ansatz == "ROT_CNOT_RING" else 2)

    def apply_ansatz(ansatz: str, theta: torch.Tensor, layer: int, qubits: int) -> None:
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
            raise ValueError(ansatz)

    class FrozenQNN(torch.nn.Module):
        def __init__(self, ansatz: str, qubits: int, layers: int, seed: int) -> None:
            super().__init__()
            self.ansatz = ansatz
            self.qubits = qubits
            self.layers = layers
            generator = torch.Generator().manual_seed(seed)
            theta = torch.empty(parameter_shape(ansatz, layers, qubits), dtype=torch.float64)
            theta.uniform_(-0.1, 0.1, generator=generator)
            self.theta = torch.nn.Parameter(theta)
            self.head = torch.nn.Linear(qubits, 1, bias=True, dtype=torch.float64)
            torch.nn.init.xavier_uniform_(self.head.weight, gain=1.0, generator=generator)
            torch.nn.init.zeros_(self.head.bias)
            device = qml.device("default.qubit", wires=qubits, shots=None)

            @qml.qnode(device, interface="torch", diff_method="adjoint")
            def circuit(inputs: torch.Tensor, parameters: torch.Tensor) -> list[Any]:
                for wire in range(qubits):
                    qml.RY(inputs[..., wire], wires=wire)
                for layer in range(layers):
                    apply_ansatz(ansatz, parameters, layer, qubits)
                return [qml.expval(qml.PauliZ(wire)) for wire in range(qubits)]

            self.circuit = circuit

        def forward(self, inputs: torch.Tensor) -> torch.Tensor:
            expectations = torch.stack(self.circuit(inputs, self.theta), dim=-1)
            return self.head(expectations).squeeze(-1)

    synthetic = torch.linspace(-1.0, 1.0, steps=48, dtype=torch.float64).reshape(8, 6)
    target = torch.tensor([0, 0, 0, 0, 0, 0, 1, 1], dtype=torch.float64)
    positive_weight = math.sqrt(6 / 2)
    loss_function = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([positive_weight], dtype=torch.float64), reduction="mean"
    )
    ansatzes = ("ROT_CNOT_RING", "RY_RZ_CZ_BRICKWORK", "RY_CRX_RING")
    parameter_counts: dict[str, int] = {}
    checked_packages: list[str] = []
    for ansatz in ansatzes:
        for qubits in (4, 6):
            for layers in (1, 2, 3):
                model = FrozenQNN(ansatz, qubits, layers, 20260818)
                logits = model(synthetic[:, :qubits])
                loss = loss_function(logits, target)
                loss.backward()
                if not torch.isfinite(logits).all() or not torch.isfinite(loss):
                    raise AssertionError(f"Non-finite QNN smoke result: {ansatz}/{qubits}/{layers}")
                if any(parameter.grad is None or not torch.isfinite(parameter.grad).all() for parameter in model.parameters()):
                    raise AssertionError(f"Non-finite QNN gradient: {ansatz}/{qubits}/{layers}")
                checked_packages.append(f"{ansatz}/q{qubits}/d{layers}")
                if qubits == 4 and layers == 2:
                    parameter_counts[ansatz] = sum(parameter.numel() for parameter in model.parameters())

    replay_a = FrozenQNN("ROT_CNOT_RING", 4, 2, 20260818)(synthetic[:, :4]).detach()
    replay_b = FrozenQNN("ROT_CNOT_RING", 4, 2, 20260818)(synthetic[:, :4]).detach()
    replay_max_abs_difference = float(torch.max(torch.abs(replay_a - replay_b)))
    if replay_max_abs_difference > 1e-8:
        raise AssertionError("Deterministic QNN replay tolerance exceeded.")

    mlp = FrozenMLP(6, (16, 8), "relu", 20260818)
    optimizer = torch.optim.Adam(
        mlp.parameters(), lr=1e-3, betas=(0.9, 0.999), eps=1e-8,
        weight_decay=1e-4, amsgrad=False, foreach=False, fused=False,
    )
    optimizer.zero_grad(set_to_none=True)
    mlp_loss = loss_function(mlp(synthetic), target)
    mlp_loss.backward()
    optimizer.step()
    integrated_gradients = IntegratedGradients(mlp)
    attribution, convergence_delta = integrated_gradients.attribute(
        synthetic[:2], baselines=torch.zeros_like(synthetic[:2]), n_steps=8,
        return_convergence_delta=True,
    )
    if attribution.shape != synthetic[:2].shape or not torch.isfinite(attribution).all():
        raise AssertionError("Invalid Captum Integrated Gradients output.")

    batch_seed = 20260818 * 10000 + 2015
    generator_a = torch.Generator().manual_seed(batch_seed)
    generator_b = torch.Generator().manual_seed(batch_seed)
    batch_order_equal = torch.equal(torch.randperm(32, generator=generator_a), torch.randperm(32, generator=generator_b))
    if not batch_order_equal:
        raise AssertionError("Shared minibatch seed did not reproduce order.")

    with tempfile.TemporaryDirectory(prefix="model_stage_checkpoint_") as directory:
        path = Path(directory) / "checkpoint.pt"
        checkpoint = {
            "model_state": mlp.state_dict(),
            "optimizer_state": optimizer.state_dict(),
            "epoch": 1,
            "torch_rng_state": torch.get_rng_state(),
            "configuration_id": "synthetic_smoke",
        }
        torch.save(checkpoint, path)
        restored = torch.load(path, map_location="cpu", weights_only=False)
        checkpoint_round_trip = restored["epoch"] == 1 and restored["configuration_id"] == "synthetic_smoke"
        if not checkpoint_round_trip:
            raise AssertionError("Checkpoint round trip failed.")

    expected_counts = {"ROT_CNOT_RING": 29, "RY_RZ_CZ_BRICKWORK": 21, "RY_CRX_RING": 21}
    if parameter_counts != expected_counts:
        raise AssertionError(f"Unexpected QNN parameter counts: {parameter_counts}")

    return {
        "stack": "qnn_mlp",
        "status": "passed",
        "synthetic_only": True,
        "versions": distribution_versions([
            "numpy", "scipy", "pandas", "scikit-learn", "torch",
            "PennyLane", "pennylane-lightning", "captum"
        ]),
        "torch_deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
        "qnn_packages_checked": checked_packages,
        "stage_q1_trainable_parameters": parameter_counts,
        "replay_max_abs_difference": replay_max_abs_difference,
        "shared_minibatch_order": batch_order_equal,
        "captum_integrated_gradients_shape": list(attribution.shape),
        "captum_convergence_delta_finite": bool(torch.isfinite(convergence_delta).all()),
        "checkpoint_round_trip": checkpoint_round_trip,
        "synthetic_smoke_wall_seconds": time.perf_counter() - started,
        "peak_rss_bytes": peak_rss_bytes(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stack", choices=("classical", "qnn"))
    args = parser.parse_args()
    result = classical_smoke() if args.stack == "classical" else qnn_smoke()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

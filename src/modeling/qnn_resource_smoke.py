"""Synthetic-only QNN executable/resource smoke for every frozen ansatz."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import time
from typing import Any

import numpy as np

from src.modeling.environment_audit import environment_report
from src.modeling.production_worker import build_qnn, torch_configuration


ANSATZES = ("ROT_CNOT_RING", "RY_RZ_CZ_BRICKWORK", "RY_CRX_RING")
QUBITS = (4, 6)


def peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def smoke() -> dict[str, Any]:
    torch = torch_configuration()
    seed = 20260818
    cases: list[dict[str, Any]] = []
    for ansatz in ANSATZES:
        for qubits in QUBITS:
            parameters = {
                "qubits_pca": qubits,
                "layers": 2,
                "epochs": 1,
                "learning_rate": 0.01,
                "batch_size": 4,
                "weight_decay": 1e-4,
                "imbalance": "sqrt",
            }
            inputs = torch.linspace(
                -1.0, 1.0, steps=4 * qubits, dtype=torch.float64
            ).reshape(4, qubits)
            labels = torch.tensor([0.0, 1.0, 0.0, 1.0], dtype=torch.float64)
            before_rss = peak_rss_bytes()
            started = time.perf_counter()
            model = build_qnn(torch, parameters, ansatz, seed)
            logits = model(inputs)
            loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, labels)
            loss.backward()
            elapsed = time.perf_counter() - started
            gradients_finite = all(
                parameter.grad is not None and torch.isfinite(parameter.grad).all()
                for parameter in model.parameters()
            )
            outputs_finite = bool(torch.isfinite(logits).all() and torch.isfinite(loss))
            replay_model = build_qnn(torch, parameters, ansatz, seed)
            replay = replay_model(inputs).detach()
            replay_max_abs_difference = float(
                torch.max(torch.abs(logits.detach() - replay))
            )
            with tempfile.TemporaryDirectory(prefix="qnn_resource_checkpoint_") as directory:
                checkpoint_path = Path(directory) / "checkpoint.pt"
                torch.save(
                    {
                        "model_state": model.state_dict(),
                        "ansatz": ansatz,
                        "qubits": qubits,
                        "seed": seed,
                    },
                    checkpoint_path,
                )
                restored_payload = torch.load(
                    checkpoint_path, map_location="cpu", weights_only=False
                )
                restored = build_qnn(torch, parameters, ansatz, seed + 1)
                restored.load_state_dict(restored_payload["model_state"])
                restored_scores = restored(inputs).detach()
                checkpoint_max_abs_difference = float(
                    torch.max(torch.abs(logits.detach() - restored_scores))
                )
                checkpoint_bytes = checkpoint_path.stat().st_size
            trainable_parameters = sum(
                parameter.numel() for parameter in model.parameters()
            )
            estimated_parameter_optimizer_bytes = trainable_parameters * 8 * 4
            after_rss = peak_rss_bytes()
            case = {
                "ansatz": ansatz,
                "qubits": qubits,
                "layers": 2,
                "batch_rows": 4,
                "forward_backward_seconds": elapsed,
                "outputs_finite": outputs_finite,
                "gradients_finite": bool(gradients_finite),
                "deterministic_replay_max_abs_difference": replay_max_abs_difference,
                "checkpoint_round_trip_max_abs_difference": checkpoint_max_abs_difference,
                "checkpoint_bytes": checkpoint_bytes,
                "trainable_parameters": trainable_parameters,
                "estimated_parameter_gradient_adam_state_bytes": estimated_parameter_optimizer_bytes,
                "peak_rss_before_bytes": before_rss,
                "peak_rss_after_bytes": after_rss,
                "peak_rss_increment_upper_bound_bytes": max(0, after_rss - before_rss),
            }
            case["status"] = (
                "PASS"
                if outputs_finite
                and gradients_finite
                and replay_max_abs_difference == 0.0
                and checkpoint_max_abs_difference == 0.0
                else "FAIL"
            )
            cases.append(case)
    environment = environment_report("qnn_mlp", smoke_imports=True)
    passed = environment["status"] == "READY" and all(
        case["status"] == "PASS" for case in cases
    )
    return {
        "schema_version": 1,
        "id": "qnn_resource_smoke_v1_0_0",
        "status": "PASS" if passed else "FAIL",
        "synthetic_only": True,
        "project_data_opened": False,
        "project_model_training_performed": False,
        "device": {
            "name": "default.qubit",
            "shots": None,
            "differentiation": "adjoint",
            "interface": "torch",
            "dtype": "float64",
        },
        "environment": environment,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = smoke()
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    raise SystemExit(0 if report["status"] == "PASS" else 2)


if __name__ == "__main__":
    main()

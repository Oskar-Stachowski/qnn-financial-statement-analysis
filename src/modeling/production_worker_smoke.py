"""Synthetic-only end-to-end smoke of both numeric production workers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

import numpy as np

from src.modeling.model_execution_contract import canonical_sha256, load_contract, load_registry
from src.modeling.production_runner import (
    FoldTask,
    SubprocessFoldExecutor,
    atomic_write_json,
    float64_vector_sha256,
)


def make_task(
    *,
    family: str,
    configuration_id: str,
    parameters: dict,
    role: str,
    environment_sha256: str,
    selected_ansatz_id: str | None = None,
) -> FoldTask:
    contract = load_contract()
    feature_block = "BLOCK_AGNOSTIC" if family == "dummy_prior" else "L"
    checkpoint_identity = {
        "family": family,
        "configuration_id": configuration_id,
        "parameters_sha256": canonical_sha256(parameters),
        "feature_block": feature_block,
        "fold_id": "fold_2015",
        "training_seed": 20260818,
        "train_membership_sha256": "synthetic_train",
        "validation_membership_sha256": "synthetic_validation",
        "preprocessing_sha256": "synthetic_preprocessing",
        "pca_sha256_if_applicable": "synthetic_pca" if family == "qnn" else None,
        "software_environment_sha256": environment_sha256,
        "device_identity": contract["qnn_executable_identity"]["device_identity"]
        if family == "qnn"
        else "cpu",
    }
    return FoldTask(
        stage="qnn_q2" if family == "qnn" else "coarse",
        family=family,
        feature_block=feature_block,
        configuration_id=configuration_id,
        parameters=parameters,
        training_seed=20260818,
        fold_id="fold_2015",
        validation_feature_year=2015,
        selected_ansatz_id=selected_ansatz_id,
        train_membership_sha256="synthetic_train",
        validation_membership_sha256="synthetic_validation",
        preprocessing_sha256="synthetic_preprocessing",
        pca_sha256_if_applicable="synthetic_pca" if family == "qnn" else None,
        software_environment_role=role,
        checkpoint_identity=checkpoint_identity,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classical-python", required=True, type=Path)
    parser.add_argument("--qnn-python", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    executor = SubprocessFoldExecutor(
        root=root,
        classical_python=args.classical_python,
        qnn_python=args.qnn_python,
    )
    registry = load_registry()
    mlp_candidate = registry["coarse"]["pytorch_mlp"][0]
    qnn_candidate = registry["qnn"]["stage_q2"][1]
    tasks = [
        make_task(
            family="dummy_prior",
            configuration_id="model_stage_v1__coarse__dummy_prior__001",
            parameters={"strategy": "prior", "imbalance": "none"},
            role="classical",
            environment_sha256=executor.environment_hashes["classical"],
        ),
        make_task(
            family="pytorch_mlp",
            configuration_id=mlp_candidate["configuration_id"],
            parameters=dict(mlp_candidate["parameters"]),
            role="qnn_mlp",
            environment_sha256=executor.environment_hashes["qnn_mlp"],
        ),
        make_task(
            family="qnn",
            configuration_id=qnn_candidate["configuration_id"],
            parameters={
                key: value
                for key, value in qnn_candidate.items()
                if key != "configuration_id"
            },
            role="qnn_mlp",
            environment_sha256=executor.environment_hashes["qnn_mlp"],
            selected_ansatz_id="ROT_CNOT_RING",
        ),
    ]
    x = np.asarray(
        [
            [-0.8, -0.4, 0.1, 0.3],
            [-0.4, 0.2, 0.3, 0.5],
            [0.1, 0.4, 0.6, 0.8],
            [0.4, 0.7, 0.9, 1.0],
            [0.8, 0.6, 0.2, -0.1],
            [1.0, 0.8, 0.5, 0.2],
        ],
        dtype=np.float64,
    )
    y = np.asarray([0, 0, 1, 1, 0, 1], dtype=np.int64)
    validation = np.asarray([[-0.2, 0.1, 0.4, 0.5], [0.7, 0.8, 0.3, 0.2]])
    sample_weight = np.where(y == 1, 1.0, 1.0).astype(np.float64)
    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="production_worker_smoke_") as directory:
        base = Path(directory)
        for task in tasks:
            x_train = np.empty((len(y), 0)) if task.family == "dummy_prior" else x
            x_validation = (
                np.empty((len(validation), 0))
                if task.family == "dummy_prior"
                else validation
            )
            execution = executor.execute(
                task,
                x_train=x_train,
                y_train=y,
                x_validation=x_validation,
                sample_weight=sample_weight,
                checkpoint_path=base / task.family / "checkpoint.pt",
                timeout_seconds=120,
            )
            results.append(
                {
                    "family": task.family,
                    "configuration_id": task.configuration_id,
                    "status": execution.status,
                    "failure_code": execution.failure_code,
                    "raw_score_sha256": float64_vector_sha256(execution.raw_scores)
                    if execution.raw_scores is not None
                    else None,
                    "raw_score_count": len(execution.raw_scores)
                    if execution.raw_scores is not None
                    else 0,
                    "attempts": execution.attempts,
                    "software_environment_sha256": execution.software_environment_sha256,
                }
            )
    passed = all(row["status"] == "COMPLETE" for row in results)
    report = {
        "schema_version": 1,
        "id": "production_worker_synthetic_smoke_v1_0_0",
        "status": "PASS" if passed else "FAIL",
        "synthetic_only": True,
        "project_data_opened": False,
        "project_model_training_performed": False,
        "results": results,
    }
    atomic_write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()

"""Economic-group permutation remediation for secondary execution v1.1.5."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping

import numpy as np
import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling import secondary_analysis_execution_v1_1_4 as v114
from src.modeling.secondary_analysis_execution_worker_v1_1_5 import POLICY_ID


ROOT = base.ROOT
DEFAULT_CONFIG = (
    ROOT
    / "configs/secondary_development_execution_v1_1_5_economic_group_permutation_fix.yaml"
)
DEFAULT_OUTPUT = ROOT / "data/model_runs/secondary_development_v1_1_5"
WORKER_MODULE = "src.modeling.secondary_analysis_execution_worker_v1_1_5"
_BASE_PREFLIGHT_CONTEXT = v114._BASE_PREFLIGHT_CONTEXT


def load_execution_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = yaml.safe_load(path.resolve().read_text(encoding="utf-8"))
    base._require(isinstance(payload, dict), "v1.1.5 config must be a mapping.")
    extension = payload.get("extends")
    base._require(isinstance(extension, Mapping), "v1.1.5 must extend v1.1.4.")
    base_path = (ROOT / str(extension["path"])).resolve()
    expected = (
        ROOT
        / "configs/secondary_development_execution_v1_1_4_parallel_checkpoint_fix.yaml"
    )
    base._require(base_path == expected, "Wrong v1.1.5 amendment base.")
    base._require(
        base.file_sha256(base_path) == str(extension["sha256"]),
        "v1.1.4 config hash mismatch.",
    )
    inherited = v114.load_execution_config(base_path)
    merged = v114._merge(
        inherited, {key: value for key, value in payload.items() if key != "extends"}
    )
    section = merged["secondary_development_execution"]
    base._require(section["id"] == "secondary_development_execution_v1_1_5", "Wrong v1.1.5 ID.")
    base._require(section["version"] == "1.1.5", "Wrong v1.1.5 version.")
    base._require(
        section["status"] == "executable_economic_group_permutation_amendment_frozen",
        "v1.1.5 is not frozen.",
    )
    amendment = section["economic_group_permutation_amendment"]
    expected_flags = {
        "target_values_changed": False,
        "sample_membership_changed": False,
        "fold_policy_changed": False,
        "task_roster_changed": False,
        "task_identity_changed": False,
        "model_parameters_changed": False,
        "interpretation_method_changed": True,
        "robustness_method_changed": False,
        "methodology_changed": True,
    }
    for field, expected_value in expected_flags.items():
        base._require(
            amendment[field] is expected_value,
            f"Wrong v1.1.5 amendment flag: {field}",
        )
    policy = section["interpretation"]["common_permutation"]
    base._require(
        policy["economic_group_duplicate_policy"] == POLICY_ID,
        "Wrong v1.1.5 economic-group policy.",
    )
    base._require(
        policy["require_consistent_label_within_economic_group"] is True,
        "v1.1.5 must validate within-group labels.",
    )
    base._require(
        policy["feature_aggregation"] == "none",
        "v1.1.5 may not aggregate observed features.",
    )
    return merged


def verify_amendment_authority(config: Mapping[str, Any]) -> dict[str, str]:
    authority = config["secondary_development_execution"][
        "amendment_authority_v1_1_5"
    ]
    verified: dict[str, str] = {}
    for name, item in authority.items():
        path = (ROOT / str(item["path"])).resolve()
        base._require(path.is_relative_to(ROOT), f"v1.1.5 authority escapes repository: {name}")
        base._require(path.is_file(), f"Missing v1.1.5 authority: {name}")
        actual = base.file_sha256(path)
        base._require(actual == str(item["sha256"]), f"v1.1.5 authority mismatch: {name}")
        verified[name] = actual
    return verified


def _output_identity(config_path: Path, git_index_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": "secondary_development_execution_v1_1_5",
        "execution_config_sha256": base.file_sha256(config_path),
        "base_execution_config_sha256": base.file_sha256(
            ROOT / "configs/secondary_development_execution_v1_1_0.yaml"
        ),
        "frozen_schedule_sha256": base.file_sha256(
            ROOT / "configs/secondary_development_analyses_v1_0_0.yaml"
        ),
        "package_git_index_sha256": git_index_sha256,
        "economic_group_duplicate_policy": POLICY_ID,
        "protected_feature_years_opened": False,
    }


def _economic_group_audit(
    sample: Any, config: Mapping[str, Any]
) -> dict[str, Any]:
    expected = config["secondary_development_execution"][
        "economic_group_permutation_amendment"
    ]["observed_excess_rows_by_fold"]
    actual: dict[str, int] = {}
    unique_groups: dict[str, int] = {}
    for year in range(2015, 2021):
        fold_id = f"fold_{year}"
        frame = sample.loc[sample["feature_year"].eq(year)]
        grouped = frame.groupby("economic_group_id", sort=False, dropna=False)
        inconsistent = grouped["target_label"].nunique(dropna=False)
        base._require(
            bool((inconsistent == 1).all()),
            f"Target label differs within an economic group: {fold_id}",
        )
        groups = int(frame["economic_group_id"].astype(str).nunique())
        actual[fold_id] = int(len(frame) - groups)
        unique_groups[fold_id] = groups
    base._require(actual == {str(key): int(value) for key, value in expected.items()}, "Economic-group duplicate audit drifted.")
    return {
        "policy": POLICY_ID,
        "excess_rows_by_fold": actual,
        "unique_groups_by_fold": unique_groups,
        "total_excess_rows": sum(actual.values()),
        "within_group_labels_consistent": True,
        "feature_aggregation": "none",
        "protected_feature_years_opened": False,
    }


def _patched_preflight_context(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> Any:
    config = load_execution_config(config_path)
    verify_amendment_authority(config)
    if not synthetic:
        from src.modeling.verify_secondary_analysis_execution_v1_1_5 import (
            verify_secondary_analysis_execution_v1_1_5,
        )

        report = verify_secondary_analysis_execution_v1_1_5()
        base._require(report["status"] == "PASS", "v1.1.5 package verification failed.")
    context = _BASE_PREFLIGHT_CONTEXT(config_path, output_dir, synthetic=synthetic)
    if not synthetic:
        _config, schedule, _tasks, _runner, sample, _folds = context
        inventory = v114.verify_checkpoint_inventory(config, schedule)
        audit = _economic_group_audit(sample, config)
        preflight_path = output_dir / "preflight_manifest.json"
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight.update(
            {
                "parallel_checkpoint_amendment_version": "1.1.4",
                "economic_group_permutation_amendment_version": "1.1.5",
                "interpretation_checkpoint_count": inventory["checkpoint_count"],
                "interpretation_checkpoint_inventory_sha256": inventory[
                    "inventory_sha256"
                ],
                "parallel_execution": config["secondary_development_execution"][
                    "parallel_execution"
                ],
                "economic_group_permutation_audit": audit,
            }
        )
        base.atomic_write_json(preflight_path, preflight)
    return context


def _run_interpretation_fold(
    *,
    output_dir: Path,
    runner: Any,
    plan_task: Mapping[str, Any],
    representative: Mapping[str, Any],
    fold_id: str,
    folds: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    family = str(representative["family"])
    block = str(representative["feature_block"])
    prepared = runner._prepare_fold(block=block, fold_tuple=folds[fold_id])
    arrays: dict[str, np.ndarray] = {
        "x_train_base": prepared.x_train,
        "x_validation_base": prepared.x_validation,
        "y_train": prepared.train["target_label"].to_numpy(dtype=np.int64),
        "y_validation": prepared.validation["target_label"].to_numpy(dtype=np.int64),
        "sample_weight": runner._sample_weight(
            prepared.train["target_label"].to_numpy(dtype=np.int64),
            str(representative["parameters"].get("imbalance", "none")),
        ),
        "cluster_codes": base.pd.Categorical(
            prepared.validation["economic_group_id"].astype(str)
        ).codes.astype(np.int64),
    }
    qubits: int | None = None
    if family == "qnn":
        qubits = int(representative["parameters"]["qubits_pca"])
        runner._prepare_fold(block=block, fold_tuple=folds[fold_id], qubits=qubits)
        arrays.update(base._pca_arrays(runner, block, qubits, fold_id))
    seeds = base._seeds(representative)
    identity = plan_task["task_identity"]
    analysis_id = str(identity["analysis_id"])
    if analysis_id == "common_grouped_permutation":
        action = "grouped_permutation"
    elif identity.get("representative_role") == "linear":
        action = "detailed_linear"
    elif identity.get("representative_role") == "tree_boosting":
        action = "detailed_tree_shap"
    elif identity.get("representative_role") == "mlp":
        action = "detailed_mlp_ig"
    else:
        action = "detailed_qnn_sensitivity"
    task: dict[str, Any] = {
        "action": action,
        "family": family,
        "parameters": representative["parameters"],
        "source_stage": representative["stage"],
        "seeds": seeds,
        "fold_id": fold_id,
        "model_feature_names": (
            list(prepared.predictor_names)
            if family != "qnn"
            else [f"pca_angle_{index + 1}" for index in range(int(qubits or 0))]
        ),
    }
    interpretation = config["secondary_development_execution"]["interpretation"]
    if action == "grouped_permutation":
        originals = list(base.features_for_blocks(base.BLOCK_PARTS[block]))
        task.update(
            {
                "feature_names": originals,
                "feature_groups": [
                    [index, index + len(originals)]
                    for index in range(len(originals))
                ],
                "repetitions": interpretation["common_permutation"]["repetitions"],
                "permutation_seed": interpretation["common_permutation"]["seed"],
                "economic_group_duplicate_policy": interpretation[
                    "common_permutation"
                ]["economic_group_duplicate_policy"],
            }
        )
    elif action == "detailed_tree_shap":
        task.update(
            {
                "background_rows_max": interpretation["tree_shap"][
                    "background_train_rows_max"
                ],
                "oof_rows_max": interpretation["tree_shap"][
                    "oof_rows_per_fold_max"
                ],
            }
        )
    elif action == "detailed_mlp_ig":
        task.update(
            {
                "oof_rows_max": interpretation["mlp_integrated_gradients"][
                    "oof_rows_per_fold_max"
                ],
                "steps": interpretation["mlp_integrated_gradients"]["steps"],
            }
        )
    elif action == "detailed_qnn_sensitivity":
        task["oof_rows_max"] = interpretation["qnn_sensitivity"][
            "oof_rows_per_fold_max"
        ]
    if family in {"pytorch_mlp", "qnn"}:
        checkpoints, checkpoint_ids = base._source_checkpoints(
            representative, seeds, fold_id
        )
        task["checkpoint_paths"] = checkpoints
        task["checkpoint_task_identity_sha256"] = checkpoint_ids
        if family == "qnn":
            task["selected_ansatz_id"] = "ROT_CNOT_RING"
            task["device_name"] = runner.contract["qnn_executable_identity"][
                "device_identity"
            ]["name"]
    fold_dir = (
        output_dir
        / "task_artifacts"
        / plan_task["task_identity_sha256"]
        / fold_id
    )
    fold_dir.mkdir(parents=True, exist_ok=True)
    arrays_path = fold_dir / "interpretation_arrays.npz"
    np.savez(arrays_path, **arrays)
    task_sha = base.canonical_sha256(task)
    task_path = fold_dir / "interpretation_task.json"
    result_path = fold_dir / "interpretation_result.json"
    payload = {
        "worker_mode": "interpretation",
        "interpretation_task": task,
        "interpretation_task_sha256": task_sha,
        "arrays_path": str(arrays_path),
        "result_path": str(result_path),
    }
    base.atomic_write_json(task_path, payload)
    role_python = base.QNN_PYTHON if family in {"pytorch_mlp", "qnn"} else base.CLASSICAL_PYTHON
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": str(ROOT),
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
    )
    completed = subprocess.run(
        [str(role_python), "-m", WORKER_MODULE, "--task", str(task_path)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=43200 if family == "qnn" else 14400,
        check=False,
    )
    base._require(
        result_path.is_file(),
        f"Interpretation worker produced no result: {family}/{fold_id}",
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["returncode"] = completed.returncode
    result["stderr_sha256"] = hashlib.sha256(completed.stderr.encode()).hexdigest()
    if result.get("status") == "COMPLETE":
        arrays_path.unlink(missing_ok=True)
    return result


def activate_amendment() -> None:
    v114.activate_amendment()
    base.DEFAULT_CONFIG = DEFAULT_CONFIG
    base.load_execution_config = load_execution_config
    base._output_identity = _output_identity
    base._preflight_context = _patched_preflight_context
    base._run_interpretation_fold = _run_interpretation_fold


@contextmanager
def _isolated_activation() -> Any:
    names = (
        "DEFAULT_CONFIG",
        "load_execution_config",
        "_load_project_sample_and_robustness",
        "_output_identity",
        "_preflight_context",
        "_source_checkpoints",
        "_run_interpretation_fold",
        "execute_pca_controls",
        "execute_interpretability",
        "execute_classical_robustness",
        "execute_qnn_robustness",
    )
    previous = {name: getattr(base, name) for name in names}
    try:
        activate_amendment()
        yield
    finally:
        for name, value in previous.items():
            setattr(base, name, value)


def create_report(config_path: Path, output_dir: Path) -> dict[str, Any]:
    report = base.create_report(config_path, output_dir)
    report["id"] = "secondary_development_execution_v1_1_5"
    report["parallel_checkpoint_amendment"] = "1.1.4"
    report["economic_group_permutation_amendment"] = "1.1.5"
    base.atomic_write_json(output_dir / "run_manifest.json", report)
    result_path = output_dir / "secondary_development_report.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["id"] = "secondary_development_results_v1_1_5"
        result["parallel_checkpoint_amendment"] = "1.1.4"
        result["economic_group_permutation_amendment"] = "1.1.5"
        base.atomic_write_json(result_path, result)
    return report


def main() -> None:
    activate_amendment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "status",
            "plan",
            "smoke",
            "preflight",
            "pca-controls",
            "interpretability",
            "robustness-classical",
            "robustness-qnn",
            "report",
            "all",
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config_path = args.config.resolve()
    if args.output_dir is not None:
        output_dir = args.output_dir.resolve()
    elif args.mode in {"plan", "smoke"}:
        output_dir = (
            ROOT / f"data/model_runs/secondary_development_v1_1_5_{args.mode}"
        ).resolve()
    else:
        output_dir = DEFAULT_OUTPUT.resolve()
    base._require(
        config_path == DEFAULT_CONFIG.resolve(),
        "Only canonical v1.1.5 config may execute.",
    )
    if args.mode == "status":
        result = base.package_status(config_path)
        result["amendment_authority_v1_1_5"] = verify_amendment_authority(
            load_execution_config(config_path)
        )
    elif args.mode == "plan":
        result = base.write_plan(config_path, output_dir)
        result["id"] = "secondary_development_execution_plan_v1_1_5"
        result["economic_group_permutation_amendment"] = "1.1.5"
        base.atomic_write_json(
            output_dir / "secondary_analysis_execution_plan.json", result
        )
    elif args.mode == "smoke":
        result = base.synthetic_smoke(config_path, output_dir)
        result["economic_group_permutation_amendment"] = "1.1.5"
    elif args.mode == "preflight":
        _config, _schedule, tasks, _runner, _sample, folds = base._preflight_context(
            config_path, output_dir
        )
        preflight = json.loads(
            (output_dir / "preflight_manifest.json").read_text(encoding="utf-8")
        )
        result = {
            "status": "PASS",
            "planned_tasks": len(tasks),
            "fold_ids": list(folds),
            "parallel_checkpoint_amendment": "1.1.4",
            "economic_group_permutation_amendment": "1.1.5",
            "interpretation_checkpoint_count": preflight[
                "interpretation_checkpoint_count"
            ],
            "interpretation_checkpoint_inventory_sha256": preflight[
                "interpretation_checkpoint_inventory_sha256"
            ],
            "economic_group_permutation_audit": preflight[
                "economic_group_permutation_audit"
            ],
            "project_data_read": True,
            "project_model_fit_performed": False,
            "protected_feature_years_opened": False,
        }
    elif args.mode == "pca-controls":
        result = base.execute_pca_controls(config_path, output_dir)
    elif args.mode == "interpretability":
        result = base.execute_interpretability(config_path, output_dir)
    elif args.mode == "robustness-classical":
        result = base.execute_classical_robustness(config_path, output_dir)
    elif args.mode == "robustness-qnn":
        result = base.execute_qnn_robustness(config_path, output_dir)
    elif args.mode == "report":
        result = create_report(config_path, output_dir)
    else:
        base.execute_pca_controls(config_path, output_dir)
        base.execute_interpretability(config_path, output_dir)
        base.execute_classical_robustness(config_path, output_dir)
        base.execute_qnn_robustness(config_path, output_dir)
        result = create_report(config_path, output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

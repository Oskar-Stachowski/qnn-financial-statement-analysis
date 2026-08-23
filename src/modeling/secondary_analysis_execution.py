"""Execute the frozen 96-task secondary-development schedule.

Real-data modes fail closed unless the execution package is committed and
unmodified.  Only exact SHA-verified 2011--2020 train projections are loaded;
workers receive numeric arrays and have no project-data loader.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
import yaml

from src.modeling.preprocessing import (
    FinancialPreprocessor,
    PreprocessingPolicy,
    features_for_blocks,
)
from src.modeling.production_runner import (
    BLOCK_PARTS,
    FoldExecution,
    FoldTask,
    PreparedFold,
    ProductionExperimentRunner,
    ProtectedDataAccessError,
    RunnerIntegrityError,
    SubprocessFoldExecutor,
    SyntheticFoldExecutor,
    atomic_write_json,
    canonical_timestamp,
    membership_sha256,
)
from src.modeling.secondary_analysis_runner import (
    _build_tasks,
    _load_frozen_representatives,
    _validate_contract_alignment,
)
from src.modeling.secondary_analysis_schemas import (
    ROOT,
    SecondaryAnalysisIntegrityError,
    canonical_sha256,
    file_sha256,
    load_config as load_frozen_config,
    require,
    validate_config as validate_frozen_config,
    verify_authority as verify_frozen_authority,
)
from src.modeling.verify_post_coarse_results_freeze import (
    verify_post_coarse_results_freeze,
)
from src.modeling.verify_secondary_analysis_package import (
    verify_secondary_analysis_package,
)


DEFAULT_CONFIG = ROOT / "configs/secondary_development_execution_v1_1_0.yaml"
RUNNER_CONFIG = ROOT / "configs/production_experiment_runner_v1_0_1_lightning.yaml"
CLASSICAL_PYTHON = ROOT / ".venv-classical/bin/python"
QNN_PYTHON = ROOT / ".venv-qnn-mlp/bin/python"
TERMINAL = {"COMPLETE", "TECHNICALLY_INVALID", "METHOD_FAILED", "RESOURCE_LIMIT_REACHED"}
MODEL_COMPLETE = "COMPLETE"


class SecondaryExecutionIntegrityError(RuntimeError):
    """Raised when an executable secondary-analysis invariant fails."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SecondaryExecutionIntegrityError(message)


def load_execution_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), "Execution config must be a mapping.")
    _require(payload.get("schema_version") == 1, "Wrong execution schema version.")
    section = payload.get("secondary_development_execution")
    _require(isinstance(section, dict), "Missing secondary execution section.")
    _require(section.get("id") == "secondary_development_execution_v1_1_0", "Wrong execution ID.")
    _require(section.get("version") == "1.1.0", "Wrong execution version.")
    _require(
        section.get("status") in {"executable_package_pending_freeze", "executable_package_frozen"},
        "Execution package has an invalid state.",
    )
    boundary = section["data_boundary"]
    _require(boundary["permitted_feature_year_bounds"] == [2011, 2020], "Permitted years changed.")
    _require(boundary["protected_feature_years"] == [2021, 2022, 2023, 2024], "Protected years changed.")
    _require(boundary["raw_directory_may_be_read"] is False, "Raw-data read was enabled.")
    _require(section["frozen_schedule"]["task_count"] == 96, "Frozen task count changed.")
    return payload


def _resolve(path: str | Path) -> Path:
    resolved = (ROOT / Path(path)).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    _require(resolved.is_relative_to(ROOT), f"Path escapes repository: {path}")
    return resolved


def verify_static_authority(config: Mapping[str, Any]) -> dict[str, str]:
    section = config["secondary_development_execution"]
    verified: dict[str, str] = {}
    for group_name in ("frozen_schedule", "authority"):
        for name, item in section[group_name].items():
            if not isinstance(item, Mapping) or "path" not in item or "sha256" not in item:
                continue
            path = _resolve(str(item["path"]))
            _require(path.is_file(), f"Missing authority: {group_name}.{name}")
            actual = file_sha256(path)
            _require(actual == str(item["sha256"]), f"Authority hash mismatch: {group_name}.{name}")
            verified[f"{group_name}.{name}"] = actual
    package = verify_secondary_analysis_package()
    _require(package["status"] == "PASS", "Pre-execution package verification failed.")
    post_coarse = verify_post_coarse_results_freeze(
        ROOT / "configs/post_coarse_v1_3_0_results_freeze_manifest.yaml"
    )
    _require(post_coarse["status"] == "PASS", "Post-coarse freeze verification failed.")
    return verified


def frozen_schedule(config: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    frozen_path = _resolve(config["secondary_development_execution"]["frozen_schedule"]["config"]["path"])
    frozen = load_frozen_config(frozen_path)
    validate_frozen_config(frozen)
    verify_frozen_authority(frozen)
    _validate_contract_alignment(frozen)
    representatives, selection = _load_frozen_representatives(frozen)
    tasks, counts = _build_tasks(
        frozen["secondary_development_analyses"], representatives, selection
    )
    _require(len(tasks) == 96 and counts["total_planned_tasks"] == 96, "Frozen roster changed.")
    return {
        "representatives": representatives,
        "qnn_selection": selection,
        "counts": counts,
        "frozen_config_sha256": file_sha256(frozen_path),
    }, tasks


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise SecondaryExecutionIntegrityError(completed.stderr.strip() or "Git gate failed.")
    return completed.stdout.strip()


def verify_committed_package(config: Mapping[str, Any]) -> str:
    files = [str(value) for value in config["secondary_development_execution"]["git_gate"]["package_files"]]
    for path in files:
        _git(ROOT, "ls-files", "--error-unmatch", "--", path)
    dirty = _git(ROOT, "status", "--porcelain", "--", *files)
    _require(not dirty, "Execution package is uncommitted or modified:\n" + dirty)
    rows = _git(ROOT, "ls-files", "-s", "--", *files).splitlines()
    _require(len(rows) == len(files), "Git gate package cardinality mismatch.")
    return canonical_sha256(sorted(rows))


def _output_identity(config_path: Path, git_index_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": "secondary_development_execution_v1_1_0",
        "execution_config_sha256": file_sha256(config_path),
        "frozen_schedule_sha256": file_sha256(
            ROOT / "configs/secondary_development_analyses_v1_0_0.yaml"
        ),
        "package_git_index_sha256": git_index_sha256,
        "protected_feature_years_opened": False,
    }


def establish_output_identity(output_dir: Path, identity: Mapping[str, Any]) -> None:
    marker = output_dir / "execution_identity.json"
    if marker.is_file():
        existing = json.loads(marker.read_text(encoding="utf-8"))
        _require(existing == identity, "OUTPUT_IDENTITY_CONFLICT")
        return
    if output_dir.exists():
        existing = list(output_dir.iterdir())
        _require(not existing, "Nonempty output has no execution identity.")
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(marker, identity)


class SecondarySubprocessFoldExecutor(SubprocessFoldExecutor):
    """Use the pinned retry state machine with the secondary numeric worker."""

    def _one_attempt(
        self,
        task: FoldTask,
        *,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_validation: np.ndarray,
        sample_weight: np.ndarray,
        checkpoint_path: Path,
        timeout_seconds: int,
        resume: bool,
        work: Path,
        attempt: int,
    ) -> tuple[FoldExecution, dict[str, Any]]:
        arrays_path = work / "arrays.npz"
        np.savez(
            arrays_path,
            x_train=np.asarray(x_train, dtype=np.float64),
            y_train=np.asarray(y_train, dtype=np.int64),
            x_validation=np.asarray(x_validation, dtype=np.float64),
            sample_weight=np.asarray(sample_weight, dtype=np.float64),
        )
        task_path = work / f"task_attempt_{attempt}.json"
        result_path = work / f"worker_result_{attempt}.json"
        score_path = work / f"raw_scores_{attempt}.npy"
        payload = {
            "worker_mode": "model_fit",
            "task": task.identity,
            "task_identity_sha256": task.identity_sha256,
            "contract_path": str(self.contract_path),
            "arrays_path": str(arrays_path),
            "checkpoint_path": str(checkpoint_path),
            "resume": resume,
            "result_path": str(result_path),
            "raw_scores_path": str(score_path),
        }
        atomic_write_json(task_path, payload)
        command = [
            str(self.interpreters[task.software_environment_role]), "-m",
            "src.modeling.secondary_analysis_execution_worker", "--task", str(task_path),
        ]
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONPATH": str(self.root), "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "VECLIB_MAXIMUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
            }
        )
        audit: dict[str, Any] = {
            "attempt": attempt, "resume": resume,
            "command_sha256": canonical_sha256(command),
        }
        try:
            completed = subprocess.run(
                command, cwd=self.root, env=environment, capture_output=True,
                text=True, timeout=timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired:
            audit["outcome"] = "TIMEOUT_INVALID"
            return FoldExecution("TIMEOUT_INVALID", None, "TIMEOUT", "", "unknown", [audit]), audit
        except OSError:
            audit["outcome"] = "INFRASTRUCTURE_FAILURE"
            return FoldExecution("INFRASTRUCTURE_FAILURE", None, "TEMPORARY_FILESYSTEM_IO_FAILURE", "", "unknown", [audit]), audit
        audit["returncode"] = completed.returncode
        audit["stderr_sha256"] = hashlib.sha256(completed.stderr.encode()).hexdigest()
        if not result_path.is_file():
            audit["outcome"] = "EXCEPTION_INVALID"
            return FoldExecution("EXCEPTION_INVALID", None, "DETERMINISTIC_LIBRARY_EXCEPTION", "", "unknown", [audit]), audit
        worker = json.loads(result_path.read_text(encoding="utf-8"))
        _require(worker.get("task_identity_sha256") == task.identity_sha256, "Worker identity mismatch.")
        status = str(worker["status"])
        scores: np.ndarray | None = None
        if status == "COMPLETE":
            _require(score_path.is_file(), "Worker score artifact missing.")
            _require(file_sha256(score_path) == worker.get("raw_scores_file_sha256"), "Worker score hash mismatch.")
            scores = np.load(score_path, allow_pickle=False).astype(np.float64)
        audit["outcome"] = status
        return FoldExecution(
            status, scores, worker.get("failure_code"),
            str(worker.get("software_environment_sha256", "")),
            worker.get("device_identity", "unknown"), [audit],
        ), audit


def _make_runner(output_dir: Path, *, synthetic: bool) -> ProductionExperimentRunner:
    if synthetic:
        executor: Any = SyntheticFoldExecutor()
    else:
        executor = SecondarySubprocessFoldExecutor(
            root=ROOT, classical_python=CLASSICAL_PYTHON, qnn_python=QNN_PYTHON,
            runner_config_path=RUNNER_CONFIG,
        )
    runner = ProductionExperimentRunner(
        output_dir=output_dir / "execution_artifacts", executor=executor,
        runner_config_path=RUNNER_CONFIG,
    )
    runner._write_runtime_metadata([])
    if not synthetic:
        executor.configure_qnn_ledger(
            output_dir / "qnn_structural_resource_ledger.json",
            maximum_attempts=72, maximum_runtime_seconds=172800,
        )
    return runner


def _load_project_sample_and_robustness(
    runner: ProductionExperimentRunner, config: Mapping[str, Any]
) -> tuple[pd.DataFrame, Any, dict[str, Any]]:
    sample, expectations = runner.load_frozen_project_sample()
    section = config["secondary_development_execution"]
    target_item = section["authority"]["robustness_target_train"]
    target_path = _resolve(target_item["path"])
    _require(target_path.is_file(), "REQUIRED_DEVELOPMENT_INPUT_MISSING")
    _require(file_sha256(target_path) == target_item["sha256"], "Robustness target hash mismatch.")
    columns = list(section["data_boundary"]["robustness_target_columns"])
    try:
        target = pd.read_csv(target_path, usecols=columns, low_memory=False)
    except ValueError as error:
        raise SecondaryExecutionIntegrityError("REQUIRED_DEVELOPMENT_COLUMN_MISSING") from error
    years = pd.to_numeric(target["feature_year"], errors="raise").astype(int)
    permitted = set(range(2011, 2021))
    found = set(years)
    if not found <= permitted:
        raise ProtectedDataAccessError(f"Forbidden years in robustness target: {sorted(found - permitted)}")
    target["feature_year"] = years
    key = "research_universe_company_year_id"
    _require(not target[key].astype(str).duplicated().any(), "Duplicate robustness target identity.")
    target[key] = target[key].astype(str)
    merged = sample.merge(
        target, on=key, how="left", validate="one_to_one", suffixes=("", "_robustness")
    )
    _require(
        merged["feature_year"].eq(merged["feature_year_robustness"]).all(),
        "Robustness target year alignment mismatch.",
    )
    required_numeric = ["deterioration_score_1y", "D1_roa", "D2_ocf_assets", "D3_current_ratio", "D4_liabilities_assets", "D5_revenues"]
    for column in required_numeric:
        merged[column] = pd.to_numeric(merged[column], errors="raise")
        _require(merged[column].notna().all(), f"Missing robustness target component: {column}")
    merged["target__deterioration_score_at_least_2"] = (merged["deterioration_score_1y"] >= 2).astype(int)
    merged["target__deterioration_score_at_least_4"] = (merged["deterioration_score_1y"] >= 4).astype(int)
    alternative = (
        merged[["D1_roa", "D2_ocf_assets"]].max(axis=1)
        + merged["D3_current_ratio"] + merged["D4_liabilities_assets"] + merged["D5_revenues"]
    )
    merged["target__operating_performance_max_D1_D2_alternative_score_at_least_3"] = (alternative >= 3).astype(int)
    merged = runner._canonicalize_sample(merged)
    folds = runner.verify_sample_and_folds(merged, expectations)
    audit = {
        "sample_membership_n": len(merged),
        "sample_membership_sha256": membership_sha256(merged[key].tolist()),
        "robustness_target_sha256": file_sha256(target_path),
        "feature_year_min": int(merged["feature_year"].min()),
        "feature_year_max": int(merged["feature_year"].max()),
        "fold_ids": list(folds),
        "project_data_read": True,
        "protected_feature_years_opened": False,
    }
    return merged, expectations, audit


def _preflight_context(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], ProductionExperimentRunner, pd.DataFrame, Mapping[str, Any]]:
    _require(config_path.resolve() == DEFAULT_CONFIG.resolve(), "Only the canonical v1.1.0 config may execute.")
    config = load_execution_config(config_path)
    verify_static_authority(config)
    schedule, tasks = frozen_schedule(config)
    if synthetic:
        runner = _make_runner(output_dir, synthetic=True)
        from src.modeling.production_runner import synthetic_dataset, synthetic_expectations

        sample = synthetic_dataset(rows_per_year=8)
        # The production synthetic fixture intentionally reuses economic groups
        # across years.  The secondary smoke also needs a nonempty unseen-group
        # robustness fold, so give each generated company-year its own group.
        sample["economic_group_id"] = sample[
            "research_universe_company_year_id"
        ].astype(str)
        synthetic_features = list(features_for_blocks(("L", "D", "R")))
        sample.loc[:, synthetic_features] = sample.loc[:, synthetic_features].fillna(0.0)
        sample["target__deterioration_score_at_least_2"] = sample[
            "target_label"
        ].astype(int)
        sample["target__deterioration_score_at_least_4"] = sample[
            "target_label"
        ].astype(int)
        sample[
            "target__operating_performance_max_D1_D2_alternative_score_at_least_3"
        ] = sample["target_label"].astype(int)
        expectations = synthetic_expectations(sample)
        folds = runner.verify_sample_and_folds(sample, expectations)
        return config, schedule, tasks, runner, sample, folds
    from src.modeling.verify_secondary_analysis_execution_package import (
        verify_secondary_analysis_execution_package,
    )

    package = verify_secondary_analysis_execution_package()
    _require(package["status"] == "PASS", "Execution package freeze verification failed.")
    git_sha = verify_committed_package(config)
    identity = _output_identity(config_path, git_sha)
    establish_output_identity(output_dir, identity)
    runner = _make_runner(output_dir, synthetic=False)
    sample, _expectations, audit = _load_project_sample_and_robustness(runner, config)
    folds = runner.verify_sample_and_folds(sample, runner.production_input_expectations())
    atomic_write_json(output_dir / "preflight_manifest.json", {
        "schema_version": 1, "status": "PASS", "authority": verify_static_authority(config),
        "schedule_counts": schedule["counts"], **audit,
    })
    return config, schedule, tasks, runner, sample, folds


def _terminal_status(status: str) -> str:
    if status == "COMPLETE":
        return "COMPLETE"
    if status in {"TIMEOUT_INVALID", "INFRASTRUCTURE_EXHAUSTED"}:
        return "RESOURCE_LIMIT_REACHED"
    if status in {"NUMERICAL_INVALID", "CONVERGENCE_INVALID", "CHECKPOINT_INVALID"}:
        return "TECHNICALLY_INVALID"
    return "METHOD_FAILED"


def _task_result_path(output_dir: Path, task: Mapping[str, Any]) -> Path:
    return output_dir / "task_results" / f"{task['task_identity_sha256']}.json"


def _existing_task_result(output_dir: Path, task: Mapping[str, Any]) -> dict[str, Any] | None:
    path = _task_result_path(output_dir, task)
    if not path.is_file():
        return None
    result = json.loads(path.read_text(encoding="utf-8"))
    _require(result.get("task_identity_sha256") == task["task_identity_sha256"], "Existing task identity conflict.")
    _require(result.get("status") in TERMINAL, "Existing task is not terminal.")
    return result


def _execute_prepared_model_task(
    *,
    output_dir: Path,
    runner: ProductionExperimentRunner,
    plan_task: Mapping[str, Any],
    prepared: PreparedFold,
    parameters: Mapping[str, Any],
    family: str,
    source_configuration_id: str,
    training_seed: int,
    y_train: np.ndarray,
    y_validation: np.ndarray,
    selected_ansatz_id: str | None,
) -> dict[str, Any]:
    identity = plan_task["task_identity"]
    role = "qnn_mlp" if family in {"pytorch_mlp", "qnn"} else "classical"
    checkpoint_identity = {
        "family": family, "configuration_id": source_configuration_id,
        "parameters_sha256": canonical_sha256(parameters),
        "feature_block": str(identity.get("feature_block") or identity.get("qnn_feature_block")),
        "fold_id": prepared.fold_id, "training_seed": int(training_seed),
        "train_membership_sha256": prepared.train_membership_sha256,
        "validation_membership_sha256": prepared.validation_membership_sha256,
        "preprocessing_sha256": prepared.preprocessing_sha256,
        "pca_sha256_if_applicable": prepared.pca_sha256,
        "software_environment_sha256": runner._environment_hashes[role],
        "device_identity": runner.contract["qnn_executable_identity"]["device_identity"] if family == "qnn" else "cpu",
    }
    if family == "pytorch_mlp":
        checkpoint_identity["epochs"] = int(parameters["epochs"])
    execution_task = FoldTask(
        stage=f"secondary::{identity['stage']}::{identity['analysis_id']}",
        family=family,
        feature_block=str(identity.get("feature_block") or identity.get("qnn_feature_block")),
        configuration_id=source_configuration_id,
        parameters=dict(parameters), training_seed=int(training_seed),
        fold_id=prepared.fold_id, validation_feature_year=prepared.validation_feature_year,
        selected_ansatz_id=selected_ansatz_id,
        train_membership_sha256=prepared.train_membership_sha256,
        validation_membership_sha256=prepared.validation_membership_sha256,
        preprocessing_sha256=prepared.preprocessing_sha256,
        pca_sha256_if_applicable=prepared.pca_sha256,
        software_environment_role=role, checkpoint_identity=checkpoint_identity,
    )
    existing = _existing_task_result(output_dir, plan_task)
    if existing is not None:
        _require(
            existing.get("execution_identity_sha256") == execution_task.identity_sha256,
            "Existing result has a different execution identity.",
        )
        return existing
    task_dir = output_dir / "task_artifacts" / plan_task["task_identity_sha256"]
    checkpoint_path = task_dir / "checkpoint.pt"
    sample_weight = runner._sample_weight(y_train, str(parameters.get("imbalance", "none")))
    timeout = int(runner.contract["execution_failure_state_machine"]["timeouts_cumulative_wall_seconds_per_fold_fit"][family])
    execution = runner.executor.execute(
        execution_task, x_train=prepared.x_train, y_train=y_train,
        x_validation=prepared.x_validation, sample_weight=sample_weight,
        checkpoint_path=checkpoint_path, timeout_seconds=timeout,
    )
    prediction_sha: str | None = None
    prediction_reference: str | None = None
    if execution.status == MODEL_COMPLETE:
        scores = np.asarray(execution.raw_scores, dtype=np.float64)
        _require(scores.shape == (len(prepared.validation),), "Raw-score shape mismatch.")
        _require(np.isfinite(scores).all(), "Nonfinite raw score.")
        rows = []
        for (_, observation), label, score in zip(
            prepared.validation.iterrows(), y_validation, scores, strict=True
        ):
            rows.append({
                "validation_feature_year": int(observation["feature_year"]),
                "research_universe_company_year_id": str(observation["research_universe_company_year_id"]),
                "economic_group_id": str(observation["economic_group_id"]),
                "fold_id": prepared.fold_id, "target_label": int(label),
                "raw_score": float(score), "raw_score_float64_hex": float(score).hex(),
            })
        prediction_path = task_dir / "oof_predictions.json"
        prediction_sha = atomic_write_json(prediction_path, {"schema_version": 1, "rows": rows})
        prediction_reference = str(prediction_path.relative_to(output_dir))
    result = {
        "schema_version": 1, "task_identity": plan_task["task_identity"],
        "task_identity_sha256": plan_task["task_identity_sha256"],
        "execution_identity": execution_task.identity,
        "execution_identity_sha256": execution_task.identity_sha256,
        "status": _terminal_status(execution.status),
        "failure_code": execution.failure_code,
        "worker_status": execution.status,
        "source_authority_sha256": file_sha256(DEFAULT_CONFIG),
        "attempts": execution.attempts,
        "prediction_artifact": prediction_reference,
        "prediction_artifact_sha256": prediction_sha,
        "train_rows": len(prepared.train), "validation_rows": len(prepared.validation),
        "project_data_read": not runner.executor.synthetic_only,
        "project_model_fit_performed": True,
        "protected_feature_years_opened": False,
        "may_change_primary_selection": False,
    }
    atomic_write_json(_task_result_path(output_dir, plan_task), result)
    # Numeric worker inputs and duplicate score arrays are reproducible from the
    # frozen train projections.  Keep checkpoints and audit JSON, but release
    # these temporary files after the terminal result is durable.
    worker_io = task_dir / "worker_io"
    for temporary in [worker_io / "arrays.npz", *worker_io.glob("raw_scores_*.npy")]:
        temporary.unlink(missing_ok=True)
    return result


def _custom_prepared_fold(
    *, runner: ProductionExperimentRunner, output_dir: Path,
    fold_tuple: tuple[Any, pd.DataFrame, pd.DataFrame, Any], block: str,
    variant: str, qubits: int | None = None,
) -> PreparedFold:
    fold, train, validation, _audit = fold_tuple
    features = features_for_blocks(BLOCK_PARTS[block])
    all_features = features_for_blocks(("L", "D", "R"))
    train = train.copy()
    validation = validation.copy()
    if variant == "complete_case":
        train = train.loc[train[list(features)].notna().all(axis=1)].copy()
        validation = validation.loc[validation[list(features)].notna().all(axis=1)].copy()
    elif variant == "purged_economic_group_cv":
        validation_groups = set(validation["economic_group_id"].astype(str))
        train = train.loc[~train["economic_group_id"].astype(str).isin(validation_groups)].copy()
    elif variant == "sparse_row_available_features_at_least_11_of_17":
        train = train.loc[train[list(all_features)].notna().sum(axis=1).ge(11)].copy()
        validation = validation.loc[validation[list(all_features)].notna().sum(axis=1).ge(11)].copy()
    _require(not train.empty and not validation.empty, f"Empty partition for {variant}/{fold.name}")
    policy = PreprocessingPolicy(
        lower_quantile=0.0 if variant == "no_winsorization" else 0.01,
        upper_quantile=1.0 if variant == "no_winsorization" else 0.99,
        add_missing_indicators=variant != "B_without_missing_indicators",
    )
    preprocessor = FinancialPreprocessor.for_blocks(BLOCK_PARTS[block], policy=policy)
    x_train_frame = preprocessor.fit_transform(train)
    x_validation_frame = preprocessor.transform(validation)
    preprocessing_payload = {
        "schema_version": 1,
        "identity": {"feature_block": block, "fold_id": fold.name, "variant": variant},
        "fit_scope": "fold_train_only", "state": preprocessor.fitted_state(),
    }
    prep_path = output_dir / "execution_artifacts" / "preprocessing_variants" / variant / block.replace("+", "_") / f"{fold.name}.json"
    prep_sha = atomic_write_json(prep_path, preprocessing_payload)
    x_train = x_train_frame.to_numpy(dtype=np.float64)
    x_validation = x_validation_frame.to_numpy(dtype=np.float64)
    names = tuple(x_train_frame.columns)
    pca_sha: str | None = None
    if qubits is not None:
        pca = PCA(n_components=qubits, svd_solver="full", whiten=False)
        train_components = pca.fit_transform(x_train)
        validation_components = pca.transform(x_validation)
        scaler = StandardScaler(with_mean=True, with_std=True)
        train_components = scaler.fit_transform(train_components)
        validation_components = scaler.transform(validation_components)
        x_train = np.pi / 3.0 * np.clip(train_components, -3.0, 3.0)
        x_validation = np.pi / 3.0 * np.clip(validation_components, -3.0, 3.0)
        pca_payload = {
            "schema_version": 1,
            "identity": {"feature_block": block, "fold_id": fold.name, "qubits": qubits, "variant": variant, "preprocessing_sha256": prep_sha},
            "fit_scope": "fold_train_only", "input_feature_order": list(names),
            "components_float64_hex": [[float(value).hex() for value in row] for row in pca.components_],
            "explained_variance_float64_hex": [float(value).hex() for value in pca.explained_variance_],
            "pca_mean_float64_hex": [float(value).hex() for value in pca.mean_],
            "component_scaler_mean_float64_hex": [float(value).hex() for value in scaler.mean_],
            "component_scaler_scale_float64_hex": [float(value).hex() for value in scaler.scale_],
            "clipping": [-3.0, 3.0], "angle_multiplier_float64_hex": float(np.pi / 3.0).hex(),
        }
        pca_path = output_dir / "execution_artifacts" / "pca_variants" / variant / block.replace("+", "_") / f"q{qubits}" / f"{fold.name}.json"
        pca_sha = atomic_write_json(pca_path, pca_payload)
        names = tuple(f"pca_angle_{index + 1}" for index in range(qubits))
    _require(np.isfinite(x_train).all() and np.isfinite(x_validation).all(), "Nonfinite prepared matrix.")
    return PreparedFold(
        fold_id=fold.name, validation_feature_year=fold.validation_start,
        train=train, validation=validation,
        train_membership_sha256=membership_sha256(train["research_universe_company_year_id"].tolist()),
        validation_membership_sha256=membership_sha256(validation["research_universe_company_year_id"].tolist()),
        preprocessing_sha256=prep_sha, pca_sha256=pca_sha,
        x_train=x_train, x_validation=x_validation, predictor_names=names,
    )


def execute_pca_controls(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> dict[str, Any]:
    config, schedule, tasks, runner, _sample, folds = _preflight_context(config_path, output_dir, synthetic=synthetic)
    selected = [task for task in tasks if task["task_identity"]["stage"] == "pca_matched_controls"]
    results = []
    reps = schedule["representatives"]
    qnn = reps["qnn"]
    for task in selected:
        identity = task["task_identity"]
        fold_id = identity["fold_id"]
        prepared = runner._prepare_fold(block=qnn["feature_block"], fold_tuple=folds[fold_id], qubits=int(qnn["parameters"]["qubits_pca"]))
        source = reps[identity["family"]]
        results.append(_execute_prepared_model_task(
            output_dir=output_dir, runner=runner, plan_task=task, prepared=prepared,
            parameters=source["parameters"], family=identity["family"],
            source_configuration_id=source["configuration_id"],
            training_seed=int(identity["training_seed"]),
            y_train=prepared.train["target_label"].to_numpy(dtype=np.int64),
            y_validation=prepared.validation["target_label"].to_numpy(dtype=np.int64),
            selected_ansatz_id=None,
        ))
    return _phase_manifest(output_dir, "pca_matched_controls", selected, results)


def execute_classical_robustness(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> dict[str, Any]:
    if not synthetic:
        _require_terminal_phase(output_dir, "interpretability")
    _config, schedule, tasks, runner, _sample, folds = _preflight_context(config_path, output_dir, synthetic=synthetic)
    selected = [task for task in tasks if task["task_identity"]["stage"] == "robustness" and task["task_identity"]["family"] == "xgboost"]
    winner = schedule["representatives"]["xgboost"]
    results = []
    pipeline_variants = {
        "B_without_missing_indicators", "complete_case", "no_winsorization",
        "purged_economic_group_cv", "sparse_row_available_features_at_least_11_of_17",
    }
    for task in selected:
        identity = task["task_identity"]
        variant = identity["analysis_id"]
        fold_id = identity["fold_id"]
        if variant in pipeline_variants:
            prepared = _custom_prepared_fold(
                runner=runner, output_dir=output_dir, fold_tuple=folds[fold_id],
                block=winner["feature_block"], variant=variant,
            )
            label_column = "target_label"
        else:
            prepared = runner._prepare_fold(block=winner["feature_block"], fold_tuple=folds[fold_id])
            label_column = f"target__{variant}"
        results.append(_execute_prepared_model_task(
            output_dir=output_dir, runner=runner, plan_task=task, prepared=prepared,
            parameters=winner["parameters"], family="xgboost",
            source_configuration_id=winner["configuration_id"],
            training_seed=int(identity["training_seed"]),
            y_train=prepared.train[label_column].to_numpy(dtype=np.int64),
            y_validation=prepared.validation[label_column].to_numpy(dtype=np.int64),
            selected_ansatz_id=None,
        ))
    return _phase_manifest(output_dir, "robustness_classical", selected, results)


def execute_qnn_robustness(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> dict[str, Any]:
    if not synthetic:
        _require_terminal_phase(output_dir, "robustness_classical")
    config, schedule, tasks, runner, _sample, folds = _preflight_context(config_path, output_dir, synthetic=synthetic)
    selected = [task for task in tasks if task["task_identity"]["stage"] == "robustness" and task["task_identity"]["family"] == "qnn"]
    qnn = schedule["representatives"]["qnn"]
    variants = config["secondary_development_execution"]["qnn_structural_variants"]
    results = []
    for task in selected:
        identity = task["task_identity"]
        variant = identity["analysis_id"]
        parameters = dict(qnn["parameters"])
        ansatz = str(identity["selected_ansatz_id"])
        qubits = int(parameters["qubits_pca"])
        if variant == "swap_4_and_6_qubit_PCA_at_fixed_other_settings":
            qubits = int(variants[variant]["qubit_mapping"][qubits])
            parameters["qubits_pca"] = qubits
        else:
            ansatz = str(variants[variant]["executable_ansatz_id"])
        prepared = runner._prepare_fold(block=qnn["feature_block"], fold_tuple=folds[identity["fold_id"]], qubits=qubits)
        results.append(_execute_prepared_model_task(
            output_dir=output_dir, runner=runner, plan_task=task, prepared=prepared,
            parameters=parameters, family="qnn",
            source_configuration_id=qnn["configuration_id"],
            training_seed=int(identity["training_seed"]),
            y_train=prepared.train["target_label"].to_numpy(dtype=np.int64),
            y_validation=prepared.validation["target_label"].to_numpy(dtype=np.int64),
            selected_ansatz_id=ansatz,
        ))
    return _phase_manifest(output_dir, "robustness_qnn", selected, results)


def _phase_manifest(
    output_dir: Path, phase: str, tasks: Sequence[Mapping[str, Any]], results: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    complete = sum(result["status"] == "COMPLETE" for result in results)
    manifest = {
        "schema_version": 1, "phase": phase,
        "status": "COMPLETE" if len(results) == len(tasks) and all(result["status"] in TERMINAL for result in results) else "INCOMPLETE",
        "planned_tasks": len(tasks), "terminal_tasks": len(results),
        "complete_tasks": complete, "failed_tasks": len(results) - complete,
        "task_result_references": [str(_task_result_path(output_dir, task).relative_to(output_dir)) for task in tasks],
        "protected_feature_years_opened": False,
        "may_change_primary_selection": False,
    }
    atomic_write_json(output_dir / "phase_manifests" / f"{phase}.json", manifest)
    return manifest


def _require_terminal_phase(output_dir: Path, phase: str) -> None:
    path = output_dir / "phase_manifests" / f"{phase}.json"
    _require(path.is_file(), f"Required preceding phase is missing: {phase}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _require(manifest.get("status") == "COMPLETE", f"Required phase is not terminal: {phase}")
    _require(
        int(manifest.get("planned_tasks", -1))
        == int(manifest.get("terminal_tasks", -2)),
        f"Required phase is not fully accounted for: {phase}",
    )


def _seeds(representative: Mapping[str, Any]) -> list[int]:
    value = representative["training_seed"]
    if isinstance(value, int):
        return [value]
    _require(value == "AVERAGED_20260818_20260819_20260820", "Unexpected representative seed identity.")
    return [20260818, 20260819, 20260820]


def _source_checkpoints(
    representative: Mapping[str, Any], seeds: Sequence[int], fold_id: str
) -> tuple[list[str], list[str]]:
    paths: list[str] = []
    identities: list[str] = []
    for seed in seeds:
        fold_dir = (
            ROOT / "data/model_runs/post_coarse_v1_3_0/candidate_results"
            / str(representative["stage"]) / str(representative["family"])
            / str(representative["configuration_id"])
            / str(representative["feature_block"]).replace("+", "_")
            / f"seed_{seed}" / fold_id
        )
        manifest_path = fold_dir / "result_manifest.json"
        checkpoint_path = fold_dir / "checkpoint.pt"
        _require(manifest_path.is_file() and checkpoint_path.is_file(), f"Missing exact checkpoint: {fold_dir}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        _require(manifest.get("status") == "COMPLETE", f"Source fold is incomplete: {fold_dir}")
        paths.append(str(checkpoint_path))
        identities.append(str(manifest["task_identity_sha256"]))
    return paths, identities


def _pca_arrays(
    runner: ProductionExperimentRunner, block: str, qubits: int, fold_id: str
) -> dict[str, np.ndarray]:
    path = runner.output_dir / "pca" / block.replace("+", "_") / f"q{qubits}" / f"{fold_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "pca_components": np.asarray([[float.fromhex(value) for value in row] for row in payload["components_float64_hex"]]),
        "pca_explained_variance": np.asarray([float.fromhex(value) for value in payload["explained_variance_float64_hex"]]),
        "pca_mean": np.asarray([float.fromhex(value) for value in payload["pca_mean_float64_hex"]]),
        "pca_scaler_mean": np.asarray([float.fromhex(value) for value in payload["component_scaler_mean_float64_hex"]]),
        "pca_scaler_scale": np.asarray([float.fromhex(value) for value in payload["component_scaler_scale_float64_hex"]]),
        "angle_multiplier": np.asarray([float.fromhex(payload["angle_multiplier_float64_hex"])]),
    }


def _run_interpretation_fold(
    *, output_dir: Path, runner: ProductionExperimentRunner,
    plan_task: Mapping[str, Any], representative: Mapping[str, Any], fold_id: str,
    folds: Mapping[str, Any], config: Mapping[str, Any],
) -> dict[str, Any]:
    family = str(representative["family"])
    block = str(representative["feature_block"])
    base = runner._prepare_fold(block=block, fold_tuple=folds[fold_id])
    arrays: dict[str, np.ndarray] = {
        "x_train_base": base.x_train, "x_validation_base": base.x_validation,
        "y_train": base.train["target_label"].to_numpy(dtype=np.int64),
        "y_validation": base.validation["target_label"].to_numpy(dtype=np.int64),
        "sample_weight": runner._sample_weight(
            base.train["target_label"].to_numpy(dtype=np.int64),
            str(representative["parameters"].get("imbalance", "none")),
        ),
        "cluster_codes": pd.Categorical(base.validation["economic_group_id"].astype(str)).codes.astype(np.int64),
    }
    qubits: int | None = None
    if family == "qnn":
        qubits = int(representative["parameters"]["qubits_pca"])
        runner._prepare_fold(block=block, fold_tuple=folds[fold_id], qubits=qubits)
        arrays.update(_pca_arrays(runner, block, qubits, fold_id))
    seeds = _seeds(representative)
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
        "action": action, "family": family,
        "parameters": representative["parameters"], "source_stage": representative["stage"],
        "seeds": seeds, "fold_id": fold_id,
        "model_feature_names": list(base.predictor_names) if family != "qnn" else [f"pca_angle_{index + 1}" for index in range(int(qubits or 0))],
    }
    interpretation = config["secondary_development_execution"]["interpretation"]
    if action == "grouped_permutation":
        originals = list(features_for_blocks(BLOCK_PARTS[block]))
        task.update({
            "feature_names": originals,
            "feature_groups": [[index, index + len(originals)] for index in range(len(originals))],
            "repetitions": interpretation["common_permutation"]["repetitions"],
            "permutation_seed": interpretation["common_permutation"]["seed"],
        })
    elif action == "detailed_tree_shap":
        task.update({
            "background_rows_max": interpretation["tree_shap"]["background_train_rows_max"],
            "oof_rows_max": interpretation["tree_shap"]["oof_rows_per_fold_max"],
        })
    elif action == "detailed_mlp_ig":
        task.update({
            "oof_rows_max": interpretation["mlp_integrated_gradients"]["oof_rows_per_fold_max"],
            "steps": interpretation["mlp_integrated_gradients"]["steps"],
        })
    elif action == "detailed_qnn_sensitivity":
        task["oof_rows_max"] = interpretation["qnn_sensitivity"]["oof_rows_per_fold_max"]
    if family in {"pytorch_mlp", "qnn"}:
        checkpoints, checkpoint_ids = _source_checkpoints(representative, seeds, fold_id)
        task["checkpoint_paths"] = checkpoints
        task["checkpoint_task_identity_sha256"] = checkpoint_ids
        if family == "qnn":
            task["selected_ansatz_id"] = "ROT_CNOT_RING"
            task["device_name"] = runner.contract["qnn_executable_identity"]["device_identity"]["name"]
    fold_dir = output_dir / "task_artifacts" / plan_task["task_identity_sha256"] / fold_id
    fold_dir.mkdir(parents=True, exist_ok=True)
    arrays_path = fold_dir / "interpretation_arrays.npz"
    np.savez(arrays_path, **arrays)
    task_sha = canonical_sha256(task)
    task_path = fold_dir / "interpretation_task.json"
    result_path = fold_dir / "interpretation_result.json"
    payload = {
        "worker_mode": "interpretation", "interpretation_task": task,
        "interpretation_task_sha256": task_sha, "arrays_path": str(arrays_path),
        "result_path": str(result_path),
    }
    atomic_write_json(task_path, payload)
    role_python = QNN_PYTHON if family in {"pytorch_mlp", "qnn"} else CLASSICAL_PYTHON
    environment = os.environ.copy()
    environment.update({
        "PYTHONPATH": str(ROOT), "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
    })
    completed = subprocess.run(
        [str(role_python), "-m", "src.modeling.secondary_analysis_execution_worker", "--task", str(task_path)],
        cwd=ROOT, env=environment, capture_output=True, text=True,
        timeout=43200 if family == "qnn" else 14400, check=False,
    )
    _require(result_path.is_file(), f"Interpretation worker produced no result: {family}/{fold_id}")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["returncode"] = completed.returncode
    result["stderr_sha256"] = hashlib.sha256(completed.stderr.encode()).hexdigest()
    if result.get("status") == "COMPLETE":
        arrays_path.unlink(missing_ok=True)
    return result


def execute_interpretability(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> dict[str, Any]:
    if not synthetic:
        _require_terminal_phase(output_dir, "pca_matched_controls")
    config, schedule, tasks, runner, _sample, folds = _preflight_context(config_path, output_dir, synthetic=synthetic)
    selected = [task for task in tasks if task["task_identity"]["stage"] == "interpretability"]
    reps = schedule["representatives"]
    results: list[dict[str, Any]] = []
    for plan_task in selected:
        existing = _existing_task_result(output_dir, plan_task)
        if existing is not None:
            results.append(existing)
            continue
        identity = plan_task["task_identity"]
        representative = reps[str(identity["family"])]
        fold_results = []
        for fold_id in folds:
            try:
                fold_results.append(_run_interpretation_fold(
                    output_dir=output_dir, runner=runner, plan_task=plan_task,
                    representative=representative, fold_id=fold_id, folds=folds,
                    config=config,
                ))
            except Exception as error:
                fold_results.append({"status": "EXCEPTION_INVALID", "failure_code": type(error).__name__, "fold_id": fold_id})
        complete = all(result.get("status") == "COMPLETE" for result in fold_results)
        result = {
            "schema_version": 1, "task_identity": identity,
            "task_identity_sha256": plan_task["task_identity_sha256"],
            "status": "COMPLETE" if complete else "METHOD_FAILED",
            "failure_code": None if complete else "INTERPRETATION_FOLD_FAILED",
            "source_authority_sha256": file_sha256(config_path),
            "fold_results": fold_results,
            "project_data_read": not synthetic, "project_model_fit_performed": family_requires_refit(str(identity["family"])),
            "protected_feature_years_opened": False, "may_change_primary_selection": False,
        }
        atomic_write_json(_task_result_path(output_dir, plan_task), result)
        results.append(result)
    return _phase_manifest(output_dir, "interpretability", selected, results)


def family_requires_refit(family: str) -> bool:
    return family not in {"pytorch_mlp", "qnn"}


def create_report(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = load_execution_config(config_path)
    verify_static_authority(config)
    schedule, tasks = frozen_schedule(config)
    results = []
    missing = []
    for task in tasks:
        path = _task_result_path(output_dir, task)
        if path.is_file():
            results.append(json.loads(path.read_text(encoding="utf-8")))
        else:
            missing.append(task["task_identity_sha256"])
    counts = {status: sum(result.get("status") == status for result in results) for status in sorted(TERMINAL)}
    report = {
        "schema_version": 1, "id": "secondary_development_results_v1_1_0",
        "status": "COMPLETE" if not missing and len(results) == 96 else "INCOMPLETE",
        "planned_tasks": 96, "terminal_tasks": len(results), "missing_task_ids": missing,
        "terminal_status_counts": counts, "task_counts": schedule["counts"],
        "final_primary_ranking_unchanged": True, "may_change_primary_selection": False,
        "protected_feature_years_opened": False,
    }
    report_sha = atomic_write_json(output_dir / "secondary_development_report.json", report)
    phase_hashes = {}
    for path in sorted((output_dir / "phase_manifests").glob("*.json")):
        phase_hashes[path.name] = file_sha256(path)
    manifest = {
        "schema_version": 1, "id": "secondary_development_execution_v1_1_0",
        "status": report["status"], "authority": verify_static_authority(config),
        "phase_manifest_sha256": phase_hashes,
        "secondary_report_sha256": report_sha,
        "final_primary_ranking_unchanged": True,
        "protected_feature_years_opened": False,
    }
    atomic_write_json(output_dir / "run_manifest.json", manifest)
    return manifest


def package_status(config_path: Path) -> dict[str, Any]:
    config = load_execution_config(config_path)
    verified = verify_static_authority(config)
    schedule, tasks = frozen_schedule(config)
    return {
        "status": "PASS", "id": config["secondary_development_execution"]["id"],
        "package_state": config["secondary_development_execution"]["status"],
        "verified_static_authorities": len(verified), "planned_tasks": len(tasks),
        "task_counts": schedule["counts"], "project_data_read": False,
        "project_model_fit_performed": False, "protected_feature_years_opened": False,
    }


def write_plan(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = load_execution_config(config_path)
    verify_static_authority(config)
    schedule, tasks = frozen_schedule(config)
    plan = {
        "schema_version": 1, "id": "secondary_development_execution_plan_v1_1_0",
        "status": "PLAN_ONLY_NO_PROJECT_DATA_ACCESS", "task_counts": schedule["counts"],
        "tasks": tasks, "execution_config_sha256": file_sha256(config_path),
        "project_data_read": False, "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }
    atomic_write_json(output_dir / "secondary_analysis_execution_plan.json", plan)
    return plan


def synthetic_smoke(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config, schedule, tasks, runner, _sample, folds = _preflight_context(config_path, output_dir, synthetic=True)
    representatives = schedule["representatives"]
    checks: list[dict[str, Any]] = []
    winner = representatives["xgboost"]
    fold_id = "fold_2015"
    for variant in config["secondary_development_execution"]["preprocessing_variants"]:
        prepared = _custom_prepared_fold(
            runner=runner, output_dir=output_dir, fold_tuple=folds[fold_id],
            block=winner["feature_block"], variant=variant,
        )
        checks.append({"id": f"preprocessing::{variant}", "status": "PASS", "train_rows": len(prepared.train), "validation_rows": len(prepared.validation)})
    qnn_variants = config["secondary_development_execution"]["qnn_structural_variants"]
    _require(qnn_variants["replace_entangling_gates_with_identity"]["executable_ansatz_id"] == "ROT_IDENTITY", "QNN identity route changed.")
    checks.append({"id": "qnn_structural_routes", "status": "PASS", "variants": len(qnn_variants)})
    _require(len(tasks) == 96, "Synthetic smoke roster mismatch.")
    checks.append({"id": "frozen_96_task_roster", "status": "PASS"})
    result = {
        "schema_version": 1, "status": "PASS", "checks": checks,
        "project_data_read": False, "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }
    atomic_write_json(output_dir / "secondary_execution_synthetic_smoke.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=(
        "status", "plan", "smoke", "preflight", "pca-controls", "interpretability",
        "robustness-classical", "robustness-qnn", "report", "all",
    ))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config_path = args.config.resolve()
    if args.output_dir is not None:
        output_dir = args.output_dir.resolve()
    elif args.mode in {"plan", "smoke"}:
        output_dir = (
            ROOT / f"data/model_runs/secondary_development_v1_1_0_{args.mode}"
        ).resolve()
    else:
        output_dir = (ROOT / "data/model_runs/secondary_development_v1_1_0").resolve()
    _require(config_path.is_relative_to(ROOT), "Config must be inside repository.")
    if args.mode == "status":
        result = package_status(config_path)
    elif args.mode == "plan":
        result = write_plan(config_path, output_dir)
    elif args.mode == "smoke":
        result = synthetic_smoke(config_path, output_dir)
    elif args.mode == "preflight":
        config, schedule, tasks, _runner, _sample, folds = _preflight_context(config_path, output_dir)
        result = {"status": "PASS", "planned_tasks": len(tasks), "fold_ids": list(folds), "project_data_read": True, "project_model_fit_performed": False, "protected_feature_years_opened": False}
    elif args.mode == "pca-controls":
        result = execute_pca_controls(config_path, output_dir)
    elif args.mode == "interpretability":
        result = execute_interpretability(config_path, output_dir)
    elif args.mode == "robustness-classical":
        result = execute_classical_robustness(config_path, output_dir)
    elif args.mode == "robustness-qnn":
        result = execute_qnn_robustness(config_path, output_dir)
    elif args.mode == "report":
        result = create_report(config_path, output_dir)
    else:
        execute_pca_controls(config_path, output_dir)
        execute_interpretability(config_path, output_dir)
        execute_classical_robustness(config_path, output_dir)
        execute_qnn_robustness(config_path, output_dir)
        result = create_report(config_path, output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

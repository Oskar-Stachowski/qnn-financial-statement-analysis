"""Contract-bound production orchestration for the frozen model stage.

The controller is deliberately separated from estimator workers.  It is the only
component allowed to assemble the frozen 2011--2020 sample, create point-in-time
folds, fit fold-train preprocessing/PCA, rank candidates, aggregate seeds, and
freeze calibration/threshold artifacts.  Estimator workers receive numeric
matrices only and cannot read project data.

Importing this module never reads project data and never fits a model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Mapping, Protocol, Sequence
import warnings

import numpy as np
import pandas as pd
import yaml
from scipy.special import expit
from sklearn.decomposition import PCA
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler

from src.modeling.model_execution_contract import (
    align_and_average_raw_scores,
    calibration_plan,
    candidate_fold_aggregate_status,
    canonical_candidate_index,
    canonical_json,
    canonical_sha256,
    file_sha256,
    load_contract,
    load_registry,
    max_f1_threshold,
    merge_coarse_refinement_results,
    rank_candidates,
    select_confirmation_candidates,
    select_qnn_ansatz,
    select_qnn_confirmation_candidates,
    select_refinement_families,
    validate_contract,
)
from src.modeling.preprocessing import FinancialPreprocessor, features_for_blocks
from src.modeling.temporal_cv import iter_point_in_time_folds


ROOT = Path(__file__).resolve().parents[2]
RUNNER_CONFIG_PATH = ROOT / "configs/production_experiment_runner_v1_0_0.yaml"
PIPELINE_CONFIG_PATH = ROOT / "configs/supervised_ml_pipeline_v1_3_0_timezone_fix.yaml"
BLOCKS: tuple[str, ...] = ("L", "L+D", "L+D+R")
BLOCK_PARTS: dict[str, tuple[str, ...]] = {
    "L": ("L",),
    "L+D": ("L", "D"),
    "L+D+R": ("L", "D", "R"),
}
BLOCK_AGNOSTIC = "BLOCK_AGNOSTIC"
REQUIRED_SAMPLE_METADATA: tuple[str, ...] = (
    "research_universe_company_year_id",
    "feature_year",
    "economic_group_id",
    "prediction_timestamp",
    "target_available_at",
    "target_label",
)


class RunnerIntegrityError(RuntimeError):
    """A frozen hash, identity, membership, or schema does not match."""


class ProtectedDataAccessError(RunnerIntegrityError):
    """An input could expose a protected feature year before its gate."""


class TechnicalExecutionError(RuntimeError):
    """A fold task failed with a contract-defined technical status."""

    def __init__(self, status: str, failure_code: str, message: str = "") -> None:
        super().__init__(message or failure_code)
        self.status = status
        self.failure_code = failure_code


def current_git_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return "UNKNOWN"
    value = completed.stdout.strip()
    return value if value else "UNKNOWN"


def controller_runtime_metadata(root: Path) -> dict[str, Any]:
    distributions = (
        "numpy",
        "pandas",
        "scipy",
        "scikit-learn",
        "xgboost",
        "torch",
        "PennyLane",
    )
    versions: dict[str, str | None] = {}
    for distribution in distributions:
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = None
    return {
        "sys_executable": os.path.abspath(sys.executable),
        "python_version": platform.python_version(),
        "main_library_versions": versions,
        "git_commit": current_git_commit(root),
    }


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
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


def atomic_write_json(path: Path, value: Any) -> str:
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    atomic_write_bytes(path, payload)
    return hashlib.sha256(payload).hexdigest()


class QNNResourceLedger:
    """Thread-safe ledger enforcing the preregistered global QNN caps."""

    def __init__(
        self,
        path: Path,
        *,
        maximum_attempts: int,
        maximum_runtime_seconds: float,
    ) -> None:
        self.path = path
        self._lock = threading.RLock()
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                int(payload.get("maximum_attempts", -1)) != int(maximum_attempts)
                or float(payload.get("maximum_runtime_seconds", -1.0))
                != float(maximum_runtime_seconds)
            ):
                raise RunnerIntegrityError("Existing QNN resource ledger limits differ.")
            self.payload = payload
            interrupted = 0
            for entry in self.payload["attempts"]:
                if entry.get("status") == "STARTED":
                    entry["status"] = "INTERRUPTED"
                    entry["outcome"] = "CONTROLLER_RESTART"
                    interrupted += 1
            if interrupted:
                self.payload["interrupted_attempts"] = int(
                    self.payload.get("interrupted_attempts", 0)
                ) + interrupted
                self._write()
        else:
            self.payload = {
                "schema_version": 1,
                "maximum_attempts": int(maximum_attempts),
                "maximum_runtime_seconds": float(maximum_runtime_seconds),
                "started_attempts": 0,
                "completed_attempts": 0,
                "interrupted_attempts": 0,
                "total_runtime_seconds": 0.0,
                "limit_reached": False,
                "limit_reason": None,
                "attempts": [],
            }
            self._write()

    @property
    def remaining_runtime_seconds(self) -> float:
        with self._lock:
            return max(
                0.0,
                float(self.payload["maximum_runtime_seconds"])
                - float(self.payload["total_runtime_seconds"]),
            )

    @property
    def limit_reached(self) -> bool:
        with self._lock:
            return bool(self.payload.get("limit_reached", False))

    @property
    def limit_reason(self) -> str | None:
        with self._lock:
            value = self.payload.get("limit_reason")
            return str(value) if value is not None else None

    def _write(self) -> None:
        with self._lock:
            atomic_write_json(self.path, self.payload)

    def _mark_limit(self, reason: str) -> None:
        with self._lock:
            self.payload["limit_reached"] = True
            self.payload["limit_reason"] = reason
            self._write()

    def begin_attempt(self, retry_reason: str) -> int | None:
        with self._lock:
            if int(self.payload["started_attempts"]) >= int(
                self.payload["maximum_attempts"]
            ):
                self._mark_limit("MAXIMUM_TOTAL_FIT_ATTEMPTS")
                return None
            if self.remaining_runtime_seconds <= 0.0:
                self._mark_limit("MAXIMUM_TOTAL_RUNTIME")
                return None
            global_attempt = int(self.payload["started_attempts"]) + 1
            self.payload["started_attempts"] = global_attempt
            self.payload["attempts"].append(
                {
                    "global_attempt": global_attempt,
                    "retry_reason": retry_reason,
                    "status": "STARTED",
                    "runtime_seconds": None,
                    "outcome": None,
                }
            )
            self._write()
            return global_attempt

    def finish_attempt(
        self,
        global_attempt: int,
        *,
        runtime_seconds: float,
        outcome: str,
    ) -> None:
        with self._lock:
            entry = next(
                item
                for item in self.payload["attempts"]
                if int(item["global_attempt"]) == int(global_attempt)
            )
            if entry["status"] != "STARTED":
                raise RunnerIntegrityError("QNN resource attempt was already finalized.")
            entry["status"] = "COMPLETED"
            entry["runtime_seconds"] = float(runtime_seconds)
            entry["outcome"] = str(outcome)
            self.payload["completed_attempts"] = int(
                self.payload["completed_attempts"]
            ) + 1
            self.payload["total_runtime_seconds"] = float(
                self.payload["total_runtime_seconds"]
            ) + float(runtime_seconds)
            if float(self.payload["total_runtime_seconds"]) > float(
                self.payload["maximum_runtime_seconds"]
            ):
                self.payload["limit_reached"] = True
                self.payload["limit_reason"] = "MAXIMUM_TOTAL_RUNTIME"
            self._write()


def membership_sha256(values: Sequence[Any] | pd.Series) -> str:
    normalized = [str(value) for value in values]
    if len(normalized) != len(set(normalized)):
        raise RunnerIntegrityError("Membership identity contains duplicates.")
    payload = "".join(f"{value}\n" for value in sorted(normalized))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def float64_vector_sha256(values: Sequence[float]) -> str:
    array = np.asarray(values, dtype=">f8")
    if array.ndim != 1 or not np.isfinite(array).all():
        raise RunnerIntegrityError("Expected a finite one-dimensional float64 vector.")
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def canonical_timestamp(value: Any) -> str:
    timestamp = pd.to_datetime(value, errors="raise", utc=True)
    return timestamp.isoformat()


def load_runner_config(path: Path = RUNNER_CONFIG_PATH) -> dict[str, Any]:
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    extension = parsed.get("extends") if isinstance(parsed, dict) else None
    if isinstance(extension, Mapping):
        base_path = (ROOT / str(extension["path"])).resolve()
        if not base_path.is_file() or file_sha256(base_path) != str(
            extension["sha256"]
        ):
            raise RunnerIntegrityError("Runner base configuration SHA-256 mismatch.")
        base = yaml.safe_load(base_path.read_text(encoding="utf-8"))
        if not isinstance(base, dict):
            raise RunnerIntegrityError("Runner base configuration is invalid.")

        def merge(base_value: Any, overlay_value: Any) -> Any:
            if isinstance(base_value, Mapping) and isinstance(overlay_value, Mapping):
                result = dict(base_value)
                for key, value in overlay_value.items():
                    result[key] = merge(result.get(key), value)
                return result
            return overlay_value

        parsed = merge(base, {key: value for key, value in parsed.items() if key != "extends"})
    runner = parsed.get("runner", {}) if isinstance(parsed, dict) else {}
    if (
        not isinstance(parsed, dict)
        or runner.get("id") != "production_experiment_runner"
        or runner.get("version") not in {"1.0.0", "1.0.1", "1.0.2"}
    ):
        raise RunnerIntegrityError("Unexpected production runner configuration.")
    return parsed


@dataclass(frozen=True)
class InputExpectations:
    membership_n: int
    membership_sha256: str
    folds: Mapping[str, Mapping[str, Any]]
    source_kind: str = "frozen_project_train"


@dataclass(frozen=True)
class FoldTask:
    stage: str
    family: str
    feature_block: str
    configuration_id: str
    parameters: Mapping[str, Any]
    training_seed: int
    fold_id: str
    validation_feature_year: int
    selected_ansatz_id: str | None
    train_membership_sha256: str
    validation_membership_sha256: str
    preprocessing_sha256: str
    pca_sha256_if_applicable: str | None
    software_environment_role: str
    checkpoint_identity: Mapping[str, Any]

    @property
    def identity(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def identity_sha256(self) -> str:
        return canonical_sha256(self.identity)


@dataclass
class FoldExecution:
    status: str
    raw_scores: np.ndarray | None
    failure_code: str | None
    software_environment_sha256: str
    device_identity: Mapping[str, Any] | str
    attempts: list[dict[str, Any]]


class FoldExecutor(Protocol):
    """Numeric-only execution boundary; implementations never receive DataFrames."""

    synthetic_only: bool

    def execute(
        self,
        task: FoldTask,
        *,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_validation: np.ndarray,
        sample_weight: np.ndarray,
        checkpoint_path: Path,
        timeout_seconds: int,
    ) -> FoldExecution: ...


class SyntheticFoldExecutor:
    """Fast deterministic estimator used only by synthetic integration tests."""

    synthetic_only = True
    environment_sha256 = canonical_sha256(
        {"role": "synthetic_orchestration_test", "project_data": False, "version": 1}
    )
    environment_hashes = {
        "classical": environment_sha256,
        "qnn_mlp": environment_sha256,
    }
    runtime_metadata_by_role = {
        "synthetic": {
            "sys_executable": os.path.abspath(sys.executable),
            "python_version": platform.python_version(),
            "main_library_versions": {
                "numpy": np.__version__,
                "pandas": pd.__version__,
            },
        }
    }

    def execute(
        self,
        task: FoldTask,
        *,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_validation: np.ndarray,
        sample_weight: np.ndarray,
        checkpoint_path: Path,
        timeout_seconds: int,
    ) -> FoldExecution:
        del checkpoint_path, timeout_seconds
        y = np.asarray(y_train, dtype=np.float64)
        if task.family == "dummy_prior":
            prior = float(np.mean(y))
            prior = min(max(prior, 1e-7), 1.0 - 1e-7)
            scores = np.full(len(x_validation), math.log(prior / (1.0 - prior)))
        else:
            train = np.asarray(x_train, dtype=np.float64)
            validation = np.asarray(x_validation, dtype=np.float64)
            design = np.column_stack([train, np.ones(len(train), dtype=np.float64)])
            weighted_design = design * np.sqrt(sample_weight)[:, None]
            centered_target = (y - np.average(y, weights=sample_weight)) * np.sqrt(
                sample_weight
            )
            coefficient = np.linalg.pinv(weighted_design, rcond=1e-10) @ centered_target
            scores = np.column_stack(
                [validation, np.ones(len(validation), dtype=np.float64)]
            ) @ coefficient
            # This does not alter ordering.  It makes seed/config identity observable
            # while deliberately producing metric ties that exercise frozen tie rules.
            identity_offset = int(task.identity_sha256[:12], 16) / float(16**12)
            scores = scores + identity_offset * 1e-9
        return FoldExecution(
            status="COMPLETE",
            raw_scores=np.asarray(scores, dtype=np.float64),
            failure_code=None,
            software_environment_sha256=self.environment_sha256,
            device_identity="synthetic_cpu",
            attempts=[{"attempt": 1, "outcome": "COMPLETE", "synthetic_only": True}],
        )


class SubprocessFoldExecutor:
    """Dispatch one fold fit to the frozen classical or QNN/MLP interpreter."""

    synthetic_only = False
    qnn_ledger: QNNResourceLedger | None = None

    def __init__(
        self,
        *,
        root: Path,
        classical_python: Path,
        qnn_python: Path,
        runner_config_path: Path = RUNNER_CONFIG_PATH,
        contract_path: Path | None = None,
    ) -> None:
        self._shutdown_requested = threading.Event()
        self.root = root.resolve()
        self.runner_config_path = runner_config_path.resolve()
        runner_config = load_runner_config(self.runner_config_path)

        contract_authority = runner_config["authority"]["execution_contract"]
        configured_contract_path = (
            self.root / str(contract_authority["path"])
        ).resolve()
        self.contract_path = (
            contract_path or configured_contract_path
        ).resolve()

        if self.contract_path != configured_contract_path:
            raise RunnerIntegrityError(
                "Executor contract path differs from runner authority."
            )
        if (
            not self.contract_path.is_file()
            or file_sha256(self.contract_path)
            != str(contract_authority["sha256"])
        ):
            raise RunnerIntegrityError(
                "Executor execution-contract SHA-256 mismatch."
            )

        environment_authority = runner_config["authority"]["model_environments"]
        environment_config_path = (
            self.root / str(environment_authority["path"])
        ).resolve()
        if (
            not environment_config_path.is_file()
            or file_sha256(environment_config_path)
            != str(environment_authority["sha256"])
        ):
            raise RunnerIntegrityError(
                "Model-environments configuration SHA-256 mismatch."
            )

        environment_config = yaml.safe_load(
            environment_config_path.read_text(encoding="utf-8")
        )
        self.interpreters = {
            # Do not resolve venv interpreter symlinks: resolving them would bypass
            # the venv and silently execute against the base pyenv installation.
            "classical": Path(os.path.abspath(classical_python)),
            "qnn_mlp": Path(os.path.abspath(qnn_python)),
        }
        for role, interpreter in self.interpreters.items():
            if not interpreter.is_file():
                raise RunnerIntegrityError(f"Missing {role} interpreter: {interpreter}")
        self.lockfiles: dict[str, Path] = {}
        expected_environment_hashes: dict[str, str] = {}
        for role in self.interpreters:
            specification = environment_config["environments"][role]
            lockfile = (self.root / specification["lockfile"]).resolve()
            if not lockfile.is_file() or file_sha256(lockfile) != specification[
                "lockfile_sha256"
            ]:
                raise RunnerIntegrityError(f"{role} lockfile SHA-256 mismatch.")
            self.lockfiles[role] = lockfile
            expected_environment_hashes[role] = str(
                specification["software_environment_sha256"]
            )
        self.environment_hashes: dict[str, str] = {}
        self.runtime_metadata_by_role: dict[str, dict[str, Any]] = {}
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONPATH": str(self.root),
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "VECLIB_MAXIMUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            }
        )
        for role, interpreter in self.interpreters.items():
            completed = subprocess.run(
                [
                    str(interpreter),
                    "-m",
                    "src.modeling.environment_audit",
                    "--role",
                    role,
                    "--smoke-imports",
                    "--contract",
                    str(self.contract_path),
                    "--lockfile",
                    str(self.lockfiles[role]),
                ],
                cwd=self.root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RunnerIntegrityError(
                    f"{role} environment audit failed before execution "
                    f"(returncode={completed.returncode})\n"
                    f"STDOUT:\n{completed.stdout}\n"
                    f"STDERR:\n{completed.stderr}"
                )
            report = json.loads(completed.stdout)
            if report.get("status") != "READY":
                raise RunnerIntegrityError(f"{role} environment is not frozen-ready.")
            lock_verification = report.get("lock_verification", {})
            if (
                lock_verification.get("status") != "EXACT_MATCH"
                or lock_verification.get("lockfile_sha256")
                != environment_config["environments"][role]["lockfile_sha256"]
            ):
                raise RunnerIntegrityError(
                    f"{role} installed distributions do not exactly match the lockfile."
                )
            actual_environment_hash = str(report["software_environment_sha256"])
            if actual_environment_hash != expected_environment_hashes[role]:
                raise RunnerIntegrityError(f"{role} runtime environment identity mismatch.")
            self.environment_hashes[role] = actual_environment_hash
            runtime_identity = report["runtime_identity"]
            self.runtime_metadata_by_role[role] = {
                "sys_executable": str(interpreter),
                "python_version": str(runtime_identity["python_version"]),
                "main_library_versions": dict(runtime_identity["package_versions"]),
            }

    def configure_qnn_ledger(
        self,
        path: Path,
        *,
        maximum_attempts: int,
        maximum_runtime_seconds: float,
    ) -> None:
        self.qnn_ledger = QNNResourceLedger(
            path,
            maximum_attempts=maximum_attempts,
            maximum_runtime_seconds=maximum_runtime_seconds,
        )

    def request_shutdown(self) -> None:
        event = getattr(self, "_shutdown_requested", None)
        if event is None:
            event = threading.Event()
            self._shutdown_requested = event
        event.set()

    def _is_shutdown_requested(self) -> bool:
        event = getattr(self, "_shutdown_requested", None)
        return bool(event is not None and event.is_set())

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
            str(self.interpreters[task.software_environment_role]),
            "-m",
            "src.modeling.production_worker",
            "--task",
            str(task_path),
        ]
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONPATH": str(self.root),
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "VECLIB_MAXIMUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            }
        )
        audit: dict[str, Any] = {
            "attempt": attempt,
            "resume": resume,
            "command_sha256": canonical_sha256(command),
        }
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            audit["outcome"] = "TIMEOUT_INVALID"
            return FoldExecution(
                "TIMEOUT_INVALID", None, "TIMEOUT", "", "unknown", [audit]
            ), audit
        except OSError:
            audit["outcome"] = "INFRASTRUCTURE_FAILURE"
            return FoldExecution(
                "INFRASTRUCTURE_FAILURE",
                None,
                "TEMPORARY_FILESYSTEM_IO_FAILURE",
                "",
                "unknown",
                [audit],
            ), audit
        audit["returncode"] = completed.returncode
        audit["stderr_sha256"] = hashlib.sha256(completed.stderr.encode()).hexdigest()
        if completed.returncode < 0:
            audit["outcome"] = "INFRASTRUCTURE_FAILURE"
            return FoldExecution(
                "INFRASTRUCTURE_FAILURE",
                None,
                "WORKER_PROCESS_LOST_BY_OS_SIGNAL",
                "",
                "unknown",
                [audit],
            ), audit
        if not result_path.is_file():
            audit["outcome"] = "EXCEPTION_INVALID"
            return FoldExecution(
                "EXCEPTION_INVALID",
                None,
                "DETERMINISTIC_LIBRARY_EXCEPTION",
                "",
                "unknown",
                [audit],
            ), audit
        worker = json.loads(result_path.read_text(encoding="utf-8"))
        if worker.get("task_identity_sha256") != task.identity_sha256:
            raise RunnerIntegrityError("Worker returned a mismatched task identity.")
        status = str(worker["status"])
        scores: np.ndarray | None = None
        if status == "COMPLETE":
            if not score_path.is_file() or file_sha256(score_path) != worker.get(
                "raw_scores_file_sha256"
            ):
                raise RunnerIntegrityError("Worker raw-score artifact hash mismatch.")
            scores = np.load(score_path, allow_pickle=False).astype(np.float64)
        audit["outcome"] = status
        execution = FoldExecution(
            status=status,
            raw_scores=scores,
            failure_code=worker.get("failure_code"),
            software_environment_sha256=str(worker.get("software_environment_sha256", "")),
            device_identity=worker.get("device_identity", "unknown"),
            attempts=[audit],
        )
        return execution, audit

    def execute(
        self,
        task: FoldTask,
        *,
        x_train: np.ndarray,
        y_train: np.ndarray,
        x_validation: np.ndarray,
        sample_weight: np.ndarray,
        checkpoint_path: Path,
        timeout_seconds: int,
    ) -> FoldExecution:
        checkpoint_capable = task.family in {"pytorch_mlp", "qnn"}
        work = checkpoint_path.parent / "worker_io"
        work.mkdir(parents=True, exist_ok=True)
        attempts: list[dict[str, Any]] = []
        cumulative_started = time.monotonic()

        def remaining_timeout() -> int:
            remaining = float(timeout_seconds) - (time.monotonic() - cumulative_started)
            return max(0, math.ceil(remaining))

        def resource_limit_result(reason: str) -> tuple[FoldExecution, dict[str, Any]]:
            audit = {
                "attempt": len(attempts) + 1,
                "outcome": "INFRASTRUCTURE_EXHAUSTED",
                "retry_reason": reason,
                "qnn_global_resource_limit": True,
            }
            return (
                FoldExecution(
                    "INFRASTRUCTURE_EXHAUSTED",
                    None,
                    reason,
                    "",
                    "unknown",
                    [audit],
                ),
                audit,
            )

        def run_attempt(
            *,
            resume: bool,
            attempt: int,
            retry_reason: str,
        ) -> tuple[FoldExecution, dict[str, Any]]:
            remaining = remaining_timeout()
            if remaining <= 0:
                audit = {
                    "attempt": attempt,
                    "outcome": "TIMEOUT_INVALID",
                    "retry_reason": retry_reason,
                    "cumulative_wall_timeout": True,
                }
                return (
                    FoldExecution(
                        "TIMEOUT_INVALID", None, "TIMEOUT", "", "unknown", [audit]
                    ),
                    audit,
                )
            ledger = self.qnn_ledger if task.family == "qnn" else None
            global_attempt: int | None = None
            if ledger is not None:
                remaining = min(
                    remaining, math.floor(ledger.remaining_runtime_seconds)
                )
                if remaining <= 0:
                    ledger._mark_limit("MAXIMUM_TOTAL_RUNTIME")
                    return resource_limit_result("QNN_GLOBAL_RUNTIME_LIMIT")
                global_attempt = ledger.begin_attempt(retry_reason)
                if global_attempt is None:
                    reason = (
                        "QNN_GLOBAL_ATTEMPT_LIMIT"
                        if ledger.limit_reason == "MAXIMUM_TOTAL_FIT_ATTEMPTS"
                        else "QNN_GLOBAL_RUNTIME_LIMIT"
                    )
                    return resource_limit_result(reason)
            started = time.monotonic()
            try:
                execution, audit = self._one_attempt(
                    task,
                    x_train=x_train,
                    y_train=y_train,
                    x_validation=x_validation,
                    sample_weight=sample_weight,
                    checkpoint_path=checkpoint_path,
                    timeout_seconds=remaining,
                    resume=resume,
                    work=work,
                    attempt=attempt,
                )
            except Exception:
                if ledger is not None and global_attempt is not None:
                    ledger.finish_attempt(
                        global_attempt,
                        runtime_seconds=time.monotonic() - started,
                        outcome="RAISED_EXCEPTION",
                    )
                raise
            elapsed = time.monotonic() - started
            audit["runtime_seconds"] = elapsed
            audit["retry_reason"] = retry_reason
            if ledger is not None and global_attempt is not None:
                ledger.finish_attempt(
                    global_attempt,
                    runtime_seconds=elapsed,
                    outcome=str(audit.get("outcome", execution.status)),
                )
                audit["qnn_global_attempt"] = global_attempt
                audit["qnn_attempt_runtime_seconds"] = elapsed
            return execution, audit

        initial_resume = checkpoint_capable and checkpoint_path.is_file()
        execution, audit = run_attempt(
            resume=initial_resume,
            attempt=1,
            retry_reason=(
                "CHECKPOINT_RESUME_AFTER_CONTROLLER_RESTART"
                if initial_resume
                else "INITIAL"
            ),
        )
        attempts.append(audit)
        if self._is_shutdown_requested():
            raise InterruptedError("Fold execution interrupted by controller shutdown.")
        if initial_resume and execution.status == "CHECKPOINT_INVALID":
            quarantine = checkpoint_path.with_suffix(
                checkpoint_path.suffix + ".invalid-for-fresh-retry"
            )
            os.replace(checkpoint_path, quarantine)
            execution, audit = run_attempt(
                resume=False,
                attempt=2,
                retry_reason="FRESH_RETRY_AFTER_CHECKPOINT_IDENTITY_MISMATCH",
            )
            attempts.append(audit)
            execution.attempts = attempts
            return execution
        if execution.status != "INFRASTRUCTURE_FAILURE":
            execution.attempts = attempts
            return execution
        if checkpoint_capable and checkpoint_path.is_file():
            previous_reason = execution.failure_code or execution.status
            execution, audit = run_attempt(
                resume=True,
                attempt=2,
                retry_reason=f"CHECKPOINT_RESUME_AFTER_{previous_reason}",
            )
            attempts.append(audit)
            if self._is_shutdown_requested():
                raise InterruptedError("Fold execution interrupted by controller shutdown.")
            if execution.status not in {
                "INFRASTRUCTURE_FAILURE",
                "CHECKPOINT_INVALID",
            }:
                execution.attempts = attempts
                return execution
        # The frozen state machine permits one fresh infrastructure retry.  An
        # incompatible checkpoint is quarantined instead of silently reused.
        if checkpoint_path.exists():
            quarantine = checkpoint_path.with_suffix(
                checkpoint_path.suffix + ".invalid-for-fresh-retry"
            )
            os.replace(checkpoint_path, quarantine)
        previous_reason = execution.failure_code or execution.status
        execution, audit = run_attempt(
            resume=False,
            attempt=len(attempts) + 1,
            retry_reason=f"FRESH_RETRY_AFTER_{previous_reason}",
        )
        attempts.append(audit)
        if execution.status == "INFRASTRUCTURE_FAILURE":
            execution.status = "INFRASTRUCTURE_EXHAUSTED"
        execution.attempts = attempts
        return execution


@dataclass
class PreparedFold:
    fold_id: str
    validation_feature_year: int
    train: pd.DataFrame
    validation: pd.DataFrame
    train_membership_sha256: str
    validation_membership_sha256: str
    preprocessing_sha256: str
    pca_sha256: str | None
    x_train: np.ndarray
    x_validation: np.ndarray
    predictor_names: tuple[str, ...]


@dataclass
class CandidateExecutionResult:
    row: dict[str, Any]
    predictions: list[dict[str, Any]]


def final_eligibility_pool(
    merged_results: Sequence[CandidateExecutionResult],
    confirmed_results: Sequence[CandidateExecutionResult],
    contract: Mapping[str, Any],
    *,
    qnn_resource_limit_reached: bool = False,
) -> list[CandidateExecutionResult]:
    """Return the common final pool without dropping deterministic refinement."""

    deterministic_families = set(
        contract["confirmation"]["deterministic_exceptions"]
    )
    deterministic = [
        result
        for result in merged_results
        if result.row["family"] in deterministic_families
    ]
    confirmed = [
        result
        for result in confirmed_results
        if not (qnn_resource_limit_reached and result.row["family"] == "qnn")
    ]
    return [*deterministic, *confirmed]


class ProductionExperimentRunner:
    """Execute the frozen primary experiment without discretionary branches."""

    def __init__(
        self,
        *,
        output_dir: Path,
        executor: FoldExecutor,
        root: Path = ROOT,
        runner_config_path: Path = RUNNER_CONFIG_PATH,
        contract_path: Path | None = None,
        registry_path: Path | None = None,
    ) -> None:
        self.root = root.resolve()
        self.output_dir = output_dir.resolve()
        self.executor = executor
        self.runner_config_path = runner_config_path.resolve()
        self.runner_config = load_runner_config(self.runner_config_path)
        configured_contract = self.root / self.runner_config["authority"]["execution_contract"]["path"]
        configured_registry = self.root / self.runner_config["authority"]["candidate_registry"]["path"]
        self.contract_path = (contract_path or configured_contract).resolve()
        self.registry_path = (registry_path or configured_registry).resolve()
        self.contract = load_contract(self.contract_path)
        self.registry = load_registry(self.registry_path)
        self._prepared_cache: dict[tuple[str, str, int | None], PreparedFold] = {}
        self._state_lock = threading.RLock()
        self._environment_hashes: dict[str, str] = dict(
            getattr(executor, "environment_hashes", {})
        )
        self._runtime_metadata_sha256: str | None = None
        self._qnn_ledger: QNNResourceLedger | None = getattr(
            executor, "qnn_ledger", None
        )
        self._preflight()

    def _write_runtime_metadata(
        self, index: Sequence[Mapping[str, Any]]
    ) -> str:
        configuration_ids = list(
            dict.fromkeys(str(item["configuration_id"]) for item in index)
        )
        metadata = {
            "schema_version": 1,
            "controller": controller_runtime_metadata(self.root),
            "workers": dict(
                getattr(self.executor, "runtime_metadata_by_role", {})
            ),
            "seeds": {
                "coarse_and_refinement": int(
                    self.contract["confirmation"]["coarse_seed"]
                ),
                "confirmation": list(
                    self.contract["confirmation"]["confirmation_seeds"]
                ),
            },
            "configuration_ids": configuration_ids,
        }
        self._runtime_metadata_sha256 = atomic_write_json(
            self.output_dir / "runtime_metadata.json", metadata
        )
        return self._runtime_metadata_sha256

    def _configure_qnn_ledger(self) -> None:
        configure = getattr(self.executor, "configure_qnn_ledger", None)
        if not callable(configure):
            return
        model_stage_path = self.root / str(
            self.contract["authority"]["model_stage_v1"]["path"]
        )
        model_stage = yaml.safe_load(model_stage_path.read_text(encoding="utf-8"))
        policy = model_stage["qnn"]["resource_policy"]
        configure(
            self.output_dir / "qnn_resource_ledger.json",
            maximum_attempts=int(policy["maximum_total_fit_attempts"]),
            maximum_runtime_seconds=float(policy["maximum_total_cpu_hours"])
            * 3600.0,
        )
        self._qnn_ledger = getattr(self.executor, "qnn_ledger", None)

    def _preflight(self) -> None:
        authority = self.runner_config["authority"]
        for name, item in authority.items():
            if not isinstance(item, Mapping) or "path" not in item or "sha256" not in item:
                continue
            authority_path = (self.root / str(item["path"])).resolve()
            if not authority_path.is_file() or file_sha256(authority_path) != str(
                item["sha256"]
            ):
                raise RunnerIntegrityError(f"Runner authority SHA-256 mismatch: {name}")
        expected_contract = authority["execution_contract"]
        expected_registry = authority["candidate_registry"]
        if self.contract_path != (self.root / expected_contract["path"]).resolve():
            raise RunnerIntegrityError("Execution contract path is not canonical.")
        if self.registry_path != (self.root / expected_registry["path"]).resolve():
            raise RunnerIntegrityError("Candidate registry path is not canonical.")
        if file_sha256(self.contract_path) != str(expected_contract["sha256"]):
            raise RunnerIntegrityError("Execution contract SHA-256 mismatch.")
        if file_sha256(self.registry_path) != str(expected_registry["sha256"]):
            raise RunnerIntegrityError("Candidate registry SHA-256 mismatch.")
        validation = validate_contract(self.contract, self.registry)
        required = (
            "authority_hashes_match",
            "candidate_index_count_matches",
            "candidate_index_hash_matches",
            "software_spec_hashes_match",
        )
        if not all(validation[item] for item in required):
            raise RunnerIntegrityError(f"Frozen execution contract preflight failed: {validation}")
        configured_index_hash = self.runner_config["determinism"][
            "expanded_candidate_order_sha256"
        ]
        actual_index_hash = canonical_sha256(
            canonical_candidate_index(self.contract, self.registry)
        )
        if actual_index_hash != configured_index_hash:
            raise RunnerIntegrityError("Expanded candidate ordering hash mismatch.")
        allowlist = tuple(self.runner_config["data"]["financial_predictor_allowlist"])
        expected_allowlist = features_for_blocks(("L", "D", "R"))
        if allowlist != expected_allowlist:
            raise RunnerIntegrityError("Predictor allowlist differs from frozen L+D+R order.")
        for block in BLOCKS:
            expected_columns = tuple(
                [*features_for_blocks(BLOCK_PARTS[block])]
                + [
                    f"{name}__missing"
                    for name in features_for_blocks(BLOCK_PARTS[block])
                ]
            )
            frozen = self.registry["pca_feature_order"][block]
            order_sha = hashlib.sha256(
                "".join(f"{name}\n" for name in expected_columns).encode("utf-8")
            ).hexdigest()
            if tuple(frozen["columns"]) != expected_columns or frozen[
                "sha256_utf8_lf_with_trailing_lf"
            ] != order_sha:
                raise RunnerIntegrityError(f"Frozen PCA predictor order mismatch: {block}")
        permitted_bounds = list(self.contract["data_boundary"]["permitted_feature_years"])
        if list(self.runner_config["data"]["permitted_feature_years"]) != permitted_bounds:
            raise RunnerIntegrityError("Runner permitted-year boundary differs from contract.")
        if list(self.runner_config["data"]["protected_feature_years"]) != list(
            self.contract["data_boundary"]["protected_feature_years"]
        ):
            raise RunnerIntegrityError("Runner protected-year boundary differs from contract.")
        pipeline = yaml.safe_load(
            (self.root / PIPELINE_CONFIG_PATH.relative_to(ROOT)).read_text(
                encoding="utf-8"
            )
        )
        expected_inputs = {
            "raw_x_t_train": pipeline["upstream_inputs"]["raw_x_t"],
            "target_application_train": pipeline["upstream_inputs"]["target"],
        }
        for name, frozen in expected_inputs.items():
            configured = self.runner_config["data"]["frozen_train_inputs"][name]
            if configured["path"] != frozen["artifact"] or configured["sha256"] != frozen[
                "sha256"
            ]:
                raise RunnerIntegrityError(
                    f"Runner {name} input is not the timezone-corrected train projection."
                )

    def production_input_expectations(self) -> InputExpectations:
        pipeline = yaml.safe_load(
            (self.root / PIPELINE_CONFIG_PATH.relative_to(ROOT)).read_text(
                encoding="utf-8"
            )
        )
        sample = pipeline["supervised_sample"]
        folds = {
            row["id"]: {
                "train_n": row["pit_safe_train_n"],
                "validation_n": row["validation_n"],
                "train_membership_sha256": row["train_membership_sha256"],
                "validation_membership_sha256": row["validation_membership_sha256"],
            }
            for row in pipeline["temporal_cv_membership"]["folds"]
        }
        return InputExpectations(
            membership_n=int(sample["train_n"]),
            membership_sha256=str(sample["membership_sha256"]),
            folds=folds,
        )

    def load_frozen_project_sample(self) -> tuple[pd.DataFrame, InputExpectations]:
        """Verify exact train projections before deserializing selected columns."""

        if self.executor.synthetic_only:
            raise RunnerIntegrityError("Synthetic executor cannot load project data.")
        inputs = self.runner_config["data"]["frozen_train_inputs"]
        resolved: dict[str, Path] = {}
        for name, item in inputs.items():
            path = (self.root / item["path"]).resolve()
            if path != (self.root / str(item["path"])).resolve():
                raise ProtectedDataAccessError("Non-canonical input path.")
            if not path.is_file():
                raise RunnerIntegrityError(f"Missing frozen input: {path}")
            if file_sha256(path) != str(item["sha256"]):
                raise RunnerIntegrityError(f"Frozen input hash mismatch: {name}")
            resolved[name] = path

        financial_features = list(
            self.runner_config["data"]["financial_predictor_allowlist"]
        )
        raw_columns = [
            "research_universe_company_year_id",
            "feature_year",
            "membership_status",
            "economic_group_id",
            "prediction_timestamp",
            "x_t_status",
            *[f"{feature}_value" for feature in financial_features],
        ]
        target_columns = [
            "research_universe_company_year_id",
            "feature_year",
            "membership_status",
            "economic_group_id",
            "target_status",
            "target_candidate_v2_pit_b",
            "anchor_t1_accepted_at",
        ]
        raw = pd.read_csv(resolved["raw_x_t_train"], usecols=raw_columns, low_memory=False)
        target = pd.read_csv(
            resolved["target_application_train"], usecols=target_columns, low_memory=False
        )
        if raw["research_universe_company_year_id"].duplicated().any():
            raise RunnerIntegrityError("Duplicate raw X_t company-year identity.")
        if target["research_universe_company_year_id"].duplicated().any():
            raise RunnerIntegrityError("Duplicate target company-year identity.")
        target = target.rename(
            columns={
                "feature_year": "target_feature_year",
                "membership_status": "target_membership_status",
                "economic_group_id": "target_economic_group_id",
                "target_candidate_v2_pit_b": "target_label",
                "anchor_t1_accepted_at": "target_available_at",
            }
        )
        sample = raw.merge(
            target,
            how="left",
            on="research_universe_company_year_id",
            validate="one_to_one",
        )
        alignment = (
            pd.to_numeric(sample["feature_year"], errors="raise").astype(int)
            == pd.to_numeric(sample["target_feature_year"], errors="raise").astype(int)
        ) & (
            sample["economic_group_id"].astype(str)
            == sample["target_economic_group_id"].astype(str)
        )
        if not alignment.all():
            raise RunnerIntegrityError("Raw X_t and target identity metadata disagree.")
        policy = self.runner_config["data"]["sample_policy"]
        keep = (
            sample["membership_status"].eq(policy["required_membership_status"])
            & sample["target_membership_status"].eq(
                policy["required_membership_status"]
            )
            & sample["target_status"].eq(policy["required_target_status"])
            & sample["x_t_status"].isin(policy["allowed_x_t_statuses"])
        )
        sample = sample.loc[keep].copy()
        sample = sample.rename(
            columns={f"{feature}_value": feature for feature in financial_features}
        )
        sample["target_label"] = pd.to_numeric(
            sample["target_label"], errors="raise"
        ).astype(int)
        return self._canonicalize_sample(sample), self.production_input_expectations()

    def _canonicalize_sample(self, sample: pd.DataFrame) -> pd.DataFrame:
        missing = sorted(
            (
                set(REQUIRED_SAMPLE_METADATA)
                | set(self.runner_config["data"]["financial_predictor_allowlist"])
            )
            - set(sample.columns)
        )
        if missing:
            raise RunnerIntegrityError(f"Sample is missing required columns: {missing}")
        frame = sample.copy()
        years = pd.to_numeric(frame["feature_year"], errors="raise").astype(int)
        permitted_bounds = self.contract["data_boundary"]["permitted_feature_years"]
        permitted = set(range(int(permitted_bounds[0]), int(permitted_bounds[-1]) + 1))
        protected = set(self.contract["data_boundary"]["protected_feature_years"])
        found = set(years)
        if found & protected or not found <= permitted:
            raise ProtectedDataAccessError(
                f"Runner input contains forbidden feature years: {sorted(found - permitted)}"
            )
        frame["feature_year"] = years
        frame["research_universe_company_year_id"] = frame[
            "research_universe_company_year_id"
        ].astype(str)
        frame["economic_group_id"] = frame["economic_group_id"].astype(str)
        if frame["research_universe_company_year_id"].duplicated().any():
            raise RunnerIntegrityError("Sample contains duplicate company-year identities.")
        labels = pd.to_numeric(frame["target_label"], errors="raise").astype(int)
        if set(labels) - {0, 1}:
            raise RunnerIntegrityError("Target labels must be binary integers.")
        frame["target_label"] = labels
        for column in ("prediction_timestamp", "target_available_at"):
            timestamps = pd.to_datetime(frame[column], errors="coerce", utc=True)
            if timestamps.isna().any():
                raise RunnerIntegrityError(f"Invalid or missing {column}.")
            frame[column] = timestamps
        if not frame["prediction_timestamp"].lt(frame["target_available_at"]).all():
            raise RunnerIntegrityError(
                "Prediction timestamp must strictly precede target availability."
            )
        return frame.sort_values(
            ["feature_year", "research_universe_company_year_id"], kind="mergesort"
        ).reset_index(drop=True)

    def verify_sample_and_folds(
        self, sample: pd.DataFrame, expectations: InputExpectations
    ) -> dict[str, tuple[Any, pd.DataFrame, pd.DataFrame, Any]]:
        sample = self._canonicalize_sample(sample)
        if len(sample) != int(expectations.membership_n):
            raise RunnerIntegrityError("Frozen supervised sample row count mismatch.")
        actual_membership = membership_sha256(
            sample["research_universe_company_year_id"].tolist()
        )
        if actual_membership != expectations.membership_sha256:
            raise RunnerIntegrityError("Frozen supervised sample membership SHA mismatch.")
        folds: dict[str, tuple[Any, pd.DataFrame, pd.DataFrame, Any]] = {}
        for fold, train, validation, audit in iter_point_in_time_folds(sample):
            if fold.name not in expectations.folds:
                raise RunnerIntegrityError(f"Unexpected temporal fold: {fold.name}")
            expected = expectations.folds[fold.name]
            actual = {
                "train_n": len(train),
                "validation_n": len(validation),
                "train_membership_sha256": membership_sha256(
                    train["research_universe_company_year_id"].tolist()
                ),
                "validation_membership_sha256": membership_sha256(
                    validation["research_universe_company_year_id"].tolist()
                ),
            }
            for key, value in actual.items():
                if str(value) != str(expected[key]):
                    raise RunnerIntegrityError(
                        f"{fold.name} {key} mismatch: expected {expected[key]}, got {value}"
                    )
            folds[fold.name] = (fold, train, validation, audit)
        if set(folds) != set(expectations.folds):
            raise RunnerIntegrityError("Frozen temporal fold set mismatch.")
        return folds

    def _preprocessing_artifact(
        self,
        *,
        block: str,
        fold_id: str,
        preprocessor: FinancialPreprocessor,
    ) -> tuple[Path, str]:
        payload = {
            "schema_version": 1,
            "identity": {"feature_block": block, "fold_id": fold_id},
            "fit_scope": "fold_train_only",
            "state": preprocessor.fitted_state(),
        }
        path = self.output_dir / "preprocessing" / block.replace("+", "_") / f"{fold_id}.json"
        digest = atomic_write_json(path, payload)
        return path, digest

    def _prepare_fold(
        self,
        *,
        block: str,
        fold_tuple: tuple[Any, pd.DataFrame, pd.DataFrame, Any],
        qubits: int | None = None,
    ) -> PreparedFold:
        fold, train, validation, _audit = fold_tuple
        cache_key = (fold.name, block, qubits)
        if cache_key in self._prepared_cache:
            return self._prepared_cache[cache_key]
        if block == BLOCK_AGNOSTIC:
            prepared = PreparedFold(
                fold_id=fold.name,
                validation_feature_year=fold.validation_start,
                train=train,
                validation=validation,
                train_membership_sha256=membership_sha256(
                    train["research_universe_company_year_id"].tolist()
                ),
                validation_membership_sha256=membership_sha256(
                    validation["research_universe_company_year_id"].tolist()
                ),
                preprocessing_sha256=canonical_sha256({"mode": "none_dummy_prior"}),
                pca_sha256=None,
                x_train=np.empty((len(train), 0), dtype=np.float64),
                x_validation=np.empty((len(validation), 0), dtype=np.float64),
                predictor_names=(),
            )
            self._prepared_cache[cache_key] = prepared
            return prepared

        preprocessor = FinancialPreprocessor.for_blocks(BLOCK_PARTS[block])
        x_train_frame = preprocessor.fit_transform(train)
        x_validation_frame = preprocessor.transform(validation)
        expected_names = tuple(
            [*features_for_blocks(BLOCK_PARTS[block])]
            + [f"{name}__missing" for name in features_for_blocks(BLOCK_PARTS[block])]
        )
        actual_names = tuple(x_train_frame.columns)
        if actual_names != expected_names or tuple(x_validation_frame.columns) != expected_names:
            raise RunnerIntegrityError("Post-preprocessing predictor allowlist/order mismatch.")
        if "economic_group_id" in actual_names:
            raise RunnerIntegrityError("economic_group_id entered the predictor matrix.")
        _, preprocessing_sha = self._preprocessing_artifact(
            block=block, fold_id=fold.name, preprocessor=preprocessor
        )
        x_train = x_train_frame.to_numpy(dtype=np.float64, copy=True)
        x_validation = x_validation_frame.to_numpy(dtype=np.float64, copy=True)
        if not np.isfinite(x_train).all() or not np.isfinite(x_validation).all():
            raise TechnicalExecutionError(
                "NUMERICAL_INVALID", "NAN_OR_INF_INPUT", "Nonfinite preprocessed matrix."
            )
        pca_sha: str | None = None
        predictor_names = actual_names
        if qubits is not None:
            if qubits not in (4, 6):
                raise RunnerIntegrityError("Only preregistered 4/6-qubit PCA is allowed.")
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
                "identity": {
                    "feature_block": block,
                    "fold_id": fold.name,
                    "qubits": qubits,
                    "preprocessing_sha256": preprocessing_sha,
                },
                "fit_scope": "fold_train_only",
                "input_feature_order": list(actual_names),
                "components_float64_hex": [
                    [float(value).hex() for value in row] for row in pca.components_
                ],
                "explained_variance_float64_hex": [
                    float(value).hex() for value in pca.explained_variance_
                ],
                "pca_mean_float64_hex": [float(value).hex() for value in pca.mean_],
                "component_scaler_mean_float64_hex": [
                    float(value).hex() for value in scaler.mean_
                ],
                "component_scaler_scale_float64_hex": [
                    float(value).hex() for value in scaler.scale_
                ],
                "clipping": [-3.0, 3.0],
                "angle_multiplier_float64_hex": float(np.pi / 3.0).hex(),
            }
            pca_path = (
                self.output_dir
                / "pca"
                / block.replace("+", "_")
                / f"q{qubits}"
                / f"{fold.name}.json"
            )
            pca_sha = atomic_write_json(pca_path, pca_payload)
            predictor_names = tuple(f"pca_angle_{index + 1}" for index in range(qubits))
        prepared = PreparedFold(
            fold_id=fold.name,
            validation_feature_year=fold.validation_start,
            train=train,
            validation=validation,
            train_membership_sha256=membership_sha256(
                train["research_universe_company_year_id"].tolist()
            ),
            validation_membership_sha256=membership_sha256(
                validation["research_universe_company_year_id"].tolist()
            ),
            preprocessing_sha256=preprocessing_sha,
            pca_sha256=pca_sha,
            x_train=x_train,
            x_validation=x_validation,
            predictor_names=predictor_names,
        )
        self._prepared_cache[cache_key] = prepared
        return prepared

    @staticmethod
    def _sample_weight(labels: np.ndarray, imbalance: str) -> np.ndarray:
        labels = np.asarray(labels, dtype=np.int64)
        negative = int(np.sum(labels == 0))
        positive = int(np.sum(labels == 1))
        if negative == 0 or positive == 0:
            raise TechnicalExecutionError(
                "NUMERICAL_INVALID", "DEGENERATE_TRAIN_CLASS", "Fold train has one class."
            )
        if imbalance == "none":
            positive_weight = 1.0
        elif imbalance == "sqrt":
            positive_weight = math.sqrt(negative / positive)
        else:
            raise RunnerIntegrityError(f"Unknown imbalance policy: {imbalance}")
        return np.where(labels == 1, positive_weight, 1.0).astype(np.float64)

    def _candidate_parameters(self, stage: str, family: str, configuration_id: str) -> dict[str, Any]:
        if stage in {"coarse", "refinement"}:
            candidates = self.registry[stage][family]
        elif stage == "qnn_q1":
            candidates = self.registry["qnn"]["stage_q1"]
        elif stage == "qnn_q2":
            candidates = self.registry["qnn"]["stage_q2"]
        else:
            raise RunnerIntegrityError(f"Unknown stage: {stage}")
        matches = [row for row in candidates if row["configuration_id"] == configuration_id]
        if len(matches) != 1:
            raise RunnerIntegrityError("Candidate identity missing or duplicated in registry.")
        return dict(matches[0])

    def _artifact_directory(
        self, *, stage: str, family: str, configuration_id: str, block: str, seed: int
    ) -> Path:
        return (
            self.output_dir
            / "candidate_results"
            / stage
            / family
            / configuration_id
            / block.replace("+", "_")
            / f"seed_{seed}"
        )

    def _execute_candidate(
        self,
        *,
        stage: str,
        family: str,
        feature_block: str,
        candidate: Mapping[str, Any],
        training_seed: int,
        folds: Mapping[str, tuple[Any, pd.DataFrame, pd.DataFrame, Any]],
        selected_ansatz_id: str | None = None,
    ) -> CandidateExecutionResult:
        configuration_id = str(candidate["configuration_id"])
        parameters = dict(candidate.get("parameters") or {})
        if stage.startswith("qnn_"):
            parameters = {key: value for key, value in candidate.items() if key != "configuration_id"}
        fold_statuses: dict[str, str] = {}
        fold_manifests: list[dict[str, Any]] = []
        predictions: list[dict[str, Any]] = []
        base_directory = self._artifact_directory(
            stage=stage,
            family=family,
            configuration_id=configuration_id,
            block=feature_block,
            seed=training_seed,
        )
        for fold_id in self.contract["execution_failure_state_machine"]["required_folds"]:
            fold_tuple = folds[str(fold_id)]
            qubits = int(parameters["qubits_pca"]) if family == "qnn" else None
            prepared = self._prepare_fold(
                block=feature_block, fold_tuple=fold_tuple, qubits=qubits
            )
            role = "qnn_mlp" if family in {"pytorch_mlp", "qnn"} else "classical"
            checkpoint_identity = {
                "family": family,
                "configuration_id": configuration_id,
                "parameters_sha256": canonical_sha256(parameters),
                "feature_block": feature_block,
                "fold_id": fold_id,
                "training_seed": training_seed,
                "train_membership_sha256": prepared.train_membership_sha256,
                "validation_membership_sha256": prepared.validation_membership_sha256,
                "preprocessing_sha256": prepared.preprocessing_sha256,
                "pca_sha256_if_applicable": prepared.pca_sha256,
                "software_environment_sha256": self._environment_hashes[role],
                "device_identity": self.contract["qnn_executable_identity"]["device_identity"]
                if family == "qnn"
                else "cpu",
            }
            if family == "pytorch_mlp":
                checkpoint_identity["epochs"] = int(parameters["epochs"])
            task = FoldTask(
                stage=stage,
                family=family,
                feature_block=feature_block,
                configuration_id=configuration_id,
                parameters=parameters,
                training_seed=int(training_seed),
                fold_id=str(fold_id),
                validation_feature_year=prepared.validation_feature_year,
                selected_ansatz_id=selected_ansatz_id,
                train_membership_sha256=prepared.train_membership_sha256,
                validation_membership_sha256=prepared.validation_membership_sha256,
                preprocessing_sha256=prepared.preprocessing_sha256,
                pca_sha256_if_applicable=prepared.pca_sha256,
                software_environment_role=role,
                checkpoint_identity=checkpoint_identity,
            )
            fold_directory = base_directory / str(fold_id)
            manifest_path = fold_directory / "result_manifest.json"
            prediction_path = fold_directory / "oof_predictions.json"
            # Completed fold results are the only resumable terminal artifacts.
            if manifest_path.is_file():
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
                if existing.get("task_identity_sha256") != task.identity_sha256:
                    raise RunnerIntegrityError("Existing result manifest identity mismatch.")
                if existing.get("status") == "COMPLETE":
                    if not prediction_path.is_file() or file_sha256(prediction_path) != existing.get(
                        "oof_prediction_artifact_sha256"
                    ):
                        raise RunnerIntegrityError("Existing prediction artifact hash mismatch.")
                    rows = json.loads(prediction_path.read_text(encoding="utf-8"))["rows"]
                    predictions.extend(rows)
                    fold_statuses[str(fold_id)] = "COMPLETE"
                    fold_manifests.append(existing)
                    continue
                raise RunnerIntegrityError(
                    "Terminal non-complete fold manifest cannot be rerun without a new run directory."
                )

            y_train = prepared.train["target_label"].to_numpy(dtype=np.int64)
            sample_weight = self._sample_weight(
                y_train, str(parameters.get("imbalance", "none"))
            )
            timeout = int(
                self.contract["execution_failure_state_machine"][
                    "timeouts_cumulative_wall_seconds_per_fold_fit"
                ][family]
            )
            checkpoint_path = fold_directory / "checkpoint.pt"
            execution = self.executor.execute(
                task,
                x_train=prepared.x_train,
                y_train=y_train,
                x_validation=prepared.x_validation,
                sample_weight=sample_weight,
                checkpoint_path=checkpoint_path,
                timeout_seconds=timeout,
            )
            status = execution.status
            allowed_statuses = set(
                self.contract["execution_failure_state_machine"]["terminal_fold_statuses"]
            )
            if status not in allowed_statuses:
                raise RunnerIntegrityError(f"Executor returned unknown terminal status: {status}")
            fold_statuses[str(fold_id)] = status
            environment_hash = execution.software_environment_sha256
            if environment_hash:
                with self._state_lock:
                    previous = self._environment_hashes.setdefault(role, environment_hash)
                    if previous != environment_hash:
                        raise RunnerIntegrityError("Runtime environment hash changed within role.")
            prediction_sha: str | None = None
            if status == "COMPLETE":
                scores = np.asarray(execution.raw_scores, dtype=np.float64)
                if scores.shape != (len(prepared.validation),) or not np.isfinite(scores).all():
                    status = "NUMERICAL_INVALID"
                    fold_statuses[str(fold_id)] = status
                    execution.failure_code = "NAN_OR_INF_RAW_SCORE"
                else:
                    rows: list[dict[str, Any]] = []
                    for (_, observation), score in zip(
                        prepared.validation.iterrows(), scores, strict=True
                    ):
                        rows.append(
                            {
                                "validation_feature_year": int(observation["feature_year"]),
                                "research_universe_company_year_id": str(
                                    observation["research_universe_company_year_id"]
                                ),
                                "fold_id": str(fold_id),
                                "target_label": int(observation["target_label"]),
                                "economic_group_id": str(observation["economic_group_id"]),
                                "prediction_timestamp": canonical_timestamp(
                                    observation["prediction_timestamp"]
                                ),
                                "raw_score": float(score),
                                "raw_score_float64_hex": float(score).hex(),
                            }
                        )
                    rows.sort(
                        key=lambda row: (
                            row["validation_feature_year"],
                            row["research_universe_company_year_id"].encode("utf-8"),
                        )
                    )
                    prediction_sha = atomic_write_json(
                        prediction_path,
                        {
                            "schema_version": 1,
                            "task_identity_sha256": task.identity_sha256,
                            "canonical_key": list(
                                self.contract["seed_aggregation"]["canonical_prediction_key"]
                            ),
                            "rows": rows,
                        },
                    )
                    predictions.extend(rows)
            manifest = {
                "schema_version": 1,
                "task_identity": task.identity,
                "task_identity_sha256": task.identity_sha256,
                "status": status,
                "failure_code": execution.failure_code,
                "configuration_id": configuration_id,
                "training_seed": int(training_seed),
                "epochs": int(parameters["epochs"])
                if family == "pytorch_mlp"
                else None,
                "runtime_metadata_sha256": self._runtime_metadata_sha256,
                "attempts": execution.attempts,
                "train_rows": len(prepared.train),
                "validation_rows": len(prepared.validation),
                "predictor_names": list(prepared.predictor_names),
                "predictor_order_sha256": canonical_sha256(list(prepared.predictor_names)),
                "software_environment_sha256": execution.software_environment_sha256,
                "device_identity": execution.device_identity,
                "oof_prediction_artifact": str(prediction_path.relative_to(self.output_dir))
                if prediction_sha
                else None,
                "oof_prediction_artifact_sha256": prediction_sha,
            }
            atomic_write_json(manifest_path, manifest)
            fold_manifests.append(manifest)

        aggregate_status = candidate_fold_aggregate_status(
            fold_statuses, self.contract, family="qnn" if family == "qnn" else "classical_or_mlp"
        )
        pooled: float | None = None
        prediction_sha: str | None = None
        if aggregate_status == "COMPLETE":
            predictions.sort(
                key=lambda row: (
                    int(row["validation_feature_year"]),
                    str(row["research_universe_company_year_id"]).encode("utf-8"),
                )
            )
            labels = np.asarray([row["target_label"] for row in predictions], dtype=np.int64)
            scores = np.asarray([row["raw_score"] for row in predictions], dtype=np.float64)
            pooled = float(average_precision_score(labels, scores))
            prediction_sha = canonical_sha256(
                [
                    {
                        "key": [
                            row["validation_feature_year"],
                            row["research_universe_company_year_id"],
                        ],
                        "score_float64_hex": float(row["raw_score"]).hex(),
                    }
                    for row in predictions
                ]
            )
        row = {
            "stage": stage,
            "family": family,
            "feature_block": feature_block,
            "configuration_id": configuration_id,
            "parameters": parameters,
            "training_seed": int(training_seed),
            "fold_statuses": fold_statuses,
            "status": aggregate_status,
            "pooled_oof_pr_auc": pooled,
            "oof_prediction_artifact_sha256": prediction_sha,
            "failure_code": None if aggregate_status == "COMPLETE" else "PARTIAL_OR_INVALID_FOLD",
        }
        if selected_ansatz_id is not None:
            row["selected_ansatz_id"] = selected_ansatz_id
        atomic_write_json(
            base_directory / "candidate_manifest.json",
            {"schema_version": 1, "candidate": row, "fold_manifests": fold_manifests},
        )
        return CandidateExecutionResult(row=row, predictions=predictions)

    def _reuse_q1_as_q2_t0(
        self,
        *,
        source: CandidateExecutionResult,
        q2_candidate: Mapping[str, Any],
        selected_ansatz_id: str,
    ) -> CandidateExecutionResult:
        row = dict(source.row)
        row.update(
            {
                "stage": "qnn_q2",
                "configuration_id": q2_candidate["configuration_id"],
                "parameters": {
                    key: value for key, value in q2_candidate.items() if key != "configuration_id"
                },
                "selected_ansatz_id": selected_ansatz_id,
                "reuse_source": {
                    "stage": "qnn_q1",
                    "configuration_id": source.row["configuration_id"],
                    "oof_prediction_artifact_sha256": source.row[
                        "oof_prediction_artifact_sha256"
                    ],
                },
            }
        )
        base = self._artifact_directory(
            stage="qnn_q2",
            family="qnn",
            configuration_id=str(q2_candidate["configuration_id"]),
            block=str(row["feature_block"]),
            seed=int(row["training_seed"]),
        )
        source_base = self._artifact_directory(
            stage=str(source.row["stage"]),
            family="qnn",
            configuration_id=str(source.row["configuration_id"]),
            block=str(source.row["feature_block"]),
            seed=int(source.row["training_seed"]),
        )
        reused_fold_manifests: list[dict[str, Any]] = []
        for fold_id in self.contract["execution_failure_state_machine"]["required_folds"]:
            source_manifest_path = source_base / fold_id / "result_manifest.json"
            if not source_manifest_path.is_file():
                raise RunnerIntegrityError("Q1 source fold manifest is missing for Q2/T0 reuse.")
            source_manifest = json.loads(
                source_manifest_path.read_text(encoding="utf-8")
            )
            source_status = str(source.row["fold_statuses"][fold_id])
            if str(source_manifest.get("status")) != source_status:
                raise RunnerIntegrityError("Q1 row and fold manifest statuses disagree.")
            source_failure_code = source_manifest.get("failure_code")
            fold_rows = [p for p in source.predictions if p["fold_id"] == fold_id]
            prediction_path = base / fold_id / "oof_predictions.json"
            prediction_sha: str | None = None
            if source_status == "COMPLETE":
                if not fold_rows:
                    raise RunnerIntegrityError(
                        "Complete Q1 fold has no predictions for Q2/T0 reuse."
                    )
                prediction_sha = atomic_write_json(
                    prediction_path,
                    {
                        "schema_version": 1,
                        "execution_mode": "q1_selected_ansatz_reuse_as_q2_t0",
                        "rows": fold_rows,
                    },
                )
            reused_manifest = {
                "schema_version": 1,
                "status": source_status,
                "failure_code": source_failure_code,
                "execution_mode": "q1_selected_ansatz_reuse_as_q2_t0",
                "identity": {
                    "stage": "qnn_q2",
                    "family": "qnn",
                    "configuration_id": q2_candidate["configuration_id"],
                    "feature_block": row["feature_block"],
                    "training_seed": row["training_seed"],
                    "fold_id": fold_id,
                    "selected_ansatz_id": selected_ansatz_id,
                },
                "configuration_id": q2_candidate["configuration_id"],
                "training_seed": row["training_seed"],
                "runtime_metadata_sha256": self._runtime_metadata_sha256,
                "source_configuration_id": source.row["configuration_id"],
                "source_status": source_status,
                "source_failure_code": source_failure_code,
                "source_prediction_sha256": source_manifest.get(
                    "oof_prediction_artifact_sha256"
                ),
                "oof_prediction_artifact_sha256": prediction_sha,
            }
            atomic_write_json(
                base / fold_id / "result_manifest.json",
                reused_manifest,
            )
            reused_fold_manifests.append(reused_manifest)
        atomic_write_json(
            base / "candidate_manifest.json",
            {
                "schema_version": 1,
                "candidate": row,
                "fold_manifests": reused_fold_manifests,
            },
        )
        return CandidateExecutionResult(row=row, predictions=list(source.predictions))

    def _aggregate_confirmed(
        self,
        base: CandidateExecutionResult,
        confirmations: Sequence[CandidateExecutionResult],
    ) -> CandidateExecutionResult:
        all_results = [base, *confirmations]
        if not all(result.row["status"] == "COMPLETE" for result in all_results):
            row = dict(base.row)
            row["training_seed"] = "AVERAGED_20260818_20260819_20260820"
            row["status"] = (
                "QNN_CANDIDATE_TECHNICALLY_INVALID"
                if row["family"] == "qnn"
                else "FAMILY_CANDIDATE_TECHNICALLY_INVALID"
            )
            row["pooled_oof_pr_auc"] = None
            row["oof_prediction_artifact_sha256"] = None
            row["failure_code"] = "CONFIRMATION_SEED_FAILURE_NO_PROMOTION"
            return CandidateExecutionResult(row=row, predictions=[])
        predictions_by_seed = {
            int(result.row["training_seed"]): result.predictions for result in all_results
        }
        averaged = align_and_average_raw_scores(
            predictions_by_seed,
            self.contract["seed_aggregation"]["seed_order"],
            self.contract,
        )
        averaged = [
            {
                **row,
                "raw_score": float(row["averaged_raw_score"]),
                "raw_score_float64_hex": float(row["averaged_raw_score"]).hex(),
            }
            for row in averaged
        ]
        labels = [int(row["target_label"]) for row in averaged]
        scores = [float(row["raw_score"]) for row in averaged]
        row = dict(base.row)
        row["training_seed"] = "AVERAGED_20260818_20260819_20260820"
        row["status"] = "COMPLETE"
        row["pooled_oof_pr_auc"] = float(average_precision_score(labels, scores))
        row["seed_component_prediction_sha256"] = {
            str(result.row["training_seed"]): result.row["oof_prediction_artifact_sha256"]
            for result in all_results
        }
        averaged_path = (
            self.output_dir
            / "seed_averaged_oof"
            / str(row["family"])
            / str(row["configuration_id"])
            / str(row["feature_block"]).replace("+", "_")
            / "oof_predictions.json"
        )
        averaged_sha = atomic_write_json(
            averaged_path,
            {
                "schema_version": 1,
                "identity": {
                    key: row[key]
                    for key in ("family", "configuration_id", "feature_block")
                },
                "seed_order": list(self.contract["seed_aggregation"]["seed_order"]),
                "canonical_prediction_key": list(
                    self.contract["seed_aggregation"]["canonical_prediction_key"]
                ),
                "rows": averaged,
            },
        )
        row["oof_prediction_artifact"] = str(
            averaged_path.relative_to(self.output_dir)
        )
        row["oof_prediction_artifact_sha256"] = averaged_sha
        return CandidateExecutionResult(row=row, predictions=averaged)

    def _fit_calibration_and_threshold(
        self, representative: CandidateExecutionResult
    ) -> dict[str, Any]:
        rows = representative.predictions
        labels = np.asarray([row["target_label"] for row in rows], dtype=np.int64)
        scores = np.asarray([row["raw_score"] for row in rows], dtype=np.float64)
        plan = calibration_plan(labels.tolist(), scores.tolist())
        identity = {
            key: representative.row[key]
            for key in ("family", "configuration_id", "feature_block")
        }
        if plan["status"] == "FIT_PLATT_LOGISTIC":
            constructor = self.contract["calibration"]["constructor"]
            estimator = LogisticRegression(
                penalty=None,
                solver=str(constructor["solver"]),
                tol=float(constructor["tol"]),
                fit_intercept=bool(constructor["fit_intercept"]),
                class_weight=None,
                random_state=None,
                max_iter=int(constructor["max_iter"]),
                n_jobs=int(constructor["n_jobs"]),
            )
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", FutureWarning)
                    warnings.simplefilter("error", ConvergenceWarning)
                    estimator.fit(scores.reshape(-1, 1), labels)
                coefficient = float(estimator.coef_[0, 0])
                intercept = float(estimator.intercept_[0])
            except (ConvergenceWarning, Exception) as error:
                # The broad exception maps deterministically to the frozen no-fallback
                # calibration failure state; there is no method substitution.
                return {
                    "identity": identity,
                    "status": "CALIBRATION_TECHNICALLY_INVALID",
                    "failure_type": type(error).__name__,
                }
            fit_status = "COMPLETE"
        elif plan["status"] == "CONSTANT_SCORE_INTERCEPT_ONLY":
            coefficient = float(plan["coefficient"])
            intercept = float(plan["intercept"])
            fit_status = "CONSTANT_SCORE_INTERCEPT_ONLY"
        else:
            return {"identity": identity, "status": "CALIBRATION_TECHNICALLY_INVALID"}
        calibrated = expit(coefficient * scores + intercept).astype(np.float64)
        if not np.isfinite(calibrated).all():
            return {"identity": identity, "status": "CALIBRATION_TECHNICALLY_INVALID"}
        key_payload = [
            [row["validation_feature_year"], row["research_universe_company_year_id"]]
            for row in rows
        ]
        calibration_artifact = {
            "schema_version": 1,
            "identity": identity,
            "coef_float64_hex": coefficient.hex(),
            "intercept_float64_hex": intercept.hex(),
            "input_key_sha256": canonical_sha256(key_payload),
            "input_score_sha256": float64_vector_sha256(scores),
            "target_sha256": hashlib.sha256(labels.astype(">i8").tobytes()).hexdigest(),
            "software_environment_sha256": self._environment_hashes.get(
                "classical", SyntheticFoldExecutor.environment_sha256
            ),
            "fit_status": fit_status,
        }
        stem = "__".join(
            [identity["family"], identity["configuration_id"], identity["feature_block"]]
        ).replace("+", "_")
        calibration_path = self.output_dir / "calibration" / f"{stem}.json"
        calibration_sha = atomic_write_json(calibration_path, calibration_artifact)
        threshold = max_f1_threshold(labels.tolist(), calibrated.tolist())
        if threshold["status"] != "THRESHOLD_SELECTED":
            return {
                "identity": identity,
                "status": "THRESHOLD_TECHNICALLY_INVALID",
                "calibration_sha256": calibration_sha,
            }
        threshold_artifact = {
            "schema_version": 1,
            "identity": identity,
            "threshold_float64_hex": threshold["threshold_float64_hex"],
            "achieved_f1_numerator": threshold["achieved_f1_numerator"],
            "achieved_f1_denominator": threshold["achieved_f1_denominator"],
            "candidate_count": threshold["candidate_count"],
            "calibrated_input_sha256": float64_vector_sha256(calibrated),
            "selection_rule_id": "MODEL_EXECUTION_CONTRACT_V1_2_0_EXACT_MAX_F1",
        }
        threshold_path = self.output_dir / "thresholds" / f"{stem}.json"
        threshold_sha = atomic_write_json(threshold_path, threshold_artifact)
        return {
            "identity": identity,
            "status": "COMPLETE",
            "calibration_artifact": str(calibration_path.relative_to(self.output_dir)),
            "calibration_sha256": calibration_sha,
            "threshold_artifact": str(threshold_path.relative_to(self.output_dir)),
            "threshold_sha256": threshold_sha,
        }

    def _dry_run_plan(self, folds: Mapping[str, Any], expectations: InputExpectations) -> dict[str, Any]:
        index = canonical_candidate_index(self.contract, self.registry)
        plan = {
            "schema_version": 1,
            "mode": "dry_run_no_model_fit",
            "contract_sha256": file_sha256(self.contract_path),
            "registry_sha256": file_sha256(self.registry_path),
            "candidate_index_sha256": canonical_sha256(index),
            "candidate_positions": len(index),
            "fold_ids": list(folds),
            "sample_membership_sha256": expectations.membership_sha256,
            "model_fit_performed": False,
            "protected_feature_years_opened": False,
        }
        plan["runtime_metadata_sha256"] = self._write_runtime_metadata(index)
        atomic_write_json(self.output_dir / "dry_run_plan.json", plan)
        return plan

    def _complete_candidate_report(
        self,
        result: CandidateExecutionResult,
        *,
        expected_oof_keys: set[tuple[int, str]],
    ) -> dict[str, Any]:
        row = result.row
        predictions = list(result.predictions)
        if row["status"] != "COMPLETE":
            raise RunnerIntegrityError(
                "Candidate is not complete: "
                f"{row['family']}/{row['configuration_id']}/{row['feature_block']} "
                f"status={row['status']} failure_code={row['failure_code']}"
            )
        keys = [
            (
                int(item["validation_feature_year"]),
                str(item["research_universe_company_year_id"]),
            )
            for item in predictions
        ]
        if len(keys) != len(set(keys)):
            raise RunnerIntegrityError("Duplicate OOF prediction key in candidate result.")
        if set(keys) != expected_oof_keys:
            raise RunnerIntegrityError("Candidate OOF keys do not match all six folds.")
        scores = np.asarray([item["raw_score"] for item in predictions], dtype=np.float64)
        labels = np.asarray([item["target_label"] for item in predictions], dtype=np.int64)
        if not np.isfinite(scores).all():
            raise RunnerIntegrityError("Nonfinite OOF score in candidate result.")
        if set(labels) - {0, 1}:
            raise RunnerIntegrityError("Nonbinary OOF target in candidate result.")
        ordered = sorted(
            predictions,
            key=lambda item: (
                int(item["validation_feature_year"]),
                str(item["research_universe_company_year_id"]).encode("utf-8"),
            ),
        )
        if predictions != ordered:
            raise RunnerIntegrityError("Candidate OOF predictions are not in canonical key order.")
        base_directory = self._artifact_directory(
            stage=str(row["stage"]),
            family=str(row["family"]),
            configuration_id=str(row["configuration_id"]),
            block=str(row["feature_block"]),
            seed=int(row["training_seed"]),
        )
        oof_path = base_directory / "canonical_oof_predictions.json"
        oof_sha = atomic_write_json(
            oof_path,
            {
                "schema_version": 1,
                "canonical_key": list(
                    self.contract["seed_aggregation"]["canonical_prediction_key"]
                ),
                "configuration_id": row["configuration_id"],
                "training_seed": row["training_seed"],
                "rows": predictions,
            },
        )
        candidate_manifest_path = base_directory / "candidate_manifest.json"
        candidate_manifest = json.loads(
            candidate_manifest_path.read_text(encoding="utf-8")
        )
        fold_runtime_seconds: dict[str, float] = {}
        for manifest in candidate_manifest["fold_manifests"]:
            fold_runtime_seconds[str(manifest["task_identity"]["fold_id"])] = float(
                sum(
                    float(attempt.get("runtime_seconds", 0.0))
                    for attempt in manifest.get("attempts", [])
                )
            )
        per_fold: list[dict[str, Any]] = []
        fold_pr_auc: list[float] = []
        for fold_id in self.contract["execution_failure_state_machine"]["required_folds"]:
            fold_rows = [item for item in predictions if item["fold_id"] == fold_id]
            fold_labels = np.asarray(
                [item["target_label"] for item in fold_rows], dtype=np.int64
            )
            fold_scores = np.asarray(
                [item["raw_score"] for item in fold_rows], dtype=np.float64
            )
            pr_auc = float(average_precision_score(fold_labels, fold_scores))
            roc_auc = float(roc_auc_score(fold_labels, fold_scores))
            fold_pr_auc.append(pr_auc)
            per_fold.append(
                {
                    "fold_id": fold_id,
                    "validation_feature_year": int(
                        fold_rows[0]["validation_feature_year"]
                    ),
                    "n": len(fold_rows),
                    "positive_n": int(fold_labels.sum()),
                    "pr_auc": pr_auc,
                    "roc_auc": roc_auc,
                    "runtime_seconds": fold_runtime_seconds.get(fold_id, 0.0),
                    "status": row["fold_statuses"][fold_id],
                }
            )
        report = {
            "family": row["family"],
            "configuration_id": row["configuration_id"],
            "feature_block": row["feature_block"],
            "parameters": row["parameters"],
            "training_seed": row["training_seed"],
            "status": row["status"],
            "failure_code": row["failure_code"],
            "convergence_status": (
                "CONVERGED_NO_WARNINGS"
                if row["status"] == "COMPLETE"
                else "NOT_CONVERGED_OR_INVALID"
            ),
            "pooled_oof_n": len(predictions),
            "pooled_oof_positive_n": int(labels.sum()),
            "pooled_oof_pr_auc": float(average_precision_score(labels, scores)),
            "pooled_oof_roc_auc": float(roc_auc_score(labels, scores)),
            "fold_pr_auc_mean": float(np.mean(fold_pr_auc)),
            "fold_pr_auc_sample_sd": float(np.std(fold_pr_auc, ddof=1)),
            "per_fold": per_fold,
            "runtime_seconds": float(sum(fold_runtime_seconds.values())),
            "oof_key_count": len(keys),
            "oof_unique_key_count": len(set(keys)),
            "oof_nonfinite_score_count": int((~np.isfinite(scores)).sum()),
            "canonical_oof_predictions": str(oof_path.relative_to(self.output_dir)),
            "canonical_oof_predictions_sha256": oof_sha,
            "canonical_prediction_keys_sha256": canonical_sha256(
                [[year, identifier] for year, identifier in keys]
            ),
            "candidate_manifest": str(
                candidate_manifest_path.relative_to(self.output_dir)
            ),
            "candidate_manifest_sha256": file_sha256(candidate_manifest_path),
        }
        return report

    def _terminal_candidate_report(
        self,
        result: CandidateExecutionResult,
        *,
        expected_oof_keys: set[tuple[int, str]],
    ) -> dict[str, Any]:
        """Materialize a complete OOF report or a terminal technical-failure report."""

        if result.row["status"] == "COMPLETE":
            return self._complete_candidate_report(
                result, expected_oof_keys=expected_oof_keys
            )
        row = result.row
        required_folds = list(
            self.contract["execution_failure_state_machine"]["required_folds"]
        )
        if list(row["fold_statuses"]) != required_folds:
            raise RunnerIntegrityError(
                "Terminal candidate does not account for every required fold in order."
            )
        base_directory = self._artifact_directory(
            stage=str(row["stage"]),
            family=str(row["family"]),
            configuration_id=str(row["configuration_id"]),
            block=str(row["feature_block"]),
            seed=int(row["training_seed"]),
        )
        candidate_manifest_path = base_directory / "candidate_manifest.json"
        if not candidate_manifest_path.is_file():
            raise RunnerIntegrityError("Terminal candidate manifest is missing.")
        candidate_manifest = json.loads(
            candidate_manifest_path.read_text(encoding="utf-8")
        )
        by_fold = {
            str(manifest["task_identity"]["fold_id"]): manifest
            for manifest in candidate_manifest["fold_manifests"]
        }
        if list(by_fold) != required_folds:
            raise RunnerIntegrityError(
                "Terminal candidate manifests do not cover every required fold in order."
            )
        per_fold: list[dict[str, Any]] = []
        total_runtime = 0.0
        for fold_id in required_folds:
            manifest = by_fold[fold_id]
            runtime_seconds = float(
                sum(
                    float(attempt.get("runtime_seconds", 0.0))
                    for attempt in manifest.get("attempts", [])
                )
            )
            total_runtime += runtime_seconds
            per_fold.append(
                {
                    "fold_id": fold_id,
                    "validation_feature_year": int(
                        manifest["task_identity"]["validation_feature_year"]
                    ),
                    "n": int(manifest["validation_rows"]),
                    "positive_n": None,
                    "pr_auc": None,
                    "roc_auc": None,
                    "runtime_seconds": runtime_seconds,
                    "status": str(manifest["status"]),
                    "failure_code": manifest.get("failure_code"),
                }
            )
        partial_scores = np.asarray(
            [item["raw_score"] for item in result.predictions], dtype=np.float64
        )
        return {
            "family": row["family"],
            "configuration_id": row["configuration_id"],
            "feature_block": row["feature_block"],
            "parameters": row["parameters"],
            "training_seed": row["training_seed"],
            "status": row["status"],
            "failure_code": row["failure_code"],
            "convergence_status": "NOT_CONVERGED_OR_INVALID",
            "pooled_oof_n": None,
            "pooled_oof_positive_n": None,
            "pooled_oof_pr_auc": None,
            "pooled_oof_roc_auc": None,
            "fold_pr_auc_mean": None,
            "fold_pr_auc_sample_sd": None,
            "per_fold": per_fold,
            "runtime_seconds": total_runtime,
            "oof_key_count": len(result.predictions),
            "oof_unique_key_count": len(
                {
                    (
                        int(item["validation_feature_year"]),
                        str(item["research_universe_company_year_id"]),
                    )
                    for item in result.predictions
                }
            ),
            "oof_nonfinite_score_count": int(
                (~np.isfinite(partial_scores)).sum()
            ),
            "canonical_oof_predictions": None,
            "canonical_oof_predictions_sha256": None,
            "canonical_prediction_keys_sha256": None,
            "candidate_manifest": str(
                candidate_manifest_path.relative_to(self.output_dir)
            ),
            "candidate_manifest_sha256": file_sha256(candidate_manifest_path),
        }

    def run_real_data_execution_smoke(
        self,
        sample: pd.DataFrame,
        *,
        expectations: InputExpectations,
    ) -> dict[str, Any]:
        """Execute only preregistered dummy and fixed-L2 coarse positions.

        This is an execution smoke, never a model-selection or ranking path.
        """

        sample = self._canonicalize_sample(sample)
        if expectations.source_kind == "synthetic" and not self.executor.synthetic_only:
            raise RunnerIntegrityError("Synthetic input requires the synthetic-only executor.")
        if expectations.source_kind != "synthetic" and self.executor.synthetic_only:
            raise RunnerIntegrityError("Synthetic executor is forbidden for project data.")
        folds = self.verify_sample_and_folds(sample, expectations)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        full_index = canonical_candidate_index(self.contract, self.registry)
        smoke_index = [
            entry
            for entry in full_index
            if entry["stage"] == "coarse"
            and entry["family"] in {"dummy_prior", "fixed_l2_logistic"}
        ]
        if len(smoke_index) != 7:
            raise RunnerIntegrityError(
                "Frozen smoke scope must contain one dummy and six fixed-L2 positions."
            )
        if {entry["family"] for entry in smoke_index} != {
            "dummy_prior",
            "fixed_l2_logistic",
        }:
            raise RunnerIntegrityError("Execution smoke family scope changed.")
        self._write_runtime_metadata(smoke_index)
        expected_oof_keys = {
            (int(observation["feature_year"]), str(observation["research_universe_company_year_id"]))
            for _, _, validation, _ in folds.values()
            for _, observation in validation.iterrows()
        }
        reports: list[dict[str, Any]] = []
        started = time.monotonic()
        for entry in smoke_index:
            candidate = self._candidate_parameters(
                "coarse", str(entry["family"]), str(entry["configuration_id"])
            )
            result = self._execute_candidate(
                stage="coarse",
                family=str(entry["family"]),
                feature_block=str(entry["feature_block_or_binding"]),
                candidate=candidate,
                training_seed=int(self.contract["confirmation"]["coarse_seed"]),
                folds=folds,
            )
            reports.append(
                self._complete_candidate_report(
                    result, expected_oof_keys=expected_oof_keys
                )
            )
        if any(report["status"] != "COMPLETE" for report in reports):
            status = "FAILED"
        else:
            status = "COMPLETE"
        family_manifests: dict[str, dict[str, str]] = {}
        for family in ("dummy_prior", "fixed_l2_logistic"):
            family_path = self.output_dir / "smoke_results" / family / "result_manifest.json"
            family_sha = atomic_write_json(
                family_path,
                {
                    "schema_version": 1,
                    "mode": "real_data_execution_smoke_not_model_selection",
                    "family": family,
                    "candidate_results": [
                        report for report in reports if report["family"] == family
                    ],
                },
            )
            family_manifests[family] = {
                "path": str(family_path.relative_to(self.output_dir)),
                "sha256": family_sha,
            }
        manifest = {
            "schema_version": 1,
            "status": status,
            "mode": "real_data_execution_smoke_not_model_selection",
            "source_kind": expectations.source_kind,
            "contract_sha256": file_sha256(self.contract_path),
            "candidate_registry_sha256": file_sha256(self.registry_path),
            "runner_config_sha256": file_sha256(self.runner_config_path),
            "sample_membership_sha256": expectations.membership_sha256,
            "executed_families": ["dummy_prior", "fixed_l2_logistic"],
            "executed_candidate_positions": len(reports),
            "executed_fold_fits": len(reports) * len(folds),
            "training_seed": int(self.contract["confirmation"]["coarse_seed"]),
            "fold_ids": list(folds),
            "runtime_seconds": float(time.monotonic() - started),
            "runtime_metadata_sha256": self._runtime_metadata_sha256,
            "family_result_manifests": family_manifests,
            "candidate_results": reports,
            "oof_expected_key_count": len(expected_oof_keys),
            "all_oof_keys_exactly_once": all(
                report["oof_key_count"] == report["oof_unique_key_count"]
                == len(expected_oof_keys)
                for report in reports
            ),
            "all_scores_finite": all(
                report["oof_nonfinite_score_count"] == 0 for report in reports
            ),
            "preprocessing_fit_scope": "from_scratch_within_each_train_fold",
            "model_selection_performed": False,
            "refinement_performed": False,
            "mlp_performed": False,
            "qnn_performed": False,
            "robustness_or_interpretability_performed": False,
            "external_validation_or_test_opened": False,
            "protected_feature_years_opened": False,
            "project_data_model_fit_performed": expectations.source_kind != "synthetic",
        }
        manifest_sha = atomic_write_json(
            self.output_dir / "real_data_execution_smoke_manifest.json", manifest
        )
        atomic_write_json(
            self.output_dir / "run_manifest.json",
            {
                "schema_version": 1,
                "status": status,
                "mode": manifest["mode"],
                "real_data_execution_smoke_manifest_sha256": manifest_sha,
                "model_fit_performed": True,
                "project_data_model_fit_performed": expectations.source_kind
                != "synthetic",
                "protected_feature_years_opened": False,
                "runtime_metadata_sha256": self._runtime_metadata_sha256,
            },
        )
        return manifest

    @staticmethod
    def _coarse_summary_entry(
        report: Mapping[str, Any],
        *,
        rank: int | None = None,
    ) -> dict[str, Any]:
        entry = {
            key: report.get(key)
            for key in (
                "family",
                "configuration_id",
                "feature_block",
                "parameters",
                "training_seed",
                "status",
                "failure_code",
                "convergence_status",
                "pooled_oof_n",
                "pooled_oof_positive_n",
                "pooled_oof_pr_auc",
                "pooled_oof_roc_auc",
                "fold_pr_auc_mean",
                "fold_pr_auc_sample_sd",
                "per_fold",
                "runtime_seconds",
                "delta_pr_auc_vs_dummy",
                "delta_pr_auc_vs_fixed_l2",
            )
        }
        if rank is not None:
            entry["rank"] = rank
        return entry

    def run_classical_mlp_coarse_search(
        self,
        sample: pd.DataFrame,
        *,
        expectations: InputExpectations,
    ) -> dict[str, Any]:
        """Execute the complete frozen non-QNN coarse index and stop before refinement."""

        sample = self._canonicalize_sample(sample)
        if expectations.source_kind == "synthetic" and not self.executor.synthetic_only:
            raise RunnerIntegrityError("Synthetic input requires the synthetic-only executor.")
        if expectations.source_kind != "synthetic" and self.executor.synthetic_only:
            raise RunnerIntegrityError("Synthetic executor is forbidden for project data.")
        folds = self.verify_sample_and_folds(sample, expectations)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        full_index = canonical_candidate_index(self.contract, self.registry)
        coarse_index = [entry for entry in full_index if entry["stage"] == "coarse"]
        expected_families = [
            family
            for family in self.contract["canonical_ordering"]["family_order"]
            if family != "qnn"
        ]
        if len(coarse_index) != 247:
            raise RunnerIntegrityError(
                "Frozen classical/MLP coarse scope must contain 247 candidate positions."
            )
        if list(dict.fromkeys(entry["family"] for entry in coarse_index)) != expected_families:
            raise RunnerIntegrityError("Frozen classical/MLP coarse family scope changed.")
        self._write_runtime_metadata(coarse_index)
        expected_oof_keys = {
            (
                int(observation["feature_year"]),
                str(observation["research_universe_company_year_id"]),
            )
            for _, _, validation, _ in folds.values()
            for _, observation in validation.iterrows()
        }
        fold_summary = [
            {
                "fold_id": fold_id,
                "validation_feature_year": int(fold.validation_start),
                "train_n": len(train),
                "validation_n": len(validation),
                "validation_positive_n": int(validation["target_label"].sum()),
                "train_membership_sha256": membership_sha256(
                    train["research_universe_company_year_id"].tolist()
                ),
                "validation_membership_sha256": membership_sha256(
                    validation["research_universe_company_year_id"].tolist()
                ),
            }
            for fold_id, (fold, train, validation, _) in folds.items()
        ]
        reports: list[dict[str, Any]] = []
        coarse_results: list[CandidateExecutionResult] = []
        started = time.monotonic()
        for entry in coarse_index:
            candidate = self._candidate_parameters(
                "coarse", str(entry["family"]), str(entry["configuration_id"])
            )
            result = self._execute_candidate(
                stage="coarse",
                family=str(entry["family"]),
                feature_block=str(entry["feature_block_or_binding"]),
                candidate=candidate,
                training_seed=int(self.contract["confirmation"]["coarse_seed"]),
                folds=folds,
            )
            coarse_results.append(result)
            reports.append(
                self._terminal_candidate_report(
                    result, expected_oof_keys=expected_oof_keys
                )
            )

        report_by_identity = {
            (
                report["family"],
                report["feature_block"],
                report["configuration_id"],
                int(report["training_seed"]),
            ): report
            for report in reports
        }
        ranked_rows = rank_candidates(
            [result.row for result in coarse_results], self.contract
        )
        ranked_complete_reports = [
            report_by_identity[
                (
                    row["family"],
                    row["feature_block"],
                    row["configuration_id"],
                    int(row["training_seed"]),
                )
            ]
            for row in ranked_rows
            if row["status"] == "COMPLETE"
        ]
        dummy_report = next(
            report
            for report in ranked_complete_reports
            if report["family"] == "dummy_prior"
        )
        fixed_l2_report = next(
            report
            for report in ranked_complete_reports
            if report["family"] == "fixed_l2_logistic"
        )
        dummy_metric = float(dummy_report["pooled_oof_pr_auc"])
        fixed_l2_metric = float(fixed_l2_report["pooled_oof_pr_auc"])
        for report in reports:
            metric = report.get("pooled_oof_pr_auc")
            report["delta_pr_auc_vs_dummy"] = (
                float(metric) - dummy_metric if metric is not None else None
            )
            report["delta_pr_auc_vs_fixed_l2"] = (
                float(metric) - fixed_l2_metric if metric is not None else None
            )

        best_by_family_and_block: list[dict[str, Any]] = []
        for family in expected_families:
            family_blocks = (
                [BLOCK_AGNOSTIC]
                if family == "dummy_prior"
                else list(self.contract["canonical_ordering"]["feature_block_order"])
            )
            for block in family_blocks:
                candidates = [
                    result.row
                    for result in coarse_results
                    if result.row["family"] == family
                    and result.row["feature_block"] == block
                ]
                leader = rank_candidates(candidates, self.contract)[0]
                leader_report = report_by_identity[
                    (
                        leader["family"],
                        leader["feature_block"],
                        leader["configuration_id"],
                        int(leader["training_seed"]),
                    )
                ]
                best_by_family_and_block.append(
                    self._coarse_summary_entry(leader_report)
                )
        best_by_family: list[dict[str, Any]] = []
        for family in expected_families:
            candidates = [
                result.row
                for result in coarse_results
                if result.row["family"] == family
            ]
            leader = rank_candidates(candidates, self.contract)[0]
            leader_report = report_by_identity[
                (
                    leader["family"],
                    leader["feature_block"],
                    leader["configuration_id"],
                    int(leader["training_seed"]),
                )
            ]
            best_by_family.append(self._coarse_summary_entry(leader_report))
        top_20 = [
            self._coarse_summary_entry(report, rank=index)
            for index, report in enumerate(ranked_complete_reports[:20], 1)
        ]
        activations = select_refinement_families(
            [result.row for result in coarse_results], self.contract
        )
        refinement_sha = atomic_write_json(
            self.output_dir / "refinement_eligibility.json",
            {
                "schema_version": 1,
                "status": "QUALIFIED_NOT_EXECUTED",
                "source": "coarse_seed_20260818_OOF_2015_2020_only",
                "frozen_rule_applied": True,
                "refinement_performed": False,
                "qualified_families": activations,
            },
        )
        family_manifests: dict[str, dict[str, str]] = {}
        for family in expected_families:
            family_path = (
                self.output_dir / "coarse_results" / family / "result_manifest.json"
            )
            family_sha = atomic_write_json(
                family_path,
                {
                    "schema_version": 1,
                    "mode": "classical_mlp_coarse_search",
                    "family": family,
                    "candidate_results": [
                        report for report in reports if report["family"] == family
                    ],
                },
            )
            family_manifests[family] = {
                "path": str(family_path.relative_to(self.output_dir)),
                "sha256": family_sha,
            }
        terminal_statuses = set(
            self.contract["execution_failure_state_machine"]["terminal_fold_statuses"]
        )
        all_positions_terminal = all(
            len(result.row["fold_statuses"]) == len(folds)
            and set(result.row["fold_statuses"].values()) <= terminal_statuses
            for result in coarse_results
        )
        all_complete_oof_exact = all(
            report["oof_key_count"] == report["oof_unique_key_count"]
            == len(expected_oof_keys)
            for report in reports
            if report["status"] == "COMPLETE"
        )
        all_complete_scores_finite = all(
            report["oof_nonfinite_score_count"] == 0
            for report in reports
            if report["status"] == "COMPLETE"
        )
        status = (
            "COMPLETE"
            if all_positions_terminal
            and all_complete_oof_exact
            and all_complete_scores_finite
            else "FAILED"
        )
        manifest = {
            "schema_version": 1,
            "status": status,
            "mode": "classical_mlp_coarse_search",
            "source_kind": expectations.source_kind,
            "contract_sha256": file_sha256(self.contract_path),
            "candidate_registry_sha256": file_sha256(self.registry_path),
            "runner_config_sha256": file_sha256(self.runner_config_path),
            "sample_membership_sha256": expectations.membership_sha256,
            "candidate_index_sha256": canonical_sha256(coarse_index),
            "executed_families": expected_families,
            "executed_candidate_positions": len(reports),
            "executed_fold_fits": len(reports) * len(folds),
            "complete_candidate_positions": sum(
                report["status"] == "COMPLETE" for report in reports
            ),
            "technically_invalid_candidate_positions": sum(
                report["status"] != "COMPLETE" for report in reports
            ),
            "training_seed": int(self.contract["confirmation"]["coarse_seed"]),
            "folds": fold_summary,
            "runtime_seconds": float(time.monotonic() - started),
            "runtime_metadata_sha256": self._runtime_metadata_sha256,
            "family_result_manifests": family_manifests,
            "refinement_eligibility_sha256": refinement_sha,
            "candidate_results": reports,
            "best_by_family_and_feature_block": best_by_family_and_block,
            "best_by_family": best_by_family,
            "top_20_coarse_candidates": top_20,
            "dummy_baseline_identity": self._coarse_summary_entry(dummy_report),
            "fixed_l2_baseline_identity": self._coarse_summary_entry(fixed_l2_report),
            "refinement_qualified_families": activations,
            "all_candidate_positions_terminal": all_positions_terminal,
            "all_complete_oof_keys_exactly_once": all_complete_oof_exact,
            "all_complete_scores_finite": all_complete_scores_finite,
            "preprocessing_fit_scope": "from_scratch_within_each_train_fold",
            "model_selection_performed": False,
            "refinement_performed": False,
            "qnn_performed": False,
            "calibration_or_threshold_performed": False,
            "robustness_or_interpretability_performed": False,
            "external_validation_or_test_opened": False,
            "protected_feature_years_opened": False,
            "project_data_model_fit_performed": expectations.source_kind != "synthetic",
        }
        manifest_sha = atomic_write_json(
            self.output_dir / "classical_mlp_coarse_search_manifest.json", manifest
        )
        atomic_write_json(
            self.output_dir / "run_manifest.json",
            {
                "schema_version": 1,
                "status": status,
                "mode": manifest["mode"],
                "classical_mlp_coarse_search_manifest_sha256": manifest_sha,
                "model_fit_performed": True,
                "project_data_model_fit_performed": expectations.source_kind
                != "synthetic",
                "protected_feature_years_opened": False,
                "runtime_metadata_sha256": self._runtime_metadata_sha256,
            },
        )
        return manifest

    def run(
        self,
        sample: pd.DataFrame,
        *,
        expectations: InputExpectations,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        sample = self._canonicalize_sample(sample)
        if expectations.source_kind == "synthetic" and not self.executor.synthetic_only:
            raise RunnerIntegrityError("Synthetic input requires the synthetic-only executor.")
        if expectations.source_kind != "synthetic" and self.executor.synthetic_only:
            raise RunnerIntegrityError("Synthetic executor is forbidden for project data.")
        folds = self.verify_sample_and_folds(sample, expectations)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if dry_run:
            return self._dry_run_plan(folds, expectations)

        index = canonical_candidate_index(self.contract, self.registry)
        self._write_runtime_metadata(index)
        self._configure_qnn_ledger()
        coarse_results: list[CandidateExecutionResult] = []
        for entry in index:
            if entry["stage"] != "coarse":
                continue
            candidate = self._candidate_parameters(
                "coarse", entry["family"], entry["configuration_id"]
            )
            coarse_results.append(
                self._execute_candidate(
                    stage="coarse",
                    family=str(entry["family"]),
                    feature_block=str(entry["feature_block_or_binding"]),
                    candidate=candidate,
                    training_seed=20260818,
                    folds=folds,
                )
            )

        activations = select_refinement_families(
            [result.row for result in coarse_results], self.contract
        )
        atomic_write_json(
            self.output_dir / "refinement_activation.json",
            {
                "schema_version": 1,
                "source": "coarse_seed_20260818_OOF_2015_2020_only",
                "activations": activations,
            },
        )
        active_blocks = {row["family"]: row["feature_block"] for row in activations}
        refinement_results: list[CandidateExecutionResult] = []
        for entry in index:
            if entry["stage"] != "refinement" or entry["family"] not in active_blocks:
                continue
            candidate = self._candidate_parameters(
                "refinement", entry["family"], entry["configuration_id"]
            )
            refinement_results.append(
                self._execute_candidate(
                    stage="refinement",
                    family=str(entry["family"]),
                    feature_block=str(active_blocks[entry["family"]]),
                    candidate=candidate,
                    training_seed=20260818,
                    folds=folds,
                )
            )
        merged_rows = merge_coarse_refinement_results(
            [result.row for result in coarse_results],
            [result.row for result in refinement_results],
            activations,
            self.contract,
        )
        result_lookup: dict[tuple[str, str, str, int], CandidateExecutionResult] = {
            (
                result.row["family"],
                result.row["feature_block"],
                result.row["configuration_id"],
                int(result.row["training_seed"]),
            ): result
            for result in [*coarse_results, *refinement_results]
        }

        q1_results: list[CandidateExecutionResult] = []
        for entry in index:
            if entry["stage"] != "qnn_q1":
                continue
            candidate = self._candidate_parameters("qnn_q1", "qnn", entry["configuration_id"])
            q1_results.append(
                self._execute_candidate(
                    stage="qnn_q1",
                    family="qnn",
                    feature_block=str(entry["feature_block_or_binding"]),
                    candidate=candidate,
                    training_seed=20260818,
                    folds=folds,
                    selected_ansatz_id=str(candidate["ansatz"]),
                )
            )
        ansatz_selection = select_qnn_ansatz([result.row for result in q1_results], self.contract)
        atomic_write_json(
            self.output_dir / "qnn_selected_ansatz.json",
            {"schema_version": 1, **ansatz_selection},
        )
        q2_results: list[CandidateExecutionResult] = []
        if ansatz_selection["status"] == "SELECTED":
            selected_ansatz = str(ansatz_selection["selected_ansatz_id"])
            q1_by_block = {
                result.row["feature_block"]: result
                for result in q1_results
                if result.row["parameters"]["ansatz"] == selected_ansatz
            }
            for entry in index:
                if entry["stage"] != "qnn_q2":
                    continue
                block = str(entry["feature_block_or_binding"])
                candidate = self._candidate_parameters("qnn_q2", "qnn", entry["configuration_id"])
                if bool(candidate.get("reuse_q1_winner")):
                    q2_results.append(
                        self._reuse_q1_as_q2_t0(
                            source=q1_by_block[block],
                            q2_candidate=candidate,
                            selected_ansatz_id=selected_ansatz,
                        )
                    )
                else:
                    q2_results.append(
                        self._execute_candidate(
                            stage="qnn_q2",
                            family="qnn",
                            feature_block=block,
                            candidate=candidate,
                            training_seed=20260818,
                            folds=folds,
                            selected_ansatz_id=selected_ansatz,
                        )
                    )

        confirmation_selection = select_confirmation_candidates(merged_rows, self.contract)
        qnn_confirmation_selection = select_qnn_confirmation_candidates(
            [result.row for result in q2_results], self.contract
        )
        atomic_write_json(
            self.output_dir / "confirmation_selection.json",
            {
                "schema_version": 1,
                "classical_mlp": confirmation_selection,
                "qnn": qnn_confirmation_selection,
            },
        )
        confirmed_results: list[CandidateExecutionResult] = []
        confirmation_seed_results: list[CandidateExecutionResult] = []
        for selection in confirmation_selection:
            key = (
                selection["family"],
                selection["feature_block"],
                selection["configuration_id"],
                20260818,
            )
            base = result_lookup[key]
            candidate = self._candidate_parameters(
                str(base.row["stage"]), str(base.row["family"]), str(base.row["configuration_id"])
            )
            extras = [
                self._execute_candidate(
                    stage=str(base.row["stage"]),
                    family=str(base.row["family"]),
                    feature_block=str(base.row["feature_block"]),
                    candidate=candidate,
                    training_seed=int(seed),
                    folds=folds,
                )
                for seed in selection["confirmation_seeds"]
            ]
            confirmation_seed_results.extend(extras)
            confirmed_results.append(self._aggregate_confirmed(base, extras))
        q2_lookup = {
            (r.row["feature_block"], r.row["configuration_id"]): r for r in q2_results
        }
        for selection in qnn_confirmation_selection:
            base = q2_lookup[(selection["feature_block"], selection["configuration_id"])]
            candidate = self._candidate_parameters("qnn_q2", "qnn", selection["configuration_id"])
            extras = [
                self._execute_candidate(
                    stage="qnn_q2",
                    family="qnn",
                    feature_block=str(selection["feature_block"]),
                    candidate=candidate,
                    training_seed=int(seed),
                    folds=folds,
                    selected_ansatz_id=str(selection["selected_ansatz_id"]),
                )
                for seed in selection["confirmation_seeds"]
            ]
            confirmation_seed_results.extend(extras)
            confirmed_results.append(self._aggregate_confirmed(base, extras))

        deterministic_families = set(
            self.contract["confirmation"]["deterministic_exceptions"]
        )
        merged_results = [
            result_lookup[
                (
                    str(row["family"]),
                    str(row["feature_block"]),
                    str(row["configuration_id"]),
                    int(row["training_seed"]),
                )
            ]
            for row in merged_rows
        ]
        qnn_resource_limit_reached = bool(
            self._qnn_ledger is not None and self._qnn_ledger.limit_reached
        )
        final_results = final_eligibility_pool(
            merged_results,
            confirmed_results,
            self.contract,
            qnn_resource_limit_reached=qnn_resource_limit_reached,
        )
        complete_final = [result for result in final_results if result.row["status"] == "COMPLETE"]
        family_representatives: list[CandidateExecutionResult] = []
        for family in self.contract["canonical_ordering"]["family_order"]:
            candidates = [result for result in complete_final if result.row["family"] == family]
            if not candidates:
                continue
            ranked = rank_candidates([result.row for result in candidates], self.contract)
            leader = ranked[0]
            family_representatives.append(
                next(result for result in candidates if result.row is leader or result.row == leader)
            )
        ranked_representative_rows = rank_candidates(
            [result.row for result in family_representatives], self.contract
        )
        representative_lookup = {
            (
                result.row["family"],
                result.row["configuration_id"],
                result.row["feature_block"],
            ): result
            for result in family_representatives
        }
        ranked_representatives = [
            representative_lookup[
                (row["family"], row["configuration_id"], row["feature_block"])
            ]
            for row in ranked_representative_rows
        ]
        calibration = [
            self._fit_calibration_and_threshold(result) for result in ranked_representatives
        ]
        selected_confirmation_keys = {
            (row["family"], row["feature_block"], row["configuration_id"])
            for row in confirmation_selection
        }
        common_rows: list[dict[str, Any]] = []
        for row in merged_rows:
            materialized = dict(row)
            identity = (
                row["family"],
                row["feature_block"],
                row["configuration_id"],
            )
            if (
                row["family"]
                in self.contract["confirmation"]["stochastic_classical_mlp_families"]
                and identity not in selected_confirmation_keys
            ):
                materialized["final_eligibility"] = "NOT_SELECTED_FOR_CONFIRMATION"
            elif row["family"] in deterministic_families:
                materialized["final_eligibility"] = (
                    "ELIGIBLE" if row["status"] == "COMPLETE" else "TECHNICALLY_INVALID"
                )
            else:
                materialized["final_eligibility"] = "REPLACED_BY_THREE_SEED_AGGREGATE"
            common_rows.append(materialized)
        for result in [*q1_results, *q2_results, *confirmation_seed_results]:
            common_rows.append({**result.row, "final_eligibility": "INTERMEDIATE_EXECUTION_ROW"})
        for result in confirmed_results:
            common_rows.append(
                {
                    **result.row,
                    "final_eligibility": "ELIGIBLE"
                    if result.row["status"] == "COMPLETE"
                    else "TECHNICALLY_INVALID",
                }
            )
        candidate_ordinals: dict[tuple[str, str, str, str], int] = {}
        for entry in index:
            key = (
                str(entry["stage"]),
                str(entry["family"]),
                str(entry["feature_block_or_binding"]),
                str(entry["configuration_id"]),
            )
            candidate_ordinals[key] = int(entry["ordinal"])

        def common_row_key(row: Mapping[str, Any]) -> tuple[int, int]:
            binding = (
                "$BEST_COARSE_BLOCK"
                if row["stage"] == "refinement"
                else str(row["feature_block"])
            )
            ordinal = candidate_ordinals[
                (
                    str(row["stage"]),
                    str(row["family"]),
                    binding,
                    str(row["configuration_id"]),
                )
            ]
            seed = row["training_seed"]
            seed_rank = {
                20260818: 0,
                20260819: 1,
                20260820: 2,
                "AVERAGED_20260818_20260819_20260820": 3,
            }[seed]
            return ordinal, seed_rank

        common_rows.sort(key=common_row_key)
        common_table_sha = atomic_write_json(
            self.output_dir / "canonical_candidate_result_table.json",
            {
                "schema_version": 1,
                "canonical_candidate_order_sha256": self.runner_config["determinism"][
                    "expanded_candidate_order_sha256"
                ],
                "rows": common_rows,
            },
        )
        roster_artifact = {
            "schema_version": 1,
            "representatives": [
                {
                    "rank": rank,
                    **{
                        key: result.row[key]
                        for key in ("family", "configuration_id", "feature_block")
                    },
                    "oof_prediction_artifact_sha256": result.row[
                        "oof_prediction_artifact_sha256"
                    ],
                }
                for rank, result in enumerate(ranked_representatives, 1)
            ],
        }
        roster_sha = atomic_write_json(
            self.output_dir / "final_family_roster.json", roster_artifact
        )
        qnn_feasibility = {
            "schema_version": 1,
            "status": "QNN_TECHNICALLY_FEASIBLE"
            if any(result.row["family"] == "qnn" for result in ranked_representatives)
            else "QNN_TECHNICALLY_INFEASIBLE",
            "selected_ansatz": ansatz_selection,
            "final_qnn_representative": next(
                (
                    {
                        key: result.row[key]
                        for key in (
                            "configuration_id",
                            "feature_block",
                            "selected_ansatz_id",
                            "parameters",
                        )
                    }
                    for result in ranked_representatives
                    if result.row["family"] == "qnn"
                ),
                None,
            ),
            "device_identity": self.contract["qnn_executable_identity"]["device_identity"],
            "software_environment_sha256": self._environment_hashes.get("qnn_mlp"),
            "global_resource_limit_reached": qnn_resource_limit_reached,
            "global_resource_limit_reason": self._qnn_ledger.payload.get(
                "limit_reason"
            )
            if self._qnn_ledger is not None
            else None,
        }
        qnn_feasibility_sha = atomic_write_json(
            self.output_dir / "qnn_feasibility_and_executable_identity.json",
            qnn_feasibility,
        )
        secondary_plan = {
            "interpretability": self.contract["interpretability_execution_scope"],
            "robustness": self.contract["robustness_execution_scope"],
            "representative_identities": [
                {
                    key: result.row[key]
                    for key in ("family", "configuration_id", "feature_block")
                }
                for result in ranked_representatives
            ],
            "global_winner_identity": {
                key: ranked_representatives[0].row[key]
                for key in ("family", "configuration_id", "feature_block")
            }
            if ranked_representatives
            else None,
            "may_change_primary_ranking": False,
        }
        secondary_plan_sha = atomic_write_json(
            self.output_dir / "secondary_analysis_execution_plan.json", secondary_plan
        )
        ranking_manifest = {
            "schema_version": 1,
            "contract_sha256": file_sha256(self.contract_path),
            "candidate_registry_sha256": file_sha256(self.registry_path),
            "runner_config_sha256": file_sha256(self.runner_config_path),
            "sample_membership_sha256": expectations.membership_sha256,
            "runtime_environment_sha256_by_role": self._environment_hashes,
            "runtime_metadata_sha256": self._runtime_metadata_sha256,
            "qnn_resource_ledger_sha256": file_sha256(
                self._qnn_ledger.path
            )
            if self._qnn_ledger is not None
            else None,
            "canonical_candidate_result_table_sha256": common_table_sha,
            "final_family_roster_sha256": roster_sha,
            "qnn_feasibility_and_executable_identity_sha256": qnn_feasibility_sha,
            "family_ranking": ranked_representative_rows,
            "global_winner": ranked_representative_rows[0]
            if ranked_representative_rows
            else None,
            "calibration_and_threshold": calibration,
            "secondary_analysis_execution_plan_sha256": secondary_plan_sha,
            "protected_feature_years_opened": False,
            "project_data_model_fit_performed": expectations.source_kind != "synthetic",
            "synthetic_only": expectations.source_kind == "synthetic",
        }
        ranking_sha = atomic_write_json(
            self.output_dir / "final_ranking_manifest.json", ranking_manifest
        )
        run_manifest = {
            "schema_version": 1,
            "status": "COMPLETE",
            "source_kind": expectations.source_kind,
            "final_ranking_manifest_sha256": ranking_sha,
            "artifact_root": str(self.output_dir),
            "model_fit_performed": True,
            "project_data_model_fit_performed": expectations.source_kind != "synthetic",
            "protected_feature_years_opened": False,
            "runtime_metadata_sha256": self._runtime_metadata_sha256,
            "qnn_resource_ledger_sha256": file_sha256(
                self._qnn_ledger.path
            )
            if self._qnn_ledger is not None
            else None,
        }
        atomic_write_json(self.output_dir / "run_manifest.json", run_manifest)
        return ranking_manifest


def synthetic_dataset(rows_per_year: int = 8) -> pd.DataFrame:
    """Create the only dataset accepted by the synthetic integration path."""

    if rows_per_year < 4:
        raise ValueError("Synthetic fixture needs at least four rows per year.")
    rng = np.random.default_rng(20260818)
    features = features_for_blocks(("L", "D", "R"))
    rows: list[dict[str, Any]] = []
    for year in range(2011, 2021):
        for position in range(rows_per_year):
            latent = (position - rows_per_year / 2) / rows_per_year + (year - 2011) * 0.01
            row: dict[str, Any] = {
                "research_universe_company_year_id": f"SYN-{year}-{position:03d}",
                "feature_year": year,
                "economic_group_id": f"SYN-GROUP-{position % 5:02d}",
                "prediction_timestamp": f"{year}-04-30T12:00:00Z",
                "target_available_at": f"{year + 1}-03-01T12:00:00Z",
                "target_label": int(position % 4 == 0 or (position == 1 and year % 2 == 0)),
            }
            for index, feature in enumerate(features):
                value = latent * (index + 1) / len(features) + rng.normal(0.0, 0.05)
                row[feature] = np.nan if (year + position + index) % 19 == 0 else value
            rows.append(row)
    return pd.DataFrame(rows)


def synthetic_expectations(sample: pd.DataFrame) -> InputExpectations:
    canonical = sample.sort_values(
        ["feature_year", "research_universe_company_year_id"], kind="mergesort"
    )
    folds: dict[str, dict[str, Any]] = {}
    for fold, train, validation, _audit in iter_point_in_time_folds(canonical):
        folds[fold.name] = {
            "train_n": len(train),
            "validation_n": len(validation),
            "train_membership_sha256": membership_sha256(
                train["research_universe_company_year_id"].tolist()
            ),
            "validation_membership_sha256": membership_sha256(
                validation["research_universe_company_year_id"].tolist()
            ),
        }
    return InputExpectations(
        membership_n=len(canonical),
        membership_sha256=membership_sha256(
            canonical["research_universe_company_year_id"].tolist()
        ),
        folds=folds,
        source_kind="synthetic",
    )

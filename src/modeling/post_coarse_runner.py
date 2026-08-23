"""Post-coarse execution controller for classical refinement, MLP comparator and QNN.

This module deliberately reuses the already completed coarse-search artifacts. It
never re-runs the 247 coarse candidate positions.  The original frozen primary
refinement rule remains unchanged.  PyTorch MLP refinement is executed in a
separate, explicitly secondary comparator track so that the thesis can compare a
refined classical neural network with the hybrid QNN without retroactively
changing the primary classical model-selection rule.

The controller is phase-gated:

1. ``plan``          – integrity checks and an execution plan; no model fitting.
2. ``refinement``    – the three frozen primary families plus secondary MLP.
3. ``qnn``           – Q1, frozen ansatz selection and Q2; requires refinement.
4. ``confirmation-classical`` – classical/MLP confirmation only; stops before QNN.
5. ``confirmation-qnn`` – QNN confirmation after the classical confirmation gate.
6. ``confirmation``  – both confirmation parts and final development summaries.
7. ``all``           – stages 2–6 in sequence (staged execution is recommended).

Protected feature years 2021–2024 are never opened by this module.  It delegates
all preprocessing, fold construction, estimator execution, checkpointing and
environment verification to :mod:`src.modeling.production_runner`.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import yaml
from sklearn.metrics import average_precision_score, roc_auc_score

from src.modeling.model_execution_contract import (
    canonical_candidate_index,
    canonical_sha256,
    merge_coarse_refinement_results,
    rank_candidates,
    select_confirmation_candidates,
    select_qnn_ansatz,
    select_qnn_confirmation_candidates,
    select_refinement_families,
)
from src.modeling.production_runner import (
    CandidateExecutionResult,
    ProductionExperimentRunner,
    SubprocessFoldExecutor,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "configs/post_coarse_experiment_v1_0_0.yaml"
BLOCKS = ("L", "L+D", "L+D+R")
EXECUTION_MODES = {
    "refinement",
    "qnn",
    "confirmation-classical",
    "confirmation-qnn",
    "confirmation",
    "all",
}
TERMINAL_QNN_PHASE_STATUSES = {"COMPLETE", "QNN_TECHNICALLY_INFEASIBLE"}


class PostCoarseIntegrityError(RuntimeError):
    """Raised when a frozen source, phase gate or artifact identity is invalid."""


@dataclass(frozen=True)
class AuthorityContext:
    amendment_path: Path
    amendment_sha256: str
    backend_amendment_path: Path
    backend_amendment_sha256: str
    base_contract_path: Path
    base_contract_sha256: str
    candidate_registry_path: Path
    candidate_registry_sha256: str
    coarse_manifest_path: Path
    coarse_manifest_sha256: str
    authority_git_index_sha256: str

    def as_dict(self, root: Path) -> dict[str, Any]:
        return {
            "methodology_amendment": {
                "path": _relative_or_absolute(self.amendment_path, root),
                "sha256": self.amendment_sha256,
            },
            "backend_amendment": {
                "path": _relative_or_absolute(self.backend_amendment_path, root),
                "sha256": self.backend_amendment_sha256,
            },
            "base_execution_contract": {
                "path": _relative_or_absolute(self.base_contract_path, root),
                "sha256": self.base_contract_sha256,
            },
            "candidate_registry": {
                "path": _relative_or_absolute(self.candidate_registry_path, root),
                "sha256": self.candidate_registry_sha256,
            },
            "coarse_manifest": {
                "path": _relative_or_absolute(self.coarse_manifest_path, root),
                "sha256": self.coarse_manifest_sha256,
            },
            "authority_git_index_sha256": self.authority_git_index_sha256,
        }


# ---------------------------------------------------------------------------
# Canonical file helpers
# ---------------------------------------------------------------------------


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return hashlib.sha256(payload).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PostCoarseIntegrityError(f"Expected a JSON object: {path}")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PostCoarseIntegrityError(f"Expected a YAML mapping: {path}")
    return value


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _resolve_from_root(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _canonical_prediction_sort_key(row: Mapping[str, Any]) -> tuple[int, bytes]:
    return (
        int(row["validation_feature_year"]),
        str(row["research_universe_company_year_id"]).encode("utf-8"),
    )


def _assert_finite_predictions(rows: Sequence[Mapping[str, Any]], label: str) -> None:
    keys: set[tuple[int, str]] = set()
    for row in rows:
        key = (
            int(row["validation_feature_year"]),
            str(row["research_universe_company_year_id"]),
        )
        if key in keys:
            raise PostCoarseIntegrityError(f"Duplicate OOF key in {label}: {key}")
        keys.add(key)
        score = float(row["raw_score"])
        if not math.isfinite(score):
            raise PostCoarseIntegrityError(f"Nonfinite OOF score in {label}")
        if int(row["target_label"]) not in (0, 1):
            raise PostCoarseIntegrityError(f"Non-binary target in {label}")


def _metric_summary(result: CandidateExecutionResult) -> dict[str, Any]:
    rows = result.predictions
    if result.row.get("status") != "COMPLETE" or not rows:
        return {
            "status": result.row.get("status"),
            "n": 0,
            "positive_n": 0,
            "positive_share": None,
            "pooled_oof_pr_auc": None,
            "pooled_oof_roc_auc": None,
            "fold_pr_auc_mean": None,
            "fold_pr_auc_sample_sd": None,
        }
    labels = np.asarray([int(row["target_label"]) for row in rows], dtype=np.int64)
    scores = np.asarray([float(row["raw_score"]) for row in rows], dtype=np.float64)
    per_fold: list[float] = []
    for year in sorted({int(row["validation_feature_year"]) for row in rows}):
        mask = np.asarray(
            [int(row["validation_feature_year"]) == year for row in rows], dtype=bool
        )
        fold_labels = labels[mask]
        fold_scores = scores[mask]
        if len(np.unique(fold_labels)) == 2:
            per_fold.append(float(average_precision_score(fold_labels, fold_scores)))
    return {
        "status": "COMPLETE",
        "n": int(len(labels)),
        "positive_n": int(labels.sum()),
        "positive_share": float(labels.mean()),
        "pooled_oof_pr_auc": float(average_precision_score(labels, scores)),
        "pooled_oof_roc_auc": float(roc_auc_score(labels, scores))
        if len(np.unique(labels)) == 2
        else None,
        "fold_pr_auc_mean": float(np.mean(per_fold)) if per_fold else None,
        "fold_pr_auc_sample_sd": float(np.std(per_fold, ddof=1))
        if len(per_fold) > 1
        else 0.0 if len(per_fold) == 1 else None,
    }


# ---------------------------------------------------------------------------
# Configuration, authority and Git gate
# ---------------------------------------------------------------------------


def load_post_coarse_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    def merge(base_value: Any, overlay_value: Any) -> Any:
        if isinstance(base_value, Mapping) and isinstance(overlay_value, Mapping):
            result = dict(base_value)
            for key, value in overlay_value.items():
                result[key] = merge(result.get(key), value)
            return result
        return overlay_value

    def load_layer(layer_path: Path, stack: tuple[Path, ...]) -> dict[str, Any]:
        resolved = layer_path.resolve()
        if resolved in stack:
            raise PostCoarseIntegrityError(
                "Post-coarse configuration inheritance contains a cycle."
            )
        layer = load_yaml(resolved)
        extension = layer.get("extends")
        if not isinstance(extension, Mapping):
            return layer
        base_path = (ROOT / str(extension["path"])).resolve()
        if not base_path.is_file() or file_sha256(base_path) != str(
            extension["sha256"]
        ):
            raise PostCoarseIntegrityError(
                "Post-coarse base configuration SHA-256 mismatch."
            )
        base = load_layer(base_path, (*stack, resolved))
        return merge(
            base,
            {key: value for key, value in layer.items() if key != "extends"},
        )

    config = load_layer(path, ())
    section = config.get("post_coarse_execution")
    if not isinstance(section, dict) or str(section.get("version")) not in {
        "1.0.0",
        "1.0.1",
        "1.0.2",
        "1.0.3",
        "1.0.4",
    }:
        raise PostCoarseIntegrityError("Unexpected post-coarse configuration version.")
    return config


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise PostCoarseIntegrityError(
            f"Git command failed: git {' '.join(args)}\n{completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def verify_committed_authority(root: Path, config: Mapping[str, Any]) -> str:
    """Require methodology/code authority files to be tracked and unmodified."""

    authority_files = [
        str(item)
        for item in config["post_coarse_execution"]["git_gate"]["authority_files"]
    ]
    for item in authority_files:
        _git_output(root, "ls-files", "--error-unmatch", "--", item)
    dirty = _git_output(root, "status", "--porcelain", "--", *authority_files)
    if dirty:
        raise PostCoarseIntegrityError(
            "Authority files are uncommitted or modified. Commit them before model fitting:\n"
            + dirty
        )
    index_rows = _git_output(root, "ls-files", "-s", "--", *authority_files).splitlines()
    if len(index_rows) != len(authority_files):
        raise PostCoarseIntegrityError("Git index does not contain every authority file exactly once.")
    return canonical_sha256(sorted(index_rows))


def build_authority_context(
    *,
    root: Path,
    config: Mapping[str, Any],
    coarse_dir: Path,
    require_committed: bool,
) -> AuthorityContext:
    section = config["post_coarse_execution"]
    authority = section["authority"]
    amendment_path = _resolve_from_root(root, authority["methodology_amendment"]["path"])
    backend_amendment_path = _resolve_from_root(
        root, authority["backend_amendment"]["path"]
    )
    contract_path = _resolve_from_root(root, authority["base_execution_contract"]["path"])
    registry_path = _resolve_from_root(root, authority["candidate_registry"]["path"])
    coarse_manifest_path = coarse_dir / section["coarse_source"]["manifest_name"]

    checks = (
        (
            amendment_path,
            str(authority["methodology_amendment"]["sha256"]),
            "methodology amendment",
        ),
        (
            backend_amendment_path,
            str(authority["backend_amendment"]["sha256"]),
            "QNN backend amendment",
        ),
        (
            contract_path,
            str(authority["base_execution_contract"]["sha256"]),
            "base execution contract",
        ),
        (
            registry_path,
            str(authority["candidate_registry"]["sha256"]),
            "candidate registry",
        ),
        (
            coarse_manifest_path,
            str(section["coarse_source"]["manifest_sha256"]),
            "coarse manifest",
        ),
    )
    for path, expected, label in checks:
        if not path.is_file():
            raise PostCoarseIntegrityError(f"Missing {label}: {path}")
        actual = file_sha256(path)
        if actual != expected:
            raise PostCoarseIntegrityError(
                f"SHA-256 mismatch for {label}: expected {expected}, got {actual}"
            )

    authority_git_index_sha256 = (
        verify_committed_authority(root, config) if require_committed else "PLAN_ONLY"
    )
    return AuthorityContext(
        amendment_path=amendment_path,
        amendment_sha256=file_sha256(amendment_path),
        backend_amendment_path=backend_amendment_path,
        backend_amendment_sha256=file_sha256(backend_amendment_path),
        base_contract_path=contract_path,
        base_contract_sha256=file_sha256(contract_path),
        candidate_registry_path=registry_path,
        candidate_registry_sha256=file_sha256(registry_path),
        coarse_manifest_path=coarse_manifest_path,
        coarse_manifest_sha256=file_sha256(coarse_manifest_path),
        authority_git_index_sha256=authority_git_index_sha256,
    )


def _authority_matches(
    manifest: Mapping[str, Any], authority: AuthorityContext, root: Path
) -> bool:
    expected = authority.as_dict(root)
    actual = manifest.get("authority")
    return isinstance(actual, dict) and canonical_sha256(actual) == canonical_sha256(expected)


# ---------------------------------------------------------------------------
# Coarse-search materialization without re-fitting
# ---------------------------------------------------------------------------


def _coarse_row(report: Mapping[str, Any]) -> dict[str, Any]:
    per_fold = list(report.get("per_fold") or [])
    fold_statuses = {
        str(item["fold_id"]): str(item["status"])
        for item in per_fold
        if "fold_id" in item and "status" in item
    }
    row = {
        "stage": "coarse",
        "family": str(report["family"]),
        "feature_block": str(report["feature_block"]),
        "configuration_id": str(report["configuration_id"]),
        "parameters": dict(report.get("parameters") or {}),
        "training_seed": int(report["training_seed"]),
        "fold_statuses": fold_statuses,
        "status": str(report["status"]),
        "pooled_oof_pr_auc": report.get("pooled_oof_pr_auc"),
        "oof_prediction_artifact_sha256": report.get(
            "canonical_oof_predictions_sha256"
        ),
        "failure_code": report.get("failure_code"),
    }
    return row


def load_coarse_results(
    coarse_dir: Path,
    *,
    config: Mapping[str, Any],
) -> tuple[dict[str, Any], list[CandidateExecutionResult]]:
    section = config["post_coarse_execution"]
    manifest_path = coarse_dir / section["coarse_source"]["manifest_name"]
    manifest = load_json(manifest_path)
    if manifest.get("mode") != "classical_mlp_coarse_search":
        raise PostCoarseIntegrityError("The source manifest is not a coarse-search run.")
    if manifest.get("status") != "COMPLETE":
        raise PostCoarseIntegrityError("Coarse search is not COMPLETE.")
    if manifest.get("source_kind") != "frozen_project_train":
        raise PostCoarseIntegrityError("Coarse source is not the frozen project train sample.")
    if manifest.get("all_candidate_positions_terminal") is not True:
        raise PostCoarseIntegrityError("Coarse candidate positions are not all terminal.")
    if manifest.get("model_selection_performed") is not False:
        raise PostCoarseIntegrityError("Coarse source already performed model selection.")
    if int(manifest.get("training_seed", -1)) != int(
        section["coarse_source"]["training_seed"]
    ):
        raise PostCoarseIntegrityError("Unexpected coarse-search training seed.")
    if manifest.get("protected_feature_years_opened") is not False:
        raise PostCoarseIntegrityError("Coarse source reports protected-year access.")
    if manifest.get("refinement_performed") is not False or manifest.get(
        "qnn_performed"
    ) is not False:
        raise PostCoarseIntegrityError("Coarse source is not a clean pre-refinement state.")

    run_manifest_path = coarse_dir / "run_manifest.json"
    if not run_manifest_path.is_file():
        raise PostCoarseIntegrityError("Missing coarse run_manifest.json.")
    run_manifest = load_json(run_manifest_path)
    expected_manifest_sha = run_manifest.get(
        "classical_mlp_coarse_search_manifest_sha256"
    )
    if expected_manifest_sha != file_sha256(manifest_path):
        raise PostCoarseIntegrityError("Coarse run-manifest hash chain is invalid.")
    eligibility_path = coarse_dir / "refinement_eligibility.json"
    eligibility_sha = manifest.get("refinement_eligibility_sha256")
    if (
        not eligibility_path.is_file()
        or not eligibility_sha
        or file_sha256(eligibility_path) != str(eligibility_sha)
    ):
        raise PostCoarseIntegrityError("Coarse refinement-eligibility hash chain is invalid.")

    expected_positions = int(section["coarse_source"]["expected_candidate_positions"])
    reports = list(manifest.get("candidate_results") or [])
    if len(reports) != expected_positions:
        raise PostCoarseIntegrityError(
            f"Expected {expected_positions} coarse positions, found {len(reports)}."
        )

    materialized: list[CandidateExecutionResult] = []
    for report in reports:
        row = _coarse_row(report)
        predictions: list[dict[str, Any]] = []
        candidate_manifest_rel = report.get("candidate_manifest")
        candidate_manifest_sha = report.get("candidate_manifest_sha256")
        if candidate_manifest_rel and candidate_manifest_sha:
            candidate_manifest_path = coarse_dir / str(candidate_manifest_rel)
            if not candidate_manifest_path.is_file() or file_sha256(
                candidate_manifest_path
            ) != str(candidate_manifest_sha):
                raise PostCoarseIntegrityError(
                    f"Coarse candidate manifest mismatch: {candidate_manifest_path}"
                )
        result = CandidateExecutionResult(row=row, predictions=predictions)
        if row["status"] == "COMPLETE":
            prediction_rel = report.get("canonical_oof_predictions")
            prediction_sha = report.get("canonical_oof_predictions_sha256")
            if not prediction_rel or not prediction_sha:
                raise PostCoarseIntegrityError(
                    f"Complete coarse candidate lacks predictions: {row['configuration_id']}"
                )
            prediction_path = coarse_dir / str(prediction_rel)
            if not prediction_path.is_file():
                raise PostCoarseIntegrityError(
                    f"Missing coarse OOF prediction artifact: {prediction_path}"
                )
            actual_prediction_sha = file_sha256(prediction_path)
            if actual_prediction_sha != str(prediction_sha):
                raise PostCoarseIntegrityError(
                    f"Coarse OOF prediction hash mismatch: {prediction_path}"
                )
            # Prediction payloads are intentionally loaded lazily. Reading all
            # complete OOF files at once would consume unnecessary memory; plan
            # mode streams every file only for SHA-256 verification, while rows
            # are materialized solely for candidates selected later.
            setattr(result, "_coarse_prediction_path", prediction_path)
            setattr(result, "_coarse_prediction_sha256", str(prediction_sha))
            setattr(result, "_coarse_prediction_expected_n", int(report.get("oof_key_count", -1)))
            setattr(result, "_coarse_reported_pr_auc", float(row["pooled_oof_pr_auc"]))
        materialized.append(result)

    identities = [
        (
            result.row["family"],
            result.row["feature_block"],
            result.row["configuration_id"],
            result.row["training_seed"],
        )
        for result in materialized
    ]
    if len(identities) != len(set(identities)):
        raise PostCoarseIntegrityError("Duplicate coarse candidate identity.")
    return manifest, materialized

def materialize_coarse_result(
    result: CandidateExecutionResult,
) -> CandidateExecutionResult:
    """Load and verify one selected coarse candidate's canonical OOF predictions."""

    if result.row.get("stage") != "coarse" or result.row.get("status") != "COMPLETE":
        return result
    if result.predictions:
        return result
    path = getattr(result, "_coarse_prediction_path", None)
    expected_sha = getattr(result, "_coarse_prediction_sha256", None)
    expected_n = getattr(result, "_coarse_prediction_expected_n", None)
    reported_pr_auc = getattr(result, "_coarse_reported_pr_auc", None)
    if not isinstance(path, Path) or not expected_sha:
        raise PostCoarseIntegrityError("Coarse result lacks its lazy prediction reference.")
    if not path.is_file() or file_sha256(path) != str(expected_sha):
        raise PostCoarseIntegrityError(f"Coarse OOF prediction hash mismatch: {path}")
    payload = load_json(path)
    predictions = [dict(item) for item in payload.get("rows") or []]
    predictions.sort(key=_canonical_prediction_sort_key)
    _assert_finite_predictions(predictions, str(path))
    if expected_n is not None and len(predictions) != int(expected_n):
        raise PostCoarseIntegrityError("Coarse OOF row count mismatch.")
    labels = [int(item["target_label"]) for item in predictions]
    scores = [float(item["raw_score"]) for item in predictions]
    recalculated = float(average_precision_score(labels, scores))
    if reported_pr_auc is not None and not math.isclose(
        recalculated, float(reported_pr_auc), rel_tol=0.0, abs_tol=1e-12
    ):
        raise PostCoarseIntegrityError(
            "Coarse pooled PR-AUC does not reproduce from canonical OOF scores."
        )
    result.predictions = predictions
    return result


def derive_primary_activations(
    coarse_results: Sequence[CandidateExecutionResult],
    runner: ProductionExperimentRunner | None,
    *,
    contract: Mapping[str, Any] | None = None,
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    effective_contract = runner.contract if runner is not None else contract
    if effective_contract is None:
        raise PostCoarseIntegrityError("A contract is required for activation derivation.")
    activations = select_refinement_families(
        [result.row for result in coarse_results], effective_contract
    )
    expected = [
        str(item)
        for item in config["post_coarse_execution"]["primary_refinement"][
            "expected_qualified_families_ordered"
        ]
    ]
    actual = [str(item["family"]) for item in activations]
    if actual != expected:
        raise PostCoarseIntegrityError(
            f"Primary refinement activation changed: expected {expected}, got {actual}."
        )
    expected_blocks = config["post_coarse_execution"]["primary_refinement"][
        "expected_feature_blocks"
    ]
    for activation in activations:
        family = str(activation["family"])
        if str(activation["feature_block"]) != str(expected_blocks[family]):
            raise PostCoarseIntegrityError(
                f"Unexpected refinement block for {family}: {activation['feature_block']}"
            )
    return activations


def derive_mlp_comparator_identity(
    coarse_results: Sequence[CandidateExecutionResult],
    *,
    contract: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    mlp_rows = [
        result.row
        for result in coarse_results
        if result.row["family"] == "pytorch_mlp"
        and result.row["status"] == "COMPLETE"
    ]
    if not mlp_rows:
        raise PostCoarseIntegrityError("No complete coarse MLP candidate exists.")
    leader = rank_candidates(mlp_rows, contract)[0]
    policy = config["post_coarse_execution"]["supplemental_mlp_comparator"]
    if str(leader["feature_block"]) != str(policy["expected_best_coarse_block"]):
        raise PostCoarseIntegrityError("Best coarse MLP block differs from the amendment.")
    if str(leader["configuration_id"]) != str(
        policy["expected_coarse_leader_configuration_id"]
    ):
        raise PostCoarseIntegrityError("Best coarse MLP identity differs from the amendment.")
    return {
        "family": "pytorch_mlp",
        "feature_block": str(leader["feature_block"]),
        "coarse_leader_configuration_id": str(leader["configuration_id"]),
        "coarse_leader_pooled_oof_pr_auc": float(leader["pooled_oof_pr_auc"]),
        "analysis_role": "SECONDARY_TITLE_ALIGNED_NEURAL_COMPARATOR",
    }


# ---------------------------------------------------------------------------
# Result references used for phase restart/resume
# ---------------------------------------------------------------------------


def _candidate_artifact_directory(
    output_dir: Path, row: Mapping[str, Any]
) -> Path:
    seed = row["training_seed"]
    if not isinstance(seed, int):
        raise PostCoarseIntegrityError("Candidate result reference requires an integer seed.")
    return (
        output_dir
        / "candidate_results"
        / str(row["stage"])
        / str(row["family"])
        / str(row["configuration_id"])
        / str(row["feature_block"]).replace("+", "_")
        / f"seed_{seed}"
    )


def result_reference(
    result: CandidateExecutionResult,
    *,
    output_dir: Path,
    root: Path,
    analysis_role: str,
) -> dict[str, Any]:
    row = dict(result.row)
    if isinstance(row.get("training_seed"), int):
        directory = _candidate_artifact_directory(output_dir, row)
        candidate_manifest = directory / "candidate_manifest.json"
        if not candidate_manifest.is_file():
            raise PostCoarseIntegrityError(
                f"Missing candidate manifest after execution: {candidate_manifest}"
            )
        return {
            "kind": "candidate",
            "analysis_role": analysis_role,
            "row": row,
            "candidate_manifest": _relative_or_absolute(candidate_manifest, root),
            "candidate_manifest_sha256": file_sha256(candidate_manifest),
        }
    prediction_artifact = row.get("oof_prediction_artifact")
    prediction_sha = row.get("oof_prediction_artifact_sha256")
    if not prediction_artifact or not prediction_sha:
        if row.get("status") != "COMPLETE":
            return {
                "kind": "seed_averaged_invalid",
                "analysis_role": analysis_role,
                "row": row,
            }
        raise PostCoarseIntegrityError("Complete seed-averaged result lacks predictions.")
    prediction_path = output_dir / str(prediction_artifact)
    if not prediction_path.is_file() or file_sha256(prediction_path) != str(
        prediction_sha
    ):
        raise PostCoarseIntegrityError("Seed-averaged prediction artifact mismatch.")
    return {
        "kind": "seed_averaged",
        "analysis_role": analysis_role,
        "row": row,
        "prediction_artifact": _relative_or_absolute(prediction_path, root),
        "prediction_artifact_sha256": file_sha256(prediction_path),
    }


def load_result_reference(
    reference: Mapping[str, Any],
    *,
    root: Path = ROOT,
) -> CandidateExecutionResult:
    kind = str(reference["kind"])
    row = dict(reference["row"])
    if kind == "seed_averaged_invalid":
        return CandidateExecutionResult(row=row, predictions=[])
    if kind == "seed_averaged":
        path = _resolve_from_root(root, str(reference["prediction_artifact"]))
        if not path.is_file() or file_sha256(path) != str(
            reference["prediction_artifact_sha256"]
        ):
            raise PostCoarseIntegrityError("Seed-averaged result reference mismatch.")
        payload = load_json(path)
        predictions = [dict(item) for item in payload.get("rows") or []]
        predictions.sort(key=_canonical_prediction_sort_key)
        _assert_finite_predictions(predictions, str(path))
        return CandidateExecutionResult(row=row, predictions=predictions)
    if kind != "candidate":
        raise PostCoarseIntegrityError(f"Unknown result reference kind: {kind}")

    candidate_manifest_path = _resolve_from_root(
        root, str(reference["candidate_manifest"])
    )
    if not candidate_manifest_path.is_file() or file_sha256(
        candidate_manifest_path
    ) != str(reference["candidate_manifest_sha256"]):
        raise PostCoarseIntegrityError("Candidate result reference mismatch.")
    candidate_manifest = load_json(candidate_manifest_path)
    manifest_row = candidate_manifest.get("candidate")
    if not isinstance(manifest_row, dict) or canonical_sha256(manifest_row) != canonical_sha256(
        row
    ):
        raise PostCoarseIntegrityError("Candidate row differs from its manifest.")

    predictions: list[dict[str, Any]] = []
    if row.get("status") == "COMPLETE":
        required_folds = list(row.get("fold_statuses") or {})
        for fold_id in required_folds:
            fold_dir = candidate_manifest_path.parent / str(fold_id)
            fold_manifest_path = fold_dir / "result_manifest.json"
            prediction_path = fold_dir / "oof_predictions.json"
            if not fold_manifest_path.is_file() or not prediction_path.is_file():
                raise PostCoarseIntegrityError(
                    f"Missing fold result while loading {candidate_manifest_path}: {fold_id}"
                )
            fold_manifest = load_json(fold_manifest_path)
            expected_sha = fold_manifest.get("oof_prediction_artifact_sha256")
            if not expected_sha or file_sha256(prediction_path) != str(expected_sha):
                raise PostCoarseIntegrityError("Fold prediction hash mismatch.")
            payload = load_json(prediction_path)
            predictions.extend(dict(item) for item in payload.get("rows") or [])
        predictions.sort(key=_canonical_prediction_sort_key)
        _assert_finite_predictions(predictions, str(candidate_manifest_path))
    return CandidateExecutionResult(row=row, predictions=predictions)


def load_phase_results(
    manifest: Mapping[str, Any],
    key: str,
    *,
    root: Path = ROOT,
) -> list[CandidateExecutionResult]:
    references = list(manifest.get(key) or [])
    return [load_result_reference(item, root=root) for item in references]


def historical_refinement_reuse_enabled(
    config: Mapping[str, Any],
) -> bool:
    reuse = config["post_coarse_execution"].get("historical_refinement_reuse")
    return isinstance(reuse, Mapping) and bool(reuse.get("enabled"))


def require_historical_refinement_reuse(
    *,
    config: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    reuse = config["post_coarse_execution"].get("historical_refinement_reuse")
    if not isinstance(reuse, Mapping) or not bool(reuse.get("enabled")):
        raise PostCoarseIntegrityError(
            "Historical refinement reuse is not enabled."
        )

    source = reuse["source_manifest"]
    manifest_path = _resolve_from_root(root, str(source["path"]))

    if not manifest_path.is_file():
        raise PostCoarseIntegrityError(
            f"Historical refinement manifest is missing: {manifest_path}"
        )

    actual_sha = file_sha256(manifest_path)
    expected_sha = str(source["sha256"])
    if actual_sha != expected_sha:
        raise PostCoarseIntegrityError(
            "Historical refinement manifest SHA-256 mismatch."
        )

    manifest = load_json(manifest_path)

    if str(manifest.get("status")) != str(reuse["required_status"]):
        raise PostCoarseIntegrityError(
            "Historical refinement manifest is not COMPLETE."
        )

    if manifest.get("protected_feature_years_opened") is not False:
        raise PostCoarseIntegrityError(
            "Historical refinement opened protected feature years."
        )

    primary_refs = list(manifest.get("primary_result_references") or [])
    mlp_refs = list(manifest.get("supplemental_mlp_result_references") or [])

    if len(primary_refs) != int(reuse["expected_primary_result_references"]):
        raise PostCoarseIntegrityError(
            "Historical primary refinement reference count mismatch."
        )

    if len(mlp_refs) != int(
        reuse["expected_supplemental_mlp_result_references"]
    ):
        raise PostCoarseIntegrityError(
            "Historical supplemental MLP reference count mismatch."
        )

    historical_authority = manifest.get("authority")
    if not isinstance(historical_authority, Mapping):
        raise PostCoarseIntegrityError(
            "Historical refinement authority is missing."
        )

    expected_contract = dict(reuse["source_execution_contract"])
    if historical_authority.get("base_execution_contract") != expected_contract:
        raise PostCoarseIntegrityError(
            "Historical refinement execution-contract authority mismatch."
        )

    expected_methodology = dict(reuse["source_methodology_amendment"])
    if historical_authority.get("methodology_amendment") != expected_methodology:
        raise PostCoarseIntegrityError(
            "Historical refinement methodology authority mismatch."
        )

    # Deep verification of every referenced candidate/fold artifact.
    primary_results = load_phase_results(
        manifest, "primary_result_references", root=root
    )
    mlp_results = load_phase_results(
        manifest, "supplemental_mlp_result_references", root=root
    )

    if len(primary_results) != len(primary_refs):
        raise PostCoarseIntegrityError(
            "Historical primary refinement artifact count mismatch."
        )

    if len(mlp_results) != len(mlp_refs):
        raise PostCoarseIntegrityError(
            "Historical MLP refinement artifact count mismatch."
        )

    return manifest


def require_refinement_manifest_for_current_config(
    path: Path,
    *,
    config: Mapping[str, Any],
    authority: AuthorityContext,
    root: Path,
) -> dict[str, Any]:
    if historical_refinement_reuse_enabled(config):
        configured = _resolve_from_root(
            root,
            str(
                config["post_coarse_execution"]
                ["historical_refinement_reuse"]
                ["source_manifest"]
                ["path"]
            ),
        )
        if path.resolve() != configured.resolve():
            raise PostCoarseIntegrityError(
                "Historical refinement path differs from configured source."
            )
        return require_historical_refinement_reuse(
            config=config,
            root=root,
        )

    return require_phase_manifest(
        path,
        allowed_statuses={"COMPLETE"},
        authority=authority,
        root=root,
    )


def historical_qnn_reuse_enabled(config: Mapping[str, Any]) -> bool:
    reuse = config["post_coarse_execution"].get("historical_qnn_reuse")
    return isinstance(reuse, Mapping) and bool(reuse.get("enabled"))


def require_historical_qnn_reuse(
    *,
    config: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    """Deep-verify the completed QNN phase frozen before a schedule amendment."""

    reuse = config["post_coarse_execution"].get("historical_qnn_reuse")
    if not isinstance(reuse, Mapping) or not bool(reuse.get("enabled")):
        raise PostCoarseIntegrityError("Historical QNN reuse is not enabled.")

    source = reuse["source_manifest"]
    manifest_path = _resolve_from_root(root, str(source["path"]))
    if not manifest_path.is_file():
        raise PostCoarseIntegrityError(
            f"Historical QNN manifest is missing: {manifest_path}"
        )
    if file_sha256(manifest_path) != str(source["sha256"]):
        raise PostCoarseIntegrityError("Historical QNN manifest SHA-256 mismatch.")

    manifest = load_json(manifest_path)
    if str(manifest.get("status")) != str(reuse["required_status"]):
        raise PostCoarseIntegrityError("Historical QNN manifest is not COMPLETE.")
    if manifest.get("protected_feature_years_opened") is not False:
        raise PostCoarseIntegrityError("Historical QNN phase opened protected years.")
    if manifest.get("authority") != dict(reuse["source_authority"]):
        raise PostCoarseIntegrityError("Historical QNN authority mismatch.")

    q1_refs = list(manifest.get("q1_result_references") or [])
    q2_refs = list(manifest.get("q2_result_references") or [])
    if len(q1_refs) != int(reuse["expected_q1_result_references"]):
        raise PostCoarseIntegrityError("Historical QNN Q1 reference count mismatch.")
    if len(q2_refs) != int(reuse["expected_q2_result_references"]):
        raise PostCoarseIntegrityError("Historical QNN Q2 reference count mismatch.")

    q1_results = load_phase_results(manifest, "q1_result_references", root=root)
    q2_results = load_phase_results(manifest, "q2_result_references", root=root)
    if any(result.row.get("status") != "COMPLETE" for result in q1_results):
        raise PostCoarseIntegrityError("Historical QNN Q1 contains a non-complete result.")
    if any(result.row.get("status") != "COMPLETE" for result in q2_results):
        raise PostCoarseIntegrityError("Historical QNN Q2 contains a non-complete result.")

    ansatz_path = _resolve_from_root(root, str(reuse["selected_ansatz_artifact"]["path"]))
    if file_sha256(ansatz_path) != str(reuse["selected_ansatz_artifact"]["sha256"]):
        raise PostCoarseIntegrityError("Historical QNN ansatz artifact mismatch.")
    if manifest.get("qnn_selected_ansatz_artifact_sha256") != file_sha256(ansatz_path):
        raise PostCoarseIntegrityError("Historical QNN ansatz hash chain mismatch.")

    ledger = manifest.get("qnn_resource_ledger")
    if not isinstance(ledger, Mapping) or not ledger.get("path") or not ledger.get("sha256"):
        raise PostCoarseIntegrityError("Historical QNN ledger reference is missing.")
    ledger_path = _resolve_from_root(root, str(ledger["path"]))
    if file_sha256(ledger_path) != str(ledger["sha256"]):
        raise PostCoarseIntegrityError("Historical QNN ledger hash mismatch.")
    return manifest


def require_qnn_manifest_for_current_config(
    path: Path,
    *,
    config: Mapping[str, Any],
    authority: AuthorityContext,
    root: Path,
) -> dict[str, Any]:
    if historical_qnn_reuse_enabled(config):
        configured = _resolve_from_root(
            root,
            str(
                config["post_coarse_execution"]
                ["historical_qnn_reuse"]
                ["source_manifest"]
                ["path"]
            ),
        )
        if path.resolve() != configured.resolve():
            raise PostCoarseIntegrityError(
                "Historical QNN path differs from configured source."
            )
        return require_historical_qnn_reuse(config=config, root=root)
    return require_phase_manifest(
        path,
        allowed_statuses=TERMINAL_QNN_PHASE_STATUSES,
        authority=authority,
        root=root,
    )


def historical_classical_confirmation_reuse_enabled(
    config: Mapping[str, Any],
) -> bool:
    reuse = config["post_coarse_execution"].get(
        "historical_classical_confirmation_reuse"
    )
    return isinstance(reuse, Mapping) and bool(reuse.get("enabled"))


def _verify_embedded_fold_manifests(
    references: Sequence[Mapping[str, Any]], *, root: Path
) -> None:
    """Verify that candidate manifests still bind the on-disk fold manifests."""

    for reference in references:
        if str(reference.get("kind")) != "candidate":
            continue
        candidate_path = _resolve_from_root(
            root, str(reference["candidate_manifest"])
        )
        candidate = load_json(candidate_path)
        embedded = list(candidate.get("fold_manifests") or [])
        expected_folds = list(
            dict(reference["row"].get("fold_statuses") or {}).keys()
        )
        actual_folds = [
            str(item.get("task_identity", {}).get("fold_id")) for item in embedded
        ]
        if actual_folds != expected_folds:
            raise PostCoarseIntegrityError(
                "Historical candidate fold order differs from its frozen row."
            )
        for fold_id, expected in zip(expected_folds, embedded, strict=True):
            fold_path = candidate_path.parent / fold_id / "result_manifest.json"
            if not fold_path.is_file() or canonical_sha256(
                load_json(fold_path)
            ) != canonical_sha256(expected):
                raise PostCoarseIntegrityError(
                    "Historical fold manifest differs from its candidate manifest."
                )


def require_historical_classical_confirmation_reuse(
    *,
    config: Mapping[str, Any],
    root: Path = ROOT,
) -> dict[str, Any]:
    """Deep-verify the classical confirmation gate frozen before v1.0.4."""

    reuse = config["post_coarse_execution"].get(
        "historical_classical_confirmation_reuse"
    )
    if not isinstance(reuse, Mapping) or not bool(reuse.get("enabled")):
        raise PostCoarseIntegrityError(
            "Historical classical confirmation reuse is not enabled."
        )

    source = reuse["source_manifest"]
    manifest_path = _resolve_from_root(root, str(source["path"]))
    if not manifest_path.is_file() or file_sha256(manifest_path) != str(
        source["sha256"]
    ):
        raise PostCoarseIntegrityError(
            "Historical classical confirmation manifest SHA-256 mismatch."
        )
    manifest = load_json(manifest_path)
    if str(manifest.get("status")) != str(reuse["required_status"]):
        raise PostCoarseIntegrityError(
            "Historical classical confirmation is not COMPLETE."
        )
    if manifest.get("protected_feature_years_opened") is not False:
        raise PostCoarseIntegrityError(
            "Historical classical confirmation opened protected years."
        )
    if manifest.get("qnn_confirmation_started") is not False:
        raise PostCoarseIntegrityError(
            "Historical classical gate was not frozen before QNN confirmation."
        )
    if manifest.get("authority") != dict(reuse["source_authority"]):
        raise PostCoarseIntegrityError(
            "Historical classical confirmation authority mismatch."
        )

    selection = reuse["selection_artifact"]
    selection_path = _resolve_from_root(root, str(selection["path"]))
    if not selection_path.is_file() or file_sha256(selection_path) != str(
        selection["sha256"]
    ):
        raise PostCoarseIntegrityError(
            "Historical confirmation selection SHA-256 mismatch."
        )
    if manifest.get("confirmation_selection_sha256") != file_sha256(
        selection_path
    ):
        raise PostCoarseIntegrityError(
            "Historical classical-selection hash chain mismatch."
        )
    selection_payload = load_json(selection_path)
    if (
        selection_payload.get("status") != "FROZEN_BEFORE_CONFIRMATION_FITS"
        or selection_payload.get("authority") != dict(reuse["source_authority"])
        or selection_payload.get("protected_feature_years_opened") is not False
    ):
        raise PostCoarseIntegrityError(
            "Historical confirmation selection identity is invalid."
        )

    source_qnn = reuse["source_qnn_phase_manifest"]
    source_qnn_path = _resolve_from_root(root, str(source_qnn["path"]))
    if not source_qnn_path.is_file() or file_sha256(source_qnn_path) != str(
        source_qnn["sha256"]
    ):
        raise PostCoarseIntegrityError(
            "Historical classical gate source-QNN manifest mismatch."
        )
    if manifest.get("source_qnn_phase_manifest_sha256") != file_sha256(
        source_qnn_path
    ):
        raise PostCoarseIntegrityError(
            "Historical classical source-QNN hash chain mismatch."
        )

    primary_refs = list(manifest.get("primary_confirmed_result_references") or [])
    extra_refs = list(
        manifest.get("classical_extra_seed_candidate_result_references") or []
    )
    if len(primary_refs) != int(reuse["expected_primary_result_references"]):
        raise PostCoarseIntegrityError(
            "Historical classical primary reference count mismatch."
        )
    if len(extra_refs) != int(reuse["expected_extra_seed_result_references"]):
        raise PostCoarseIntegrityError(
            "Historical classical extra-seed reference count mismatch."
        )
    supplemental_ref = manifest.get("supplemental_mlp_confirmed_result_reference")
    if not isinstance(supplemental_ref, Mapping):
        raise PostCoarseIntegrityError(
            "Historical supplemental MLP confirmation reference is missing."
        )

    primary_results = load_phase_results(
        manifest, "primary_confirmed_result_references", root=root
    )
    extra_results = load_phase_results(
        manifest, "classical_extra_seed_candidate_result_references", root=root
    )
    supplemental_result = load_result_reference(supplemental_ref, root=root)
    if any(result.row.get("status") != "COMPLETE" for result in primary_results):
        raise PostCoarseIntegrityError(
            "Historical classical primary confirmation is incomplete."
        )
    if any(result.row.get("status") != "COMPLETE" for result in extra_results):
        raise PostCoarseIntegrityError(
            "Historical classical extra-seed confirmation is incomplete."
        )
    if supplemental_result.row.get("status") != "COMPLETE":
        raise PostCoarseIntegrityError(
            "Historical supplemental MLP confirmation is incomplete."
        )
    expected_seeds = sorted(int(seed) for seed in reuse["confirmation_seeds"])
    actual_seeds = sorted(
        {int(result.row["training_seed"]) for result in extra_results}
    )
    if actual_seeds != expected_seeds:
        raise PostCoarseIntegrityError(
            "Historical classical confirmation seeds mismatch."
        )
    extra_lookup = _result_lookup(extra_results)
    if len(extra_lookup) != len(extra_results):
        raise PostCoarseIntegrityError(
            "Historical classical extra-seed identities are not unique."
        )
    expected_per_seed = int(reuse["expected_primary_result_references"])
    if any(
        sum(
            int(result.row["training_seed"]) == seed
            for result in extra_results
        )
        != expected_per_seed
        for seed in expected_seeds
    ):
        raise PostCoarseIntegrityError(
            "Historical classical extra-seed coverage is incomplete."
        )
    _verify_embedded_fold_manifests(extra_refs, root=root)

    schedule = config["post_coarse_execution"][
        "confirmation_schedule_amendment"
    ]
    worker = schedule["frozen_qnn_worker"]
    worker_path = _resolve_from_root(root, str(worker["path"]))
    if not worker_path.is_file() or file_sha256(worker_path) != str(
        worker["sha256"]
    ):
        raise PostCoarseIntegrityError(
            "QNN worker changed under the confirmation-only schedule amendment."
        )
    return manifest


def _result_lookup(
    results: Iterable[CandidateExecutionResult],
) -> dict[tuple[str, str, str, int], CandidateExecutionResult]:
    lookup: dict[tuple[str, str, str, int], CandidateExecutionResult] = {}
    for result in results:
        seed = result.row["training_seed"]
        if not isinstance(seed, int):
            continue
        key = (
            str(result.row["family"]),
            str(result.row["feature_block"]),
            str(result.row["configuration_id"]),
            seed,
        )
        if key in lookup:
            raise PostCoarseIntegrityError(f"Duplicate result identity: {key}")
        lookup[key] = result
    return lookup


# ---------------------------------------------------------------------------
# Runner construction and phase gates
# ---------------------------------------------------------------------------


def build_runner_and_folds(
    *,
    config: Mapping[str, Any],
    authority: AuthorityContext,
    output_dir: Path,
    classical_python: Path,
    qnn_python: Path,
    configure_qnn_ledger: bool,
    qnn_ledger_path: Path | None = None,
) -> tuple[
    ProductionExperimentRunner,
    Mapping[str, tuple[Any, Any, Any, Any]],
]:
    production_runner_spec = (
        config["post_coarse_execution"]["authority"]["production_runner"]
    )
    production_runner_path = _resolve_from_root(
        ROOT, str(production_runner_spec["path"])
    )

    if not production_runner_path.is_file():
        raise PostCoarseIntegrityError(
            f"Missing production runner config: {production_runner_path}"
        )
    if file_sha256(production_runner_path) != str(
        production_runner_spec["sha256"]
    ):
        raise PostCoarseIntegrityError(
            "Production runner configuration SHA-256 mismatch."
        )

    executor = SubprocessFoldExecutor(
        root=ROOT,
        classical_python=classical_python,
        qnn_python=qnn_python,
        runner_config_path=production_runner_path,
        contract_path=authority.base_contract_path,
    )
    runner = ProductionExperimentRunner(
        output_dir=output_dir,
        executor=executor,
        runner_config_path=production_runner_path,
        contract_path=authority.base_contract_path,
        registry_path=authority.candidate_registry_path,
    )
    sample, expectations = runner.load_frozen_project_sample()
    folds = runner.verify_sample_and_folds(sample, expectations)
    runner._write_runtime_metadata(canonical_candidate_index(runner.contract, runner.registry))
    if configure_qnn_ledger:
        runner._configure_qnn_ledger(ledger_path=qnn_ledger_path)
    return runner, folds


def _execute_qnn_candidate_batch(
    runner: ProductionExperimentRunner,
    requests: Sequence[Mapping[str, Any]],
) -> list[CandidateExecutionResult]:
    """Execute independent QNN candidates concurrently and return frozen order."""

    if not requests:
        return []
    scheduler = runner.runner_config.get("execution_scheduler", {})
    maximum = int(scheduler.get("maximum_parallel_qnn_candidates", 1))
    workers = max(1, min(maximum, len(requests)))
    if workers == 1:
        return [runner._execute_candidate(**dict(request)) for request in requests]

    pool = ThreadPoolExecutor(
        max_workers=workers,
        thread_name_prefix="qnn-candidate",
    )
    futures = [
        pool.submit(runner._execute_candidate, **dict(request))
        for request in requests
    ]
    try:
        return [future.result() for future in futures]
    except BaseException:
        request_shutdown = getattr(runner.executor, "request_shutdown", None)
        if callable(request_shutdown):
            request_shutdown()
        for future in futures:
            future.cancel()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _prewarm_qnn_fold_cache(
    runner: ProductionExperimentRunner,
    folds: Mapping[str, tuple[Any, Any, Any, Any]],
    requests: Sequence[Mapping[str, Any]],
) -> None:
    identities = {
        (
            str(request["feature_block"]),
            int(dict(request["candidate"])["qubits_pca"]),
        )
        for request in requests
    }
    required_folds = runner.contract["execution_failure_state_machine"]["required_folds"]
    for block, qubits in sorted(identities):
        for fold_id in required_folds:
            runner._prepare_fold(
                block=block,
                fold_tuple=folds[str(fold_id)],
                qubits=qubits,
            )


def require_phase_manifest(
    path: Path,
    *,
    allowed_statuses: set[str],
    authority: AuthorityContext,
    root: Path,
) -> dict[str, Any]:
    if not path.is_file():
        raise PostCoarseIntegrityError(f"Required phase manifest is missing: {path}")
    manifest = load_json(path)
    if str(manifest.get("status")) not in allowed_statuses:
        raise PostCoarseIntegrityError(
            f"Phase gate failed for {path.name}: {manifest.get('status')}"
        )
    if not _authority_matches(manifest, authority, root):
        raise PostCoarseIntegrityError(f"Authority changed since {path.name} was created.")
    if manifest.get("protected_feature_years_opened") is not False:
        raise PostCoarseIntegrityError(f"Protected-year flag is invalid in {path.name}.")
    return manifest


def _phase_manifest_existing(
    path: Path,
    *,
    statuses: set[str],
    authority: AuthorityContext,
    root: Path,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return require_phase_manifest(
        path,
        allowed_statuses=statuses,
        authority=authority,
        root=root,
    )


def _terminal_counts(results: Sequence[CandidateExecutionResult]) -> dict[str, int]:
    return {
        "candidate_positions": len(results),
        "complete": sum(result.row.get("status") == "COMPLETE" for result in results),
        "technically_invalid": sum(
            result.row.get("status") != "COMPLETE" for result in results
        ),
    }


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def create_plan(
    *,
    config: Mapping[str, Any],
    coarse_dir: Path,
    output_dir: Path,
    authority: AuthorityContext,
) -> dict[str, Any]:
    # Load the frozen contract/registry without creating a worker environment.
    from src.modeling.model_execution_contract import load_contract, load_registry

    contract = load_contract(authority.base_contract_path)
    registry = load_registry(authority.candidate_registry_path)
    coarse_manifest, coarse_results = load_coarse_results(coarse_dir, config=config)
    activations = derive_primary_activations(
        coarse_results, None, contract=contract, config=config
    )
    mlp_identity = derive_mlp_comparator_identity(
        coarse_results, contract=contract, config=config
    )
    folds_n = len(contract["execution_failure_state_machine"]["required_folds"])
    primary_candidates = sum(
        len(registry["refinement"][str(item["family"])]) for item in activations
    )
    mlp_candidates = len(registry["refinement"]["pytorch_mlp"])
    q1_positions = len(registry["qnn"]["stage_q1"]) * len(BLOCKS)
    q2_positions = len(registry["qnn"]["stage_q2"]) * len(BLOCKS)
    q2_reused_positions = sum(
        bool(candidate.get("reuse_q1_winner"))
        for candidate in registry["qnn"]["stage_q2"]
    ) * len(BLOCKS)
    confirmation_policy = contract["confirmation"]
    primary_confirmation_slots = int(
        confirmation_policy["classical_mlp_confirmation_slots"]
    )
    qnn_confirmation_slots = int(confirmation_policy["qnn_confirmation_slots"])
    extra_seeds_n = len(confirmation_policy["confirmation_seeds"])
    plan = {
        "schema_version": 1,
        "id": "post_coarse_execution_plan_v1_0_0",
        "status": "PLAN_ONLY_NO_MODEL_FIT",
        "authority": authority.as_dict(ROOT),
        "coarse_source": {
            "status": coarse_manifest["status"],
            "candidate_positions": len(coarse_results),
            "model_fit_reused_not_repeated": True,
        },
        "primary_refinement": {
            "activations": activations,
            "candidate_positions": primary_candidates,
            "fold_fits": primary_candidates * folds_n,
            "may_be_changed_by_mlp_supplement": False,
        },
        "supplemental_mlp_comparator": {
            **mlp_identity,
            "candidate_positions": mlp_candidates,
            "fold_fits": mlp_candidates * folds_n,
            "primary_ranking_eligible": False,
        },
        "qnn": {
            "q1_candidate_positions": q1_positions,
            "q1_fold_fits": q1_positions * folds_n,
            "q2_logical_candidate_positions": q2_positions,
            "q2_reused_q1_positions": q2_reused_positions,
            "q2_new_fold_fits": (q2_positions - q2_reused_positions) * folds_n,
            "confirmation_slots": qnn_confirmation_slots,
            "confirmation_additional_fold_fits": qnn_confirmation_slots
            * extra_seeds_n
            * folds_n,
        },
        "primary_confirmation": {
            "slots": primary_confirmation_slots,
            "additional_fold_fits": primary_confirmation_slots
            * extra_seeds_n
            * folds_n,
        },
        "supplemental_mlp_confirmation": {
            "maximum_additional_slots": 1,
            "maximum_additional_fold_fits": extra_seeds_n * folds_n,
            "deduplicated_if_already_in_primary_confirmation": True,
        },
        "neural_comparison_inference": {
            "resampling_unit": config["post_coarse_execution"]["inference"][
                "resampling_unit"
            ],
            "paired_cluster_draws_across_models": config[
                "post_coarse_execution"
            ]["inference"]["paired_cluster_draws_across_models"],
            "replicates": config["post_coarse_execution"]["inference"][
                "replicates"
            ],
            "confidence_level": config["post_coarse_execution"]["inference"][
                "confidence_level"
            ],
            "seed": config["post_coarse_execution"]["inference"]["seed"],
            "model_fit_performed": False,
        },
        "stage_order": ["refinement", "qnn", "confirmation", "inference", "report"],
        "protected_feature_years_opened": False,
        "project_data_model_fit_performed": False,
        "planned_output_dir": _relative_or_absolute(output_dir, ROOT),
    }
    atomic_write_json(output_dir / "post_coarse_plan.json", plan)
    return plan


# ---------------------------------------------------------------------------
# Refinement phase
# ---------------------------------------------------------------------------


def run_refinement_phase(
    *,
    config: Mapping[str, Any],
    coarse_dir: Path,
    output_dir: Path,
    authority: AuthorityContext,
    classical_python: Path,
    qnn_python: Path,
) -> dict[str, Any]:
    manifest_path = output_dir / "refinement_phase_manifest.json"

    if historical_refinement_reuse_enabled(config):
        return require_historical_refinement_reuse(
            config=config,
            root=ROOT,
        )

    existing = _phase_manifest_existing(
        manifest_path,
        statuses={"COMPLETE"},
        authority=authority,
        root=ROOT,
    )
    if existing is not None:
        return existing

    started = time.monotonic()
    _, coarse_results = load_coarse_results(coarse_dir, config=config)
    runner, folds = build_runner_and_folds(
        config=config,
        authority=authority,
        output_dir=output_dir,
        classical_python=classical_python,
        qnn_python=qnn_python,
        configure_qnn_ledger=False,
    )
    activations = derive_primary_activations(
        coarse_results, runner, config=config
    )
    mlp_identity = derive_mlp_comparator_identity(
        coarse_results, contract=runner.contract, config=config
    )

    primary_results: list[CandidateExecutionResult] = []
    for activation in activations:
        family = str(activation["family"])
        block = str(activation["feature_block"])
        for candidate_spec in runner.registry["refinement"][family]:
            candidate = runner._candidate_parameters(
                "refinement", family, str(candidate_spec["configuration_id"])
            )
            primary_results.append(
                runner._execute_candidate(
                    stage="refinement",
                    family=family,
                    feature_block=block,
                    candidate=candidate,
                    training_seed=int(runner.contract["confirmation"]["coarse_seed"]),
                    folds=folds,
                )
            )

    mlp_results: list[CandidateExecutionResult] = []
    mlp_block = str(mlp_identity["feature_block"])
    expected_ids = [
        str(value)
        for value in config["post_coarse_execution"]["supplemental_mlp_comparator"][
            "refinement_configuration_ids"
        ]
    ]
    actual_ids = [
        str(item["configuration_id"])
        for item in runner.registry["refinement"]["pytorch_mlp"]
    ]
    if actual_ids != expected_ids:
        raise PostCoarseIntegrityError("Frozen MLP refinement candidate list changed.")
    for configuration_id in expected_ids:
        candidate = runner._candidate_parameters(
            "refinement", "pytorch_mlp", configuration_id
        )
        mlp_results.append(
            runner._execute_candidate(
                stage="refinement",
                family="pytorch_mlp",
                feature_block=mlp_block,
                candidate=candidate,
                training_seed=int(runner.contract["confirmation"]["coarse_seed"]),
                folds=folds,
            )
        )

    manifest = {
        "schema_version": 1,
        "id": "post_coarse_refinement_phase_v1_0_0",
        "status": "COMPLETE",
        "authority": authority.as_dict(ROOT),
        "primary_track": {
            "activation_rule_unchanged": True,
            "activations": activations,
            "counts": _terminal_counts(primary_results),
            "primary_global_ranking_eligible": True,
        },
        "supplemental_mlp_comparator": {
            **mlp_identity,
            "counts": _terminal_counts(mlp_results),
            "primary_global_ranking_eligible": False,
            "claim_role": "secondary_title_aligned_comparison_only",
        },
        "primary_result_references": [
            result_reference(
                result,
                output_dir=output_dir,
                root=ROOT,
                analysis_role="PRIMARY_FROZEN_REFINEMENT",
            )
            for result in primary_results
        ],
        "supplemental_mlp_result_references": [
            result_reference(
                result,
                output_dir=output_dir,
                root=ROOT,
                analysis_role="SECONDARY_TITLE_ALIGNED_NEURAL_COMPARATOR",
            )
            for result in mlp_results
        ],
        "runtime_seconds": float(time.monotonic() - started),
        "protected_feature_years_opened": False,
        "project_data_model_fit_performed": True,
        "qnn_performed": False,
    }
    atomic_write_json(manifest_path, manifest)
    return manifest


# ---------------------------------------------------------------------------
# QNN Q1/Q2 phase
# ---------------------------------------------------------------------------


def run_qnn_phase(
    *,
    config: Mapping[str, Any],
    coarse_dir: Path,
    output_dir: Path,
    authority: AuthorityContext,
    classical_python: Path,
    qnn_python: Path,
) -> dict[str, Any]:
    if historical_qnn_reuse_enabled(config):
        return require_historical_qnn_reuse(config=config, root=ROOT)

    manifest_path = output_dir / "qnn_phase_manifest.json"
    existing = _phase_manifest_existing(
        manifest_path,
        statuses=TERMINAL_QNN_PHASE_STATUSES,
        authority=authority,
        root=ROOT,
    )
    if existing is not None:
        return existing

    require_refinement_manifest_for_current_config(
        output_dir / "refinement_phase_manifest.json",
        config=config,
        authority=authority,
        root=ROOT,
    )
    # Re-verify coarse source at the gate; its scores are not used to select Q1.
    load_coarse_results(coarse_dir, config=config)
    started = time.monotonic()
    runner, folds = build_runner_and_folds(
        config=config,
        authority=authority,
        output_dir=output_dir,
        classical_python=classical_python,
        qnn_python=qnn_python,
        configure_qnn_ledger=True,
    )

    q1_results: list[CandidateExecutionResult] = []
    for block in runner.contract["canonical_ordering"]["feature_block_order"]:
        requests: list[dict[str, Any]] = []
        for candidate_spec in runner.registry["qnn"]["stage_q1"]:
            candidate = runner._candidate_parameters(
                "qnn_q1", "qnn", str(candidate_spec["configuration_id"])
            )
            requests.append(
                {
                    "stage": "qnn_q1",
                    "family": "qnn",
                    "feature_block": str(block),
                    "candidate": candidate,
                    "training_seed": int(
                        runner.contract["confirmation"]["coarse_seed"]
                    ),
                    "folds": folds,
                    "selected_ansatz_id": str(candidate["ansatz"]),
                }
            )
        _prewarm_qnn_fold_cache(runner, folds, requests)
        q1_results.extend(_execute_qnn_candidate_batch(runner, requests))

    ansatz_selection = select_qnn_ansatz(
        [result.row for result in q1_results], runner.contract
    )
    ansatz_artifact = {
        "schema_version": 1,
        "authority": authority.as_dict(ROOT),
        **ansatz_selection,
        "selection_data": "Q1_OOF_2015_2020_only",
        "protected_feature_years_opened": False,
    }
    ansatz_sha = atomic_write_json(
        output_dir / "qnn_selected_ansatz.json", ansatz_artifact
    )

    q2_results: list[CandidateExecutionResult] = []
    if ansatz_selection["status"] == "SELECTED":
        selected_ansatz = str(ansatz_selection["selected_ansatz_id"])
        q1_by_block = {
            str(result.row["feature_block"]): result
            for result in q1_results
            if str(result.row["parameters"]["ansatz"]) == selected_ansatz
        }
        if set(q1_by_block) != set(BLOCKS):
            raise PostCoarseIntegrityError(
                "Selected Q1 ansatz is not represented in all three feature blocks."
            )
        for block in runner.contract["canonical_ordering"]["feature_block_order"]:
            block_candidates: list[tuple[Mapping[str, Any], bool]] = []
            requests = []
            for candidate_spec in runner.registry["qnn"]["stage_q2"]:
                candidate = runner._candidate_parameters(
                    "qnn_q2", "qnn", str(candidate_spec["configuration_id"])
                )
                reuse = bool(candidate.get("reuse_q1_winner"))
                block_candidates.append((candidate, reuse))
                if not reuse:
                    requests.append(
                        {
                            "stage": "qnn_q2",
                            "family": "qnn",
                            "feature_block": str(block),
                            "candidate": candidate,
                            "training_seed": int(
                                runner.contract["confirmation"]["coarse_seed"]
                            ),
                            "folds": folds,
                            "selected_ansatz_id": selected_ansatz,
                        }
                    )
            _prewarm_qnn_fold_cache(runner, folds, requests)
            executed = iter(_execute_qnn_candidate_batch(runner, requests))
            for candidate, reuse in block_candidates:
                if reuse:
                    q2_results.append(
                        runner._reuse_q1_as_q2_t0(
                            source=q1_by_block[str(block)],
                            q2_candidate=candidate,
                            selected_ansatz_id=selected_ansatz,
                        )
                    )
                else:
                    q2_results.append(next(executed))

    status = (
        "COMPLETE"
        if ansatz_selection["status"] == "SELECTED"
        else "QNN_TECHNICALLY_INFEASIBLE"
    )
    qnn_ledger = output_dir / "qnn_resource_ledger.json"
    manifest = {
        "schema_version": 1,
        "id": "post_coarse_qnn_phase_v1_0_0",
        "status": status,
        "authority": authority.as_dict(ROOT),
        "refinement_gate_passed": True,
        "ansatz_selection": ansatz_selection,
        "qnn_selected_ansatz_artifact_sha256": ansatz_sha,
        "q1_counts": _terminal_counts(q1_results),
        "q2_counts": _terminal_counts(q2_results),
        "q1_result_references": [
            result_reference(
                result,
                output_dir=output_dir,
                root=ROOT,
                analysis_role="QNN_Q1_ANSATZ_SELECTION",
            )
            for result in q1_results
        ],
        "q2_result_references": [
            result_reference(
                result,
                output_dir=output_dir,
                root=ROOT,
                analysis_role="QNN_Q2_BLOCK_SPECIFIC_REFINEMENT",
            )
            for result in q2_results
        ],
        "qnn_resource_ledger": {
            "path": _relative_or_absolute(qnn_ledger, ROOT)
            if qnn_ledger.is_file()
            else None,
            "sha256": file_sha256(qnn_ledger) if qnn_ledger.is_file() else None,
        },
        "runtime_seconds": float(time.monotonic() - started),
        "protected_feature_years_opened": False,
        "project_data_model_fit_performed": True,
    }
    atomic_write_json(manifest_path, manifest)
    return manifest


# ---------------------------------------------------------------------------
# Confirmation and final development-only outputs
# ---------------------------------------------------------------------------


def _base_key(result: CandidateExecutionResult) -> tuple[str, str, str, int]:
    seed = result.row["training_seed"]
    if not isinstance(seed, int):
        raise PostCoarseIntegrityError("Base confirmation result must have an integer seed.")
    return (
        str(result.row["family"]),
        str(result.row["feature_block"]),
        str(result.row["configuration_id"]),
        seed,
    )


def _confirm_candidate(
    *,
    runner: ProductionExperimentRunner,
    folds: Mapping[str, tuple[Any, Any, Any, Any]],
    base: CandidateExecutionResult,
    confirmation_seeds: Sequence[int],
    selected_ansatz_id: str | None = None,
) -> tuple[CandidateExecutionResult, list[CandidateExecutionResult]]:
    if base.row.get("stage") == "coarse":
        materialize_coarse_result(base)
    stage = str(base.row["stage"])
    family = str(base.row["family"])
    candidate = runner._candidate_parameters(
        stage, family, str(base.row["configuration_id"])
    )
    extras = [
        runner._execute_candidate(
            stage=stage,
            family=family,
            feature_block=str(base.row["feature_block"]),
            candidate=candidate,
            training_seed=int(seed),
            folds=folds,
            selected_ansatz_id=selected_ansatz_id,
        )
        for seed in confirmation_seeds
    ]
    return runner._aggregate_confirmed(base, extras), extras


def _confirm_qnn_candidates_parallel(
    *,
    runner: ProductionExperimentRunner,
    folds: Mapping[str, tuple[Any, Any, Any, Any]],
    jobs: Sequence[tuple[CandidateExecutionResult, Mapping[str, Any]]],
    confirmation_seeds: Sequence[int],
    maximum_workers: int,
) -> list[tuple[CandidateExecutionResult, list[CandidateExecutionResult]]]:
    """Confirm QNN representatives via a bounded global fold queue.

    Fold processes may start in a different order, but candidate, seed and fold
    results are assembled in the contract's frozen canonical order.
    """

    if not jobs:
        return []
    if maximum_workers < 1 or maximum_workers > 4:
        raise PostCoarseIntegrityError(
            "QNN confirmation fold parallelism must be between one and four."
        )

    prepared_jobs: list[
        tuple[CandidateExecutionResult, Mapping[str, Any], dict[str, Any]]
    ] = []
    prewarm_requests: list[dict[str, Any]] = []
    for base, selection in jobs:
        candidate = runner._candidate_parameters(
            str(base.row["stage"]),
            str(base.row["family"]),
            str(base.row["configuration_id"]),
        )
        prewarm_requests.append(
            {
                "feature_block": str(base.row["feature_block"]),
                "candidate": candidate,
            }
        )
        if str(selection["selected_ansatz_id"]) != str(
            base.row.get("selected_ansatz_id")
        ):
            raise PostCoarseIntegrityError(
                "Frozen QNN confirmation ansatz differs from its Q2 source."
            )
        if [int(seed) for seed in selection["confirmation_seeds"]] != [
            int(seed) for seed in confirmation_seeds
        ]:
            raise PostCoarseIntegrityError(
                "Frozen QNN confirmation seeds differ from the contract."
            )
        prepared_jobs.append((base, selection, candidate))
    _prewarm_qnn_fold_cache(runner, folds, prewarm_requests)

    required_folds = [
        str(item)
        for item in runner.contract["execution_failure_state_machine"][
            "required_folds"
        ]
    ]
    if not required_folds or not confirmation_seeds:
        raise PostCoarseIntegrityError(
            "QNN confirmation requires non-empty frozen folds and seeds."
        )
    work: list[tuple[int, int, int, dict[str, Any]]] = []
    for job_index, (base, selection, candidate) in enumerate(prepared_jobs):
        for seed_index, seed in enumerate(confirmation_seeds):
            for fold_index, fold_id in enumerate(required_folds):
                work.append(
                    (
                        job_index,
                        seed_index,
                        fold_index,
                        {
                            "stage": str(base.row["stage"]),
                            "family": str(base.row["family"]),
                            "feature_block": str(base.row["feature_block"]),
                            "candidate": candidate,
                            "training_seed": int(seed),
                            "folds": folds,
                            "fold_id": fold_id,
                            "selected_ansatz_id": str(
                                selection["selected_ansatz_id"]
                            ),
                        },
                    )
                )

    def execute(item: tuple[int, int, int, dict[str, Any]]) -> Any:
        return runner._execute_candidate_fold(**item[3])

    workers = min(maximum_workers, len(work))
    if workers == 1:
        completed_folds = [execute(item) for item in work]
    else:
        pool = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="qnn-confirmation-fold",
        )
        futures = [pool.submit(execute, item) for item in work]
        try:
            # Reading futures in submission order preserves deterministic assembly.
            completed_folds = [future.result() for future in futures]
        except BaseException:
            request_shutdown = getattr(runner.executor, "request_shutdown", None)
            if callable(request_shutdown):
                request_shutdown()
            for future in futures:
                future.cancel()
            raise
        finally:
            pool.shutdown(wait=True, cancel_futures=True)

    completed_by_identity = {
        (job_index, seed_index, fold_index): result
        for (job_index, seed_index, fold_index, _), result in zip(
            work, completed_folds, strict=True
        )
    }
    confirmed: list[
        tuple[CandidateExecutionResult, list[CandidateExecutionResult]]
    ] = []
    for job_index, (base, selection, candidate) in enumerate(prepared_jobs):
        extras: list[CandidateExecutionResult] = []
        for seed_index, seed in enumerate(confirmation_seeds):
            fold_results = [
                completed_by_identity[(job_index, seed_index, fold_index)]
                for fold_index in range(len(required_folds))
            ]
            extras.append(
                runner._assemble_candidate_execution(
                    stage=str(base.row["stage"]),
                    family=str(base.row["family"]),
                    feature_block=str(base.row["feature_block"]),
                    candidate=candidate,
                    training_seed=int(seed),
                    fold_results=fold_results,
                    selected_ansatz_id=str(selection["selected_ansatz_id"]),
                )
            )
        confirmed.append((runner._aggregate_confirmed(base, extras), extras))
    return confirmed


def _configure_confirmation_qnn_ledger(
    *,
    runner: ProductionExperimentRunner,
    config: Mapping[str, Any],
    source_qnn_manifest: Mapping[str, Any],
    output_dir: Path,
) -> Path:
    """Fork the frozen QNN ledger before recording confirmation attempts."""

    schedule = config["post_coarse_execution"].get(
        "confirmation_schedule_amendment"
    )
    if not isinstance(schedule, Mapping):
        raise PostCoarseIntegrityError(
            "QNN confirmation requires a versioned schedule amendment."
        )
    configured_path = schedule.get("qnn_confirmation_resource_ledger")
    if not configured_path:
        raise PostCoarseIntegrityError(
            "QNN confirmation ledger path is not configured."
        )
    confirmation_path = _resolve_from_root(ROOT, str(configured_path))
    if confirmation_path.parent.resolve() != output_dir.resolve():
        raise PostCoarseIntegrityError(
            "QNN confirmation ledger must live in the configured output directory."
        )

    source = source_qnn_manifest.get("qnn_resource_ledger")
    if not isinstance(source, Mapping):
        raise PostCoarseIntegrityError("Source QNN ledger reference is missing.")
    source_path = _resolve_from_root(ROOT, str(source["path"]))
    if source_path.resolve() == confirmation_path.resolve():
        raise PostCoarseIntegrityError(
            "QNN confirmation must not mutate the frozen source ledger."
        )
    if file_sha256(source_path) != str(source["sha256"]):
        raise PostCoarseIntegrityError("Frozen source QNN ledger hash mismatch.")
    source_payload = load_json(source_path)

    if not confirmation_path.exists():
        atomic_write_json(confirmation_path, source_payload)
    else:
        confirmation_payload = load_json(confirmation_path)
        source_attempts = list(source_payload.get("attempts") or [])
        confirmation_attempts = list(confirmation_payload.get("attempts") or [])
        if confirmation_attempts[: len(source_attempts)] != source_attempts:
            raise PostCoarseIntegrityError(
                "QNN confirmation ledger does not preserve the frozen attempt prefix."
            )
        for key in ("maximum_attempts", "maximum_runtime_seconds"):
            if confirmation_payload.get(key) != source_payload.get(key):
                raise PostCoarseIntegrityError(
                    f"QNN confirmation ledger changed resource policy: {key}"
                )

    runner._configure_qnn_ledger(ledger_path=confirmation_path)
    return confirmation_path


def _final_primary_representatives(
    *,
    merged_primary_results: Sequence[CandidateExecutionResult],
    primary_confirmed: Sequence[CandidateExecutionResult],
    qnn_confirmed: Sequence[CandidateExecutionResult],
    contract: Mapping[str, Any],
) -> list[CandidateExecutionResult]:
    deterministic = set(contract["confirmation"]["deterministic_exceptions"])
    eligible: list[CandidateExecutionResult] = [
        result
        for result in merged_primary_results
        if result.row["family"] in deterministic and result.row["status"] == "COMPLETE"
    ]
    eligible.extend(
        result for result in primary_confirmed if result.row["status"] == "COMPLETE"
    )
    eligible.extend(result for result in qnn_confirmed if result.row["status"] == "COMPLETE")

    representatives: list[CandidateExecutionResult] = []
    for family in contract["canonical_ordering"]["family_order"]:
        family_results = [
            result for result in eligible if str(result.row["family"]) == str(family)
        ]
        if not family_results:
            continue
        leader_row = rank_candidates(
            [result.row for result in family_results], contract
        )[0]
        leader_identity = (
            leader_row["family"],
            leader_row["feature_block"],
            leader_row["configuration_id"],
            leader_row["training_seed"],
        )
        representatives.append(
            next(
                result
                for result in family_results
                if (
                    result.row["family"],
                    result.row["feature_block"],
                    result.row["configuration_id"],
                    result.row["training_seed"],
                )
                == leader_identity
            )
        )
    ordered_rows = rank_candidates([item.row for item in representatives], contract)
    lookup = {
        (
            item.row["family"],
            item.row["feature_block"],
            item.row["configuration_id"],
            item.row["training_seed"],
        ): item
        for item in representatives
    }
    return [
        lookup[
            (
                row["family"],
                row["feature_block"],
                row["configuration_id"],
                row["training_seed"],
            )
        ]
        for row in ordered_rows
    ]


def run_confirmation_phase(
    *,
    config: Mapping[str, Any],
    coarse_dir: Path,
    output_dir: Path,
    authority: AuthorityContext,
    classical_python: Path,
    qnn_python: Path,
    stop_before_qnn_confirmation: bool = False,
) -> dict[str, Any]:
    manifest_path = output_dir / "confirmation_phase_manifest.json"
    existing = _phase_manifest_existing(
        manifest_path,
        statuses={"COMPLETE"},
        authority=authority,
        root=ROOT,
    )
    if existing is not None:
        return existing

    refinement_manifest = require_refinement_manifest_for_current_config(
        output_dir / "refinement_phase_manifest.json",
        config=config,
        authority=authority,
        root=ROOT,
    )
    qnn_manifest = require_qnn_manifest_for_current_config(
        output_dir / "qnn_phase_manifest.json",
        config=config,
        authority=authority,
        root=ROOT,
    )
    started = time.monotonic()
    _, coarse_results = load_coarse_results(coarse_dir, config=config)
    primary_refinement = load_phase_results(
        refinement_manifest, "primary_result_references", root=ROOT
    )
    supplemental_mlp = load_phase_results(
        refinement_manifest, "supplemental_mlp_result_references", root=ROOT
    )
    q2_results = load_phase_results(qnn_manifest, "q2_result_references", root=ROOT)

    runner, folds = build_runner_and_folds(
        config=config,
        authority=authority,
        output_dir=output_dir,
        classical_python=classical_python,
        qnn_python=qnn_python,
        configure_qnn_ledger=False,
    )
    activations = derive_primary_activations(
        coarse_results, runner, config=config
    )
    merged_primary_rows = merge_coarse_refinement_results(
        [result.row for result in coarse_results],
        [result.row for result in primary_refinement],
        activations,
        runner.contract,
    )
    primary_lookup = _result_lookup([*coarse_results, *primary_refinement])
    merged_primary_results = [
        primary_lookup[
            (
                str(row["family"]),
                str(row["feature_block"]),
                str(row["configuration_id"]),
                int(row["training_seed"]),
            )
        ]
        for row in merged_primary_rows
    ]
    primary_selection = select_confirmation_candidates(
        merged_primary_rows, runner.contract
    )

    confirmation_seeds = [
        int(seed) for seed in runner.contract["confirmation"]["confirmation_seeds"]
    ]

    # Freeze every confirmation identity before any additional-seed fit starts.
    # Supplemental MLP is selected from coarse + amendment-authorized MLP
    # refinement, but remains excluded from the primary ranking.
    mlp_pool = [
        result
        for result in [*coarse_results, *supplemental_mlp]
        if result.row["family"] == "pytorch_mlp"
        and result.row["status"] == "COMPLETE"
        and isinstance(result.row["training_seed"], int)
    ]
    if not mlp_pool:
        raise PostCoarseIntegrityError("No complete MLP candidate is available for comparison.")
    mlp_leader_row = rank_candidates(
        [result.row for result in mlp_pool], runner.contract
    )[0]
    mlp_leader = next(
        result
        for result in mlp_pool
        if (
            result.row["family"],
            result.row["feature_block"],
            result.row["configuration_id"],
            result.row["training_seed"],
        )
        == (
            mlp_leader_row["family"],
            mlp_leader_row["feature_block"],
            mlp_leader_row["configuration_id"],
            mlp_leader_row["training_seed"],
        )
    )
    qnn_selection: list[dict[str, Any]] = []
    if qnn_manifest["status"] == "COMPLETE":
        qnn_selection = select_qnn_confirmation_candidates(
            [result.row for result in q2_results], runner.contract
        )

    selection_artifact = {
        "schema_version": 1,
        "status": "FROZEN_BEFORE_CONFIRMATION_FITS",
        "authority": authority.as_dict(ROOT),
        "primary_contract_selection": primary_selection,
        "supplemental_mlp_selection": {
            "family": mlp_leader.row["family"],
            "feature_block": mlp_leader.row["feature_block"],
            "configuration_id": mlp_leader.row["configuration_id"],
            "source_stage": mlp_leader.row["stage"],
            "confirmation_seeds": confirmation_seeds,
            "primary_ranking_eligible": False,
        },
        "qnn_selection": qnn_selection,
        "protected_feature_years_opened": False,
    }
    selection_path = output_dir / "post_coarse_confirmation_selection.json"
    classical_manifest_path = output_dir / "confirmation_classical_phase_manifest.json"
    historical_classical_reuse = historical_classical_confirmation_reuse_enabled(
        config
    )
    if historical_classical_reuse:
        reuse = config["post_coarse_execution"][
            "historical_classical_confirmation_reuse"
        ]
        configured_manifest_path = _resolve_from_root(
            ROOT, str(reuse["source_manifest"]["path"])
        )
        configured_selection_path = _resolve_from_root(
            ROOT, str(reuse["selection_artifact"]["path"])
        )
        if classical_manifest_path.resolve() != configured_manifest_path.resolve():
            raise PostCoarseIntegrityError(
                "Historical classical manifest path differs from configured output."
            )
        if selection_path.resolve() != configured_selection_path.resolve():
            raise PostCoarseIntegrityError(
                "Historical selection path differs from configured output."
            )
        classical_existing = require_historical_classical_confirmation_reuse(
            config=config,
            root=ROOT,
        )
    else:
        classical_existing = _phase_manifest_existing(
            classical_manifest_path,
            statuses={"COMPLETE"},
            authority=authority,
            root=ROOT,
        )
    if classical_existing is None:
        selection_sha = atomic_write_json(selection_path, selection_artifact)
    else:
        selection_sha = str(classical_existing["confirmation_selection_sha256"])
        if not selection_path.is_file() or file_sha256(selection_path) != selection_sha:
            raise PostCoarseIntegrityError(
                "Frozen confirmation selection artifact hash mismatch."
            )
        frozen_selection = load_json(selection_path)
        comparable_frozen = dict(frozen_selection)
        comparable_current = dict(selection_artifact)
        if historical_classical_reuse:
            # Authority changes with the schedule amendment; selection identity does not.
            comparable_frozen.pop("authority", None)
            comparable_current.pop("authority", None)
        if canonical_sha256(comparable_frozen) != canonical_sha256(comparable_current):
            raise PostCoarseIntegrityError(
                "Recomputed confirmation selection differs from the frozen artifact."
            )

    if classical_existing is None:
        primary_confirmed: list[CandidateExecutionResult] = []
        classical_extra_seed_results: list[CandidateExecutionResult] = []
        confirmed_by_key: dict[
            tuple[str, str, str, int], CandidateExecutionResult
        ] = {}
        for selection in primary_selection:
            key = (
                str(selection["family"]),
                str(selection["feature_block"]),
                str(selection["configuration_id"]),
                int(runner.contract["confirmation"]["coarse_seed"]),
            )
            base = primary_lookup[key]
            aggregate, extras = _confirm_candidate(
                runner=runner,
                folds=folds,
                base=base,
                confirmation_seeds=confirmation_seeds,
            )
            confirmed_by_key[key] = aggregate
            primary_confirmed.append(aggregate)
            classical_extra_seed_results.extend(extras)

        mlp_key = _base_key(mlp_leader)
        if mlp_key in confirmed_by_key:
            supplemental_mlp_confirmed = confirmed_by_key[mlp_key]
            supplemental_mlp_extra_fits = 0
        else:
            supplemental_mlp_confirmed, extras = _confirm_candidate(
                runner=runner,
                folds=folds,
                base=mlp_leader,
                confirmation_seeds=confirmation_seeds,
            )
            classical_extra_seed_results.extend(extras)
            supplemental_mlp_extra_fits = len(extras) * len(folds)

        classical_manifest = {
            "schema_version": 1,
            "id": "post_coarse_confirmation_classical_phase_v1_0_3",
            "status": "COMPLETE",
            "authority": authority.as_dict(ROOT),
            "confirmation_selection_sha256": selection_sha,
            "source_qnn_phase_manifest_sha256": file_sha256(
                output_dir / "qnn_phase_manifest.json"
            ),
            "primary_confirmed_result_references": [
                result_reference(
                    result,
                    output_dir=output_dir,
                    root=ROOT,
                    analysis_role="PRIMARY_CONTRACT_CONFIRMATION",
                )
                for result in primary_confirmed
            ],
            "supplemental_mlp_confirmed_result_reference": result_reference(
                supplemental_mlp_confirmed,
                output_dir=output_dir,
                root=ROOT,
                analysis_role=(
                    "SECONDARY_TITLE_ALIGNED_NEURAL_COMPARATOR_CONFIRMATION"
                ),
            ),
            "classical_extra_seed_candidate_result_references": [
                result_reference(
                    result,
                    output_dir=output_dir,
                    root=ROOT,
                    analysis_role="CONFIRMATION_SEED_COMPONENT_CLASSICAL_OR_MLP",
                )
                for result in classical_extra_seed_results
            ],
            "primary_confirmation_slots": len(primary_selection),
            "qnn_confirmation_slots_planned": len(qnn_selection),
            "supplemental_mlp_additional_fold_fits": supplemental_mlp_extra_fits,
            "qnn_confirmation_started": False,
            "runtime_seconds": float(time.monotonic() - started),
            "protected_feature_years_opened": False,
            "project_data_model_fit_performed": True,
        }
        atomic_write_json(classical_manifest_path, classical_manifest)
    else:
        classical_manifest = classical_existing
        if classical_manifest.get("qnn_confirmation_started") is not False:
            raise PostCoarseIntegrityError(
                "Classical confirmation gate has an invalid QNN-started flag."
            )
        if classical_manifest.get("source_qnn_phase_manifest_sha256") != file_sha256(
            output_dir / "qnn_phase_manifest.json"
        ):
            raise PostCoarseIntegrityError(
                "Classical confirmation source-QNN hash mismatch."
            )
        primary_confirmed = load_phase_results(
            classical_manifest, "primary_confirmed_result_references", root=ROOT
        )
        classical_extra_seed_results = load_phase_results(
            classical_manifest,
            "classical_extra_seed_candidate_result_references",
            root=ROOT,
        )
        supplemental_mlp_confirmed = load_result_reference(
            classical_manifest["supplemental_mlp_confirmed_result_reference"],
            root=ROOT,
        )
        supplemental_mlp_extra_fits = int(
            classical_manifest["supplemental_mlp_additional_fold_fits"]
        )
        if len(primary_confirmed) != len(primary_selection):
            raise PostCoarseIntegrityError(
                "Classical confirmation result count differs from frozen selection."
            )

    if stop_before_qnn_confirmation:
        return classical_manifest

    qnn_confirmed: list[CandidateExecutionResult] = []
    qnn_extra_seed_results: list[CandidateExecutionResult] = []
    qnn_confirmation_ledger_path: Path | None = None
    if qnn_selection:
        qnn_confirmation_ledger_path = _configure_confirmation_qnn_ledger(
            runner=runner,
            config=config,
            source_qnn_manifest=qnn_manifest,
            output_dir=output_dir,
        )
        q2_lookup = {
            (
                str(result.row["feature_block"]),
                str(result.row["configuration_id"]),
            ): result
            for result in q2_results
        }
        jobs = [
            (
                q2_lookup[
                    (
                        str(selection["feature_block"]),
                        str(selection["configuration_id"]),
                    )
                ],
                selection,
            )
            for selection in qnn_selection
        ]
        schedule = config["post_coarse_execution"].get(
            "confirmation_schedule_amendment", {}
        )
        maximum_workers = int(
            schedule.get(
                "maximum_parallel_qnn_confirmation_folds",
                schedule.get("maximum_parallel_qnn_confirmation_candidates", 1),
            )
        )
        confirmed_jobs = _confirm_qnn_candidates_parallel(
            runner=runner,
            folds=folds,
            jobs=jobs,
            confirmation_seeds=confirmation_seeds,
            maximum_workers=maximum_workers,
        )
        for aggregate, extras in confirmed_jobs:
            qnn_confirmed.append(aggregate)
            qnn_extra_seed_results.extend(extras)

    extra_seed_results = [
        *classical_extra_seed_results,
        *qnn_extra_seed_results,
    ]

    representatives = _final_primary_representatives(
        merged_primary_results=merged_primary_results,
        primary_confirmed=primary_confirmed,
        qnn_confirmed=qnn_confirmed,
        contract=runner.contract,
    )
    for representative in representatives:
        if representative.row.get("stage") == "coarse":
            materialize_coarse_result(representative)
    primary_calibration = [
        runner._fit_calibration_and_threshold(result) for result in representatives
    ]
    representative_rows = [
        {
            "rank": index,
            **result.row,
            "metric_summary": _metric_summary(result),
        }
        for index, result in enumerate(representatives, 1)
    ]
    primary_ranking_manifest = {
        "schema_version": 1,
        "id": "post_coarse_primary_development_ranking_v1_0_0",
        "status": "COMPLETE",
        "authority": authority.as_dict(ROOT),
        "primary_methodology_unchanged": True,
        "family_representatives": representative_rows,
        "global_winner": representative_rows[0] if representative_rows else None,
        "calibration_and_threshold": primary_calibration,
        "supplemental_mlp_excluded_from_primary_ranking": True,
        "protected_feature_years_opened": False,
    }
    primary_ranking_sha = atomic_write_json(
        output_dir / "final_primary_development_ranking.json",
        primary_ranking_manifest,
    )

    neural_rows: list[dict[str, Any]] = []
    mlp_metrics = _metric_summary(supplemental_mlp_confirmed)
    neural_rows.append(
        {
            "comparison_role": "REFINED_CLASSICAL_MLP_SECONDARY_COMPARATOR",
            **{
                key: supplemental_mlp_confirmed.row[key]
                for key in (
                    "family",
                    "stage",
                    "configuration_id",
                    "feature_block",
                    "training_seed",
                    "parameters",
                    "status",
                )
            },
            **mlp_metrics,
            "delta_pr_auc_vs_refined_mlp": 0.0
            if mlp_metrics["pooled_oof_pr_auc"] is not None
            else None,
            "delta_roc_auc_vs_refined_mlp": 0.0
            if mlp_metrics["pooled_oof_roc_auc"] is not None
            else None,
        }
    )
    for result in qnn_confirmed:
        metrics = _metric_summary(result)
        neural_rows.append(
            {
                "comparison_role": "QNN_CONFIRMED_BLOCK_REPRESENTATIVE",
                **{
                    key: result.row[key]
                    for key in (
                        "family",
                        "stage",
                        "configuration_id",
                        "feature_block",
                        "training_seed",
                        "parameters",
                        "status",
                    )
                },
                "selected_ansatz_id": result.row.get("selected_ansatz_id"),
                **metrics,
                "delta_pr_auc_vs_refined_mlp": (
                    float(metrics["pooled_oof_pr_auc"])
                    - float(mlp_metrics["pooled_oof_pr_auc"])
                    if metrics["pooled_oof_pr_auc"] is not None
                    and mlp_metrics["pooled_oof_pr_auc"] is not None
                    else None
                ),
                "delta_roc_auc_vs_refined_mlp": (
                    float(metrics["pooled_oof_roc_auc"])
                    - float(mlp_metrics["pooled_oof_roc_auc"])
                    if metrics["pooled_oof_roc_auc"] is not None
                    and mlp_metrics["pooled_oof_roc_auc"] is not None
                    else None
                ),
            }
        )
    neural_calibration: list[dict[str, Any]] = []
    if supplemental_mlp_confirmed.row["status"] == "COMPLETE":
        neural_calibration.append(
            runner._fit_calibration_and_threshold(supplemental_mlp_confirmed)
        )
    else:
        neural_calibration.append(
            {
                "family": "pytorch_mlp",
                "configuration_id": supplemental_mlp_confirmed.row.get(
                    "configuration_id"
                ),
                "feature_block": supplemental_mlp_confirmed.row.get(
                    "feature_block"
                ),
                "status": "NOT_CREATED_COMPARATOR_TECHNICALLY_INVALID",
            }
        )
    # Calibrate each confirmed QNN block for complete, auditable comparison.
    neural_calibration.extend(
        runner._fit_calibration_and_threshold(result)
        for result in qnn_confirmed
        if result.row["status"] == "COMPLETE"
    )
    neural_manifest = {
        "schema_version": 1,
        "id": "refined_mlp_vs_qnn_development_comparison_v1_0_0",
        "status": "COMPLETE"
        if supplemental_mlp_confirmed.row["status"] == "COMPLETE"
        else "MLP_COMPARATOR_TECHNICALLY_INVALID",
        "authority": authority.as_dict(ROOT),
        "analysis_role": "secondary_title_aligned_comparison",
        "claim_limit": (
            "The supplemental MLP refinement was declared after coarse-search results "
            "were known; it is excluded from the frozen primary ranking and is used only "
            "for the classical-NN versus QNN comparison."
        ),
        "rows": neural_rows,
        "calibration_and_threshold": neural_calibration,
        "protected_feature_years_opened": False,
    }
    neural_sha = atomic_write_json(
        output_dir / "neural_comparison_manifest.json", neural_manifest
    )

    manifest = {
        "schema_version": 1,
        "id": "post_coarse_confirmation_phase_v1_0_0",
        "status": "COMPLETE",
        "authority": authority.as_dict(ROOT),
        "confirmation_selection_sha256": selection_sha,
        "confirmation_classical_phase_manifest_sha256": file_sha256(
            classical_manifest_path
        ),
        "primary_confirmed_result_references": [
            result_reference(
                result,
                output_dir=output_dir,
                root=ROOT,
                analysis_role="PRIMARY_CONTRACT_CONFIRMATION",
            )
            for result in primary_confirmed
        ],
        "supplemental_mlp_confirmed_result_reference": result_reference(
            supplemental_mlp_confirmed,
            output_dir=output_dir,
            root=ROOT,
            analysis_role="SECONDARY_TITLE_ALIGNED_NEURAL_COMPARATOR_CONFIRMATION",
        ),
        "qnn_confirmed_result_references": [
            result_reference(
                result,
                output_dir=output_dir,
                root=ROOT,
                analysis_role="QNN_BLOCK_CONFIRMATION",
            )
            for result in qnn_confirmed
        ],
        "extra_seed_candidate_result_references": [
            result_reference(
                result,
                output_dir=output_dir,
                root=ROOT,
                analysis_role="CONFIRMATION_SEED_COMPONENT",
            )
            for result in extra_seed_results
        ],
        "primary_confirmation_slots": len(primary_selection),
        "qnn_confirmation_slots": len(qnn_selection),
        "qnn_confirmation_resource_ledger": (
            {
                "path": _relative_or_absolute(qnn_confirmation_ledger_path, ROOT),
                "sha256": file_sha256(qnn_confirmation_ledger_path),
            }
            if qnn_confirmation_ledger_path is not None
            else None
        ),
        "supplemental_mlp_additional_fold_fits": supplemental_mlp_extra_fits,
        "final_primary_development_ranking_sha256": primary_ranking_sha,
        "neural_comparison_manifest_sha256": neural_sha,
        "runtime_seconds": float(time.monotonic() - started)
        + (
            float(classical_manifest["runtime_seconds"])
            if classical_existing is not None
            else 0.0
        ),
        "protected_feature_years_opened": False,
        "project_data_model_fit_performed": True,
    }
    atomic_write_json(manifest_path, manifest)
    atomic_write_json(
        output_dir / "run_manifest.json",
        {
            "schema_version": 1,
            "status": "COMPLETE",
            "mode": "post_coarse_refinement_qnn_confirmation",
            "authority": authority.as_dict(ROOT),
            "refinement_phase_manifest_sha256": file_sha256(
                output_dir / "refinement_phase_manifest.json"
            ),
            "qnn_phase_manifest_sha256": file_sha256(
                output_dir / "qnn_phase_manifest.json"
            ),
            "confirmation_classical_phase_manifest_sha256": file_sha256(
                classical_manifest_path
            ),
            "qnn_confirmation_resource_ledger_sha256": (
                file_sha256(qnn_confirmation_ledger_path)
                if qnn_confirmation_ledger_path is not None
                else None
            ),
            "confirmation_phase_manifest_sha256": file_sha256(manifest_path),
            "final_primary_development_ranking_sha256": primary_ranking_sha,
            "neural_comparison_manifest_sha256": neural_sha,
            "protected_feature_years_opened": False,
            "project_data_model_fit_performed": True,
        },
    )
    return manifest


def run_confirmation_classical_phase(
    **kwargs: Any,
) -> dict[str, Any]:
    return run_confirmation_phase(
        **kwargs,
        stop_before_qnn_confirmation=True,
    )


def run_confirmation_qnn_phase(
    **kwargs: Any,
) -> dict[str, Any]:
    config = kwargs["config"]
    authority = kwargs["authority"]
    output_dir = kwargs["output_dir"]
    if historical_classical_confirmation_reuse_enabled(config):
        reuse = config["post_coarse_execution"][
            "historical_classical_confirmation_reuse"
        ]
        configured_path = _resolve_from_root(
            ROOT, str(reuse["source_manifest"]["path"])
        )
        actual_path = output_dir / "confirmation_classical_phase_manifest.json"
        if actual_path.resolve() != configured_path.resolve():
            raise PostCoarseIntegrityError(
                "Historical classical manifest path differs from configured output."
            )
        require_historical_classical_confirmation_reuse(
            config=config,
            root=ROOT,
        )
    else:
        require_phase_manifest(
            output_dir / "confirmation_classical_phase_manifest.json",
            allowed_statuses={"COMPLETE"},
            authority=authority,
            root=ROOT,
        )
    return run_confirmation_phase(
        **kwargs,
        stop_before_qnn_confirmation=False,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _execution_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    if args.classical_python is None or args.qnn_python is None:
        raise PostCoarseIntegrityError(
            "--classical-python and --qnn-python are required for model-fitting modes."
        )
    # Preserve virtual-environment interpreter symlinks. Resolving them can
    # bypass the venv and execute against the base pyenv installation.
    classical = args.classical_python.absolute()
    qnn = args.qnn_python.absolute()
    if not classical.is_file():
        raise PostCoarseIntegrityError(f"Classical interpreter does not exist: {classical}")
    if not qnn.is_file():
        raise PostCoarseIntegrityError(f"QNN/MLP interpreter does not exist: {qnn}")
    return classical, qnn


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run post-coarse refinement and QNN without repeating coarse search."
    )
    parser.add_argument(
        "mode",
        choices=(
            "plan",
            "refinement",
            "qnn",
            "confirmation-classical",
            "confirmation-qnn",
            "confirmation",
            "all",
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--coarse-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--classical-python", type=Path)
    parser.add_argument("--qnn-python", type=Path)
    args = parser.parse_args()

    config_path = args.config.resolve()
    config = load_post_coarse_config(config_path)
    section = config["post_coarse_execution"]
    coarse_dir = (
        args.coarse_dir.resolve()
        if args.coarse_dir is not None
        else _resolve_from_root(ROOT, section["coarse_source"]["root"])
    )
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir is not None
        else _resolve_from_root(ROOT, section["default_output_root"])
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    require_committed = args.mode in EXECUTION_MODES
    authority = build_authority_context(
        root=ROOT,
        config=config,
        coarse_dir=coarse_dir,
        require_committed=require_committed,
    )

    if args.mode == "plan":
        result = create_plan(
            config=config,
            coarse_dir=coarse_dir,
            output_dir=output_dir,
            authority=authority,
        )
    else:
        classical_python, qnn_python = _execution_paths(args)
        if args.mode == "refinement":
            result = run_refinement_phase(
                config=config,
                coarse_dir=coarse_dir,
                output_dir=output_dir,
                authority=authority,
                classical_python=classical_python,
                qnn_python=qnn_python,
            )
        elif args.mode == "qnn":
            result = run_qnn_phase(
                config=config,
                coarse_dir=coarse_dir,
                output_dir=output_dir,
                authority=authority,
                classical_python=classical_python,
                qnn_python=qnn_python,
            )
        elif args.mode == "confirmation-classical":
            result = run_confirmation_classical_phase(
                config=config,
                coarse_dir=coarse_dir,
                output_dir=output_dir,
                authority=authority,
                classical_python=classical_python,
                qnn_python=qnn_python,
            )
        elif args.mode == "confirmation-qnn":
            result = run_confirmation_qnn_phase(
                config=config,
                coarse_dir=coarse_dir,
                output_dir=output_dir,
                authority=authority,
                classical_python=classical_python,
                qnn_python=qnn_python,
            )
        elif args.mode == "confirmation":
            result = run_confirmation_phase(
                config=config,
                coarse_dir=coarse_dir,
                output_dir=output_dir,
                authority=authority,
                classical_python=classical_python,
                qnn_python=qnn_python,
            )
        else:
            run_refinement_phase(
                config=config,
                coarse_dir=coarse_dir,
                output_dir=output_dir,
                authority=authority,
                classical_python=classical_python,
                qnn_python=qnn_python,
            )
            run_qnn_phase(
                config=config,
                coarse_dir=coarse_dir,
                output_dir=output_dir,
                authority=authority,
                classical_python=classical_python,
                qnn_python=qnn_python,
            )
            result = run_confirmation_phase(
                config=config,
                coarse_dir=coarse_dir,
                output_dir=output_dir,
                authority=authority,
                classical_python=classical_python,
                qnn_python=qnn_python,
            )

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

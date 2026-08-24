"""Verify the frozen secondary-development results through report v1.1.7.

The verifier is read-only. It reads completed development artifacts bounded to
2011--2020 and hashes opaque model files. It never opens protected-period data.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping

import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling.build_secondary_development_results_freeze_inventory_v1_1_7 import (
    EXECUTION_ROOT,
    REPORT_ROOT,
    collect_inventory,
)
from src.modeling.secondary_analysis_execution_v1_1_7 import (
    DEFAULT_CONFIG as V117_CONFIG,
    load_execution_config as load_v117_config,
)
from src.modeling.secondary_analysis_schemas import ROOT, canonical_sha256, file_sha256
from src.modeling.verify_secondary_analysis_execution_v1_1_7 import (
    verify_secondary_analysis_execution_v1_1_7,
)


DEFAULT_MANIFEST = (
    ROOT / "configs/secondary_development_v1_1_7_results_freeze_manifest.yaml"
)
DEFAULT_INVENTORY = (
    ROOT / "reports/secondary_development_v1_1_7/artifact_inventory.json"
)
class SecondaryDevelopmentResultsFreezeError(RuntimeError):
    """Raised when a frozen secondary result or invariant does not match."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SecondaryDevelopmentResultsFreezeError(message)


def _load_json(path: Path) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), f"Missing JSON artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"Expected a JSON object: {path}")
    return payload


def _verify_file_entry(entry: Mapping[str, Any]) -> Path:
    path = (ROOT / str(entry["path"])).resolve()
    _require(path.is_relative_to(ROOT), f"Frozen path escapes repository: {path}")
    _require(path.is_file() and not path.is_symlink(), f"Missing frozen artifact: {path}")
    _require(path.stat().st_size == int(entry["bytes"]), f"Size mismatch: {path}")
    _require(file_sha256(path) == str(entry["sha256"]), f"SHA-256 mismatch: {path}")
    expected_status = entry.get("json_status")
    if expected_status is not None:
        _require(_load_json(path).get("status") == expected_status, f"JSON status mismatch: {path}")
    return path


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise SecondaryDevelopmentResultsFreezeError(
            completed.stderr.strip() or "Secondary result-freeze Git gate failed."
        )
    return completed.stdout.strip()


def _verify_committed_package(
    manifest_path: Path, verification_entries: list[Mapping[str, Any]]
) -> str:
    paths = [str(item["path"]) for item in verification_entries]
    paths.append(str(DEFAULT_INVENTORY.relative_to(ROOT)))
    paths.append(str(manifest_path.relative_to(ROOT)))
    for relative in paths:
        _git("ls-files", "--error-unmatch", "--", relative)
    dirty = _git("status", "--porcelain", "--", *paths)
    _require(not dirty, "Result-freeze package is uncommitted or modified:\n" + dirty)
    rows = _git("ls-files", "-s", "--", *paths).splitlines()
    _require(len(rows) == len(paths), "Result-freeze Git cardinality mismatch.")
    return canonical_sha256(sorted(rows))


def _verify_prediction_artifact(result: Mapping[str, Any]) -> bool:
    relative = result.get("prediction_artifact")
    if relative is None:
        return False
    path = EXECUTION_ROOT / str(relative)
    _require(path.is_file() and not path.is_symlink(), f"Missing prediction artifact: {path}")
    _require(
        file_sha256(path) == result.get("prediction_artifact_sha256"),
        f"Prediction artifact hash mismatch: {path}",
    )
    payload = _load_json(path)
    rows = payload.get("rows") or []
    expected_rows = int(result.get("validation_rows", -1))
    fold_id = str((result.get("task_identity") or {}).get("fold_id"))
    _require(len(rows) == expected_rows, f"Prediction row count mismatch: {path}")
    seen: set[str] = set()
    for row in rows:
        company_year_id = str(row.get("research_universe_company_year_id"))
        _require(company_year_id not in seen, f"Duplicate prediction identity: {path}")
        seen.add(company_year_id)
        _require(row.get("fold_id") == fold_id, f"Prediction fold mismatch: {path}")
        year = int(row.get("validation_feature_year", -1))
        _require(2015 <= year <= 2020, f"Prediction opened a protected year: {path}")
        _require(isinstance(row.get("raw_score"), (int, float)), f"Invalid raw score: {path}")
        _require(isinstance(row.get("raw_score_float64_hex"), str), f"Missing exact score: {path}")
    return True


def verify_secondary_development_results_freeze_v1_1_7(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    require_committed: bool = False,
) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), "Freeze manifest must be a mapping.")
    freeze = payload.get("secondary_development_results_freeze") or {}
    _require(
        freeze.get("id") == "secondary_development_results_v1_1_7"
        and str(freeze.get("version")) == "1.1.7"
        and freeze.get("formal_freeze_effected_by_this_manifest") is True,
        "Unexpected secondary result-freeze identity.",
    )
    _require(freeze.get("status") == "FROZEN", "Secondary result freeze is not FROZEN.")
    _require(
        freeze.get("verdict")
        == "SECONDARY_DEVELOPMENT_V1_1_7_RESULTS_INTEGRITY_PASS",
        "Unexpected secondary result-freeze verdict.",
    )
    _require(
        freeze.get("protected_feature_years_opened") is False,
        "Freeze declares protected-period access.",
    )
    _require(
        freeze.get("project_data_model_fit_performed") is True
        and freeze.get("project_model_fit_performed_by_freeze") is False,
        "Unexpected result-freeze model-fit declaration.",
    )

    compact_entries = payload.get("compact_result_artifacts") or []
    verification_entries = payload.get("verification_sources") or []
    _require(compact_entries and verification_entries, "Freeze artifact sections may not be empty.")
    entry_paths = [str(entry["path"]) for entry in [*compact_entries, *verification_entries]]
    _require(len(entry_paths) == len(set(entry_paths)), "Duplicate frozen file entry.")
    for entry in [*compact_entries, *verification_entries]:
        _verify_file_entry(entry)
    git_index_sha256 = "NOT_REQUIRED_FOR_READ_ONLY_VERIFY"
    if require_committed:
        git_index_sha256 = _verify_committed_package(
            manifest_path, list(verification_entries)
        )

    package = verify_secondary_analysis_execution_v1_1_7(require_committed=True)
    _require(package["status"] == "PASS", "v1.1.7 reporting package is not valid.")
    _require(
        package["package_git_index_sha256"]
        == freeze["reporting_package_git_index_sha256"],
        "v1.1.7 reporting-package Git identity changed.",
    )
    config = load_v117_config(V117_CONFIG)
    schedule, tasks = base.frozen_schedule(config)
    expected_task_ids = {str(task["task_identity_sha256"]) for task in tasks}

    frozen_inventory = _load_json(DEFAULT_INVENTORY)
    actual_inventory = collect_inventory()
    _require(frozen_inventory == actual_inventory, "Full secondary artifact inventory changed.")
    for field in (
        "project_data_deserialized",
        "project_model_fit_performed",
        "protected_feature_years_opened",
    ):
        _require(frozen_inventory.get(field) is False, f"Unsafe inventory flag: {field}")
    expected_inventory = payload["frozen_inventory"]
    for field in ("file_count", "logical_bytes", "files_sha256"):
        _require(
            frozen_inventory.get(field) == expected_inventory.get(field),
            f"Frozen inventory field mismatch: {field}",
        )
    expected_roots = expected_inventory.get("roots") or []
    _require(frozen_inventory.get("roots") == expected_roots, "Frozen root inventory changed.")

    result_paths = sorted((EXECUTION_ROOT / "task_results").glob("*.json"))
    _require(len(result_paths) == len(tasks) == 96, "Task-result cardinality changed.")
    _require({path.stem for path in result_paths} == expected_task_ids, "Task-result roster changed.")
    prediction_artifacts = 0
    statuses: list[str] = []
    stages: dict[str, int] = {}
    for path in result_paths:
        result = _load_json(path)
        _require(result.get("task_identity_sha256") == path.stem, f"Task identity mismatch: {path}")
        _require(result.get("status") == "COMPLETE", f"Task is not COMPLETE: {path}")
        _require(result.get("failure_code") is None, f"Task has a failure code: {path}")
        _require(result.get("protected_feature_years_opened") is False, f"Task opened a protected year: {path}")
        statuses.append(str(result["status"]))
        stage = str((result.get("task_identity") or {}).get("stage"))
        stages[stage] = stages.get(stage, 0) + 1
        prediction_artifacts += int(_verify_prediction_artifact(result))

    expected_counts = payload["frozen_counts"]
    _require(
        int(expected_counts["planned_tasks"])
        == int(expected_counts["complete_tasks"])
        == len(tasks),
        "Frozen planned-task count changed.",
    )
    _require(int(expected_counts["failed_tasks"]) == 0, "Frozen failed-task count changed.")
    _require(statuses.count("COMPLETE") == int(expected_counts["complete_tasks"]), "Complete-task count changed.")
    _require(stages == dict(expected_counts["tasks_by_stage"]), "Task stage counts changed.")
    _require(prediction_artifacts == int(expected_counts["prediction_artifacts"]), "Prediction count changed.")
    checkpoint_files = list((EXECUTION_ROOT / "task_artifacts").glob("*/checkpoint.pt"))
    _require(len(checkpoint_files) == int(expected_counts["checkpoint_files"]), "Checkpoint count changed.")

    phase_specs = {
        "pca_matched_controls": 12,
        "interpretability": 12,
        "robustness_classical": 48,
        "robustness_qnn": 24,
    }
    _require(
        dict(expected_counts["tasks_by_phase"]) == phase_specs,
        "Frozen phase-task counts changed.",
    )
    for phase, count in phase_specs.items():
        phase_payload = _load_json(EXECUTION_ROOT / "phase_manifests" / f"{phase}.json")
        _require(
            phase_payload.get("status") == "COMPLETE"
            and phase_payload.get("planned_tasks") == count
            and phase_payload.get("complete_tasks") == count
            and phase_payload.get("failed_tasks") == 0,
            f"Phase accounting changed: {phase}",
        )
        _require(
            phase_payload.get("protected_feature_years_opened") is False,
            f"Phase opened a protected year: {phase}",
        )

    ledger = _load_json(EXECUTION_ROOT / "qnn_structural_resource_ledger.json")
    attempts = ledger.get("attempts") or []
    _require(len(attempts) == int(expected_counts["qnn_attempts"]), "QNN attempt count changed.")
    _require(
        all(
            attempt.get("status") == "COMPLETED"
            and attempt.get("outcome") == "COMPLETE"
            and attempt.get("retry_reason") == "INITIAL"
            for attempt in attempts
        ),
        "QNN ledger contains a failed or retried attempt.",
    )
    _require(ledger.get("limit_reached") is False, "QNN resource limit was reached.")
    _require(
        int(expected_counts["qnn_retries"]) == 0,
        "Frozen QNN retry count changed.",
    )
    _require(
        ledger.get("interrupted_attempts")
        == int(expected_counts["qnn_interrupted_attempts"])
        == 0,
        "QNN attempt was interrupted.",
    )

    repair = _load_json(EXECUTION_ROOT / "treeshap_repair_manifest.json")
    _require(
        repair.get("status") == "COMPLETE"
        and repair.get("recomputed_tree_shap_folds")
        == int(expected_counts["treeshap_recomputed_folds"])
        and repair.get("interpretability_failed_tasks") == 0,
        "TreeSHAP repair accounting changed.",
    )
    carry = _load_json(EXECUTION_ROOT / "carry_forward_manifest.json")
    _require(
        carry.get("status") == "COMPLETE"
        and carry.get("carried_pca_tasks")
        == int(expected_counts["carried_pca_tasks"])
        and carry.get("carried_interpretation_tasks")
        == int(expected_counts["carried_interpretability_tasks"]),
        "Carry-forward accounting changed.",
    )

    report = _load_json(REPORT_ROOT / "secondary_development_report.json")
    run = _load_json(REPORT_ROOT / "run_manifest.json")
    _require(report.get("status") == run.get("status") == "COMPLETE", "Final report is incomplete.")
    _require(report.get("terminal_tasks") == report.get("planned_tasks") == 96, "Final report task count changed.")
    _require(report.get("missing_task_ids") == [], "Final report has missing tasks.")
    _require(report.get("source_results_changed") is False, "Final report changed source results.")
    _require(run.get("source_output_mutated") is False, "Final report mutated source output.")
    _require(run.get("source_results_copied") is False, "Final report copied source results.")
    _require(
        run.get("secondary_report_sha256")
        == file_sha256(REPORT_ROOT / "secondary_development_report.json"),
        "Final report SHA-256 mismatch.",
    )
    for item in (report, run):
        _require(item.get("project_model_fit_performed") is False, "Final reporting performed a fit.")
        _require(item.get("protected_feature_years_opened") is False, "Final reporting opened a protected year.")

    access = payload.get("access_boundary") or {}
    _require(
        access.get("this_freeze_authorizes_2021_2024_access") is False,
        "Result freeze must not authorize protected-period access.",
    )
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": freeze["verdict"],
        "verified_compact_files": len(compact_entries),
        "verified_inventory_files": int(frozen_inventory["file_count"]),
        "inventory_logical_bytes": int(frozen_inventory["logical_bytes"]),
        "task_results": len(result_paths),
        "complete_tasks": statuses.count("COMPLETE"),
        "prediction_artifacts": prediction_artifacts,
        "checkpoint_files": len(checkpoint_files),
        "qnn_attempts": len(attempts),
        "git_index_sha256": git_index_sha256,
        "project_model_fit_performed_by_verifier": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--require-committed", action="store_true")
    args = parser.parse_args()
    result = verify_secondary_development_results_freeze_v1_1_7(
        args.manifest, require_committed=args.require_committed
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

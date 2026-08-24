"""Read-only verifier for the v1.1.7 report-integrity amendment."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling.secondary_analysis_execution_v1_1_6 import (
    DEFAULT_CONFIG as V116_CONFIG,
    load_execution_config as load_v116_config,
)
from src.modeling.secondary_analysis_execution_v1_1_7 import (
    DEFAULT_CONFIG,
    ROOT,
    load_execution_config,
    verify_amendment_authority,
)
from src.modeling.verify_secondary_analysis_execution_v1_1_6 import (
    verify_secondary_analysis_execution_v1_1_6,
)


DEFAULT_MANIFEST = (
    ROOT / "configs/secondary_development_execution_v1_1_7_freeze_manifest.yaml"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "v1.1.7 Git gate failed.")
    return completed.stdout.strip()


def verify_secondary_analysis_execution_v1_1_7(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    require_committed: bool = False,
) -> dict[str, Any]:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    freeze = payload.get("secondary_development_report_freeze") or {}
    _require(freeze.get("id") == "secondary_development_execution_v1_1_7", "Wrong v1.1.7 freeze ID.")
    _require(freeze.get("status") == "FROZEN", "v1.1.7 is not frozen.")
    config = load_execution_config(DEFAULT_CONFIG)
    section = config["secondary_development_execution"]
    _require(
        section["status"] == "executable_report_integrity_amendment_frozen",
        "v1.1.7 config is not frozen.",
    )

    verified: dict[str, str] = {}
    package_files: list[str] = []
    for item in freeze.get("files") or []:
        relative = str(item["path"])
        path = (ROOT / relative).resolve()
        _require(path.is_relative_to(ROOT), "v1.1.7 path escapes repository.")
        _require(path.is_file(), f"Missing v1.1.7 file: {relative}")
        actual = base.file_sha256(path)
        _require(actual == str(item["sha256"]), f"v1.1.7 hash mismatch: {relative}")
        _require(path.stat().st_size == int(item["bytes"]), f"v1.1.7 size mismatch: {relative}")
        if item.get("executable"):
            _require(bool(path.stat().st_mode & 0o111), f"v1.1.7 script is not executable: {relative}")
        verified[relative] = actual
        package_files.append(relative)
    manifest_relative = str(manifest_path.relative_to(ROOT))
    expected_inventory = set(package_files) | {manifest_relative}
    _require(
        set(section["git_gate"]["package_files"]) == expected_inventory,
        "v1.1.7 Git inventory mismatch.",
    )
    package_files.append(manifest_relative)
    git_index_sha256 = "NOT_REQUIRED_FOR_READ_ONLY_VERIFY"
    if require_committed:
        for relative in package_files:
            _git("ls-files", "--error-unmatch", "--", relative)
        dirty = _git("status", "--porcelain", "--", *package_files)
        _require(not dirty, "v1.1.7 package is uncommitted or modified:\n" + dirty)
        rows = _git("ls-files", "-s", "--", *package_files).splitlines()
        _require(len(rows) == len(package_files), "v1.1.7 Git cardinality mismatch.")
        git_index_sha256 = base.canonical_sha256(sorted(rows))

    base_report = verify_secondary_analysis_execution_v1_1_6()
    _require(base_report["status"] == "PASS", "v1.1.6 base verification failed.")
    authority = verify_amendment_authority(config)
    schedule, tasks = base.frozen_schedule(config)
    inherited_schedule, inherited_tasks = base.frozen_schedule(
        load_v116_config(V116_CONFIG)
    )
    _require(len(tasks) == 96, "v1.1.7 changed the roster cardinality.")
    _require(schedule["counts"] == inherited_schedule["counts"], "v1.1.7 changed task counts.")
    _require(
        [task["task_identity_sha256"] for task in tasks]
        == [task["task_identity_sha256"] for task in inherited_tasks],
        "v1.1.7 changed task identities or order.",
    )
    amendment = section["report_integrity_amendment"]
    for field in (
        "source_output_mutated",
        "source_results_copied",
        "source_results_changed",
        "target_values_changed",
        "sample_membership_changed",
        "fold_policy_changed",
        "task_roster_changed",
        "task_identity_changed",
        "model_parameters_changed",
        "interpretation_method_changed",
        "robustness_method_changed",
        "methodology_changed",
        "project_data_read",
        "project_model_fit_performed",
        "protected_feature_years_opened",
    ):
        _require(amendment[field] is False, f"v1.1.7 changed {field}.")
    source = section["report_source"]
    _require(source["expected_tasks"] == source["expected_complete_tasks"] == 96, "Wrong source task count.")
    _require(source["report_actual_sha256"] != source["report_recorded_stale_sha256"], "Source defect is not pinned.")
    _require(len(source["phase_manifest_sha256"]) == 4, "Wrong source phase count.")

    controller_source = (
        ROOT / "src/modeling/secondary_analysis_execution_v1_1_7.py"
    ).read_text(encoding="utf-8")
    report_write = controller_source.index(
        "report_sha256 = base.atomic_write_json(report_path, dict(report))"
    )
    manifest_reference = controller_source.index(
        'final_manifest["secondary_report_sha256"] = report_sha256'
    )
    manifest_write = controller_source.index(
        'base.atomic_write_json(output_dir / "run_manifest.json", final_manifest)'
    )
    _require(report_write < manifest_reference < manifest_write, "Report hash write order is unsafe.")
    for forbidden in (
        "execute_pca_controls(",
        "execute_interpretability(",
        "execute_classical_robustness(",
        "execute_qnn_robustness(",
    ):
        _require(forbidden not in controller_source, f"v1.1.7 may not execute models: {forbidden}")
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": "SECONDARY_DEVELOPMENT_EXECUTION_V1_1_7_REPORT_INTEGRITY_PASS",
        "base_amendment_verdict": base_report["verdict"],
        "verified_package_files": len(verified),
        "verified_amendment_authorities": len(authority),
        "committed_clean_gate_required": require_committed,
        "package_git_index_sha256": git_index_sha256,
        "planned_tasks": len(tasks),
        "task_counts": schedule["counts"],
        "task_identities_changed": False,
        "methodology_changed": False,
        "source_results_changed": False,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    print(
        json.dumps(
            verify_secondary_analysis_execution_v1_1_7(), indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()

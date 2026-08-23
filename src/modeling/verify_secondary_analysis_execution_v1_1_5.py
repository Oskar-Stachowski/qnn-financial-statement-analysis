"""Read-only verifier for the v1.1.5 economic-group permutation amendment."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling.secondary_analysis_execution_v1_1_4 import (
    DEFAULT_CONFIG as V114_CONFIG,
    load_execution_config as load_v114_config,
)
from src.modeling.secondary_analysis_execution_v1_1_5 import (
    DEFAULT_CONFIG,
    POLICY_ID,
    ROOT,
    load_execution_config,
    verify_amendment_authority,
)
from src.modeling.verify_secondary_analysis_execution_v1_1_4 import (
    verify_secondary_analysis_execution_v1_1_4,
)


DEFAULT_MANIFEST = (
    ROOT / "configs/secondary_development_execution_v1_1_5_freeze_manifest.yaml"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "v1.1.5 Git gate failed.")
    return completed.stdout.strip()


def verify_secondary_analysis_execution_v1_1_5(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    require_committed: bool = False,
) -> dict[str, Any]:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    freeze = payload.get("secondary_development_economic_group_permutation_freeze") or {}
    _require(freeze.get("id") == "secondary_development_execution_v1_1_5", "Wrong v1.1.5 freeze ID.")
    _require(freeze.get("status") == "FROZEN", "v1.1.5 is not frozen.")
    config = load_execution_config(DEFAULT_CONFIG)
    section = config["secondary_development_execution"]
    _require(
        section["status"]
        == "executable_economic_group_permutation_amendment_frozen",
        "v1.1.5 config is not frozen.",
    )

    verified: dict[str, str] = {}
    package_files: list[str] = []
    for item in freeze.get("files") or []:
        relative = str(item["path"])
        path = (ROOT / relative).resolve()
        _require(path.is_relative_to(ROOT), "v1.1.5 path escapes repository.")
        _require(path.is_file(), f"Missing v1.1.5 file: {relative}")
        actual = base.file_sha256(path)
        _require(actual == str(item["sha256"]), f"v1.1.5 hash mismatch: {relative}")
        _require(path.stat().st_size == int(item["bytes"]), f"v1.1.5 size mismatch: {relative}")
        if item.get("executable"):
            _require(bool(path.stat().st_mode & 0o111), f"v1.1.5 script is not executable: {relative}")
        verified[relative] = actual
        package_files.append(relative)
    manifest_relative = str(manifest_path.relative_to(ROOT))
    expected_inventory = set(package_files) | {manifest_relative}
    _require(
        set(section["git_gate"]["package_files"]) == expected_inventory,
        "v1.1.5 Git inventory mismatch.",
    )
    package_files.append(manifest_relative)
    git_index_sha256 = "NOT_REQUIRED_FOR_READ_ONLY_VERIFY"
    if require_committed:
        for relative in package_files:
            _git("ls-files", "--error-unmatch", "--", relative)
        dirty = _git("status", "--porcelain", "--", *package_files)
        _require(not dirty, "v1.1.5 package is uncommitted or modified:\n" + dirty)
        rows = _git("ls-files", "-s", "--", *package_files).splitlines()
        _require(len(rows) == len(package_files), "v1.1.5 Git cardinality mismatch.")
        git_index_sha256 = base.canonical_sha256(sorted(rows))

    base_report = verify_secondary_analysis_execution_v1_1_4()
    _require(base_report["status"] == "PASS", "v1.1.4 base verification failed.")
    authority = verify_amendment_authority(config)
    schedule, tasks = base.frozen_schedule(config)
    inherited_schedule, inherited_tasks = base.frozen_schedule(
        load_v114_config(V114_CONFIG)
    )
    _require(len(tasks) == 96, "v1.1.5 changed the roster cardinality.")
    _require(schedule["counts"] == inherited_schedule["counts"], "v1.1.5 changed task counts.")
    _require(
        [task["task_identity_sha256"] for task in tasks]
        == [task["task_identity_sha256"] for task in inherited_tasks],
        "v1.1.5 changed task identities or order.",
    )
    common = section["interpretation"]["common_permutation"]
    _require(common["economic_group_duplicate_policy"] == POLICY_ID, "Wrong v1.1.5 policy ID.")
    _require(common["require_consistent_label_within_economic_group"] is True, "Within-group label check disabled.")
    _require(common["canonical_representative_order"] == "frozen_validation_row_order", "Canonical order changed.")
    _require(common["feature_aggregation"] == "none", "Feature aggregation is forbidden.")
    expected_duplicates = {
        "fold_2015": 2,
        "fold_2016": 2,
        "fold_2017": 0,
        "fold_2018": 0,
        "fold_2019": 1,
        "fold_2020": 0,
    }
    amendment = section["economic_group_permutation_amendment"]
    _require(amendment["observed_excess_rows_by_fold"] == expected_duplicates, "Frozen duplicate audit changed.")
    _require(amendment["observed_total_excess_rows"] == 5, "Wrong duplicate total.")

    controller_source = (
        ROOT / "src/modeling/secondary_analysis_execution_v1_1_5.py"
    ).read_text(encoding="utf-8")
    worker_source = (
        ROOT / "src/modeling/secondary_analysis_execution_worker_v1_1_5.py"
    ).read_text(encoding="utf-8")
    _require(
        "secondary_analysis_execution_worker_v1_1_5" in controller_source,
        "v1.1.5 controller does not route to amended worker.",
    )
    _require(
        "canonical_economic_group_indices" in worker_source,
        "v1.1.5 canonical group selection is absent.",
    )
    _require(
        "Target label differs within an economic group" in worker_source,
        "v1.1.5 label consistency gate is absent.",
    )
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": "SECONDARY_DEVELOPMENT_EXECUTION_V1_1_5_ECONOMIC_GROUP_PERMUTATION_INTEGRITY_PASS",
        "base_amendment_verdict": base_report["verdict"],
        "verified_package_files": len(verified),
        "verified_amendment_authorities": len(authority),
        "committed_clean_gate_required": require_committed,
        "package_git_index_sha256": git_index_sha256,
        "planned_tasks": len(tasks),
        "task_counts": schedule["counts"],
        "task_identities_changed": False,
        "interpretation_method_changed": True,
        "methodology_changed": True,
        "economic_group_duplicate_policy": POLICY_ID,
        "observed_excess_rows_by_fold": expected_duplicates,
        "observed_total_excess_rows": 5,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    print(
        json.dumps(
            verify_secondary_analysis_execution_v1_1_5(), indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()

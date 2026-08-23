"""Read-only verifier for the v1.1.4 parallel/checkpoint amendment."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling.secondary_analysis_execution_v1_1_4 import (
    DEFAULT_CONFIG,
    ROOT,
    load_execution_config,
    verify_amendment_authority,
)
from src.modeling.secondary_analysis_execution_v1_1_3 import (
    DEFAULT_CONFIG as V113_CONFIG,
    load_execution_config as load_v113_config,
)
from src.modeling.verify_secondary_analysis_execution_v1_1_3 import (
    verify_secondary_analysis_execution_v1_1_3,
)


DEFAULT_MANIFEST = (
    ROOT / "configs/secondary_development_execution_v1_1_4_freeze_manifest.yaml"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "v1.1.4 Git gate failed.")
    return completed.stdout.strip()


def verify_secondary_analysis_execution_v1_1_4(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    require_committed: bool = False,
) -> dict[str, Any]:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    freeze = payload.get("secondary_development_parallel_checkpoint_freeze") or {}
    _require(freeze.get("id") == "secondary_development_execution_v1_1_4", "Wrong v1.1.4 freeze ID.")
    _require(freeze.get("status") == "FROZEN", "v1.1.4 is not frozen.")
    config = load_execution_config(DEFAULT_CONFIG)
    section = config["secondary_development_execution"]
    _require(
        section["status"] == "executable_parallel_checkpoint_amendment_frozen",
        "v1.1.4 config is not frozen.",
    )
    verified: dict[str, str] = {}
    package_files: list[str] = []
    for item in freeze.get("files") or []:
        relative = str(item["path"])
        path = (ROOT / relative).resolve()
        _require(path.is_relative_to(ROOT), "v1.1.4 path escapes repository.")
        _require(path.is_file(), f"Missing v1.1.4 file: {relative}")
        actual = base.file_sha256(path)
        _require(actual == str(item["sha256"]), f"v1.1.4 hash mismatch: {relative}")
        _require(path.stat().st_size == int(item["bytes"]), f"v1.1.4 size mismatch: {relative}")
        if item.get("executable"):
            _require(bool(path.stat().st_mode & 0o111), f"v1.1.4 script is not executable: {relative}")
        verified[relative] = actual
        package_files.append(relative)
    manifest_relative = str(manifest_path.relative_to(ROOT))
    expected_inventory = set(package_files) | {manifest_relative}
    _require(set(section["git_gate"]["package_files"]) == expected_inventory, "v1.1.4 Git inventory mismatch.")
    package_files.append(manifest_relative)
    git_index_sha256 = "NOT_REQUIRED_FOR_READ_ONLY_VERIFY"
    if require_committed:
        for relative in package_files:
            _git("ls-files", "--error-unmatch", "--", relative)
        dirty = _git("status", "--porcelain", "--", *package_files)
        _require(not dirty, "v1.1.4 package is uncommitted or modified:\n" + dirty)
        rows = _git("ls-files", "-s", "--", *package_files).splitlines()
        _require(len(rows) == len(package_files), "v1.1.4 Git cardinality mismatch.")
        git_index_sha256 = base.canonical_sha256(sorted(rows))

    base_report = verify_secondary_analysis_execution_v1_1_3()
    _require(base_report["status"] == "PASS", "v1.1.3 base verification failed.")
    authority = verify_amendment_authority(config)
    schedule, tasks = base.frozen_schedule(config)
    inherited_schedule, inherited_tasks = base.frozen_schedule(load_v113_config(V113_CONFIG))
    _require(len(tasks) == 96, "v1.1.4 changed the roster cardinality.")
    _require(
        [task["task_identity_sha256"] for task in tasks]
        == [task["task_identity_sha256"] for task in inherited_tasks],
        "v1.1.4 changed task identities or order.",
    )
    _require(schedule["counts"] == inherited_schedule["counts"], "v1.1.4 changed task counts.")
    parallel = section["parallel_execution"]
    expected_limits = {
        "maximum_parallel_classical_folds": 4,
        "maximum_parallel_mlp_folds": 2,
        "maximum_parallel_qnn_folds": 4,
    }
    for key, value in expected_limits.items():
        _require(int(parallel[key]) == value, f"Wrong v1.1.4 limit: {key}")
        _require(int(section["resources"][key]) == value, f"v1.1.4 exceeds inherited limit: {key}")
    policy = section["interpretation_checkpoint_sources"]
    _require(int(policy["expected_checkpoint_count"]) == 36, "Wrong checkpoint inventory size.")
    _require(policy["base_seed"] == 20260818, "Base checkpoint seed changed.")
    _require(policy["confirmation_seeds"] == [20260819, 20260820], "Confirmation seeds changed.")
    _require(
        set(policy["expected_families"]) == {"pytorch_mlp", "qnn"},
        "Checkpoint families changed.",
    )
    controller_source = (ROOT / "src/modeling/secondary_analysis_execution_v1_1_4.py").read_text(
        encoding="utf-8"
    )
    _require("ThreadPoolExecutor" in controller_source, "v1.1.4 ordered concurrency is absent.")
    _require("ordered_parallel_map" in controller_source, "v1.1.4 ordered map is absent.")
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": "SECONDARY_DEVELOPMENT_EXECUTION_V1_1_4_PARALLEL_CHECKPOINT_INTEGRITY_PASS",
        "base_amendment_verdict": base_report["verdict"],
        "verified_package_files": len(verified),
        "verified_amendment_authorities": len(authority),
        "committed_clean_gate_required": require_committed,
        "package_git_index_sha256": git_index_sha256,
        "planned_tasks": len(tasks),
        "task_counts": schedule["counts"],
        "checkpoint_inventory_expected": 36,
        "parallel_limits": expected_limits,
        "task_identities_changed": False,
        "methodology_changed": False,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    print(
        json.dumps(
            verify_secondary_analysis_execution_v1_1_4(), indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()

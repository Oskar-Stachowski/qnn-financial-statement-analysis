"""Read-only verifier for the v1.1.3 signal-source amendment."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling.secondary_analysis_execution_v1_1_3 import (
    DEFAULT_CONFIG,
    ROOT,
    load_execution_config,
    verify_amendment_authority,
)
from src.modeling.verify_secondary_analysis_execution_v1_1_1 import (
    verify_secondary_analysis_execution_v1_1_1,
)


DEFAULT_MANIFEST = (
    ROOT / "configs/secondary_development_execution_v1_1_3_freeze_manifest.yaml"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "v1.1.3 Git gate failed.")
    return completed.stdout.strip()


def verify_secondary_analysis_execution_v1_1_3(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    require_committed: bool = False,
) -> dict[str, Any]:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    freeze = payload.get("secondary_development_signal_source_freeze") or {}
    _require(freeze.get("id") == "secondary_development_execution_v1_1_3", "Wrong v1.1.3 freeze ID.")
    _require(freeze.get("status") == "FROZEN", "v1.1.3 is not frozen.")
    config = load_execution_config(DEFAULT_CONFIG)
    section = config["secondary_development_execution"]
    _require(section["status"] == "executable_signal_source_amendment_frozen", "v1.1.3 config is not frozen.")
    verified: dict[str, str] = {}
    package_files: list[str] = []
    for item in freeze.get("files") or []:
        relative = str(item["path"])
        path = (ROOT / relative).resolve()
        _require(path.is_relative_to(ROOT), "v1.1.3 path escapes repository.")
        _require(path.is_file(), f"Missing v1.1.3 file: {relative}")
        actual = base.file_sha256(path)
        _require(actual == str(item["sha256"]), f"v1.1.3 hash mismatch: {relative}")
        _require(path.stat().st_size == int(item["bytes"]), f"v1.1.3 size mismatch: {relative}")
        if item.get("executable"):
            _require(bool(path.stat().st_mode & 0o111), f"v1.1.3 script is not executable: {relative}")
        verified[relative] = actual
        package_files.append(relative)
    manifest_relative = str(manifest_path.relative_to(ROOT))
    expected_inventory = set(package_files) | {manifest_relative}
    _require(set(section["git_gate"]["package_files"]) == expected_inventory, "v1.1.3 Git inventory mismatch.")
    package_files.append(manifest_relative)
    git_index_sha256 = "NOT_REQUIRED_FOR_READ_ONLY_VERIFY"
    if require_committed:
        for relative in package_files:
            _git("ls-files", "--error-unmatch", "--", relative)
        dirty = _git("status", "--porcelain", "--", *package_files)
        _require(not dirty, "v1.1.3 package is uncommitted or modified:\n" + dirty)
        rows = _git("ls-files", "-s", "--", *package_files).splitlines()
        _require(len(rows) == len(package_files), "v1.1.3 Git cardinality mismatch.")
        git_index_sha256 = base.canonical_sha256(sorted(rows))
    base_report = verify_secondary_analysis_execution_v1_1_1()
    _require(base_report["status"] == "PASS", "v1.1.1 base verification failed.")
    authority = verify_amendment_authority(config)
    schedule, tasks = base.frozen_schedule(config)
    _require(len(tasks) == 96, "v1.1.3 changed the roster.")
    source = section["authority"]["robustness_signal_source"]
    _require(
        source["path"]
        == section["authority"]["production_runner_config"]["path"].replace(
            "configs/production_experiment_runner_v1_0_1_lightning.yaml",
            "data/processed/research_universe_pit_v1_1_0_target_pit_b_v1_2_0_train.csv",
        ),
        "v1.1.3 signal source is not the frozen production target projection.",
    )
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": "SECONDARY_DEVELOPMENT_EXECUTION_V1_1_3_SIGNAL_SOURCE_INTEGRITY_PASS",
        "base_amendment_verdict": base_report["verdict"],
        "verified_package_files": len(verified),
        "verified_amendment_authorities": len(authority),
        "committed_clean_gate_required": require_committed,
        "package_git_index_sha256": git_index_sha256,
        "planned_tasks": len(tasks),
        "task_counts": schedule["counts"],
        "additional_interim_target_deserialization": False,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    print(
        json.dumps(
            verify_secondary_analysis_execution_v1_1_3(), indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()

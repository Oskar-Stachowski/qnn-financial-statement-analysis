"""Read-only integrity verifier for secondary-development execution v1.1.0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.modeling.secondary_analysis_execution import (
    DEFAULT_CONFIG,
    ROOT,
    file_sha256,
    frozen_schedule,
    load_execution_config,
    verify_static_authority,
)


DEFAULT_MANIFEST = (
    ROOT / "configs/secondary_development_execution_v1_1_0_freeze_manifest.yaml"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_secondary_analysis_execution_package(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    freeze = manifest.get("secondary_development_execution_freeze") or {}
    _require(freeze.get("id") == "secondary_development_execution_v1_1_0", "Wrong freeze ID.")
    _require(freeze.get("status") == "FROZEN", "Execution package is not frozen.")
    config = load_execution_config(DEFAULT_CONFIG)
    section = config["secondary_development_execution"]
    _require(section["status"] == "executable_package_frozen", "Config is not frozen.")
    verified_files: dict[str, str] = {}
    for item in freeze.get("files") or []:
        path = (ROOT / str(item["path"])).resolve()
        _require(path.is_relative_to(ROOT), "Package path escapes repository.")
        _require(path.is_file(), f"Missing package file: {path}")
        actual = file_sha256(path)
        _require(actual == str(item["sha256"]), f"Package hash mismatch: {item['path']}")
        _require(path.stat().st_size == int(item["bytes"]), f"Package size mismatch: {item['path']}")
        if item.get("executable"):
            _require(bool(path.stat().st_mode & 0o111), f"Script is not executable: {path}")
        verified_files[str(item["path"])] = actual
    expected_inventory = set(verified_files) | {str(manifest_path.relative_to(ROOT))}
    _require(set(section["git_gate"]["package_files"]) == expected_inventory, "Git-gate inventory mismatch.")
    static_authority = verify_static_authority(config)
    schedule, tasks = frozen_schedule(config)
    _require(len(tasks) == 96, "Frozen task count mismatch.")
    _require(schedule["counts"]["pca_matched_control_fold_fits"] == 12, "PCA count mismatch.")
    _require(schedule["counts"]["global_winner_robustness_fold_fits"] == 48, "Classical robustness count mismatch.")
    _require(schedule["counts"]["qnn_structural_robustness_fold_fits"] == 24, "QNN robustness count mismatch.")
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": "SECONDARY_DEVELOPMENT_EXECUTION_V1_1_0_PACKAGE_INTEGRITY_PASS",
        "verified_package_files": len(verified_files),
        "verified_static_authorities": len(static_authority),
        "planned_tasks": len(tasks),
        "pca_control_fold_fits": 12,
        "interpretability_tasks": 12,
        "classical_robustness_fold_fits": 48,
        "qnn_structural_fold_fits": 24,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    print(
        json.dumps(
            verify_secondary_analysis_execution_package(), indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()

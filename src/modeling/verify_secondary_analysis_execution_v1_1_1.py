"""Read-only verifier for the v1.1.1 input-key amendment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling.secondary_analysis_execution_v1_1_1 import (
    DEFAULT_CONFIG,
    ROOT,
    load_execution_config,
    verify_amendment_authority,
)
from src.modeling.verify_secondary_analysis_execution_package import (
    verify_secondary_analysis_execution_package,
)


DEFAULT_MANIFEST = (
    ROOT / "configs/secondary_development_execution_v1_1_1_freeze_manifest.yaml"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_secondary_analysis_execution_v1_1_1(
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    freeze = manifest.get("secondary_development_execution_amendment_freeze") or {}
    _require(freeze.get("id") == "secondary_development_execution_v1_1_1", "Wrong amendment freeze ID.")
    _require(freeze.get("status") == "FROZEN", "Amendment is not frozen.")
    config = load_execution_config(DEFAULT_CONFIG)
    section = config["secondary_development_execution"]
    _require(section["status"] == "executable_input_key_amendment_frozen", "Amendment config is not frozen.")
    verified_files: dict[str, str] = {}
    for item in freeze.get("files") or []:
        path = (ROOT / str(item["path"])).resolve()
        _require(path.is_relative_to(ROOT), "Amendment path escapes repository.")
        _require(path.is_file(), f"Missing amendment file: {item['path']}")
        actual = base.file_sha256(path)
        _require(actual == str(item["sha256"]), f"Amendment hash mismatch: {item['path']}")
        _require(path.stat().st_size == int(item["bytes"]), f"Amendment size mismatch: {item['path']}")
        if item.get("executable"):
            _require(bool(path.stat().st_mode & 0o111), f"Script is not executable: {item['path']}")
        verified_files[str(item["path"])] = actual
    expected = set(verified_files) | {str(manifest_path.relative_to(ROOT))}
    _require(set(section["git_gate"]["package_files"]) == expected, "Amendment Git inventory mismatch.")
    base_report = verify_secondary_analysis_execution_package()
    _require(base_report["status"] == "PASS", "Base v1.1.0 package failed verification.")
    amendment_authority = verify_amendment_authority(config)
    schedule, tasks = base.frozen_schedule(config)
    _require(len(tasks) == 96, "Amendment changed the task roster.")
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": "SECONDARY_DEVELOPMENT_EXECUTION_V1_1_1_INPUT_KEY_INTEGRITY_PASS",
        "verified_amendment_files": len(verified_files),
        "verified_amendment_authorities": len(amendment_authority),
        "base_package_verdict": base_report["verdict"],
        "planned_tasks": len(tasks),
        "task_counts": schedule["counts"],
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    print(json.dumps(verify_secondary_analysis_execution_v1_1_1(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

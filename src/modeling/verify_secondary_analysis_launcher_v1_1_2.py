"""Verify the single-import launcher amendment v1.1.2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from src.modeling.secondary_analysis_execution_v1_1_1 import ROOT
from src.modeling.secondary_analysis_schemas import canonical_sha256, file_sha256
from src.modeling.verify_secondary_analysis_execution_v1_1_1 import (
    verify_secondary_analysis_execution_v1_1_1,
)


DEFAULT_MANIFEST = (
    ROOT / "configs/secondary_development_execution_v1_1_2_launcher_freeze_manifest.yaml"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "Launcher Git gate failed.")
    return completed.stdout.strip()


def verify_secondary_analysis_launcher_v1_1_2(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    require_committed: bool = False,
) -> dict[str, Any]:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    freeze = payload.get("secondary_development_execution_launcher_freeze") or {}
    _require(freeze.get("id") == "secondary_development_execution_launcher_v1_1_2", "Wrong launcher freeze ID.")
    _require(freeze.get("status") == "FROZEN", "Launcher is not frozen.")
    verified: dict[str, str] = {}
    package_files: list[str] = []
    for item in freeze.get("files") or []:
        relative = str(item["path"])
        path = (ROOT / relative).resolve()
        _require(path.is_relative_to(ROOT), "Launcher path escapes repository.")
        _require(path.is_file(), f"Missing launcher file: {relative}")
        actual = file_sha256(path)
        _require(actual == str(item["sha256"]), f"Launcher hash mismatch: {relative}")
        _require(path.stat().st_size == int(item["bytes"]), f"Launcher size mismatch: {relative}")
        if item.get("executable"):
            _require(bool(path.stat().st_mode & 0o111), f"Launcher is not executable: {relative}")
        verified[relative] = actual
        package_files.append(relative)
    manifest_relative = str(manifest_path.relative_to(ROOT))
    package_files.append(manifest_relative)
    git_index_sha256 = "NOT_REQUIRED_FOR_READ_ONLY_VERIFY"
    if require_committed:
        for relative in package_files:
            _git("ls-files", "--error-unmatch", "--", relative)
        dirty = _git("status", "--porcelain", "--", *package_files)
        _require(not dirty, "Launcher package is uncommitted or modified:\n" + dirty)
        rows = _git("ls-files", "-s", "--", *package_files).splitlines()
        _require(len(rows) == len(package_files), "Launcher Git inventory mismatch.")
        git_index_sha256 = canonical_sha256(sorted(rows))
    base_report = verify_secondary_analysis_execution_v1_1_1()
    _require(base_report["status"] == "PASS", "v1.1.1 amendment verification failed.")
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": "SECONDARY_DEVELOPMENT_EXECUTION_V1_1_2_SINGLE_IMPORT_LAUNCHER_PASS",
        "base_amendment_verdict": base_report["verdict"],
        "verified_launcher_files": len(verified),
        "committed_clean_gate_required": require_committed,
        "launcher_git_index_sha256": git_index_sha256,
        "planned_tasks": 96,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-committed", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            verify_secondary_analysis_launcher_v1_1_2(
                require_committed=args.require_committed
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

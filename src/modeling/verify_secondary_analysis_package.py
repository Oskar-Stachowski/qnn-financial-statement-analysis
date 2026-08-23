"""Read-only verifier for the secondary-development pre-execution freeze."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from src.modeling.secondary_analysis_runner import package_status
from src.modeling.secondary_analysis_schemas import (
    DEFAULT_CONFIG,
    ROOT,
    file_sha256,
    load_config,
    require,
)
from src.modeling.verify_post_coarse_results_freeze import (
    verify_post_coarse_results_freeze,
)


DEFAULT_FREEZE_MANIFEST = (
    ROOT / "configs/secondary_development_analyses_v1_0_0_freeze_manifest.yaml"
)


def _verify_file(entry: Mapping[str, Any]) -> None:
    path = (ROOT / str(entry["path"])).resolve()
    require(path.is_relative_to(ROOT), f"Package file escapes repository: {path}")
    require(path.is_file(), f"Missing frozen package file: {path}")
    require(path.stat().st_size == int(entry["bytes"]), f"Size mismatch: {path}")
    require(file_sha256(path) == str(entry["sha256"]), f"SHA-256 mismatch: {path}")
    if entry.get("executable") is True:
        require(bool(path.stat().st_mode & 0o111), f"Executable bit missing: {path}")


def verify_secondary_analysis_package(
    manifest_path: Path = DEFAULT_FREEZE_MANIFEST,
) -> dict[str, Any]:
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    require(isinstance(manifest, dict), "Package freeze manifest must be a mapping.")
    freeze = manifest.get("secondary_analysis_package_freeze") or {}
    require(freeze.get("status") == "FROZEN", "Package is not FROZEN.")
    require(
        freeze.get("verdict") == "SECONDARY_DEVELOPMENT_V1_0_0_PACKAGE_INTEGRITY_PASS",
        "Unexpected package-freeze verdict.",
    )
    require(freeze.get("project_data_read") is False, "Package freeze read project data.")
    require(
        freeze.get("project_model_fit_performed") is False,
        "Package freeze fit a project model.",
    )
    require(
        freeze.get("protected_feature_years_opened") is False,
        "Package freeze opened protected years.",
    )

    entries = manifest.get("package_files") or []
    require(isinstance(entries, list) and entries, "Package file inventory is empty.")
    for entry in entries:
        _verify_file(entry)

    config = load_config(DEFAULT_CONFIG)
    configured_files = set(
        config["secondary_development_analyses"]["git_gate"]["package_files"]
    )
    frozen_files = {str(entry["path"]) for entry in entries}
    frozen_files.add(str(manifest_path.relative_to(ROOT)))
    require(configured_files == frozen_files, "Git-gate and freeze file inventories differ.")

    status = package_status(DEFAULT_CONFIG)
    require(status["status"] == "PASS", "Package status failed.")
    expected = manifest.get("frozen_counts") or {}
    counts = status["planned_fit_counts"]
    require(
        counts["pca_matched_control_fold_fits"]
        == int(expected["pca_matched_control_fold_fits"]),
        "PCA fit count mismatch.",
    )
    require(
        counts["global_winner_robustness_fold_fits"]
        == int(expected["global_winner_robustness_fold_fits"]),
        "Winner robustness count mismatch.",
    )
    require(
        counts["qnn_structural_fold_fits"]
        == int(expected["qnn_structural_fold_fits"]),
        "QNN robustness count mismatch.",
    )

    post_coarse = verify_post_coarse_results_freeze()
    require(post_coarse["status"] == "PASS", "Upstream post-coarse freeze failed.")
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": freeze["verdict"],
        "verified_package_files": len(entries),
        "verified_authority_files": status["verified_authority_files"],
        "pca_matched_control_fold_fits": counts["pca_matched_control_fold_fits"],
        "global_winner_robustness_fold_fits": counts[
            "global_winner_robustness_fold_fits"
        ],
        "qnn_structural_fold_fits": counts["qnn_structural_fold_fits"],
        "post_coarse_freeze_verdict": post_coarse["verdict"],
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    print(json.dumps(verify_secondary_analysis_package(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Read-only verifier for the v1.1.6 TreeSHAP compatibility amendment."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling.secondary_analysis_execution_v1_1_5 import (
    DEFAULT_CONFIG as V115_CONFIG,
    load_execution_config as load_v115_config,
)
from src.modeling.secondary_analysis_execution_v1_1_6 import (
    DEFAULT_CONFIG,
    ROOT,
    TREE_SHAP_TASK_SHA256,
    load_execution_config,
    verify_amendment_authority,
)
from src.modeling.secondary_analysis_execution_worker_v1_1_6 import (
    TREE_SHAP_POLICY_ID,
)
from src.modeling.verify_secondary_analysis_execution_v1_1_5 import (
    verify_secondary_analysis_execution_v1_1_5,
)


DEFAULT_MANIFEST = (
    ROOT / "configs/secondary_development_execution_v1_1_6_freeze_manifest.yaml"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "v1.1.6 Git gate failed.")
    return completed.stdout.strip()


def verify_secondary_analysis_execution_v1_1_6(
    manifest_path: Path = DEFAULT_MANIFEST,
    *,
    require_committed: bool = False,
) -> dict[str, Any]:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    freeze = payload.get("secondary_development_treeshap_freeze") or {}
    _require(freeze.get("id") == "secondary_development_execution_v1_1_6", "Wrong v1.1.6 freeze ID.")
    _require(freeze.get("status") == "FROZEN", "v1.1.6 is not frozen.")
    config = load_execution_config(DEFAULT_CONFIG)
    section = config["secondary_development_execution"]
    _require(
        section["status"] == "executable_treeshap_compatibility_amendment_frozen",
        "v1.1.6 config is not frozen.",
    )

    verified: dict[str, str] = {}
    package_files: list[str] = []
    for item in freeze.get("files") or []:
        relative = str(item["path"])
        path = (ROOT / relative).resolve()
        _require(path.is_relative_to(ROOT), "v1.1.6 path escapes repository.")
        _require(path.is_file(), f"Missing v1.1.6 file: {relative}")
        actual = base.file_sha256(path)
        _require(actual == str(item["sha256"]), f"v1.1.6 hash mismatch: {relative}")
        _require(path.stat().st_size == int(item["bytes"]), f"v1.1.6 size mismatch: {relative}")
        if item.get("executable"):
            _require(bool(path.stat().st_mode & 0o111), f"v1.1.6 script is not executable: {relative}")
        verified[relative] = actual
        package_files.append(relative)
    manifest_relative = str(manifest_path.relative_to(ROOT))
    expected_inventory = set(package_files) | {manifest_relative}
    _require(
        set(section["git_gate"]["package_files"]) == expected_inventory,
        "v1.1.6 Git inventory mismatch.",
    )
    package_files.append(manifest_relative)
    git_index_sha256 = "NOT_REQUIRED_FOR_READ_ONLY_VERIFY"
    if require_committed:
        for relative in package_files:
            _git("ls-files", "--error-unmatch", "--", relative)
        dirty = _git("status", "--porcelain", "--", *package_files)
        _require(not dirty, "v1.1.6 package is uncommitted or modified:\n" + dirty)
        rows = _git("ls-files", "-s", "--", *package_files).splitlines()
        _require(len(rows) == len(package_files), "v1.1.6 Git cardinality mismatch.")
        git_index_sha256 = base.canonical_sha256(sorted(rows))

    base_report = verify_secondary_analysis_execution_v1_1_5()
    _require(base_report["status"] == "PASS", "v1.1.5 base verification failed.")
    authority = verify_amendment_authority(config)
    schedule, tasks = base.frozen_schedule(config)
    inherited_schedule, inherited_tasks = base.frozen_schedule(
        load_v115_config(V115_CONFIG)
    )
    _require(len(tasks) == 96, "v1.1.6 changed the roster cardinality.")
    _require(schedule["counts"] == inherited_schedule["counts"], "v1.1.6 changed task counts.")
    _require(
        [task["task_identity_sha256"] for task in tasks]
        == [task["task_identity_sha256"] for task in inherited_tasks],
        "v1.1.6 changed task identities or order.",
    )
    tree_task = next(
        (task for task in tasks if task["task_identity_sha256"] == TREE_SHAP_TASK_SHA256),
        None,
    )
    _require(tree_task is not None, "Frozen TreeSHAP repair task is absent.")
    identity = tree_task["task_identity"]
    _require(identity.get("family") == "xgboost", "TreeSHAP repair family changed.")
    _require(identity.get("representative_role") == "tree_boosting", "TreeSHAP repair role changed.")

    amendment = section["treeshap_compatibility_amendment"]
    for field in (
        "target_values_changed",
        "sample_membership_changed",
        "fold_policy_changed",
        "task_roster_changed",
        "task_identity_changed",
        "model_parameters_changed",
        "interpretation_method_changed",
        "robustness_method_changed",
        "methodology_changed",
    ):
        _require(amendment[field] is False, f"v1.1.6 changed {field}.")
    policy = section["interpretation"]["tree_shap"]["runtime_compatibility"]
    _require(policy["policy_id"] == TREE_SHAP_POLICY_ID, "Wrong TreeSHAP policy ID.")
    _require(policy["feature_perturbation"] == "interventional", "TreeSHAP perturbation changed.")
    _require(policy["model_output"] == "raw", "TreeSHAP model output changed.")
    _require(policy["background_subsampling"] is False, "TreeSHAP background subsampling enabled.")
    _require(policy["verify_booster_bytes_unchanged"] is True, "Booster preservation gate disabled.")
    _require(policy["verify_raw_scores_unchanged"] is True, "Raw-score preservation gate disabled.")
    carry = section["carry_forward"]
    _require(carry["required_complete_pca_tasks"] == 12, "Wrong PCA carry count.")
    _require(carry["required_complete_interpretation_tasks"] == 11, "Wrong interpretation carry count.")
    _require(carry["required_failed_interpretation_tasks"] == 1, "Wrong failed-task count.")
    _require(carry["excluded_failed_task_identity_sha256"] == TREE_SHAP_TASK_SHA256, "Wrong excluded task.")

    worker_source = (
        ROOT / "src/modeling/secondary_analysis_execution_worker_v1_1_6.py"
    ).read_text(encoding="utf-8")
    controller_source = (
        ROOT / "src/modeling/secondary_analysis_execution_v1_1_6.py"
    ).read_text(encoding="utf-8")
    for required in (
        "model.set_params(enable_categorical=False)",
        "max_samples=len(background)",
        "booster_before != booster_after",
        "np.array_equal(raw_before, raw_after)",
        "additivity_max_abs > 1e-4",
    ):
        _require(required in worker_source, f"Missing TreeSHAP safety gate: {required}")
    for required in (
        "os.link(source, target)",
        "source_stat.st_ino == target_stat.st_ino",
        "excluded_failed_task_identity_sha256",
        "carried_interpretation_tasks",
    ):
        _require(required in controller_source, f"Missing carry-forward safety gate: {required}")
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": "SECONDARY_DEVELOPMENT_EXECUTION_V1_1_6_TREESHAP_INTEGRITY_PASS",
        "base_amendment_verdict": base_report["verdict"],
        "verified_package_files": len(verified),
        "verified_amendment_authorities": len(authority),
        "committed_clean_gate_required": require_committed,
        "package_git_index_sha256": git_index_sha256,
        "planned_tasks": len(tasks),
        "task_counts": schedule["counts"],
        "task_identities_changed": False,
        "methodology_changed": False,
        "tree_shap_policy": TREE_SHAP_POLICY_ID,
        "recomputed_tasks": 1,
        "recomputed_folds": 6,
        "carried_pca_tasks": 12,
        "carried_interpretation_tasks": 11,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    print(
        json.dumps(
            verify_secondary_analysis_execution_v1_1_6(), indent=2, sort_keys=True
        )
    )


if __name__ == "__main__":
    main()

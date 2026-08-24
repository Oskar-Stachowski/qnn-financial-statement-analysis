"""TreeSHAP repair and exact result carry-forward for secondary v1.1.6."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling import secondary_analysis_execution_v1_1_4 as v114
from src.modeling import secondary_analysis_execution_v1_1_5 as v115
from src.modeling.secondary_analysis_execution_worker_v1_1_6 import (
    TREE_SHAP_POLICY_ID,
)


ROOT = base.ROOT
DEFAULT_CONFIG = (
    ROOT / "configs/secondary_development_execution_v1_1_6_treeshap_fix.yaml"
)
DEFAULT_OUTPUT = ROOT / "data/model_runs/secondary_development_v1_1_6"
SOURCE_OUTPUT = ROOT / "data/model_runs/secondary_development_v1_1_5"
WORKER_MODULE = "src.modeling.secondary_analysis_execution_worker_v1_1_6"
TREE_SHAP_TASK_SHA256 = (
    "fb495db9591e3ac313b53e0818cde0043e9335e9c91562b68811efcb269382c0"
)
_BASE_PREFLIGHT_CONTEXT = v114._BASE_PREFLIGHT_CONTEXT


def load_execution_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = yaml.safe_load(path.resolve().read_text(encoding="utf-8"))
    base._require(isinstance(payload, dict), "v1.1.6 config must be a mapping.")
    extension = payload.get("extends")
    base._require(isinstance(extension, Mapping), "v1.1.6 must extend v1.1.5.")
    base_path = (ROOT / str(extension["path"])).resolve()
    expected = (
        ROOT
        / "configs/secondary_development_execution_v1_1_5_economic_group_permutation_fix.yaml"
    )
    base._require(base_path == expected, "Wrong v1.1.6 amendment base.")
    base._require(
        base.file_sha256(base_path) == str(extension["sha256"]),
        "v1.1.5 config hash mismatch.",
    )
    inherited = v115.load_execution_config(base_path)
    merged = v114._merge(
        inherited, {key: value for key, value in payload.items() if key != "extends"}
    )
    section = merged["secondary_development_execution"]
    base._require(section["id"] == "secondary_development_execution_v1_1_6", "Wrong v1.1.6 ID.")
    base._require(section["version"] == "1.1.6", "Wrong v1.1.6 version.")
    base._require(
        section["status"] == "executable_treeshap_compatibility_amendment_frozen",
        "v1.1.6 is not frozen.",
    )
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
        base._require(amendment[field] is False, f"Forbidden v1.1.6 change: {field}")
    policy = section["interpretation"]["tree_shap"]["runtime_compatibility"]
    base._require(policy["policy_id"] == TREE_SHAP_POLICY_ID, "Wrong TreeSHAP policy.")
    base._require(policy["background_subsampling"] is False, "TreeSHAP background may not be subsampled.")
    base._require(policy["fitted_booster_may_change"] is False, "TreeSHAP repair may not change booster.")
    return merged


def verify_amendment_authority(config: Mapping[str, Any]) -> dict[str, str]:
    authority = config["secondary_development_execution"][
        "amendment_authority_v1_1_6"
    ]
    verified: dict[str, str] = {}
    for name, item in authority.items():
        path = (ROOT / str(item["path"])).resolve()
        base._require(path.is_relative_to(ROOT), f"v1.1.6 authority escapes repository: {name}")
        base._require(path.is_file(), f"Missing v1.1.6 authority: {name}")
        actual = base.file_sha256(path)
        base._require(actual == str(item["sha256"]), f"v1.1.6 authority mismatch: {name}")
        verified[name] = actual
    return verified


def _output_identity(config_path: Path, git_index_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": "secondary_development_execution_v1_1_6",
        "execution_config_sha256": base.file_sha256(config_path),
        "base_execution_config_sha256": base.file_sha256(
            ROOT / "configs/secondary_development_execution_v1_1_0.yaml"
        ),
        "frozen_schedule_sha256": base.file_sha256(
            ROOT / "configs/secondary_development_analyses_v1_0_0.yaml"
        ),
        "package_git_index_sha256": git_index_sha256,
        "economic_group_duplicate_policy": v115.POLICY_ID,
        "tree_shap_policy": TREE_SHAP_POLICY_ID,
        "protected_feature_years_opened": False,
    }


def _patched_preflight_context(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> Any:
    config = load_execution_config(config_path)
    verify_amendment_authority(config)
    if not synthetic:
        from src.modeling.verify_secondary_analysis_execution_v1_1_6 import (
            verify_secondary_analysis_execution_v1_1_6,
        )

        report = verify_secondary_analysis_execution_v1_1_6()
        base._require(report["status"] == "PASS", "v1.1.6 package verification failed.")
    context = _BASE_PREFLIGHT_CONTEXT(config_path, output_dir, synthetic=synthetic)
    if not synthetic:
        _config, schedule, _tasks, _runner, sample, _folds = context
        inventory = v114.verify_checkpoint_inventory(config, schedule)
        group_audit = v115._economic_group_audit(sample, config)
        preflight_path = output_dir / "preflight_manifest.json"
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight.update(
            {
                "parallel_checkpoint_amendment_version": "1.1.4",
                "economic_group_permutation_amendment_version": "1.1.5",
                "treeshap_compatibility_amendment_version": "1.1.6",
                "interpretation_checkpoint_count": inventory["checkpoint_count"],
                "interpretation_checkpoint_inventory_sha256": inventory[
                    "inventory_sha256"
                ],
                "parallel_execution": config["secondary_development_execution"][
                    "parallel_execution"
                ],
                "economic_group_permutation_audit": group_audit,
                "tree_shap_policy": config["secondary_development_execution"][
                    "interpretation"
                ]["tree_shap"]["runtime_compatibility"],
            }
        )
        base.atomic_write_json(preflight_path, preflight)
    return context


def _hardlink_file(source: Path, target: Path, output_root: Path) -> dict[str, Any]:
    base._require(source.is_file() and not source.is_symlink(), f"Invalid carry-forward source: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    base._require(not target.exists(), f"Carry-forward target already exists: {target}")
    os.link(source, target)
    source_stat = source.stat()
    target_stat = target.stat()
    base._require(
        source_stat.st_dev == target_stat.st_dev
        and source_stat.st_ino == target_stat.st_ino,
        "Carry-forward file is not an exact hard link.",
    )
    return {
        "path": str(target.relative_to(output_root)),
        "bytes": int(target_stat.st_size),
        "sha256": base.file_sha256(target),
    }


def _source_result(task_sha: str) -> tuple[Path, dict[str, Any]]:
    path = SOURCE_OUTPUT / "task_results" / f"{task_sha}.json"
    base._require(path.is_file(), f"Missing v1.1.5 task result: {task_sha}")
    result = json.loads(path.read_text(encoding="utf-8"))
    base._require(result.get("task_identity_sha256") == task_sha, "Source task identity mismatch.")
    return path, result


def carry_forward_completed_results(
    config_path: Path, output_dir: Path
) -> dict[str, Any]:
    base._require(output_dir.resolve() == DEFAULT_OUTPUT.resolve(), "Carry-forward output must be canonical v1.1.6 root.")
    manifest_path = output_dir / "carry_forward_manifest.json"
    if manifest_path.is_file():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        base._require(existing.get("status") == "COMPLETE", "Carry-forward manifest is incomplete.")
        return existing

    config = load_execution_config(config_path)

    from src.modeling.verify_secondary_analysis_execution_v1_1_5 import (
        verify_secondary_analysis_execution_v1_1_5,
    )

    base._require(
        verify_secondary_analysis_execution_v1_1_5(require_committed=True)["status"]
        == "PASS",
        "v1.1.5 source package verification failed.",
    )
    source_identity_path = SOURCE_OUTPUT / "execution_identity.json"
    source_preflight_path = SOURCE_OUTPUT / "preflight_manifest.json"
    source_pca_path = SOURCE_OUTPUT / "phase_manifests/pca_matched_controls.json"
    source_interpretation_path = SOURCE_OUTPUT / "phase_manifests/interpretability.json"
    for path in (
        source_identity_path,
        source_preflight_path,
        source_pca_path,
        source_interpretation_path,
    ):
        base._require(path.is_file(), f"Missing v1.1.5 carry-forward authority: {path}")
    source_identity = json.loads(source_identity_path.read_text(encoding="utf-8"))
    source_pca = json.loads(source_pca_path.read_text(encoding="utf-8"))
    source_interpretation = json.loads(source_interpretation_path.read_text(encoding="utf-8"))
    base._require(source_identity.get("id") == "secondary_development_execution_v1_1_5", "Wrong carry-forward source identity.")
    carry_policy = config["secondary_development_execution"]["carry_forward"]
    base._require(
        source_identity.get("execution_config_sha256")
        == carry_policy["source_execution_config_sha256"],
        "Carry-forward source config identity changed.",
    )
    base._require(
        source_identity.get("package_git_index_sha256")
        == carry_policy["source_package_git_index_sha256"],
        "Carry-forward source package identity changed.",
    )
    source_preflight = json.loads(source_preflight_path.read_text(encoding="utf-8"))
    base._require(
        source_preflight.get("status") == "PASS"
        and source_preflight.get("protected_feature_years_opened") is False,
        "v1.1.5 source preflight is not valid.",
    )
    base._require(source_pca.get("complete_tasks") == 12 and source_pca.get("failed_tasks") == 0, "v1.1.5 PCA phase is not fully complete.")
    base._require(source_interpretation.get("complete_tasks") == 11 and source_interpretation.get("failed_tasks") == 1, "Unexpected v1.1.5 interpretation accounting.")

    schedule, tasks = base.frozen_schedule(config)
    pca_tasks = [task for task in tasks if task["task_identity"]["stage"] == "pca_matched_controls"]
    interpretation_tasks = [task for task in tasks if task["task_identity"]["stage"] == "interpretability"]
    pca_ids = [str(task["task_identity_sha256"]) for task in pca_tasks]
    interpretation_ids = [str(task["task_identity_sha256"]) for task in interpretation_tasks]
    base._require(TREE_SHAP_TASK_SHA256 in interpretation_ids, "Frozen TreeSHAP task is absent.")
    _failed_path, failed_result = _source_result(TREE_SHAP_TASK_SHA256)
    base._require(
        failed_result.get("status") == "METHOD_FAILED"
        and failed_result.get("failure_code") == "INTERPRETATION_FOLD_FAILED",
        "The excluded v1.1.5 TreeSHAP task has an unexpected status.",
    )
    carried_ids = [*pca_ids, *[value for value in interpretation_ids if value != TREE_SHAP_TASK_SHA256]]

    base._require(not (output_dir / "task_results").exists(), "v1.1.6 task results already exist without a carry-forward manifest.")
    base._require(not (output_dir / "task_artifacts").exists(), "v1.1.6 task artifacts already exist without a carry-forward manifest.")
    artifact_inventory: list[dict[str, Any]] = []
    result_inventory: list[dict[str, Any]] = []
    carried_results: dict[str, dict[str, Any]] = {}
    for task_sha in carried_ids:
        source_result_path, result = _source_result(task_sha)
        base._require(result.get("status") == "COMPLETE", f"Cannot carry failed task: {task_sha}")
        source_artifact_dir = SOURCE_OUTPUT / "task_artifacts" / task_sha
        base._require(source_artifact_dir.is_dir(), f"Missing task artifacts: {task_sha}")
        for source_file in sorted(source_artifact_dir.rglob("*")):
            if source_file.is_file():
                relative = source_file.relative_to(SOURCE_OUTPUT)
                artifact_inventory.append(
                    _hardlink_file(source_file, output_dir / relative, output_dir)
                )
        carried = dict(result)
        carried["carry_forward"] = {
            "source_execution_id": "secondary_development_execution_v1_1_5",
            "source_execution_config_sha256": source_identity[
                "execution_config_sha256"
            ],
            "source_task_result_sha256": base.file_sha256(source_result_path),
            "method_unchanged_for_task": True,
            "artifact_strategy": "verified_hardlink_same_filesystem",
            "protected_feature_years_opened": False,
        }
        target_result_path = output_dir / "task_results" / f"{task_sha}.json"
        result_sha = base.atomic_write_json(target_result_path, carried)
        result_inventory.append(
            {"task_identity_sha256": task_sha, "sha256": result_sha}
        )
        carried_results[task_sha] = carried

    pca_manifest = base._phase_manifest(
        output_dir,
        "pca_matched_controls",
        pca_tasks,
        [carried_results[value] for value in pca_ids],
    )
    pca_manifest["carry_forward_source"] = "secondary_development_execution_v1_1_5"
    pca_manifest["carry_forward_tasks"] = 12
    base.atomic_write_json(
        output_dir / "phase_manifests/pca_matched_controls.json", pca_manifest
    )
    manifest = {
        "schema_version": 1,
        "status": "COMPLETE",
        "source_execution_id": "secondary_development_execution_v1_1_5",
        "source_execution_identity_sha256": base.file_sha256(source_identity_path),
        "source_preflight_sha256": base.file_sha256(source_preflight_path),
        "source_pca_manifest_sha256": base.file_sha256(source_pca_path),
        "source_interpretation_manifest_sha256": base.file_sha256(source_interpretation_path),
        "carried_pca_tasks": 12,
        "carried_interpretation_tasks": 11,
        "excluded_failed_task_identity_sha256": TREE_SHAP_TASK_SHA256,
        "artifact_files": len(artifact_inventory),
        "artifact_logical_bytes": sum(item["bytes"] for item in artifact_inventory),
        "artifact_inventory_sha256": base.canonical_sha256(artifact_inventory),
        "result_inventory_sha256": base.canonical_sha256(result_inventory),
        "storage_strategy": "verified_hardlink_same_filesystem",
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }
    base.atomic_write_json(manifest_path, manifest)
    return manifest


def repair_treeshap(config_path: Path, output_dir: Path) -> dict[str, Any]:
    base._preflight_context(config_path, output_dir)
    carry = carry_forward_completed_results(config_path, output_dir)
    phase = base.execute_interpretability(config_path, output_dir)
    base._require(
        phase.get("complete_tasks") == 12 and phase.get("failed_tasks") == 0,
        "v1.1.6 TreeSHAP repair did not complete interpretation.",
    )
    tree_result_path = output_dir / "task_results" / f"{TREE_SHAP_TASK_SHA256}.json"
    tree_result = json.loads(tree_result_path.read_text(encoding="utf-8"))
    base._require(tree_result.get("status") == "COMPLETE", "TreeSHAP task is not complete.")
    folds = tree_result.get("fold_results") or []
    base._require(len(folds) == 6, "TreeSHAP fold cardinality changed.")
    for fold in folds:
        base._require(fold.get("status") == "COMPLETE", "TreeSHAP fold failed.")
        base._require(fold.get("tree_shap_policy") == TREE_SHAP_POLICY_ID, "TreeSHAP policy mismatch.")
        base._require(fold.get("background_subsampled") is False, "TreeSHAP background was subsampled.")
        base._require(fold.get("estimator_metadata_normalized_after_fit") is True, "TreeSHAP metadata was not normalized.")
    repair = {
        "schema_version": 1,
        "status": "COMPLETE",
        "tree_shap_task_identity_sha256": TREE_SHAP_TASK_SHA256,
        "tree_shap_fold_count": 6,
        "tree_shap_policy": TREE_SHAP_POLICY_ID,
        "carried_pca_tasks": carry["carried_pca_tasks"],
        "carried_interpretation_tasks": carry["carried_interpretation_tasks"],
        "recomputed_interpretation_tasks": 1,
        "recomputed_tree_shap_folds": 6,
        "interpretability_complete_tasks": phase["complete_tasks"],
        "interpretability_failed_tasks": phase["failed_tasks"],
        "may_change_primary_selection": False,
        "protected_feature_years_opened": False,
    }
    base.atomic_write_json(output_dir / "treeshap_repair_manifest.json", repair)
    return repair


def activate_amendment() -> None:
    v115.activate_amendment()
    v115.WORKER_MODULE = WORKER_MODULE
    base.DEFAULT_CONFIG = DEFAULT_CONFIG
    base.load_execution_config = load_execution_config
    base._output_identity = _output_identity
    base._preflight_context = _patched_preflight_context


@contextmanager
def _isolated_activation() -> Any:
    names = (
        "DEFAULT_CONFIG",
        "load_execution_config",
        "_load_project_sample_and_robustness",
        "_output_identity",
        "_preflight_context",
        "_source_checkpoints",
        "_run_interpretation_fold",
        "execute_pca_controls",
        "execute_interpretability",
        "execute_classical_robustness",
        "execute_qnn_robustness",
    )
    previous = {name: getattr(base, name) for name in names}
    previous_worker = v115.WORKER_MODULE
    try:
        activate_amendment()
        yield
    finally:
        v115.WORKER_MODULE = previous_worker
        for name, value in previous.items():
            setattr(base, name, value)


def create_report(config_path: Path, output_dir: Path) -> dict[str, Any]:
    report = base.create_report(config_path, output_dir)
    report["id"] = "secondary_development_execution_v1_1_6"
    report["parallel_checkpoint_amendment"] = "1.1.4"
    report["economic_group_permutation_amendment"] = "1.1.5"
    report["treeshap_compatibility_amendment"] = "1.1.6"
    base.atomic_write_json(output_dir / "run_manifest.json", report)
    result_path = output_dir / "secondary_development_report.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["id"] = "secondary_development_results_v1_1_6"
        result["parallel_checkpoint_amendment"] = "1.1.4"
        result["economic_group_permutation_amendment"] = "1.1.5"
        result["treeshap_compatibility_amendment"] = "1.1.6"
        base.atomic_write_json(result_path, result)
    return report


def main() -> None:
    activate_amendment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "status",
            "plan",
            "smoke",
            "preflight",
            "repair-treeshap",
            "robustness-classical",
            "robustness-qnn",
            "report",
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config_path = args.config.resolve()
    output_dir = (
        args.output_dir.resolve() if args.output_dir is not None else DEFAULT_OUTPUT.resolve()
    )
    base._require(config_path == DEFAULT_CONFIG.resolve(), "Only canonical v1.1.6 config may execute.")
    base._require(output_dir == DEFAULT_OUTPUT.resolve(), "Only canonical v1.1.6 output may execute.")
    if args.mode == "status":
        result = base.package_status(config_path)
        result["amendment_authority_v1_1_6"] = verify_amendment_authority(
            load_execution_config(config_path)
        )
    elif args.mode == "plan":
        result = base.write_plan(config_path, output_dir)
        result["id"] = "secondary_development_execution_plan_v1_1_6"
        result["treeshap_compatibility_amendment"] = "1.1.6"
        base.atomic_write_json(output_dir / "secondary_analysis_execution_plan.json", result)
    elif args.mode == "smoke":
        result = base.synthetic_smoke(config_path, output_dir)
        result["treeshap_compatibility_amendment"] = "1.1.6"
    elif args.mode == "preflight":
        _config, _schedule, tasks, _runner, _sample, folds = base._preflight_context(
            config_path, output_dir
        )
        result = {
            "status": "PASS",
            "planned_tasks": len(tasks),
            "fold_ids": list(folds),
            "project_data_read": True,
            "project_model_fit_performed": False,
            "protected_feature_years_opened": False,
        }
    elif args.mode == "repair-treeshap":
        result = repair_treeshap(config_path, output_dir)
    elif args.mode == "robustness-classical":
        result = base.execute_classical_robustness(config_path, output_dir)
    elif args.mode == "robustness-qnn":
        result = base.execute_qnn_robustness(config_path, output_dir)
    else:
        result = create_report(config_path, output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

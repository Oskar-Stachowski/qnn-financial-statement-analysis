"""Report-integrity repair for completed secondary execution v1.1.7."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling import secondary_analysis_execution_v1_1_4 as v114
from src.modeling import secondary_analysis_execution_v1_1_6 as v116


ROOT = base.ROOT
DEFAULT_CONFIG = (
    ROOT / "configs/secondary_development_execution_v1_1_7_report_integrity_fix.yaml"
)
DEFAULT_OUTPUT = ROOT / "data/model_runs/secondary_development_v1_1_7"
SOURCE_OUTPUT = ROOT / "data/model_runs/secondary_development_v1_1_6"
EMPTY_STDERR_SHA256 = hashlib.sha256(b"").hexdigest()


def load_execution_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = yaml.safe_load(path.resolve().read_text(encoding="utf-8"))
    base._require(isinstance(payload, dict), "v1.1.7 config must be a mapping.")
    extension = payload.get("extends")
    base._require(isinstance(extension, Mapping), "v1.1.7 must extend v1.1.6.")
    base_path = (ROOT / str(extension["path"])).resolve()
    base._require(base_path == v116.DEFAULT_CONFIG.resolve(), "Wrong v1.1.7 amendment base.")
    base._require(
        base.file_sha256(base_path) == str(extension["sha256"]),
        "v1.1.6 config hash mismatch.",
    )
    inherited = v116.load_execution_config(base_path)
    merged = v114._merge(
        inherited, {key: value for key, value in payload.items() if key != "extends"}
    )
    section = merged["secondary_development_execution"]
    base._require(section["id"] == "secondary_development_execution_v1_1_7", "Wrong v1.1.7 ID.")
    base._require(section["version"] == "1.1.7", "Wrong v1.1.7 version.")
    base._require(
        section["status"] == "executable_report_integrity_amendment_frozen",
        "v1.1.7 is not frozen.",
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
        base._require(amendment[field] is False, f"Forbidden v1.1.7 change: {field}")
    return merged


def verify_amendment_authority(config: Mapping[str, Any]) -> dict[str, str]:
    authority = config["secondary_development_execution"][
        "amendment_authority_v1_1_7"
    ]
    verified: dict[str, str] = {}
    for name, item in authority.items():
        path = (ROOT / str(item["path"])).resolve()
        base._require(path.is_relative_to(ROOT), f"v1.1.7 authority escapes repository: {name}")
        base._require(path.is_file(), f"Missing v1.1.7 authority: {name}")
        actual = base.file_sha256(path)
        base._require(actual == str(item["sha256"]), f"v1.1.7 authority mismatch: {name}")
        verified[name] = actual
    return verified


def _read_json(path: Path, label: str) -> dict[str, Any]:
    base._require(path.is_file() and not path.is_symlink(), f"Missing {label}: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    base._require(isinstance(payload, dict), f"{label} must be a JSON object.")
    return payload


def _atomic_json_sha256(value: Any) -> str:
    payload = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _legacy_pre_amendment_report(report: Mapping[str, Any]) -> dict[str, Any]:
    legacy = dict(report)
    legacy["id"] = "secondary_development_results_v1_1_0"
    legacy.pop("parallel_checkpoint_amendment", None)
    legacy.pop("economic_group_permutation_amendment", None)
    legacy.pop("treeshap_compatibility_amendment", None)
    return legacy


def validate_source_execution(config: Mapping[str, Any]) -> dict[str, Any]:
    from src.modeling.verify_secondary_analysis_execution_v1_1_6 import (
        verify_secondary_analysis_execution_v1_1_6,
    )

    source = config["secondary_development_execution"]["report_source"]
    base._require(
        (ROOT / str(source["output_root"])).resolve() == SOURCE_OUTPUT.resolve(),
        "Wrong v1.1.6 report source root.",
    )
    package = verify_secondary_analysis_execution_v1_1_6(require_committed=True)
    base._require(package["status"] == "PASS", "v1.1.6 source package verification failed.")
    base._require(
        package["package_git_index_sha256"] == source["package_git_index_sha256"],
        "v1.1.6 source package identity changed.",
    )

    identity_path = SOURCE_OUTPUT / "execution_identity.json"
    preflight_path = SOURCE_OUTPUT / "preflight_manifest.json"
    source_manifest_path = SOURCE_OUTPUT / "run_manifest.json"
    source_report_path = SOURCE_OUTPUT / "secondary_development_report.json"
    for path, expected, label in (
        (identity_path, source["execution_identity_sha256"], "source execution identity"),
        (preflight_path, source["preflight_manifest_sha256"], "source preflight"),
        (source_manifest_path, source["run_manifest_sha256"], "source run manifest"),
        (source_report_path, source["report_actual_sha256"], "source report"),
    ):
        base._require(base.file_sha256(path) == expected, f"v1.1.6 {label} hash changed.")

    identity = _read_json(identity_path, "source execution identity")
    preflight = _read_json(preflight_path, "source preflight")
    source_manifest = _read_json(source_manifest_path, "source run manifest")
    source_report = _read_json(source_report_path, "source report")
    base._require(identity.get("id") == source["execution_id"], "Wrong source execution ID.")
    base._require(
        identity.get("execution_config_sha256") == source["execution_config_sha256"],
        "Wrong source execution config identity.",
    )
    base._require(
        identity.get("package_git_index_sha256") == source["package_git_index_sha256"],
        "Wrong source package identity in execution output.",
    )
    base._require(
        preflight.get("status") == "PASS"
        and preflight.get("protected_feature_years_opened") is False,
        "Source preflight is not valid.",
    )
    base._require(
        source_manifest.get("status") == "COMPLETE"
        and source_report.get("status") == "COMPLETE",
        "Source report is not complete.",
    )

    expected_phases = dict(source["phase_manifest_sha256"])
    base._require(
        source_manifest.get("phase_manifest_sha256") == expected_phases,
        "Source run manifest phase inventory changed.",
    )
    for name, expected in expected_phases.items():
        phase_path = SOURCE_OUTPUT / "phase_manifests" / name
        base._require(base.file_sha256(phase_path) == expected, f"Source phase hash changed: {name}")
        phase = _read_json(phase_path, f"source phase {name}")
        base._require(
            phase.get("status") == "COMPLETE"
            and phase.get("failed_tasks") == 0
            and phase.get("protected_feature_years_opened") is False,
            f"Source phase is not complete: {name}",
        )

    recorded = str(source_manifest.get("secondary_report_sha256"))
    actual = base.file_sha256(source_report_path)
    base._require(recorded == source["report_recorded_stale_sha256"], "Unexpected recorded source report hash.")
    base._require(actual == source["report_actual_sha256"], "Unexpected actual source report hash.")
    base._require(actual != recorded, "The pinned v1.1.6 hash defect is no longer present.")
    base._require(
        _atomic_json_sha256(_legacy_pre_amendment_report(source_report)) == recorded,
        "The stale hash is not the exact pre-amendment v1.1.0 report hash.",
    )

    schedule, tasks = base.frozen_schedule(config)
    expected_ids = {str(task["task_identity_sha256"]) for task in tasks}
    result_paths = sorted((SOURCE_OUTPUT / "task_results").glob("*.json"))
    base._require(len(tasks) == len(result_paths) == source["expected_tasks"] == 96, "Source task cardinality changed.")
    base._require({path.stem for path in result_paths} == expected_ids, "Source task roster changed.")
    inventory: list[dict[str, str]] = []
    statuses: list[str] = []
    for path in result_paths:
        result = _read_json(path, f"source task result {path.stem}")
        base._require(result.get("task_identity_sha256") == path.stem, "Source task identity mismatch.")
        base._require(result.get("status") == "COMPLETE", f"Source task is not complete: {path.stem}")
        base._require(result.get("protected_feature_years_opened") is False, "Source task opened a protected year.")
        statuses.append(str(result["status"]))
        inventory.append(
            {"task_identity_sha256": path.stem, "sha256": base.file_sha256(path)}
        )
    inventory_sha256 = base.canonical_sha256(inventory)
    base._require(
        inventory_sha256 == source["task_result_inventory_sha256"],
        "Source task-result inventory changed.",
    )
    base._require(
        statuses.count("COMPLETE") == source["expected_complete_tasks"] == 96,
        "Source complete-task count changed.",
    )
    return {
        "schedule": schedule,
        "task_count": len(tasks),
        "terminal_status_counts": {
            "COMPLETE": statuses.count("COMPLETE"),
            "METHOD_FAILED": 0,
            "RESOURCE_LIMIT_REACHED": 0,
            "TECHNICALLY_INVALID": 0,
        },
        "phase_manifest_sha256": expected_phases,
        "task_result_inventory_sha256": inventory_sha256,
        "source_execution_identity_sha256": base.file_sha256(identity_path),
        "source_preflight_manifest_sha256": base.file_sha256(preflight_path),
        "source_run_manifest_sha256": base.file_sha256(source_manifest_path),
        "source_report_actual_sha256": actual,
        "source_report_recorded_stale_sha256": recorded,
    }


def _write_report_artifacts(
    output_dir: Path, report: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    report_path = output_dir / "secondary_development_report.json"
    report_sha256 = base.atomic_write_json(report_path, dict(report))
    final_manifest = dict(manifest)
    final_manifest["secondary_report_sha256"] = report_sha256
    base.atomic_write_json(output_dir / "run_manifest.json", final_manifest)
    base._require(
        base.file_sha256(report_path) == report_sha256,
        "Final v1.1.7 report hash changed after serialization.",
    )
    return final_manifest


def create_report(config_path: Path, output_dir: Path) -> dict[str, Any]:
    base._require(output_dir.resolve() == DEFAULT_OUTPUT.resolve(), "Only canonical v1.1.7 output may execute.")
    config = load_execution_config(config_path)
    authority = verify_amendment_authority(config)
    source = config["secondary_development_execution"]["report_source"]
    validated = validate_source_execution(config)
    report = {
        "schema_version": 1,
        "id": "secondary_development_results_v1_1_7",
        "status": "COMPLETE",
        "planned_tasks": 96,
        "terminal_tasks": validated["task_count"],
        "missing_task_ids": [],
        "terminal_status_counts": validated["terminal_status_counts"],
        "task_counts": validated["schedule"]["counts"],
        "final_primary_ranking_unchanged": True,
        "may_change_primary_selection": False,
        "parallel_checkpoint_amendment": "1.1.4",
        "economic_group_permutation_amendment": "1.1.5",
        "treeshap_compatibility_amendment": "1.1.6",
        "report_integrity_amendment": "1.1.7",
        "source_execution_id": source["execution_id"],
        "source_results_changed": False,
        "source_task_result_inventory_sha256": validated[
            "task_result_inventory_sha256"
        ],
        "source_report_hash_defect_repaired": True,
        "source_report_actual_sha256": validated["source_report_actual_sha256"],
        "source_report_recorded_stale_sha256": validated[
            "source_report_recorded_stale_sha256"
        ],
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }
    manifest = {
        "schema_version": 1,
        "id": "secondary_development_execution_v1_1_7",
        "status": "COMPLETE",
        "authority": authority,
        "source_execution_id": source["execution_id"],
        "source_execution_identity_sha256": validated[
            "source_execution_identity_sha256"
        ],
        "source_preflight_manifest_sha256": validated[
            "source_preflight_manifest_sha256"
        ],
        "source_run_manifest_sha256": validated["source_run_manifest_sha256"],
        "source_phase_manifest_sha256": validated["phase_manifest_sha256"],
        "source_task_result_inventory_sha256": validated[
            "task_result_inventory_sha256"
        ],
        "report_integrity_amendment": "1.1.7",
        "source_output_mutated": False,
        "source_results_copied": False,
        "source_results_changed": False,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "final_primary_ranking_unchanged": True,
        "protected_feature_years_opened": False,
    }
    final_manifest = _write_report_artifacts(output_dir, report, manifest)
    verify_generated_report(output_dir)
    return final_manifest


def verify_generated_report(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    manifest_path = output_dir / "run_manifest.json"
    report_path = output_dir / "secondary_development_report.json"
    manifest = _read_json(manifest_path, "v1.1.7 run manifest")
    report = _read_json(report_path, "v1.1.7 report")
    actual_report_sha256 = base.file_sha256(report_path)
    base._require(manifest.get("status") == "COMPLETE", "v1.1.7 run manifest is incomplete.")
    base._require(report.get("status") == "COMPLETE", "v1.1.7 report is incomplete.")
    base._require(
        manifest.get("secondary_report_sha256") == actual_report_sha256,
        "v1.1.7 report SHA-256 does not match the final serialized report.",
    )
    base._require(report.get("terminal_tasks") == report.get("planned_tasks") == 96, "v1.1.7 task accounting changed.")
    base._require(report.get("missing_task_ids") == [], "v1.1.7 report has missing tasks.")
    base._require(
        report.get("terminal_status_counts", {}).get("COMPLETE") == 96,
        "v1.1.7 report does not contain 96 complete tasks.",
    )
    for payload in (manifest, report):
        base._require(payload.get("source_results_changed") is False, "v1.1.7 changed source results.")
        base._require(payload.get("project_model_fit_performed") is False, "v1.1.7 performed a model fit.")
        base._require(payload.get("protected_feature_years_opened") is False, "v1.1.7 opened a protected year.")
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": "SECONDARY_DEVELOPMENT_REPORT_V1_1_7_INTEGRITY_PASS",
        "secondary_report_sha256": actual_report_sha256,
        "terminal_tasks": 96,
        "source_results_changed": False,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def package_status(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = load_execution_config(config_path)
    authority = verify_amendment_authority(config)
    schedule, tasks = base.frozen_schedule(config)
    return {
        "schema_version": 1,
        "status": "PASS",
        "id": "secondary_development_execution_v1_1_7",
        "package_state": "executable_report_integrity_amendment_frozen",
        "verified_amendment_authorities": len(authority),
        "planned_tasks": len(tasks),
        "task_counts": schedule["counts"],
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("status", "report", "verify-report"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config_path = args.config.resolve()
    output_dir = (
        args.output_dir.resolve() if args.output_dir is not None else DEFAULT_OUTPUT.resolve()
    )
    base._require(config_path == DEFAULT_CONFIG.resolve(), "Only canonical v1.1.7 config may execute.")
    base._require(output_dir == DEFAULT_OUTPUT.resolve(), "Only canonical v1.1.7 output may execute.")
    if args.mode == "status":
        result = package_status(config_path)
    elif args.mode == "report":
        result = create_report(config_path, output_dir)
    else:
        result = verify_generated_report(output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

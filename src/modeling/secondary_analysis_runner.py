"""Plan the frozen secondary development analyses without reading project rows.

The v1.0.0 package deliberately exposes planning, status, and synthetic-smoke
modes only.  Project-data reads and project model fits remain fail-closed until
an explicit post-freeze execution command is added in a later committed version.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

import yaml

from src.modeling.secondary_analysis_schemas import (
    DEFAULT_CONFIG,
    ROOT,
    SecondaryAnalysisIntegrityError,
    canonical_sha256,
    file_sha256,
    load_config,
    require,
    validate_config,
    validate_plan,
    verify_authority,
)
from src.modeling.verify_post_coarse_results_freeze import (
    verify_post_coarse_results_freeze,
)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), f"Expected a JSON object: {path}")
    return payload


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> str:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    with temporary.open("xb") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return file_sha256(path)


def _authority_path(config: Mapping[str, Any], name: str) -> Path:
    item = config["secondary_development_analyses"]["authority"][name]
    return (ROOT / str(item["path"])).resolve()


def _compact_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rank": int(row["rank"]),
        "family": str(row["family"]),
        "stage": str(row["stage"]),
        "feature_block": str(row["feature_block"]),
        "configuration_id": str(row["configuration_id"]),
        "training_seed": row["training_seed"],
        "status": str(row["status"]),
        "parameters": dict(row.get("parameters") or {}),
    }


def _load_frozen_representatives(
    config: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    ranking = load_json(_authority_path(config, "final_primary_ranking"))
    qnn_phase = load_json(_authority_path(config, "qnn_phase"))
    require(ranking.get("status") == "COMPLETE", "Final ranking is not COMPLETE.")
    require(ranking.get("protected_feature_years_opened") is False, "Ranking opened protected years.")
    require(qnn_phase.get("status") == "COMPLETE", "QNN phase is not COMPLETE.")
    require(qnn_phase.get("protected_feature_years_opened") is False, "QNN phase opened protected years.")

    representatives: dict[str, dict[str, Any]] = {}
    ordered = sorted(
        ranking.get("family_representatives") or [], key=lambda row: int(row["rank"])
    )
    for row in ordered:
        identity = _compact_identity(row)
        require(identity["status"] == "COMPLETE", f"Incomplete representative: {identity['family']}")
        require(identity["family"] not in representatives, "Duplicate family representative.")
        representatives[identity["family"]] = identity

    expected_families = {
        "dummy_prior",
        "fixed_l2_logistic",
        "elastic_net_logistic",
        "rbf_svm",
        "random_forest",
        "hist_gradient_boosting",
        "xgboost",
        "pytorch_mlp",
        "qnn",
    }
    require(set(representatives) == expected_families, "Final family roster changed.")
    require(ordered[0]["family"] == "xgboost", "Frozen global winner is not XGBoost.")
    selection = dict(qnn_phase.get("ansatz_selection") or {})
    require(selection.get("status") == "SELECTED", "No frozen QNN ansatz.")
    require(selection.get("selected_ansatz_id") == "ROT_CNOT_RING", "QNN ansatz changed.")
    return representatives, selection


def _validate_contract_alignment(config: Mapping[str, Any]) -> None:
    section = config["secondary_development_analyses"]
    contract = yaml.safe_load(
        _authority_path(config, "execution_contract_base").read_text(encoding="utf-8")
    )
    frozen_i = contract["interpretability_execution_scope"]
    planned_i = section["interpretability"]
    require(
        planned_i["common_grouped_permutation"]["repetitions"]
        == frozen_i["common_grouped_permutation"]["repetitions"],
        "Permutation repetitions differ from contract.",
    )
    require(
        planned_i["common_grouped_permutation"]["permutation_seed"]
        == frozen_i["common_grouped_permutation"]["permutation_seed"],
        "Permutation seed differs from contract.",
    )
    require(
        planned_i["detailed_representatives"] == frozen_i["detailed_representatives"],
        "Detailed representative rules differ from contract.",
    )
    require(
        planned_i["detailed_methods"] == frozen_i["detailed_methods"],
        "Detailed methods differ from contract.",
    )
    require(
        planned_i["sampling_limits"] == frozen_i["required_sampling_limits"],
        "Sampling limits differ from contract.",
    )

    frozen_r = contract["robustness_execution_scope"]
    planned_r = section["robustness"]
    require(
        planned_r["pipeline_runs_ordered"]
        == frozen_r["global_winner_mandatory_pipeline_runs"],
        "Pipeline robustness differs from contract.",
    )
    require(
        planned_r["label_runs_ordered"]
        == frozen_r["global_winner_mandatory_label_runs"],
        "Label robustness differs from contract.",
    )
    require(
        planned_r["qnn_structural_runs_ordered"]
        == frozen_r["qnn_structural_runs_if_qnn_feasible"],
        "QNN structural robustness differs from contract.",
    )
    require(frozen_r["retuning_allowed"] is False, "Contract permits retuning.")


def _task(stage: str, analysis_id: str, **identity: Any) -> dict[str, Any]:
    task_identity = {"stage": stage, "analysis_id": analysis_id, **identity}
    return {
        "task_identity": task_identity,
        "task_identity_sha256": canonical_sha256(task_identity),
        "status": "PLANNED",
    }


def _build_tasks(
    section: Mapping[str, Any],
    representatives: Mapping[str, Mapping[str, Any]],
    selection: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    tasks: list[dict[str, Any]] = []
    pca = section["pca_matched_controls"]
    qnn = representatives["qnn"]
    for control in pca["controls_ordered"]:
        source_family = str(control["family"])
        source = representatives[source_family]
        for fold_id in pca["required_folds"]:
            tasks.append(
                _task(
                    "pca_matched_controls",
                    str(control["id"]),
                    family=source_family,
                    source_configuration_id=source["configuration_id"],
                    qnn_configuration_id=qnn["configuration_id"],
                    qnn_feature_block=qnn["feature_block"],
                    qnn_qubits=int(qnn["parameters"]["qubits_pca"]),
                    training_seed=int(pca["training_seed"]),
                    fold_id=str(fold_id),
                )
            )

    common = section["interpretability"]["common_grouped_permutation"]
    common_families: list[str] = []
    for item in common["families_ordered"]:
        family = "qnn" if item == "qnn_if_technically_feasible" else str(item)
        common_families.append(family)
        source = representatives[family]
        tasks.append(
            _task(
                "interpretability",
                "common_grouped_permutation",
                family=family,
                source_configuration_id=source["configuration_id"],
                feature_block=source["feature_block"],
                repetitions=int(common["repetitions"]),
                permutation_seed=int(common["permutation_seed"]),
            )
        )

    ranked_linear = [
        representatives[name]
        for name in ("fixed_l2_logistic", "elastic_net_logistic")
    ]
    linear = min(ranked_linear, key=lambda item: int(item["rank"]))
    detailed = {
        "linear": linear,
        "tree_boosting": representatives["xgboost"],
        "mlp": representatives["pytorch_mlp"],
        "qnn": qnn,
    }
    methods = section["interpretability"]["detailed_methods"]
    for role, source in detailed.items():
        tasks.append(
            _task(
                "interpretability",
                str(methods[role]),
                representative_role=role,
                family=source["family"],
                source_configuration_id=source["configuration_id"],
                feature_block=source["feature_block"],
            )
        )

    robustness = section["robustness"]
    winner = representatives["xgboost"]
    for variant in [
        *robustness["pipeline_runs_ordered"],
        *robustness["label_runs_ordered"],
    ]:
        for fold_id in robustness["required_folds"]:
            tasks.append(
                _task(
                    "robustness",
                    str(variant),
                    family=winner["family"],
                    source_configuration_id=winner["configuration_id"],
                    feature_block=winner["feature_block"],
                    training_seed=int(robustness["training_seed"]),
                    fold_id=str(fold_id),
                )
            )
    for variant in robustness["qnn_structural_runs_ordered"]:
        for fold_id in robustness["required_folds"]:
            tasks.append(
                _task(
                    "robustness",
                    str(variant),
                    family="qnn",
                    source_configuration_id=qnn["configuration_id"],
                    feature_block=qnn["feature_block"],
                    selected_ansatz_id=str(selection["selected_ansatz_id"]),
                    training_seed=int(robustness["training_seed"]),
                    fold_id=str(fold_id),
                )
            )

    counts = {
        "pca_matched_control_fold_fits": len(pca["controls_ordered"]) * len(pca["required_folds"]),
        "common_grouped_permutation_methods": len(common_families),
        "detailed_interpretability_methods": len(detailed),
        "global_winner_robustness_fold_fits": (
            len(robustness["pipeline_runs_ordered"])
            + len(robustness["label_runs_ordered"])
        )
        * len(robustness["required_folds"]),
        "qnn_structural_robustness_fold_fits": len(robustness["qnn_structural_runs_ordered"])
        * len(robustness["required_folds"]),
        "total_planned_tasks": len(tasks),
    }
    require(counts["pca_matched_control_fold_fits"] == 12, "PCA task count mismatch.")
    require(counts["global_winner_robustness_fold_fits"] == 48, "Winner task count mismatch.")
    require(counts["qnn_structural_robustness_fold_fits"] == 24, "QNN task count mismatch.")
    require(counts["total_planned_tasks"] == 96, "Total task count mismatch.")
    return tasks, counts


def create_plan(config_path: Path, output_dir: Path) -> dict[str, Any]:
    config = load_config(config_path)
    counts = validate_config(config)
    authority = verify_authority(config)
    _validate_contract_alignment(config)
    freeze = verify_post_coarse_results_freeze(
        _authority_path(config, "post_coarse_results_freeze")
    )
    require(freeze["status"] == "PASS", "Post-coarse result freeze failed.")
    representatives, selection = _load_frozen_representatives(config)
    section = config["secondary_development_analyses"]
    tasks, task_counts = _build_tasks(section, representatives, selection)
    require(task_counts["pca_matched_control_fold_fits"] == counts["pca_matched_control_fold_fits"], "PCA derived count mismatch.")
    require(task_counts["global_winner_robustness_fold_fits"] == counts["global_winner_robustness_fold_fits"], "Winner derived count mismatch.")
    require(task_counts["qnn_structural_robustness_fold_fits"] == counts["qnn_structural_fold_fits"], "QNN derived count mismatch.")

    plan = {
        "schema_version": 1,
        "id": "secondary_development_analysis_plan_v1_0_0",
        "status": "PLAN_ONLY_NO_PROJECT_DATA_ACCESS",
        "authority": {
            "secondary_config_path": str(config_path.relative_to(ROOT)),
            "secondary_config_sha256": file_sha256(config_path),
            "verified_authority_sha256": authority,
            "post_coarse_freeze_verdict": freeze["verdict"],
        },
        "frozen_representatives": {
            family: dict(identity) for family, identity in representatives.items()
        },
        "selected_qnn_ansatz_id": selection["selected_ansatz_id"],
        "stages": list(section["stage_order"]),
        "task_counts": task_counts,
        "tasks": tasks,
        "result_magnitudes_used_for_schedule": False,
        "protected_feature_years_opened": False,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "project_execution_available_in_this_package": False,
    }
    validate_plan(plan, config)
    output_path = output_dir / section["output_schemas"]["plan"]["path"]
    if output_path.is_file():
        existing = load_json(output_path)
        require(existing == plan, f"Existing plan differs: {output_path}")
    else:
        atomic_write_json(output_path, plan)
    return plan


def package_status(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    counts = validate_config(config)
    authority = verify_authority(config)
    _validate_contract_alignment(config)
    return {
        "status": "PASS",
        "id": config["secondary_development_analyses"]["id"],
        "verified_authority_files": len(authority),
        "planned_fit_counts": counts,
        "project_data_read": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("status", "plan"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/model_runs/secondary_development_v1_0_0")
    args = parser.parse_args()
    config_path = args.config.resolve()
    require(config_path.is_relative_to(ROOT), "Config must be inside the repository.")
    if args.mode == "status":
        result = package_status(config_path)
    else:
        result = create_plan(config_path, args.output_dir.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

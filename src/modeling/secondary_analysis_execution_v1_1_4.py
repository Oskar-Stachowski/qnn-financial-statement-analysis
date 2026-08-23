"""Parallel-fold and checkpoint-source amendment for secondary execution v1.1.4.

This operational layer preserves the frozen 96-task roster and every scientific
identity.  It resolves seed-20260818 neural checkpoints from their immutable
origin directories and executes independent folds concurrently within the
already frozen classical/MLP/QNN limits.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TypeVar

import numpy as np
import yaml

from src.modeling import secondary_analysis_execution as base
from src.modeling import secondary_analysis_execution_v1_1_3 as v113


ROOT = base.ROOT
DEFAULT_CONFIG = (
    ROOT / "configs/secondary_development_execution_v1_1_4_parallel_checkpoint_fix.yaml"
)
DEFAULT_OUTPUT = ROOT / "data/model_runs/secondary_development_v1_1_4"
_BASE_PREFLIGHT_CONTEXT = v113._BASE_PREFLIGHT_CONTEXT

T = TypeVar("T")
R = TypeVar("R")


def _merge(base_value: Any, overlay_value: Any) -> Any:
    if isinstance(base_value, Mapping) and isinstance(overlay_value, Mapping):
        result = dict(base_value)
        for key, value in overlay_value.items():
            result[key] = _merge(result.get(key), value)
        return result
    return overlay_value


def load_execution_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    payload = yaml.safe_load(path.resolve().read_text(encoding="utf-8"))
    base._require(isinstance(payload, dict), "v1.1.4 config must be a mapping.")
    extension = payload.get("extends")
    base._require(isinstance(extension, Mapping), "v1.1.4 must extend v1.1.3.")
    base_path = (ROOT / str(extension["path"])).resolve()
    expected = ROOT / "configs/secondary_development_execution_v1_1_3_signal_source_fix.yaml"
    base._require(base_path == expected, "Wrong v1.1.4 amendment base.")
    base._require(
        base.file_sha256(base_path) == str(extension["sha256"]),
        "v1.1.3 config hash mismatch.",
    )
    inherited = v113.load_execution_config(base_path)
    merged = _merge(
        inherited, {key: value for key, value in payload.items() if key != "extends"}
    )
    section = merged["secondary_development_execution"]
    base._require(section["id"] == "secondary_development_execution_v1_1_4", "Wrong v1.1.4 ID.")
    base._require(section["version"] == "1.1.4", "Wrong v1.1.4 version.")
    base._require(
        section["status"] == "executable_parallel_checkpoint_amendment_frozen",
        "v1.1.4 is not frozen.",
    )
    amendment = section["parallel_checkpoint_amendment"]
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
        base._require(amendment[field] is False, f"Forbidden v1.1.4 change: {field}")
    parallel = section["parallel_execution"]
    inherited_resources = section["resources"]
    for family in ("classical", "mlp", "qnn"):
        key = f"maximum_parallel_{family}_folds"
        base._require(int(parallel[key]) == int(inherited_resources[key]), f"v1.1.4 changed {key}.")
    base._require(parallel["ordered_map"] is True, "v1.1.4 ordered map disabled.")
    base._require(
        amendment["parallel_across_analysis_variants"] is False,
        "v1.1.4 may not parallelize across analysis variants.",
    )
    return merged


def verify_amendment_authority(config: Mapping[str, Any]) -> dict[str, str]:
    authority = config["secondary_development_execution"]["amendment_authority_v1_1_4"]
    verified: dict[str, str] = {}
    for name, item in authority.items():
        path = (ROOT / str(item["path"])).resolve()
        base._require(path.is_relative_to(ROOT), f"v1.1.4 authority escapes repository: {name}")
        base._require(path.is_file(), f"Missing v1.1.4 authority: {name}")
        actual = base.file_sha256(path)
        base._require(actual == str(item["sha256"]), f"v1.1.4 authority mismatch: {name}")
        verified[name] = actual
    return verified


def _parallel_limit(config: Mapping[str, Any], family: str) -> int:
    role = "qnn" if family == "qnn" else "mlp" if family == "pytorch_mlp" else "classical"
    value = int(
        config["secondary_development_execution"]["parallel_execution"][
            f"maximum_parallel_{role}_folds"
        ]
    )
    base._require(1 <= value <= 4, f"Unsafe v1.1.4 parallel limit: {role}")
    return value


def ordered_parallel_map(
    items: Sequence[T], function: Callable[[T], R], *, maximum_workers: int
) -> list[R]:
    """Run independent work concurrently and return exact input order."""
    base._require(maximum_workers >= 1, "Parallel worker limit must be positive.")
    if len(items) <= 1 or maximum_workers == 1:
        return [function(item) for item in items]
    with ThreadPoolExecutor(
        max_workers=min(maximum_workers, len(items)),
        thread_name_prefix="secondary-fold",
    ) as pool:
        return list(pool.map(function, items))


def checkpoint_fold_directory(
    representative: Mapping[str, Any],
    seed: int,
    fold_id: str,
    config: Mapping[str, Any],
) -> Path:
    section = config["secondary_development_execution"]
    policy = section["interpretation_checkpoint_sources"]
    family = str(representative["family"])
    base._require(family in set(policy["expected_families"]), "Unsupported checkpoint family.")
    base._require(fold_id in set(policy["expected_folds"]), "Unexpected checkpoint fold.")
    if int(seed) == int(policy["base_seed"]):
        rule_name = "qnn_base_seed" if family == "qnn" else "pytorch_mlp_base_seed"
        rule = policy[rule_name]
        root = base._resolve(str(rule["root"]))
        stage = str(rule["stage"])
        source_family = str(rule["family"])
        configuration_id = str(rule["configuration_id"])
    else:
        base._require(int(seed) in set(policy["confirmation_seeds"]), "Unexpected checkpoint seed.")
        root = base._resolve(str(policy["frozen_post_coarse_root"]))
        stage = str(representative["stage"])
        source_family = family
        configuration_id = str(representative["configuration_id"])
    base._require(source_family == family, "Checkpoint family substitution is forbidden.")
    directory = (
        root
        / stage
        / source_family
        / configuration_id
        / str(representative["feature_block"]).replace("+", "_")
        / f"seed_{int(seed)}"
        / fold_id
    ).resolve()
    base._require(directory.is_relative_to(ROOT), "Checkpoint directory escapes repository.")
    return directory


def _validated_checkpoint_entry(
    representative: Mapping[str, Any],
    seed: int,
    fold_id: str,
    config: Mapping[str, Any],
    *,
    include_file_hashes: bool,
) -> dict[str, Any]:
    directory = checkpoint_fold_directory(representative, seed, fold_id, config)
    manifest_path = directory / "result_manifest.json"
    checkpoint_path = directory / "checkpoint.pt"
    base._require(manifest_path.is_file(), f"Missing exact checkpoint manifest: {directory}")
    base._require(checkpoint_path.is_file(), f"Missing exact checkpoint: {directory}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    base._require(manifest.get("status") == "COMPLETE", f"Incomplete checkpoint source: {directory}")
    identity = manifest.get("task_identity") or {}
    base._require(identity.get("family") == representative["family"], "Checkpoint family mismatch.")
    base._require(identity.get("feature_block") == representative["feature_block"], "Checkpoint block mismatch.")
    base._require(identity.get("fold_id") == fold_id, "Checkpoint fold mismatch.")
    base._require(int(identity.get("training_seed", -1)) == int(seed), "Checkpoint seed mismatch.")
    task_sha = str(manifest.get("task_identity_sha256") or "")
    base._require(bool(task_sha), "Checkpoint task identity is absent.")
    if representative["family"] == "qnn":
        base._require(identity.get("selected_ansatz_id") == "ROT_CNOT_RING", "QNN ansatz mismatch.")
    entry = {
        "family": str(representative["family"]),
        "seed": int(seed),
        "fold_id": fold_id,
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "checkpoint_path": str(checkpoint_path.relative_to(ROOT)),
        "checkpoint_task_identity_sha256": task_sha,
    }
    if include_file_hashes:
        entry["manifest_sha256"] = base.file_sha256(manifest_path)
        entry["checkpoint_sha256"] = base.file_sha256(checkpoint_path)
    return entry


def _verify_qnn_base_reuse_marker(
    representative: Mapping[str, Any], fold_id: str, config: Mapping[str, Any]
) -> None:
    policy = config["secondary_development_execution"]["interpretation_checkpoint_sources"]
    rule = policy["qnn_base_seed"]
    marker = (
        base._resolve(str(policy["frozen_post_coarse_root"]))
        / "qnn_q2"
        / "qnn"
        / str(rule["q2_reuse_configuration_id"])
        / str(representative["feature_block"]).replace("+", "_")
        / f"seed_{int(policy['base_seed'])}"
        / fold_id
        / "result_manifest.json"
    )
    base._require(marker.is_file(), f"Missing Q2 reuse marker: {marker}")
    payload = json.loads(marker.read_text(encoding="utf-8"))
    base._require(payload.get("status") == "COMPLETE", "Q2 reuse marker is incomplete.")
    base._require(payload.get("source_status") == "COMPLETE", "Q2 source is incomplete.")
    base._require(
        payload.get("source_configuration_id") == rule["configuration_id"],
        "Q2 reuse marker points to a different Q1 configuration.",
    )


def source_checkpoints(
    representative: Mapping[str, Any], seeds: Sequence[int], fold_id: str
) -> tuple[list[str], list[str]]:
    config = load_execution_config(DEFAULT_CONFIG)
    paths: list[str] = []
    identities: list[str] = []
    for seed in seeds:
        entry = _validated_checkpoint_entry(
            representative, int(seed), fold_id, config, include_file_hashes=False
        )
        if representative["family"] == "qnn" and int(seed) == int(
            config["secondary_development_execution"]["interpretation_checkpoint_sources"]["base_seed"]
        ):
            _verify_qnn_base_reuse_marker(representative, fold_id, config)
        paths.append(str(ROOT / entry["checkpoint_path"]))
        identities.append(str(entry["checkpoint_task_identity_sha256"]))
    return paths, identities


def verify_checkpoint_inventory(
    config: Mapping[str, Any], schedule: Mapping[str, Any]
) -> dict[str, Any]:
    section = config["secondary_development_execution"]
    policy = section["interpretation_checkpoint_sources"]
    seeds = [int(policy["base_seed"]), *map(int, policy["confirmation_seeds"])]
    entries: list[dict[str, Any]] = []
    for family in policy["expected_families"]:
        representative = schedule["representatives"][str(family)]
        for seed in seeds:
            for fold_id in policy["expected_folds"]:
                entry = _validated_checkpoint_entry(
                    representative,
                    seed,
                    str(fold_id),
                    config,
                    include_file_hashes=True,
                )
                if family == "qnn" and seed == int(policy["base_seed"]):
                    _verify_qnn_base_reuse_marker(representative, str(fold_id), config)
                entries.append(entry)
    base._require(len(entries) == int(policy["expected_checkpoint_count"]), "Checkpoint inventory count mismatch.")
    base._require(
        len({entry["checkpoint_path"] for entry in entries}) == len(entries),
        "Checkpoint inventory contains duplicate paths.",
    )
    return {
        "checkpoint_count": len(entries),
        "families": list(policy["expected_families"]),
        "seeds": seeds,
        "folds": list(policy["expected_folds"]),
        "inventory_sha256": base.canonical_sha256(entries),
        "entries": entries,
    }


def _output_identity(config_path: Path, git_index_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": "secondary_development_execution_v1_1_4",
        "execution_config_sha256": base.file_sha256(config_path),
        "base_execution_config_sha256": base.file_sha256(
            ROOT / "configs/secondary_development_execution_v1_1_0.yaml"
        ),
        "frozen_schedule_sha256": base.file_sha256(
            ROOT / "configs/secondary_development_analyses_v1_0_0.yaml"
        ),
        "package_git_index_sha256": git_index_sha256,
        "protected_feature_years_opened": False,
    }


def _patched_preflight_context(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> Any:
    config = load_execution_config(config_path)
    verify_amendment_authority(config)
    if not synthetic:
        from src.modeling.verify_secondary_analysis_execution_v1_1_4 import (
            verify_secondary_analysis_execution_v1_1_4,
        )

        report = verify_secondary_analysis_execution_v1_1_4()
        base._require(report["status"] == "PASS", "v1.1.4 package verification failed.")
    context = _BASE_PREFLIGHT_CONTEXT(config_path, output_dir, synthetic=synthetic)
    if not synthetic:
        _config, schedule, _tasks, _runner, _sample, _folds = context
        inventory = verify_checkpoint_inventory(config, schedule)
        preflight_path = output_dir / "preflight_manifest.json"
        audit = json.loads(preflight_path.read_text(encoding="utf-8"))
        audit.update(
            {
                "parallel_checkpoint_amendment_version": "1.1.4",
                "interpretation_checkpoint_count": inventory["checkpoint_count"],
                "interpretation_checkpoint_inventory_sha256": inventory["inventory_sha256"],
                "parallel_execution": config["secondary_development_execution"]["parallel_execution"],
            }
        )
        base.atomic_write_json(preflight_path, audit)
    return context


def _group_in_frozen_order(
    tasks: Sequence[Mapping[str, Any]], key: Callable[[Mapping[str, Any]], str]
) -> list[list[Mapping[str, Any]]]:
    groups: list[list[Mapping[str, Any]]] = []
    names: list[str] = []
    for task in tasks:
        name = key(task)
        if name not in names:
            names.append(name)
            groups.append([])
        groups[names.index(name)].append(task)
    return groups


def execute_pca_controls(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> dict[str, Any]:
    config, schedule, tasks, runner, _sample, folds = base._preflight_context(
        config_path, output_dir, synthetic=synthetic
    )
    selected = [task for task in tasks if task["task_identity"]["stage"] == "pca_matched_controls"]
    representatives = schedule["representatives"]
    qnn = representatives["qnn"]
    results_by_id: dict[str, dict[str, Any]] = {}

    def run_task(task: Mapping[str, Any]) -> dict[str, Any]:
        identity = task["task_identity"]
        prepared = runner._prepare_fold(
            block=qnn["feature_block"],
            fold_tuple=folds[identity["fold_id"]],
            qubits=int(qnn["parameters"]["qubits_pca"]),
        )
        source = representatives[identity["family"]]
        return base._execute_prepared_model_task(
            output_dir=output_dir,
            runner=runner,
            plan_task=task,
            prepared=prepared,
            parameters=source["parameters"],
            family=identity["family"],
            source_configuration_id=source["configuration_id"],
            training_seed=int(identity["training_seed"]),
            y_train=prepared.train["target_label"].to_numpy(dtype=np.int64),
            y_validation=prepared.validation["target_label"].to_numpy(dtype=np.int64),
            selected_ansatz_id=None,
        )

    for group in _group_in_frozen_order(selected, lambda task: str(task["task_identity"]["family"])):
        family = str(group[0]["task_identity"]["family"])
        outputs = ordered_parallel_map(group, run_task, maximum_workers=_parallel_limit(config, family))
        results_by_id.update(zip((task["task_identity_sha256"] for task in group), outputs, strict=True))
    results = [results_by_id[task["task_identity_sha256"]] for task in selected]
    return base._phase_manifest(output_dir, "pca_matched_controls", selected, results)


def execute_interpretability(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> dict[str, Any]:
    if not synthetic:
        base._require_terminal_phase(output_dir, "pca_matched_controls")
    config, schedule, tasks, runner, _sample, folds = base._preflight_context(
        config_path, output_dir, synthetic=synthetic
    )
    selected = [task for task in tasks if task["task_identity"]["stage"] == "interpretability"]
    representatives = schedule["representatives"]
    results: list[dict[str, Any]] = []
    fold_ids = list(folds)
    for plan_task in selected:
        existing = base._existing_task_result(output_dir, plan_task)
        if existing is not None:
            results.append(existing)
            continue
        identity = plan_task["task_identity"]
        representative = representatives[str(identity["family"])]

        def run_fold(fold_id: str) -> dict[str, Any]:
            try:
                return base._run_interpretation_fold(
                    output_dir=output_dir,
                    runner=runner,
                    plan_task=plan_task,
                    representative=representative,
                    fold_id=fold_id,
                    folds=folds,
                    config=config,
                )
            except Exception as error:
                return {
                    "status": "EXCEPTION_INVALID",
                    "failure_code": type(error).__name__,
                    "fold_id": fold_id,
                }

        fold_results = ordered_parallel_map(
            fold_ids,
            run_fold,
            maximum_workers=_parallel_limit(config, str(identity["family"])),
        )
        complete = all(result.get("status") == "COMPLETE" for result in fold_results)
        result = {
            "schema_version": 1,
            "task_identity": identity,
            "task_identity_sha256": plan_task["task_identity_sha256"],
            "status": "COMPLETE" if complete else "METHOD_FAILED",
            "failure_code": None if complete else "INTERPRETATION_FOLD_FAILED",
            "source_authority_sha256": base.file_sha256(config_path),
            "fold_results": fold_results,
            "project_data_read": not synthetic,
            "project_model_fit_performed": base.family_requires_refit(str(identity["family"])),
            "protected_feature_years_opened": False,
            "may_change_primary_selection": False,
        }
        base.atomic_write_json(base._task_result_path(output_dir, plan_task), result)
        results.append(result)
    return base._phase_manifest(output_dir, "interpretability", selected, results)


def execute_classical_robustness(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> dict[str, Any]:
    if not synthetic:
        base._require_terminal_phase(output_dir, "interpretability")
    config, schedule, tasks, runner, _sample, folds = base._preflight_context(
        config_path, output_dir, synthetic=synthetic
    )
    selected = [
        task
        for task in tasks
        if task["task_identity"]["stage"] == "robustness"
        and task["task_identity"]["family"] == "xgboost"
    ]
    winner = schedule["representatives"]["xgboost"]
    pipeline_variants = {
        "B_without_missing_indicators",
        "complete_case",
        "no_winsorization",
        "purged_economic_group_cv",
        "sparse_row_available_features_at_least_11_of_17",
    }
    results_by_id: dict[str, dict[str, Any]] = {}

    def run_task(task: Mapping[str, Any]) -> dict[str, Any]:
        identity = task["task_identity"]
        variant = identity["analysis_id"]
        fold_id = identity["fold_id"]
        if variant in pipeline_variants:
            prepared = base._custom_prepared_fold(
                runner=runner,
                output_dir=output_dir,
                fold_tuple=folds[fold_id],
                block=winner["feature_block"],
                variant=variant,
            )
            label_column = "target_label"
        else:
            prepared = runner._prepare_fold(
                block=winner["feature_block"], fold_tuple=folds[fold_id]
            )
            label_column = f"target__{variant}"
        return base._execute_prepared_model_task(
            output_dir=output_dir,
            runner=runner,
            plan_task=task,
            prepared=prepared,
            parameters=winner["parameters"],
            family="xgboost",
            source_configuration_id=winner["configuration_id"],
            training_seed=int(identity["training_seed"]),
            y_train=prepared.train[label_column].to_numpy(dtype=np.int64),
            y_validation=prepared.validation[label_column].to_numpy(dtype=np.int64),
            selected_ansatz_id=None,
        )

    groups = _group_in_frozen_order(selected, lambda task: str(task["task_identity"]["analysis_id"]))
    for group in groups:
        outputs = ordered_parallel_map(
            group, run_task, maximum_workers=_parallel_limit(config, "xgboost")
        )
        results_by_id.update(zip((task["task_identity_sha256"] for task in group), outputs, strict=True))
    results = [results_by_id[task["task_identity_sha256"]] for task in selected]
    return base._phase_manifest(output_dir, "robustness_classical", selected, results)


def execute_qnn_robustness(
    config_path: Path, output_dir: Path, *, synthetic: bool = False
) -> dict[str, Any]:
    if not synthetic:
        base._require_terminal_phase(output_dir, "robustness_classical")
    config, schedule, tasks, runner, _sample, folds = base._preflight_context(
        config_path, output_dir, synthetic=synthetic
    )
    selected = [
        task
        for task in tasks
        if task["task_identity"]["stage"] == "robustness"
        and task["task_identity"]["family"] == "qnn"
    ]
    qnn = schedule["representatives"]["qnn"]
    variants = config["secondary_development_execution"]["qnn_structural_variants"]
    results_by_id: dict[str, dict[str, Any]] = {}

    def run_task(task: Mapping[str, Any]) -> dict[str, Any]:
        identity = task["task_identity"]
        variant = identity["analysis_id"]
        parameters = dict(qnn["parameters"])
        ansatz = str(identity["selected_ansatz_id"])
        qubits = int(parameters["qubits_pca"])
        if variant == "swap_4_and_6_qubit_PCA_at_fixed_other_settings":
            qubits = int(variants[variant]["qubit_mapping"][qubits])
            parameters["qubits_pca"] = qubits
        else:
            ansatz = str(variants[variant]["executable_ansatz_id"])
        prepared = runner._prepare_fold(
            block=qnn["feature_block"],
            fold_tuple=folds[identity["fold_id"]],
            qubits=qubits,
        )
        return base._execute_prepared_model_task(
            output_dir=output_dir,
            runner=runner,
            plan_task=task,
            prepared=prepared,
            parameters=parameters,
            family="qnn",
            source_configuration_id=qnn["configuration_id"],
            training_seed=int(identity["training_seed"]),
            y_train=prepared.train["target_label"].to_numpy(dtype=np.int64),
            y_validation=prepared.validation["target_label"].to_numpy(dtype=np.int64),
            selected_ansatz_id=ansatz,
        )

    groups = _group_in_frozen_order(selected, lambda task: str(task["task_identity"]["analysis_id"]))
    for group in groups:
        outputs = ordered_parallel_map(
            group, run_task, maximum_workers=_parallel_limit(config, "qnn")
        )
        results_by_id.update(zip((task["task_identity_sha256"] for task in group), outputs, strict=True))
    results = [results_by_id[task["task_identity_sha256"]] for task in selected]
    return base._phase_manifest(output_dir, "robustness_qnn", selected, results)


def activate_amendment() -> None:
    v113.activate_amendment()
    base.DEFAULT_CONFIG = DEFAULT_CONFIG
    base.load_execution_config = load_execution_config
    base._output_identity = _output_identity
    base._preflight_context = _patched_preflight_context
    base._source_checkpoints = source_checkpoints
    base.execute_pca_controls = execute_pca_controls
    base.execute_interpretability = execute_interpretability
    base.execute_classical_robustness = execute_classical_robustness
    base.execute_qnn_robustness = execute_qnn_robustness


@contextmanager
def _isolated_activation() -> Any:
    names = (
        "DEFAULT_CONFIG",
        "load_execution_config",
        "_load_project_sample_and_robustness",
        "_output_identity",
        "_preflight_context",
        "_source_checkpoints",
        "execute_pca_controls",
        "execute_interpretability",
        "execute_classical_robustness",
        "execute_qnn_robustness",
    )
    previous = {name: getattr(base, name) for name in names}
    try:
        activate_amendment()
        yield
    finally:
        for name, value in previous.items():
            setattr(base, name, value)


def synthetic_smoke_isolated(
    config_path: Path = DEFAULT_CONFIG, output_dir: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    with _isolated_activation():
        return base.synthetic_smoke(config_path, output_dir)


def synthetic_pca_controls_isolated(
    config_path: Path, output_dir: Path
) -> dict[str, Any]:
    with _isolated_activation():
        return base.execute_pca_controls(config_path, output_dir, synthetic=True)


def synthetic_model_fit_phases_isolated(
    config_path: Path, output_dir: Path
) -> dict[str, dict[str, Any]]:
    with _isolated_activation():
        return {
            "pca": base.execute_pca_controls(
                config_path, output_dir, synthetic=True
            ),
            "classical": base.execute_classical_robustness(
                config_path, output_dir, synthetic=True
            ),
            "qnn": base.execute_qnn_robustness(
                config_path, output_dir, synthetic=True
            ),
        }


def create_report(config_path: Path, output_dir: Path) -> dict[str, Any]:
    report = base.create_report(config_path, output_dir)
    report["id"] = "secondary_development_execution_v1_1_4"
    report["parallel_checkpoint_amendment"] = "1.1.4"
    base.atomic_write_json(output_dir / "run_manifest.json", report)
    result_path = output_dir / "secondary_development_report.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["id"] = "secondary_development_results_v1_1_4"
        result["parallel_checkpoint_amendment"] = "1.1.4"
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
            "pca-controls",
            "interpretability",
            "robustness-classical",
            "robustness-qnn",
            "report",
            "all",
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config_path = args.config.resolve()
    if args.output_dir is not None:
        output_dir = args.output_dir.resolve()
    elif args.mode in {"plan", "smoke"}:
        output_dir = (ROOT / f"data/model_runs/secondary_development_v1_1_4_{args.mode}").resolve()
    else:
        output_dir = DEFAULT_OUTPUT.resolve()
    base._require(config_path == DEFAULT_CONFIG.resolve(), "Only canonical v1.1.4 config may execute.")
    if args.mode == "status":
        result = base.package_status(config_path)
        result["amendment_authority_v1_1_4"] = verify_amendment_authority(
            load_execution_config(config_path)
        )
    elif args.mode == "plan":
        result = base.write_plan(config_path, output_dir)
        result["id"] = "secondary_development_execution_plan_v1_1_4"
        result["parallel_checkpoint_amendment"] = "1.1.4"
        base.atomic_write_json(output_dir / "secondary_analysis_execution_plan.json", result)
    elif args.mode == "smoke":
        result = base.synthetic_smoke(config_path, output_dir)
        result["parallel_checkpoint_amendment"] = "1.1.4"
    elif args.mode == "preflight":
        _config, _schedule, tasks, _runner, _sample, folds = base._preflight_context(
            config_path, output_dir
        )
        preflight = json.loads((output_dir / "preflight_manifest.json").read_text(encoding="utf-8"))
        result = {
            "status": "PASS",
            "planned_tasks": len(tasks),
            "fold_ids": list(folds),
            "parallel_checkpoint_amendment": "1.1.4",
            "interpretation_checkpoint_count": preflight["interpretation_checkpoint_count"],
            "interpretation_checkpoint_inventory_sha256": preflight[
                "interpretation_checkpoint_inventory_sha256"
            ],
            "project_data_read": True,
            "project_model_fit_performed": False,
            "protected_feature_years_opened": False,
        }
    elif args.mode == "pca-controls":
        result = base.execute_pca_controls(config_path, output_dir)
    elif args.mode == "interpretability":
        result = base.execute_interpretability(config_path, output_dir)
    elif args.mode == "robustness-classical":
        result = base.execute_classical_robustness(config_path, output_dir)
    elif args.mode == "robustness-qnn":
        result = base.execute_qnn_robustness(config_path, output_dir)
    elif args.mode == "report":
        result = create_report(config_path, output_dir)
    else:
        base.execute_pca_controls(config_path, output_dir)
        base.execute_interpretability(config_path, output_dir)
        base.execute_classical_robustness(config_path, output_dir)
        base.execute_qnn_robustness(config_path, output_dir)
        result = create_report(config_path, output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

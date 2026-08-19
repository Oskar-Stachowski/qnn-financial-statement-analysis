"""Pure reference algorithms for model execution contract v1.2.0.

This module loads specifications and synthetic/result metadata only.  It has no
project-data loader, estimator constructor, training loop, or production runner.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any, Iterable, Mapping, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "configs/model_execution_contract_v1_2_0_scientific_patch.yaml"
REGISTRY_PATH = ROOT / "configs/model_stage_candidates_v1_scientific_patch.json"
BEST_BLOCK_BINDING = "$BEST_COARSE_BLOCK"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    overlay = (
        contract.get("scientific_correctness_overlay")
        if isinstance(contract, dict)
        else None
    )
    if isinstance(overlay, dict):
        base = (ROOT / str(overlay["base_contract"]["path"])).resolve()
        if file_sha256(base) != str(overlay["base_contract"]["sha256"]):
            raise ValueError("Scientific patch base-contract hash mismatch")
        contract = yaml.safe_load(base.read_text(encoding="utf-8"))
        contract["scientific_correctness_patch"] = {
            key: value
            for key, value in overlay.items()
            if key not in {"base_contract", "candidate_registry", "expanded_order_sha256"}
        }
        contract["authority"]["candidate_registry"] = dict(
            overlay["candidate_registry"]
        )
        contract["canonical_ordering"]["expanded_order_sha256"] = str(
            overlay["expanded_order_sha256"]
        )
        checkpoint_field = str(overlay["checkpoint_identity_append"])
        checkpoint_fields = contract["execution_failure_state_machine"][
            "checkpoint_identity_fields"
        ]
        if checkpoint_field not in checkpoint_fields:
            checkpoint_fields.append(checkpoint_field)
        contract["execution_failure_state_machine"][
            "qnn_global_resource_ledger"
        ] = dict(overlay["qnn_global_resource_ledger"])
    if not isinstance(contract, dict) or "execution_contract" not in contract:
        raise ValueError(f"Invalid model execution contract: {path}")
    return contract


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("id") != "model_stage_candidates_v1":
        raise ValueError(f"Invalid model candidate registry: {path}")
    return registry


def _ordered_candidates(candidates: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    ordered = list(candidates)
    identifiers = [str(item["configuration_id"]) for item in ordered]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Candidate registry list contains duplicate configuration IDs")
    return ordered


def canonical_candidate_index(
    contract: Mapping[str, Any] | None = None,
    registry: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Enumerate every coarse/refinement/QNN candidate execution position."""

    contract = contract or load_contract()
    registry = registry or load_registry()
    ordering = contract["canonical_ordering"]
    blocks = list(ordering["feature_block_order"])
    block_agnostic = str(ordering["block_agnostic_token"])
    entries: list[dict[str, Any]] = []

    for family in ordering["family_order"]:
        if family == "qnn":
            continue
        candidates = _ordered_candidates(registry["coarse"][family])
        family_blocks = [block_agnostic] if family == "dummy_prior" else blocks
        for feature_block in family_blocks:
            for candidate in candidates:
                entries.append(
                    {
                        "stage": "coarse",
                        "family": family,
                        "feature_block_or_binding": feature_block,
                        "configuration_id": candidate["configuration_id"],
                    }
                )

    for family in ordering["refinement_family_order"]:
        for candidate in _ordered_candidates(registry["refinement"][family]):
            entries.append(
                {
                    "stage": "refinement",
                    "family": family,
                    "feature_block_or_binding": BEST_BLOCK_BINDING,
                    "configuration_id": candidate["configuration_id"],
                }
            )

    for stage, registry_key in (("qnn_q1", "stage_q1"), ("qnn_q2", "stage_q2")):
        for feature_block in blocks:
            for candidate in _ordered_candidates(registry["qnn"][registry_key]):
                entries.append(
                    {
                        "stage": stage,
                        "family": "qnn",
                        "feature_block_or_binding": feature_block,
                        "configuration_id": candidate["configuration_id"],
                    }
                )

    return [dict(ordinal=index, **entry) for index, entry in enumerate(entries, 1)]


def quantized_metric(value: float, decimal_places: int = 6) -> Decimal:
    if not math.isfinite(float(value)):
        raise ValueError("Primary metric must be finite")
    quantum = Decimal(1).scaleb(-decimal_places)
    return Decimal(str(float(value))).quantize(quantum, rounding=ROUND_HALF_EVEN)


def _feature_block_rank(feature_block: str, contract: Mapping[str, Any]) -> int:
    block_agnostic = str(contract["canonical_ordering"]["block_agnostic_token"])
    if feature_block == block_agnostic:
        return -1
    return list(contract["canonical_ordering"]["feature_block_order"]).index(
        feature_block
    )


def candidate_complexity_units(
    family: str,
    parameters: Mapping[str, Any],
    feature_block: str,
    stage: str,
    *,
    selected_ansatz_id: str | None = None,
    contract: Mapping[str, Any] | None = None,
) -> int:
    """Return the frozen static complexity proxy used only for exact ties."""

    contract = contract or load_contract()
    dimensions = contract["complexity_units"]["input_dimensions_after_preprocessing_C"]
    maximum_train_rows = int(
        contract["complexity_units"]["maximum_train_rows_for_static_bounds"]
    )
    if family == "dummy_prior":
        return 1
    if family in {"fixed_l2_logistic", "elastic_net_logistic"}:
        return int(dimensions[feature_block]) + 1
    if family == "rbf_svm":
        return maximum_train_rows + 1
    if family == "random_forest":
        fixed = contract["complexity_units"]["fixed_family_parameters"]
        n_estimators = int(
            fixed[
                "refinement_random_forest_n_estimators"
                if stage == "refinement"
                else "coarse_random_forest_n_estimators"
            ]
        )
        max_samples = float(parameters["max_samples"])
        effective_rows = max(1, math.floor(maximum_train_rows * max_samples))
        leaves_by_samples = max(
            1, effective_rows // int(parameters["min_samples_leaf"])
        )
        depth = parameters["max_depth"]
        leaves_by_depth = leaves_by_samples if depth is None else 2 ** int(depth)
        leaves = min(leaves_by_samples, leaves_by_depth)
        return n_estimators * (2 * leaves - 1)
    if family == "hist_gradient_boosting":
        return int(parameters["max_iter"]) * (
            2 * int(parameters["max_leaf_nodes"]) - 1
        )
    if family == "xgboost":
        return int(parameters["n_estimators"]) * (
            2 ** (int(parameters["max_depth"]) + 1) - 1
        )
    if family == "pytorch_mlp":
        sizes = [int(dimensions[feature_block])]
        sizes.extend(int(item) for item in parameters["hidden_layer_sizes"])
        sizes.append(1)
        return sum(
            input_size * output_size + output_size
            for input_size, output_size in zip(sizes[:-1], sizes[1:], strict=True)
        )
    if family == "qnn":
        ansatz = selected_ansatz_id or str(parameters.get("ansatz", ""))
        qubits = int(parameters["qubits_pca"])
        layers = int(parameters["layers"])
        if ansatz == "ROT_CNOT_RING":
            circuit_parameters = layers * qubits * 3
        elif ansatz in {"RY_RZ_CZ_BRICKWORK", "RY_CRX_RING"}:
            circuit_parameters = layers * qubits * 2
        else:
            raise ValueError(f"Unknown QNN ansatz: {ansatz}")
        return circuit_parameters + qubits + 1
    raise ValueError(f"Unknown model family: {family}")


def deterministic_ranking_key(
    row: Mapping[str, Any],
    contract: Mapping[str, Any] | None = None,
) -> tuple[Any, ...]:
    contract = contract or load_contract()
    complete = str(row.get("status")) == "COMPLETE"
    metric = row.get("pooled_oof_pr_auc")
    metric_key = (
        -quantized_metric(float(metric))
        if complete and metric is not None
        else Decimal("Infinity")
    )
    family = str(row["family"])
    feature_block = str(row["feature_block"])
    parameters = row.get("parameters") or {}
    imbalance = str(parameters.get("imbalance", "none"))
    family_rank = list(contract["canonical_ordering"]["family_order"]).index(family)
    stage_rank = list(contract["canonical_ordering"]["stage_order"]).index(
        str(row["stage"])
    )
    complexity = candidate_complexity_units(
        family,
        parameters,
        feature_block,
        str(row["stage"]),
        selected_ansatz_id=row.get("selected_ansatz_id"),
        contract=contract,
    )
    return (
        0 if complete else 1,
        metric_key,
        _feature_block_rank(feature_block, contract),
        family_rank,
        0 if imbalance == "none" else 1,
        complexity,
        stage_rank,
        str(row["configuration_id"]).encode("utf-8"),
    )


def rank_candidates(
    rows: Iterable[Mapping[str, Any]],
    contract: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    contract = contract or load_contract()
    materialized = [dict(row) for row in rows]
    identities = [
        (
            row.get("stage"),
            row.get("family"),
            row.get("feature_block"),
            row.get("configuration_id"),
            row.get("training_seed"),
        )
        for row in materialized
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate candidate result identity")
    return sorted(materialized, key=lambda row: deterministic_ranking_key(row, contract))


def is_boundary_candidate(
    family: str,
    parameters: Mapping[str, Any],
    contract: Mapping[str, Any] | None = None,
) -> bool:
    contract = contract or load_contract()
    domains = contract["boundary_hyperparameters"]["ordered_domains"].get(family, {})
    for parameter, ordered_values in domains.items():
        if parameter not in parameters or not ordered_values:
            continue
        value = parameters[parameter]
        if value not in ordered_values:
            continue
        if value == ordered_values[0] or value == ordered_values[-1]:
            return True
    return False


def select_refinement_families(
    coarse_rows: Iterable[Mapping[str, Any]],
    contract: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    contract = contract or load_contract()
    policy = contract["conditional_refinement"]
    complete = [
        dict(row)
        for row in coarse_rows
        if row.get("stage") == "coarse"
        and row.get("family") != "qnn"
        and row.get("status") == "COMPLETE"
        and int(row.get("training_seed", -1)) == 20260818
    ]
    if not complete:
        return []
    global_leader = rank_candidates(complete, contract)[0]
    global_metric = float(global_leader["pooled_oof_pr_auc"])
    activated: list[dict[str, Any]] = []
    refinement_order = list(contract["canonical_ordering"]["refinement_family_order"])
    for family in policy["eligible_families"]:
        family_rows = [row for row in complete if row["family"] == family]
        if not family_rows:
            continue
        family_ranked = rank_candidates(family_rows, contract)
        leader = family_ranked[0]
        best_block = str(leader["feature_block"])
        same_block = [
            row
            for row in family_ranked
            if row["feature_block"] == best_block
            and row["configuration_id"] != leader["configuration_id"]
        ]
        runner_up = same_block[0] if same_block else None
        leader_metric = float(leader["pooled_oof_pr_auc"])
        distance = max(0.0, global_metric - leader_metric)
        runner_up_gap = (
            max(0.0, leader_metric - float(runner_up["pooled_oof_pr_auc"]))
            if runner_up is not None
            else math.inf
        )
        boundary = is_boundary_candidate(
            family, leader.get("parameters") or {}, contract
        )
        eligible = distance <= float(policy["coarse_leader_pr_auc_distance_max"]) and (
            boundary or runner_up_gap <= float(policy["runner_up_gap_max"])
        )
        if eligible:
            activated.append(
                {
                    "family": family,
                    "feature_block": best_block,
                    "family_leader_configuration_id": leader["configuration_id"],
                    "distance_to_global_coarse_leader": distance,
                    "runner_up_gap": runner_up_gap,
                    "boundary": boundary,
                    "_leader": leader,
                    "_family_order": refinement_order.index(family),
                }
            )
    activated.sort(
        key=lambda item: (
            item["distance_to_global_coarse_leader"],
            deterministic_ranking_key(item["_leader"], contract),
            item["_family_order"],
        )
    )
    output: list[dict[str, Any]] = []
    for item in activated[: int(policy["maximum_families"])]:
        output.append({key: value for key, value in item.items() if not key.startswith("_")})
    return output


def merge_coarse_refinement_results(
    coarse_rows: Iterable[Mapping[str, Any]],
    refinement_rows: Iterable[Mapping[str, Any]],
    activations: Iterable[Mapping[str, Any]],
    contract: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    contract = contract or load_contract()
    active = {
        str(item["family"]): str(item["feature_block"]) for item in activations
    }
    merged = [dict(row) for row in coarse_rows]
    for raw_row in refinement_rows:
        row = dict(raw_row)
        family = str(row["family"])
        if row.get("stage") != "refinement":
            raise ValueError("Refinement table contains a non-refinement row")
        if family not in active or str(row["feature_block"]) != active[family]:
            raise ValueError("Refinement row is outside its activated family/best block")
        merged.append(row)
    keys = [
        (
            row["family"],
            row["feature_block"],
            row["configuration_id"],
            int(row["training_seed"]),
        )
        for row in merged
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate coarse/refinement merge key")
    stage_order = list(contract["canonical_ordering"]["stage_order"])
    family_order = list(contract["canonical_ordering"]["family_order"])
    return sorted(
        merged,
        key=lambda row: (
            stage_order.index(str(row["stage"])),
            family_order.index(str(row["family"])),
            _feature_block_rank(str(row["feature_block"]), contract),
            str(row["configuration_id"]).encode("utf-8"),
            int(row["training_seed"]),
        ),
    )


def select_confirmation_candidates(
    merged_rows: Iterable[Mapping[str, Any]],
    contract: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    contract = contract or load_contract()
    confirmation = contract["confirmation"]
    rows = [dict(row) for row in merged_rows]
    selected: list[dict[str, Any]] = []
    for family in confirmation["stochastic_classical_mlp_families"]:
        for block in contract["canonical_ordering"]["feature_block_order"]:
            eligible = [
                row
                for row in rows
                if row["family"] == family
                and row["feature_block"] == block
                and row["status"] == "COMPLETE"
                and int(row["training_seed"]) == int(confirmation["coarse_seed"])
            ]
            for rank, row in enumerate(rank_candidates(eligible, contract)[:2], 1):
                selected.append(
                    {
                        "family": family,
                        "feature_block": block,
                        "configuration_id": row["configuration_id"],
                        "source_stage": row["stage"],
                        "confirmation_rank": rank,
                        "confirmation_seeds": list(confirmation["confirmation_seeds"]),
                    }
                )
    return selected


def select_qnn_ansatz(
    q1_rows: Iterable[Mapping[str, Any]],
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Select the one global Q1 ansatz with the frozen QNN-specific key."""

    contract = contract or load_contract()
    rows = [
        dict(row)
        for row in q1_rows
        if row.get("stage") == "qnn_q1"
        and row.get("family") == "qnn"
        and row.get("status") == "COMPLETE"
        and int(row.get("training_seed", -1)) == 20260818
    ]
    if not rows:
        return {"status": "QNN_TECHNICALLY_INFEASIBLE", "reason": "no_complete_q1_candidate"}

    def q1_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
        parameters = row.get("parameters") or {}
        ansatz = str(parameters["ansatz"])
        complexity = candidate_complexity_units(
            "qnn",
            parameters,
            str(row["feature_block"]),
            "qnn_q1",
            selected_ansatz_id=ansatz,
            contract=contract,
        )
        return (
            -quantized_metric(float(row["pooled_oof_pr_auc"])),
            _feature_block_rank(str(row["feature_block"]), contract),
            complexity,
            1 if ansatz == "RY_CRX_RING" else 0,
            ansatz.encode("utf-8"),
            str(row["configuration_id"]).encode("utf-8"),
        )

    leader = sorted(rows, key=q1_key)[0]
    return {
        "status": "SELECTED",
        "selected_ansatz_id": leader["parameters"]["ansatz"],
        "q1_configuration_id": leader["configuration_id"],
        "q1_feature_block": leader["feature_block"],
        "q1_pooled_oof_pr_auc": leader["pooled_oof_pr_auc"],
    }


def select_qnn_confirmation_candidates(
    q2_rows: Iterable[Mapping[str, Any]],
    contract: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Select exactly one seed-20260818 Q2 candidate per feature block."""

    contract = contract or load_contract()
    rows = [
        dict(row)
        for row in q2_rows
        if row.get("stage") == "qnn_q2"
        and row.get("family") == "qnn"
        and row.get("status") == "COMPLETE"
        and int(row.get("training_seed", -1)) == 20260818
    ]
    selected: list[dict[str, Any]] = []
    for block in contract["canonical_ordering"]["feature_block_order"]:
        block_rows = [row for row in rows if row["feature_block"] == block]

        def q2_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
            parameters = row.get("parameters") or {}
            imbalance = str(parameters.get("imbalance", "none"))
            complexity = candidate_complexity_units(
                "qnn",
                parameters,
                block,
                "qnn_q2",
                selected_ansatz_id=str(row["selected_ansatz_id"]),
                contract=contract,
            )
            return (
                -quantized_metric(float(row["pooled_oof_pr_auc"])),
                0 if imbalance == "none" else 1,
                complexity,
                str(row["configuration_id"]).encode("utf-8"),
            )

        if block_rows:
            leader = sorted(block_rows, key=q2_key)[0]
            selected.append(
                {
                    "family": "qnn",
                    "feature_block": block,
                    "configuration_id": leader["configuration_id"],
                    "selected_ansatz_id": leader["selected_ansatz_id"],
                    "confirmation_rank": 1,
                    "confirmation_seeds": [20260819, 20260820],
                }
            )
    return selected


def align_and_average_raw_scores(
    predictions_by_seed: Mapping[int, Sequence[Mapping[str, Any]]],
    expected_seeds: Sequence[int],
    contract: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    contract = contract or load_contract()
    policy = contract["seed_aggregation"]
    if set(predictions_by_seed) != {int(seed) for seed in expected_seeds}:
        raise ValueError("Prediction seed set does not match the frozen seed set")
    key_fields = tuple(policy["canonical_prediction_key"])
    alignment_fields = tuple(policy["required_alignment_fields"])
    seed_maps: dict[int, dict[tuple[Any, ...], Mapping[str, Any]]] = {}
    for seed in expected_seeds:
        mapping: dict[tuple[Any, ...], Mapping[str, Any]] = {}
        for row in predictions_by_seed[int(seed)]:
            key = tuple(row[field] for field in key_fields)
            if key in mapping:
                raise ValueError("Duplicate canonical OOF prediction key")
            score = float(row["raw_score"])
            if not math.isfinite(score):
                raise ValueError("Nonfinite raw score")
            mapping[key] = row
        seed_maps[int(seed)] = mapping
    reference_keys = set(seed_maps[int(expected_seeds[0])])
    if any(set(mapping) != reference_keys for mapping in seed_maps.values()):
        raise ValueError("Missing or extra OOF prediction key across seeds")
    ordered_keys = sorted(reference_keys, key=lambda key: (int(key[0]), str(key[1]).encode("utf-8")))
    output: list[dict[str, Any]] = []
    for key in ordered_keys:
        rows = [seed_maps[int(seed)][key] for seed in expected_seeds]
        reference = rows[0]
        for row in rows[1:]:
            if any(row[field] != reference[field] for field in alignment_fields):
                raise ValueError("OOF alignment metadata differs across seeds")
        scores = [float(row["raw_score"]) for row in rows]
        output.append(
            {
                **{field: reference[field] for field in alignment_fields},
                "averaged_raw_score": float(math.fsum(scores) / len(scores)),
                "seed_order": [int(seed) for seed in expected_seeds],
            }
        )
    return output


def fold_retry_action(
    family: str,
    event: str,
    *,
    checkpoint_valid: bool = False,
    resume_attempts_used: int = 0,
    fresh_retries_used: int = 0,
    contract: Mapping[str, Any] | None = None,
) -> str:
    contract = contract or load_contract()
    policy = contract["execution_failure_state_machine"]
    if event == "SUCCESS_FINITE":
        return "COMPLETE"
    terminal = {
        "NAN_OR_INF_INPUT": "NUMERICAL_INVALID",
        "NAN_OR_INF_PARAMETER": "NUMERICAL_INVALID",
        "NAN_OR_INF_RAW_SCORE": "NUMERICAL_INVALID",
        "NUMERICAL_RUNTIME_WARNING": "NUMERICAL_INVALID",
        "CONVERGENCE_WARNING": "CONVERGENCE_INVALID",
        "TIMEOUT": "TIMEOUT_INVALID",
        "DETERMINISTIC_LIBRARY_EXCEPTION": "EXCEPTION_INVALID",
        "UNEXPECTED_WARNING": "EXCEPTION_INVALID",
    }
    if event in terminal:
        return terminal[event]
    if event == "CHECKPOINT_IDENTITY_MISMATCH":
        if fresh_retries_used < int(policy["fresh_infrastructure_retry_limit"]):
            return "FRESH_RETRY"
        return "CHECKPOINT_INVALID"
    if event != "INFRASTRUCTURE_FAILURE":
        raise ValueError(f"Unknown fold execution event: {event}")
    checkpoint_capable = family in policy["checkpoint_capable_families"]
    if (
        checkpoint_capable
        and checkpoint_valid
        and resume_attempts_used < int(policy["valid_checkpoint_resume_limit"])
    ):
        return "RESUME_CHECKPOINT"
    if fresh_retries_used < int(policy["fresh_infrastructure_retry_limit"]):
        return "FRESH_RETRY"
    return "INFRASTRUCTURE_EXHAUSTED"


def candidate_fold_aggregate_status(
    fold_statuses: Mapping[str, str],
    contract: Mapping[str, Any] | None = None,
    *,
    family: str = "classical_or_mlp",
) -> str:
    contract = contract or load_contract()
    required = list(contract["execution_failure_state_machine"]["required_folds"])
    if set(fold_statuses) != set(required):
        return (
            "QNN_CANDIDATE_TECHNICALLY_INVALID"
            if family == "qnn"
            else "FAMILY_CANDIDATE_TECHNICALLY_INVALID"
        )
    if all(fold_statuses[fold] == "COMPLETE" for fold in required):
        return "COMPLETE"
    return (
        "QNN_CANDIDATE_TECHNICALLY_INVALID"
        if family == "qnn"
        else "FAMILY_CANDIDATE_TECHNICALLY_INVALID"
    )


def qnn_execution_identity(
    selected_ansatz_id: str,
    q2_configuration_id: str,
    feature_block: str,
    fold_id: str,
    training_seed: int,
    software_environment_sha256: str,
    contract: Mapping[str, Any] | None = None,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = contract or load_contract()
    registry = registry or load_registry()
    candidates = {
        item["configuration_id"]: item for item in registry["qnn"]["stage_q2"]
    }
    if q2_configuration_id not in candidates:
        raise ValueError("Unknown QNN Q2 configuration")
    if selected_ansatz_id not in {
        item["ansatz"] for item in registry["qnn"]["stage_q1"]
    }:
        raise ValueError("Unknown selected QNN ansatz")
    candidate = candidates[q2_configuration_id]
    identity = {
        "selected_ansatz_id": selected_ansatz_id,
        "q1_or_q2_configuration_id": q2_configuration_id,
        "feature_block": feature_block,
        "qubits_pca": int(candidate["qubits_pca"]),
        "layers": int(candidate["layers"]),
        "epochs": int(candidate["epochs"]),
        "learning_rate": float(candidate["learning_rate"]),
        "batch_size": int(candidate["batch_size"]),
        "weight_decay": float(candidate["weight_decay"]),
        "imbalance": candidate["imbalance"],
        "optimizer_identity": contract["qnn_executable_identity"]["optimizer_identity"],
        "training_seed": int(training_seed),
        "fold_id": fold_id,
        "software_environment_sha256": software_environment_sha256,
        "device_identity": contract["qnn_executable_identity"]["device_identity"],
    }
    return {**identity, "executable_identity_sha256": canonical_sha256(identity)}


def software_spec_payload(role: str, contract: Mapping[str, Any] | None = None) -> dict[str, Any]:
    contract = contract or load_contract()
    policy = contract["software_environment_identity"]
    expected = policy[f"{role}_expected"]
    return {
        "python": str(expected["python"]),
        "packages": {key: str(value) for key, value in expected["packages"].items()},
        "thread_environment": {
            key: int(value) for key, value in policy["thread_environment"].items()
        },
    }


def calibration_plan(
    labels: Sequence[int],
    raw_scores: Sequence[float],
    *,
    epsilon: float = 1e-7,
) -> dict[str, Any]:
    if len(labels) != len(raw_scores) or not labels:
        return {"status": "CALIBRATION_TECHNICALLY_INVALID", "reason": "empty_or_misaligned"}
    normalized_labels = [int(label) for label in labels]
    if set(normalized_labels) - {0, 1} or len(set(normalized_labels)) < 2:
        return {"status": "CALIBRATION_TECHNICALLY_INVALID", "reason": "degenerate_labels"}
    scores = [float(score) for score in raw_scores]
    if not all(math.isfinite(score) for score in scores):
        return {"status": "CALIBRATION_TECHNICALLY_INVALID", "reason": "nonfinite_scores"}
    packed = {struct.pack(">d", score) for score in scores}
    if len(packed) == 1:
        prevalence = min(max(math.fsum(normalized_labels) / len(normalized_labels), epsilon), 1 - epsilon)
        return {
            "status": "CONSTANT_SCORE_INTERCEPT_ONLY",
            "coefficient": 0.0,
            "intercept": math.log(prevalence / (1.0 - prevalence)),
        }
    return {"status": "FIT_PLATT_LOGISTIC"}


def max_f1_threshold(
    labels: Sequence[int], calibrated_probabilities: Sequence[float]
) -> dict[str, Any]:
    if len(labels) != len(calibrated_probabilities) or not labels:
        return {"status": "THRESHOLD_TECHNICALLY_INVALID"}
    y = [int(label) for label in labels]
    if set(y) - {0, 1} or len(set(y)) < 2:
        return {"status": "THRESHOLD_NOT_CREATED_CALIBRATION_INVALID"}
    probabilities = [float(value) for value in calibrated_probabilities]
    if not all(math.isfinite(value) for value in probabilities):
        return {"status": "THRESHOLD_TECHNICALLY_INVALID"}
    candidates = sorted(set(probabilities))
    candidates.append(math.nextafter(max(candidates), math.inf))
    best: tuple[int, int, float] | None = None
    for threshold in candidates:
        predicted = [value >= threshold for value in probabilities]
        tp = sum(label == 1 and prediction for label, prediction in zip(y, predicted, strict=True))
        fp = sum(label == 0 and prediction for label, prediction in zip(y, predicted, strict=True))
        fn = sum(label == 1 and not prediction for label, prediction in zip(y, predicted, strict=True))
        numerator = 2 * tp
        denominator = 2 * tp + fp + fn
        if best is None:
            best = (numerator, denominator, threshold)
            continue
        left = numerator * best[1]
        right = best[0] * denominator
        if left > right or (left == right and threshold > best[2]):
            best = (numerator, denominator, threshold)
    assert best is not None
    return {
        "status": "THRESHOLD_SELECTED",
        "threshold": best[2],
        "threshold_float64_hex": float(best[2]).hex(),
        "achieved_f1_numerator": best[0],
        "achieved_f1_denominator": best[1],
        "candidate_count": len(candidates),
    }


def second_integrity_gate_verdict(
    evidence: Mapping[str, Any],
    contract: Mapping[str, Any] | None = None,
) -> str:
    contract = contract or load_contract()
    gate = contract["second_freeze_gate"]
    required = list(gate["pass_requires_all"])
    forbidden = set(gate["forbidden_gate_inputs"])
    if forbidden.intersection(evidence):
        return "MODEL_EXECUTION_V1_2_INTEGRITY_FAIL"
    if evidence.get("performance_metric_fields_consumed") is not False:
        return "MODEL_EXECUTION_V1_2_INTEGRITY_FAIL"
    if evidence.get("manual_override_or_waiver") is not False:
        return "MODEL_EXECUTION_V1_2_INTEGRITY_FAIL"
    checks = evidence.get("checks")
    if not isinstance(checks, Mapping) or set(checks) != set(required):
        return "MODEL_EXECUTION_V1_2_INTEGRITY_FAIL"
    if not all(checks[item] is True for item in required):
        return "MODEL_EXECUTION_V1_2_INTEGRITY_FAIL"
    return "MODEL_EXECUTION_V1_2_INTEGRITY_PASS"


def validate_contract(
    contract: Mapping[str, Any] | None = None,
    registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = contract or load_contract()
    registry = registry or load_registry()
    authority_checks = {}
    for name, item in contract["authority"].items():
        if not isinstance(item, Mapping) or "path" not in item or "sha256" not in item:
            continue
        actual = file_sha256(ROOT / str(item["path"]))
        authority_checks[name] = actual == str(item["sha256"])
    index = canonical_candidate_index(contract, registry)
    ordering = contract["canonical_ordering"]
    index_hash = canonical_sha256(index)
    environment_hashes = {
        role: canonical_sha256(software_spec_payload(role, contract))
        for role in ("classical", "qnn_mlp")
    }
    expected_environment_hashes = {
        role: str(
            contract["software_environment_identity"][f"{role}_expected"][
                "expected_spec_sha256"
            ]
        )
        for role in ("classical", "qnn_mlp")
    }
    return {
        "authority_hashes_match": all(authority_checks.values()),
        "authority_checks": authority_checks,
        "candidate_index_count": len(index),
        "candidate_index_count_matches": len(index)
        == int(ordering["expected_expanded_entries"]),
        "candidate_index_sha256": index_hash,
        "candidate_index_hash_matches": index_hash
        == str(ordering["expanded_order_sha256"]),
        "software_spec_sha256": environment_hashes,
        "software_spec_hashes_match": environment_hashes
        == expected_environment_hashes,
        "protected_feature_years_opened": False,
        "model_training_performed": False,
        "production_runner_implemented": False,
    }

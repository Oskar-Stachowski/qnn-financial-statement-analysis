"""Deterministic materialization helpers for model-stage preregistration.

This module contains configuration data and hashing only.  It does not load project
data, inspect validation/test values, construct estimators, or train models.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import random
from typing import Any, Iterable, Mapping, Sequence

from src.modeling.preprocessing import FEATURE_BLOCKS, features_for_blocks

COARSE_SAMPLING_SEED = 20260818
REFINEMENT_SAMPLING_SEED = 20260821
INDICATOR_SUFFIX = "__missing"
BLOCKS: dict[str, tuple[str, ...]] = {
    "L": ("L",),
    "L+D": ("L", "D"),
    "L+D+R": ("L", "D", "R"),
}


def canonical_json(value: Any) -> str:
    """Return the exact serialization used by every preregistration hash."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def feature_order_hash(columns: Sequence[str]) -> str:
    """Hash ordered UTF-8 names joined by LF, including one trailing LF."""

    payload = "".join(f"{column}\n" for column in columns).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def pca_input_columns(block: str) -> tuple[str, ...]:
    financial = features_for_blocks(BLOCKS[block])
    indicators = tuple(f"{feature}{INDICATOR_SUFFIX}" for feature in financial)
    return (*financial, *indicators)


def _product(space: Mapping[str, Sequence[Any]]) -> list[dict[str, Any]]:
    keys = tuple(space)
    return [dict(zip(keys, values, strict=True)) for values in itertools.product(*(space[key] for key in keys))]


def _materialize(
    family: str,
    stage: str,
    space: Mapping[str, Sequence[Any]],
    limit: int,
    seed: int,
) -> list[dict[str, Any]]:
    population = _product(space)
    if limit > len(population):
        raise ValueError(f"Limit {limit} exceeds {family} population {len(population)}.")
    if limit == len(population):
        selected = population
    else:
        selected = random.Random(seed).sample(population, limit)
    selected = sorted(selected, key=canonical_json)
    return [
        {
            "configuration_id": f"model_stage_v1__{stage}__{family}__{position:03d}",
            "parameters": parameters,
        }
        for position, parameters in enumerate(selected, start=1)
    ]


COARSE_SPACES: dict[str, tuple[dict[str, Sequence[Any]], int]] = {
    "dummy_prior": (
        {"strategy": ["prior"], "imbalance": ["none"]},
        1,
    ),
    "fixed_l2_logistic": (
        {"C": [1.0], "imbalance": ["none", "sqrt"]},
        2,
    ),
    "elastic_net_logistic": (
        {
            "C": [1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0],
            "l1_ratio": [0.0, 0.25, 0.5, 0.75, 1.0],
            "imbalance": ["none", "sqrt"],
        },
        12,
    ),
    "rbf_svm": (
        {"C": [0.1, 1.0, 10.0, 100.0], "gamma": ["scale", 0.01, 0.1], "imbalance": ["none", "sqrt"]},
        12,
    ),
    "random_forest": (
        {
            "criterion": ["gini", "log_loss"],
            "max_depth": [None, 6, 12, 24],
            "min_samples_leaf": [1, 5, 20],
            "max_features": ["sqrt", 0.5, 1.0],
            "max_samples": [0.7, 1.0],
            "imbalance": ["none", "sqrt"],
        },
        12,
    ),
    "hist_gradient_boosting": (
        {
            "learning_rate": [0.03, 0.06, 0.1],
            "max_iter": [150, 300],
            "max_leaf_nodes": [7, 15, 31],
            "min_samples_leaf": [20, 50, 100],
            "l2_regularization": [0.0, 0.1, 1.0, 10.0],
            "max_features": [0.7, 1.0],
            "imbalance": ["none", "sqrt"],
        },
        16,
    ),
    "xgboost": (
        {
            "n_estimators": [200, 500, 800],
            "max_depth": [2, 3, 5, 8],
            "learning_rate": [0.02, 0.05, 0.1],
            "subsample": [0.7, 1.0],
            "colsample_bytree": [0.7, 1.0],
            "min_child_weight": [1, 5, 20],
            "reg_alpha": [0.0, 0.01, 0.1],
            "reg_lambda": [1.0, 5.0, 20.0],
            "gamma": [0.0, 0.1],
            "imbalance": ["none", "sqrt"],
        },
        16,
    ),
    "pytorch_mlp": (
        {
            "hidden_layer_sizes": [[16], [32], [64], [32, 16], [64, 32]],
            "activation": ["relu", "tanh"],
            "weight_decay": [1e-5, 1e-4, 1e-3],
            "learning_rate": [3e-4, 1e-3, 3e-3],
            "batch_size": [64, 256],
            "imbalance": ["none", "sqrt"],
        },
        12,
    ),
}

REFINEMENT_SPACES: dict[str, tuple[dict[str, Sequence[Any]], int]] = {
    "elastic_net_logistic": (
        {"C": [0.003, 0.03, 0.3, 3.0, 30.0, 300.0], "l1_ratio": [0.125, 0.375, 0.625, 0.875], "imbalance": ["none", "sqrt"]},
        8,
    ),
    "rbf_svm": (
        {"C": [0.03, 0.3, 3.0, 30.0, 300.0], "gamma": [0.003, 0.03, 0.3], "imbalance": ["none", "sqrt"]},
        8,
    ),
    "random_forest": (
        {
            "criterion": ["gini", "log_loss"],
            "max_depth": [4, 9, 18, 32],
            "min_samples_leaf": [2, 10, 35],
            "max_features": [0.35, 0.7],
            "max_samples": [0.85],
            "imbalance": ["none", "sqrt"],
        },
        8,
    ),
    "hist_gradient_boosting": (
        {
            "learning_rate": [0.02, 0.045, 0.08],
            "max_iter": [225, 450],
            "max_leaf_nodes": [11, 23, 47],
            "min_samples_leaf": [10, 35, 75],
            "l2_regularization": [0.03, 0.3, 3.0],
            "max_features": [0.85],
            "imbalance": ["none", "sqrt"],
        },
        10,
    ),
    "xgboost": (
        {
            "n_estimators": [350, 650, 1000],
            "max_depth": [2, 4, 6],
            "learning_rate": [0.015, 0.035, 0.075],
            "min_child_weight": [2, 10],
            "subsample": [0.85],
            "colsample_bytree": [0.85],
            "reg_alpha": [0.03, 0.3],
            "reg_lambda": [2.0, 10.0],
            "gamma": [0.03, 0.3],
            "imbalance": ["none", "sqrt"],
        },
        10,
    ),
    "pytorch_mlp": (
        {
            "hidden_layer_sizes": [[24], [48], [96], [48, 24], [96, 48]],
            "activation": ["relu", "tanh"],
            "weight_decay": [3e-5, 3e-4, 3e-3],
            "learning_rate": [1e-4, 6e-4, 2e-3],
            "batch_size": [128],
            "imbalance": ["none", "sqrt"],
        },
        8,
    ),
}

QNN_STAGE_Q1 = [
    {
        "configuration_id": f"model_stage_v1__qnn_q1__{ansatz.lower()}",
        "ansatz": ansatz,
        "qubits_pca": 4,
        "layers": 2,
        "epochs": 45,
        "learning_rate": 0.01,
        "batch_size": 128,
        "weight_decay": 1e-4,
        "imbalance": "sqrt",
    }
    for ansatz in ("ROT_CNOT_RING", "RY_RZ_CZ_BRICKWORK", "RY_CRX_RING")
]

QNN_STAGE_Q2 = [
    {"configuration_id": "model_stage_v1__qnn_q2__t0", "qubits_pca": 4, "layers": 2, "epochs": 45, "learning_rate": 0.01, "batch_size": 128, "weight_decay": 1e-4, "imbalance": "sqrt", "reuse_q1_winner": True},
    {"configuration_id": "model_stage_v1__qnn_q2__t1", "qubits_pca": 4, "layers": 1, "epochs": 30, "learning_rate": 0.03, "batch_size": 256, "weight_decay": 0.0, "imbalance": "none", "reuse_q1_winner": False},
    {"configuration_id": "model_stage_v1__qnn_q2__t2", "qubits_pca": 6, "layers": 2, "epochs": 45, "learning_rate": 0.01, "batch_size": 128, "weight_decay": 1e-4, "imbalance": "sqrt", "reuse_q1_winner": False},
    {"configuration_id": "model_stage_v1__qnn_q2__t3", "qubits_pca": 6, "layers": 3, "epochs": 60, "learning_rate": 0.003, "batch_size": 256, "weight_decay": 1e-3, "imbalance": "none", "reuse_q1_winner": False},
]


def materialized_registry() -> dict[str, Any]:
    coarse = {
        family: _materialize(family, "coarse", space, limit, COARSE_SAMPLING_SEED)
        for family, (space, limit) in COARSE_SPACES.items()
    }
    refinement = {
        family: _materialize(family, "refinement", space, limit, REFINEMENT_SAMPLING_SEED)
        for family, (space, limit) in REFINEMENT_SPACES.items()
    }
    lists: dict[str, list[dict[str, Any]]] = {
        **{f"coarse.{family}": candidates for family, candidates in coarse.items()},
        **{f"refinement.{family}": candidates for family, candidates in refinement.items()},
        "qnn.stage_q1": QNN_STAGE_Q1,
        "qnn.stage_q2": QNN_STAGE_Q2,
    }
    feature_orders = {
        block: {
            "columns": list(pca_input_columns(block)),
            "includes_missing_indicators": True,
            "sha256_utf8_lf_with_trailing_lf": feature_order_hash(pca_input_columns(block)),
        }
        for block in BLOCKS
    }
    return {
        "schema_version": 1,
        "id": "model_stage_candidates_v1",
        "materialization": {
            "algorithm": "sorted_cartesian_population_then_python_random_sample_without_replacement_then_canonical_sort",
            "canonical_json": "utf8_sort_keys_no_whitespace_ensure_ascii_false",
            "coarse_seed": COARSE_SAMPLING_SEED,
            "refinement_seed": REFINEMENT_SAMPLING_SEED,
            "same_candidate_list_reused_for_all_three_feature_blocks": True,
        },
        "pca_feature_order": feature_orders,
        "coarse": coarse,
        "refinement": refinement,
        "qnn": {"stage_q1": QNN_STAGE_Q1, "stage_q2": QNN_STAGE_Q2},
        "list_hashes": {name: canonical_sha256(candidates) for name, candidates in sorted(lists.items())},
    }


def registry_json() -> str:
    return json.dumps(materialized_registry(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


"""Pre-fit identity-only patch for the frozen model candidate registry."""

from __future__ import annotations

import copy
import json
from typing import Any

from src.modeling import model_stage_preregistration as base


canonical_sha256 = base.canonical_sha256
pca_input_columns = base.pca_input_columns


def _mlp_candidates(
    candidates: list[dict[str, Any]], *, epochs: int
) -> list[dict[str, Any]]:
    patched = copy.deepcopy(candidates)
    for candidate in patched:
        candidate["parameters"]["epochs"] = int(epochs)
        prefix, position = str(candidate["configuration_id"]).rsplit("__", 1)
        candidate["configuration_id"] = f"{prefix}__epochs_{epochs}__{position}"
    return patched


def materialized_registry() -> dict[str, Any]:
    registry = copy.deepcopy(base.materialized_registry())
    registry["coarse"]["pytorch_mlp"] = _mlp_candidates(
        registry["coarse"]["pytorch_mlp"], epochs=200
    )
    registry["refinement"]["pytorch_mlp"] = _mlp_candidates(
        registry["refinement"]["pytorch_mlp"], epochs=300
    )
    registry["list_hashes"]["coarse.pytorch_mlp"] = canonical_sha256(
        registry["coarse"]["pytorch_mlp"]
    )
    registry["list_hashes"]["refinement.pytorch_mlp"] = canonical_sha256(
        registry["refinement"]["pytorch_mlp"]
    )
    registry["scientific_correctness_patch"] = {
        "version": "1.0.1",
        "scope": "explicit_pytorch_mlp_epochs_in_parameters_and_configuration_id",
        "search_space_changed": False,
    }
    return registry


def registry_json() -> str:
    return json.dumps(
        materialized_registry(), ensure_ascii=False, sort_keys=True, indent=2
    ) + "\n"

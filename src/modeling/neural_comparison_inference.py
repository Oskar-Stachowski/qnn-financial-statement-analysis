"""Paired clustered-bootstrap inference for the confirmed refined-MLP vs QNN comparison.

The bootstrap resamples ``economic_group_id`` clusters with replacement and
uses the same cluster draws for MLP and every QNN block.  This preserves a
paired comparison and follows the frozen 2,000-replicate, 95% percentile-CI
inference policy.  Only OOF predictions for feature years 2015–2020 are read.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from sklearn.metrics import average_precision_score, roc_auc_score

from src.modeling.post_coarse_runner import (
    DEFAULT_CONFIG_PATH,
    ROOT,
    atomic_write_json,
    build_authority_context,
    file_sha256,
    load_phase_results,
    load_post_coarse_config,
    load_result_reference,
    require_phase_manifest,
)


KEY_FIELDS = (
    "validation_feature_year",
    "research_universe_company_year_id",
)
ALIGNMENT_FIELDS = (
    "validation_feature_year",
    "research_universe_company_year_id",
    "fold_id",
    "target_label",
    "economic_group_id",
    "prediction_timestamp",
)


OUTPUT_CSV_FIELDS = (
    "comparison_role",
    "family",
    "feature_block",
    "configuration_id",
    "selected_ansatz_id",
    "point_pr_auc",
    "pr_auc_ci_lower",
    "pr_auc_ci_upper",
    "point_roc_auc",
    "roc_auc_ci_lower",
    "roc_auc_ci_upper",
    "point_delta_pr_auc_vs_mlp",
    "delta_pr_auc_ci_lower",
    "delta_pr_auc_ci_upper",
    "point_delta_roc_auc_vs_mlp",
    "delta_roc_auc_ci_lower",
    "delta_roc_auc_ci_upper",
    "bootstrap_probability_delta_pr_auc_gt_0",
    "bootstrap_probability_delta_roc_auc_gt_0",
)


def _key(row: Mapping[str, Any]) -> tuple[int, str]:
    return int(row[KEY_FIELDS[0]]), str(row[KEY_FIELDS[1]])


def _ordered_rows(result: Any) -> list[dict[str, Any]]:
    if result.row.get("status") != "COMPLETE":
        raise RuntimeError(
            f"Inference requires COMPLETE result: {result.row.get('family')} "
            f"{result.row.get('configuration_id')} {result.row.get('feature_block')}"
        )
    rows = [dict(row) for row in result.predictions]
    rows.sort(key=lambda row: (_key(row)[0], _key(row)[1].encode("utf-8")))
    if len(rows) != len({_key(row) for row in rows}):
        raise RuntimeError("Duplicate canonical OOF key.")
    return rows


def _align(base_rows: Sequence[Mapping[str, Any]], other_rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    other = {_key(row): row for row in other_rows}
    if set(other) != {_key(row) for row in base_rows}:
        raise RuntimeError("MLP and QNN OOF key sets differ.")
    scores: list[float] = []
    for base in base_rows:
        row = other[_key(base)]
        if any(row[field] != base[field] for field in ALIGNMENT_FIELDS):
            raise RuntimeError("MLP and QNN OOF alignment metadata differ.")
        score = float(row["raw_score"])
        if not math.isfinite(score):
            raise RuntimeError("Nonfinite raw score in inference input.")
        scores.append(score)
    return np.asarray(scores, dtype=np.float64)


def _metric_pair(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    if len(np.unique(labels)) != 2:
        raise ValueError("Degenerate bootstrap labels")
    return (
        float(average_precision_score(labels, scores)),
        float(roc_auc_score(labels, scores)),
    )


def _percentile_interval(values: Sequence[float]) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    if array.size == 0:
        return {"valid_replicates": 0, "lower_2_5": None, "median": None, "upper_97_5": None}
    return {
        "valid_replicates": int(array.size),
        "lower_2_5": float(np.percentile(array, 2.5, method="linear")),
        "median": float(np.percentile(array, 50.0, method="linear")),
        "upper_97_5": float(np.percentile(array, 97.5, method="linear")),
    }


def _update_run_manifest(
    *, output_dir: Path, bootstrap_path: Path, inference_status: str
) -> None:
    """Extend the confirmation run hash chain with the inference artifact."""

    run_manifest_path = output_dir / "run_manifest.json"
    if not run_manifest_path.is_file():
        raise RuntimeError("Missing run_manifest.json created by confirmation phase.")
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    if run_manifest.get("status") != "COMPLETE":
        raise RuntimeError("run_manifest.json is not COMPLETE.")
    if run_manifest.get("protected_feature_years_opened") is not False:
        raise RuntimeError("run_manifest.json has an invalid protected-year flag.")
    run_manifest["neural_comparison_clustered_bootstrap_sha256"] = file_sha256(
        bootstrap_path
    )
    run_manifest["neural_comparison_inference_status"] = inference_status
    run_manifest["neural_comparison_inference_completed"] = True
    atomic_write_json(run_manifest_path, run_manifest)


def _frozen_policy(config: Mapping[str, Any]) -> dict[str, Any]:
    section = config["post_coarse_execution"]
    policy = dict(section.get("inference") or {})
    expected = {
        "requires_confirmation_manifest_status": "COMPLETE",
        "resampling_unit": "economic_group_id",
        "paired_cluster_draws_across_models": True,
        "replicates": 2000,
        "seed": 20260818,
        "minimum_valid_replicates": 1900,
        "bootstrap_probability_is_p_value": False,
        "selection_adjusted": False,
        "protected_feature_years_opened": False,
    }
    for key, value in expected.items():
        if policy.get(key) != value:
            raise RuntimeError(
                f"Frozen inference policy mismatch for {key}: "
                f"expected {value!r}, got {policy.get(key)!r}"
            )
    return policy


def run_inference(
    *,
    output_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
    coarse_dir: Path | None = None,
    replicates: int | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    config = load_post_coarse_config(config_path)
    policy = _frozen_policy(config)
    frozen_replicates = int(policy["replicates"])
    frozen_seed = int(policy["seed"])
    if replicates is not None and int(replicates) != frozen_replicates:
        raise RuntimeError(
            f"The frozen inference policy requires {frozen_replicates} replicates."
        )
    if seed is not None and int(seed) != frozen_seed:
        raise RuntimeError(
            f"The frozen inference policy requires seed {frozen_seed}."
        )
    replicates = frozen_replicates
    seed = frozen_seed

    configured_coarse = Path(
        config["post_coarse_execution"]["coarse_source"]["root"]
    )
    coarse_dir = (
        coarse_dir.resolve()
        if coarse_dir is not None
        else (ROOT / configured_coarse).resolve()
    )
    authority = build_authority_context(
        root=ROOT,
        config=config,
        coarse_dir=coarse_dir,
        require_committed=True,
    )
    confirmation_path = output_dir / "confirmation_phase_manifest.json"
    confirmation = require_phase_manifest(
        confirmation_path,
        allowed_statuses={"COMPLETE"},
        authority=authority,
        root=ROOT,
    )

    mlp_ref = confirmation.get("supplemental_mlp_confirmed_result_reference")
    if not isinstance(mlp_ref, dict):
        raise RuntimeError("Missing confirmed supplemental MLP reference.")
    mlp = load_result_reference(mlp_ref, root=ROOT)
    qnns = load_phase_results(
        confirmation, "qnn_confirmed_result_references", root=ROOT
    )
    if mlp.row.get("status") != "COMPLETE":
        manifest = {
            "schema_version": 1,
            "id": "refined_mlp_vs_qnn_clustered_bootstrap_v1_0_0",
            "status": "NOT_APPLICABLE_MLP_COMPARATOR_TECHNICALLY_INVALID",
            "reason": "confirmed_supplemental_mlp_is_not_complete",
            "authority": authority.as_dict(ROOT),
            "method": {
                "resampling_unit": "economic_group_id",
                "paired_cluster_draws_across_models": True,
                "replicates_requested": int(policy["replicates"]),
                "replicates_valid": 0,
                "seed": int(policy["seed"]),
                "selection_adjusted": False,
            },
            "input": {
                "confirmation_phase_manifest": str(confirmation_path.resolve()),
                "confirmation_phase_manifest_sha256": file_sha256(
                    confirmation_path
                ),
                "mlp_status": mlp.row.get("status"),
                "qnn_confirmed_block_count": len(qnns),
            },
            "rows": [],
            "claim_guidance": {
                "comparison_available": False,
                "formal_superiority_claim_allowed": False,
                "bootstrap_probability_is_p_value": False,
                "no_quantum_advantage_claim_from_analytic_simulator": True,
            },
            "protected_feature_years_opened": False,
        }
        json_path = output_dir / "neural_comparison_clustered_bootstrap.json"
        json_path.write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n",
            encoding="utf-8",
        )
        csv_path = output_dir / "neural_comparison_clustered_bootstrap.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=list(OUTPUT_CSV_FIELDS)).writeheader()
        md_path = output_dir / "neural_comparison_clustered_bootstrap.md"
        md_path.write_text(
            "# Clustered bootstrap: refined MLP vs QNN\n\n"
            "Status: **NOT_APPLICABLE_MLP_COMPARATOR_TECHNICALLY_INVALID**.\n\n"
            "Nie można wykonać porównania, ponieważ confirmation dodatkowego "
            "MLP nie zakończyło się statusem COMPLETE.\n",
            encoding="utf-8",
        )
        _update_run_manifest(
            output_dir=output_dir,
            bootstrap_path=json_path,
            inference_status=str(manifest["status"]),
        )
        return manifest

    mlp_rows = _ordered_rows(mlp)
    years = {int(row["validation_feature_year"]) for row in mlp_rows}
    if years != {2015, 2016, 2017, 2018, 2019, 2020}:
        raise RuntimeError(f"Unexpected OOF validation years: {sorted(years)}")
    labels = np.asarray([int(row["target_label"]) for row in mlp_rows], dtype=np.int64)
    mlp_scores = np.asarray([float(row["raw_score"]) for row in mlp_rows], dtype=np.float64)
    groups = np.asarray([str(row["economic_group_id"]) for row in mlp_rows], dtype=object)
    if len(np.unique(labels)) != 2:
        raise RuntimeError("Inference input has a degenerate target.")

    qnn_scores: dict[str, np.ndarray] = {}
    qnn_identity: dict[str, dict[str, Any]] = {}
    qnn_invalid: list[dict[str, Any]] = []
    seen_qnn_blocks: set[str] = set()
    for qnn in qnns:
        block = str(qnn.row["feature_block"])
        if block in seen_qnn_blocks:
            raise RuntimeError(f"Duplicate confirmed QNN block: {block}")
        seen_qnn_blocks.add(block)
        if qnn.row.get("status") != "COMPLETE":
            qnn_invalid.append(
                {
                    "feature_block": block,
                    "configuration_id": qnn.row.get("configuration_id"),
                    "status": qnn.row.get("status"),
                    "failure_code": qnn.row.get("failure_code"),
                }
            )
            continue
        qnn_scores[block] = _align(mlp_rows, _ordered_rows(qnn))
        qnn_identity[block] = {
            "family": qnn.row["family"],
            "stage": qnn.row["stage"],
            "feature_block": block,
            "configuration_id": qnn.row["configuration_id"],
            "training_seed": qnn.row["training_seed"],
            "selected_ansatz_id": qnn.row.get("selected_ansatz_id"),
            "parameters": qnn.row.get("parameters") or {},
        }

    ordered_groups = sorted(set(groups.tolist()), key=lambda value: str(value).encode("utf-8"))
    group_indices = {
        group: np.flatnonzero(groups == group).astype(np.int64)
        for group in ordered_groups
    }
    if len(ordered_groups) < 2:
        raise RuntimeError("Fewer than two economic groups in OOF data.")

    mlp_point_pr, mlp_point_roc = _metric_pair(labels, mlp_scores)
    point_by_block: dict[str, dict[str, float]] = {}
    for block, scores in qnn_scores.items():
        pr_auc, roc_auc = _metric_pair(labels, scores)
        point_by_block[block] = {
            "pr_auc": pr_auc,
            "roc_auc": roc_auc,
            "delta_pr_auc_vs_mlp": pr_auc - mlp_point_pr,
            "delta_roc_auc_vs_mlp": roc_auc - mlp_point_roc,
        }

    mlp_boot_pr: list[float] = []
    mlp_boot_roc: list[float] = []
    qnn_boot: dict[str, dict[str, list[float]]] = {
        block: {"pr_auc": [], "roc_auc": [], "delta_pr_auc": [], "delta_roc_auc": []}
        for block in qnn_scores
    }
    invalid_replicates = 0
    rng = np.random.default_rng(seed)
    group_count = len(ordered_groups)
    for _ in range(replicates):
        sampled_positions = rng.integers(0, group_count, size=group_count)
        sampled_indices = np.concatenate(
            [group_indices[ordered_groups[int(position)]] for position in sampled_positions]
        )
        sampled_labels = labels[sampled_indices]
        if len(np.unique(sampled_labels)) != 2:
            invalid_replicates += 1
            continue
        sampled_mlp_pr, sampled_mlp_roc = _metric_pair(
            sampled_labels, mlp_scores[sampled_indices]
        )
        mlp_boot_pr.append(sampled_mlp_pr)
        mlp_boot_roc.append(sampled_mlp_roc)
        for block, scores in qnn_scores.items():
            qnn_pr, qnn_roc = _metric_pair(sampled_labels, scores[sampled_indices])
            qnn_boot[block]["pr_auc"].append(qnn_pr)
            qnn_boot[block]["roc_auc"].append(qnn_roc)
            qnn_boot[block]["delta_pr_auc"].append(qnn_pr - sampled_mlp_pr)
            qnn_boot[block]["delta_roc_auc"].append(qnn_roc - sampled_mlp_roc)

    valid_replicates = replicates - invalid_replicates
    minimum_valid = int(policy["minimum_valid_replicates"])
    if valid_replicates < minimum_valid:
        raise RuntimeError(
            f"Too few valid clustered-bootstrap replicates: "
            f"{valid_replicates}/{replicates}; minimum={minimum_valid}"
        )

    result_rows: list[dict[str, Any]] = [
        {
            "comparison_role": "REFINED_CLASSICAL_MLP",
            "family": "pytorch_mlp",
            "stage": mlp.row.get("stage"),
            "feature_block": mlp.row["feature_block"],
            "configuration_id": mlp.row["configuration_id"],
            "training_seed": mlp.row.get("training_seed"),
            "selected_ansatz_id": None,
            "parameters": mlp.row.get("parameters") or {},
            "point_pr_auc": mlp_point_pr,
            "pr_auc_ci": _percentile_interval(mlp_boot_pr),
            "point_roc_auc": mlp_point_roc,
            "roc_auc_ci": _percentile_interval(mlp_boot_roc),
            "point_delta_pr_auc_vs_mlp": 0.0,
            "delta_pr_auc_ci": _percentile_interval([0.0] * valid_replicates),
            "point_delta_roc_auc_vs_mlp": 0.0,
            "delta_roc_auc_ci": _percentile_interval([0.0] * valid_replicates),
            "bootstrap_probability_delta_pr_auc_gt_0": None,
            "bootstrap_probability_delta_roc_auc_gt_0": None,
        }
    ]
    for block in sorted(qnn_scores, key=lambda value: (len(value), value)):
        draws = qnn_boot[block]
        result_rows.append(
            {
                "comparison_role": "QNN_CONFIRMED_BLOCK_REPRESENTATIVE",
                **qnn_identity[block],
                "point_pr_auc": point_by_block[block]["pr_auc"],
                "pr_auc_ci": _percentile_interval(draws["pr_auc"]),
                "point_roc_auc": point_by_block[block]["roc_auc"],
                "roc_auc_ci": _percentile_interval(draws["roc_auc"]),
                "point_delta_pr_auc_vs_mlp": point_by_block[block][
                    "delta_pr_auc_vs_mlp"
                ],
                "delta_pr_auc_ci": _percentile_interval(draws["delta_pr_auc"]),
                "point_delta_roc_auc_vs_mlp": point_by_block[block][
                    "delta_roc_auc_vs_mlp"
                ],
                "delta_roc_auc_ci": _percentile_interval(draws["delta_roc_auc"]),
                "bootstrap_probability_delta_pr_auc_gt_0": float(
                    np.mean(np.asarray(draws["delta_pr_auc"]) > 0.0)
                ),
                "bootstrap_probability_delta_roc_auc_gt_0": float(
                    np.mean(np.asarray(draws["delta_roc_auc"]) > 0.0)
                ),
            }
        )

    comparison_available = bool(qnn_scores)
    manifest = {
        "schema_version": 1,
        "id": "refined_mlp_vs_qnn_clustered_bootstrap_v1_0_0",
        "status": (
            "COMPLETE"
            if comparison_available
            else "NOT_APPLICABLE_QNN_TECHNICALLY_INFEASIBLE"
        ),
        "reason": None if comparison_available else "no_complete_confirmed_qnn_candidate",
        "authority": authority.as_dict(ROOT),
        "method": {
            "resampling_unit": "economic_group_id",
            "paired_cluster_draws_across_models": True,
            "clusters_sampled_with_replacement": True,
            "clusters_per_replicate": len(ordered_groups),
            "replicates_requested": replicates,
            "replicates_valid": valid_replicates,
            "replicates_degenerate_discarded": invalid_replicates,
            "minimum_valid_replicates": minimum_valid,
            "interval": "95_percent_percentile",
            "percentiles": [2.5, 97.5],
            "numpy_percentile_method": "linear",
            "seed": seed,
            "selection_adjusted": False,
        },
        "input": {
            "confirmation_phase_manifest": str(confirmation_path.resolve()),
            "confirmation_phase_manifest_sha256": file_sha256(confirmation_path),
            "oof_years": sorted(years),
            "rows": len(labels),
            "positive_n": int(labels.sum()),
            "positive_share": float(labels.mean()),
            "economic_group_count": len(ordered_groups),
            "qnn_confirmed_reference_count": len(qnns),
            "qnn_complete_block_count": len(qnn_scores),
            "qnn_invalid_blocks": qnn_invalid,
        },
        "rows": result_rows,
        "claim_guidance": {
            "paired_delta_ci_role": (
                "descriptive development-set directional stability conditional "
                "on selected configurations"
            ),
            "directionally_stable_positive_difference_when": (
                "paired delta PR-AUC 95% percentile interval is entirely above 0"
            ),
            "formal_superiority_claim_allowed": False,
            "selection_adjusted": False,
            "independent_test_estimate": False,
            "bootstrap_probability_is_p_value": False,
            "point_estimate_alone_is_not_sufficient": True,
            "no_quantum_advantage_claim_from_analytic_simulator": True,
        },
        "protected_feature_years_opened": False,
    }

    json_path = output_dir / "neural_comparison_clustered_bootstrap.json"
    json_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    csv_path = output_dir / "neural_comparison_clustered_bootstrap.csv"
    fieldnames = list(OUTPUT_CSV_FIELDS)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in result_rows:
            writer.writerow(
                {
                    "comparison_role": row.get("comparison_role"),
                    "family": row.get("family"),
                    "feature_block": row.get("feature_block"),
                    "configuration_id": row.get("configuration_id"),
                    "selected_ansatz_id": row.get("selected_ansatz_id"),
                    "point_pr_auc": row.get("point_pr_auc"),
                    "pr_auc_ci_lower": row["pr_auc_ci"]["lower_2_5"],
                    "pr_auc_ci_upper": row["pr_auc_ci"]["upper_97_5"],
                    "point_roc_auc": row.get("point_roc_auc"),
                    "roc_auc_ci_lower": row["roc_auc_ci"]["lower_2_5"],
                    "roc_auc_ci_upper": row["roc_auc_ci"]["upper_97_5"],
                    "point_delta_pr_auc_vs_mlp": row.get(
                        "point_delta_pr_auc_vs_mlp"
                    ),
                    "delta_pr_auc_ci_lower": row["delta_pr_auc_ci"]["lower_2_5"],
                    "delta_pr_auc_ci_upper": row["delta_pr_auc_ci"]["upper_97_5"],
                    "point_delta_roc_auc_vs_mlp": row.get(
                        "point_delta_roc_auc_vs_mlp"
                    ),
                    "delta_roc_auc_ci_lower": row["delta_roc_auc_ci"]["lower_2_5"],
                    "delta_roc_auc_ci_upper": row["delta_roc_auc_ci"]["upper_97_5"],
                    "bootstrap_probability_delta_pr_auc_gt_0": row.get(
                        "bootstrap_probability_delta_pr_auc_gt_0"
                    ),
                    "bootstrap_probability_delta_roc_auc_gt_0": row.get(
                        "bootstrap_probability_delta_roc_auc_gt_0"
                    ),
                }
            )

    md_path = output_dir / "neural_comparison_clustered_bootstrap.md"
    lines = [
        "# Clustered bootstrap: refined MLP vs QNN",
        "",
        f"Status: **{manifest['status']}**.",
        "",
        f"Jednostka losowania: `economic_group_id`; poprawne replikacje: "
        f"{valid_replicates}/{replicates}; seed: `{seed}`.",
        "",
        "| Model | Block | PR-AUC | 95% CI | ΔPR-AUC vs MLP | 95% CI różnicy |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in result_rows:
        name = "Refined MLP" if row["family"] == "pytorch_mlp" else "QNN"
        lines.append(
            f"| {name} | {row.get('feature_block')} | {row['point_pr_auc']:.6f} | "
            f"[{row['pr_auc_ci']['lower_2_5']:.6f}, {row['pr_auc_ci']['upper_97_5']:.6f}] | "
            f"{row['point_delta_pr_auc_vs_mlp']:.6f} | "
            f"[{row['delta_pr_auc_ci']['lower_2_5']:.6f}, {row['delta_pr_auc_ci']['upper_97_5']:.6f}] |"
        )
    lines.extend(
        [
            "",
            "Przedziały są sparowane, ale opisują rozwojowe OOF warunkowo względem "
            "wybranych konfiguracji. Nie są niezależnym testem, nie korygują selekcji "
            "modelu, a raportowane prawdopodobieństwo bootstrapowe nie jest wartością p. "
            "Wynik z analitycznego symulatora nie stanowi dowodu przewagi kwantowej.",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    _update_run_manifest(
        output_dir=output_dir,
        bootstrap_path=json_path,
        inference_status=str(manifest["status"]),
    )
    return manifest

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--coarse-dir", type=Path)
    parser.add_argument("--replicates", type=int)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()
    result = run_inference(
        output_dir=args.output_dir.resolve(),
        config_path=args.config.resolve(),
        coarse_dir=args.coarse_dir.resolve() if args.coarse_dir else None,
        replicates=args.replicates,
        seed=args.seed,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

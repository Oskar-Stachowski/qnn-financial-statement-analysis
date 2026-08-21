"""Generate thesis-ready tables and a concise Markdown summary after post-coarse runs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.modeling.post_coarse_runner import (
    ROOT,
    _metric_summary,
    file_sha256,
    load_json,
    load_phase_results,
    load_result_reference,
)


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _flatten_result(result: Any, role: str) -> dict[str, Any]:
    row = dict(result.row)
    metrics = _metric_summary(result)
    return {
        "analysis_role": role,
        "family": row.get("family"),
        "stage": row.get("stage"),
        "feature_block": row.get("feature_block"),
        "configuration_id": row.get("configuration_id"),
        "training_seed": row.get("training_seed"),
        "status": row.get("status"),
        "failure_code": row.get("failure_code"),
        "selected_ansatz_id": row.get("selected_ansatz_id"),
        "parameters": _json_cell(row.get("parameters") or {}),
        "n": metrics.get("n"),
        "positive_n": metrics.get("positive_n"),
        "positive_share": metrics.get("positive_share"),
        "pooled_oof_pr_auc": metrics.get("pooled_oof_pr_auc"),
        "pooled_oof_roc_auc": metrics.get("pooled_oof_roc_auc"),
        "fold_pr_auc_mean": metrics.get("fold_pr_auc_mean"),
        "fold_pr_auc_sample_sd": metrics.get("fold_pr_auc_sample_sd"),
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("status\nNO_ROWS\n", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _format_metric(value: Any) -> str:
    return "—" if value is None else f"{float(value):.6f}"


def _format_interval(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "—"
    lower = value.get("lower_2_5")
    upper = value.get("upper_97_5")
    if lower is None or upper is None:
        return "—"
    return f"[{float(lower):.6f}, {float(upper):.6f}]"


def generate_report(output_dir: Path, report_dir: Path) -> dict[str, Any]:
    report_dir.mkdir(parents=True, exist_ok=True)
    source_hashes: dict[str, str | None] = {}
    summary_lines = [
        "# Wyniki refinementu i eksperymentu QNN",
        "",
        "Raport dotyczy wyłącznie wewnętrznej walidacji czasowej OOF 2015–2020. "
        "Nie otwiera ani nie wykorzystuje lat chronionych 2021–2024.",
        "",
    ]

    refinement_path = output_dir / "refinement_phase_manifest.json"
    if refinement_path.is_file():
        refinement = load_json(refinement_path)
        source_hashes[refinement_path.name] = file_sha256(refinement_path)
        primary_results = load_phase_results(
            refinement, "primary_result_references", root=ROOT
        )
        mlp_results = load_phase_results(
            refinement, "supplemental_mlp_result_references", root=ROOT
        )
        primary_rows = [
            _flatten_result(result, "PRIMARY_FROZEN_REFINEMENT")
            for result in primary_results
        ]
        mlp_rows = [
            _flatten_result(result, "SECONDARY_MLP_COMPARATOR_REFINEMENT")
            for result in mlp_results
        ]
        primary_rows.sort(
            key=lambda row: (
                str(row["family"]),
                -(row["pooled_oof_pr_auc"] or float("-inf")),
                str(row["configuration_id"]),
            )
        )
        mlp_rows.sort(
            key=lambda row: (
                -(row["pooled_oof_pr_auc"] or float("-inf")),
                str(row["configuration_id"]),
            )
        )
        _write_csv(report_dir / "01_primary_refinement_results.csv", primary_rows)
        _write_csv(report_dir / "02_mlp_comparator_refinement_results.csv", mlp_rows)
        summary_lines.extend(
            [
                "## Refinement modeli klasycznych",
                "",
                f"Pozycje głównego refinementu: **{len(primary_rows)}**. "
                f"Pozycje dodatkowego refinementu MLP: **{len(mlp_rows)}**.",
                "",
            ]
        )
        complete_mlp = [row for row in mlp_rows if row["status"] == "COMPLETE"]
        if complete_mlp:
            best_mlp = complete_mlp[0]
            summary_lines.extend(
                [
                    "Najlepsza jednoseedowa konfiguracja dodatkowego MLP:",
                    "",
                    f"- `{best_mlp['configuration_id']}`, blok **{best_mlp['feature_block']}**, "
                    f"PR-AUC **{_format_metric(best_mlp['pooled_oof_pr_auc'])}**, "
                    f"ROC-AUC **{_format_metric(best_mlp['pooled_oof_roc_auc'])}**.",
                    "",
                ]
            )

    qnn_path = output_dir / "qnn_phase_manifest.json"
    if qnn_path.is_file():
        qnn = load_json(qnn_path)
        source_hashes[qnn_path.name] = file_sha256(qnn_path)
        q1_results = load_phase_results(qnn, "q1_result_references", root=ROOT)
        q2_results = load_phase_results(qnn, "q2_result_references", root=ROOT)
        q1_rows = [_flatten_result(result, "QNN_Q1") for result in q1_results]
        q2_rows = [_flatten_result(result, "QNN_Q2") for result in q2_results]
        q1_rows.sort(
            key=lambda row: (
                -(row["pooled_oof_pr_auc"] or float("-inf")),
                str(row["feature_block"]),
                str(row["configuration_id"]),
            )
        )
        q2_rows.sort(
            key=lambda row: (
                str(row["feature_block"]),
                -(row["pooled_oof_pr_auc"] or float("-inf")),
                str(row["configuration_id"]),
            )
        )
        _write_csv(report_dir / "03_qnn_q1_ansatz_results.csv", q1_rows)
        _write_csv(report_dir / "04_qnn_q2_results.csv", q2_rows)
        selection = qnn.get("ansatz_selection") or {}
        summary_lines.extend(
            [
                "## QNN",
                "",
                f"Status fazy QNN: **{qnn.get('status')}**.",
                "",
            ]
        )
        if selection.get("status") == "SELECTED":
            summary_lines.extend(
                [
                    f"Wybrany globalny ansatz Q1: **{selection.get('selected_ansatz_id')}** "
                    f"(konfiguracja `{selection.get('q1_configuration_id')}`, "
                    f"blok **{selection.get('q1_feature_block')}**, "
                    f"PR-AUC **{_format_metric(selection.get('q1_pooled_oof_pr_auc'))}**).",
                    "",
                ]
            )

    confirmation_path = output_dir / "confirmation_phase_manifest.json"
    if confirmation_path.is_file():
        confirmation = load_json(confirmation_path)
        source_hashes[confirmation_path.name] = file_sha256(confirmation_path)
        primary_confirmed = load_phase_results(
            confirmation, "primary_confirmed_result_references", root=ROOT
        )
        qnn_confirmed = load_phase_results(
            confirmation, "qnn_confirmed_result_references", root=ROOT
        )
        mlp_reference = confirmation.get(
            "supplemental_mlp_confirmed_result_reference"
        )
        mlp_confirmed = (
            load_result_reference(mlp_reference, root=ROOT)
            if isinstance(mlp_reference, dict)
            else None
        )
        primary_rows = [
            _flatten_result(result, "PRIMARY_THREE_SEED_CONFIRMATION")
            for result in primary_confirmed
        ]
        _write_csv(report_dir / "05_primary_confirmation_results.csv", primary_rows)

        neural_rows: list[dict[str, Any]] = []
        mlp_metrics: dict[str, Any] | None = None
        if mlp_confirmed is not None:
            mlp_row = _flatten_result(
                mlp_confirmed, "REFINED_CLASSICAL_MLP_COMPARATOR"
            )
            mlp_metrics = mlp_row
            mlp_row["delta_pr_auc_vs_refined_mlp"] = 0.0
            mlp_row["delta_roc_auc_vs_refined_mlp"] = 0.0
            neural_rows.append(mlp_row)
        for result in qnn_confirmed:
            row = _flatten_result(result, "CONFIRMED_QNN_BLOCK_REPRESENTATIVE")
            row["delta_pr_auc_vs_refined_mlp"] = (
                float(row["pooled_oof_pr_auc"])
                - float(mlp_metrics["pooled_oof_pr_auc"])
                if mlp_metrics
                and row["pooled_oof_pr_auc"] is not None
                and mlp_metrics["pooled_oof_pr_auc"] is not None
                else None
            )
            row["delta_roc_auc_vs_refined_mlp"] = (
                float(row["pooled_oof_roc_auc"])
                - float(mlp_metrics["pooled_oof_roc_auc"])
                if mlp_metrics
                and row["pooled_oof_roc_auc"] is not None
                and mlp_metrics["pooled_oof_roc_auc"] is not None
                else None
            )
            neural_rows.append(row)
        _write_csv(report_dir / "06_confirmed_mlp_vs_qnn.csv", neural_rows)

        summary_lines.extend(
            [
                "## Confirmation i porównanie MLP–QNN",
                "",
                f"Sloty confirmation modeli klasycznych/MLP: **{confirmation.get('primary_confirmation_slots')}**. "
                f"Sloty QNN: **{confirmation.get('qnn_confirmation_slots')}**.",
                "",
            ]
        )
        for row in neural_rows:
            label = (
                "Refined MLP"
                if row["family"] == "pytorch_mlp"
                else f"QNN {row['feature_block']}"
            )
            summary_lines.append(
                f"- **{label}**: PR-AUC **{_format_metric(row['pooled_oof_pr_auc'])}**, "
                f"ROC-AUC **{_format_metric(row['pooled_oof_roc_auc'])}**, "
                f"ΔPR-AUC vs MLP **{_format_metric(row.get('delta_pr_auc_vs_refined_mlp'))}**."
            )
        summary_lines.extend(
            [
                "",
                "> Uwaga metodologiczna: dodatkowy refinement MLP jest analizą wtórną, "
                "zadeklarowaną po coarse searchu i przed QNN. Nie zmienia głównego, "
                "zamrożonego rankingu modeli klasycznych; służy wyłącznie porównaniu "
                "klasycznej sieci neuronowej z QNN.",
                "",
            ]
        )

    bootstrap_path = output_dir / "neural_comparison_clustered_bootstrap.json"
    if bootstrap_path.is_file():
        bootstrap = load_json(bootstrap_path)
        source_hashes[bootstrap_path.name] = file_sha256(bootstrap_path)
        bootstrap_rows: list[dict[str, Any]] = []
        for row in list(bootstrap.get("rows") or []):
            pr_ci = dict(row.get("pr_auc_ci") or {})
            roc_ci = dict(row.get("roc_auc_ci") or {})
            delta_pr_ci = dict(row.get("delta_pr_auc_ci") or {})
            delta_roc_ci = dict(row.get("delta_roc_auc_ci") or {})
            bootstrap_rows.append(
                {
                    "comparison_role": row.get("comparison_role"),
                    "family": row.get("family"),
                    "feature_block": row.get("feature_block"),
                    "configuration_id": row.get("configuration_id"),
                    "selected_ansatz_id": row.get("selected_ansatz_id"),
                    "point_pr_auc": row.get("point_pr_auc"),
                    "pr_auc_ci_lower": pr_ci.get("lower_2_5"),
                    "pr_auc_ci_median": pr_ci.get("median"),
                    "pr_auc_ci_upper": pr_ci.get("upper_97_5"),
                    "point_roc_auc": row.get("point_roc_auc"),
                    "roc_auc_ci_lower": roc_ci.get("lower_2_5"),
                    "roc_auc_ci_median": roc_ci.get("median"),
                    "roc_auc_ci_upper": roc_ci.get("upper_97_5"),
                    "point_delta_pr_auc_vs_mlp": row.get(
                        "point_delta_pr_auc_vs_mlp"
                    ),
                    "delta_pr_auc_ci_lower": delta_pr_ci.get("lower_2_5"),
                    "delta_pr_auc_ci_median": delta_pr_ci.get("median"),
                    "delta_pr_auc_ci_upper": delta_pr_ci.get("upper_97_5"),
                    "point_delta_roc_auc_vs_mlp": row.get(
                        "point_delta_roc_auc_vs_mlp"
                    ),
                    "delta_roc_auc_ci_lower": delta_roc_ci.get("lower_2_5"),
                    "delta_roc_auc_ci_median": delta_roc_ci.get("median"),
                    "delta_roc_auc_ci_upper": delta_roc_ci.get("upper_97_5"),
                    "bootstrap_probability_delta_pr_auc_gt_0": row.get(
                        "bootstrap_probability_delta_pr_auc_gt_0"
                    ),
                    "bootstrap_probability_delta_roc_auc_gt_0": row.get(
                        "bootstrap_probability_delta_roc_auc_gt_0"
                    ),
                }
            )
        _write_csv(
            report_dir / "08_neural_comparison_clustered_bootstrap.csv",
            bootstrap_rows,
        )
        method = dict(bootstrap.get("method") or {})
        summary_lines.extend(
            [
                "## Niepewność porównania MLP–QNN",
                "",
                f"Status clustered bootstrap: **{bootstrap.get('status')}**. "
                f"Poprawne replikacje: **{method.get('replicates_valid')}**/"
                f"**{method.get('replicates_requested')}**, jednostka losowania: "
                f"`{method.get('resampling_unit')}`, seed: `{method.get('seed')}`.",
                "",
            ]
        )
        for row in list(bootstrap.get("rows") or []):
            label = (
                "Refined MLP"
                if row.get("family") == "pytorch_mlp"
                else f"QNN {row.get('feature_block')}"
            )
            summary_lines.append(
                f"- **{label}**: PR-AUC **{_format_metric(row.get('point_pr_auc'))}** "
                f"(95% CI {_format_interval(row.get('pr_auc_ci'))}), "
                f"ΔPR-AUC vs MLP **{_format_metric(row.get('point_delta_pr_auc_vs_mlp'))}** "
                f"(95% CI {_format_interval(row.get('delta_pr_auc_ci'))})."
            )
        summary_lines.extend(
            [
                "",
                "> Te przedziały są sparowane, ale dotyczą rozwojowego OOF i są "
                "warunkowe względem wybranych konfiguracji. Nie są niezależnym "
                "testem, nie korygują selekcji modeli, a prawdopodobieństwo "
                "bootstrapowe nie jest wartością p.",
                "",
            ]
        )

    primary_ranking_path = output_dir / "final_primary_development_ranking.json"
    if primary_ranking_path.is_file():
        primary_ranking = load_json(primary_ranking_path)
        source_hashes[primary_ranking_path.name] = file_sha256(primary_ranking_path)
        ranking_rows = list(primary_ranking.get("family_representatives") or [])
        flat_ranking: list[dict[str, Any]] = []
        for row in ranking_rows:
            metrics = dict(row.get("metric_summary") or {})
            flat_ranking.append(
                {
                    "rank": row.get("rank"),
                    "family": row.get("family"),
                    "stage": row.get("stage"),
                    "feature_block": row.get("feature_block"),
                    "configuration_id": row.get("configuration_id"),
                    "training_seed": row.get("training_seed"),
                    "status": row.get("status"),
                    "pooled_oof_pr_auc": metrics.get("pooled_oof_pr_auc"),
                    "pooled_oof_roc_auc": metrics.get("pooled_oof_roc_auc"),
                    "parameters": _json_cell(row.get("parameters") or {}),
                }
            )
        _write_csv(report_dir / "07_final_primary_family_ranking.csv", flat_ranking)
        winner = primary_ranking.get("global_winner")
        if isinstance(winner, dict):
            summary_lines.extend(
                [
                    "## Główny ranking rozwojowy",
                    "",
                    f"Globalny zwycięzca głównego protokołu: **{winner.get('family')}**, "
                    f"`{winner.get('configuration_id')}`, blok **{winner.get('feature_block')}**.",
                    "",
                ]
            )

    summary_path = report_dir / "summary.md"
    summary_path.write_text("\n".join(summary_lines).rstrip() + "\n", encoding="utf-8")
    report_manifest = {
        "schema_version": 1,
        "status": "COMPLETE",
        "source_output_dir": str(output_dir.resolve()),
        "source_manifest_sha256": source_hashes,
        "summary_md": str(summary_path.resolve()),
        "generated_tables": sorted(path.name for path in report_dir.glob("*.csv")),
        "protected_feature_years_opened": False,
    }
    manifest_path = report_dir / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(report_manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report-dir", required=True, type=Path)
    args = parser.parse_args()
    result = generate_report(args.output_dir.resolve(), args.report_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

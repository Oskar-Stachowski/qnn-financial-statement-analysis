"""Initial pre-resolver freeze-gate diagnostics for PIT-B.

The script is audit-only: it does not change target thresholds, train models,
use feature years 2023--2024, or rebuild the research universe.  Its revenue
concept-sensitivity output is an explicit input to the later fixed 60-row
review sample.  The final post-resolver verdict is compiled by stages 16--19.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.data.target_candidate_v2_pit import (
    COMPANYFACTS_DIR,
    TARGET_SIGNALS,
    build_anchors,
    choose_year_anchor,
    load_config,
    parse_scope,
    strategy_evaluations,
    submission_metadata,
)


BASE_DIR = Path(__file__).resolve().parents[2]
ROWS_PATH = BASE_DIR / "data" / "interim" / "target_candidate_v2_pit_b.csv"
REPORT_DIR = BASE_DIR / "data" / "reports"
PREFIX = REPORT_DIR / "target_candidate_v2_pit_b_freeze_gate"
STATUS_ORDER = ("available", "missing", "ambiguous", "hard_exclude")
PRIMITIVES = (
    "assets",
    "liabilities",
    "current_assets",
    "current_liabilities",
    "revenues",
    "net_income",
    "operating_cash_flow",
)


def semicolon_counts(series: pd.Series) -> pd.DataFrame:
    counter: Counter[str] = Counter()
    for value in series.fillna(""):
        counter.update(item for item in str(value).split(";") if item)
    return pd.DataFrame(
        [
            {"reason": reason, "observation_count": int(count)}
            for reason, count in sorted(
                counter.items(), key=lambda item: (-item[1], item[0])
            )
        ]
    )


def status_distribution(frame: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    counts = (
        frame.groupby([*groups, "target_status"], dropna=False)
        .size()
        .unstack(fill_value=0)
    )
    for status in STATUS_ORDER:
        if status not in counts:
            counts[status] = 0
    counts = counts[list(STATUS_ORDER)]
    counts["total"] = counts.sum(axis=1)
    for status in STATUS_ORDER:
        counts[f"{status}_rate"] = counts[status] / counts["total"]
    return counts.reset_index()


def within_year_quartile(values: pd.Series, years: pd.Series, label: str) -> pd.Series:
    output = pd.Series("missing", index=values.index, dtype=object)
    for _, indices in years.groupby(years).groups.items():
        subset = values.loc[indices]
        valid = subset[subset.notna() & np.isfinite(subset) & (subset > 0)]
        if valid.empty:
            continue
        ranks = valid.rank(method="first")
        bins = min(4, len(valid))
        labels = [f"Q{index}_{label}" for index in range(1, bins + 1)]
        output.loc[valid.index] = pd.qcut(ranks, q=bins, labels=labels).astype(str)
    return output


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = numerator / denominator.where(denominator.abs() > 1_000)
    return result.replace([np.inf, -np.inf], np.nan)


def add_feature_diagnostics(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    values = {
        primitive: pd.to_numeric(
            frame[f"A_current_t_{primitive}_value"], errors="coerce"
        )
        for primitive in PRIMITIVES
    }
    frame = frame.copy()
    frame["log10_assets_t"] = np.log10(values["assets"].where(values["assets"] > 0))
    frame["log10_positive_revenues_t"] = np.log10(
        values["revenues"].where(values["revenues"] > 0)
    )
    frame["roa_t"] = safe_ratio(values["net_income"], values["assets"])
    frame["ocf_assets_t"] = safe_ratio(values["operating_cash_flow"], values["assets"])
    frame["current_ratio_t"] = safe_ratio(
        values["current_assets"], values["current_liabilities"]
    )
    frame["liabilities_assets_t"] = safe_ratio(values["liabilities"], values["assets"])
    frame["revenues_assets_t"] = safe_ratio(values["revenues"], values["assets"])
    frame["assets_size_quartile"] = within_year_quartile(
        values["assets"], frame["feature_year"], "assets"
    )
    frame["revenues_size_quartile"] = within_year_quartile(
        values["revenues"], frame["feature_year"], "revenues"
    )
    frame["missing_primitives_t"] = sum(
        ~frame[f"A_current_t_{primitive}_status"].eq("selected")
        for primitive in PRIMITIVES
    )
    labels = {
        "log10_assets_t": "log10 assets t",
        "log10_positive_revenues_t": "log10 positive revenues t",
        "roa_t": "ROA t",
        "ocf_assets_t": "OCF/assets t",
        "current_ratio_t": "current ratio t",
        "liabilities_assets_t": "liabilities/assets t",
        "revenues_assets_t": "revenues/assets t",
    }
    return frame, labels


def smd(left: pd.Series, reference: pd.Series) -> float:
    left = pd.to_numeric(left, errors="coerce").dropna()
    reference = pd.to_numeric(reference, errors="coerce").dropna()
    if len(left) < 2 or len(reference) < 2:
        return np.nan
    combined = pd.concat([left, reference])
    lower, upper = combined.quantile([0.01, 0.99])
    left = left.clip(lower, upper)
    reference = reference.clip(lower, upper)
    pooled = np.sqrt((left.var(ddof=1) + reference.var(ddof=1)) / 2)
    if not np.isfinite(pooled) or pooled == 0:
        return np.nan
    return float((left.mean() - reference.mean()) / pooled)


def feature_summary(frame: pd.DataFrame, labels: dict[str, str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    reference = frame[frame["target_status"].eq("available")]
    for column, label in labels.items():
        for status in STATUS_ORDER:
            subset = frame[frame["target_status"].eq(status)]
            values = pd.to_numeric(subset[column], errors="coerce")
            valid = values.dropna()
            rows.append(
                {
                    "feature": label,
                    "status": status,
                    "group_n": int(len(subset)),
                    "available_n": int(len(valid)),
                    "coverage": float(values.notna().mean()) if len(values) else np.nan,
                    "q25": float(valid.quantile(0.25)) if len(valid) else np.nan,
                    "median": float(valid.median()) if len(valid) else np.nan,
                    "q75": float(valid.quantile(0.75)) if len(valid) else np.nan,
                    "smd_vs_available": (
                        0.0 if status == "available" else smd(valid, reference[column])
                    ),
                }
            )
    return pd.DataFrame(rows)


def primitive_status_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for primitive in PRIMITIVES:
        counts = frame[f"B_{primitive}_status"].fillna("not_evaluated").value_counts()
        for status, count in counts.items():
            rows.append(
                {
                    "primitive": primitive,
                    "primitive_status": status,
                    "observation_count": int(count),
                    "share_all": float(count / len(frame)),
                }
            )
    return pd.DataFrame(rows)


def signal_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for signal in TARGET_SIGNALS:
        for status in ("all", *STATUS_ORDER):
            subset = (
                frame if status == "all" else frame[frame["target_status"].eq(status)]
            )
            rows.append(
                {
                    "signal": signal,
                    "target_status": status,
                    "n": int(len(subset)),
                    "available_n": int(subset[signal].notna().sum()),
                    "coverage": float(subset[signal].notna().mean())
                    if len(subset)
                    else np.nan,
                }
            )
    return pd.DataFrame(rows)


def revenue_d5(evaluation: dict[str, Any], minimum: float) -> int | None:
    comparative = float(evaluation["roles"]["comparative_t"]["value"])
    current = float(evaluation["roles"]["current_t1"]["value"])
    if comparative <= minimum or current <= minimum:
        return None
    return int(current / comparative - 1.0 <= -0.10)


def revenue_sensitivity(frame: pd.DataFrame) -> pd.DataFrame:
    config = load_config()
    scope = parse_scope(config)
    policy = config["primitive_concepts"]["revenues"]
    diagnostics = frame[
        frame["B_revenues_semantic_diagnostic"].eq(
            "lower_priority_revenue_concepts_disagree"
        )
    ]
    output: list[dict[str, Any]] = []
    for cik10, company_rows in diagnostics.groupby("cik10"):
        payload = json.loads(
            (COMPANYFACTS_DIR / f"CIK{cik10}.json").read_text(encoding="utf-8")
        )
        anchors = build_anchors(
            payload.get("facts", {}), submission_metadata(cik10), config, scope
        )
        by_year: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for anchor in anchors:
            by_year[int(anchor["resolved_fiscal_year"])].append(anchor)
        for _, row in company_rows.iterrows():
            year = int(row["feature_year"])
            anchor_t = choose_year_anchor(by_year.get(year, []))
            anchor_t1 = choose_year_anchor(by_year.get(year + 1, []))
            anchor_tm1 = choose_year_anchor(by_year.get(year - 1, []))
            if anchor_t is None or anchor_t1 is None:
                continue
            specs = {
                "comparative_t": (
                    anchor_t["report_end"],
                    anchor_tm1["report_end"] + timedelta(days=1)
                    if anchor_tm1
                    else None,
                ),
                "current_t1": (
                    anchor_t1["report_end"],
                    anchor_t["report_end"] + timedelta(days=1),
                ),
            }
            evaluations = strategy_evaluations(policy, anchor_t1, specs, scope)
            complete = sorted(
                [
                    evaluation
                    for evaluation in evaluations
                    if all(
                        evaluation["roles"][role]["status"] == "selected"
                        for role in ("comparative_t", "current_t1")
                    )
                ],
                key=lambda evaluation: evaluation["priority"],
            )
            if len(complete) < 2:
                continue
            selected, alternative = complete[0], complete[1]
            selected_d5 = revenue_d5(selected, scope.minimum_denominator_usd)
            alternative_d5 = revenue_d5(alternative, scope.minimum_denominator_usd)
            other_signals = [
                row.get(signal)
                for signal in (
                    "D1_roa",
                    "D2_ocf_assets",
                    "D3_current_ratio",
                    "D4_liabilities_assets",
                )
            ]
            scores_evaluable = (
                selected_d5 is not None
                and alternative_d5 is not None
                and all(pd.notna(value) for value in other_signals)
            )
            selected_score = alternative_score = selected_target = (
                alternative_target
            ) = pd.NA
            if scores_evaluable:
                other_score = sum(int(value) for value in other_signals)
                selected_score = other_score + int(selected_d5)
                alternative_score = other_score + int(alternative_d5)
                selected_target = int(selected_score >= 3)
                alternative_target = int(alternative_score >= 3)
            selected_comp = selected["roles"]["comparative_t"]
            selected_curr = selected["roles"]["current_t1"]
            alternative_comp = alternative["roles"]["comparative_t"]
            alternative_curr = alternative["roles"]["current_t1"]
            output.append(
                {
                    "cik10": cik10,
                    "company_name": row.get("company_name", ""),
                    "feature_year": year,
                    "split": row.get("split", ""),
                    "research_sector": row.get("research_sector", ""),
                    "sic": row.get("sic", ""),
                    "target_status": row.get("target_status", ""),
                    "anchor_t1_accession": anchor_t1["accn"],
                    "anchor_t1_primary_document": anchor_t1.get("primary_document", ""),
                    "selected_strategy": selected["name"],
                    "selected_comparative_tag": selected_comp.get("tag", ""),
                    "selected_current_tag": selected_curr.get("tag", ""),
                    "selected_comparative_value": selected_comp["value"],
                    "selected_current_value": selected_curr["value"],
                    "selected_d5": selected_d5,
                    "alternative_strategy": alternative["name"],
                    "alternative_comparative_tag": alternative_comp.get("tag", ""),
                    "alternative_current_tag": alternative_curr.get("tag", ""),
                    "alternative_comparative_value": alternative_comp["value"],
                    "alternative_current_value": alternative_curr["value"],
                    "alternative_d5": alternative_d5,
                    "selected_score": selected_score,
                    "alternative_score": alternative_score,
                    "selected_target": selected_target,
                    "alternative_target": alternative_target,
                    "actual_target_candidate_v2": row.get("target_candidate_v2", pd.NA),
                    "d5_evaluable": selected_d5 is not None
                    and alternative_d5 is not None,
                    "d5_changed": (
                        selected_d5 is not None
                        and alternative_d5 is not None
                        and selected_d5 != alternative_d5
                    ),
                    "score_evaluable": scores_evaluable,
                    "score_changed": (
                        scores_evaluable and selected_score != alternative_score
                    ),
                    "raw_threshold_target_changed": (
                        scores_evaluable and selected_target != alternative_target
                    ),
                    "available_target_changed": (
                        row.get("target_status") == "available"
                        and scores_evaluable
                        and selected_target != alternative_target
                    ),
                }
            )
    return pd.DataFrame(output)


def stratified_revenue_review(sensitivity: pd.DataFrame) -> pd.DataFrame:
    changed = sensitivity[
        sensitivity["d5_changed"] | sensitivity["raw_threshold_target_changed"]
    ].copy()
    changed["concept_pair"] = (
        changed["selected_strategy"] + " -> " + changed["alternative_strategy"]
    )
    changed["year_band"] = pd.cut(
        changed["feature_year"],
        bins=[2010, 2014, 2018, 2022],
        labels=["2011-2014", "2015-2018", "2019-2022"],
    ).astype(str)
    changed = changed.sort_values(
        [
            "available_target_changed",
            "concept_pair",
            "research_sector",
            "year_band",
            "feature_year",
            "cik10",
        ],
        ascending=[False, True, True, True, True, True],
    )
    sample = changed.groupby(
        ["concept_pair", "research_sector", "year_band"], group_keys=False
    ).head(1)
    # Keep the review manageable while preserving all concept-pair coverage.
    guaranteed = changed.groupby("concept_pair", group_keys=False).head(1)
    sample = pd.concat([guaranteed, sample], ignore_index=True).drop_duplicates(
        ["cik10", "feature_year"]
    )
    sample = sample.head(32).copy()
    sample["manual_review_outcome"] = "pending"
    sample["manual_preferred_economic_concept"] = ""
    sample["manual_evidence_url"] = ""
    sample["manual_notes"] = ""
    return sample


def pct(value: float) -> str:
    return f"{value:.2%}"


def build_markdown(
    frame: pd.DataFrame,
    by_year: pd.DataFrame,
    by_sector: pd.DataFrame,
    features: pd.DataFrame,
    primitive_status: pd.DataFrame,
    revenue: pd.DataFrame,
) -> str:
    status = frame["target_status"].value_counts()
    lines = [
        "# Initial pre-resolver freeze-gate audit — target_candidate_v2 PIT B",
        "",
        "Status: historyczny audyt przed poprawką finalnego resolvera revenues. Definicja targetu nie została zmieniona; modeli nie trenowano; feature years 2023–2024 nie użyto. Finalny werdykt powstaje w etapach 16–19.",
        "",
        "## Populacja PIT B",
        "",
        "| Status | N | Udział |",
        "|---|---:|---:|",
    ]
    for name in STATUS_ORDER:
        value = int(status.get(name, 0))
        lines.append(f"| {name} | {value:,} | {value / len(frame):.2%} |")
    lines.extend(
        [
            "",
            "## Status według roku",
            "",
            "| Rok | N | Available | Missing | Ambiguous | Hard-exclude |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in by_year.iterrows():
        lines.append(
            f"| {int(row['feature_year'])} | {int(row['total']):,} | "
            f"{row['available_rate']:.2%} | {row['missing_rate']:.2%} | "
            f"{row['ambiguous_rate']:.2%} | {row['hard_exclude_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Status według sektora",
            "",
            "| Sektor | N | Available | Missing | Ambiguous | Hard-exclude |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in by_sector.iterrows():
        lines.append(
            f"| {row['research_sector']} | {int(row['total']):,} | "
            f"{row['available_rate']:.2%} | {row['missing_rate']:.2%} | "
            f"{row['ambiguous_rate']:.2%} | {row['hard_exclude_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Revenue concept sensitivity",
            "",
            f"Diagnostyki: {len(revenue):,}.",
        ]
    )
    for flag, evaluable, label in (
        ("d5_changed", "d5_evaluable", "D5"),
        ("score_changed", "score_evaluable", "score"),
        ("available_target_changed", "score_evaluable", "dostępny target"),
    ):
        if label == "dostępny target":
            denominator = revenue["target_status"].eq("available") & revenue[evaluable]
        else:
            denominator = revenue[evaluable]
        changed = denominator & revenue[flag]
        lines.append(
            f"- {label}: {int(changed.sum()):,}/{int(denominator.sum()):,} "
            f"({changed.sum() / denominator.sum():.2%}) zmian."
        )
    lines.extend(
        [
            "",
            "Szczegółowe tabele i ręczna kontrola są zapisane w artefaktach CSV. Werdykt i końcowa interpretacja są uzupełniane po manual review.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.read_csv(ROWS_PATH, dtype={"cik10": str}, low_memory=False)
    if frame["feature_year"].min() != 2011 or frame["feature_year"].max() != 2022:
        raise RuntimeError("Freeze-gate scope must be feature years 2011--2022")
    if set(frame["target_status"].dropna()) - set(STATUS_ORDER):
        raise RuntimeError("Unexpected target status")
    frame, feature_labels = add_feature_diagnostics(frame)

    by_year = status_distribution(frame, ["feature_year"])
    by_sector = status_distribution(frame, ["research_sector"])
    by_sic_major = status_distribution(frame, ["sic_major_group"])
    by_sic = status_distribution(frame, ["sic", "sic_description"])
    by_assets_size = status_distribution(frame, ["assets_size_quartile"])
    by_revenues_size = status_distribution(frame, ["revenues_size_quartile"])
    by_missing_t = status_distribution(frame, ["missing_primitives_t"])
    features = feature_summary(frame, feature_labels)
    primitive_status = primitive_status_summary(frame)
    signals = signal_coverage(frame)
    missing_reasons = semicolon_counts(frame["missing_reasons"])
    ambiguous_reasons = semicolon_counts(frame["ambiguous_reasons"])
    hard_reasons = semicolon_counts(frame["hard_exclude_reasons"])
    revenue = revenue_sensitivity(frame)
    review = stratified_revenue_review(revenue)

    artifacts = {
        "status_by_year": by_year,
        "status_by_sector": by_sector,
        "status_by_sic_major": by_sic_major,
        "status_by_sic": by_sic,
        "status_by_assets_size": by_assets_size,
        "status_by_revenues_size": by_revenues_size,
        "status_by_missing_primitives_t": by_missing_t,
        "feature_summary": features,
        "primitive_status": primitive_status,
        "signal_coverage": signals,
        "missing_reasons": missing_reasons,
        "ambiguous_reasons": ambiguous_reasons,
        "hard_exclude_reasons": hard_reasons,
        "revenue_concept_sensitivity": revenue,
        "revenue_manual_review": review,
    }
    for name, artifact in artifacts.items():
        artifact.to_csv(f"{PREFIX}_{name}.csv", index=False)

    audit = {
        "scope": {
            "feature_year_min": int(frame["feature_year"].min()),
            "feature_year_max": int(frame["feature_year"].max()),
            "feature_years_2023_2024_used": False,
            "models_trained": False,
            "target_definition_changed": False,
            "research_universe_changed": False,
            "target_frozen": False,
        },
        "rows": int(len(frame)),
        "status_counts": {
            status: int(frame["target_status"].eq(status).sum())
            for status in STATUS_ORDER
        },
        "accepted_at": {
            "rows_with_anchor_t_missing_accepted_at": int(
                (
                    frame["anchor_t_accn"].notna()
                    & frame["anchor_t_accepted_at"].isna()
                ).sum()
            ),
            "available_rows_missing_anchor_t1_accepted_at": int(
                (
                    frame["target_status"].eq("available")
                    & frame["anchor_t1_accepted_at"].isna()
                ).sum()
            ),
            "all_rows_with_anchor_t1_missing_accepted_at": int(
                (
                    frame["anchor_t1_accn"].notna()
                    & frame["anchor_t1_accepted_at"].isna()
                ).sum()
            ),
            "unique_accessions_missing_accepted_at": int(
                len(
                    set(
                        frame.loc[
                            frame["anchor_t_accn"].notna()
                            & frame["anchor_t_accepted_at"].isna(),
                            "anchor_t_accn",
                        ]
                    )
                    | set(
                        frame.loc[
                            frame["anchor_t1_accn"].notna()
                            & frame["anchor_t1_accepted_at"].isna(),
                            "anchor_t1_accn",
                        ]
                    )
                )
            ),
        },
        "revenue_sensitivity": {
            "diagnostic_rows": int(len(revenue)),
            "d5_evaluable": int(revenue["d5_evaluable"].sum()),
            "d5_changed": int(revenue["d5_changed"].sum()),
            "score_evaluable": int(revenue["score_evaluable"].sum()),
            "score_changed": int(revenue["score_changed"].sum()),
            "raw_threshold_target_changed": int(
                revenue["raw_threshold_target_changed"].sum()
            ),
            "available_evaluable": int(
                (
                    revenue["target_status"].eq("available")
                    & revenue["score_evaluable"]
                ).sum()
            ),
            "available_target_changed": int(revenue["available_target_changed"].sum()),
        },
        "manual_review_rows": int(len(review)),
    }
    Path(f"{PREFIX}.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    Path(f"{PREFIX}.md").write_text(
        build_markdown(frame, by_year, by_sector, features, primitive_status, revenue),
        encoding="utf-8",
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()

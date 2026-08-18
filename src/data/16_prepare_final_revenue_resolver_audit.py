"""Prepare the final, reproducible audit of the PIT-B revenue resolver.

The script is diagnostic only.  It uses feature years 2011--2022, does not
train a model, does not change D1--D5 or the score threshold, and does not
freeze the target.  Historical concept conflicts and revision deltas are
required inputs, so the fixed sample cannot depend on incidental file
availability.  Human judgements remain pending in a separate template and are
completed only by an explicit direct-statement review artifact.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    from src.data.revenue_manual_review import assert_expected_review_keys
except ModuleNotFoundError:  # direct script execution
    from revenue_manual_review import assert_expected_review_keys


BASE_DIR = Path(__file__).resolve().parents[2]
ROWS_PATH = BASE_DIR / "data" / "interim" / "target_candidate_v2_pit_b.csv"
REVISIONS_PATH = (
    BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_revision_deltas.csv"
)
OLD_CONFLICTS_PATH = (
    BASE_DIR
    / "data"
    / "reports"
    / "target_candidate_v2_pit_b_freeze_gate_revenue_concept_sensitivity.csv"
)
REPORT_DIR = BASE_DIR / "data" / "reports"
PREFIX = REPORT_DIR / "target_candidate_v2_pit_b_final_revenue_resolver"
REVIEW_TEMPLATE_PATH = Path(f"{PREFIX}_manual_review_template.csv")
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
SIGNALS = (
    "D1_roa",
    "D2_ocf_assets",
    "D3_current_ratio",
    "D4_liabilities_assets",
    "D5_revenues",
)
KEY = ["cik10", "feature_year"]
RANDOM_SEED = 20260817


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
    for indices in years.groupby(years).groups.values():
        valid = values.loc[indices]
        valid = valid[valid.notna() & np.isfinite(valid) & (valid > 0)]
        if valid.empty:
            continue
        bins = min(4, len(valid))
        ranks = valid.rank(method="first")
        labels = [f"Q{index}_{label}" for index in range(1, bins + 1)]
        output.loc[valid.index] = pd.qcut(ranks, q=bins, labels=labels).astype(str)
    return output


def safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return (numerator / denominator.where(denominator.abs() > 1_000)).replace(
        [np.inf, -np.inf], np.nan
    )


def add_feature_diagnostics(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str]]:
    frame = frame.copy()
    values = {
        primitive: pd.to_numeric(
            frame[f"A_current_t_{primitive}_value"], errors="coerce"
        )
        for primitive in PRIMITIVES
    }
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


def standardized_mean_difference(left: pd.Series, reference: pd.Series) -> float:
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
    available = frame[frame["target_status"].eq("available")]
    for column, label in labels.items():
        for status in STATUS_ORDER:
            subset = frame[frame["target_status"].eq(status)]
            values = pd.to_numeric(subset[column], errors="coerce")
            valid = values.dropna()
            rows.append(
                {
                    "feature": label,
                    "status": status,
                    "group_n": len(subset),
                    "available_n": len(valid),
                    "coverage": values.notna().mean() if len(values) else np.nan,
                    "q25": valid.quantile(0.25) if len(valid) else np.nan,
                    "median": valid.median() if len(valid) else np.nan,
                    "q75": valid.quantile(0.75) if len(valid) else np.nan,
                    "smd_vs_available": (
                        0.0
                        if status == "available"
                        else standardized_mean_difference(valid, available[column])
                    ),
                }
            )
    return pd.DataFrame(rows)


def reason_counts(series: pd.Series) -> pd.DataFrame:
    counts: Counter[str] = Counter()
    for value in series.fillna(""):
        counts.update(item for item in str(value).split(";") if item)
    return pd.DataFrame(
        [
            {"reason": reason, "observation_count": count}
            for reason, count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0])
            )
        ]
    )


def primitive_status_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for primitive in PRIMITIVES:
        column = f"B_{primitive}_status"
        counts = frame[column].fillna("not_evaluated").value_counts(dropna=False)
        for status, count in counts.items():
            rows.append(
                {
                    "primitive": primitive,
                    "status": str(status),
                    "observation_count": int(count),
                    "share_all": float(count / len(frame)) if len(frame) else np.nan,
                }
            )
    return pd.DataFrame(rows)


def signal_coverage_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for split in ("all", "train", "validation"):
        subset = frame if split == "all" else frame[frame["split"].eq(split)]
        for signal in SIGNALS:
            available = int(subset[signal].notna().sum())
            rows.append(
                {
                    "split": split,
                    "signal": signal,
                    "available": available,
                    "coverage": float(available / len(subset))
                    if len(subset)
                    else np.nan,
                }
            )
    return pd.DataFrame(rows)


def sole_missing_signal_summary(frame: pd.DataFrame) -> pd.DataFrame:
    not_hard_excluded = frame[~frame["target_status"].eq("hard_exclude")]
    missing_matrix = not_hard_excluded[list(SIGNALS)].isna()
    exactly_one = missing_matrix.sum(axis=1).eq(1)
    unavailable = not_hard_excluded[~not_hard_excluded["target_status"].eq("available")]
    rows: list[dict[str, Any]] = []
    for signal in SIGNALS:
        count = int((exactly_one & missing_matrix[signal]).sum())
        rows.append(
            {
                "signal": signal,
                "sole_missing_observations": count,
                "share_of_non_hard_excluded_unavailable": (
                    float(count / len(unavailable)) if len(unavailable) else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def stratified_head(
    frame: pd.DataFrame, group_columns: list[str], count: int, seed: int
) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    stable = frame.sort_values(KEY).reset_index(drop=True)
    shuffled = stable.sample(frac=1, random_state=seed)
    first = shuffled.groupby(group_columns, dropna=False, group_keys=False).head(1)
    selected = first.head(count)
    if len(selected) < count:
        remaining = shuffled.loc[~shuffled.index.isin(selected.index)]
        selected = pd.concat([selected, remaining.head(count - len(selected))])
    return selected


def prepare_manual_sample(frame: pd.DataFrame) -> pd.DataFrame:
    base_columns = [
        *KEY,
        "company_name",
        "split",
        "research_sector",
        "sic",
        "target_status",
        "D5_revenues",
        "anchor_t1_accn",
        "B_revenues_reason",
        "B_revenues_strategy",
        "B_comparative_t_revenues_value",
        "B_current_t1_revenues_value",
        "B_comparative_t_revenues_tag",
        "B_current_t1_revenues_tag",
        "B_comparative_t_revenues_accn",
        "B_current_t1_revenues_accn",
        "B_comparative_t_revenues_start",
        "B_comparative_t_revenues_end",
        "B_current_t1_revenues_start",
        "B_current_t1_revenues_end",
        "B_comparative_t_revenues_statement_file",
        "B_comparative_t_revenues_statement_short_name",
        "B_comparative_t_revenues_statement_long_name",
        "B_comparative_t_revenues_statement_role_uri",
        "B_comparative_t_revenues_statement_label",
        "B_comparative_t_revenues_statement_concepts",
        "B_comparative_t_revenues_statement_row_class",
        "B_comparative_t_revenues_statement_priority",
        "B_comparative_t_revenues_statement_scale",
        "B_comparative_t_revenues_statement_scale_label",
        "B_revenues_statement_candidate_count",
        "B_revenues_statement_candidates_json",
    ]
    available = (
        frame[frame["B_revenues_status"].eq("selected") & frame["D5_revenues"].notna()]
        .copy()
        .sort_values(KEY)
        .reset_index(drop=True)
    )
    available["year_band"] = pd.cut(
        available["feature_year"],
        bins=[2010, 2014, 2018, 2022],
        labels=["2011-2014", "2015-2018", "2019-2022"],
    ).astype(str)

    selections: list[pd.DataFrame] = []
    random_rows = stratified_head(
        available,
        ["year_band", "research_sector", "B_current_t1_revenues_tag"],
        20,
        RANDOM_SEED,
    ).copy()
    random_rows["review_category"] = "random_available_D5"
    selections.append(random_rows)

    conflicts = pd.read_csv(OLD_CONFLICTS_PATH, dtype={"cik10": str})
    conflicts["cik10"] = conflicts["cik10"].str.zfill(10)
    conflicts["old_concept_pair"] = (
        conflicts["selected_strategy"].astype(str)
        + " -> "
        + conflicts["alternative_strategy"].astype(str)
    )
    conflict_columns = [*KEY, "old_concept_pair"]
    conflict_rows = available.merge(conflicts[conflict_columns], on=KEY, how="inner")
    conflict_rows = stratified_head(
        conflict_rows,
        ["old_concept_pair", "research_sector", "year_band"],
        25,
        RANDOM_SEED + 1,
    ).copy()
    conflict_rows["review_category"] = "historical_concept_conflict"
    selections.append(conflict_rows)

    revisions = pd.read_csv(REVISIONS_PATH, dtype={"cik10": str})
    revisions["cik10"] = revisions["cik10"].str.zfill(10)
    revenue_revisions = revisions[revisions["variable"].eq("revenues")].copy()
    revenue_revisions["abs_revenue_revision_delta"] = pd.to_numeric(
        revenue_revisions["revision_delta"], errors="coerce"
    ).abs()
    revision_columns = [
        *KEY,
        "revision_delta",
        "scaled_revision_delta",
        "abs_revenue_revision_delta",
    ]
    outliers = available.merge(revenue_revisions[revision_columns], on=KEY, how="inner")
    absolute_outliers = (
        outliers.sort_values(
            ["abs_revenue_revision_delta", "feature_year", "cik10"],
            ascending=[False, True, True],
        )
        .head(10)
        .copy()
    )
    absolute_outliers["review_category"] = "largest_revenue_revision_delta_absolute"
    scaled_outliers = (
        outliers.assign(
            abs_scaled_revision_delta=pd.to_numeric(
                outliers["scaled_revision_delta"], errors="coerce"
            ).abs()
        )
        .sort_values(
            ["abs_scaled_revision_delta", "feature_year", "cik10"],
            ascending=[False, True, True],
        )
        .head(10)
        .copy()
    )
    scaled_outliers["review_category"] = "largest_revenue_revision_delta_scaled"
    selections.extend([absolute_outliers, scaled_outliers])

    combined = pd.concat(selections, ignore_index=True, sort=False)
    combined = combined.sort_values(["review_category", "feature_year", "cik10"])
    category_map = (
        combined.groupby(KEY)["review_category"]
        .agg(lambda values: ";".join(dict.fromkeys(values)))
        .rename("review_category")
        .reset_index()
    )
    extras = (
        combined.sort_values(KEY)
        .drop_duplicates(KEY)
        .drop(columns="review_category")
        .merge(category_map, on=KEY, how="left")
    )
    if len(extras) < 60:
        remaining = (
            available.loc[
                ~available.set_index(KEY).index.isin(extras.set_index(KEY).index)
            ]
            .sort_values(KEY)
            .sample(frac=1, random_state=RANDOM_SEED + 2)
        )
        fill = remaining.head(60 - len(extras)).copy()
        fill["review_category"] = "random_available_D5_fill"
        extras = pd.concat([extras, fill], ignore_index=True, sort=False)
    if len(extras) != 60:
        raise RuntimeError(f"Manual review sample must contain 60 rows: {len(extras)}")

    review = extras[
        [column for column in base_columns if column in extras.columns]
        + [
            column
            for column in (
                "year_band",
                "old_concept_pair",
                "revision_delta",
                "scaled_revision_delta",
                "abs_revenue_revision_delta",
                "abs_scaled_revision_delta",
                "review_category",
            )
            if column in extras.columns
        ]
    ].copy()
    review["statement_url"] = review.apply(
        lambda row: (
            "https://www.sec.gov/Archives/edgar/data/"
            f"{int(row['cik10'])}/{str(row['anchor_t1_accn']).replace('-', '')}/"
            f"{row['B_comparative_t_revenues_statement_file']}"
        ),
        axis=1,
    )
    review["local_statement_path"] = review.apply(
        lambda row: str(
            Path("data")
            / "raw"
            / "sec_filings"
            / "revenue_statement_evidence"
            / str(row["cik10"]).zfill(10)
            / str(row["anchor_t1_accn"]).replace("-", "")
            / str(row["B_comparative_t_revenues_statement_file"])
        ).replace("\\", "/"),
        axis=1,
    )
    review["manual_review_outcome"] = "pending"
    review["manual_statement_is_primary_consolidated"] = pd.NA
    review["manual_row_is_total_revenue"] = pd.NA
    review["manual_current_value_matches"] = pd.NA
    review["manual_comparative_value_matches"] = pd.NA
    review["manual_provenance_matches"] = pd.NA
    review["manual_selection_error"] = pd.NA
    review["manual_notes"] = ""
    review = review.sort_values(["review_category", "feature_year", "cik10"])
    return assert_expected_review_keys(review, label="generated manual-review template")


def require_manual_sample_inputs() -> None:
    required = {
        "PIT-B row-level build": ROWS_PATH,
        "revision deltas": REVISIONS_PATH,
        "historical revenue concept conflicts": OLD_CONFLICTS_PATH,
    }
    missing = [
        f"{label}: {path}" for label, path in required.items() if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Required audit inputs are missing; regenerate the preceding PIT-B "
            "stages before preparing the fixed manual-review sample:\n- "
            + "\n- ".join(missing)
        )


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    require_manual_sample_inputs()
    frame = pd.read_csv(ROWS_PATH, dtype={"cik10": str}, low_memory=False)
    frame["cik10"] = frame["cik10"].str.zfill(10)
    if (
        int(frame["feature_year"].min()) != 2011
        or int(frame["feature_year"].max()) != 2022
    ):
        raise RuntimeError("Audit scope must be feature years 2011--2022")
    if frame["feature_year"].isin([2023, 2024]).any():
        raise RuntimeError("Test feature years 2023--2024 must not be used")
    if set(frame["target_status"].dropna()) - set(STATUS_ORDER):
        raise RuntimeError("Unexpected target status")
    frame, feature_labels = add_feature_diagnostics(frame)

    tables = {
        "status_by_year": status_distribution(frame, ["feature_year"]),
        "status_by_sector": status_distribution(frame, ["research_sector"]),
        "status_by_sic_major": status_distribution(frame, ["sic_major_group"]),
        "status_by_sic": status_distribution(frame, ["sic", "sic_description"]),
        "status_by_assets_size": status_distribution(frame, ["assets_size_quartile"]),
        "status_by_revenues_size": status_distribution(
            frame, ["revenues_size_quartile"]
        ),
        "status_by_missing_primitives_t": status_distribution(
            frame, ["missing_primitives_t"]
        ),
        "feature_summary": feature_summary(frame, feature_labels),
        "missing_reasons": reason_counts(frame["missing_reasons"]),
        "ambiguous_reasons": reason_counts(frame["ambiguous_reasons"]),
        "hard_exclude_reasons": reason_counts(frame["hard_exclude_reasons"]),
        "primitive_status": primitive_status_summary(frame),
        "signal_coverage": signal_coverage_summary(frame),
        "sole_missing_signal": sole_missing_signal_summary(frame),
        "revenue_reason_counts": (
            frame.groupby(["B_revenues_status", "B_revenues_reason"], dropna=False)
            .size()
            .rename("observation_count")
            .reset_index()
            .sort_values("observation_count", ascending=False)
        ),
    }
    for name, table in tables.items():
        table.to_csv(f"{PREFIX}_{name}.csv", index=False)

    review = prepare_manual_sample(frame)
    review.to_csv(REVIEW_TEMPLATE_PATH, index=False)

    coverage: list[dict[str, Any]] = []
    balance: list[dict[str, Any]] = []
    for split in ("all", "train", "validation"):
        subset = frame if split == "all" else frame[frame["split"].eq(split)]
        available = subset[subset["target_status"].eq("available")]
        coverage.append(
            {
                "split": split,
                "rows": len(subset),
                "D5_available": int(subset["D5_revenues"].notna().sum()),
                "D5_coverage": float(subset["D5_revenues"].notna().mean()),
                "target_available": len(available),
                "target_coverage": float(len(available) / len(subset)),
            }
        )
        positives = int(available["target_candidate_v2"].sum())
        balance.append(
            {
                "split": split,
                "available": len(available),
                "positive": positives,
                "positive_rate": float(positives / len(available))
                if len(available)
                else None,
            }
        )

    audit = {
        "scope": {
            "feature_year_min": 2011,
            "feature_year_max": 2022,
            "feature_years_2023_2024_used": False,
            "models_trained": False,
            "target_definition_changed": False,
            "target_frozen": False,
        },
        "rows": len(frame),
        "target_status": {
            status: int(frame["target_status"].eq(status).sum())
            for status in STATUS_ORDER
        },
        "coverage": coverage,
        "class_balance": balance,
        "revenues": {
            "selected": int(frame["B_revenues_status"].eq("selected").sum()),
            "missing": int(frame["B_revenues_status"].eq("missing").sum()),
            "ambiguous": int(frame["B_revenues_status"].eq("ambiguous").sum()),
            "not_evaluated": int(frame["B_revenues_status"].isna().sum()),
        },
        "manual_review": {
            "rows": len(review),
            "template_path": str(REVIEW_TEMPLATE_PATH.relative_to(BASE_DIR)),
            "years": sorted(int(value) for value in review["feature_year"].unique()),
            "sectors": int(review["research_sector"].nunique()),
            "selected_tags": int(review["B_current_t1_revenues_tag"].nunique()),
            "historical_concept_pairs": int(
                review.get("old_concept_pair", pd.Series(dtype=object)).nunique()
            ),
            "status": "pending_direct_statement_review",
        },
    }
    Path(f"{PREFIX}.json").write_text(
        json.dumps(audit, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(audit, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

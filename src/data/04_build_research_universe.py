"""
Build the research universe from classified SEC company metadata.

Input:
- data/interim/sec_company_classified.csv

Output:
- data/processed/research_universe.csv
- data/processed/research_universe_excluded.csv
- data/processed/research_universe_summary.csv

This script selects companies that belong to the predefined research scope based
on the SIC-based classification created in the previous pipeline step.

The research universe is intended to be used in later steps for selecting SEC
filings, downloading financial statements, calculating financial ratios, and
building the final ML/QNN dataset.
"""

from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
INTERIM_DIR = BASE_DIR / "data" / "interim"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

INPUT_PATH = INTERIM_DIR / "sec_company_classified.csv"
OUTPUT_PATH = PROCESSED_DIR / "research_universe.csv"
EXCLUDED_OUTPUT_PATH = PROCESSED_DIR / "research_universe_excluded.csv"
SUMMARY_OUTPUT_PATH = PROCESSED_DIR / "research_universe_summary.csv"


TARGET_RESEARCH_SECTORS = {
    "Technology",
    "Retail",
    "Industrials_Manufacturing",
    "Extended_Candidate",
}

READ_DTYPES = {
    "cik10": str,
    "sic": str,
    "fiscal_year_end": str,
}

RESEARCH_UNIVERSE_SORT_COLUMNS = [
    "research_sector",
    "sic_int",
    "company_name",
    "cik10",
]

EXCLUDED_SORT_COLUMNS = [
    "exclude_reason",
    "research_sector",
    "company_name",
    "cik10",
]


REQUIRED_COLUMNS = {
    "cik",
    "cik10",
    "name_from_ticker_map",
    "name_from_sec",
    "entity_type",
    "sic",
    "sic_int",
    "sic_description",
    "sic_major_group",
    "research_sector",
    "include_in_research_universe",
    "exclude_reason",
    "classification_rule",
    "fiscal_year_end",
    "tickers",
    "exchanges",
}


FINAL_OUTPUT_COLUMNS = [
    "research_universe_id",
    "cik",
    "cik10",
    "company_name",
    "primary_ticker",
    "tickers",
    "primary_exchange",
    "exchanges",
    "entity_type",
    "sic",
    "sic_int",
    "sic_description",
    "sic_major_group",
    "research_sector",
    "fiscal_year_end",
    "classification_rule",
]


EXCLUDED_OUTPUT_COLUMNS = [
    "cik",
    "cik10",
    "company_name",
    "primary_ticker",
    "tickers",
    "primary_exchange",
    "exchanges",
    "entity_type",
    "sic",
    "sic_int",
    "sic_description",
    "sic_major_group",
    "research_sector",
    "include_in_research_universe",
    "exclude_reason",
    "classification_rule",
]


def validate_input(classified: pd.DataFrame) -> None:
    """Validate required input columns."""
    missing_columns = REQUIRED_COLUMNS - set(classified.columns)

    if missing_columns:
        raise ValueError(
            f"Missing required columns in {INPUT_PATH}: {sorted(missing_columns)}"
        )


def first_semicolon_value(value: object) -> str:
    """Return the first value from a semicolon-separated string."""
    if pd.isna(value):
        return ""

    return next(
        (item.strip() for item in str(value).split(";") if item.strip()),
        "",
    )


def build_company_name(row: pd.Series) -> str:
    """Prefer SEC company name and fall back to ticker-map name."""
    name_from_sec = str(row.get("name_from_sec", "") or "").strip()
    name_from_ticker_map = str(row.get("name_from_ticker_map", "") or "").strip()

    return name_from_sec or name_from_ticker_map


def add_normalized_columns(classified: pd.DataFrame) -> pd.DataFrame:
    """Add normalized helper columns used in the research universe."""
    result = classified.copy()

    result["cik10"] = result["cik10"].astype(str).str.zfill(10)
    result["company_name"] = result.apply(build_company_name, axis=1)
    result["primary_ticker"] = result["tickers"].apply(first_semicolon_value)
    result["primary_exchange"] = result["exchanges"].apply(first_semicolon_value)

    return result


def build_research_universe_mask(classified: pd.DataFrame) -> pd.Series:
    """Return mask for companies that belong to the target research universe."""
    include_mask = classified["include_in_research_universe"]
    sector_mask = classified["research_sector"].isin(TARGET_RESEARCH_SECTORS)
    entity_mask = classified["entity_type"].astype(str).str.lower() == "operating"
    sic_mask = classified["sic_int"].notna()

    return include_mask & sector_mask & entity_mask & sic_mask


def select_research_universe(classified: pd.DataFrame) -> pd.DataFrame:
    """Select companies that belong to the target research universe."""
    research_universe = classified[build_research_universe_mask(classified)].copy()

    research_universe = research_universe.sort_values(
        by=RESEARCH_UNIVERSE_SORT_COLUMNS,
    )

    research_universe.insert(
        loc=0,
        column="research_universe_id",
        value=range(1, len(research_universe) + 1),
    )

    return research_universe


def select_excluded_companies(classified: pd.DataFrame) -> pd.DataFrame:
    """Select companies that were excluded from the research universe."""
    selected_cik10 = set(
        classified.loc[
            classified["include_in_research_universe"],
            "cik10",
        ]
    )

    excluded = classified[
        ~classified["cik10"].isin(selected_cik10)
        | ~classified["research_sector"].isin(TARGET_RESEARCH_SECTORS)
    ].copy()

    excluded = excluded.sort_values(
        by=EXCLUDED_SORT_COLUMNS,
    )

    return excluded


def append_metric(rows: list[dict], metric: str, value: int) -> None:
    rows.append(
        {
            "metric": metric,
            "value": int(value),
        }
    )


def append_value_counts(
    rows: list[dict],
    series: pd.Series,
    metric_prefix: str,
    missing_label: str | None = None,
) -> None:
    for label, count in series.value_counts().items():
        if missing_label is not None and not label:
            label = missing_label
        append_metric(rows, f"{metric_prefix}__{label}", count)


def build_summary(classified: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    """Build summary statistics for the research-universe selection."""
    rows = []

    append_metric(rows, "input_rows", len(classified))
    append_metric(rows, "research_universe_rows", len(universe))
    append_metric(rows, "excluded_or_out_of_scope_rows", len(classified) - len(universe))
    append_metric(rows, "unique_ciks_in_research_universe", universe["cik10"].nunique())
    append_metric(
        rows,
        "unique_primary_tickers_in_research_universe",
        universe["primary_ticker"].replace("", pd.NA).nunique(),
    )
    append_metric(
        rows,
        "missing_primary_ticker_in_research_universe",
        (universe["primary_ticker"] == "").sum(),
    )
    append_metric(
        rows,
        "missing_primary_exchange_in_research_universe",
        (universe["primary_exchange"] == "").sum(),
    )
    append_value_counts(rows, universe["research_sector"], "sector_count")
    append_value_counts(rows, universe["sic_major_group"], "sic_major_group_count")
    append_value_counts(
        rows,
        universe["primary_exchange"],
        "primary_exchange_count",
        missing_label="missing",
    )

    return pd.DataFrame(rows)


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_PATH}. "
            "Run 03_classify_sec_companies_by_sic.py first."
        )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    classified = pd.read_csv(INPUT_PATH, dtype=READ_DTYPES)

    validate_input(classified)

    classified = add_normalized_columns(classified)

    research_universe = select_research_universe(classified)
    excluded_companies = select_excluded_companies(classified)
    summary = build_summary(classified, research_universe)

    research_universe = research_universe[FINAL_OUTPUT_COLUMNS]
    excluded_companies = excluded_companies[EXCLUDED_OUTPUT_COLUMNS]

    research_universe.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    excluded_companies.to_csv(EXCLUDED_OUTPUT_PATH, index=False, encoding="utf-8")
    summary.to_csv(SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8")

    print(f"Read classified companies:       {INPUT_PATH}")
    print(f"Saved research universe:         {OUTPUT_PATH}")
    print(f"Saved excluded companies:        {EXCLUDED_OUTPUT_PATH}")
    print(f"Saved research universe summary: {SUMMARY_OUTPUT_PATH}")
    print()
    print(f"Input rows:                      {len(classified):,}")
    print(f"Research universe rows:          {len(research_universe):,}")
    print(f"Excluded/out of scope rows:      {len(excluded_companies):,}")
    print()
    print("Research universe sector counts:")
    print(research_universe["research_sector"].value_counts().to_string())
    print()
    print("Research universe primary exchange counts:")
    print(research_universe["primary_exchange"].value_counts().to_string())


if __name__ == "__main__":
    main()

"""
Classify SEC companies by SIC for research-universe preparation.

Input:
- data/interim/sec_company_metadata.csv

Output:
- data/interim/sec_company_classified.csv

This script classifies companies using SEC SIC metadata downloaded in the
previous pipeline step. It assigns a simplified research-sector label and marks
whether a company should be included in the preliminary research universe.
"""

from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
INTERIM_DIR = BASE_DIR / "data" / "interim"

INPUT_PATH = INTERIM_DIR / "sec_company_metadata.csv"
OUTPUT_PATH = INTERIM_DIR / "sec_company_classified.csv"


SIC_MAJOR_GROUPS = [
    (100, 999, "Agriculture_Forestry_Fishing"),
    (1000, 1499, "Mining"),
    (1500, 1799, "Construction"),
    (2000, 3999, "Manufacturing"),
    (4000, 4999, "Transportation_Communications_Utilities"),
    (5000, 5199, "Wholesale_Trade"),
    (5200, 5999, "Retail_Trade"),
    (6000, 6799, "Finance_Insurance_Real_Estate"),
    (7000, 8999, "Services"),
    (9000, 9999, "Public_Administration_Or_Nonclassifiable"),
]

TECHNOLOGY_RANGES = [
    (3570, 3579),
    (3660, 3669),
    (3670, 3679),
    (3810, 3819),
    (3820, 3829),
    (7370, 7379),
]

TECHNOLOGY_KEYWORDS = [
    "computer",
    "software",
    "semiconductor",
    "data processing",
    "electronic",
    "communications equipment",
]

EXTENDED_CANDIDATE_RANGES = [
    (8000, 8099, "extended_candidate_healthcare_services"),
    (7000, 8999, "extended_candidate_services"),
    (5000, 5199, "extended_candidate_wholesale_trade"),
    (1500, 1799, "extended_candidate_construction"),
    (4000, 4899, "extended_candidate_transportation_communications"),
    (1000, 1499, "extended_candidate_energy_mining"),
]

SPAC_KEYWORDS = [
    "blank check",
    "special purpose acquisition",
    "acquisition corp",
    "acquisition corporation",
    "acquisition company",
    "acquisition co",
    "spac",
]

REIT_KEYWORDS = [
    "real estate investment trust",
    "reit",
]

FUND_TRUST_KEYWORDS = [
    "etf",
    "fund",
    "trust",
    "portfolio",
    "shares",
    "physical gold",
    "physical silver",
]


def parse_sic(value: object) -> int | None:
    """Parse SIC value to int. Return None when SIC is missing or invalid."""
    if pd.isna(value):
        return None

    value_as_str = str(value).strip()

    if not value_as_str:
        return None

    try:
        return int(float(value_as_str))
    except ValueError:
        return None


# https://www.sec.gov/search-filings/standard-industrial-classification-sic-code-list
def get_sic_major_group(sic: int | None) -> str:
    """Return simplified SIC major group label."""
    for start, end, label in SIC_MAJOR_GROUPS:
        if in_range(sic, start, end):
            return label

    return "Unknown"


def in_range(sic: int | None, start: int, end: int) -> bool:
    return sic is not None and start <= sic <= end


def in_any_range(sic: int | None, ranges: list[tuple[int, int]]) -> bool:
    return sic is not None and any(start <= sic <= end for start, end in ranges)


def contains_any(text: str, keywords: list[str]) -> bool:
    text = text.lower()
    return any(keyword in text for keyword in keywords)


def get_extended_candidate_rule(sic: int | None) -> str | None:
    for start, end, rule in EXTENDED_CANDIDATE_RANGES:
        if in_range(sic, start, end):
            return rule

    return None


def decision(
    research_sector: str,
    include: bool,
    exclude_reason: str,
    rule: str,
) -> tuple[str, bool, str, str]:
    return research_sector, include, exclude_reason, rule


def classify_research_sector(
    sic: int | None,
    sic_description: str,
    entity_type: str,
    name: str,
    download_status: str,
) -> tuple[str, bool, str, str]:
    """
    Return:
    - research_sector
    - include_in_research_universe
    - exclude_reason
    - classification_rule
    """
    entity_type_normalized = entity_type.strip().lower()
    download_status_normalized = download_status.strip().lower()
    text = f"{sic_description} {name}"

    if download_status_normalized != "success":
        return decision(
            "Unknown",
            False,
            "metadata_download_error",
            "download_status_not_success",
        )

    if sic is None:
        return decision(
            "Unknown",
            False,
            "missing_sic",
            "sic_missing_or_invalid",
        )

    if entity_type_normalized and entity_type_normalized != "operating":
        return decision(
            "Excluded_NonOperating_Entity",
            False,
            "non_operating_entity_type",
            "entity_type_not_operating",
        )

    if sic == 6770 or contains_any(text, SPAC_KEYWORDS):
        return decision(
            "Excluded_SPAC_Blank_Check",
            False,
            "spac_or_blank_check_company",
            "sic_6770_or_blank_check_keyword",
        )

    if sic == 6798 or contains_any(text, REIT_KEYWORDS):
        return decision(
            "Excluded_REIT",
            False,
            "reit_excluded",
            "sic_6798_or_reit_keyword",
        )

    if sic in {6722, 6726, 6732, 6733} or contains_any(text, FUND_TRUST_KEYWORDS):
        return decision(
            "Excluded_Fund_ETF_Trust",
            False,
            "fund_etf_or_trust_excluded",
            "fund_etf_trust_keyword_or_sic",
        )

    if in_range(sic, 6000, 6799):
        return decision(
            "Excluded_Financials_Insurance_RealEstate",
            False,
            "financials_insurance_real_estate_excluded",
            "sic_6000_6799",
        )

    if in_range(sic, 4900, 4999):
        return decision(
            "Excluded_Utilities",
            False,
            "utilities_excluded",
            "sic_4900_4999",
        )

    if in_any_range(sic, TECHNOLOGY_RANGES) or contains_any(
        sic_description,
        TECHNOLOGY_KEYWORDS,
    ):
        return decision(
            "Technology",
            True,
            "",
            "technology_sic_range_or_keyword",
        )

    if 5200 <= sic <= 5999:
        return decision(
            "Retail",
            True,
            "",
            "sic_5200_5999",
        )

    if 2000 <= sic <= 3999:
        return decision(
            "Industrials_Manufacturing",
            True,
            "",
            "sic_2000_3999_non_technology",
        )

    extended_candidate_rule = get_extended_candidate_rule(sic)
    if extended_candidate_rule:
        return decision(
            "Extended_Candidate",
            True,
            "",
            extended_candidate_rule,
        )

    return decision(
        "Other_Out_Of_Scope",
        False,
        "out_of_scope_sector",
        "not_in_target_research_sectors",
    )


def classify_row(row: pd.Series) -> pd.Series:
    """Classify one company metadata row."""
    sic = parse_sic(row.get("sic"))
    sic_description = str(row.get("sic_description", "") or "")
    entity_type = str(row.get("entity_type", "") or "")
    download_status = str(row.get("download_status", "") or "")

    name_from_sec = str(row.get("name_from_sec", "") or "")
    name_from_ticker_map = str(row.get("name_from_ticker_map", "") or "")
    name = name_from_sec or name_from_ticker_map

    (
        research_sector,
        include_in_research_universe,
        exclude_reason,
        classification_rule,
    ) = classify_research_sector(
        sic=sic,
        sic_description=sic_description,
        entity_type=entity_type,
        name=name,
        download_status=download_status,
    )

    return pd.Series(
        {
            "sic_int": sic,
            "sic_major_group": get_sic_major_group(sic),
            "research_sector": research_sector,
            "include_in_research_universe": include_in_research_universe,
            "exclude_reason": exclude_reason,
            "classification_rule": classification_rule,
        }
    )


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_PATH}. "
            "Run 02_download_sec_company_metadata.py first."
        )

    metadata = pd.read_csv(INPUT_PATH, dtype={"cik10": str, "sic": str, "fiscal_year_end": str})

    metadata["cik10"] = metadata["cik10"].astype(str).str.zfill(10)

    metadata["fiscal_year_end"] = metadata["fiscal_year_end"].astype(str).str.zfill(4)

    classification = metadata.apply(classify_row, axis=1)

    classified = pd.concat([metadata, classification], axis=1)

    output_columns = [
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
    ]

    classified = classified[output_columns]
    classified.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")

    included_count = int(classified["include_in_research_universe"].sum())
    excluded_count = len(classified) - included_count
    missing_sic_count = int(classified["sic_int"].isna().sum())

    print(f"Read company metadata:       {INPUT_PATH}")
    print(f"Saved classified companies:  {OUTPUT_PATH}")
    print(f"Rows:                        {len(classified):,}")
    print(f"Included in research scope:  {included_count:,}")
    print(f"Excluded/out of scope:       {excluded_count:,}")
    print(f"Missing SIC:                 {missing_sic_count:,}")
    print()
    print("Research sector counts:")
    print(classified["research_sector"].value_counts(dropna=False).to_string())
    print()
    print("Exclude reason counts:")
    print(classified["exclude_reason"].replace("", "included").value_counts().to_string())


if __name__ == "__main__":
    main()

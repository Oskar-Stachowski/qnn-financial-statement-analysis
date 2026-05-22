"""
Parse SEC Company Facts JSON files into configured financial variables.

Input:
- data/raw/companyfacts/CIK{cik10}.json
- data/processed/research_universe.csv
- configs/sec_tags.yaml
- configs/dataset_config.yaml

Output:
- data/interim/sec_facts_long.csv
- data/interim/sec_facts_wide.csv
- data/reports/xbrl_variable_coverage.csv
- data/reports/xbrl_tag_usage.csv
- data/reports/xbrl_missing_by_company.csv
- data/reports/xbrl_parse_quality_report.md

This script applies the XBRL tag mapping from configs/sec_tags.yaml to SEC
Company Facts. It keeps only accepted units and configured annual filing forms,
resolves duplicates deterministically, and does not impute missing values or
interpret the results.
"""

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
import json
import re

import pandas as pd
import yaml


BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
INTERIM_DIR = BASE_DIR / "data" / "interim"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
REPORTS_DIR = BASE_DIR / "data" / "reports"
CONFIG_DIR = BASE_DIR / "configs"

COMPANYFACTS_DIR = RAW_DIR / "companyfacts"
RESEARCH_UNIVERSE_PATH = PROCESSED_DIR / "research_universe.csv"
SEC_TAGS_CONFIG_PATH = CONFIG_DIR / "sec_tags.yaml"
DATASET_CONFIG_PATH = CONFIG_DIR / "dataset_config.yaml"

LONG_OUTPUT_PATH = INTERIM_DIR / "sec_facts_long.csv"
WIDE_OUTPUT_PATH = INTERIM_DIR / "sec_facts_wide.csv"
VARIABLE_COVERAGE_PATH = REPORTS_DIR / "xbrl_variable_coverage.csv"
TAG_USAGE_PATH = REPORTS_DIR / "xbrl_tag_usage.csv"
MISSING_BY_COMPANY_PATH = REPORTS_DIR / "xbrl_missing_by_company.csv"
QUALITY_REPORT_PATH = REPORTS_DIR / "xbrl_parse_quality_report.md"

ACCEPTED_UNITS = ("USD",)
DEFAULT_ACCEPTED_FORMS = ("10-K",)
ANNUAL_PERIOD_MIN_DAYS = 300
ANNUAL_PERIOD_MAX_DAYS = 400
MAX_END_YEAR_LEAD = 1
# Generous 10-K lag cap; removes prior-year comparative facts from later filings.
MAX_SELECTED_FILING_LAG_DAYS = 240
MAX_FILING_YEAR_LEAD = 1
NON_ANNUAL_RANK = 99
PROGRESS_EVERY_FILES = 100

COMPANY_COLUMNS = [
    "research_universe_id",
    "cik",
    "cik10",
    "company_name",
    "primary_ticker",
    "research_sector",
    "fiscal_year_end",
]

FLOW_VARIABLES = {
    "revenues",
    "net_income",
    "cost_of_revenue",
    "operating_costs",
    "depreciation_amortization",
    "ebit",
    "interest_expense",
    "capex",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
}

STOCK_VARIABLES = {
    "assets",
    "liabilities",
    "liabilities_and_equity",
    "current_assets",
    "current_liabilities",
    "equity",
    "cash",
    "accounts_receivable",
    "inventory",
    "ppe",
    "intangible_assets",
    "goodwill",
    "long_term_investments",
    "long_term_debt",
    "short_term_debt",
    "retained_earnings",
}

LONG_COLUMNS = [
    *COMPANY_COLUMNS,
    "company_year",
    "variable",
    "value",
    "unit",
    "namespace",
    "tag",
    "tier",
    "tag_priority",
    "form",
    "fp",
    "filed",
    "accn",
    "frame",
    "start",
    "end",
    "fy",
    "source_file",
]

REPORT_OUTPUTS = {
    VARIABLE_COVERAGE_PATH: [
        "variable",
        "configured_tag_count",
        "selected_observations",
        "companies_with_value",
        "company_years_with_value",
        "company_coverage_ratio",
        "company_year_coverage_ratio",
        "units",
        "forms",
    ],
    TAG_USAGE_PATH: [
        "variable",
        "tier",
        "tag_priority",
        "namespace",
        "tag",
        "selected_observations",
        "companies_with_selected_value",
        "company_years_with_selected_value",
        "units",
        "forms",
    ],
    MISSING_BY_COMPANY_PATH: [
        *COMPANY_COLUMNS,
        "company_year_count",
        "selected_observations",
        "variables_with_any_value",
        "variables_missing_any_value",
        "missing_variables",
    ],
}


def normalize_cik10(value: object) -> str:
    text = str(value).strip()
    if text.upper().startswith("CIK"):
        text = text[3:]
    if not text.isdigit() or len(text) > 10:
        raise ValueError(f"Invalid CIK: {value!r}")
    return text.zfill(10)


def tier_rank(tier: str) -> int:
    match = re.fullmatch(r"tier_(\d+)", tier)
    if not match:
        raise ValueError(f"Invalid tier name in {SEC_TAGS_CONFIG_PATH}: {tier}")
    return int(match.group(1))


def read_research_universe(path: Path) -> pd.DataFrame:
    companies = pd.read_csv(path, dtype=str).fillna("")
    if "cik10" not in companies.columns:
        raise ValueError(f"Missing required column 'cik10' in {path}")

    companies["cik10"] = companies["cik10"].map(normalize_cik10)
    return companies.drop_duplicates("cik10", keep="first")[COMPANY_COLUMNS].reset_index(drop=True)


def read_sec_tag_config(path: Path) -> tuple[list[str], pd.DataFrame]:
    if yaml is None:
        raise ImportError("PyYAML is required. Install it with: pip install PyYAML")

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict) or not config:
        raise ValueError(f"No tag rules parsed from {path}")

    unclassified_variables = set(config) - FLOW_VARIABLES - STOCK_VARIABLES
    if unclassified_variables:
        raise ValueError(
            "Variables must be classified as flow or stock before parsing: "
            f"{sorted(unclassified_variables)}"
        )

    rows = []
    for variable, tiers in config.items():
        if not isinstance(tiers, dict):
            raise ValueError(f"Invalid variable config for {variable!r} in {path}")

        tag_priority = 0
        for tier, tags in tiers.items():
            rank = tier_rank(str(tier))
            if not isinstance(tags, list):
                raise ValueError(f"Invalid tag list for {variable}.{tier} in {path}")

            for tag_config in tags:
                if not isinstance(tag_config, dict):
                    raise ValueError(f"Invalid tag config for {variable}.{tier} in {path}")

                namespace = str(tag_config.get("namespace", "")).strip()
                tag = str(tag_config.get("tag", "")).strip()
                if not namespace or not tag:
                    raise ValueError(f"Missing namespace or tag for {variable}.{tier} in {path}")

                tag_priority += 1
                rows.append(
                    {
                        "variable": variable,
                        "tier": str(tier),
                        "tier_rank": rank,
                        "namespace": namespace,
                        "tag": tag,
                        "tag_priority": tag_priority,
                    }
                )

    return list(config), pd.DataFrame(rows)


def read_dataset_scope(path: Path) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "accepted_forms": DEFAULT_ACCEPTED_FORMS,
        "start_year": None,
        "end_year": None,
        "target_horizon_years": None,
        "max_split_year": None,
    }
    if not path.exists():
        return scope

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    dataset_config = config.get("dataset", {}) if isinstance(config, dict) else {}
    target_config = config.get("target", {}) if isinstance(config, dict) else {}
    splits_config = config.get("splits", {}) if isinstance(config, dict) else {}
    configured_forms = dataset_config.get("forms", DEFAULT_ACCEPTED_FORMS)
    if not isinstance(configured_forms, (list, tuple)):
        raise ValueError(f"Invalid dataset.forms in {path}: expected a list")

    accepted_forms = tuple(
        str(form).strip().upper()
        for form in configured_forms
        if str(form).strip()
    )
    if not accepted_forms:
        raise ValueError(f"Invalid dataset.forms in {path}: at least one form is required")

    for key in ["start_year", "end_year"]:
        value = dataset_config.get(key)
        if value in (None, ""):
            continue
        try:
            scope[key] = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid dataset.{key} in {path}: {value!r}") from error

    scope["accepted_forms"] = accepted_forms
    scope["target_horizon_years"] = int(target_config.get("horizon_years", 0) or 0)
    split_years = []
    train_end_year = splits_config.get("train_end_year")
    if train_end_year not in (None, ""):
        split_years.append(int(train_end_year))
    for split_key in ["validation_years", "test_years"]:
        years = splits_config.get(split_key, [])
        if not isinstance(years, (list, tuple)):
            raise ValueError(f"Invalid splits.{split_key} in {path}: expected a list")
        split_years.extend(int(year) for year in years)
    scope["max_split_year"] = max(split_years) if split_years else None

    if scope["start_year"] is not None and scope["end_year"] is not None:
        if scope["start_year"] > scope["end_year"]:
            raise ValueError(
                f"Invalid dataset year range in {path}: "
                f"{scope['start_year']} > {scope['end_year']}"
            )

    if (
        scope["end_year"] is not None
        and scope["max_split_year"] is not None
        and scope["target_horizon_years"] is not None
    ):
        required_end_year = scope["max_split_year"] + scope["target_horizon_years"]
        if scope["end_year"] < required_end_year:
            raise ValueError(
                "dataset.end_year must include the target lookahead period: "
                f"got {scope['end_year']}, expected at least {required_end_year} "
                f"for max split year {scope['max_split_year']} and horizon "
                f"{scope['target_horizon_years']}."
            )

    return scope


def company_year_in_dataset_scope(company_year: str, dataset_scope: dict[str, Any]) -> bool:
    try:
        year = int(company_year)
    except (TypeError, ValueError):
        return False

    start_year = dataset_scope.get("start_year")
    end_year = dataset_scope.get("end_year")
    if start_year is not None and year < start_year:
        return False
    if end_year is not None and year > end_year:
        return False
    return True


def parse_iso_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def date_sort_value(value: object) -> int:
    parsed = parse_iso_date(value)
    return 0 if parsed is None else parsed.year * 10000 + parsed.month * 100 + parsed.day


def period_days(fact: dict[str, Any]) -> int | None:
    start_date = parse_iso_date(fact.get("start"))
    end_date = parse_iso_date(fact.get("end"))
    if start_date is None or end_date is None:
        return None
    return (end_date - start_date).days + 1


def frame_year(fact: dict[str, Any]) -> str | None:
    match = re.fullmatch(r"CY(\d{4})(?:Q4I)?", str(fact.get("frame", "") or ""))
    return match.group(1) if match else None


def has_valid_annual_flow_period(fact: dict[str, Any]) -> bool:
    days = period_days(fact)
    return days is not None and ANNUAL_PERIOD_MIN_DAYS <= days <= ANNUAL_PERIOD_MAX_DAYS


def annual_rank(
    fact: dict[str, Any],
    variable: str,
    accepted_forms: tuple[str, ...],
) -> int:
    if variable in FLOW_VARIABLES:
        return 0 if has_valid_annual_flow_period(fact) else NON_ANNUAL_RANK

    if str(fact.get("fp", "") or "").upper() == "FY":
        return 0

    days = period_days(fact)
    if days is not None and ANNUAL_PERIOD_MIN_DAYS <= days <= ANNUAL_PERIOD_MAX_DAYS:
        return 1

    frame = str(fact.get("frame", "") or "")
    if re.fullmatch(r"CY\d{4}", frame) or re.fullmatch(r"CY\d{4}Q4I", frame):
        return 2

    form = str(fact.get("form", "") or "").upper()
    if form in accepted_forms and fact.get("end") and not fact.get("start"):
        return 3

    return NON_ANNUAL_RANK


def form_rank(form: object, accepted_forms: tuple[str, ...]) -> int:
    form_text = str(form or "").upper()
    return accepted_forms.index(form_text) if form_text in accepted_forms else len(accepted_forms)


def fp_rank(fact: dict[str, Any]) -> int:
    return 0 if str(fact.get("fp", "") or "").upper() == "FY" else 1


def company_year_from_fact(fact: dict[str, Any]) -> str:
    fiscal_year = fact.get("fy")
    try:
        return str(int(fiscal_year))
    except (TypeError, ValueError):
        pass

    framed_year = frame_year(fact)
    if framed_year is not None:
        return framed_year

    end_date = parse_iso_date(fact.get("end"))
    if end_date is not None:
        return str(end_date.year)

    return "" if fiscal_year in (None, "") else str(fiscal_year)


def has_invalid_end_year(fact: dict[str, Any]) -> bool:
    end_date = parse_iso_date(fact.get("end"))
    if end_date is None:
        return False

    filed_date = parse_iso_date(fact.get("filed"))
    if filed_date is not None and end_date.year > filed_date.year + MAX_END_YEAR_LEAD:
        return True

    try:
        fiscal_year = int(fact.get("fy"))
    except (TypeError, ValueError):
        return False

    return end_date.year > fiscal_year + MAX_END_YEAR_LEAD


def fy_match_rank(fact: dict[str, Any], company_year: str) -> int:
    try:
        return 0 if str(int(fact.get("fy"))) == company_year else 2
    except (TypeError, ValueError):
        return 1


def frame_match_rank(fact: dict[str, Any], company_year: str) -> int:
    framed_year = frame_year(fact)
    if framed_year is None:
        return 1
    return 0 if framed_year == company_year else 2


def period_match_rank(fact: dict[str, Any], company_year: str) -> int:
    framed_year = frame_year(fact)
    try:
        fiscal_year = str(int(fact.get("fy")))
    except (TypeError, ValueError):
        fiscal_year = None

    frame_matches = framed_year == company_year
    fy_matches = fiscal_year == company_year

    if frame_matches and fy_matches:
        return 0
    if fy_matches:
        return 1
    if frame_matches:
        return 2
    if framed_year is None and fiscal_year is None:
        return 3
    return 4


def filing_lag_days(fact: dict[str, Any]) -> int:
    filed_date = parse_iso_date(fact.get("filed"))
    end_date = parse_iso_date(fact.get("end"))
    if filed_date is None or end_date is None:
        return 999_999

    lag_days = (filed_date - end_date).days
    return lag_days if lag_days >= 0 else 999_999


def has_excessive_filing_lag(fact: dict[str, Any]) -> bool:
    return filing_lag_days(fact) > MAX_SELECTED_FILING_LAG_DAYS


def has_invalid_filing_year(fact: dict[str, Any], company_year: str) -> bool:
    filed_date = parse_iso_date(fact.get("filed"))
    if filed_date is None:
        return False

    try:
        year = int(company_year)
    except (TypeError, ValueError):
        return False

    return filed_date.year > year + MAX_FILING_YEAR_LEAD


def candidate_sort_key(row: dict[str, Any]) -> tuple:
    return (
        row["_annual_rank"],
        row["_form_rank"],
        row["_fp_rank"],
        row["_period_match_rank"],
        row["_filing_lag_days"],
        row["_fy_match_rank"],
        row["_frame_match_rank"],
        row["_tier_rank"],
        row["tag_priority"],
        date_sort_value(row["filed"]),
        -date_sort_value(row["end"]),
        str(row["accn"]),
        str(row["namespace"]),
        str(row["tag"]),
        str(row["value"]),
    )


def build_candidate_row(
    company: dict[str, str],
    source_path: Path,
    rule: pd.Series,
    unit: str,
    fact: dict[str, Any],
    company_year: str,
    rank: int,
    accepted_forms: tuple[str, ...],
) -> dict[str, Any]:
    return {
        **company,
        "company_year": company_year,
        "variable": rule["variable"],
        "value": fact.get("val", ""),
        "unit": unit,
        "namespace": rule["namespace"],
        "tag": rule["tag"],
        "tier": rule["tier"],
        "tag_priority": int(rule["tag_priority"]),
        "form": fact.get("form", ""),
        "fp": fact.get("fp", ""),
        "filed": fact.get("filed", ""),
        "accn": fact.get("accn", ""),
        "frame": fact.get("frame", ""),
        "start": fact.get("start", ""),
        "end": fact.get("end", ""),
        "fy": fact.get("fy", ""),
        "source_file": str(source_path.relative_to(BASE_DIR)),
        "_annual_rank": rank,
        "_form_rank": form_rank(fact.get("form"), accepted_forms),
        "_fp_rank": fp_rank(fact),
        "_period_match_rank": period_match_rank(fact, company_year),
        "_filing_lag_days": filing_lag_days(fact),
        "_fy_match_rank": fy_match_rank(fact, company_year),
        "_frame_match_rank": frame_match_rank(fact, company_year),
        "_tier_rank": int(rule["tier_rank"]),
    }


def keep_best_candidate(
    selected_rows: dict[tuple[str, str, str], dict[str, Any]],
    row: dict[str, Any],
) -> None:
    key = (row["cik10"], row["variable"], row["company_year"])
    current = selected_rows.get(key)
    if current is None or candidate_sort_key(row) < candidate_sort_key(current):
        selected_rows[key] = row


def numeric_value(row: dict[str, Any]) -> float | None:
    try:
        return float(row["value"])
    except (TypeError, ValueError):
        return None


def build_derived_row(
    source_row: dict[str, Any],
    variable: str,
    tag: str,
    value: float,
    *additional_source_rows: dict[str, Any],
) -> dict[str, Any]:
    source_rows = (source_row, *additional_source_rows)
    row = source_row.copy()
    row.update(
        {
            "variable": variable,
            "value": value,
            "namespace": "derived",
            "tag": tag,
            "tier": "derived",
            "tag_priority": 0,
            "_annual_rank": max(row.get("_annual_rank", 0) for row in source_rows),
            "_form_rank": max(row.get("_form_rank", 0) for row in source_rows),
            "_fp_rank": max(row.get("_fp_rank", 0) for row in source_rows),
            "_period_match_rank": max(row.get("_period_match_rank", 0) for row in source_rows),
            "_filing_lag_days": max(row.get("_filing_lag_days", 0) for row in source_rows),
            "_fy_match_rank": max(row.get("_fy_match_rank", 0) for row in source_rows),
            "_frame_match_rank": max(row.get("_frame_match_rank", 0) for row in source_rows),
            "_tier_rank": 99,
        }
    )
    return row


def add_derived_balance_sheet_values(
    selected_rows: dict[tuple[str, str, str], dict[str, Any]],
    stats: dict[str, int],
) -> None:
    company_years = {
        (cik10, company_year)
        for cik10, variable, company_year in selected_rows
        if variable in {"liabilities_and_equity", "equity"}
    }

    for cik10, company_year in sorted(company_years):
        assets_key = (cik10, "assets", company_year)
        liabilities_key = (cik10, "liabilities", company_year)
        total_key = (cik10, "liabilities_and_equity", company_year)
        equity_key = (cik10, "equity", company_year)

        if total_key not in selected_rows:
            continue

        total_value = numeric_value(selected_rows[total_key])
        if total_value is None:
            stats["derived_assets_rejected"] += 1
            stats["derived_liabilities_rejected"] += 1
            continue
        if total_value < 0:
            stats["derived_assets_rejected"] += 1
            stats["derived_liabilities_rejected"] += 1
            continue

        if assets_key not in selected_rows:
            selected_rows[assets_key] = build_derived_row(
                selected_rows[total_key],
                "assets",
                "LiabilitiesAndStockholdersEquityAsAssets",
                total_value,
            )
            stats["derived_assets"] += 1

        if liabilities_key not in selected_rows and equity_key in selected_rows:
            equity_value = numeric_value(selected_rows[equity_key])
            if equity_value is None:
                stats["derived_liabilities_rejected"] += 1
                continue

            derived_value = total_value - equity_value
            if derived_value < 0:
                stats["derived_liabilities_rejected"] += 1
                continue

            selected_rows[liabilities_key] = build_derived_row(
                selected_rows[total_key],
                "liabilities",
                "LiabilitiesAndStockholdersEquityLessEquity",
                derived_value,
                selected_rows[equity_key],
            )
            stats["derived_liabilities"] += 1


def add_derived_operating_cost_values(
    selected_rows: dict[tuple[str, str, str], dict[str, Any]],
    stats: dict[str, int],
) -> None:
    company_years = {
        (cik10, company_year)
        for cik10, variable, company_year in selected_rows
        if variable in {"revenues", "ebit"}
    }

    for cik10, company_year in sorted(company_years):
        operating_costs_key = (cik10, "operating_costs", company_year)
        revenues_key = (cik10, "revenues", company_year)
        ebit_key = (cik10, "ebit", company_year)

        if revenues_key not in selected_rows or ebit_key not in selected_rows:
            continue

        revenues_value = numeric_value(selected_rows[revenues_key])
        ebit_value = numeric_value(selected_rows[ebit_key])
        if revenues_value is None or ebit_value is None:
            stats["derived_operating_costs_rejected"] += 1
            continue

        derived_value = revenues_value - ebit_value
        if derived_value < 0:
            stats["derived_operating_costs_rejected"] += 1
            continue

        replacing_existing = operating_costs_key in selected_rows
        selected_rows[operating_costs_key] = build_derived_row(
            selected_rows[revenues_key],
            "operating_costs",
            "RevenuesLessOperatingIncomeLoss",
            derived_value,
            selected_rows[ebit_key],
        )
        if replacing_existing:
            stats["derived_operating_costs_replaced"] += 1
        else:
            stats["derived_operating_costs"] += 1


def parse_companyfacts_file(
    company: dict[str, str],
    path: Path,
    rules: pd.DataFrame,
    dataset_scope: dict[str, Any],
    selected_rows: dict[tuple[str, str, str], dict[str, Any]],
    stats: dict[str, int],
) -> None:
    with path.open("r", encoding="utf-8") as f:
        all_facts = json.load(f).get("facts", {})

    if not isinstance(all_facts, dict):
        stats["files_without_facts"] += 1
        return

    accepted_forms = dataset_scope["accepted_forms"]
    for _, rule in rules.iterrows():
        units = all_facts.get(rule["namespace"], {}).get(rule["tag"], {}).get("units", {})
        if not isinstance(units, dict):
            continue

        for unit, facts in units.items():
            if not isinstance(facts, list):
                continue
            if unit not in ACCEPTED_UNITS:
                stats["facts_rejected_unit"] += len(facts)
                continue

            for fact in facts:
                if not isinstance(fact, dict):
                    continue
                form = str(fact.get("form", "") or "").strip().upper()
                if form not in accepted_forms:
                    stats["facts_rejected_form"] += 1
                    continue
                if fact.get("val") in (None, ""):
                    stats["facts_without_value"] += 1
                    continue

                company_year = company_year_from_fact(fact)
                if not company_year:
                    stats["facts_without_company_year"] += 1
                    continue
                if not company_year_in_dataset_scope(company_year, dataset_scope):
                    stats["facts_rejected_company_year"] += 1
                    continue

                if has_invalid_end_year(fact):
                    stats["facts_rejected_invalid_end_year"] += 1
                    continue
                if has_excessive_filing_lag(fact):
                    stats["facts_rejected_excessive_filing_lag"] += 1
                    continue
                if has_invalid_filing_year(fact, company_year):
                    stats["facts_rejected_filing_year"] += 1
                    continue

                if rule["variable"] in FLOW_VARIABLES and not has_valid_annual_flow_period(fact):
                    stats["facts_rejected_invalid_flow_period"] += 1
                    continue

                rank = annual_rank(fact, str(rule["variable"]), accepted_forms)
                if rank == NON_ANNUAL_RANK:
                    stats["facts_rejected_nonannual"] += 1
                    continue

                stats["candidate_facts"] += 1
                keep_best_candidate(
                    selected_rows,
                    build_candidate_row(
                        company,
                        path,
                        rule,
                        str(unit),
                        fact,
                        company_year,
                        rank,
                        accepted_forms,
                    ),
                )


def semicolon_join(series: pd.Series) -> str:
    return ";".join(sorted(str(value) for value in series.dropna().unique() if str(value)))


def selected_count(frame: pd.DataFrame, group_columns: list[str], name: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*group_columns, name])
    return frame.groupby(group_columns, dropna=False).size().reset_index(name=name)


def distinct_count(
    frame: pd.DataFrame,
    group_columns: list[str],
    value_columns: list[str],
    name: str,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=[*group_columns, name])
    counts = frame[group_columns + value_columns].drop_duplicates()
    return counts.groupby(group_columns, dropna=False).size().reset_index(name=name)


def build_wide_frame(long_frame: pd.DataFrame, companies: pd.DataFrame, variables: list[str]) -> pd.DataFrame:
    columns = [*COMPANY_COLUMNS, "company_year", *variables]
    if long_frame.empty:
        return pd.DataFrame(columns=columns)

    values = long_frame.pivot(
        index=["cik10", "company_year"],
        columns="variable",
        values="value",
    ).reset_index()
    values.columns.name = None

    wide = companies.merge(values, on="cik10", how="inner")
    for variable in variables:
        if variable not in wide.columns:
            wide[variable] = ""

    return wide[columns].sort_values(["cik10", "company_year"]).fillna("")


def build_variable_coverage(
    long_frame: pd.DataFrame,
    variables: list[str],
    rules: pd.DataFrame,
    company_count: int,
    wide_row_count: int,
) -> pd.DataFrame:
    coverage = pd.DataFrame({"variable": variables})
    configured = rules.groupby("variable").size().rename("configured_tag_count").reset_index()

    for counts in [
        selected_count(long_frame, ["variable"], "selected_observations"),
        distinct_count(long_frame, ["variable"], ["cik10"], "companies_with_value"),
        distinct_count(long_frame, ["variable"], ["cik10", "company_year"], "company_years_with_value"),
    ]:
        coverage = coverage.merge(counts, on="variable", how="left")

    if not long_frame.empty:
        units = long_frame.groupby("variable")["unit"].apply(semicolon_join).rename("units").reset_index()
        forms = long_frame.groupby("variable")["form"].apply(semicolon_join).rename("forms").reset_index()
        coverage = coverage.merge(units, on="variable", how="left").merge(forms, on="variable", how="left")

    coverage = coverage.merge(configured, on="variable", how="left")
    coverage["company_coverage_ratio"] = coverage["companies_with_value"].fillna(0).div(company_count).round(6)
    coverage["company_year_coverage_ratio"] = (
        coverage["company_years_with_value"].fillna(0).div(wide_row_count).round(6)
        if wide_row_count
        else 0
    )

    return coverage[
        [
            "variable",
            "configured_tag_count",
            "selected_observations",
            "companies_with_value",
            "company_years_with_value",
            "company_coverage_ratio",
            "company_year_coverage_ratio",
            "units",
            "forms",
        ]
    ].fillna({"units": "", "forms": ""}).fillna(0)


def build_tag_usage(long_frame: pd.DataFrame, rules: pd.DataFrame) -> pd.DataFrame:
    tag_columns = ["variable", "tier", "tag_priority", "namespace", "tag"]
    usage = rules[tag_columns].copy()

    for counts in [
        selected_count(long_frame, tag_columns, "selected_observations"),
        distinct_count(long_frame, tag_columns, ["cik10"], "companies_with_selected_value"),
        distinct_count(
            long_frame,
            tag_columns,
            ["cik10", "company_year"],
            "company_years_with_selected_value",
        ),
    ]:
        usage = usage.merge(counts, on=tag_columns, how="left")

    if not long_frame.empty:
        usage = usage.merge(
            long_frame.groupby(tag_columns)["unit"].apply(semicolon_join).rename("units").reset_index(),
            on=tag_columns,
            how="left",
        ).merge(
            long_frame.groupby(tag_columns)["form"].apply(semicolon_join).rename("forms").reset_index(),
            on=tag_columns,
            how="left",
        )

    return usage[REPORT_OUTPUTS[TAG_USAGE_PATH]].fillna({"units": "", "forms": ""}).fillna(0)


def build_missing_by_company(
    long_frame: pd.DataFrame,
    companies: pd.DataFrame,
    variables: list[str],
) -> pd.DataFrame:
    count_columns = [
        "company_year_count",
        "selected_observations",
        "variables_with_any_value",
        "variables_missing_any_value",
    ]

    if long_frame.empty:
        output = companies.copy()
        output["company_year_count"] = 0
        output["selected_observations"] = 0
        output["variables_with_any_value"] = 0
        output["variables_missing_any_value"] = len(variables)
        output["missing_variables"] = ";".join(variables)
        return output[REPORT_OUTPUTS[MISSING_BY_COMPANY_PATH]]

    grouped = long_frame.groupby("cik10")
    summary = pd.DataFrame(
        {
            "company_year_count": grouped["company_year"].nunique(),
            "selected_observations": grouped.size(),
            "present_variables": grouped["variable"].agg(lambda values: set(values)),
        }
    ).reset_index()
    summary["variables_with_any_value"] = summary["present_variables"].map(len)
    summary["missing_variables"] = summary["present_variables"].map(
        lambda present: ";".join(variable for variable in variables if variable not in present)
    )
    summary["variables_missing_any_value"] = summary["missing_variables"].map(
        lambda text: 0 if not text else len(text.split(";"))
    )

    output = companies.merge(summary.drop(columns="present_variables"), on="cik10", how="left")
    output = output[REPORT_OUTPUTS[MISSING_BY_COMPANY_PATH]].fillna(
        {
            "company_year_count": 0,
            "selected_observations": 0,
            "variables_with_any_value": 0,
            "variables_missing_any_value": len(variables),
            "missing_variables": ";".join(variables),
        }
    )
    output[count_columns] = output[count_columns].astype(int)
    return output


def write_quality_report(
    path: Path,
    stats: dict[str, int],
    output_counts: dict[str, int],
    dataset_scope: dict[str, Any],
) -> None:
    accepted_forms = dataset_scope["accepted_forms"]
    configured_year_range = (
        f"{dataset_scope['start_year']}-{dataset_scope['end_year']}"
        if dataset_scope.get("start_year") is not None or dataset_scope.get("end_year") is not None
        else "not configured"
    )
    count_metrics = [
        ("Companies in research universe", "companies_in_universe"),
        ("Company Facts files found", "companyfacts_files_found"),
        ("Company Facts files parsed", "companyfacts_files_parsed"),
        ("Missing Company Facts files", "missing_companyfacts_files"),
        ("JSON parse errors", "json_parse_errors"),
        ("Files without `facts`", "files_without_facts"),
        ("Candidate annual facts", "candidate_facts"),
        ("Facts rejected by unit", "facts_rejected_unit"),
        ("Facts rejected by filing form", "facts_rejected_form"),
        ("Facts rejected by company year", "facts_rejected_company_year"),
        ("Facts rejected as non-annual", "facts_rejected_nonannual"),
        ("Facts rejected by invalid end year", "facts_rejected_invalid_end_year"),
        ("Facts rejected by excessive filing lag", "facts_rejected_excessive_filing_lag"),
        ("Facts rejected by filing year", "facts_rejected_filing_year"),
        ("Facts rejected by invalid flow period", "facts_rejected_invalid_flow_period"),
        ("Facts without value", "facts_without_value"),
        ("Facts without company year", "facts_without_company_year"),
        ("Derived assets", "derived_assets"),
        ("Derived assets rejected", "derived_assets_rejected"),
        ("Derived liabilities", "derived_liabilities"),
        ("Derived liabilities rejected", "derived_liabilities_rejected"),
        ("Derived operating costs", "derived_operating_costs"),
        ("Derived operating costs replaced", "derived_operating_costs_replaced"),
        ("Derived operating costs rejected", "derived_operating_costs_rejected"),
    ]
    output_metrics = [
        ("Long facts rows", "long_rows", LONG_OUTPUT_PATH),
        ("Wide facts rows", "wide_rows", WIDE_OUTPUT_PATH),
        ("Variable coverage rows", "variable_coverage_rows", VARIABLE_COVERAGE_PATH),
        ("Tag usage rows", "tag_usage_rows", TAG_USAGE_PATH),
        ("Missing-by-company rows", "missing_by_company_rows", MISSING_BY_COMPANY_PATH),
    ]

    lines = [
        "# XBRL Parse Quality Report",
        "",
        "Technical report generated by `src/data/06_parse_companyfacts.py`.",
        "This report does not interpret financial results.",
        "",
        "## Inputs",
        "",
        f"- Research universe: `{RESEARCH_UNIVERSE_PATH}`",
        f"- Company Facts directory: `{COMPANYFACTS_DIR}`",
        f"- Tag configuration: `{SEC_TAGS_CONFIG_PATH}`",
        f"- Dataset configuration: `{DATASET_CONFIG_PATH}`",
        f"- Accepted units: `{';'.join(ACCEPTED_UNITS)}`",
        f"- Accepted filing forms: `{';'.join(accepted_forms)}`",
        f"- Configured source company-year range: `{configured_year_range}`",
        f"- Target horizon years: `{dataset_scope.get('target_horizon_years')}`",
        f"- Max split feature year: `{dataset_scope.get('max_split_year')}`",
        "",
        "## Processing Rules",
        "",
        "- Missing values were not imputed.",
        "- Facts with units outside the accepted unit list were skipped.",
        "- Facts from filing forms outside the dataset configuration were skipped.",
        "- Facts outside the configured source company-year range were skipped.",
        "- Non-annual facts were skipped.",
        f"- Flow variables required `start`, `end` and a {ANNUAL_PERIOD_MIN_DAYS}-{ANNUAL_PERIOD_MAX_DAYS} day period.",
        "- Missing assets were derived from liabilities and equity when total assets were not reported directly.",
        "- Missing liabilities were derived from liabilities and equity minus equity when both source values were available.",
        "- Operating costs were derived as revenues minus operating income/loss when both source values were available; direct `CostsAndExpenses` values were kept only as fallback.",
        "- Company years were assigned from SEC fiscal-year metadata when available, then from annual/Q4 calendar frames, then from period end year.",
        f"- Facts with `end` year more than {MAX_END_YEAR_LEAD} year after `fy` or `filed` year were skipped.",
        f"- Facts with filing lag above {MAX_SELECTED_FILING_LAG_DAYS} days were skipped to avoid stale comparative facts from later 10-K filings.",
        f"- Facts filed more than {MAX_FILING_YEAR_LEAD} year after `company_year` were skipped.",
        "- Duplicate facts were resolved deterministically using annual status, preferred form, fiscal-period label, period match, filing lag, fiscal-year match, frame match, tier, tag priority, filing date, period end date and accession number.",
        "- Raw SEC metadata fields `form`, `fp`, `filed`, `accn`, `frame`, `start` and `end` were preserved in the long output.",
        "",
        "## Counts",
        "",
        *[f"- {label}: {stats[key]:,}" for label, key in count_metrics],
        "",
        "## Outputs",
        "",
        *[f"- {label}: {output_counts[key]:,} -> `{path}`" for label, key, path in output_metrics],
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_all_companyfacts(
    companies: pd.DataFrame,
    rules: pd.DataFrame,
    dataset_scope: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, int]]:
    selected_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    stats = defaultdict(int)
    stats["companies_in_universe"] = len(companies)
    stats["companyfacts_files_found"] = sum(1 for _ in COMPANYFACTS_DIR.glob("CIK*.json"))

    for _, company_row in companies.iterrows():
        company = company_row.to_dict()
        path = COMPANYFACTS_DIR / f"CIK{company['cik10']}.json"

        if not path.exists():
            stats["missing_companyfacts_files"] += 1
            continue

        try:
            parse_companyfacts_file(company, path, rules, dataset_scope, selected_rows, stats)
        except (OSError, json.JSONDecodeError) as error:
            stats["json_parse_errors"] += 1
            print(f"Failed to parse {path}: {error}")
            continue

        stats["companyfacts_files_parsed"] += 1
        if stats["companyfacts_files_parsed"] % PROGRESS_EVERY_FILES == 0:
            print(
                "Parsed Company Facts files: "
                f"{stats['companyfacts_files_parsed']:,} / {len(companies):,}"
            )

    add_derived_balance_sheet_values(selected_rows, stats)
    add_derived_operating_cost_values(selected_rows, stats)

    long_frame = pd.DataFrame(selected_rows.values())
    if long_frame.empty:
        return pd.DataFrame(columns=LONG_COLUMNS), stats

    long_frame = long_frame.sort_values(["cik10", "company_year", "_tier_rank", "tag_priority"])
    return long_frame[LONG_COLUMNS].reset_index(drop=True), stats


def write_outputs(outputs: dict[Path, pd.DataFrame]) -> None:
    for path, frame in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False, encoding="utf-8")


def main() -> None:
    for path, message in [
        (RESEARCH_UNIVERSE_PATH, "Run 04_build_research_universe.py first."),
        (SEC_TAGS_CONFIG_PATH, "Create configs/sec_tags.yaml first."),
    ]:
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}. {message}")
    if not COMPANYFACTS_DIR.exists():
        raise FileNotFoundError(
            f"Company Facts directory not found: {COMPANYFACTS_DIR}. Run download_sec.py first."
        )

    companies = read_research_universe(RESEARCH_UNIVERSE_PATH)
    variables, rules = read_sec_tag_config(SEC_TAGS_CONFIG_PATH)
    dataset_scope = read_dataset_scope(DATASET_CONFIG_PATH)

    print(f"Read research universe companies: {len(companies):,}")
    print(f"Read configured variables:        {len(variables):,}")
    print(f"Read configured tag rules:        {len(rules):,}")
    print(f"Accepted filing forms:            {';'.join(dataset_scope['accepted_forms'])}")

    long_frame, stats = parse_all_companyfacts(companies, rules, dataset_scope)
    wide_frame = build_wide_frame(long_frame, companies, variables)
    report_frames = {
        VARIABLE_COVERAGE_PATH: build_variable_coverage(
            long_frame,
            variables,
            rules,
            company_count=len(companies),
            wide_row_count=len(wide_frame),
        ),
        TAG_USAGE_PATH: build_tag_usage(long_frame, rules),
        MISSING_BY_COMPANY_PATH: build_missing_by_company(long_frame, companies, variables),
    }
    outputs = {
        LONG_OUTPUT_PATH: long_frame,
        WIDE_OUTPUT_PATH: wide_frame,
        **report_frames,
    }

    write_outputs(outputs)
    write_quality_report(
        QUALITY_REPORT_PATH,
        stats=stats,
        dataset_scope=dataset_scope,
        output_counts={
            "long_rows": len(long_frame),
            "wide_rows": len(wide_frame),
            "variable_coverage_rows": len(report_frames[VARIABLE_COVERAGE_PATH]),
            "tag_usage_rows": len(report_frames[TAG_USAGE_PATH]),
            "missing_by_company_rows": len(report_frames[MISSING_BY_COMPANY_PATH]),
        },
    )

    for label, path in [
        ("Saved long facts", LONG_OUTPUT_PATH),
        ("Saved wide facts", WIDE_OUTPUT_PATH),
        ("Saved variable coverage", VARIABLE_COVERAGE_PATH),
        ("Saved tag usage", TAG_USAGE_PATH),
        ("Saved missing by company", MISSING_BY_COMPANY_PATH),
        ("Saved parse quality report", QUALITY_REPORT_PATH),
    ]:
        print(f"{label}: {path}")


if __name__ == "__main__":
    main()

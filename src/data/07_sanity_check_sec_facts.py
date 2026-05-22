"""
Run technical sanity checks on parsed SEC financial facts.

Input:
- data/interim/sec_facts_wide.csv
- data/interim/sec_facts_long.csv, if available, for source-period metadata
- configs/dataset_config.yaml, if available, for expected forms and year range

Output:
- data/reports/sec_facts_sanity_warnings.csv
- data/reports/sec_facts_sanity_summary.csv

The checks flag technical issues and suspicious values. They do not modify the
dataset, impute missing values, or interpret financial results.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


BASE_DIR = Path(__file__).resolve().parents[2]
INTERIM_DIR = BASE_DIR / "data" / "interim"
REPORTS_DIR = BASE_DIR / "data" / "reports"
CONFIG_DIR = BASE_DIR / "configs"

WIDE_INPUT_PATH = INTERIM_DIR / "sec_facts_wide.csv"
LONG_INPUT_PATH = INTERIM_DIR / "sec_facts_long.csv"
DATASET_CONFIG_PATH = CONFIG_DIR / "dataset_config.yaml"
SEC_TAGS_CONFIG_PATH = CONFIG_DIR / "sec_tags.yaml"
OUTPUT_PATH = REPORTS_DIR / "sec_facts_sanity_warnings.csv"
SUMMARY_OUTPUT_PATH = REPORTS_DIR / "sec_facts_sanity_summary.csv"

CURRENT_YEAR = datetime.now(timezone.utc).year
DEFAULT_ACCEPTED_FORMS = ("10-K",)
ACCEPTED_UNITS = ("USD",)
MIN_YEARS_FOR_COVERAGE_CHECK = 5
MIN_CORE_VARIABLE_COVERAGE_RATIO = 0.5
MAX_LIABILITIES_TO_ASSETS_RATIO = 1.5
MAX_NEGATIVE_EQUITY_BALANCE_GAP_RATIO = 0.1
MAX_COMPONENT_TO_TOTAL_RATIO = 1.05
MAX_BALANCE_SHEET_GAP_RATIO = 0.5
MAX_ASSETS_TO_LIABILITIES_AND_EQUITY_GAP_RATIO = 0.05
MAX_NET_RESULT_ABS_TO_REVENUES_RATIO = 2.0
MAX_NET_RESULT_ABS_TO_ASSETS_RATIO = 1.5
MAX_NET_PROFIT_TO_REVENUES_RATIO = 2.0
MAX_NET_PROFIT_TO_ASSETS_RATIO = 1.5
MAX_DERIVED_FORMULA_GAP_RATIO = 1e-6
# Must match the parser's stale-comparative-fact cap.
MAX_SELECTED_FILING_LAG_DAYS = 240
MAX_FILING_YEAR_LEAD = 1
MIN_ANNUAL_PERIOD_DAYS = 300
MAX_ANNUAL_PERIOD_DAYS = 400
MIN_VARIABLES_PRESENT_PER_ROW = 3
INVALID_NUMERIC_FLAG_PREFIX = "_invalid_numeric__"
INVALID_NUMERIC_VALUE_PREFIX = "_invalid_numeric_value__"

ID_COLUMNS = [
    "research_universe_id",
    "cik",
    "cik10",
    "company_name",
    "primary_ticker",
    "research_sector",
    "fiscal_year_end",
    "company_year",
]

FINANCIAL_VARIABLES = [
    "assets",
    "liabilities",
    "liabilities_and_equity",
    "current_assets",
    "current_liabilities",
    "revenues",
    "net_income",
    "equity",
    "cash",
    "accounts_receivable",
    "inventory",
    "cost_of_revenue",
    "operating_costs",
    "ppe",
    "intangible_assets",
    "goodwill",
    "depreciation_amortization",
    "long_term_investments",
    "long_term_debt",
    "short_term_debt",
    "ebit",
    "interest_expense",
    "capex",
    "retained_earnings",
    "operating_cash_flow",
    "investing_cash_flow",
    "financing_cash_flow",
]

FLOW_VARIABLES = [
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
]

SOURCE_CONSISTENCY_VARIABLES = [
    "assets",
    "liabilities",
    "liabilities_and_equity",
    "equity",
    "revenues",
    "net_income",
]

CORE_COVERAGE_VARIABLES = [
    "assets",
    "liabilities",
    "revenues",
    "net_income",
    "equity",
    "operating_cash_flow",
]

LONG_REQUIRED_COLUMNS = [
    *ID_COLUMNS,
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

WARNING_COLUMNS = [
    "warning_id",
    "severity",
    "check_name",
    "scope",
    "research_universe_id",
    "cik",
    "cik10",
    "company_name",
    "primary_ticker",
    "research_sector",
    "company_year",
    "variable",
    "value",
    "reference_variable",
    "reference_value",
    "details",
]

SUMMARY_COLUMNS = [
    "severity",
    "check_name",
    "warning_count",
    "company_count",
    "company_year_count",
    "first_warning_id",
]


def read_dataset_scope(path: Path) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "accepted_forms": DEFAULT_ACCEPTED_FORMS,
        "start_year": None,
        "end_year": None,
    }
    if not path.exists():
        return scope

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    dataset_config = config.get("dataset", {}) if isinstance(config, dict) else {}
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
    return scope


def read_configured_tag_rules(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()

    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    if not isinstance(config, dict):
        raise ValueError(f"Invalid tag configuration in {path}: expected a mapping")

    configured_rules: set[tuple[str, str, str]] = set()
    for variable, tiers in config.items():
        if not isinstance(tiers, dict):
            continue

        for tags in tiers.values():
            if not isinstance(tags, list):
                continue

            for tag_config in tags:
                if not isinstance(tag_config, dict):
                    continue

                namespace = str(tag_config.get("namespace", "")).strip()
                tag = str(tag_config.get("tag", "")).strip()
                if namespace and tag:
                    configured_rules.add((str(variable), namespace, tag))

    return configured_rules


def read_wide_facts(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}. Run 06_parse_companyfacts.py first.")

    frame = pd.read_csv(path, dtype=str).fillna("")
    missing_columns = [column for column in ID_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns in {path}: {missing_columns}")

    for column in FINANCIAL_VARIABLES:
        if column in frame.columns:
            raw_values = frame[column].astype(str).str.strip()
            numeric_values = pd.to_numeric(frame[column], errors="coerce")
            invalid_numeric = raw_values.ne("") & numeric_values.isna()
            frame[f"{INVALID_NUMERIC_FLAG_PREFIX}{column}"] = invalid_numeric
            frame[f"{INVALID_NUMERIC_VALUE_PREFIX}{column}"] = frame[column].where(invalid_numeric, "")
            frame[column] = numeric_values

    frame["company_year_numeric"] = pd.to_numeric(frame["company_year"], errors="coerce")
    return frame


def read_long_facts(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=LONG_REQUIRED_COLUMNS)

    columns = set(pd.read_csv(path, nrows=0).columns)
    missing_columns = [column for column in LONG_REQUIRED_COLUMNS if column not in columns]
    if missing_columns:
        raise ValueError(f"Missing required columns in {path}: {missing_columns}")

    return pd.read_csv(path, dtype=str, usecols=LONG_REQUIRED_COLUMNS).fillna("")


def normalized_forms(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def period_days(frame: pd.DataFrame) -> pd.Series:
    start_dates = pd.to_datetime(frame["start"], errors="coerce")
    end_dates = pd.to_datetime(frame["end"], errors="coerce")
    return (end_dates - start_dates).dt.days + 1


def filing_lag_days(frame: pd.DataFrame) -> pd.Series:
    filed_dates = pd.to_datetime(frame["filed"], errors="coerce")
    end_dates = pd.to_datetime(frame["end"], errors="coerce")
    return (filed_dates - end_dates).dt.days


def filing_year_diff(frame: pd.DataFrame) -> pd.Series:
    filed_dates = pd.to_datetime(frame["filed"], errors="coerce")
    company_years = pd.to_numeric(frame["company_year"], errors="coerce")
    return filed_dates.dt.year - company_years


def semicolon_join(values: pd.Series) -> str:
    return ";".join(sorted(str(value) for value in values.dropna().unique() if str(value)))


def format_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def context_from_row(row: pd.Series | dict[str, Any]) -> dict[str, str]:
    return {
        "research_universe_id": format_value(row.get("research_universe_id", "")),
        "cik": format_value(row.get("cik", "")),
        "cik10": format_value(row.get("cik10", "")),
        "company_name": format_value(row.get("company_name", "")),
        "primary_ticker": format_value(row.get("primary_ticker", "")),
        "research_sector": format_value(row.get("research_sector", "")),
        "company_year": format_value(row.get("company_year", "")),
    }


def add_warning(
    warnings: list[dict[str, str]],
    row: pd.Series | dict[str, Any],
    severity: str,
    check_name: str,
    scope: str,
    variable: str = "",
    value: Any = "",
    reference_variable: str = "",
    reference_value: Any = "",
    details: str = "",
) -> None:
    warnings.append(
        {
            "warning_id": "",
            "severity": severity,
            "check_name": check_name,
            "scope": scope,
            **context_from_row(row),
            "variable": variable,
            "value": format_value(value),
            "reference_variable": reference_variable,
            "reference_value": format_value(reference_value),
            "details": details,
        }
    )


def add_core_variable_coverage_warnings(wide: pd.DataFrame, warnings: list[dict[str, str]]) -> None:
    grouped = wide.groupby("cik10", dropna=False)
    for _, company_rows in grouped:
        year_count = len(company_rows)
        if year_count < MIN_YEARS_FOR_COVERAGE_CHECK:
            continue

        first_row = company_rows.iloc[0]
        for variable in CORE_COVERAGE_VARIABLES:
            if variable not in company_rows.columns:
                continue

            present_count = int(company_rows[variable].notna().sum())
            coverage_ratio = present_count / year_count if year_count else 0
            if coverage_ratio >= MIN_CORE_VARIABLE_COVERAGE_RATIO:
                continue

            add_warning(
                warnings,
                first_row,
                severity="medium",
                check_name=f"{variable}_missing_for_majority_of_years",
                scope="company",
                variable=variable,
                value=present_count,
                reference_variable="company_year_count",
                reference_value=year_count,
                details=(
                    f"{variable} present in {present_count} of {year_count} company-years "
                    f"({coverage_ratio:.1%})."
                ),
            )


def add_row_condition_warnings(
    wide: pd.DataFrame,
    warnings: list[dict[str, str]],
    condition: pd.Series,
    severity: str,
    check_name: str,
    variable: str,
    reference_variable: str = "",
    details: str = "",
) -> None:
    for _, row in wide[condition.fillna(False)].iterrows():
        add_warning(
            warnings,
            row,
            severity=severity,
            check_name=check_name,
            scope="company_year",
            variable=variable,
            value=row.get(variable, ""),
            reference_variable=reference_variable,
            reference_value=row.get(reference_variable, "") if reference_variable else "",
            details=details,
        )


def add_dataset_warning(
    warnings: list[dict[str, str]],
    severity: str,
    check_name: str,
    value: Any = "",
    reference_variable: str = "",
    reference_value: Any = "",
    details: str = "",
) -> None:
    add_warning(
        warnings,
        {},
        severity=severity,
        check_name=check_name,
        scope="dataset",
        value=value,
        reference_variable=reference_variable,
        reference_value=reference_value,
        details=details,
    )


def materially_differs(
    actual: pd.Series,
    expected: pd.Series,
    tolerance_ratio: float,
) -> pd.Series:
    tolerance = expected.abs().clip(lower=1.0) * tolerance_ratio
    return actual.notna() & expected.notna() & (actual - expected).abs().gt(tolerance)


def long_keys_for_derived_variable(long: pd.DataFrame, variable: str, tag: str) -> pd.DataFrame:
    if long.empty:
        return pd.DataFrame(columns=["cik10", "company_year"])

    derived = long[
        long["variable"].eq(variable)
        & long["namespace"].eq("derived")
        & long["tag"].eq(tag)
    ]
    return derived[["cik10", "company_year"]].drop_duplicates()


def add_wide_structure_warnings(
    wide: pd.DataFrame,
    warnings: list[dict[str, str]],
    dataset_scope: dict[str, Any],
) -> None:
    missing_financial_columns = [column for column in FINANCIAL_VARIABLES if column not in wide.columns]
    if missing_financial_columns:
        add_dataset_warning(
            warnings,
            severity="high",
            check_name="financial_variables_missing_from_wide",
            value=len(missing_financial_columns),
            reference_variable="expected_financial_variables",
            reference_value=len(FINANCIAL_VARIABLES),
            details=f"Missing financial columns: {';'.join(missing_financial_columns)}.",
        )

    duplicate_keys = wide.duplicated(["cik10", "company_year"], keep=False)
    add_row_condition_warnings(
        wide,
        warnings,
        duplicate_keys,
        "high",
        "wide_duplicate_company_year",
        "company_year",
        details="Duplicate rows for the same cik10 and company_year in sec_facts_wide.csv.",
    )

    invalid_year = wide["company_year"].astype(str).str.strip().ne("") & wide["company_year_numeric"].isna()
    add_row_condition_warnings(
        wide,
        warnings,
        invalid_year,
        "high",
        "company_year_not_numeric",
        "company_year",
        details="Company year cannot be parsed as a number.",
    )

    start_year = dataset_scope.get("start_year")
    end_year = dataset_scope.get("end_year")
    outside_configured_range = pd.Series(False, index=wide.index)
    if start_year is not None:
        outside_configured_range = outside_configured_range | wide["company_year_numeric"].lt(start_year)
    if end_year is not None:
        outside_configured_range = outside_configured_range | wide["company_year_numeric"].gt(end_year)
    add_row_condition_warnings(
        wide,
        warnings,
        outside_configured_range,
        "low",
        "company_year_outside_configured_dataset_range",
        "company_year",
        details=(
            "Company year is outside dataset.start_year/dataset.end_year. "
            "This is diagnostic only; model-dataset filtering happens later."
        ),
    )

    for variable in FINANCIAL_VARIABLES:
        flag_column = f"{INVALID_NUMERIC_FLAG_PREFIX}{variable}"
        value_column = f"{INVALID_NUMERIC_VALUE_PREFIX}{variable}"
        if flag_column not in wide.columns:
            continue
        for _, row in wide[wide[flag_column]].iterrows():
            add_warning(
                warnings,
                row,
                severity="high",
                check_name="non_numeric_financial_value",
                scope="company_year",
                variable=variable,
                value=row.get(value_column, ""),
                details="Non-empty financial value cannot be parsed as numeric.",
            )


def add_balance_sheet_warnings(wide: pd.DataFrame, warnings: list[dict[str, str]]) -> None:
    add_row_condition_warnings(
        wide,
        warnings,
        wide["company_year_numeric"] > CURRENT_YEAR,
        "high",
        "company_year_in_future",
        "company_year",
        details=f"Company year is after current UTC year {CURRENT_YEAR}.",
    )

    for variable in ["assets", "liabilities_and_equity", "liabilities", "cash", "inventory", "ppe"]:
        if variable in wide.columns:
            add_row_condition_warnings(
                wide,
                warnings,
                wide[variable] < 0,
                "high" if variable in {"assets", "liabilities_and_equity"} else "medium",
                f"{variable}_negative",
                variable,
                details=f"{variable} is negative.",
            )

    if {"assets", "liabilities_and_equity"} <= set(wide.columns):
        condition = materially_differs(
            wide["assets"],
            wide["liabilities_and_equity"],
            MAX_ASSETS_TO_LIABILITIES_AND_EQUITY_GAP_RATIO,
        )
        add_row_condition_warnings(
            wide,
            warnings,
            condition,
            "medium",
            "assets_differs_from_liabilities_and_equity",
            "assets",
            "liabilities_and_equity",
            (
                "Assets differ materially from liabilities and equity. "
                "These tags should normally represent the same balance sheet total."
            ),
        )

    if {"assets", "liabilities"} <= set(wide.columns):
        condition = (
            wide["assets"].gt(0)
            & wide["liabilities"].notna()
            & wide["liabilities"].gt(wide["assets"] * MAX_LIABILITIES_TO_ASSETS_RATIO)
        )

        if "equity" in wide.columns:
            balance_gap = (wide["assets"] - wide["liabilities"] - wide["equity"]).abs()
            negative_equity_explains_liabilities = (
                wide["equity"].lt(0)
                & wide["assets"].gt(0)
                & balance_gap.le(wide["assets"].abs() * MAX_NEGATIVE_EQUITY_BALANCE_GAP_RATIO)
            )
            condition = condition & ~negative_equity_explains_liabilities

        add_row_condition_warnings(
            wide,
            warnings,
            condition,
            "high",
            "liabilities_absurdly_above_assets",
            "liabilities",
            "assets",
            (
                f"Liabilities exceed {MAX_LIABILITIES_TO_ASSETS_RATIO:.1f}x assets "
                "and are not explained by negative equity."
            ),
        )

    component_checks = [
        ("current_assets", "assets"),
        ("current_liabilities", "liabilities"),
        ("cash", "assets"),
        ("accounts_receivable", "assets"),
        ("inventory", "assets"),
        ("ppe", "assets"),
        ("goodwill", "assets"),
    ]
    for component, total in component_checks:
        if {component, total} <= set(wide.columns):
            condition = wide[total].gt(0) & wide[component].gt(wide[total] * MAX_COMPONENT_TO_TOTAL_RATIO)
            add_row_condition_warnings(
                wide,
                warnings,
                condition,
                "medium",
                f"{component}_above_{total}",
                component,
                total,
                f"{component} exceeds {MAX_COMPONENT_TO_TOTAL_RATIO:.2f}x {total}.",
            )

    if {"assets", "liabilities", "equity"} <= set(wide.columns):
        denominator = wide["assets"].abs()
        gap = (wide["assets"] - wide["liabilities"] - wide["equity"]).abs()
        condition = denominator.gt(0) & gap.gt(denominator * MAX_BALANCE_SHEET_GAP_RATIO)
        add_row_condition_warnings(
            wide,
            warnings,
            condition,
            "low",
            "large_assets_liabilities_equity_gap",
            "assets",
            "liabilities",
            "Assets differ materially from liabilities + equity. Equity definition may differ.",
        )


def add_income_statement_warnings(wide: pd.DataFrame, warnings: list[dict[str, str]]) -> None:
    if "revenues" in wide.columns:
        add_row_condition_warnings(
            wide,
            warnings,
            wide["revenues"] < 0,
            "medium",
            "revenues_negative",
            "revenues",
            details="Revenues are negative.",
        )

    if {"net_income", "revenues"} <= set(wide.columns):
        denominator = wide["revenues"].abs()
        net_loss_ratio = wide["net_income"].abs() / denominator
        condition = (
            wide["net_income"].lt(0)
            & denominator.gt(0)
            & net_loss_ratio.gt(MAX_NET_RESULT_ABS_TO_REVENUES_RATIO)
        )
        add_row_condition_warnings(
            wide,
            warnings,
            condition,
            "medium",
            "net_loss_abs_large_relative_to_revenues",
            "net_income",
            "revenues",
            f"Absolute net loss exceeds {MAX_NET_RESULT_ABS_TO_REVENUES_RATIO:.1f}x revenues.",
        )

        net_profit_ratio = wide["net_income"] / denominator
        condition = (
            wide["net_income"].gt(0)
            & denominator.gt(0)
            & net_profit_ratio.gt(MAX_NET_PROFIT_TO_REVENUES_RATIO)
        )
        add_row_condition_warnings(
            wide,
            warnings,
            condition,
            "medium",
            "net_profit_large_relative_to_revenues",
            "net_income",
            "revenues",
            f"Net profit exceeds {MAX_NET_PROFIT_TO_REVENUES_RATIO:.1f}x revenues.",
        )

    if {"net_income", "assets"} <= set(wide.columns):
        denominator = wide["assets"].abs()
        net_loss_ratio = wide["net_income"].abs() / denominator
        condition = (
            wide["net_income"].lt(0)
            & denominator.gt(0)
            & net_loss_ratio.gt(MAX_NET_RESULT_ABS_TO_ASSETS_RATIO)
        )
        add_row_condition_warnings(
            wide,
            warnings,
            condition,
            "medium",
            "net_loss_abs_large_relative_to_assets",
            "net_income",
            "assets",
            f"Absolute net loss exceeds {MAX_NET_RESULT_ABS_TO_ASSETS_RATIO:.1f}x assets.",
        )

        net_profit_ratio = wide["net_income"] / denominator
        condition = (
            wide["net_income"].gt(0)
            & denominator.gt(0)
            & net_profit_ratio.gt(MAX_NET_PROFIT_TO_ASSETS_RATIO)
        )
        add_row_condition_warnings(
            wide,
            warnings,
            condition,
            "medium",
            "net_profit_large_relative_to_assets",
            "net_income",
            "assets",
            f"Net profit exceeds {MAX_NET_PROFIT_TO_ASSETS_RATIO:.1f}x assets.",
        )

    if "cost_of_revenue" in wide.columns:
        add_row_condition_warnings(
            wide,
            warnings,
            wide["cost_of_revenue"] < 0,
            "low",
            "cost_of_revenue_negative",
            "cost_of_revenue",
            details="Cost of revenue is negative.",
        )

    if "operating_costs" in wide.columns:
        add_row_condition_warnings(
            wide,
            warnings,
            wide["operating_costs"] < 0,
            "low",
            "operating_costs_negative",
            "operating_costs",
            details="Operating costs are negative.",
        )

    if {"cost_of_revenue", "operating_costs"} <= set(wide.columns):
        condition = (
            wide["operating_costs"].gt(0)
            & wide["cost_of_revenue"].gt(wide["operating_costs"] * MAX_COMPONENT_TO_TOTAL_RATIO)
        )
        add_row_condition_warnings(
            wide,
            warnings,
            condition,
            "medium",
            "cost_of_revenue_above_operating_costs",
            "cost_of_revenue",
            "operating_costs",
            f"Cost of revenue exceeds {MAX_COMPONENT_TO_TOTAL_RATIO:.2f}x operating costs.",
        )


def add_cash_flow_warnings(wide: pd.DataFrame, warnings: list[dict[str, str]]) -> None:
    if "capex" in wide.columns:
        add_row_condition_warnings(
            wide,
            warnings,
            wide["capex"] < 0,
            "medium",
            "capex_negative",
            "capex",
            details="CAPEX uses payment tags and is expected to be non-negative.",
        )


def add_derived_formula_warnings(
    wide: pd.DataFrame,
    long: pd.DataFrame,
    warnings: list[dict[str, str]],
) -> None:
    def derived_rows(tag_variable: str, tag: str, value_columns: list[str]) -> pd.DataFrame:
        keys = long_keys_for_derived_variable(long, tag_variable, tag)
        if keys.empty or not set(value_columns) <= set(wide.columns):
            return pd.DataFrame()

        return keys.merge(
            wide[[*ID_COLUMNS, *value_columns]],
            on=["cik10", "company_year"],
            how="left",
        )

    assets = derived_rows(
        "assets",
        "LiabilitiesAndStockholdersEquityAsAssets",
        ["assets", "liabilities_and_equity"],
    )
    if not assets.empty:
        condition = materially_differs(
            assets["assets"],
            assets["liabilities_and_equity"],
            MAX_DERIVED_FORMULA_GAP_RATIO,
        )
        add_row_condition_warnings(
            assets,
            warnings,
            condition,
            "high",
            "derived_assets_formula_mismatch",
            "assets",
            "liabilities_and_equity",
            "Derived assets should equal liabilities and equity.",
        )

    liabilities = derived_rows(
        "liabilities",
        "LiabilitiesAndStockholdersEquityLessEquity",
        ["liabilities", "liabilities_and_equity", "equity"],
    )
    if not liabilities.empty:
        expected = liabilities["liabilities_and_equity"] - liabilities["equity"]
        condition = materially_differs(
            liabilities["liabilities"],
            expected,
            MAX_DERIVED_FORMULA_GAP_RATIO,
        )
        add_row_condition_warnings(
            liabilities,
            warnings,
            condition,
            "high",
            "derived_liabilities_formula_mismatch",
            "liabilities",
            "liabilities_and_equity",
            "Derived liabilities should equal liabilities and equity minus equity.",
        )

    operating_costs = derived_rows(
        "operating_costs",
        "RevenuesLessOperatingIncomeLoss",
        ["operating_costs", "revenues", "ebit"],
    )
    if not operating_costs.empty:
        expected = operating_costs["revenues"] - operating_costs["ebit"]
        condition = materially_differs(
            operating_costs["operating_costs"],
            expected,
            MAX_DERIVED_FORMULA_GAP_RATIO,
        )
        add_row_condition_warnings(
            operating_costs,
            warnings,
            condition,
            "high",
            "derived_operating_costs_formula_mismatch",
            "operating_costs",
            "revenues",
            "Derived operating costs should equal revenues minus operating income/loss.",
        )


def add_sparse_row_warnings(wide: pd.DataFrame, warnings: list[dict[str, str]]) -> None:
    variables = [column for column in FINANCIAL_VARIABLES if column in wide.columns]
    present_count = wide[variables].notna().sum(axis=1)
    condition = present_count.le(MIN_VARIABLES_PRESENT_PER_ROW)

    for index, row in wide[condition].iterrows():
        add_warning(
            warnings,
            row,
            severity="low",
            check_name="sparse_company_year",
            scope="company_year",
            variable="",
            value=int(present_count.loc[index]),
            reference_variable="configured_variables",
            reference_value=len(variables),
            details=f"{int(present_count.loc[index])} financial variables are present in this row.",
        )


def add_long_wide_consistency_warnings(
    wide: pd.DataFrame,
    long: pd.DataFrame,
    warnings: list[dict[str, str]],
) -> None:
    if long.empty:
        add_dataset_warning(
            warnings,
            severity="low",
            check_name="long_facts_not_available",
            details=(
                f"{LONG_INPUT_PATH} is not available. Source-metadata and long/wide "
                "consistency checks were skipped."
            ),
        )
        return

    duplicate_long_rows = long[long.duplicated(["cik10", "company_year", "variable"], keep=False)]
    for _, row in duplicate_long_rows.drop_duplicates(["cik10", "company_year", "variable"]).iterrows():
        duplicate_count = len(
            duplicate_long_rows[
                (duplicate_long_rows["cik10"] == row["cik10"])
                & (duplicate_long_rows["company_year"] == row["company_year"])
                & (duplicate_long_rows["variable"] == row["variable"])
            ]
        )
        add_warning(
            warnings,
            row,
            severity="high",
            check_name="long_duplicate_company_year_variable",
            scope="company_year",
            variable=row.get("variable", ""),
            value=duplicate_count,
            details="Duplicate selected facts for the same cik10, company_year and variable.",
        )

    wide_keys = wide[["cik10", "company_year"]].drop_duplicates()
    long_keys = long[["cik10", "company_year"]].drop_duplicates()
    wide_only = wide_keys.merge(long_keys, on=["cik10", "company_year"], how="left", indicator=True)
    wide_only = wide_only[wide_only["_merge"] == "left_only"]
    if not wide_only.empty:
        add_dataset_warning(
            warnings,
            severity="high",
            check_name="wide_company_year_missing_from_long",
            value=len(wide_only),
            details="Company-year keys exist in wide facts but not in long facts.",
        )

    long_only = long_keys.merge(wide_keys, on=["cik10", "company_year"], how="left", indicator=True)
    long_only = long_only[long_only["_merge"] == "left_only"]
    if not long_only.empty:
        add_dataset_warning(
            warnings,
            severity="high",
            check_name="long_company_year_missing_from_wide",
            value=len(long_only),
            details="Company-year keys exist in long facts but not in wide facts.",
        )

    comparable_variables = [variable for variable in FINANCIAL_VARIABLES if variable in wide.columns]
    wide_values = wide[["cik10", "company_year", *comparable_variables]].melt(
        id_vars=["cik10", "company_year"],
        value_vars=comparable_variables,
        var_name="variable",
        value_name="wide_value",
    )
    wide_values = wide_values[wide_values["wide_value"].notna()]
    long_values = long[["cik10", "company_year", "variable", "value"]].copy()
    long_values["long_value"] = pd.to_numeric(long_values["value"], errors="coerce")
    merged = wide_values.merge(
        long_values[["cik10", "company_year", "variable", "long_value"]],
        on=["cik10", "company_year", "variable"],
        how="left",
    )
    mismatch = merged["long_value"].isna() | (merged["wide_value"] - merged["long_value"]).abs().gt(1e-6)
    for _, row in merged[mismatch].iterrows():
        add_warning(
            warnings,
            row,
            severity="high",
            check_name="wide_value_differs_from_long",
            scope="company_year",
            variable=row.get("variable", ""),
            value=row.get("wide_value", ""),
            reference_variable="long_value",
            reference_value=row.get("long_value", ""),
            details="Wide fact value does not match the selected long fact value.",
        )


def add_source_contract_warnings(
    long: pd.DataFrame,
    warnings: list[dict[str, str]],
    configured_tag_rules: set[tuple[str, str, str]],
) -> None:
    if long.empty:
        return

    derived_metadata_invalid = long[
        long["tier"].eq("derived") != long["namespace"].eq("derived")
    ]
    for _, row in derived_metadata_invalid.iterrows():
        add_warning(
            warnings,
            row,
            severity="high",
            check_name="derived_source_metadata_invalid",
            scope="company_year",
            variable=row.get("variable", ""),
            value=row.get("namespace", ""),
            reference_variable="tier",
            reference_value=row.get("tier", ""),
            details="Derived rows must use namespace=derived and tier=derived.",
        )

    non_derived = long[~long["namespace"].eq("derived")].copy()
    if non_derived.empty:
        return

    invalid_unit = ~normalized_forms(non_derived["unit"]).isin(ACCEPTED_UNITS)
    for _, row in non_derived[invalid_unit].iterrows():
        add_warning(
            warnings,
            row,
            severity="high",
            check_name="source_unit_outside_accepted_units",
            scope="company_year",
            variable=row.get("variable", ""),
            value=row.get("unit", ""),
            reference_variable="accepted_units",
            reference_value=";".join(ACCEPTED_UNITS),
            details="Non-derived selected facts must use accepted units.",
        )

    if not configured_tag_rules:
        add_dataset_warning(
            warnings,
            severity="high",
            check_name="sec_tags_config_not_available",
            details=f"{SEC_TAGS_CONFIG_PATH} is not available or contains no tag rules.",
        )
        return

    configured = pd.DataFrame(
        sorted(configured_tag_rules),
        columns=["variable", "namespace", "tag"],
    )
    tagged = non_derived.reset_index().merge(
        configured,
        on=["variable", "namespace", "tag"],
        how="left",
        indicator=True,
    )
    invalid_tags = tagged[tagged["_merge"].eq("left_only")]
    for _, row in invalid_tags.iterrows():
        add_warning(
            warnings,
            row,
            severity="high",
            check_name="source_tag_not_in_sec_tags_config",
            scope="company_year",
            variable=row.get("variable", ""),
            value=f"{row.get('namespace', '')}:{row.get('tag', '')}",
            reference_variable="sec_tags_config",
            reference_value=str(SEC_TAGS_CONFIG_PATH),
            details="Non-derived selected fact uses a variable/namespace/tag combination not configured in sec_tags.yaml.",
        )


def add_source_metadata_warnings(
    long: pd.DataFrame,
    warnings: list[dict[str, str]],
    dataset_scope: dict[str, Any],
) -> None:
    if long.empty:
        return

    accepted_forms = set(dataset_scope["accepted_forms"])
    form_allowed = normalized_forms(long["form"]).isin(accepted_forms)
    for _, group in long[~form_allowed].groupby(["cik10", "company_year"], dropna=False):
        first_row = group.iloc[0]
        add_warning(
            warnings,
            first_row,
            severity="high",
            check_name="source_form_outside_dataset_config",
            scope="company_year",
            variable=semicolon_join(group["variable"]),
            value=len(group),
            reference_variable="accepted_forms",
            reference_value=";".join(dataset_scope["accepted_forms"]),
            details=f"Selected facts use forms outside dataset configuration: {semicolon_join(group['form'])}.",
        )

    non_derived = long[~long["namespace"].eq("derived")].copy()
    if not non_derived.empty:
        non_derived["filing_lag_days"] = filing_lag_days(non_derived)
        non_derived["filing_year_diff"] = filing_year_diff(non_derived)

        filing_before_period_end = non_derived["filing_lag_days"].lt(0)
        for _, row in non_derived[filing_before_period_end].iterrows():
            add_warning(
                warnings,
                row,
                severity="high",
                check_name="source_filing_before_period_end",
                scope="company_year",
                variable=row.get("variable", ""),
                value=row.get("filed", ""),
                reference_variable="end",
                reference_value=row.get("end", ""),
                details="Selected fact has a filing date before its source period end date.",
            )

        excessive_filing_lag = non_derived["filing_lag_days"].gt(MAX_SELECTED_FILING_LAG_DAYS)
        for _, row in non_derived[excessive_filing_lag].iterrows():
            add_warning(
                warnings,
                row,
                severity="high",
                check_name="source_filing_lag_too_long",
                scope="company_year",
                variable=row.get("variable", ""),
                value=row.get("filed", ""),
                reference_variable="filing_lag_days",
                reference_value=row.get("filing_lag_days", ""),
                details=(
                    f"Selected fact was filed more than {MAX_SELECTED_FILING_LAG_DAYS} "
                    "days after the source period end date."
                ),
            )

        filing_year_too_late = non_derived["filing_year_diff"].gt(MAX_FILING_YEAR_LEAD)
        for _, row in non_derived[filing_year_too_late].iterrows():
            add_warning(
                warnings,
                row,
                severity="high",
                check_name="source_filing_year_after_company_year_window",
                scope="company_year",
                variable=row.get("variable", ""),
                value=row.get("filed", ""),
                reference_variable="company_year",
                reference_value=row.get("company_year", ""),
                details=(
                    f"Selected fact was filed more than {MAX_FILING_YEAR_LEAD} "
                    "year after company_year."
                ),
            )

    flow = long[long["variable"].isin(FLOW_VARIABLES)].copy()
    if not flow.empty:
        flow["period_days"] = period_days(flow)
        valid_annual_period = flow["period_days"].between(MIN_ANNUAL_PERIOD_DAYS, MAX_ANNUAL_PERIOD_DAYS)
        invalid_period = flow["period_days"].isna() | ~valid_annual_period
        for _, row in flow[invalid_period].iterrows():
            add_warning(
                warnings,
                row,
                severity="high",
                check_name="flow_period_not_annual",
                scope="company_year",
                variable=row.get("variable", ""),
                value=row.get("value", ""),
                reference_variable="period_days",
                reference_value=row.get("period_days", ""),
                details=(
                    f"Flow variable source period is outside "
                    f"{MIN_ANNUAL_PERIOD_DAYS}-{MAX_ANNUAL_PERIOD_DAYS} days."
                ),
            )

        fp_not_fy = flow["fp"].str.upper().ne("FY") & valid_annual_period
        for _, row in flow[fp_not_fy].iterrows():
            add_warning(
                warnings,
                row,
                severity="low",
                check_name="flow_source_fp_not_fy",
                scope="company_year",
                variable=row.get("variable", ""),
                value=row.get("value", ""),
                reference_variable="fp",
                reference_value=row.get("fp", ""),
                details="Flow variable has an annual-length period but source metadata fp is not FY.",
            )

    source = long[long["variable"].isin(SOURCE_CONSISTENCY_VARIABLES)].copy()
    if source.empty:
        return

    source["fy_numeric"] = pd.to_numeric(source["fy"], errors="coerce")
    source["company_year_numeric"] = pd.to_numeric(source["company_year"], errors="coerce")
    source["fy_differs_from_company_year"] = (
        source["fy_numeric"].notna()
        & source["company_year_numeric"].notna()
        & source["fy_numeric"].ne(source["company_year_numeric"])
    )

    for _, group in source[source["fy_differs_from_company_year"]].groupby(
        ["cik10", "company_year"],
        dropna=False,
    ):
        first_row = group.iloc[0]
        add_warning(
            warnings,
            first_row,
            severity="medium",
            check_name="source_fy_differs_from_company_year",
            scope="company_year",
            variable=semicolon_join(group["variable"]),
            value=semicolon_join(group["fy"]),
            reference_variable="company_year",
            reference_value=first_row.get("company_year", ""),
            details="Selected source fiscal year metadata differs from company_year.",
        )

    grouped = source.groupby(["cik10", "company_year"], dropna=False)
    for _, group in grouped:
        first_row = group.iloc[0]
        fy_values = [value for value in group["fy"].dropna().unique() if str(value)]
        if len(fy_values) > 1:
            add_warning(
                warnings,
                first_row,
                severity="medium",
                check_name="mixed_source_fiscal_years",
                scope="company_year",
                variable=semicolon_join(group["variable"]),
                value=";".join(sorted(str(value) for value in fy_values)),
                details="Core variables in one company-year come from multiple source fiscal years.",
            )

        accn_values = [value for value in group["accn"].dropna().unique() if str(value)]
        if len(accn_values) > 1:
            add_warning(
                warnings,
                first_row,
                severity="low",
                check_name="mixed_source_accessions",
                scope="company_year",
                variable=semicolon_join(group["variable"]),
                value=len(accn_values),
                details="Core variables in one company-year come from multiple accession numbers.",
            )

        end_values = [value for value in group["end"].dropna().unique() if str(value)]
        if len(end_values) > 1:
            add_warning(
                warnings,
                first_row,
                severity="medium",
                check_name="mixed_source_period_ends",
                scope="company_year",
                variable=semicolon_join(group["variable"]),
                value=";".join(sorted(str(value) for value in end_values)),
                details="Core variables in one company-year have multiple source period end dates.",
            )


def add_revenue_metadata_warnings(revenue_long: pd.DataFrame, warnings: list[dict[str, str]]) -> None:
    if revenue_long.empty:
        add_warning(
            warnings,
            {},
            severity="low",
            check_name="revenue_metadata_not_available",
            scope="dataset",
            details=(
                f"{LONG_INPUT_PATH} is not available or contains no revenues rows. "
                "Quarterly-revenue metadata checks were skipped."
            ),
        )
        return

    revenue_long = revenue_long.copy()
    revenue_long["period_days"] = period_days(revenue_long)
    annual_frame = revenue_long["frame"].str.match(r"^CY\d{4}(Q4I)?$", na=False)
    annual_period = revenue_long["period_days"].between(MIN_ANNUAL_PERIOD_DAYS, MAX_ANNUAL_PERIOD_DAYS)
    nonannual_period = revenue_long["period_days"].notna() & ~annual_period
    quarterly_fp_with_nonannual_period = (
        revenue_long["fp"].str.upper().isin(["Q1", "Q2", "Q3"])
        & ~annual_frame
        & (revenue_long["period_days"].isna() | nonannual_period)
    )

    for _, row in revenue_long[nonannual_period | quarterly_fp_with_nonannual_period].iterrows():
        add_warning(
            warnings,
            row,
            severity="high",
            check_name="revenues_may_be_quarterly",
            scope="company_year",
            variable="revenues",
            value=row.get("value", ""),
            reference_variable="period_days",
            reference_value=row.get("period_days", ""),
            details=(
                f"Revenue source has fp={row.get('fp', '')}, form={row.get('form', '')}, "
                f"start={row.get('start', '')}, end={row.get('end', '')}, "
                f"accn={row.get('accn', '')}."
            ),
        )


def build_warnings(
    wide: pd.DataFrame,
    long: pd.DataFrame,
    dataset_scope: dict[str, Any],
    configured_tag_rules: set[tuple[str, str, str]],
) -> pd.DataFrame:
    warnings: list[dict[str, str]] = []

    add_wide_structure_warnings(wide, warnings, dataset_scope)
    add_long_wide_consistency_warnings(wide, long, warnings)
    add_source_contract_warnings(long, warnings, configured_tag_rules)
    add_source_metadata_warnings(long, warnings, dataset_scope)
    add_core_variable_coverage_warnings(wide, warnings)
    add_balance_sheet_warnings(wide, warnings)
    add_income_statement_warnings(wide, warnings)
    add_cash_flow_warnings(wide, warnings)
    add_derived_formula_warnings(wide, long, warnings)
    add_sparse_row_warnings(wide, warnings)
    revenue_long = long[long["variable"] == "revenues"].copy() if not long.empty else long
    add_revenue_metadata_warnings(revenue_long, warnings)

    output = pd.DataFrame(warnings, columns=WARNING_COLUMNS)
    if output.empty:
        return output

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    output["_severity_rank"] = output["severity"].map(severity_rank).fillna(9)
    output = output.sort_values(
        ["_severity_rank", "check_name", "cik10", "company_year", "variable"],
        na_position="last",
    ).drop(columns="_severity_rank")
    output["warning_id"] = range(1, len(output) + 1)
    return output[WARNING_COLUMNS]


def build_summary(warnings: pd.DataFrame) -> pd.DataFrame:
    if warnings.empty:
        return pd.DataFrame(columns=SUMMARY_COLUMNS)

    company_years = warnings[
        warnings["cik10"].astype(str).str.strip().ne("")
        & warnings["company_year"].astype(str).str.strip().ne("")
    ][["severity", "check_name", "cik10", "company_year"]].drop_duplicates()
    summary = (
        warnings.groupby(["severity", "check_name"], dropna=False)
        .agg(
            warning_count=("warning_id", "count"),
            company_count=("cik10", lambda values: values.replace("", pd.NA).nunique()),
            first_warning_id=("warning_id", "min"),
        )
        .reset_index()
    )
    company_year_counts = (
        company_years.groupby(["severity", "check_name"], dropna=False)
        .size()
        .reset_index(name="company_year_count")
    )

    summary = summary.merge(company_year_counts, on=["severity", "check_name"], how="left")
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    summary["_severity_rank"] = summary["severity"].map(severity_rank).fillna(9)
    summary = summary.sort_values(
        ["_severity_rank", "warning_count", "check_name"],
        ascending=[True, False, True],
    ).drop(columns="_severity_rank")

    return summary[SUMMARY_COLUMNS]


def main() -> None:
    dataset_scope = read_dataset_scope(DATASET_CONFIG_PATH)
    configured_tag_rules = read_configured_tag_rules(SEC_TAGS_CONFIG_PATH)
    wide = read_wide_facts(WIDE_INPUT_PATH)
    long = read_long_facts(LONG_INPUT_PATH)
    warnings = build_warnings(wide, long, dataset_scope, configured_tag_rules)
    summary = build_summary(warnings)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    warnings.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")
    summary.to_csv(SUMMARY_OUTPUT_PATH, index=False, encoding="utf-8")

    print(f"Read wide facts:      {WIDE_INPUT_PATH}")
    print(f"Read rows:            {len(wide):,}")
    print(f"Read long facts:      {LONG_INPUT_PATH}")
    print(f"Read long rows:       {len(long):,}")
    print(f"Accepted forms:       {';'.join(dataset_scope['accepted_forms'])}")
    print(f"Configured tag rules: {len(configured_tag_rules):,}")
    print(f"Warnings:             {len(warnings):,}")
    print(f"Summary rows:         {len(summary):,}")
    print(f"Saved warnings:       {OUTPUT_PATH}")
    print(f"Saved summary:        {SUMMARY_OUTPUT_PATH}")


if __name__ == "__main__":
    main()

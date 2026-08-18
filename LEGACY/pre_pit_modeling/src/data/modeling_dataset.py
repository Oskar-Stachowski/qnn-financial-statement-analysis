"""
Reusable Commit 08 modeling-dataset builder.

Input:
- data/interim/sec_facts_wide.csv
- data/reports/sec_facts_sanity_warnings.csv
- data/reports/sec_facts_sanity_summary.csv
- configs/dataset_config.yaml

Output:
- data/processed/modeling_dataset.csv
- data/processed/modeling_dataset_excluded.csv
- data/reports/modeling_dataset_split_summary.csv
- data/reports/modeling_dataset_feature_coverage.csv
- data/reports/modeling_dataset_warning_policy.csv
- data/reports/modeling_dataset_quality_report.md

The notebook is the readable EDA and methodology artifact. This module keeps
the deterministic CSV/report generation reusable from both the notebook and the
numbered pipeline runner.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


BASE_DIR = Path(__file__).resolve().parents[2]
INTERIM_DIR = BASE_DIR / "data" / "interim"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
REPORTS_DIR = BASE_DIR / "data" / "reports"
CONFIG_DIR = BASE_DIR / "configs"

WIDE_INPUT_PATH = INTERIM_DIR / "sec_facts_wide.csv"
WARNINGS_INPUT_PATH = REPORTS_DIR / "sec_facts_sanity_warnings.csv"
DATASET_CONFIG_PATH = CONFIG_DIR / "dataset_config.yaml"

MODELING_DATASET_PATH = PROCESSED_DIR / "modeling_dataset.csv"
MODELING_EXCLUDED_PATH = PROCESSED_DIR / "modeling_dataset_excluded.csv"
SPLIT_SUMMARY_PATH = REPORTS_DIR / "modeling_dataset_split_summary.csv"
FEATURE_COVERAGE_PATH = REPORTS_DIR / "modeling_dataset_feature_coverage.csv"
WARNING_POLICY_PATH = REPORTS_DIR / "modeling_dataset_warning_policy.csv"
QUALITY_REPORT_PATH = REPORTS_DIR / "modeling_dataset_quality_report.md"

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

CORE_CURRENT_VARIABLES = ["assets", "liabilities", "revenues", "net_income"]

# checki, które wskazują na problem techniczny, niespójność źródła, błędny okres, zły formularz, duplikat albo poważny problem bilansowy
# powodują usunięcie całego company-year z datasetu głównego
HARD_EXCLUDE_CHECKS = {
    "wide_duplicate_company_year",
    "long_duplicate_company_year_variable",
    "wide_value_differs_from_long",
    "derived_source_metadata_invalid",

    "source_form_outside_dataset_config",
    "source_unit_outside_accepted_units",
    "source_tag_not_in_sec_tags_config",
    "non_numeric_financial_value",

    "source_filing_before_period_end",
    "source_filing_lag_too_long",
    "source_filing_year_after_company_year_window",
    "flow_period_not_annual",
    "revenues_may_be_quarterly",
    "mixed_source_fiscal_years",
    "mixed_source_period_ends",
    "company_year_not_numeric",
    "company_year_in_future",
    "sparse_company_year",
    "source_fy_differs_from_company_year",

    "assets_negative",
    "liabilities_and_equity_negative",
    "liabilities_negative",
    "assets_differs_from_liabilities_and_equity",
    "liabilities_absurdly_above_assets",

    "derived_assets_formula_mismatch",
    "derived_liabilities_formula_mismatch",
    "derived_operating_costs_formula_mismatch",
}

# checki dotyczące konkretnej zmiennej
# dana zmienna jest ustawiana na NaN, ale obserwacja może zostać
FEATURE_CLEANUP_CHECKS = {
    "cash_negative",
    "cash_above_assets",
    "accounts_receivable_above_assets",
    "inventory_negative",
    "inventory_above_assets",
    "ppe_negative",
    "ppe_above_assets",
    "goodwill_above_assets",
    "current_assets_above_assets",
    "current_liabilities_above_liabilities",
    "capex_negative",
    "cost_of_revenue_negative",
    "operating_costs_negative",
    "cost_of_revenue_above_operating_costs",
    "revenues_negative",
}

FEATURE_CLEANUP_VARIABLES = {
    "cash_negative": "cash",
    "cash_above_assets": "cash",
    "accounts_receivable_above_assets": "accounts_receivable",
    "inventory_negative": "inventory",
    "inventory_above_assets": "inventory",
    "ppe_negative": "ppe",
    "ppe_above_assets": "ppe",
    "goodwill_above_assets": "goodwill",
    "current_assets_above_assets": "current_assets",
    "current_liabilities_above_liabilities": "current_liabilities",
    "capex_negative": "capex",
    "cost_of_revenue_negative": "cost_of_revenue",
    "operating_costs_negative": "operating_costs",
    "cost_of_revenue_above_operating_costs": "cost_of_revenue",
    "revenues_negative": "revenues",
}

# potencjalny outlier
# dodane flagi diagnostyczne
DIAGNOSTIC_CHECKS = {
    "large_assets_liabilities_equity_gap", # Nie jest to automatycznie hard error, bo equity może być mapowane inaczej niż klasyczne stockholders_equity, szczególnie przy specyficznych strukturach kapitału
    "mixed_source_accessions", # Dane dla jednego company-year pochodzą z więcej niż jednego accession number, (zgłoszenie SEC)
    "flow_source_fp_not_fy", # Dla zmiennych przepływowych (np. revenues, net_income), ale wcześniej sprawdzam długość okresu start-end. Jeśli okres wygląda jak roczny, to taki fakt może być używalny mimo innego fp
    "net_loss_abs_large_relative_to_revenues", # Realnie trudna sytuacja spółki, małe przychody, jednorazowy odpis albo outlier
    "net_profit_large_relative_to_revenues", # Mały mianownik, zdarzenia jednorazowe, sprzedaż aktywów albo nietypowa struktura sprawozdania
    "net_loss_abs_large_relative_to_assets", # Financial distress, odpisy, restrukturyzacja albo bardzo mała bazę aktywów
    "net_profit_large_relative_to_assets", # Outlier, efekt zdarzenia jednorazowego albo bardzo mała wartość aktywów
    "company_year_outside_configured_dataset_range", # nie występuje, właściwe filtrowanie lat jest zabezpieczone na innych etapach pipelin'u
}

# checki na poziomie całej spółki, wszystkie lata (flaga low coverage)
# dodane flagi coverage
COMPANY_LEVEL_COVERAGE_CHECKS = {
    "assets_missing_for_majority_of_years",
    "liabilities_missing_for_majority_of_years",
    "revenues_missing_for_majority_of_years",
    "net_income_missing_for_majority_of_years",
    "equity_missing_for_majority_of_years",
    "operating_cash_flow_missing_for_majority_of_years",
}

# checki globalne albo strukturalne (diagnostyczne)
# w praktyce nie występują
DATASET_DIAGNOSTIC_CHECKS = {
    "financial_variables_missing_from_wide",
    "long_facts_not_available",
    "wide_company_year_missing_from_long",
    "long_company_year_missing_from_wide",
    "sec_tags_config_not_available",
    "revenue_metadata_not_available",
}

MIN_ASSETS_DENOMINATOR = 1_000.0
MIN_REVENUES_DENOMINATOR = 1_000.0
MIN_CURRENT_LIABILITIES_DENOMINATOR = 1_000.0
MIN_EQUITY_DENOMINATOR = 1_000.0


# ============================================================
# 1. Wczytanie danych wejściowych
# ============================================================
def read_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def ensure_output_dirs() -> None:
    for path in [PROCESSED_DIR, REPORTS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def normalize_key(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def prepare_keys(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output["_cik_key"] = output["cik10"].map(normalize_key)
    output["_year_key"] = pd.to_numeric(output["company_year"], errors="coerce").astype("Int64")
    return output


def read_wide_facts(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}. Run 06_parse_companyfacts.py first.")

    frame = pd.read_csv(path)
    missing_columns = [column for column in ID_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns in {path}: {missing_columns}")

    for column in FINANCIAL_VARIABLES:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame["company_year"] = pd.to_numeric(frame["company_year"], errors="coerce").astype("Int64")
    return prepare_keys(frame)


# ============================================================
# 2. Klasyfikacja Warningów
# ============================================================
def read_warnings(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(
            columns=[
                "warning_id",
                "severity",
                "check_name",
                "scope",
                "cik10",
                "company_year",
                "variable",
            ]
        )

    frame = pd.read_csv(path)
    if frame.empty:
        return prepare_keys(frame.assign(cik10="", company_year=pd.Series(dtype="Int64")))
    return prepare_keys(frame)


def classify_warning_policy(check_name: str) -> tuple[str, str]:
    if check_name in HARD_EXCLUDE_CHECKS:
        return (
            "hard_exclude_company_year",
            "Technical or accounting inconsistency too risky for the main modeling dataset.",
        )
    if check_name in FEATURE_CLEANUP_CHECKS:
        return (
            "feature_level_cleanup",
            "Only the affected variable is set to missing before feature engineering.",
        )
    if check_name in DIAGNOSTIC_CHECKS:
        return (
            "diagnostic_flag",
            "Warning is retained as an audit flag and does not drop the observation.",
        )
    if check_name in COMPANY_LEVEL_COVERAGE_CHECKS:
        return (
            "company_low_coverage_flag",
            "Company is marked as low coverage; row-level target and feature rules decide inclusion.",
        )
    if check_name in DATASET_DIAGNOSTIC_CHECKS:
        return (
            "dataset_diagnostic",
            "Dataset-level diagnostic documented in the report.",
        )
    return (
        "diagnostic_flag_unclassified",
        "Not in the Commit 8 policy table; retained as a conservative diagnostic flag.",
    )


def warning_policy_report(warnings: pd.DataFrame) -> pd.DataFrame:
    if warnings.empty:
        return pd.DataFrame(columns=["check_name", "policy", "warning_count", "company_count", "company_year_count", "reason"])

    grouped = (
        warnings.groupby("check_name", dropna=False)
        .agg(
            warning_count=("warning_id", "count"),
            company_count=("_cik_key", lambda series: series[series.ne("")].nunique()),
            company_year_count=(
                "_year_key",
                lambda series: int(series.notna().sum()),
            ),
        )
        .reset_index()
    )
    policies = grouped["check_name"].map(lambda value: classify_warning_policy(str(value)))
    grouped["policy"] = policies.map(lambda item: item[0])
    grouped["reason"] = policies.map(lambda item: item[1])
    return grouped[["check_name", "policy", "warning_count", "company_count", "company_year_count", "reason"]].sort_values(
        ["policy", "warning_count", "check_name"],
        ascending=[True, False, True],
    )


# ============================================================
# 3. Mapowanie warningów na obserwacje
# ============================================================
def warning_key(row: pd.Series) -> tuple[str, int] | None:
    if not row.get("_cik_key", "") or pd.isna(row.get("_year_key")):
        return None
    return (str(row["_cik_key"]), int(row["_year_key"]))


def build_warning_maps(warnings: pd.DataFrame) -> dict[str, Any]:
    hard: dict[tuple[str, int], set[str]] = defaultdict(set)
    cleanup: dict[tuple[str, int], set[str]] = defaultdict(set)
    cleanup_variables: dict[tuple[str, int], set[str]] = defaultdict(set)
    diagnostics: dict[str, dict[tuple[str, int], bool]] = defaultdict(dict)
    low_coverage: dict[str, set[str]] = defaultdict(set)

    for _, row in warnings.iterrows():
        check_name = str(row.get("check_name", "")).strip()
        scope = str(row.get("scope", "")).strip()
        key = warning_key(row)
        policy, _ = classify_warning_policy(check_name)

        if policy == "hard_exclude_company_year" and key is not None:
            hard[key].add(check_name)
        elif policy == "feature_level_cleanup" and key is not None:
            variable = str(row.get("variable", "")).strip()
            if not variable or variable not in FINANCIAL_VARIABLES:
                variable = FEATURE_CLEANUP_VARIABLES.get(check_name, "")
            if variable:
                cleanup[key].add(f"{check_name}:{variable}")
                cleanup_variables[key].add(variable)
        elif policy == "company_low_coverage_flag" and scope == "company":
            cik_key = str(row.get("_cik_key", "")).strip()
            if cik_key:
                low_coverage[check_name].add(cik_key)
        elif policy in {"diagnostic_flag", "diagnostic_flag_unclassified"} and key is not None:
            diagnostics[check_name][key] = True

    return {
        "hard": hard,
        "cleanup": cleanup,
        "cleanup_variables": cleanup_variables,
        "diagnostics": diagnostics,
        "low_coverage": low_coverage,
    }


def semicolon_join(values: set[str] | list[str]) -> str:
    return ";".join(sorted(str(value) for value in values if str(value)))


def apply_warning_policy(frame: pd.DataFrame, warning_maps: dict[str, Any]) -> pd.DataFrame:
    output = frame.copy()
    keys = list(zip(output["_cik_key"], output["_year_key"].astype("Int64")))

    hard_reasons = []
    cleanup_reasons = []
    for key in keys:
        normalized = (str(key[0]), int(key[1])) if pd.notna(key[1]) else ("", -1)
        hard_reasons.append(semicolon_join(warning_maps["hard"].get(normalized, set())))
        cleanup_reasons.append(semicolon_join(warning_maps["cleanup"].get(normalized, set())))

    output["hard_exclude_reasons"] = hard_reasons
    output["hard_exclude_flag"] = output["hard_exclude_reasons"].str.len().gt(0)
    output["feature_cleanup_reasons"] = cleanup_reasons
    output["feature_cleanup_flag"] = output["feature_cleanup_reasons"].str.len().gt(0)

    for key, variables in warning_maps["cleanup_variables"].items():
        mask = output["_cik_key"].eq(key[0]) & output["_year_key"].eq(key[1])
        for variable in variables:
            if variable in output.columns:
                output.loc[mask, variable] = np.nan

    for check_name, check_keys in warning_maps["diagnostics"].items():
        column = f"flag_{check_name}"
        output[column] = [
            (str(key[0]), int(key[1])) in check_keys if pd.notna(key[1]) else False
            for key in keys
        ]

    for check_name, ciks in warning_maps["low_coverage"].items():
        column = f"flag_{check_name}"
        output[column] = output["_cik_key"].isin(ciks)

    return output



# ============================================================
# 4. Feature Engineering
# ============================================================
def positive_denominator(series: pd.Series, minimum: float) -> pd.Series:
    return series.notna() & series.gt(minimum)


def safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    minimum_denominator: float,
    require_positive_denominator: bool = True,
) -> pd.Series:
    result = pd.Series(np.nan, index=numerator.index, dtype="float64")
    if require_positive_denominator:
        valid = numerator.notna() & positive_denominator(denominator, minimum_denominator)
    else:
        valid = numerator.notna() & denominator.notna() & denominator.abs().gt(minimum_denominator)
    result.loc[valid] = numerator.loc[valid] / denominator.loc[valid]
    return result


def add_financial_features(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()

    output["current_ratio"] = safe_ratio(
        output["current_assets"],
        output["current_liabilities"],
        MIN_CURRENT_LIABILITIES_DENOMINATOR,
    )
    output["debt_to_assets"] = safe_ratio(
        output["liabilities"],
        output["assets"],
        MIN_ASSETS_DENOMINATOR
    )
    output["liabilities_to_equity"] = safe_ratio(
        output["liabilities"],
        output["equity"],
        MIN_EQUITY_DENOMINATOR,
    )
    output["roa"] = safe_ratio(
        output["net_income"],
        output["assets"],
        MIN_ASSETS_DENOMINATOR
    )
    output["roe"] = safe_ratio(
        output["net_income"],
        output["equity"],
        MIN_EQUITY_DENOMINATOR
    )
    output["profit_margin"] = safe_ratio(
        output["net_income"],
        output["revenues"],
        MIN_REVENUES_DENOMINATOR
    )
    output["asset_turnover"] = safe_ratio(
        output["revenues"],
        output["assets"],
        MIN_ASSETS_DENOMINATOR
    )
    output["working_capital_to_assets"] = safe_ratio(
        output["current_assets"] - output["current_liabilities"],
        output["assets"],
        MIN_ASSETS_DENOMINATOR,
    )
    output["cash_to_assets"] = safe_ratio(
        output["cash"],
        output["assets"],
        MIN_ASSETS_DENOMINATOR
    )

    sorted_output = output.sort_values(["_cik_key", "company_year"]).copy()
    grouped = sorted_output.groupby("_cik_key", dropna=False)
    previous_revenues = grouped["revenues"].shift(1)
    previous_year = grouped["company_year"].shift(1)
    valid_growth = (
        sorted_output["revenues"].notna()
        & previous_revenues.notna()
        & sorted_output["revenues"].gt(MIN_REVENUES_DENOMINATOR)
        & previous_revenues.gt(MIN_REVENUES_DENOMINATOR)
        & previous_year.eq(sorted_output["company_year"] - 1)
    )
    sorted_output["sales_growth"] = np.nan
    sorted_output.loc[valid_growth, "sales_growth"] = (
        sorted_output.loc[valid_growth, "revenues"] / previous_revenues.loc[valid_growth] - 1.0
    )

    output["sales_growth"] = sorted_output.sort_index()["sales_growth"]
    output["flag_assets_denominator_invalid"] = ~positive_denominator(output["assets"], MIN_ASSETS_DENOMINATOR)
    output["flag_revenues_denominator_invalid"] = ~positive_denominator(output["revenues"], MIN_REVENUES_DENOMINATOR)
    output["flag_current_liabilities_denominator_invalid"] = ~positive_denominator(
        output["current_liabilities"],
        MIN_CURRENT_LIABILITIES_DENOMINATOR,
    )
    output["flag_equity_denominator_invalid"] = ~positive_denominator(output["equity"], MIN_EQUITY_DENOMINATOR)

    return output


# ============================================================
# 5. Podział zbioru na treningowy/walidacyjny/testowy
# ============================================================
def assign_split(year: int, config: dict[str, Any]) -> str:
    splits = config.get("splits", {}) if isinstance(config, dict) else {}
    train_end_year = int(splits.get("train_end_year", 2020))
    validation_years = {int(value) for value in splits.get("validation_years", [2021, 2022])}
    test_years = {int(value) for value in splits.get("test_years", [2023, 2024])}

    if year <= train_end_year:
        return "train"
    if year in validation_years:
        return "validation"
    if year in test_years:
        return "test"
    return "excluded"


# ============================================================
# 6. Target - pogorszenie wskaźników o 20%
# ============================================================
def add_target(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    target_config = config.get("target", {}) if isinstance(config, dict) else {}
    horizon = int(target_config.get("horizon_years", 1))
    rules = target_config.get("deterioration_rules", {})

    roa_drop = float(rules.get("roa_drop_pct", 0.20))
    margin_drop = float(rules.get("profit_margin_drop_pct", 0.20))
    debt_increase = float(rules.get("debt_to_assets_increase_pct", 0.10))
    current_ratio_drop = float(rules.get("current_ratio_drop_pct", 0.15))
    min_conditions = int(rules.get("min_conditions_met", 2))

    next_metrics = frame[
        [
            "_cik_key",
            "company_year",
            "roa",
            "profit_margin",
            "debt_to_assets",
            "current_ratio",
            "hard_exclude_flag",
            "hard_exclude_reasons",
        ]
    ].copy()
    next_metrics["company_year"] = next_metrics["company_year"] - horizon
    next_metrics = next_metrics.rename(
        columns={
            "roa": "roa_next",
            "profit_margin": "profit_margin_next",
            "debt_to_assets": "debt_to_assets_next",
            "current_ratio": "current_ratio_next",
            "hard_exclude_flag": "next_year_hard_exclude_flag",
            "hard_exclude_reasons": "next_year_hard_exclude_reasons",
        }
    )

    output = frame.merge(next_metrics, on=["_cik_key", "company_year"], how="left")
    output["target_year"] = output["company_year"] + horizon

    output["roa_target_input_valid"] = output["roa"].notna() & output["roa_next"].notna()
    output["profit_margin_target_input_valid"] = output["profit_margin"].notna() & output["profit_margin_next"].notna()
    output["debt_to_assets_target_input_valid"] = output["debt_to_assets"].notna() & output["debt_to_assets_next"].notna()
    output["current_ratio_target_input_valid"] = output["current_ratio"].notna() & output["current_ratio_next"].notna()

    output["roa_deteriorated"] = output["roa_target_input_valid"] & output["roa_next"].le(output["roa"] * (1 - roa_drop))
    output["profit_margin_deteriorated"] = output["profit_margin_target_input_valid"] & output["profit_margin_next"].le(
        output["profit_margin"] * (1 - margin_drop)
    )
    output["debt_to_assets_deteriorated"] = output["debt_to_assets_target_input_valid"] & output["debt_to_assets_next"].ge(
        output["debt_to_assets"] * (1 + debt_increase)
    )
    output["current_ratio_deteriorated"] = output["current_ratio_target_input_valid"] & output["current_ratio_next"].le(
        output["current_ratio"] * (1 - current_ratio_drop)
    )

    valid_columns = [
        "roa_target_input_valid",
        "profit_margin_target_input_valid",
        "debt_to_assets_target_input_valid",
        "current_ratio_target_input_valid",
    ]
    condition_columns = [
        "roa_deteriorated",
        "profit_margin_deteriorated",
        "debt_to_assets_deteriorated",
        "current_ratio_deteriorated",
    ]

    output["valid_target_condition_count"] = output[valid_columns].sum(axis=1).astype(int)
    output["target_conditions_met"] = output[condition_columns].sum(axis=1).astype(int)
    output["financial_deterioration_next_year"] = pd.NA
    enough_inputs = (
        output["valid_target_condition_count"].ge(min_conditions)
        & ~output["next_year_hard_exclude_flag"].fillna(False)
    )
    output.loc[enough_inputs, "financial_deterioration_next_year"] = (
        output.loc[enough_inputs, "target_conditions_met"].ge(min_conditions).astype(int)
    )
    output["financial_deterioration_next_year"] = output["financial_deterioration_next_year"].astype("Int64")

    return output


def feature_year_bounds(config: dict[str, Any]) -> tuple[int, int, int]:
    dataset_config = config.get("dataset", {}) if isinstance(config, dict) else {}
    start_year = int(dataset_config.get("start_year", 2011))
    source_end_year = int(dataset_config.get("end_year", 2025))
    horizon = int(config.get("target", {}).get("horizon_years", 1)) if isinstance(config, dict) else 1
    feature_end_year = source_end_year - horizon
    return start_year, feature_end_year, source_end_year


def add_exclusion_reasons(
    frame: pd.DataFrame,
    base_features: list[str],
    config: dict[str, Any],
) -> pd.DataFrame:
    output = frame.copy()
    dataset_config = config.get("dataset", {}) if isinstance(config, dict) else {}
    max_missing_feature_ratio = float(dataset_config.get("max_missing_feature_ratio", 0.2))

    output["missing_feature_count"] = output[base_features].isna().sum(axis=1).astype(int)
    output["missing_feature_ratio"] = output["missing_feature_count"] / max(len(base_features), 1)

    reasons: dict[int, list[str]] = {index: [] for index in output.index}

    def add_reason(mask: pd.Series, reason: str) -> None:
        for index in output.index[mask.fillna(False)]:
            reasons[index].append(reason)

    add_reason(output["split"].eq("excluded"), "missing_split_assignment")
    add_reason(output["hard_exclude_flag"], "hard_exclude_company_year")
    add_reason(output["next_year_hard_exclude_flag"].fillna(False), "next_year_hard_exclude")
    add_reason(output["financial_deterioration_next_year"].isna(), "missing_target_inputs")
    add_reason(output["missing_feature_ratio"].gt(max_missing_feature_ratio), "feature_missing_ratio_above_config")

    missing_core = pd.Series(False, index=output.index)
    for variable in CORE_CURRENT_VARIABLES:
        if variable in output.columns:
            missing_core = missing_core | output[variable].isna()
    add_reason(missing_core, "missing_core_current_variable")

    output["exclusion_reasons"] = [semicolon_join(set(values)) for _, values in sorted(reasons.items())]
    output["is_modeling_observation"] = output["exclusion_reasons"].str.len().eq(0)
    return output


def split_summary(all_feature_rows: pd.DataFrame, modeling_dataset: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for split in ["train", "validation", "test"]:
        all_split = all_feature_rows[all_feature_rows["split"].eq(split)]
        included_split = modeling_dataset[modeling_dataset["split"].eq(split)]
        positive_count = int(included_split["financial_deterioration_next_year"].fillna(0).eq(1).sum())
        row_count = len(included_split)
        rows.append(
            {
                "split": split,
                "feature_year_min": int(included_split["company_year"].min()) if row_count else "",
                "feature_year_max": int(included_split["company_year"].max()) if row_count else "",
                "row_count": row_count,
                "company_count": int(included_split["_cik_key"].nunique()) if row_count else 0,
                "positive_target_count": positive_count,
                "positive_target_ratio": positive_count / row_count if row_count else 0.0,
                "missing_target_count": int(all_split["financial_deterioration_next_year"].isna().sum()),
                "excluded_count": int(len(all_split) - row_count),
            }
        )
    return pd.DataFrame(rows)


def feature_coverage_report(modeling_dataset: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for split in ["all", "train", "validation", "test"]:
        subset = modeling_dataset if split == "all" else modeling_dataset[modeling_dataset["split"].eq(split)]
        row_count = len(subset)
        for feature in feature_columns:
            non_missing = int(subset[feature].notna().sum()) if feature in subset.columns else 0
            rows.append(
                {
                    "split": split,
                    "feature": feature,
                    "row_count": row_count,
                    "non_missing_count": non_missing,
                    "missing_count": row_count - non_missing,
                    "coverage_ratio": non_missing / row_count if row_count else 0.0,
                }
            )
    return pd.DataFrame(rows)


def explode_reasons(series: pd.Series) -> pd.Series:
    values: list[str] = []
    for item in series.dropna():
        for reason in str(item).split(";"):
            if reason:
                values.append(reason)
    if not values:
        return pd.Series(dtype="int64")
    return pd.Series(values).value_counts()


def select_output_columns(frame: pd.DataFrame, feature_columns: list[str]) -> list[str]:
    technical_columns = [
        "target_year",
        "split",
        "financial_deterioration_next_year",
        "target_conditions_met",
        "valid_target_condition_count",
        "roa_next",
        "profit_margin_next",
        "debt_to_assets_next",
        "current_ratio_next",
        "roa_deteriorated",
        "profit_margin_deteriorated",
        "debt_to_assets_deteriorated",
        "current_ratio_deteriorated",
        "missing_feature_count",
        "missing_feature_ratio",
        "hard_exclude_flag",
        "hard_exclude_reasons",
        "feature_cleanup_flag",
        "feature_cleanup_reasons",
        "next_year_hard_exclude_flag",
        "next_year_hard_exclude_reasons",
    ]
    flag_columns = sorted(column for column in frame.columns if column.startswith("flag_"))
    columns = [
        column
        for column in [
            *ID_COLUMNS,
            *FINANCIAL_VARIABLES,
            *feature_columns,
            *technical_columns,
            *flag_columns,
        ]
        if column in frame.columns
    ]
    return list(dict.fromkeys(columns))


def markdown_table(frame: pd.DataFrame, max_rows: int = 20) -> str:
    if frame.empty:
        return "_Brak danych._"
    output = frame.head(max_rows).copy()
    columns = [str(column) for column in output.columns]

    def format_cell(value: Any) -> str:
        if pd.isna(value):
            return ""
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)

    rows = [[format_cell(value) for value in row] for row in output.to_numpy()]
    widths = [
        max(len(column), *(len(row[index]) for row in rows)) if rows else len(column)
        for index, column in enumerate(columns)
    ]
    header = "| " + " | ".join(column.ljust(widths[index]) for index, column in enumerate(columns)) + " |"
    separator = "| " + " | ".join("-" * widths[index] for index in range(len(columns))) + " |"
    body = [
        "| " + " | ".join(row[index].ljust(widths[index]) for index in range(len(columns))) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def build_quality_report(
    config: dict[str, Any],
    source_rows: pd.DataFrame,
    all_feature_rows: pd.DataFrame,
    modeling_dataset: pd.DataFrame,
    excluded: pd.DataFrame,
    split_report: pd.DataFrame,
    feature_report: pd.DataFrame,
    warning_policy: pd.DataFrame,
) -> str:
    start_year, feature_end_year, source_end_year = feature_year_bounds(config)
    exclusion_counts = explode_reasons(excluded["exclusion_reasons"]) if not excluded.empty else pd.Series(dtype="int64")
    target_distribution = (
        modeling_dataset.groupby("split")["financial_deterioration_next_year"]
        .value_counts(dropna=False)
        .rename("count")
        .reset_index()
        if not modeling_dataset.empty
        else pd.DataFrame(columns=["split", "financial_deterioration_next_year", "count"])
    )
    top_feature_coverage = feature_report[feature_report["split"].eq("all")].sort_values("coverage_ratio")
    hard_policy = warning_policy[warning_policy["policy"].eq("hard_exclude_company_year")]
    cleanup_policy = warning_policy[warning_policy["policy"].eq("feature_level_cleanup")]
    diagnostic_policy = warning_policy[warning_policy["policy"].str.contains("diagnostic", na=False)]
    coverage_policy = warning_policy[warning_policy["policy"].eq("company_low_coverage_flag")]
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    leakage_checks = [
        f"- Maksymalny feature year w `modeling_dataset.csv`: `{int(modeling_dataset['company_year'].max()) if not modeling_dataset.empty else ''}`.",
        f"- Konfiguracyjny feature range: `{start_year}-{feature_end_year}`; source end year dla targetu: `{source_end_year}`.",
        f"- Liczba obserwacji testowych z roku 2024: `{int(modeling_dataset['company_year'].eq(2024).sum())}`.",
        f"- Liczba obserwacji 2025 w datasetcie modelowym: `{int(modeling_dataset['company_year'].eq(2025).sum())}`.",
    ]

    report = [
        "# Modeling Dataset Quality Report",
        "",
        f"Generated: `{generated_at}`",
        "",
        "## Scope",
        "",
        "- Commit 08 przygotowuje pierwszy dataset modelowy `company-year` do eksperymentow ML/QNN.",
        "- Etap nie trenuje modeli, nie skaluje feature'ow i nie wykonuje finalnej imputacji.",
        "- Rok `t+1` jest uzywany tylko do targetu `financial_deterioration_next_year`.",
        "",
        "## Inputs And Outputs",
        "",
        f"- Input wide facts: `{WIDE_INPUT_PATH.relative_to(BASE_DIR)}`",
        f"- Input sanity warnings: `{WARNINGS_INPUT_PATH.relative_to(BASE_DIR)}`",
        f"- Output dataset: `{MODELING_DATASET_PATH.relative_to(BASE_DIR)}`",
        f"- Output exclusions: `{MODELING_EXCLUDED_PATH.relative_to(BASE_DIR)}`",
        f"- Output split summary: `{SPLIT_SUMMARY_PATH.relative_to(BASE_DIR)}`",
        f"- Output feature coverage: `{FEATURE_COVERAGE_PATH.relative_to(BASE_DIR)}`",
        f"- Output warning policy: `{WARNING_POLICY_PATH.relative_to(BASE_DIR)}`",
        "",
        "## Dataset Counts",
        "",
        f"- Source company-years: `{len(source_rows):,}`",
        f"- Feature-year candidates `{start_year}-{feature_end_year}`: `{len(all_feature_rows):,}`",
        f"- Modeling observations: `{len(modeling_dataset):,}`",
        f"- Excluded feature-year observations: `{len(excluded):,}`",
        f"- Companies in modeling dataset: `{modeling_dataset['_cik_key'].nunique() if not modeling_dataset.empty else 0:,}`",
        "",
        "## Split Summary",
        "",
        markdown_table(split_report),
        "",
        "## Target Distribution",
        "",
        markdown_table(target_distribution),
        "",
        "## Main Exclusion Reasons",
        "",
        markdown_table(exclusion_counts.rename_axis("reason").reset_index(name="count")),
        "",
        "## Lowest Feature Coverage",
        "",
        markdown_table(top_feature_coverage[["feature", "row_count", "non_missing_count", "missing_count", "coverage_ratio"]]),
        "",
        "## Warning Policy From Commit 07",
        "",
        markdown_table(warning_policy, max_rows=len(warning_policy)),
        "",
        "## Hard Exclude Checks Applied",
        "",
        markdown_table(hard_policy[["check_name", "warning_count", "company_count", "company_year_count"]], max_rows=len(hard_policy)),
        "",
        "## Feature-Level Cleanup Checks Applied",
        "",
        markdown_table(cleanup_policy[["check_name", "warning_count", "company_count", "company_year_count"]], max_rows=len(cleanup_policy)),
        "",
        "## Diagnostic Flags Retained",
        "",
        markdown_table(diagnostic_policy[["check_name", "warning_count", "company_count", "company_year_count"]], max_rows=len(diagnostic_policy)),
        "",
        "## Company Coverage Flags Retained",
        "",
        markdown_table(coverage_policy[["check_name", "warning_count", "company_count", "company_year_count"]], max_rows=len(coverage_policy)),
        "",
        "## Leakage Checks",
        "",
        *leakage_checks,
        "",
        "## Methodological Decisions To Approve",
        "",
        f"- Minimalny mianownik dla `assets`: `{MIN_ASSETS_DENOMINATOR:,.0f}` USD.",
        f"- Minimalny mianownik dla `revenues`: `{MIN_REVENUES_DENOMINATOR:,.0f}` USD.",
        f"- Minimalny mianownik dla `current_liabilities`: `{MIN_CURRENT_LIABILITIES_DENOMINATOR:,.0f}` USD.",
        f"- Minimalny dodatni mianownik dla `equity`: `{MIN_EQUITY_DENOMINATOR:,.0f}` USD.",
        f"- Maksymalny dopuszczalny missing ratio feature'ow bazowych: `{config.get('dataset', {}).get('max_missing_feature_ratio', 0.2)}`.",
        "- Brak winsoryzacji w Commit 08; outliery zostaja widoczne do decyzji przed eksperymentami.",
        "- Brak imputacji w Commit 08; obserwacje z malym poziomem brakow moga pozostac w datasetcie z jawnie opisanymi brakami.",
        "- Spolki z niskim coverage dostaja flagi diagnostyczne; nie sa automatycznie usuwane jako cale spolki.",
        "",
        "## Notebook Figures",
        "",
        "- Diagnostic figures are generated by `notebooks/08_modeling_dataset_eda.ipynb`.",
        "- Default output directory: `reports/figures/commit_8/`.",
        "",
        "## Notes For Thesis Workflow",
        "",
        "- Ten raport opisuje fakty techniczne i decyzje przetwarzania danych.",
        "- Interpretacja ekonomiczna oraz finalne decyzje metodologiczne powinny zostac dopisane przez autora pracy.",
    ]
    return "\n".join(report) + "\n"


def build_modeling_dataset() -> dict[str, Any]:
    ensure_output_dirs()
    config = read_config(DATASET_CONFIG_PATH)
    source_start_year, feature_end_year, source_end_year = feature_year_bounds(config)
    base_features = list(config.get("features", {}).get("base", []))
    if not base_features:
        raise ValueError("configs/dataset_config.yaml must define features.base for Commit 08.")

    wide = read_wide_facts(WIDE_INPUT_PATH)
    warnings = read_warnings(WARNINGS_INPUT_PATH)
    policy = warning_policy_report(warnings)
    warning_maps = build_warning_maps(warnings)

    cleaned = apply_warning_policy(wide, warning_maps)
    featured = add_financial_features(cleaned)
    targeted = add_target(featured, config)

    all_feature_rows = targeted[
        targeted["company_year"].between(source_start_year, feature_end_year, inclusive="both")
    ].copy()
    all_feature_rows["split"] = all_feature_rows["company_year"].map(lambda year: assign_split(int(year), config))
    all_feature_rows = add_exclusion_reasons(all_feature_rows, base_features, config)

    output_columns = select_output_columns(all_feature_rows, base_features)
    modeling_dataset = all_feature_rows[all_feature_rows["is_modeling_observation"]].copy()
    excluded = all_feature_rows[~all_feature_rows["is_modeling_observation"]].copy()

    modeling_output = modeling_dataset[[*output_columns]].copy()
    excluded_output = excluded[[*output_columns, "exclusion_reasons"]].copy()

    split_report = split_summary(all_feature_rows, modeling_dataset)
    feature_report = feature_coverage_report(modeling_dataset, base_features)

    quality_report = build_quality_report(
        config=config,
        source_rows=wide,
        all_feature_rows=all_feature_rows,
        modeling_dataset=modeling_dataset,
        excluded=excluded,
        split_report=split_report,
        feature_report=feature_report,
        warning_policy=policy,
    )

    modeling_output.to_csv(MODELING_DATASET_PATH, index=False, encoding="utf-8")
    excluded_output.to_csv(MODELING_EXCLUDED_PATH, index=False, encoding="utf-8")
    split_report.to_csv(SPLIT_SUMMARY_PATH, index=False, encoding="utf-8")
    feature_report.to_csv(FEATURE_COVERAGE_PATH, index=False, encoding="utf-8")
    policy.to_csv(WARNING_POLICY_PATH, index=False, encoding="utf-8")
    QUALITY_REPORT_PATH.write_text(quality_report, encoding="utf-8")

    return {
        "source_rows": len(wide),
        "feature_year_rows": len(all_feature_rows),
        "modeling_rows": len(modeling_dataset),
        "excluded_rows": len(excluded),
        "feature_year_min": source_start_year,
        "feature_year_max": feature_end_year,
        "source_year_max": source_end_year,
        "output_paths": [
            MODELING_DATASET_PATH,
            MODELING_EXCLUDED_PATH,
            SPLIT_SUMMARY_PATH,
            FEATURE_COVERAGE_PATH,
            WARNING_POLICY_PATH,
            QUALITY_REPORT_PATH,
        ],
    }


def main() -> None:
    result = build_modeling_dataset()
    print("Commit 08 modeling dataset built.")
    print(f"Source rows:        {result['source_rows']:,}")
    print(f"Feature-year rows:  {result['feature_year_rows']:,}")
    print(f"Modeling rows:      {result['modeling_rows']:,}")
    print(f"Excluded rows:      {result['excluded_rows']:,}")
    print(f"Feature years:      {result['feature_year_min']}-{result['feature_year_max']}")
    print(f"Source year max:    {result['source_year_max']}")
    for path in result["output_paths"]:
        print(f"Saved:              {path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()

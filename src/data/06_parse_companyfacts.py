"""
Parse SEC Company Facts JSON files into configured financial variables.

Input:
- data/raw/companyfacts/CIK{cik10}.json
- data/processed/research_universe.csv
- configs/sec_tags.yaml

Output:
- data/interim/sec_facts_long.csv
- data/interim/sec_facts_wide.csv
- data/reports/xbrl_variable_coverage.csv
- data/reports/xbrl_tag_usage.csv
- data/reports/xbrl_missing_by_company.csv
- data/reports/xbrl_parse_quality_report.md

This script applies the XBRL tag mapping from configs/sec_tags.yaml to SEC
Company Facts. It keeps only accepted units, prefers annual facts and 10-K
filings, resolves duplicates deterministically, and does not impute missing
values or interpret the results.
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

LONG_OUTPUT_PATH = INTERIM_DIR / "sec_facts_long.csv"
WIDE_OUTPUT_PATH = INTERIM_DIR / "sec_facts_wide.csv"
VARIABLE_COVERAGE_PATH = REPORTS_DIR / "xbrl_variable_coverage.csv"
TAG_USAGE_PATH = REPORTS_DIR / "xbrl_tag_usage.csv"
MISSING_BY_COMPANY_PATH = REPORTS_DIR / "xbrl_missing_by_company.csv"
QUALITY_REPORT_PATH = REPORTS_DIR / "xbrl_parse_quality_report.md"

ACCEPTED_UNITS = ("USD",)
PREFERRED_FORMS = ("10-K", "10-K/A", "10-KT", "10-KT/A")
ANNUAL_PERIOD_MIN_DAYS = 300
ANNUAL_PERIOD_MAX_DAYS = 400
MAX_END_YEAR_LEAD = 1
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


def annual_rank(fact: dict[str, Any]) -> int:
    if str(fact.get("fp", "") or "").upper() == "FY":
        return 0

    days = period_days(fact)
    if days is not None and ANNUAL_PERIOD_MIN_DAYS <= days <= ANNUAL_PERIOD_MAX_DAYS:
        return 1

    frame = str(fact.get("frame", "") or "")
    if re.fullmatch(r"CY\d{4}", frame) or re.fullmatch(r"CY\d{4}Q4I", frame):
        return 2

    form = str(fact.get("form", "") or "").upper()
    if form in PREFERRED_FORMS and fact.get("end") and not fact.get("start"):
        return 3

    return NON_ANNUAL_RANK


def form_rank(form: object) -> int:
    form_text = str(form or "").upper()
    return PREFERRED_FORMS.index(form_text) if form_text in PREFERRED_FORMS else len(PREFERRED_FORMS)


def company_year_from_fact(fact: dict[str, Any]) -> str:
    end_date = parse_iso_date(fact.get("end"))
    if end_date is not None:
        return str(end_date.year)

    match = re.match(r"CY(\d{4})", str(fact.get("frame", "") or ""))
    if match:
        return match.group(1)

    fiscal_year = fact.get("fy")
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
        return 0 if str(int(fact.get("fy"))) == company_year else 1
    except (TypeError, ValueError):
        return 1


def candidate_sort_key(row: dict[str, Any]) -> tuple:
    return (
        row["_annual_rank"],
        row["_form_rank"],
        row["_fy_match_rank"],
        row["_tier_rank"],
        row["tag_priority"],
        -date_sort_value(row["filed"]),
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
        "_form_rank": form_rank(fact.get("form")),
        "_fy_match_rank": fy_match_rank(fact, company_year),
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


def parse_companyfacts_file(
    company: dict[str, str],
    path: Path,
    rules: pd.DataFrame,
    selected_rows: dict[tuple[str, str, str], dict[str, Any]],
    stats: dict[str, int],
) -> None:
    with path.open("r", encoding="utf-8") as f:
        all_facts = json.load(f).get("facts", {})

    if not isinstance(all_facts, dict):
        stats["files_without_facts"] += 1
        return

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
                if fact.get("val") in (None, ""):
                    stats["facts_without_value"] += 1
                    continue

                company_year = company_year_from_fact(fact)
                if not company_year:
                    stats["facts_without_company_year"] += 1
                    continue

                if has_invalid_end_year(fact):
                    stats["facts_rejected_invalid_end_year"] += 1
                    continue

                rank = annual_rank(fact)
                if rank == NON_ANNUAL_RANK:
                    stats["facts_rejected_nonannual"] += 1
                    continue

                stats["candidate_facts"] += 1
                keep_best_candidate(
                    selected_rows,
                    build_candidate_row(company, path, rule, str(unit), fact, company_year, rank),
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


def write_quality_report(path: Path, stats: dict[str, int], output_counts: dict[str, int]) -> None:
    count_metrics = [
        ("Companies in research universe", "companies_in_universe"),
        ("Company Facts files found", "companyfacts_files_found"),
        ("Company Facts files parsed", "companyfacts_files_parsed"),
        ("Missing Company Facts files", "missing_companyfacts_files"),
        ("JSON parse errors", "json_parse_errors"),
        ("Files without `facts`", "files_without_facts"),
        ("Candidate annual facts", "candidate_facts"),
        ("Facts rejected by unit", "facts_rejected_unit"),
        ("Facts rejected as non-annual", "facts_rejected_nonannual"),
        ("Facts rejected by invalid end year", "facts_rejected_invalid_end_year"),
        ("Facts without value", "facts_without_value"),
        ("Facts without company year", "facts_without_company_year"),
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
        f"- Accepted units: `{';'.join(ACCEPTED_UNITS)}`",
        f"- Preferred forms: `{';'.join(PREFERRED_FORMS)}`",
        "",
        "## Processing Rules",
        "",
        "- Missing values were not imputed.",
        "- Facts with units outside the accepted unit list were skipped.",
        "- Non-annual facts were skipped.",
        f"- Facts with `end` year more than {MAX_END_YEAR_LEAD} year after `fy` or `filed` year were skipped.",
        "- Duplicate facts were resolved deterministically using annual status, preferred form, fiscal-year match, tier, tag priority, filing date, period end date and accession number.",
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
            parse_companyfacts_file(company, path, rules, selected_rows, stats)
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

    print(f"Read research universe companies: {len(companies):,}")
    print(f"Read configured variables:        {len(variables):,}")
    print(f"Read configured tag rules:        {len(rules):,}")

    long_frame, stats = parse_all_companyfacts(companies, rules)
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

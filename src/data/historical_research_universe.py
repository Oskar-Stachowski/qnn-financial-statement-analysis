"""Pure construction logic for the filing-first historical research universe.

The module deliberately does not build model features or alter the frozen PIT-B
target. Membership, feature availability, and target availability are separate
columns throughout the output.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
from pathlib import Path
import re
from typing import Any

import pandas as pd
import yaml


BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "configs" / "research_universe_pit.yaml"


@dataclass(frozen=True)
class UniverseScope:
    feature_year_start: int
    feature_year_end: int
    development_feature_year_end: int
    filing_index_year_start: int
    filing_index_year_end: int
    qualifying_forms: frozenset[str]


def load_policy(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        policy = yaml.safe_load(stream) or {}
    if not isinstance(policy, dict):
        raise ValueError(f"Invalid historical-universe policy: {path}")
    return policy


def clean_text(value: object) -> str:
    """Return normalized text without turning pandas missing values into ``nan``."""

    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def parse_scope(policy: dict[str, Any]) -> UniverseScope:
    scope = policy["scope"]
    test_years = [int(year) for year in scope["mechanically_applied_test_years"]]
    feature_year_end = max(
        int(scope["development_feature_year_end"]),
        max(test_years, default=int(scope["development_feature_year_end"])),
    )
    return UniverseScope(
        feature_year_start=int(scope["feature_year_start"]),
        feature_year_end=feature_year_end,
        development_feature_year_end=int(scope["development_feature_year_end"]),
        filing_index_year_start=int(scope["filing_index_year_start"]),
        filing_index_year_end=int(scope["filing_index_year_end"]),
        qualifying_forms=frozenset(
            str(form).upper() for form in policy["forms"]["qualifying_original"]
        ),
    )


def normalize_cik(value: object) -> str:
    text = clean_text(value)
    if not text:
        return ""
    try:
        return str(int(float(text))).zfill(10)
    except ValueError:
        return ""


def normalize_accession(value: object) -> str:
    text = clean_text(value)
    match = re.search(r"(\d{10}-\d{2}-\d{6})", text)
    return match.group(1) if match else ""


def parse_sic(value: object) -> int | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        sic = int(float(text))
    except ValueError:
        return None
    return sic if 100 <= sic <= 9999 else None


def normalize_date(value: object) -> str:
    text = clean_text(value)
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return text


def normalize_accepted_at(value: object) -> str:
    text = clean_text(value)
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 14:
        return (
            f"{digits[:4]}-{digits[4:6]}-{digits[6:8]} "
            f"{digits[8:10]}:{digits[10:12]}:{digits[12:14]}"
        )
    return text


def parse_master_index(
    text: str,
    *,
    index_year: int,
    index_quarter: int,
    qualifying_forms: frozenset[str],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    in_records = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r\n")
        if not in_records:
            if line.startswith("---"):
                in_records = True
            continue
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) != 5:
            continue
        cik, company_name, form, filed, filename = (part.strip() for part in parts)
        form = form.upper()
        if form not in qualifying_forms:
            continue
        accession = normalize_accession(filename)
        rows.append(
            {
                "accession": accession,
                "cik10_master": normalize_cik(cik),
                "company_name_master": company_name,
                "form_master": form,
                "filed_master": filed,
                "archive_filename": filename,
                "index_year": index_year,
                "index_quarter": index_quarter,
            }
        )
    return pd.DataFrame(rows)


def read_fsds_sub(path: Path, *, source_year: int, source_quarter: int) -> pd.DataFrame:
    frame = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    required = {
        "adsh",
        "cik",
        "name",
        "sic",
        "afs",
        "fye",
        "form",
        "period",
        "fy",
        "fp",
        "filed",
        "accepted",
        "prevrpt",
        "instance",
        "nciks",
        "aciks",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing SUB columns in {path}: {sorted(missing)}")
    frame = frame[frame["form"].str.upper().eq("10-K")].copy()
    frame["accession"] = frame["adsh"].map(normalize_accession)
    frame["cik10_sub"] = frame["cik"].map(normalize_cik)
    frame["fsds_source_year"] = source_year
    frame["fsds_source_quarter"] = source_quarter
    columns = [
        "accession",
        "cik10_sub",
        "name",
        "sic",
        "countryba",
        "stprba",
        "countryinc",
        "stprinc",
        "former",
        "changed",
        "afs",
        "wksi",
        "fye",
        "form",
        "period",
        "fy",
        "fp",
        "filed",
        "accepted",
        "prevrpt",
        "instance",
        "nciks",
        "aciks",
        "fsds_source_year",
        "fsds_source_quarter",
    ]
    return frame[[column for column in columns if column in frame.columns]]


HEADER_PATTERNS = {
    "accession_header": (
        r"<ACCESSION-NUMBER>\s*([^\s<]+)",
        r"ACCESSION NUMBER:\s*([^\s<]+)",
    ),
    "accepted_header": (
        r"<ACCEPTANCE-DATETIME>\s*(\d{14})",
        r"ACCEPTANCE-DATETIME:\s*(\d{14})",
    ),
    "period_header": (
        r"<PERIOD>\s*(\d{8})",
        r"CONFORMED PERIOD OF REPORT:\s*(\d{8})",
    ),
    "filed_header": (
        r"<FILING-DATE>\s*(\d{8})",
        r"FILED AS OF DATE:\s*(\d{8})",
    ),
    "company_name_header": (
        r"<CONFORMED-NAME>\s*([^\r\n<]+)",
        r"COMPANY CONFORMED NAME:\s*([^\r\n<]+)",
    ),
    "sic_header": (
        r"<ASSIGNED-SIC>\s*(\d{3,4})",
        r"STANDARD INDUSTRIAL CLASSIFICATION:[^\r\n\[]*\[(\d{3,4})\]",
    ),
    "fye_header": (
        r"<FISCAL-YEAR-END>\s*(\d{4})",
        r"FISCAL YEAR END:\s*(\d{4})",
    ),
}


def parse_submission_header(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for field, patterns in HEADER_PATTERNS.items():
        value = ""
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                break
        result[field] = value
    if result["accession_header"]:
        result["accession_header"] = normalize_accession(result["accession_header"])
    if result["accepted_header"]:
        value = result["accepted_header"]
        result["accepted_header"] = (
            f"{value[:4]}-{value[4:6]}-{value[6:8]} "
            f"{value[8:10]}:{value[10:12]}:{value[12:14]}"
        )
    for field in ("period_header", "filed_header"):
        value = result[field]
        if value:
            result[field] = f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return result


def parse_submission_header_registrants(text: str) -> list[dict[str, str]]:
    """Parse filer-specific metadata from one SEC submission header.

    A joint filing has one accession but multiple ``FILER`` blocks.  SIC is a
    registrant attribute, so it must be paired with the CIK inside that block
    rather than copied from the primary XBRL SUB row.
    """

    common = parse_submission_header(text)
    header_end = re.search(r"</SEC-HEADER>", text, flags=re.IGNORECASE)
    header = text[: header_end.end()] if header_end else text
    filer_start = re.compile(r"(?im)^(?:\s*<FILER>\s*|\s*FILER:\s*)$")
    other_party_start = re.compile(
        r"(?im)^(?:\s*<(?:FILER|REPORTING-OWNER|ISSUER)>\s*|"
        r"\s*(?:FILER|REPORTING OWNER|ISSUER):\s*)$"
    )
    starts = list(filer_start.finditer(header))
    rows: list[dict[str, str]] = []
    for start in starts:
        following = other_party_start.search(header, start.end())
        block = header[start.start() : following.start() if following else len(header)]
        cik_match = re.search(
            r"(?:<CIK>\s*|CENTRAL INDEX KEY:\s*)(\d{1,10})",
            block,
            flags=re.IGNORECASE,
        )
        if not cik_match:
            continue
        row = dict(common)
        row["cik10_header"] = normalize_cik(cik_match.group(1))
        for field, patterns in {
            "company_name_header": HEADER_PATTERNS["company_name_header"],
            "sic_header": HEADER_PATTERNS["sic_header"],
            "fye_header": HEADER_PATTERNS["fye_header"],
        }.items():
            value = ""
            for pattern in patterns:
                match = re.search(pattern, block, flags=re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    break
            row[field] = value
        rows.append(row)

    if not rows:
        cik_match = re.search(
            r"(?:<CIK>\s*|CENTRAL INDEX KEY:\s*)(\d{1,10})",
            header,
            flags=re.IGNORECASE,
        )
        if cik_match:
            row = dict(common)
            row["cik10_header"] = normalize_cik(cik_match.group(1))
            rows.append(row)

    deduplicated: dict[str, dict[str, str]] = {}
    for row in rows:
        cik10 = row["cik10_header"]
        if cik10 not in deduplicated:
            deduplicated[cik10] = row
    return list(deduplicated.values())


def in_range(value: int, bounds: list[int] | tuple[int, int]) -> bool:
    return int(bounds[0]) <= value <= int(bounds[1])


def classify_historical_sic(
    sic_value: object,
    sic_description: object,
    policy: dict[str, Any],
) -> dict[str, object]:
    sic = parse_sic(sic_value)
    if sic is None:
        return {
            "membership_status": "ambiguous",
            "research_sector": "Unknown",
            "membership_reason": "missing_or_invalid_historical_sic",
            "classification_rule": "sic_missing_or_invalid",
        }
    sector_policy = policy["sector_policy"]
    for start, end, reason in sector_policy["excluded_ranges"]:
        if start <= sic <= end:
            return {
                "membership_status": "excluded",
                "research_sector": (
                    "Excluded_Financials_Insurance_RealEstate"
                    if start == 6000
                    else "Excluded_Utilities"
                ),
                "membership_reason": reason,
                "classification_rule": f"sic_{start}_{end}",
            }
    description = clean_text(sic_description).lower()
    technology = any(
        start <= sic <= end for start, end in sector_policy["technology_ranges"]
    ) or any(
        keyword in description
        for keyword in sector_policy["technology_description_keywords"]
    )
    if technology:
        return {
            "membership_status": "eligible",
            "research_sector": "Technology",
            "membership_reason": "",
            "classification_rule": "historical_technology_sic_or_description",
        }
    if in_range(sic, sector_policy["retail_range"]):
        return {
            "membership_status": "eligible",
            "research_sector": "Retail",
            "membership_reason": "",
            "classification_rule": "historical_sic_5200_5999",
        }
    if in_range(sic, sector_policy["industrials_manufacturing_range"]):
        return {
            "membership_status": "eligible",
            "research_sector": "Industrials_Manufacturing",
            "membership_reason": "",
            "classification_rule": "historical_sic_2000_3999_non_technology",
        }
    for start, end, rule in sector_policy["extended_candidate_ranges"]:
        if start <= sic <= end:
            return {
                "membership_status": "eligible",
                "research_sector": "Extended_Candidate",
                "membership_reason": "",
                "classification_rule": rule,
            }
    return {
        "membership_status": "excluded",
        "research_sector": "Other_Out_Of_Scope",
        "membership_reason": "out_of_scope_sector",
        "classification_rule": "historical_sic_not_in_research_scope",
    }


def resolve_feature_year(
    row: pd.Series, scope: UniverseScope
) -> tuple[int | None, str, str, int | None]:
    fp = clean_text(row.get("fp", "")).upper()
    fy_text = clean_text(row.get("fy", ""))
    if fy_text and fp == "FY":
        try:
            year = int(float(fy_text))
        except ValueError:
            year = -1
        if scope.feature_year_start <= year <= scope.feature_year_end:
            return (
                year,
                "fsds_document_fiscal_year_focus",
                "resolved_in_scope",
                year,
            )
        if 1900 <= year <= 2100:
            return (
                None,
                "fsds_document_fiscal_year_focus",
                "resolved_out_of_scope",
                year,
            )
    period = clean_text(row.get("period", "")) or clean_text(
        row.get("period_header", "")
    )
    match = re.match(r"(\d{4})[-/]?\d{2}[-/]?\d{2}$", period)
    if match:
        year = int(match.group(1))
        if scope.feature_year_start <= year <= scope.feature_year_end:
            return (
                year,
                "filing_period_end_year_fallback",
                "resolved_in_scope",
                year,
            )
        return (
            None,
            "filing_period_end_year_fallback",
            "resolved_out_of_scope",
            year,
        )
    return None, "unavailable", "unresolved", None


def choose_historical_sic(row: pd.Series) -> tuple[int | None, str, str]:
    master_cik = normalize_cik(row.get("cik10_master"))
    sub_cik = normalize_cik(row.get("cik10_sub"))
    sub_sic = parse_sic(row.get("sic")) if master_cik == sub_cik else None
    header_sic = parse_sic(row.get("sic_header"))
    if sub_sic is not None and header_sic is not None and sub_sic != header_sic:
        return None, "conflict", f"fsds={sub_sic};header={header_sic}"
    if sub_sic is not None:
        return sub_sic, "fsds_sub_same_accession", ""
    if header_sic is not None:
        return header_sic, "submission_header_same_accession", ""
    return None, "unavailable", ""


def build_historical_anchors(
    master: pd.DataFrame,
    sub: pd.DataFrame,
    headers: pd.DataFrame,
    sic_descriptions: dict[int, str],
    policy: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    scope = parse_scope(policy)
    master = master.drop_duplicates(
        subset=["accession", "cik10_master"], keep="first"
    ).copy()
    master["accession_registrant_count"] = master.groupby("accession")[
        "cik10_master"
    ].transform("nunique")
    sub = sub.sort_values(
        ["accession", "fsds_source_year", "fsds_source_quarter"]
    ).drop_duplicates(subset=["accession"], keep="last")
    combined = master.merge(sub, on="accession", how="left", validate="many_to_one")
    if headers.empty:
        headers = pd.DataFrame(columns=["accession", "cik10_header"])
    combined = combined.merge(
        headers,
        left_on=["accession", "cik10_master"],
        right_on=["accession", "cik10_header"],
        how="left",
        validate="one_to_one",
    )

    candidate_rows: list[dict[str, object]] = []
    for _, row in combined.iterrows():
        cik_master = normalize_cik(row.get("cik10_master"))
        cik_sub = normalize_cik(row.get("cik10_sub"))
        cik_header = normalize_cik(row.get("cik10_header"))
        primary_xbrl_registrant = bool(cik_master and cik_master == cik_sub)
        header_conflict = bool(cik_header and cik_header != cik_master)
        cik10 = cik_master or cik_header or cik_sub
        (
            feature_year,
            feature_year_source,
            feature_year_resolution_status,
            observed_fiscal_year,
        ) = resolve_feature_year(row, scope)
        historical_sic, sic_source, sic_conflict = choose_historical_sic(row)
        sic_description = sic_descriptions.get(historical_sic or -1, "")
        classification = classify_historical_sic(
            historical_sic, sic_description, policy
        )
        reasons: list[str] = []
        if header_conflict:
            reasons.append("cik_conflict_master_vs_header")
        if not cik10:
            reasons.append("missing_cik")
        if feature_year is None:
            reasons.append(
                "feature_year_out_of_scope"
                if feature_year_resolution_status == "resolved_out_of_scope"
                else "unresolved_feature_year"
            )
        if sic_source == "conflict":
            reasons.append("historical_sic_conflict")
        elif historical_sic is None:
            if cik_header:
                reasons.append("historical_sic_missing_in_registrant_header")
            elif primary_xbrl_registrant:
                reasons.append("historical_sic_unavailable_same_accession")
            else:
                reasons.append("registrant_header_unavailable_or_unmatched")
        membership_status = str(classification["membership_status"])
        membership_reason = str(classification["membership_reason"])
        if reasons:
            membership_status = "ambiguous"
            membership_reason = ";".join(reasons)
        accepted_at = normalize_accepted_at(
            clean_text(row.get("accepted", ""))
            or clean_text(row.get("accepted_header", ""))
        )
        filed = normalize_date(
            clean_text(row.get("filed", ""))
            or clean_text(row.get("filed_header", ""))
            or clean_text(row.get("filed_master", ""))
        )
        period = normalize_date(
            clean_text(row.get("period", ""))
            or clean_text(row.get("period_header", ""))
        )
        candidate_rows.append(
            {
                "accession": row["accession"],
                "cik10": cik10,
                "feature_year": feature_year,
                "feature_year_source": feature_year_source,
                "feature_year_resolution_status": feature_year_resolution_status,
                "observed_fiscal_year": observed_fiscal_year,
                "company_name_historical": (
                    (
                        clean_text(row.get("name", ""))
                        if primary_xbrl_registrant
                        else ""
                    )
                    or clean_text(row.get("company_name_header", ""))
                    or clean_text(row.get("company_name_master", ""))
                ),
                "registrant_role": (
                    "primary_xbrl_registrant"
                    if primary_xbrl_registrant
                    else "co_registrant_or_non_xbrl_registrant"
                ),
                "accession_registrant_count": int(
                    row.get("accession_registrant_count", 1)
                ),
                "joint_filing_flag": int(
                    row.get("accession_registrant_count", 1)
                )
                > 1,
                "historical_sic": historical_sic,
                "historical_sic_description": sic_description,
                "historical_sic_source": sic_source,
                "historical_sic_conflict_details": sic_conflict,
                "same_accession_header_registrant_matched": bool(cik_header),
                "submission_header_path": clean_text(
                    row.get("submission_header_path", "")
                ),
                "research_sector": classification["research_sector"],
                "membership_status": membership_status,
                "membership_reason": membership_reason,
                "classification_rule": classification["classification_rule"],
                "form": clean_text(row.get("form_master", "")) or "10-K",
                "filed": filed,
                "accepted_at": accepted_at,
                "membership_available_at": accepted_at or filed,
                "membership_available_at_precision": (
                    "timestamp" if accepted_at else "date"
                ),
                "period_end": period,
                "document_fiscal_year_focus": clean_text(row.get("fy", "")),
                "document_fiscal_period_focus": clean_text(row.get("fp", "")),
                "fiscal_year_end": clean_text(row.get("fye", ""))
                or clean_text(row.get("fye_header", "")),
                "filer_status": clean_text(row.get("afs", ""))
                if primary_xbrl_registrant
                else "",
                "well_known_seasoned_issuer": clean_text(row.get("wksi", ""))
                if primary_xbrl_registrant
                else "",
                "country_business_address": clean_text(row.get("countryba", ""))
                if primary_xbrl_registrant
                else "",
                "state_business_address": clean_text(row.get("stprba", ""))
                if primary_xbrl_registrant
                else "",
                "country_incorporation": clean_text(row.get("countryinc", ""))
                if primary_xbrl_registrant
                else "",
                "state_incorporation": clean_text(row.get("stprinc", ""))
                if primary_xbrl_registrant
                else "",
                "former_name": clean_text(row.get("former", ""))
                if primary_xbrl_registrant
                else "",
                "former_name_changed": clean_text(row.get("changed", ""))
                if primary_xbrl_registrant
                else "",
                "xbrl_instance": clean_text(row.get("instance", "")),
                "xbrl_submission_available": bool(
                    clean_text(row.get("instance", ""))
                ),
                "co_registrant_count": clean_text(row.get("nciks", "")),
                "additional_ciks": clean_text(row.get("aciks", "")),
                "archive_filename": clean_text(row.get("archive_filename", "")),
                "index_year": row.get("index_year"),
                "index_quarter": row.get("index_quarter"),
                "fsds_source_year": row.get("fsds_source_year", ""),
                "fsds_source_quarter": row.get("fsds_source_quarter", ""),
                "x_t_status": "not_built",
                "target_status": "not_computed",
            }
        )
    candidates = pd.DataFrame(candidate_rows)
    resolved = candidates[candidates["feature_year"].notna()].copy()
    resolved["feature_year"] = resolved["feature_year"].astype(int)
    resolved["_accepted_sort"] = resolved["accepted_at"].replace("", "9999")
    resolved["_filed_sort"] = resolved["filed"].replace("", "9999")
    resolved = resolved.sort_values(
        ["cik10", "feature_year", "_accepted_sort", "_filed_sort", "accession"]
    )
    resolved["anchor_candidate_count"] = resolved.groupby(
        ["cik10", "feature_year"]
    )["accession"].transform("size")
    resolved["anchor_rank"] = (
        resolved.groupby(["cik10", "feature_year"]).cumcount() + 1
    )
    anchors = resolved[resolved["anchor_rank"].eq(1)].drop(
        columns=["_accepted_sort", "_filed_sort"]
    )
    unresolved = candidates[candidates["feature_year"].isna()].copy()
    return anchors.reset_index(drop=True), unresolved.reset_index(drop=True)


def load_sic_description_map(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not {"sic", "sic_description"}.issubset(frame.columns):
        return {}
    result: dict[int, str] = {}
    for _, row in frame.iterrows():
        sic = parse_sic(row["sic"])
        description = str(row["sic_description"]).strip()
        if sic is not None and description and sic not in result:
            result[sic] = description
    return result


def load_official_sic_description_map(path: Path) -> dict[int, str]:
    """Parse the version-cached SEC SIC list without optional HTML packages."""

    if not path.exists():
        return {}
    source = path.read_text(encoding="utf-8", errors="replace")
    result: dict[int, str] = {}
    for table_row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", source, flags=re.I | re.S):
        cells = re.findall(
            r"<t[dh]\b[^>]*>(.*?)</t[dh]>", table_row, flags=re.I | re.S
        )
        if len(cells) < 3:
            continue
        clean_cells = [
            html.unescape(re.sub(r"<[^>]+>", " ", cell)) for cell in cells
        ]
        clean_cells = [re.sub(r"\s+", " ", cell).strip() for cell in clean_cells]
        sic = parse_sic(clean_cells[0])
        if sic is not None and clean_cells[2]:
            result[sic] = clean_cells[2]
    return result


def add_comparison_statuses(
    universe: pd.DataFrame,
    old_universe_path: Path,
    current_ticker_path: Path,
    frozen_target_path: Path,
) -> pd.DataFrame:
    result = universe.copy()
    old_ciks: set[str] = set()
    if old_universe_path.exists():
        old = pd.read_csv(old_universe_path, dtype={"cik10": str})
        old_ciks = set(old["cik10"].map(normalize_cik))
    current_ticker_ciks: set[str] = set()
    if current_ticker_path.exists():
        tickers = pd.read_csv(current_ticker_path, dtype={"cik10": str})
        current_ticker_ciks = set(tickers["cik10"].map(normalize_cik))
    result["in_old_current_snapshot_universe"] = result["cik10"].isin(old_ciks)
    result["in_current_ticker_snapshot"] = result["cik10"].isin(
        current_ticker_ciks
    )
    result["recovered_vs_old_universe"] = (
        result["membership_status"].eq("eligible")
        & ~result["in_old_current_snapshot_universe"]
    )
    result["later_inactive_or_unmapped_proxy"] = (
        result["membership_status"].eq("eligible")
        & ~result["in_current_ticker_snapshot"]
    )
    if frozen_target_path.exists():
        target = pd.read_csv(
            frozen_target_path,
            usecols=["cik10", "feature_year", "target_status"],
            dtype={"cik10": str},
            low_memory=False,
        )
        target["cik10"] = target["cik10"].map(normalize_cik)
        target = target.drop_duplicates(["cik10", "feature_year"], keep="last")
        result = result.drop(columns=["target_status"]).merge(
            target,
            on=["cik10", "feature_year"],
            how="left",
            validate="one_to_one",
        )
        result["target_status"] = result["target_status"].fillna("not_computed")
    result.insert(
        0,
        "research_universe_company_year_id",
        result["cik10"] + "-" + result["feature_year"].astype(str),
    )
    return result


def utc_now_iso() -> str:
    return datetime.now().astimezone().isoformat()

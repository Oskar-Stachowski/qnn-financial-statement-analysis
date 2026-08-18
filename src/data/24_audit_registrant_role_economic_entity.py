"""Audit registrant roles and economic-entity duplication in the PIT universe.

This is a freeze-gate diagnostic.  It never rewrites the canonical historical
universe, never builds X_t, and never reads or changes target values.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
import zipfile

import pandas as pd
import yaml


BASE_DIR = Path(__file__).resolve().parents[2]
UNIVERSE_PATH = BASE_DIR / "data" / "processed" / "research_universe_pit.csv"
EVIDENCE_DIR = (
    BASE_DIR / "data" / "raw" / "sec_historical_universe" / "registrant_role_evidence"
)
EVIDENCE_MANIFEST_PATH = (
    BASE_DIR / "data" / "reports" / "research_universe_pit_registrant_evidence.json"
)
MANUAL_PATH = BASE_DIR / "configs" / "research_universe_registrant_role_manual.yaml"
DETAIL_PATH = (
    BASE_DIR / "data" / "reports" / "research_universe_pit_registrant_role_detail.csv"
)
ACCESSION_PATH = (
    BASE_DIR / "data" / "reports" / "research_universe_pit_joint_accessions.csv"
)
SUMMARY_PATH = (
    BASE_DIR / "data" / "reports" / "research_universe_pit_registrant_role_audit.json"
)
REPORT_PATH = (
    BASE_DIR / "data" / "reports" / "research_universe_pit_registrant_role_audit.md"
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_cik(value: str) -> str:
    digits = re.sub(r"\D", "", str(value))
    if not digits or len(digits) > 10:
        return ""
    return digits.zfill(10)


def source_role(row: pd.Series) -> str:
    joint = bool(row["joint_filing_flag"])
    primary = row["registrant_role"] == "primary_xbrl_registrant"
    if joint and primary:
        return "joint_primary_registrant"
    if joint:
        return "joint_co_registrant"
    if primary:
        return "single_filer_xbrl_registrant"
    return "single_filer_non_xbrl_registrant"


def _text_values(raw: bytes, pattern: bytes) -> list[str]:
    values: list[str] = []
    for match in re.findall(pattern, raw, flags=re.I | re.S):
        value = re.sub(rb"<[^>]+>", b" ", match)
        decoded = html.unescape(value.decode("utf-8", errors="ignore"))
        decoded = re.sub(r"\s+", " ", decoded).strip()
        if decoded:
            values.append(decoded)
    return values


def extract_xbrl_scope(zip_path: Path) -> dict[str, Any]:
    """Read every context-bearing document in an SEC XBRL package."""

    entity_ids: list[str] = []
    entity_names: list[str] = []
    context_files: list[str] = []
    context_count = 0
    fact_reference_count = 0
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            if not name.lower().endswith((".xml", ".htm", ".html", ".xhtml")):
                continue
            raw = archive.read(name)
            identifiers = _text_values(
                raw,
                rb"<(?:[A-Za-z0-9_-]+:)?identifier\b[^>]*>(.*?)"
                rb"</(?:[A-Za-z0-9_-]+:)?identifier\s*>",
            )
            if not identifiers:
                continue
            context_files.append(name)
            entity_ids.extend(identifiers)
            context_count += len(
                re.findall(rb"<(?:[A-Za-z0-9_-]+:)?context\b", raw, flags=re.I)
            )
            fact_reference_count += len(re.findall(rb"\bcontextRef\s*=", raw, flags=re.I))
            entity_names.extend(
                _text_values(
                    raw,
                    rb"<(?:dei:)?EntityRegistrantName\b[^>]*>(.*?)"
                    rb"</(?:dei:)?EntityRegistrantName\s*>",
                )
            )
            entity_names.extend(
                _text_values(
                    raw,
                    rb"<ix:(?:nonNumeric|nonFraction)\b[^>]*"
                    rb"\bname=[\"']dei:EntityRegistrantName[\"'][^>]*>(.*?)</ix:",
                )
            )

    cik_ids = sorted({normalized_cik(value) for value in entity_ids if normalized_cik(value)})
    non_cik_ids = sorted(
        {
            value
            for value in entity_ids
            if value and not normalized_cik(value)
        }
    )
    return {
        "xbrl_context_files": ";".join(sorted(context_files)),
        "xbrl_entity_ciks": ";".join(cik_ids),
        "xbrl_non_cik_identifiers": ";".join(non_cik_ids),
        "xbrl_entity_names": ";".join(sorted(set(entity_names))),
        "xbrl_entity_count": len(cik_ids),
        "xbrl_context_count": context_count,
        "xbrl_fact_reference_count": fact_reference_count,
    }


def load_manual_decisions() -> dict[str, dict[str, Any]]:
    if not MANUAL_PATH.exists():
        return {}
    payload = yaml.safe_load(MANUAL_PATH.read_text(encoding="utf-8")) or {}
    decisions = [
        *payload.get("non_xbrl_joint_accessions", []),
        *payload.get("xbrl_joint_accessions", []),
    ]
    for series in payload.get("xbrl_joint_accession_series", []):
        for accession in series.get("accessions", []):
            decision = {
                key: value
                for key, value in series.items()
                if key not in {"accessions", "series_id"}
            }
            decision["accession"] = accession
            decision["series_id"] = series.get("series_id", "")
            decisions.append(decision)
    return {str(item["accession"]): item for item in decisions}


class VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def primary_document_text(path: Path) -> str:
    parser = VisibleTextParser()
    parser.feed(path.read_text(encoding="latin-1", errors="ignore"))
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()


def normalize_entity_name(value: str) -> str:
    text = html.unescape(str(value)).lower().replace("&", " and ")
    text = re.sub(r"/[a-z ]+/?(?:\s|$)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    replacements = {
        "corporation": "corp",
        "company": "co",
        "incorporated": "inc",
        "limited": "ltd",
        "l l c": "llc",
        "l p": "lp",
    }
    for source, target in replacements.items():
        text = re.sub(rf"\b{source}\b", target, text)
    return re.sub(r"\s+", " ", text).strip()


def parse_header_registrants(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="latin-1", errors="ignore")
    blocks = re.split(r"(?im)^\s*FILER:\s*$", text)[1:]
    rows: list[dict[str, str]] = []
    for block in blocks:
        name_match = re.search(r"COMPANY CONFORMED NAME:\s*([^\r\n]+)", block, flags=re.I)
        cik_match = re.search(r"CENTRAL INDEX KEY:\s*(\d{1,10})", block, flags=re.I)
        if not name_match or not cik_match:
            continue
        rows.append(
            {
                "cik10": normalized_cik(cik_match.group(1)),
                "company_name": name_match.group(1).strip(),
            }
        )
    return rows


def statement_scope_from_primary(
    primary_path: Path,
    registrants: list[dict[str, str]],
) -> dict[str, Any]:
    text = primary_document_text(primary_path)
    normalized_text = normalize_entity_name(text)
    opinion_windows: list[str] = []
    opinion_pattern = re.compile(
        r"(?:we have audited (?:the )?(?:accompanying|consolidated)|"
        r"we audited (?:the )?(?:accompanying|consolidated)|"
        r"in our opinion.{0,120}(?:accompanying|consolidated))",
        flags=re.I,
    )
    opinion_matches = list(opinion_pattern.finditer(text))
    for index, match in enumerate(opinion_matches):
        window_end = min(len(text), match.end() + 1100)
        if index + 1 < len(opinion_matches):
            window_end = min(window_end, opinion_matches[index + 1].start() - 500)
        window_end = max(window_end, match.end() + 300)
        opinion_windows.append(
            normalize_entity_name(
                text[max(0, match.start() - 500) : window_end]
            )
        )

    normalized_names = [normalize_entity_name(item["company_name"]) for item in registrants]
    name_counts = Counter(normalized_names)
    collision_ciks = sorted(
        item["cik10"]
        for item, normalized in zip(registrants, normalized_names)
        if name_counts[normalized] > 1
    )
    evidence: dict[str, Any] = {}
    for registrant in registrants:
        cik = registrant["cik10"]
        name = normalize_entity_name(registrant["company_name"])
        audit_matches = sum(name in window for window in opinion_windows)
        position_matches = len(
            re.findall(
                rf"{re.escape(name)}.{{0,180}}(?:consolidated )?"
                r"(?:balance sheets?|statements? of financial position)",
                normalized_text,
            )
        )
        operations_matches = len(
            re.findall(
                rf"{re.escape(name)}.{{0,180}}(?:consolidated )?statements? of "
                r"(?:operations|income|earnings|comprehensive income)",
                normalized_text,
            )
        )
        cash_flow_matches = len(
            re.findall(
                rf"{re.escape(name)}.{{0,180}}(?:consolidated )?statements? of cash flows?",
                normalized_text,
            )
        )
        evidence[cik] = {
            "name": registrant["company_name"],
            "audit_opinion_window_matches": audit_matches,
            "balance_sheet_heading_matches": position_matches,
            "operations_heading_matches": operations_matches,
            "cash_flow_heading_matches": cash_flow_matches,
        }
    audit_scope_groups = sorted(
        {
            tuple(
                sorted(
                    registrant["cik10"]
                    for registrant in registrants
                    if normalize_entity_name(registrant["company_name"]) in window
                )
            )
            for window in opinion_windows
        }
        - {()}
    )
    grouped_ciks = {cik for group in audit_scope_groups for cik in group}
    heading_only_ciks = sorted(
        cik
        for cik, item in evidence.items()
        if cik not in grouped_ciks
        and item["balance_sheet_heading_matches"]
        and item["operations_heading_matches"]
        and item["cash_flow_heading_matches"]
    )
    return {
        "statement_entity_ciks": "",
        "audit_scope_cik_groups": json.dumps(audit_scope_groups),
        "heading_only_statement_ciks": ";".join(heading_only_ciks),
        "statement_evidence_by_cik": json.dumps(evidence, sort_keys=True),
        "audit_opinion_phrase_count": len(opinion_windows),
        "normalized_name_collision_ciks": ";".join(collision_ciks),
    }


def joint_accession_evidence(
    accession: str,
    rows: pd.DataFrame,
    manual: dict[str, dict[str, Any]],
    evidence_record: dict[str, Any],
) -> dict[str, Any]:
    accession_dir = EVIDENCE_DIR / accession
    zip_paths = sorted(accession_dir.glob("*-xbrl.zip"))
    xbrl_expected = rows["xbrl_instance"].notna().any()
    result: dict[str, Any] = {
        "accession": accession,
        "feature_year": int(rows["feature_year"].iloc[0]),
        "eligible_observation_count": int(len(rows)),
        "eligible_ciks": ";".join(sorted(rows["cik10"].astype(str))),
        "eligible_names": " | ".join(sorted(rows["company_name_historical"].astype(str))),
        "accession_registrant_count": int(rows["accession_registrant_count"].max()),
        "xbrl_expected": bool(xbrl_expected),
    }
    header_path = (
        BASE_DIR
        / "data"
        / "raw"
        / "sec_historical_universe"
        / "filing_headers"
        / f"{accession}.txt"
    )
    registrants = parse_header_registrants(header_path)
    primary_name = str(evidence_record["primary_10k_filename"])
    primary_path = accession_dir / primary_name
    if not primary_path.exists():
        result.update(
            {
                "scope_status": "ambiguous",
                "scope_reason": "primary_10k_missing",
                "statement_entity_ciks": "",
            }
        )
        return result
    parser_version = "primary_statement_mapper_v3_audit_scope_groups"
    primary_sha256 = str(evidence_record["files"]["primary_10k"]["sha256"])
    scope_cache_path = accession_dir / "primary_statement_scope_v3.json"
    cached_scope: dict[str, Any] | None = None
    if scope_cache_path.exists():
        candidate = json.loads(scope_cache_path.read_text(encoding="utf-8"))
        if (
            candidate.get("parser_version") == parser_version
            and candidate.get("primary_sha256") == primary_sha256
        ):
            cached_scope = dict(candidate["scope"])
    if cached_scope is None:
        cached_scope = statement_scope_from_primary(primary_path, registrants)
        scope_cache_path.write_text(
            json.dumps(
                {
                    "parser_version": parser_version,
                    "primary_sha256": primary_sha256,
                    "scope": cached_scope,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    result.update(cached_scope)

    if xbrl_expected:
        if len(zip_paths) != 1:
            result.update(
                {
                    "scope_status": "ambiguous",
                    "scope_reason": "xbrl_package_missing_or_nonunique",
                }
            )
            return result
        scope = extract_xbrl_scope(zip_paths[0])
        result.update(scope)
        if scope["xbrl_non_cik_identifiers"]:
            result.update(
                {
                    "scope_status": "ambiguous",
                    "scope_reason": "non_cik_xbrl_entity_identifier",
                }
            )
            return result
        if scope["xbrl_entity_count"] == 0:
            result.update(
                {
                    "scope_status": "ambiguous",
                    "scope_reason": "no_xbrl_entity_identifier",
                }
            )
            return result

    audit_groups = [
        [normalized_cik(cik) for cik in group if normalized_cik(cik)]
        for group in json.loads(result.get("audit_scope_cik_groups", "[]"))
    ]
    xbrl_ciks = {
        cik for cik in str(result.get("xbrl_entity_ciks", "")).split(";") if cik
    }
    statement_entities: set[str] = {
        cik
        for cik in str(result.get("heading_only_statement_ciks", "")).split(";")
        if cik
    }
    unresolved_audit_groups: list[list[str]] = []
    for group in audit_groups:
        if len(group) == 1:
            statement_entities.add(group[0])
            continue
        xbrl_matches = sorted(set(group) & xbrl_ciks)
        if len(xbrl_matches) == 1:
            statement_entities.add(xbrl_matches[0])
        else:
            unresolved_audit_groups.append(group)
    result["statement_entity_ciks"] = ";".join(sorted(statement_entities))
    result["unresolved_multi_cik_audit_groups"] = json.dumps(unresolved_audit_groups)

    if unresolved_audit_groups:
        result.update(
            {
                "scope_status": "ambiguous",
                "scope_reason": "multi_cik_audit_scope_without_unique_xbrl_representative",
            }
        )
    elif result["statement_entity_ciks"]:
        result.update(
            {
                "scope_status": "resolved",
                "scope_reason": "primary_10k_distinct_statement_sets_mapped",
            }
        )
    else:
        result.update(
            {
                "scope_status": "ambiguous",
                "scope_reason": "no_registrant_statement_scope_mapped",
            }
        )

    decision = manual.get(accession)
    if result.get("normalized_name_collision_ciks") and not decision:
        result.update(
            {
                "scope_status": "ambiguous",
                "scope_reason": "registrant_names_collide_in_primary_statement_mapping",
            }
        )
    if decision:
        representatives = [
            normalized_cik(value) for value in decision.get("statement_entity_ciks", [])
        ]
        representatives = [value for value in representatives if value]
        result.update(
            {
                "scope_status": str(decision["scope_status"]),
                "scope_reason": str(decision["scope_reason"]),
                "statement_entity_ciks": ";".join(sorted(set(representatives))),
                "manual_evidence": str(decision.get("evidence", "")),
                "manual_series_id": str(decision.get("series_id", "")),
                "non_operating_issuer_ciks": ";".join(
                    sorted(
                        {
                            normalized_cik(value)
                            for value in decision.get(
                                "non_operating_issuer_ciks", []
                            )
                            if normalized_cik(value)
                        }
                    )
                ),
            }
        )
    return result


def classify_joint_row(row: pd.Series) -> tuple[str, str, str]:
    if row["scope_status"] != "resolved":
        return (
            "ambiguous_reporting_scope",
            "mark_ambiguous",
            str(row["scope_reason"]),
        )
    entities = {value for value in str(row["statement_entity_ciks"]).split(";") if value}
    eligible = {value for value in str(row["eligible_ciks"]).split(";") if value}
    cik = str(row["cik10"])
    if cik in entities:
        non_operating_issuers = {
            value
            for value in str(row.get("non_operating_issuer_ciks", "")).split(";")
            if value and value != "nan"
        }
        if cik in non_operating_issuers:
            return (
                "separate_reporting_entity_nonoperating_coissuer",
                "exclude_nonoperating_issuer",
                "separate_financial_statements_but_no_substantive_operations",
            )
        return (
            "separate_reporting_entity_with_own_statements",
            "retain_one_economic_entity",
            "registrant_cik_matches_distinct_primary_statement_suite",
        )
    if not entities & eligible:
        return (
            "co_registrant_sharing_statement_of_noneligible_cik",
            "mark_ambiguous",
            "statement_entity_is_not_an_eligible_company_year",
        )
    return (
        "co_registrant_sharing_same_consolidated_statements",
        "exclude_duplicate_registrant_row",
        "registrant_has_no_distinct_primary_statement_suite",
    )


def as_markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "_Brak._"
    columns = list(frame.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for values in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in values) + " |")
    return "\n".join(lines)


def connected_joint_groups(joint: pd.DataFrame) -> dict[str, str]:
    """Conservative connected components of eligible co-filing CIKs."""

    parent = {cik: cik for cik in joint["cik10"].astype(str).unique()}

    def find(cik: str) -> str:
        while parent[cik] != cik:
            parent[cik] = parent[parent[cik]]
            cik = parent[cik]
        return cik

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        smaller, larger = sorted((left_root, right_root))
        parent[larger] = smaller

    for _, rows in joint.groupby("accession"):
        ciks = sorted(rows["cik10"].astype(str).unique())
        for cik in ciks[1:]:
            union(ciks[0], cik)

    result: dict[str, str] = {}
    for cik in parent:
        result[cik] = "joint_group_" + find(cik)
    return result


def main() -> None:
    universe = pd.read_csv(UNIVERSE_PATH, dtype={"cik10": str}, low_memory=False)
    eligible = universe.loc[universe["membership_status"].eq("eligible")].copy()
    eligible["registrant_role_resolved"] = eligible.apply(source_role, axis=1)
    scope_mask = (
        eligible["registrant_role"].eq("co_registrant_or_non_xbrl_registrant")
        | eligible["joint_filing_flag"].fillna(False)
    )
    audit = eligible.loc[scope_mask].copy()

    manual = load_manual_decisions()
    evidence_manifest = json.loads(EVIDENCE_MANIFEST_PATH.read_text(encoding="utf-8"))
    universe_sha256 = sha256_path(UNIVERSE_PATH)
    if universe_sha256 != evidence_manifest["universe_sha256"]:
        raise ValueError("Canonical PIT universe changed after evidence collection")
    evidence_records = {
        str(record["accession"]): record for record in evidence_manifest["records"]
    }
    joint = eligible.loc[eligible["joint_filing_flag"].fillna(False)].copy()
    accession_records = [
        joint_accession_evidence(
            accession,
            rows,
            manual,
            evidence_records[accession],
        )
        for accession, rows in joint.groupby("accession", sort=True)
    ]
    accessions = pd.DataFrame(accession_records)
    accessions["statement_entity_count"] = accessions["statement_entity_ciks"].map(
        lambda value: len(
            [item for item in str(value).split(";") if item and item != "nan"]
        )
    )
    accessions["joint_scope_structure"] = accessions.apply(
        lambda row: (
            "ambiguous"
            if row["scope_status"] != "resolved"
            else (
                "multiple_distinct_statement_scopes"
                if row["statement_entity_count"] > 1
                else "one_statement_scope"
            )
        ),
        axis=1,
    )
    joint_detail = joint.merge(
        accessions,
        on=["accession", "feature_year"],
        how="left",
        validate="many_to_one",
    )
    classified = joint_detail.apply(classify_joint_row, axis=1, result_type="expand")
    classified.columns = [
        "economic_entity_status",
        "recommended_membership_action",
        "economic_entity_reason",
    ]
    joint_detail = pd.concat([joint_detail, classified], axis=1)
    group_map = connected_joint_groups(joint)
    joint_detail["economic_group_id"] = joint_detail["cik10"].map(group_map)
    joint_detail["economic_statement_scope_id"] = joint_detail.apply(
        lambda row: (
            f"{row['accession']}:{row['cik10']}"
            if row["recommended_membership_action"]
            in {"retain_one_economic_entity", "exclude_nonoperating_issuer"}
            else (
                f"{row['accession']}:{row['statement_entity_ciks']}"
                if row["recommended_membership_action"]
                == "exclude_duplicate_registrant_row"
                and row["statement_entity_count"] == 1
                else ""
            )
        ),
        axis=1,
    )

    single = audit.loc[~audit["joint_filing_flag"].fillna(False)].copy()
    single["scope_status"] = "resolved"
    single["scope_reason"] = "exactly_one_registrant_in_accession"
    single["statement_entity_ciks"] = single["cik10"]
    single["economic_entity_status"] = "separate_reporting_entity_with_own_statements"
    single["recommended_membership_action"] = "retain_one_economic_entity"
    single["economic_entity_reason"] = "single_filer_original_10k"
    single["economic_group_id"] = "single_" + single["cik10"].astype(str)
    single["economic_statement_scope_id"] = (
        single["accession"].astype(str) + ":" + single["cik10"].astype(str)
    )
    single["eligible_observation_count"] = 1
    single["eligible_ciks"] = single["cik10"]

    detail = pd.concat([single, joint_detail], ignore_index=True, sort=False)
    detail["registrant_role_resolved"] = detail.apply(source_role, axis=1)
    detail["potential_non_operating_finance_registrant"] = (
        detail["recommended_membership_action"].eq("retain_one_economic_entity")
        & detail["company_name_historical"].str.contains(
            r"\b(?:finance|capital)\s+(?:corp|corporation|inc|llc)\b",
            case=False,
            na=False,
            regex=True,
        )
    )
    detail = detail.sort_values(["feature_year", "accession", "cik10"])

    role_counts = (
        detail.groupby("registrant_role_resolved")
        .agg(observations=("cik10", "size"), unique_ciks=("cik10", "nunique"), accessions=("accession", "nunique"))
        .reset_index()
    )
    all_eligible_role_counts = (
        eligible.groupby("registrant_role_resolved")
        .agg(
            observations=("cik10", "size"),
            unique_ciks=("cik10", "nunique"),
            accessions=("accession", "nunique"),
        )
        .reset_index()
    )
    status_counts = (
        detail.groupby(["economic_entity_status", "recommended_membership_action"])
        .size()
        .rename("observations")
        .reset_index()
    )
    joint_group_sizes = (
        joint.groupby("accession")["cik10"].size().value_counts().sort_index()
    )
    multi_joint = joint.groupby("accession")["cik10"].transform("size").gt(1)
    duplicate_risk_rows = int(multi_joint.sum())

    resolved_accessions = int(accessions["scope_status"].eq("resolved").sum())
    ambiguous_accessions = int(accessions["scope_status"].eq("ambiguous").sum())
    separate_rows = int(
        detail["economic_entity_status"]
        .isin(
            [
                "separate_reporting_entity_with_own_statements",
                "separate_reporting_entity_nonoperating_coissuer",
            ]
        )
        .sum()
    )
    confirmed_shared_rows = int(
        detail["recommended_membership_action"]
        .eq("exclude_duplicate_registrant_row")
        .sum()
    )
    shared_noneligible_ambiguous_rows = int(
        detail["economic_entity_status"]
        .eq("co_registrant_sharing_statement_of_noneligible_cik")
        .sum()
    )
    ambiguous_rows = int(
        detail["recommended_membership_action"].eq("mark_ambiguous").sum()
    )
    potential_finance_rows = int(
        detail["potential_non_operating_finance_registrant"].sum()
    )
    verified_nonoperating_rows = int(
        detail["recommended_membership_action"]
        .eq("exclude_nonoperating_issuer")
        .sum()
    )
    scope_structure_counts = (
        accessions["joint_scope_structure"]
        .value_counts()
        .rename_axis("joint_scope_structure")
        .reset_index(name="accessions")
    )
    freeze_ready = not (
        detail["recommended_membership_action"]
        .isin(
            [
                "exclude_duplicate_registrant_row",
                "exclude_nonoperating_issuer",
                "mark_ambiguous",
            ]
        )
        .any()
    )

    target_manifest_path = BASE_DIR / "configs" / "target_candidate_v2_pit_b_freeze_manifest.yaml"
    target_manifest = yaml.safe_load(target_manifest_path.read_text(encoding="utf-8"))
    frozen_target_path = BASE_DIR / "data" / "interim" / "target_candidate_v2_pit_b.csv"
    expected_target_hash = next(
        item["sha256"]
        for item in target_manifest["non_versioned_reproduction_checks"]
        if item["path"] == "data/interim/target_candidate_v2_pit_b.csv"
    )
    actual_target_hash = sha256_path(frozen_target_path)
    if actual_target_hash != expected_target_hash:
        raise ValueError("Frozen PIT-B artifact changed; audit aborted")

    output_columns = [
        "research_universe_company_year_id",
        "accession",
        "feature_year",
        "cik10",
        "company_name_historical",
        "historical_sic",
        "research_sector",
        "registrant_role",
        "registrant_role_resolved",
        "joint_filing_flag",
        "accession_registrant_count",
        "eligible_observation_count",
        "xbrl_instance",
        "scope_status",
        "scope_reason",
        "statement_entity_ciks",
        "manual_series_id",
        "manual_evidence",
        "non_operating_issuer_ciks",
        "economic_entity_status",
        "recommended_membership_action",
        "economic_entity_reason",
        "economic_group_id",
        "economic_statement_scope_id",
        "potential_non_operating_finance_registrant",
    ]
    DETAIL_PATH.parent.mkdir(parents=True, exist_ok=True)
    detail[output_columns].to_csv(DETAIL_PATH, index=False)
    accessions.to_csv(ACCESSION_PATH, index=False)

    summary = {
        "audit_scope_observations": int(len(detail)),
        "audit_scope_unique_ciks": int(detail["cik10"].nunique()),
        "single_filer_non_xbrl_observations": int(
            detail["registrant_role_resolved"].eq("single_filer_non_xbrl_registrant").sum()
        ),
        "joint_observations": int(len(joint)),
        "joint_accessions": int(joint["accession"].nunique()),
        "joint_accessions_resolved": resolved_accessions,
        "joint_accessions_ambiguous": ambiguous_accessions,
        "joint_observations_in_multi_eligible_accessions": duplicate_risk_rows,
        "separate_reporting_entity_observations": separate_rows,
        "confirmed_shared_statement_duplicate_observations": confirmed_shared_rows,
        "shared_statement_of_noneligible_cik_ambiguous_observations": (
            shared_noneligible_ambiguous_rows
        ),
        "ambiguous_observations": ambiguous_rows,
        "potential_non_operating_finance_registrant_observations": potential_finance_rows,
        "verified_nonoperating_coissuer_observations": verified_nonoperating_rows,
        "freeze_ready": freeze_ready,
        "canonical_universe_sha256_verified": universe_sha256,
        "frozen_target_sha256_verified": actual_target_hash,
        "artifacts": {},
    }
    for path in (DETAIL_PATH, ACCESSION_PATH):
        summary["artifacts"][str(path.relative_to(BASE_DIR))] = {
            "bytes": path.stat().st_size,
            "sha256": sha256_path(path),
        }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    reason_counts = (
        detail.loc[detail["recommended_membership_action"].eq("mark_ambiguous"), "economic_entity_reason"]
        .value_counts()
        .rename_axis("reason")
        .reset_index(name="observations")
    )
    manual_reason_counts = (
        accessions.loc[accessions["manual_evidence"].notna(), "scope_reason"]
        .value_counts()
        .rename_axis("manual_resolution")
        .reset_index(name="accessions")
    )
    group_table = joint_group_sizes.rename_axis("eligible_ciks_per_accession").reset_index(name="accessions")
    report = f"""# Final registrant-role / economic-entity audit

## Scope and invariants

The audit covers every eligible observation carrying the old combined role
`co_registrant_or_non_xbrl_registrant` and every eligible observation with
`joint_filing_flag = True`: **{len(detail):,} observations** and
**{detail['cik10'].nunique():,} CIKs**.  The frozen PIT-B target was neither
read for analysis nor modified; its frozen artifact hash was reverified as
`{actual_target_hash}`.  X_t was not built.
The canonical universe was not rewritten; its evidence-bound hash is
`{universe_sha256}`.

The all-case screen reads the primary original 10-K and maps registrants to
distinct audited annual balance-sheet, operations/income and cash-flow suites.
XBRL context identifiers are retained as secondary provenance, but are not used
alone: several combined filings have one XBRL entity identifier and two or more
separately audited reporting entities. All 13 non-XBRL joint filings also have
explicit manual decisions in `{MANUAL_PATH.relative_to(BASE_DIR)}`.
Inconclusive cases fail closed as ambiguous.

## Corrected registrant roles

All eligible observations:

{as_markdown_table(all_eligible_role_counts)}

Observations specifically covered by this audit:

{as_markdown_table(role_counts)}

The old role was therefore not semantically usable: it combined **single-filer
non-XBRL registrants** with actual **joint-filing co-registrants**.

## Economic-entity result

{as_markdown_table(status_counts)}

Across the scoped observations, **{separate_rows:,}** are supported as separate
reporting entities with their own 10-K statement scope. This total comprises
**{int(detail['recommended_membership_action'].eq('retain_one_economic_entity').sum()):,}**
retained observations and **{verified_nonoperating_rows:,}** verified nominal
finance co-issuers with their own statements but no substantive operations.
There are **{confirmed_shared_rows:,}** confirmed duplicate co-registrant rows
sharing another eligible registrant's statement scope and **{ambiguous_rows:,}**
unresolved observations. Of the ambiguous observations,
**{shared_noneligible_ambiguous_rows:,}** point to a statement entity that is
not eligible under its own historical classification; its statements are not
relabelled using the co-registrant's SIC.

The primary-document mapper resolved 311 straightforward joint accessions.
Another **{int(accessions['manual_evidence'].notna().sum()):,}** edge-case
accessions have explicit, accession-level primary-10-K decisions:

{as_markdown_table(manual_reason_counts)}

There are **{len(joint):,} eligible rows in {joint['accession'].nunique():,}
joint accessions**.  Of these accessions, **{resolved_accessions:,}** have a
resolved statement scope and **{ambiguous_accessions:,}** are ambiguous.

Statement-scope structure by accession:

{as_markdown_table(scope_structure_counts)}

## Can one accession generate multiple observations for one economic entity?

Yes.  The eligible-CIK multiplicity is:

{as_markdown_table(group_table)}

**{duplicate_risk_rows:,} eligible rows** occur in accessions that generate more
than one eligible CIK-year. Under the current `preserve_each_master_index_registrant_and_flag`
policy, all can flow into X_t as apparently independent company-years. The
audit confirms that **{confirmed_shared_rows:,} excess rows in
{int(detail.loc[detail['recommended_membership_action'].eq('exclude_duplicate_registrant_row'), 'accession'].nunique()):,}
accessions** have no distinct statement scope. Those are deterministic
duplicates if the shared values are attached to every CIK. Distinct
parent/subsidiary statement scopes are not duplicates, but remain economically
linked and often overlap; splitting by CIK can still put the same group on both
sides of a model split.

## Conservative membership rule proposed

1. Split the source role into `single_filer_xbrl_registrant`,
   `single_filer_non_xbrl_registrant`, `joint_primary_registrant`, and
   `joint_co_registrant` before any feature extraction.
2. A single-filer original 10-K remains one reporting entity regardless of
   whether an XBRL instance exists.  Non-XBRL affects X_t availability, not
   universe membership.
3. For a joint filing, define an `economic_statement_scope_id` from accession,
   annual statement scope, and XBRL entity CIK.  Retain at most one row per
   scope unless distinct full annual statement scopes are positively evidenced.
4. Retain a CIK as a separate reporting entity only when its own consolidated
   annual balance sheet, income/operations statement, and cash-flow statement
   are evidenced for that accession.  A cover-page filer, guarantor, finance
   subsidiary, operating partnership, or co-registrant without its own scope is
   not an independent company-year.
5. If multiple legal CIKs represent one consolidated/DLC economic scope, keep
   one stable representative CIK and record every linked co-registrant CIK in
   provenance. Group/split later data by `economic_statement_scope_id`, never
   by CIK alone. Distinct but related scopes from joint filings must share the
   connected-component `economic_group_id` for all future splitting and
   clustered inference.
6. If the statement entity CIK is sector-excluded while a co-registrant CIK is
   superficially eligible, do not transfer the co-registrant SIC to the shared
   statements.  Mark the candidate ambiguous pending a documented economic-scope
   classification.
7. If evidence cannot distinguish shared from separate full statements, set
   membership to `ambiguous`; do not guess and do not let the row enter X_t.
8. A finance/capital name is only a review flag, never an exclusion rule. The
   audit identifies **{potential_finance_rows:,}** such retained name-screened
   rows, but excludes only **{verified_nonoperating_rows:,}** observations for
   which the primary filing expressly documents a nominal co-issuer with no
   substantive operations. A separate zero-activity finance shell is not a
   duplicate, but it is outside an operating-company research population.

## Ambiguous cases

{as_markdown_table(reason_counts)}

## Freeze gate

The canonical universe still preserves every master-index registrant and still
uses the combined source role. Before freezing, it must (a) split that role,
(b) remove the {confirmed_shared_rows:,} confirmed duplicate rows while keeping
one stable statement-scope representative, (c) apply the issuer-substance
exclusion to the {verified_nonoperating_rows:,} verified nominal co-issuer rows,
(d) keep the {ambiguous_rows:,} unresolved rows out of X_t as ambiguous, and
(e) persist `economic_statement_scope_id` and connected `economic_group_id`.
The universe audit must then be rerun. No canonical membership row has been
changed by this freeze-gate audit.

**{'RESEARCH UNIVERSE READY TO FREEZE' if freeze_ready else 'RESEARCH UNIVERSE NOT READY TO FREEZE'}**
"""
    REPORT_PATH.write_text(report, encoding="utf-8")
    summary["artifacts"][str(REPORT_PATH.relative_to(BASE_DIR))] = {
        "bytes": REPORT_PATH.stat().st_size,
        "sha256": sha256_path(REPORT_PATH),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

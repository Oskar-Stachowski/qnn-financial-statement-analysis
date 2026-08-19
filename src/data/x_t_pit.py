"""Build the raw point-in-time X_t v1 artifact from frozen universe anchors.

The module deliberately builds no model matrix and performs no imputation,
winsorization, scaling, missing-indicator construction, or feature selection.
Every eligible historical-universe row is retained.  Financial facts are
resolved only inside the exact accession frozen by research universe v1.1.0.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, datetime, time, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import yaml

from src.data import target_candidate_v2_pit as semantic
from src.data.research_universe_target_application import verify_frozen_inputs
from src.data.revenue_statement_resolver import resolve_primary_statement_revenue


BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "configs" / "x_t_pit_v1.yaml"

PRIMITIVES = (
    "assets",
    "liabilities",
    "current_assets",
    "current_liabilities",
    "revenues",
    "net_income",
    "operating_cash_flow",
)

PROVENANCE_FIELDS = (
    "value",
    "status",
    "reason",
    "strategy",
    "tag",
    "source_tags",
    "source_values",
    "source_accessions",
    "source_starts",
    "source_ends",
    "accn",
    "start",
    "end",
    "duration_days",
    "filed",
    "accepted_at",
    "role",
    "document_fiscal_year_focus",
    "document_fiscal_period_focus",
    "document_period_end_date",
    "frame",
    "candidate_count",
    "statement_file",
    "statement_short_name",
    "statement_long_name",
    "statement_role_uri",
    "statement_label",
    "statement_concepts",
    "statement_row_class",
    "statement_priority",
    "statement_scale",
    "statement_scale_label",
    "statement_candidate_count",
    "context_id",
    "dimensions",
    "source_cache_path",
    "available_at",
    "available_at_precision",
)

PAIR_FIELDS = (
    "status",
    "reason",
    "strategy",
    "semantic_diagnostic",
    "competing_strategies",
    "candidate_strategies",
    "detail_reasons",
    "statement_candidate_count",
    "statement_candidates_json",
)

FEATURE_FIELDS = (
    "value",
    "status",
    "reason",
    "block",
    "available_at",
    "available_at_precision",
    "source_primitives",
    "source_roles",
    "near_zero_denominator_flag",
)

METADATA_COLUMNS = (
    "research_universe_company_year_id",
    "cik10",
    "feature_year",
    "split",
    "company_name_historical",
    "historical_sic",
    "historical_sic_description",
    "historical_sic_source",
    "research_sector",
    "membership_status",
    "anchor_accession",
    "anchor_form",
    "anchor_filed",
    "anchor_accepted_at",
    "anchor_period_end",
    "anchor_xbrl_period_end",
    "anchor_period_end_delta_days",
    "anchor_document_fiscal_year_focus",
    "anchor_document_fiscal_period_focus",
    "anchor_xbrl_instance",
    "xbrl_submission_available",
    "joint_filing_flag",
    "statement_scope_xbrl_available",
    "statement_scope_xbrl_status",
    "statement_scope_xbrl_reason",
    "statement_scope_xbrl_entity_ciks",
    "statement_scope_xbrl_context_files",
    "statement_scope_xbrl_evidence_path",
    "registrant_role_resolved",
    "representative_cik",
    "linked_co_registrant_ciks",
    "economic_statement_scope_id",
    "economic_group_id",
    "prediction_timestamp",
    "prediction_timestamp_precision",
    "prediction_timestamp_lower_precision",
    "feature_policy_id",
    "feature_policy_version",
    "source_companyfacts_file",
    "anchor_record_count",
    "anchor_period_validation_status",
    "anchor_period_validation_reason",
    "comparative_period_end",
    "comparative_period_source",
    "comparative_period_gap_days",
    "comparative_period_validation_status",
    "comparative_period_validation_reason",
)

ROW_DIAGNOSTIC_COLUMNS = (
    "x_t_status",
    "x_t_status_reason",
    "L_available_count",
    "D_available_count",
    "R_available_count",
    "feature_available_count",
    "feature_missing_count",
    "feature_ambiguous_count",
    "feature_not_computable_count",
    "near_zero_denominator_count",
    "near_zero_denominator_features",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return payload


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_yaml(path)
    if config.get("x_t", {}).get("id") != "x_t_pit":
        raise ValueError(f"Unexpected X_t policy identity in {path}")
    blocks = config.get("blocks", {})
    if set(blocks) != {"L", "D", "R"}:
        raise ValueError("X_t v1 must define exactly L, D, and R blocks")
    return config


def configured_path(config: dict[str, Any], section: str, key: str) -> Path:
    return BASE_DIR / str(config[section][key])


def load_negative_sign_review(
    config: dict[str, Any],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    path = configured_path(config, "sources", "negative_sign_review")
    payload = load_yaml(path)
    metadata = payload.get("review", {})
    if metadata.get("id") != "x_t_pit_v1_negative_current_primitive_sign_review":
        raise ValueError(f"Unexpected negative-sign review identity in {path}")
    if metadata.get("test_years_inspected") is not False:
        raise ValueError("Negative-sign review must not inspect test years")
    cases = payload.get("cases", [])
    if not isinstance(cases, list) or len(cases) != 25:
        raise ValueError("Negative-sign review must contain exactly 25 primitive cases")
    decisions: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in cases:
        if not isinstance(item, dict):
            raise ValueError("Every negative-sign review case must be a mapping")
        key = (
            text(item.get("company_year_id")),
            text(item.get("accession")),
            text(item.get("primitive")),
        )
        if not all(key) or key[2] not in {
            "assets",
            "liabilities",
            "current_assets",
            "current_liabilities",
            "revenues",
        }:
            raise ValueError(f"Invalid negative-sign review key: {key}")
        if key in decisions:
            raise ValueError(f"Duplicate negative-sign review key: {key}")
        if item.get("action") not in {"retain", "ambiguous_na"}:
            raise ValueError(f"Invalid negative-sign review action for {key}")
        if item.get("outcome") not in {
            "reported_economically_valid",
            "xbrl_semantic_or_context_error",
            "unresolved",
        }:
            raise ValueError(f"Invalid negative-sign review outcome for {key}")
        decisions[key] = dict(item)
    return decisions


def apply_negative_sign_review(
    selection: dict[str, Any],
    decision: dict[str, Any] | None,
) -> dict[str, Any]:
    if decision is None:
        return selection
    if selection.get("status") != "selected":
        raise RuntimeError("Reviewed negative primitive is no longer selected upstream")
    actual = float(selection["value"])
    expected = float(decision["selected_value_before"])
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9):
        raise RuntimeError(
            "Reviewed negative primitive value changed upstream: "
            f"expected={expected}, actual={actual}"
        )
    if actual >= 0:
        raise RuntimeError("Negative-sign review attached to a nonnegative value")
    if decision["action"] == "retain":
        return selection
    result = dict(selection)
    result["value"] = None
    result["status"] = "ambiguous"
    result["reason"] = (
        "manual_primary_statement_sign_review:" + str(decision["reason"])
    )
    return result


def split_for_year(year: int) -> str:
    if year <= 2020:
        return "train"
    if year <= 2022:
        return "validation"
    if year <= 2024:
        return "test"
    return "out_of_scope"


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def prediction_timestamp(row: dict[str, Any]) -> tuple[str, str, bool]:
    accepted = text(row.get("accepted_at"))
    if accepted:
        try:
            parsed = datetime.fromisoformat(accepted.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"Invalid frozen accepted_at timestamp: {accepted!r}") from error
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo("America/New_York"))
        else:
            parsed = parsed.astimezone(ZoneInfo("America/New_York"))
        return parsed.isoformat(), "accepted_timestamp_et", False
    filed = semantic.parse_date(row.get("filed"))
    if filed is None:
        return "", "unavailable", True
    next_day = filed + timedelta(days=1)
    timestamp = datetime.combine(
        next_day,
        time(0, 0),
        tzinfo=ZoneInfo("America/New_York"),
    )
    return timestamp.isoformat(), "filed_date_next_day_midnight_et", True


def feature_names(config: dict[str, Any]) -> list[str]:
    return [
        str(feature)
        for block in ("L", "D", "R")
        for feature in config["blocks"][block]["features"]
    ]


def output_columns(config: dict[str, Any]) -> list[str]:
    columns = list(METADATA_COLUMNS)
    for primitive in PRIMITIVES:
        columns.extend(f"current_t_{primitive}_{field}" for field in PROVENANCE_FIELDS)
        columns.extend(f"pair_{primitive}_{field}" for field in PAIR_FIELDS)
        columns.extend(
            f"comparative_tm1_{primitive}_{field}" for field in PROVENANCE_FIELDS
        )
        columns.extend(f"pair_current_t_{primitive}_{field}" for field in PROVENANCE_FIELDS)
    for feature in feature_names(config):
        columns.extend(f"{feature}_{field}" for field in FEATURE_FIELDS)
    columns.extend(ROW_DIAGNOSTIC_COLUMNS)
    if len(columns) != len(set(columns)):
        duplicates = [item for item, count in Counter(columns).items() if count > 1]
        raise RuntimeError(f"Duplicate output columns: {duplicates}")
    return columns


def load_universe(config: dict[str, Any]) -> tuple[pd.DataFrame, dict[tuple[str, int], date]]:
    path = configured_path(config, "frozen_inputs", "universe_artifact")
    usecols = [
        "research_universe_company_year_id",
        "accession",
        "cik10",
        "feature_year",
        "company_name_historical",
        "historical_sic",
        "historical_sic_description",
        "historical_sic_source",
        "research_sector",
        "membership_status",
        "form",
        "filed",
        "accepted_at",
        "membership_available_at_precision",
        "period_end",
        "document_fiscal_year_focus",
        "document_fiscal_period_focus",
        "xbrl_instance",
        "xbrl_submission_available",
        "joint_filing_flag",
        "registrant_role_resolved",
        "representative_cik",
        "linked_co_registrant_ciks",
        "economic_statement_scope_id",
        "economic_group_id",
    ]
    frame = pd.read_csv(path, usecols=usecols, dtype=str, low_memory=False).fillna("")
    frame["cik10"] = frame["cik10"].str.zfill(10)
    frame["feature_year"] = pd.to_numeric(frame["feature_year"], errors="raise").astype(int)
    period_ends: dict[tuple[str, int], date] = {}
    for row in frame.itertuples(index=False):
        parsed = semantic.parse_date(row.period_end)
        if parsed is not None:
            period_ends[(row.cik10, int(row.feature_year))] = parsed
    eligible = frame.loc[frame["membership_status"].eq("eligible")].copy()
    eligible = eligible.loc[eligible["feature_year"].between(2011, 2024)].copy()
    eligible = eligible.sort_values(["cik10", "feature_year"]).reset_index(drop=True)
    if len(eligible) != 64_901:
        raise RuntimeError(f"Expected 64,901 eligible rows, got {len(eligible):,}")
    if eligible.duplicated(["cik10", "feature_year"]).any():
        raise RuntimeError("Frozen eligible universe contains duplicate CIK-years")
    eligible = annotate_statement_scope_xbrl(eligible, config)
    return eligible, period_ends


def annotate_statement_scope_xbrl(
    eligible: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    """Resolve XBRL availability for the frozen economic statement scope.

    `xbrl_submission_available` is filing-level metadata.  A joint filing can
    contain an XBRL instance for one registrant while presenting a separate,
    untagged annual statement suite for another registrant.  The latter is a
    scope-specific non-XBRL observation under the accepted X_t policy.
    """

    audit_path = configured_path(config, "sources", "registrant_scope_audit")
    audit = pd.read_csv(
        audit_path,
        usecols=["accession", "xbrl_entity_ciks", "xbrl_context_files"],
        dtype=str,
        low_memory=False,
    ).fillna("")
    if audit["accession"].duplicated().any():
        raise RuntimeError("Registrant-scope audit contains duplicate accessions")
    by_accession = audit.set_index("accession").to_dict("index")
    evidence_root = configured_path(config, "sources", "registrant_scope_evidence")

    output = eligible.copy()
    resolved: list[dict[str, Any]] = []
    for source in output.to_dict("records"):
        accession = text(source.get("accession"))
        filing_xbrl = truthy(source.get("xbrl_submission_available"))
        joint = truthy(source.get("joint_filing_flag"))
        representative = text(source.get("representative_cik") or source.get("cik10")).zfill(10)
        evidence = by_accession.get(accession, {})
        entity_ciks = sorted(
            {
                item.zfill(10)
                for item in text(evidence.get("xbrl_entity_ciks")).split(";")
                if item.strip().isdigit()
            }
        )
        context_files = text(evidence.get("xbrl_context_files"))
        if not filing_xbrl:
            available: bool | str = False
            status = "not_available_non_xbrl"
            reason = "frozen_universe_anchor_has_no_xbrl_submission"
        elif not joint:
            available = True
            status = "available"
            reason = "single_filer_xbrl_submission"
        elif not evidence:
            available = ""
            status = "ambiguous"
            reason = "joint_filing_scope_xbrl_evidence_unavailable"
        elif representative in entity_ciks:
            available = True
            status = "available"
            reason = "representative_cik_matches_xbrl_entity_identifier"
        elif entity_ciks:
            available = False
            status = "not_available_non_xbrl"
            reason = "separate_statement_scope_not_tagged_in_joint_xbrl_instance"
        else:
            available = ""
            status = "ambiguous"
            reason = "joint_filing_xbrl_entity_identifier_unresolved"
        resolved.append(
            {
                "statement_scope_xbrl_available": available,
                "statement_scope_xbrl_status": status,
                "statement_scope_xbrl_reason": reason,
                "statement_scope_xbrl_entity_ciks": ";".join(entity_ciks),
                "statement_scope_xbrl_context_files": context_files,
                "statement_scope_xbrl_evidence_path": (
                    str((evidence_root / accession).relative_to(BASE_DIR))
                    if joint and evidence
                    else ""
                ),
            }
        )
    return pd.concat(
        [output.reset_index(drop=True), pd.DataFrame(resolved)], axis=1
    )


def records_by_accession(
    facts_root: dict[str, Any],
    semantic_config: dict[str, Any],
    scope: semantic.Scope,
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for tag in semantic.required_tags(semantic_config):
        units = facts_root.get("us-gaap", {}).get(tag, {}).get("units", {})
        facts = units.get("USD", []) if isinstance(units, dict) else []
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            record = semantic.fact_record(tag, fact, scope)
            if record is not None:
                record["source_format"] = "sec_companyfacts_exact_accession"
                record["context_id"] = ""
                record["dimensions"] = "issuer_level_companyfacts_api"
                output[str(record["accn"])].append(record)
    return output


def _xml_local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def _xml_namespace(value: str) -> str:
    return value[1:].split("}", 1)[0] if value.startswith("{") else ""


def _normalized_entity_cik(value: Any) -> str:
    digits = re.sub(r"\D", "", text(value))
    return digits.zfill(10) if digits and len(digits) <= 10 else ""


def scope_xbrl_instance_records(
    source: dict[str, Any],
    semantic_config: dict[str, Any],
    scope: semantic.Scope,
) -> list[dict[str, Any]]:
    """Extract issuer-total US-GAAP facts from a validated joint-filing scope.

    This fallback is used only when Company Facts has no records for the exact
    accession even though the frozen representative CIK matches the XBRL
    entity identifier found in the locally audited filing package.
    """

    if text(source.get("statement_scope_xbrl_status")) != "available":
        return []
    if not truthy(source.get("joint_filing_flag")):
        return []
    representative = _normalized_entity_cik(
        source.get("representative_cik") or source.get("cik10")
    )
    entity_ciks = {
        _normalized_entity_cik(item)
        for item in text(source.get("statement_scope_xbrl_entity_ciks")).split(";")
    }
    if not representative or representative not in entity_ciks:
        return []
    evidence_path = BASE_DIR / text(source.get("statement_scope_xbrl_evidence_path"))
    filenames = [
        item
        for item in text(source.get("statement_scope_xbrl_context_files")).split(";")
        if item
    ]
    required = semantic.required_tags(semantic_config)
    records: list[dict[str, Any]] = []
    for filename in filenames:
        path = evidence_path / filename
        if not path.exists() or path.suffix.lower() != ".xml":
            continue
        root = ElementTree.parse(path).getroot()
        contexts: dict[str, dict[str, str]] = {}
        for element in root.iter():
            if _xml_local_name(element.tag) != "context":
                continue
            context_id = text(element.attrib.get("id"))
            identifier = next(
                (
                    text(child.text)
                    for child in element.iter()
                    if _xml_local_name(child.tag) == "identifier"
                ),
                "",
            )
            if _normalized_entity_cik(identifier) != representative:
                continue
            dimensions = [
                child
                for child in element.iter()
                if _xml_local_name(child.tag) in {"explicitMember", "typedMember"}
            ]
            if dimensions:
                continue
            instant = next(
                (
                    text(child.text)
                    for child in element.iter()
                    if _xml_local_name(child.tag) == "instant"
                ),
                "",
            )
            start = next(
                (
                    text(child.text)
                    for child in element.iter()
                    if _xml_local_name(child.tag) == "startDate"
                ),
                "",
            )
            end = next(
                (
                    text(child.text)
                    for child in element.iter()
                    if _xml_local_name(child.tag) == "endDate"
                ),
                "",
            )
            contexts[context_id] = {
                "start": start,
                "end": instant or end,
                "dimensions": "issuer_total_no_explicit_or_typed_dimensions",
            }

        usd_units: set[str] = set()
        for element in root.iter():
            if _xml_local_name(element.tag) != "unit":
                continue
            unit_id = text(element.attrib.get("id"))
            measures = [
                text(child.text).upper()
                for child in element.iter()
                if _xml_local_name(child.tag) == "measure"
            ]
            if len(measures) == 1 and measures[0].split(":")[-1] == "USD":
                usd_units.add(unit_id)

        for element in root.iter():
            tag = _xml_local_name(element.tag)
            namespace = _xml_namespace(element.tag).lower()
            if tag not in required or "fasb.org/us-gaap" not in namespace:
                continue
            context_id = text(element.attrib.get("contextRef"))
            context = contexts.get(context_id)
            if context is None or text(element.attrib.get("unitRef")) not in usd_units:
                continue
            if any(_xml_local_name(key) == "nil" and truthy(value) for key, value in element.attrib.items()):
                continue
            raw_value = text(element.text).replace(",", "").strip()
            try:
                value = float(raw_value)
                scale = int(text(element.attrib.get("scale")) or "0")
                if scale:
                    value *= 10.0**scale
                if text(element.attrib.get("sign")) == "-":
                    value *= -1.0
            except (TypeError, ValueError, OverflowError):
                continue
            record = semantic.fact_record(
                tag,
                {
                    "val": value,
                    "accn": text(source.get("accession")),
                    "form": text(source.get("form")),
                    "filed": text(source.get("filed")),
                    "start": context["start"],
                    "end": context["end"],
                    "fy": source.get("document_fiscal_year_focus")
                    or source.get("feature_year"),
                    "fp": source.get("document_fiscal_period_focus") or "FY",
                    "frame": "",
                },
                scope,
            )
            if record is None:
                continue
            record.update(
                {
                    "source_format": "joint_filing_scope_xbrl_instance",
                    "context_id": context_id,
                    "dimensions": context["dimensions"],
                    "source_cache_path": str(path.relative_to(BASE_DIR)),
                }
            )
            records.append(record)
    return records


def exact_anchor(
    row: dict[str, Any],
    accession_records: dict[str, list[dict[str, Any]]],
    scope: semantic.Scope,
) -> tuple[dict[str, Any] | None, str, str]:
    accession = text(row.get("accession"))
    report_end = semantic.parse_date(row.get("period_end"))
    if text(row.get("form")).upper() != "10-K":
        return None, "hard_exclude", "frozen_anchor_form_not_original_10_k"
    if not accession or report_end is None:
        return None, "hard_exclude", "frozen_anchor_identity_or_period_missing"
    records = accession_records.get(accession, [])
    if not records:
        return None, "missing", "exact_anchor_companyfacts_records_unavailable"
    if any(text(record.get("accn")) != accession for record in records):
        return None, "hard_exclude", "mixed_accession_records_in_exact_anchor"
    xbrl_report_end, report_end_reason = semantic.choose_report_end(
        records, report_end.isoformat(), scope
    )
    if xbrl_report_end is None:
        return None, "ambiguous", "exact_anchor_annual_current_context_unresolved"
    end_delta_days = abs((xbrl_report_end - report_end).days)
    if end_delta_days > scope.period_start_tolerance_days:
        return None, "ambiguous", "frozen_and_xbrl_period_end_materially_disagree"
    anchor = {
        "accn": accession,
        "records": records,
        "report_end": xbrl_report_end,
        "filed": text(row.get("filed")),
        "accepted_at": text(row.get("accepted_at")),
        "primary_document": text(row.get("xbrl_instance")),
        "document_period_end_date": xbrl_report_end.isoformat(),
        "document_period_end_reason": report_end_reason,
        "frozen_universe_period_end": report_end.isoformat(),
        "frozen_universe_period_end_delta_days": end_delta_days,
        "document_fiscal_year_focus": semantic.safe_int(
            row.get("document_fiscal_year_focus")
        ),
        "document_fiscal_period_focus": text(
            row.get("document_fiscal_period_focus")
        ),
        "resolved_fiscal_year": int(row["feature_year"]),
        "resolved_fiscal_year_reason": "frozen_universe_feature_year",
        "resolved_fiscal_year_count": 1,
    }
    return anchor, "available", "exact_frozen_universe_anchor_validated"


def infer_comparative_end(
    anchor: dict[str, Any],
    current_end: date,
    scope: semantic.Scope,
) -> tuple[date | None, str]:
    counts: Counter[date] = Counter()
    for record in anchor["records"]:
        end = semantic.parse_date(record.get("end"))
        if end is None or end >= current_end:
            continue
        gap = (current_end - end).days
        if not scope.annual_period_min_days <= gap <= scope.annual_period_max_days:
            continue
        if text(record.get("document_fiscal_period_focus")).upper() != "FY":
            continue
        if record.get("start"):
            duration = semantic.annual_duration(record)
            if duration is None or not (
                scope.annual_period_min_days <= duration <= scope.annual_period_max_days
            ):
                continue
        counts[end] += 1
    if not counts:
        return None, "comparative_period_end_not_observed"
    maximum = max(counts.values())
    best = sorted(end for end, count in counts.items() if count == maximum)
    if len(best) != 1:
        return None, "comparative_period_end_multiple_equal_candidates"
    return best[0], "inferred_from_exact_anchor_annual_contexts"


def selection_with_provenance(
    selection: dict[str, Any],
    *,
    prediction_at: str,
    precision: str,
    cache_path: str,
    role: str | None = None,
) -> dict[str, Any]:
    result = dict(selection)
    if role is not None:
        result["role"] = role
    result.setdefault("context_id", "not_exposed_by_companyfacts")
    result.setdefault("dimensions", "issuer_level_companyfacts_api")
    result.setdefault("source_cache_path", cache_path)
    result["available_at"] = prediction_at
    result["available_at_precision"] = precision
    return result


def enrich_selection_source(
    selection: dict[str, Any],
    anchor: dict[str, Any],
) -> dict[str, Any]:
    if selection.get("status") != "selected":
        return selection
    tags = {
        item
        for item in (
            [text(selection.get("tag"))]
            if not text(selection.get("tag")).startswith("derived:")
            else text(selection.get("source_tags")).split(";")
        )
        if item
    }
    starts = set(text(selection.get("source_starts") or selection.get("start")).split(";"))
    ends = set(text(selection.get("source_ends") or selection.get("end")).split(";"))
    candidates = [
        record
        for record in anchor.get("records", [])
        if text(record.get("tag")) in tags
        and text(record.get("start")) in starts
        and text(record.get("end")) in ends
    ]
    if not candidates:
        return selection
    formats = {text(record.get("source_format")) for record in candidates if record.get("source_format")}
    paths = {text(record.get("source_cache_path")) for record in candidates if record.get("source_cache_path")}
    context_ids = {text(record.get("context_id")) for record in candidates if record.get("context_id")}
    dimensions = {text(record.get("dimensions")) for record in candidates if record.get("dimensions")}
    enriched = dict(selection)
    if formats == {"joint_filing_scope_xbrl_instance"}:
        enriched["context_id"] = ";".join(sorted(context_ids))
        enriched["dimensions"] = ";".join(sorted(dimensions))
        enriched["source_cache_path"] = ";".join(sorted(paths))
    return enriched


def add_provenance(row: dict[str, Any], prefix: str, selection: dict[str, Any]) -> None:
    for field in PROVENANCE_FIELDS:
        row[f"{prefix}_{field}"] = selection.get(field, "")


def add_empty_primitive_statuses(
    row: dict[str, Any],
    status: str,
    reason: str,
    prediction_at: str,
    precision: str,
) -> None:
    selection = selection_with_provenance(
        semantic.empty_selection(status, reason),
        prediction_at=prediction_at,
        precision=precision,
        cache_path="",
    )
    for primitive in PRIMITIVES:
        add_provenance(row, f"current_t_{primitive}", selection)
        for field in PAIR_FIELDS:
            row[f"pair_{primitive}_{field}"] = (
                status if field == "status" else reason if field == "reason" else ""
            )
        add_provenance(row, f"comparative_tm1_{primitive}", selection)
        add_provenance(row, f"pair_current_t_{primitive}", selection)


def revenue_allowed_tags(
    policy: dict[str, Any],
    anchor: dict[str, Any],
    ends: set[date],
) -> tuple[set[str], dict[str, str], str, str]:
    tag_to_strategy: dict[str, str] = {}
    tag_requirements: dict[str, set[str]] = {}
    for strategy in sorted(policy.get("strategies", []), key=lambda item: int(item["priority"])):
        for tag in strategy.get("concepts", []):
            tag_to_strategy.setdefault(str(tag), str(strategy["name"]))
            tag_requirements.setdefault(str(tag), set()).update(
                str(item) for item in strategy.get("requires_absent_concepts", [])
            )
    configured = set(tag_to_strategy)
    relevant = [
        record
        for record in anchor["records"]
        if record.get("tag") in configured
        and semantic.parse_date(record.get("end")) in ends
    ]
    relevant_ends = {semantic.parse_date(record.get("end")) for record in relevant}
    if not ends.issubset(relevant_ends):
        return set(), tag_to_strategy, "missing", "primitive_not_reported_for_required_periods"
    present_tags = {
        str(record.get("tag"))
        for record in anchor["records"]
        if semantic.parse_date(record.get("end")) in ends
    }
    allowed = {
        tag
        for tag in configured
        if not (tag_requirements.get(tag, set()) & present_tags)
    }
    if not allowed or not any(record.get("tag") in allowed for record in relevant):
        return set(), tag_to_strategy, "ambiguous", "component_revenue_without_absent_complement"
    return allowed, tag_to_strategy, "available", "allowed_revenue_tags_resolved"


def resolve_revenue_current(
    policy: dict[str, Any],
    anchor: dict[str, Any],
    previous_end: date | None,
    evidence_directory: Path,
    scope: semantic.Scope,
) -> dict[str, Any]:
    current_end = anchor["report_end"]
    allowed, tag_to_strategy, status, reason = revenue_allowed_tags(
        policy, anchor, {current_end}
    )
    if status != "available":
        return semantic.empty_selection(status, reason, role="current_t")
    if not (evidence_directory / "FilingSummary.xml").exists():
        return semantic.empty_selection(
            "ambiguous", "primary_statement_evidence_unavailable", role="current_t"
        )
    current_start = previous_end + timedelta(days=1) if previous_end else None
    resolved = resolve_primary_statement_revenue(
        directory=evidence_directory,
        anchor=anchor,
        comparative_end=current_end,
        comparative_start=current_start,
        current_end=current_end,
        current_start=current_start,
        allowed_tags=allowed,
        tag_to_strategy={tag: tag_to_strategy[tag] for tag in allowed},
        annual_min_days=scope.annual_period_min_days,
        annual_max_days=scope.annual_period_max_days,
        start_tolerance_days=scope.period_start_tolerance_days,
    )
    if resolved.get("status") != "selected":
        return semantic.empty_selection(
            str(resolved.get("status", "ambiguous")),
            str(resolved.get("reason", "primary_statement_revenue_not_confirmed")),
            role="current_t",
            statement_candidate_count=resolved.get("statement_candidate_count", ""),
            statement_candidates_json=resolved.get("statement_candidates_json", ""),
        )
    selected = dict(resolved["current_t1"])
    selected["role"] = "current_t"
    return selected


def feature_result(
    *,
    block: str,
    selections: Iterable[dict[str, Any]],
    source_primitives: Iterable[str],
    source_roles: str,
    prediction_at: str,
    precision: str,
    formula: Callable[[], float | None],
    denominator_values: Iterable[tuple[str, float | None]] = (),
    denominator_condition: Callable[[float], bool] | None = None,
    numerator_or_log_condition: Callable[[], bool] | None = None,
    near_zero: float = 1000.0,
) -> dict[str, Any]:
    components = list(selections)
    statuses = {str(selection.get("status", "missing")) for selection in components}
    base = {
        "value": None,
        "status": "missing",
        "reason": "source_primitive_missing",
        "block": block,
        "available_at": prediction_at,
        "available_at_precision": precision,
        "source_primitives": ";".join(source_primitives),
        "source_roles": source_roles,
        "near_zero_denominator_flag": False,
    }
    if "not_available_non_xbrl" in statuses:
        return {**base, "status": "not_available_non_xbrl", "reason": "non_xbrl_registrant"}
    if "ambiguous" in statuses:
        reasons = sorted(
            {str(selection.get("reason", "ambiguous")) for selection in components if selection.get("status") == "ambiguous"}
        )
        return {**base, "status": "ambiguous", "reason": ";".join(reasons)}
    if statuses != {"selected"}:
        reasons = sorted(
            {str(selection.get("reason", "missing")) for selection in components if selection.get("status") != "selected"}
        )
        return {**base, "reason": ";".join(reasons) or "source_primitive_missing"}

    denominator_pairs = list(denominator_values)
    near_zero_flag = any(
        value is not None and 0 < abs(float(value)) <= near_zero
        for _, value in denominator_pairs
    )
    if denominator_condition is not None:
        invalid = [
            name
            for name, value in denominator_pairs
            if value is None or not denominator_condition(float(value))
        ]
        if invalid:
            return {
                **base,
                "status": "not_computable",
                "reason": "nonpositive_denominator:" + ";".join(invalid),
                "near_zero_denominator_flag": near_zero_flag,
            }
    if numerator_or_log_condition is not None and not numerator_or_log_condition():
        return {
            **base,
            "status": "not_computable",
            "reason": "economic_domain_condition_not_met",
            "near_zero_denominator_flag": near_zero_flag,
        }
    try:
        value = formula()
    except (ArithmeticError, ValueError, TypeError, OverflowError):
        value = None
    if value is None or not math.isfinite(float(value)):
        return {
            **base,
            "status": "not_computable",
            "reason": "derived_value_not_finite",
            "near_zero_denominator_flag": near_zero_flag,
        }
    return {
        **base,
        "value": float(value),
        "status": "available",
        "reason": "validated_exact_anchor_feature",
        "near_zero_denominator_flag": near_zero_flag,
    }


def add_feature(row: dict[str, Any], name: str, result: dict[str, Any]) -> None:
    for field in FEATURE_FIELDS:
        row[f"{name}_{field}"] = result.get(field, "")


def initial_row(source: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    prediction_at, precision, lower = prediction_timestamp(source)
    return {
        "research_universe_company_year_id": text(
            source.get("research_universe_company_year_id")
        ),
        "cik10": text(source.get("cik10")).zfill(10),
        "feature_year": int(source["feature_year"]),
        "split": split_for_year(int(source["feature_year"])),
        "company_name_historical": text(source.get("company_name_historical")),
        "historical_sic": text(source.get("historical_sic")),
        "historical_sic_description": text(source.get("historical_sic_description")),
        "historical_sic_source": text(source.get("historical_sic_source")),
        "research_sector": text(source.get("research_sector")),
        "membership_status": text(source.get("membership_status")),
        "anchor_accession": text(source.get("accession")),
        "anchor_form": text(source.get("form")),
        "anchor_filed": text(source.get("filed")),
        "anchor_accepted_at": text(source.get("accepted_at")),
        "anchor_period_end": text(source.get("period_end")),
        "anchor_xbrl_period_end": "",
        "anchor_period_end_delta_days": "",
        "anchor_document_fiscal_year_focus": text(
            source.get("document_fiscal_year_focus")
        ),
        "anchor_document_fiscal_period_focus": text(
            source.get("document_fiscal_period_focus")
        ),
        "anchor_xbrl_instance": text(source.get("xbrl_instance")),
        "xbrl_submission_available": truthy(source.get("xbrl_submission_available")),
        "joint_filing_flag": truthy(source.get("joint_filing_flag")),
        "statement_scope_xbrl_available": source.get(
            "statement_scope_xbrl_available", ""
        ),
        "statement_scope_xbrl_status": text(
            source.get("statement_scope_xbrl_status")
        ),
        "statement_scope_xbrl_reason": text(
            source.get("statement_scope_xbrl_reason")
        ),
        "statement_scope_xbrl_entity_ciks": text(
            source.get("statement_scope_xbrl_entity_ciks")
        ),
        "statement_scope_xbrl_context_files": text(
            source.get("statement_scope_xbrl_context_files")
        ),
        "statement_scope_xbrl_evidence_path": text(
            source.get("statement_scope_xbrl_evidence_path")
        ),
        "registrant_role_resolved": text(source.get("registrant_role_resolved")),
        "representative_cik": text(source.get("representative_cik")).zfill(10),
        "linked_co_registrant_ciks": text(source.get("linked_co_registrant_ciks")),
        "economic_statement_scope_id": text(source.get("economic_statement_scope_id")),
        "economic_group_id": text(source.get("economic_group_id")),
        "prediction_timestamp": prediction_at,
        "prediction_timestamp_precision": precision,
        "prediction_timestamp_lower_precision": lower,
        "feature_policy_id": str(config["x_t"]["id"]),
        "feature_policy_version": str(config["x_t"]["version"]),
    }


def finalize_row_status(row: dict[str, Any], config: dict[str, Any]) -> None:
    names = feature_names(config)
    by_block = {
        block: [str(name) for name in config["blocks"][block]["features"]]
        for block in ("L", "D", "R")
    }
    statuses = {name: text(row.get(f"{name}_status")) for name in names}
    for block, block_names in by_block.items():
        row[f"{block}_available_count"] = sum(
            statuses[name] == "available" for name in block_names
        )
    row["feature_available_count"] = sum(value == "available" for value in statuses.values())
    row["feature_missing_count"] = sum(value == "missing" for value in statuses.values())
    row["feature_ambiguous_count"] = sum(value == "ambiguous" for value in statuses.values())
    row["feature_not_computable_count"] = sum(
        value == "not_computable" for value in statuses.values()
    )
    near_zero_features = [
        name for name in names if truthy(row.get(f"{name}_near_zero_denominator_flag"))
    ]
    row["near_zero_denominator_count"] = len(near_zero_features)
    row["near_zero_denominator_features"] = ";".join(near_zero_features)

    if row.get("statement_scope_xbrl_status") == "not_available_non_xbrl":
        row["x_t_status"] = "not_available_non_xbrl"
        row["x_t_status_reason"] = text(row.get("statement_scope_xbrl_reason"))
    elif row.get("anchor_period_validation_status") == "hard_exclude":
        row["x_t_status"] = "hard_exclude_anchor_or_entity_context"
        row["x_t_status_reason"] = text(row.get("anchor_period_validation_reason"))
    elif row["L_available_count"] == len(by_block["L"]):
        row["x_t_status"] = "available_core"
        row["x_t_status_reason"] = "all_core_level_features_available"
    elif row["feature_available_count"] > 0:
        row["x_t_status"] = "partially_available"
        row["x_t_status_reason"] = "at_least_one_feature_available"
    elif row["feature_ambiguous_count"] > 0:
        row["x_t_status"] = "ambiguous"
        row["x_t_status_reason"] = "no_feature_available_and_ambiguity_present"
    else:
        row["x_t_status"] = "missing"
        row["x_t_status_reason"] = "no_feature_available"


def set_unavailable_features(
    row: dict[str, Any],
    config: dict[str, Any],
    status: str,
    reason: str,
) -> None:
    prediction_at = text(row.get("prediction_timestamp"))
    precision = text(row.get("prediction_timestamp_precision"))
    for block in ("L", "D", "R"):
        for name in config["blocks"][block]["features"]:
            add_feature(
                row,
                str(name),
                {
                    "value": None,
                    "status": status,
                    "reason": reason,
                    "block": block,
                    "available_at": prediction_at,
                    "available_at_precision": precision,
                    "source_primitives": "",
                    "source_roles": "",
                    "near_zero_denominator_flag": False,
                },
            )
    finalize_row_status(row, config)


def process_eligible_row(
    source: dict[str, Any],
    *,
    config: dict[str, Any],
    semantic_config: dict[str, Any],
    scope: semantic.Scope,
    accession_records: dict[str, list[dict[str, Any]]],
    period_ends: dict[tuple[str, int], date],
    companyfacts_relative_path: str,
    evidence_root: Path,
    negative_sign_review: dict[tuple[str, str, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row = initial_row(source, config)
    row["source_companyfacts_file"] = companyfacts_relative_path
    prediction_at = row["prediction_timestamp"]
    precision = row["prediction_timestamp_precision"]
    near_zero = float(config["denominators"]["near_zero_diagnostic_abs_usd"])

    scope_xbrl_status = text(source.get("statement_scope_xbrl_status"))
    if scope_xbrl_status == "not_available_non_xbrl":
        reason = text(source.get("statement_scope_xbrl_reason"))
        row["anchor_record_count"] = 0
        row["anchor_period_validation_status"] = "not_available_non_xbrl"
        row["anchor_period_validation_reason"] = reason
        row["comparative_period_end"] = ""
        row["comparative_period_source"] = ""
        row["comparative_period_gap_days"] = ""
        row["comparative_period_validation_status"] = "missing"
        row["comparative_period_validation_reason"] = reason
        add_empty_primitive_statuses(
            row,
            "not_available_non_xbrl",
            reason,
            prediction_at,
            precision,
        )
        set_unavailable_features(row, config, "not_available_non_xbrl", reason)
        return row
    if scope_xbrl_status != "available":
        reason = text(source.get("statement_scope_xbrl_reason")) or (
            "statement_scope_xbrl_availability_ambiguous"
        )
        row["anchor_record_count"] = 0
        row["anchor_period_validation_status"] = "ambiguous"
        row["anchor_period_validation_reason"] = reason
        row["comparative_period_end"] = ""
        row["comparative_period_source"] = ""
        row["comparative_period_gap_days"] = ""
        row["comparative_period_validation_status"] = "ambiguous"
        row["comparative_period_validation_reason"] = reason
        add_empty_primitive_statuses(
            row,
            "ambiguous",
            reason,
            prediction_at,
            precision,
        )
        set_unavailable_features(row, config, "ambiguous", reason)
        return row

    anchor, anchor_status, anchor_reason = exact_anchor(source, accession_records, scope)
    row["anchor_period_validation_status"] = anchor_status
    row["anchor_period_validation_reason"] = anchor_reason
    row["anchor_record_count"] = len(anchor["records"]) if anchor is not None else 0
    if anchor is None:
        row["comparative_period_end"] = ""
        row["comparative_period_source"] = ""
        row["comparative_period_gap_days"] = ""
        row["comparative_period_validation_status"] = anchor_status
        row["comparative_period_validation_reason"] = anchor_reason
        primitive_status = "ambiguous" if anchor_status == "ambiguous" else "missing"
        add_empty_primitive_statuses(
            row, primitive_status, anchor_reason, prediction_at, precision
        )
        set_unavailable_features(row, config, primitive_status, anchor_reason)
        return row

    row["anchor_xbrl_period_end"] = anchor["report_end"].isoformat()
    row["anchor_period_end_delta_days"] = anchor.get(
        "frozen_universe_period_end_delta_days", ""
    )

    cik10 = text(source["cik10"]).zfill(10)
    year = int(source["feature_year"])
    current_end = anchor["report_end"]
    previous_end = period_ends.get((cik10, year - 1))
    previous_source = "frozen_universe_prior_company_year"
    if previous_end is None:
        previous_end, previous_source = infer_comparative_end(anchor, current_end, scope)
    previous_previous_end = period_ends.get((cik10, year - 2))
    if previous_end is None:
        comparative_status = "missing"
        comparative_reason = "comparative_period_end_unresolved"
        gap_days: int | str = ""
    else:
        gap_days = (current_end - previous_end).days
        if scope.annual_period_min_days <= gap_days <= scope.annual_period_max_days:
            comparative_status = "available"
            comparative_reason = "annual_comparative_period_validated"
        else:
            comparative_status = "ambiguous"
            comparative_reason = "transition_or_nonannual_comparative_gap"
    row["comparative_period_end"] = previous_end.isoformat() if previous_end else ""
    row["comparative_period_source"] = previous_source
    row["comparative_period_gap_days"] = gap_days
    row["comparative_period_validation_status"] = comparative_status
    row["comparative_period_validation_reason"] = comparative_reason

    previous_anchor = {"report_end": previous_end} if previous_end else None
    previous_previous_anchor = (
        {"report_end": previous_previous_end} if previous_previous_end else None
    )
    cache_path = companyfacts_relative_path
    evidence_directory = (
        evidence_root / cik10 / text(source["accession"]).replace("-", "")
    )
    policies = semantic_config["primitive_concepts"]
    current_selections: dict[str, dict[str, Any]] = {}
    pair_selections: dict[str, dict[str, Any]] = {}

    for primitive in PRIMITIVES:
        if primitive == "revenues":
            current = resolve_revenue_current(
                policies[primitive], anchor, previous_end, evidence_directory, scope
            )
        else:
            current = semantic.select_primitive_single_period(
                primitive,
                policies[primitive],
                anchor,
                previous_anchor,
                scope,
            )
            current["role"] = "current_t"
        current = enrich_selection_source(current, anchor)
        current = selection_with_provenance(
            current,
            prediction_at=prediction_at,
            precision=precision,
            cache_path=cache_path,
            role="current_t",
        )
        review_key = (
            text(source.get("research_universe_company_year_id")),
            text(source.get("accession")),
            primitive,
        )
        review_decision = (negative_sign_review or {}).get(review_key)
        current = apply_negative_sign_review(current, review_decision)
        current_selections[primitive] = current
        add_provenance(row, f"current_t_{primitive}", current)

        if comparative_status != "available" or previous_anchor is None:
            pair_status = "ambiguous" if comparative_status == "ambiguous" else "missing"
            pair: dict[str, Any] = {
                "status": pair_status,
                "reason": comparative_reason,
            }
        else:
            pair = semantic.select_primitive_pair(
                primitive,
                policies[primitive],
                anchor,
                previous_anchor,
                previous_previous_anchor,
                scope,
                evidence_directory if primitive == "revenues" else None,
            )
        if review_decision is not None and review_decision["action"] == "ambiguous_na":
            pair = {
                "status": "ambiguous",
                "reason": current["reason"],
                "semantic_diagnostic": "manual_primary_statement_sign_review",
            }
        pair_selections[primitive] = pair
        for field in PAIR_FIELDS:
            row[f"pair_{primitive}_{field}"] = pair.get(field, "")
        if pair.get("status") == "selected":
            comparative = selection_with_provenance(
                enrich_selection_source(pair["comparative_t"], anchor),
                prediction_at=prediction_at,
                precision=precision,
                cache_path=cache_path,
                role="comparative_t_minus_1",
            )
            pair_current = selection_with_provenance(
                enrich_selection_source(pair["current_t1"], anchor),
                prediction_at=prediction_at,
                precision=precision,
                cache_path=cache_path,
                role="current_t",
            )
        else:
            comparative = selection_with_provenance(
                semantic.empty_selection(
                    str(pair.get("status", "missing")),
                    str(pair.get("reason", "pair_not_available")),
                ),
                prediction_at=prediction_at,
                precision=precision,
                cache_path=cache_path,
                role="comparative_t_minus_1",
            )
            pair_current = selection_with_provenance(
                semantic.empty_selection(
                    str(pair.get("status", "missing")),
                    str(pair.get("reason", "pair_not_available")),
                ),
                prediction_at=prediction_at,
                precision=precision,
                cache_path=cache_path,
                role="current_t",
            )
        pair["comparative_selection"] = comparative
        pair["current_selection"] = pair_current
        add_provenance(row, f"comparative_tm1_{primitive}", comparative)
        add_provenance(row, f"pair_current_t_{primitive}", pair_current)

    def current_value(primitive: str) -> float | None:
        selection = current_selections[primitive]
        return float(selection["value"]) if selection.get("status") == "selected" else None

    def pair_value(primitive: str, role: str) -> float | None:
        pair = pair_selections[primitive]
        selection = pair.get(role, {})
        return float(selection["value"]) if selection.get("status") == "selected" else None

    def pair_components(primitives: Iterable[str]) -> list[dict[str, Any]]:
        return [
            {
                "status": pair_selections[primitive].get("status", "missing"),
                "reason": pair_selections[primitive].get("reason", "pair_not_available"),
            }
            for primitive in primitives
        ]

    assets = current_value("assets")
    liabilities = current_value("liabilities")
    current_assets = current_value("current_assets")
    current_liabilities = current_value("current_liabilities")
    revenues = current_value("revenues")
    net_income = current_value("net_income")
    ocf = current_value("operating_cash_flow")
    positive = lambda value: value > 0

    level_specs: dict[str, dict[str, Any]] = {
        "log_assets_t": feature_result(
            block="L", selections=[current_selections["assets"]],
            source_primitives=["assets"], source_roles="current_t",
            prediction_at=prediction_at, precision=precision,
            formula=lambda: math.log(float(assets)),
            numerator_or_log_condition=lambda: assets is not None and assets > 0,
            near_zero=near_zero,
        ),
        "roa_t": feature_result(
            block="L", selections=[current_selections["net_income"], current_selections["assets"]],
            source_primitives=["net_income", "assets"], source_roles="current_t",
            prediction_at=prediction_at, precision=precision,
            formula=lambda: float(net_income) / float(assets),
            denominator_values=[("assets", assets)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "ocf_to_assets_t": feature_result(
            block="L", selections=[current_selections["operating_cash_flow"], current_selections["assets"]],
            source_primitives=["operating_cash_flow", "assets"], source_roles="current_t",
            prediction_at=prediction_at, precision=precision,
            formula=lambda: float(ocf) / float(assets),
            denominator_values=[("assets", assets)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "current_ratio_t": feature_result(
            block="L", selections=[current_selections["current_assets"], current_selections["current_liabilities"]],
            source_primitives=["current_assets", "current_liabilities"], source_roles="current_t",
            prediction_at=prediction_at, precision=precision,
            formula=lambda: float(current_assets) / float(current_liabilities),
            denominator_values=[("current_liabilities", current_liabilities)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "liabilities_to_assets_t": feature_result(
            block="L", selections=[current_selections["liabilities"], current_selections["assets"]],
            source_primitives=["liabilities", "assets"], source_roles="current_t",
            prediction_at=prediction_at, precision=precision,
            formula=lambda: float(liabilities) / float(assets),
            denominator_values=[("assets", assets)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "working_capital_to_assets_t": feature_result(
            block="L", selections=[current_selections["current_assets"], current_selections["current_liabilities"], current_selections["assets"]],
            source_primitives=["current_assets", "current_liabilities", "assets"], source_roles="current_t",
            prediction_at=prediction_at, precision=precision,
            formula=lambda: (float(current_assets) - float(current_liabilities)) / float(assets),
            denominator_values=[("assets", assets)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "accruals_to_assets_t": feature_result(
            block="L", selections=[current_selections["net_income"], current_selections["operating_cash_flow"], current_selections["assets"]],
            source_primitives=["net_income", "operating_cash_flow", "assets"], source_roles="current_t",
            prediction_at=prediction_at, precision=precision,
            formula=lambda: (float(net_income) - float(ocf)) / float(assets),
            denominator_values=[("assets", assets)], denominator_condition=positive,
            near_zero=near_zero,
        ),
    }

    pa = pair_value("assets", "current_t1")
    ppa = pair_value("assets", "comparative_t")
    pnl = pair_value("net_income", "current_t1")
    ppnl = pair_value("net_income", "comparative_t")
    pocf = pair_value("operating_cash_flow", "current_t1")
    ppocf = pair_value("operating_cash_flow", "comparative_t")
    pca = pair_value("current_assets", "current_t1")
    ppca = pair_value("current_assets", "comparative_t")
    pcl = pair_value("current_liabilities", "current_t1")
    ppcl = pair_value("current_liabilities", "comparative_t")
    pl = pair_value("liabilities", "current_t1")
    ppl = pair_value("liabilities", "comparative_t")
    pr = pair_value("revenues", "current_t1")
    ppr = pair_value("revenues", "comparative_t")

    dynamic_specs: dict[str, dict[str, Any]] = {
        "asset_growth_1y": feature_result(
            block="D", selections=pair_components(["assets"]), source_primitives=["assets"],
            source_roles="comparative_t_minus_1;current_t", prediction_at=prediction_at, precision=precision,
            formula=lambda: float(pa) / float(ppa) - 1.0,
            denominator_values=[("comparative_assets", ppa)], denominator_condition=positive,
            numerator_or_log_condition=lambda: pa is not None and pa > 0, near_zero=near_zero,
        ),
        "delta_roa_1y": feature_result(
            block="D", selections=pair_components(["net_income", "assets"]), source_primitives=["net_income", "assets"],
            source_roles="comparative_t_minus_1;current_t", prediction_at=prediction_at, precision=precision,
            formula=lambda: float(pnl) / float(pa) - float(ppnl) / float(ppa),
            denominator_values=[("current_assets", pa), ("comparative_assets", ppa)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "delta_ocf_to_assets_1y": feature_result(
            block="D", selections=pair_components(["operating_cash_flow", "assets"]), source_primitives=["operating_cash_flow", "assets"],
            source_roles="comparative_t_minus_1;current_t", prediction_at=prediction_at, precision=precision,
            formula=lambda: float(pocf) / float(pa) - float(ppocf) / float(ppa),
            denominator_values=[("current_assets", pa), ("comparative_assets", ppa)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "current_ratio_change_1y": feature_result(
            block="D", selections=pair_components(["current_assets", "current_liabilities"]), source_primitives=["current_assets", "current_liabilities"],
            source_roles="comparative_t_minus_1;current_t", prediction_at=prediction_at, precision=precision,
            formula=lambda: (float(pca) / float(pcl)) / (float(ppca) / float(ppcl)) - 1.0,
            denominator_values=[("current_current_liabilities", pcl), ("comparative_current_liabilities", ppcl), ("comparative_current_assets", ppca)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "delta_liabilities_to_assets_1y": feature_result(
            block="D", selections=pair_components(["liabilities", "assets"]), source_primitives=["liabilities", "assets"],
            source_roles="comparative_t_minus_1;current_t", prediction_at=prediction_at, precision=precision,
            formula=lambda: float(pl) / float(pa) - float(ppl) / float(ppa),
            denominator_values=[("current_assets", pa), ("comparative_assets", ppa)], denominator_condition=positive,
            near_zero=near_zero,
        ),
    }

    revenue_specs: dict[str, dict[str, Any]] = {
        "log1p_revenues_t": feature_result(
            block="R", selections=[current_selections["revenues"]], source_primitives=["revenues"],
            source_roles="current_t", prediction_at=prediction_at, precision=precision,
            formula=lambda: math.log1p(float(revenues)),
            numerator_or_log_condition=lambda: revenues is not None and revenues >= 0,
            near_zero=near_zero,
        ),
        "profit_margin_t": feature_result(
            block="R", selections=[current_selections["net_income"], current_selections["revenues"]], source_primitives=["net_income", "revenues"],
            source_roles="current_t", prediction_at=prediction_at, precision=precision,
            formula=lambda: float(net_income) / float(revenues),
            denominator_values=[("revenues", revenues)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "ocf_margin_t": feature_result(
            block="R", selections=[current_selections["operating_cash_flow"], current_selections["revenues"]], source_primitives=["operating_cash_flow", "revenues"],
            source_roles="current_t", prediction_at=prediction_at, precision=precision,
            formula=lambda: float(ocf) / float(revenues),
            denominator_values=[("revenues", revenues)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "asset_turnover_t": feature_result(
            block="R", selections=[current_selections["revenues"], current_selections["assets"]], source_primitives=["revenues", "assets"],
            source_roles="current_t", prediction_at=prediction_at, precision=precision,
            formula=lambda: float(revenues) / float(assets),
            denominator_values=[("assets", assets)], denominator_condition=positive,
            near_zero=near_zero,
        ),
        "revenue_growth_1y": feature_result(
            block="R", selections=pair_components(["revenues"]), source_primitives=["revenues"],
            source_roles="comparative_t_minus_1;current_t", prediction_at=prediction_at, precision=precision,
            formula=lambda: float(pr) / float(ppr) - 1.0,
            denominator_values=[("comparative_revenues", ppr)], denominator_condition=positive,
            numerator_or_log_condition=lambda: pr is not None and pr >= 0,
            near_zero=near_zero,
        ),
    }

    for name, result in {**level_specs, **dynamic_specs, **revenue_specs}.items():
        add_feature(row, name, result)
    finalize_row_status(row, config)
    return row


def process_company(
    item: tuple[str, list[dict[str, Any]]],
    *,
    config: dict[str, Any],
    semantic_config: dict[str, Any],
    scope: semantic.Scope,
    period_ends: dict[tuple[str, int], date],
    companyfacts_root: Path,
    evidence_root: Path,
    negative_sign_review: dict[tuple[str, str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    cik10, source_rows = item
    companyfacts_path = companyfacts_root / f"CIK{cik10}.json"
    relative_path = str(companyfacts_path.relative_to(BASE_DIR))
    facts_root: dict[str, Any] = {}
    if companyfacts_path.exists():
        try:
            payload = json.loads(companyfacts_path.read_text(encoding="utf-8"))
            facts_root = payload.get("facts", {}) if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Invalid Company Facts cache {relative_path}: {error}") from error
    accession_records = records_by_accession(facts_root, semantic_config, scope)
    for source in source_rows:
        accession = text(source.get("accession"))
        if accession in accession_records:
            continue
        instance_records = scope_xbrl_instance_records(
            source, semantic_config, scope
        )
        if instance_records:
            accession_records[accession].extend(instance_records)
    return [
        process_eligible_row(
            source,
            config=config,
            semantic_config=semantic_config,
            scope=scope,
            accession_records=accession_records,
            period_ends=period_ends,
            companyfacts_relative_path=relative_path,
            evidence_root=evidence_root,
            negative_sign_review=negative_sign_review,
        )
        for source in source_rows
    ]


def validate_raw_artifact(frame: pd.DataFrame, config: dict[str, Any]) -> None:
    expected_columns = output_columns(config)
    if list(frame.columns) != expected_columns:
        missing = sorted(set(expected_columns) - set(frame.columns))
        extra = sorted(set(frame.columns) - set(expected_columns))
        raise RuntimeError(f"Raw X_t schema mismatch; missing={missing}; extra={extra}")
    if len(frame) != 64_901:
        raise RuntimeError(f"Expected 64,901 raw X_t rows, got {len(frame):,}")
    if not frame["membership_status"].eq("eligible").all():
        raise RuntimeError("Raw X_t contains a non-eligible universe row")
    if frame.duplicated(["research_universe_company_year_id"]).any():
        raise RuntimeError("Raw X_t contains duplicate universe row identifiers")
    forbidden = [
        column
        for column in frame.columns
        if "target" in column.lower()
        or column.lower().startswith("d1_")
        or column.lower().startswith("d2_")
        or column.lower().startswith("d3_")
        or column.lower().startswith("d4_")
        or column.lower().startswith("d5_")
    ]
    if forbidden:
        raise RuntimeError(f"Target/provenance leakage columns in raw X_t: {forbidden}")
    if frame["feature_policy_id"].ne("x_t_pit").any():
        raise RuntimeError("Unexpected feature policy identifier")
    if frame["feature_policy_version"].astype(str).ne("1.0.0").any():
        raise RuntimeError("Unexpected feature policy version")
    scope_statuses = set(frame["statement_scope_xbrl_status"].astype(str))
    if not scope_statuses.issubset(
        {"available", "not_available_non_xbrl", "ambiguous"}
    ):
        raise RuntimeError(f"Unexpected statement-scope XBRL status: {scope_statuses}")

    for primitive in PRIMITIVES:
        for prefix in ("current_t", "comparative_tm1", "pair_current_t"):
            accn = frame[f"{prefix}_{primitive}_accn"].fillna("").astype(str)
            invalid = accn.ne("") & accn.ne(frame["anchor_accession"].fillna("").astype(str))
            if invalid.any():
                raise RuntimeError(
                    f"Exact-accession invariant failed for {prefix}_{primitive}: "
                    f"{int(invalid.sum()):,} rows"
                )
    non_xbrl = frame["statement_scope_xbrl_status"].eq(
        "not_available_non_xbrl"
    )
    if not frame.loc[non_xbrl, "x_t_status"].eq("not_available_non_xbrl").all():
        raise RuntimeError("Non-XBRL row-status invariant failed")
    feature_statuses = set(config["status_policy"]["feature_statuses"])
    for feature in feature_names(config):
        observed = set(frame[f"{feature}_status"].dropna().astype(str))
        if not observed.issubset(feature_statuses):
            raise RuntimeError(f"Unexpected status for {feature}: {sorted(observed - feature_statuses)}")
    validate_negative_sign_review_frame(frame, config)


def validate_negative_sign_review_frame(
    frame: pd.DataFrame,
    config: dict[str, Any],
) -> None:
    decisions = load_negative_sign_review(config)
    observed_keys: set[tuple[str, str, str]] = set()
    development = frame.loc[frame["feature_year"].between(2011, 2022)]
    for primitive in (
        "assets",
        "liabilities",
        "current_assets",
        "current_liabilities",
        "revenues",
    ):
        values = pd.to_numeric(
            development[f"current_t_{primitive}_value"], errors="coerce"
        )
        selected_negative = development.loc[
            development[f"current_t_{primitive}_status"].eq("selected")
            & values.lt(0)
        ]
        for row in selected_negative.itertuples(index=False):
            key = (
                str(row.research_universe_company_year_id),
                str(row.anchor_accession),
                primitive,
            )
            decision = decisions.get(key)
            if decision is None or decision["action"] != "retain":
                raise RuntimeError(f"Unreviewed selected negative primitive: {key}")
    indexed = frame.set_index("research_universe_company_year_id", drop=False)
    for key, decision in decisions.items():
        company_year_id, accession, primitive = key
        if company_year_id not in indexed.index:
            raise RuntimeError(f"Reviewed company-year absent from X_t: {key}")
        row = indexed.loc[company_year_id]
        if isinstance(row, pd.DataFrame):
            raise RuntimeError(f"Duplicate reviewed company-year in X_t: {key}")
        if str(row["anchor_accession"]) != accession:
            raise RuntimeError(f"Reviewed accession differs from X_t: {key}")
        observed_keys.add(key)
        status = str(row[f"current_t_{primitive}_status"])
        value = pd.to_numeric(
            pd.Series([row[f"current_t_{primitive}_value"]]), errors="coerce"
        ).iloc[0]
        if decision["action"] == "retain":
            if status != "selected" or pd.isna(value) or not math.isclose(
                float(value),
                float(decision["selected_value_before"]),
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise RuntimeError(f"Retained reviewed primitive changed: {key}")
            continue
        expected_reason = "manual_primary_statement_sign_review:" + str(
            decision["reason"]
        )
        if status != "ambiguous" or pd.notna(value):
            raise RuntimeError(f"Fail-closed reviewed primitive not ambiguous/NA: {key}")
        if str(row[f"current_t_{primitive}_reason"]) != expected_reason:
            raise RuntimeError(f"Unexpected fail-closed review reason: {key}")
        if str(row[f"pair_{primitive}_status"]) != "ambiguous":
            raise RuntimeError(f"Reviewed primitive pair remains usable: {key}")
        for feature in feature_names(config):
            sources = str(row[f"{feature}_source_primitives"]).split(";")
            if primitive not in sources:
                continue
            if str(row[f"{feature}_status"]) == "available" or pd.notna(
                pd.to_numeric(
                    pd.Series([row[f"{feature}_value"]]), errors="coerce"
                ).iloc[0]
            ):
                raise RuntimeError(
                    f"Dependent feature remains available after sign review: {key}; {feature}"
                )
    if observed_keys != set(decisions):
        raise RuntimeError("Not every negative-sign review decision was validated")


def validate_raw_artifact_path(
    path: Path,
    config: dict[str, Any],
    *,
    enforce_negative_sign_review: bool = True,
) -> int:
    expected_columns = output_columns(config)
    actual_columns = list(pd.read_csv(path, nrows=0).columns)
    if actual_columns != expected_columns:
        missing = sorted(set(expected_columns) - set(actual_columns))
        extra = sorted(set(actual_columns) - set(expected_columns))
        raise RuntimeError(f"Raw X_t schema mismatch; missing={missing}; extra={extra}")
    forbidden = [
        column
        for column in actual_columns
        if "target" in column.lower()
        or column.lower().startswith(("d1_", "d2_", "d3_", "d4_", "d5_"))
    ]
    if forbidden:
        raise RuntimeError(f"Target/provenance leakage columns in raw X_t: {forbidden}")

    validation_columns = list(METADATA_COLUMNS)
    for primitive in PRIMITIVES:
        validation_columns.extend(
            f"{prefix}_{primitive}_accn"
            for prefix in ("current_t", "comparative_tm1", "pair_current_t")
        )
    for feature in feature_names(config):
        validation_columns.append(f"{feature}_status")
    validation_columns.extend(["x_t_status"])
    for primitive in (
        "assets",
        "liabilities",
        "current_assets",
        "current_liabilities",
        "revenues",
    ):
        validation_columns.extend(
            [
                f"current_t_{primitive}_value",
                f"current_t_{primitive}_status",
                f"current_t_{primitive}_reason",
                f"pair_{primitive}_status",
            ]
        )
    for feature in feature_names(config):
        validation_columns.extend(
            [f"{feature}_value", f"{feature}_source_primitives"]
        )

    seen_ids: set[str] = set()
    row_count = 0
    reviewed_rows: list[pd.DataFrame] = []
    reviewed_ids = {
        key[0] for key in load_negative_sign_review(config)
    }
    for chunk in pd.read_csv(
        path,
        usecols=validation_columns,
        dtype=str,
        chunksize=5_000,
        keep_default_na=False,
        low_memory=False,
    ):
        if chunk["membership_status"].ne("eligible").any():
            raise RuntimeError("Raw X_t contains a non-eligible universe row")
        ids = chunk["research_universe_company_year_id"].astype(str)
        if ids.duplicated().any() or any(item in seen_ids for item in ids):
            raise RuntimeError("Raw X_t contains duplicate universe row identifiers")
        seen_ids.update(ids)
        if chunk["feature_policy_id"].ne("x_t_pit").any():
            raise RuntimeError("Unexpected feature policy identifier")
        if chunk["feature_policy_version"].ne("1.0.0").any():
            raise RuntimeError("Unexpected feature policy version")
        scope_statuses = set(chunk["statement_scope_xbrl_status"].astype(str))
        if not scope_statuses.issubset(
            {"available", "not_available_non_xbrl", "ambiguous"}
        ):
            raise RuntimeError(
                f"Unexpected statement-scope XBRL status: {scope_statuses}"
            )
        for primitive in PRIMITIVES:
            for prefix in ("current_t", "comparative_tm1", "pair_current_t"):
                accn = chunk[f"{prefix}_{primitive}_accn"]
                invalid = accn.ne("") & accn.ne(chunk["anchor_accession"])
                if invalid.any():
                    raise RuntimeError(
                        f"Exact-accession invariant failed for {prefix}_{primitive}: "
                        f"{int(invalid.sum()):,} rows in validation chunk"
                    )
        non_xbrl = chunk["statement_scope_xbrl_status"].eq(
            "not_available_non_xbrl"
        )
        if not chunk.loc[non_xbrl, "x_t_status"].eq("not_available_non_xbrl").all():
            raise RuntimeError("Non-XBRL row-status invariant failed")
        allowed = set(config["status_policy"]["feature_statuses"])
        for feature in feature_names(config):
            observed = set(chunk[f"{feature}_status"].astype(str))
            if not observed.issubset(allowed):
                raise RuntimeError(
                    f"Unexpected status for {feature}: {sorted(observed - allowed)}"
                )
        review_part = chunk.loc[
            chunk["research_universe_company_year_id"].isin(reviewed_ids)
        ]
        if not review_part.empty:
            reviewed_rows.append(review_part)
        row_count += len(chunk)
    if row_count != 64_901:
        raise RuntimeError(f"Expected 64,901 raw X_t rows, got {row_count:,}")
    if not enforce_negative_sign_review:
        return row_count
    if reviewed_rows:
        review_frame = pd.concat(reviewed_rows, ignore_index=True)
        review_frame["feature_year"] = pd.to_numeric(
            review_frame["feature_year"], errors="raise"
        ).astype(int)
        validate_negative_sign_review_frame(review_frame, config)
    else:
        raise RuntimeError("No negative-sign review rows found in raw X_t")
    return row_count


def write_build_manifest(
    config_path: Path = CONFIG_PATH,
    *,
    built_at_utc: str | None = None,
) -> dict[str, Any]:
    """Validate an existing raw artifact and write its reproducibility manifest."""

    config = load_config(config_path)
    frozen_hashes = verify_frozen_inputs(config)
    output_path = configured_path(config, "outputs", "raw_artifact")
    validated_rows = validate_raw_artifact_path(output_path, config)
    columns = output_columns(config)
    source_inventory_files = {
        key: {
            "path": str(configured_path(config, "sources", key).relative_to(BASE_DIR)),
            "sha256": sha256(configured_path(config, "sources", key)),
        }
        for key in (
            "companyfacts_download_inventory",
            "revenue_evidence_download_inventory",
            "x_t_source_download_inventory",
        )
    }
    review_files = {
        key: {
            "path": str(configured_path(config, "sources", key).relative_to(BASE_DIR)),
            "sha256": sha256(configured_path(config, "sources", key)),
        }
        for key in ("negative_sign_review", "negative_sign_evidence_inventory")
    }
    manifest = {
        "artifact_id": config["x_t"]["id"],
        "artifact_version": str(config["x_t"]["version"]),
        "status": config["x_t"]["status"],
        "built_at_utc": built_at_utc or datetime.now(tz=ZoneInfo("UTC")).isoformat(),
        "raw_artifact": str(output_path.relative_to(BASE_DIR)),
        "raw_artifact_rows": validated_rows,
        "raw_artifact_columns": len(columns),
        "raw_artifact_bytes": output_path.stat().st_size,
        "raw_artifact_sha256": sha256(output_path),
        "config_path": str(config_path.relative_to(BASE_DIR)),
        "config_sha256": sha256(config_path),
        "construction_code": "src/data/x_t_pit.py",
        "construction_code_sha256": sha256(BASE_DIR / "src/data/x_t_pit.py"),
        "semantic_resolver_code": "src/data/target_candidate_v2_pit.py",
        "semantic_resolver_code_sha256": sha256(
            BASE_DIR / "src/data/target_candidate_v2_pit.py"
        ),
        "revenue_resolver_code": "src/data/revenue_statement_resolver.py",
        "revenue_resolver_code_sha256": sha256(
            BASE_DIR / "src/data/revenue_statement_resolver.py"
        ),
        "primitive_policy_config": str(
            configured_path(config, "frozen_inputs", "primitive_policy_source").relative_to(
                BASE_DIR
            )
        ),
        "primitive_policy_config_sha256": sha256(
            configured_path(config, "frozen_inputs", "primitive_policy_source")
        ),
        "universe_artifact_sha256": frozen_hashes["universe_artifact_sha256"],
        "target_artifact_sha256": frozen_hashes["target_artifact_sha256"],
        "source_download_inventories": source_inventory_files,
        "negative_sign_validation": review_files,
        "eligible_rows_expected": 64_901,
        "feature_blocks": {
            block: list(config["blocks"][block]["features"])
            for block in ("L", "D", "R")
        },
        "preprocessing_applied": False,
        "models_trained": False,
        "test_used_for_policy_or_resolver_decisions": False,
    }
    manifest_path = configured_path(config, "outputs", "build_manifest")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def build_raw_x_t(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    frozen_hashes = verify_frozen_inputs(config)
    if frozen_hashes["universe_artifact_sha256"] != config["frozen_inputs"]["universe_sha256"]:
        raise RuntimeError("Frozen universe hash differs from X_t policy")
    if frozen_hashes["target_artifact_sha256"] != config["frozen_inputs"]["target_sha256"]:
        raise RuntimeError("Frozen target hash differs from X_t policy")

    semantic_config = semantic.load_config(
        configured_path(config, "frozen_inputs", "primitive_policy_source")
    )
    base_scope = semantic.parse_scope(semantic_config)
    pit = config["point_in_time"]
    scope = replace(
        base_scope,
        feature_year_start=int(config["x_t"]["feature_year_start"]),
        feature_year_end=int(config["x_t"]["feature_year_end"]),
        annual_period_min_days=int(pit["annual_period_min_days"]),
        annual_period_max_days=int(pit["annual_period_max_days"]),
        period_start_tolerance_days=int(pit["period_start_tolerance_days"]),
        minimum_denominator_usd=0.0,
    )
    eligible, period_ends = load_universe(config)
    companyfacts_root = configured_path(config, "sources", "companyfacts")
    evidence_root = configured_path(config, "sources", "revenue_statement_evidence")
    negative_sign_review = load_negative_sign_review(config)
    grouped: list[tuple[str, list[dict[str, Any]]]] = [
        (str(cik10), group.to_dict("records"))
        for cik10, group in eligible.groupby("cik10", sort=True)
    ]
    columns = output_columns(config)
    output_path = configured_path(config, "outputs", "raw_artifact")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    worker_count = max(1, int(os.environ.get("X_T_WORKERS", "8")))

    processed_rows = 0
    first_write = True
    buffer: list[dict[str, Any]] = []
    worker = lambda item: process_company(
        item,
        config=config,
        semantic_config=semantic_config,
        scope=scope,
        period_ends=period_ends,
        companyfacts_root=companyfacts_root,
        evidence_root=evidence_root,
        negative_sign_review=negative_sign_review,
    )
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        for company_rows in executor.map(worker, grouped):
            buffer.extend(company_rows)
            if len(buffer) < 500:
                continue
            chunk = pd.DataFrame(buffer).reindex(columns=columns)
            chunk.to_csv(
                temporary_path,
                mode="w" if first_write else "a",
                header=first_write,
                index=False,
                encoding="utf-8",
                lineterminator="\n",
                float_format="%.17g",
            )
            processed_rows += len(chunk)
            first_write = False
            buffer = []
    if buffer:
        chunk = pd.DataFrame(buffer).reindex(columns=columns)
        chunk.to_csv(
            temporary_path,
            mode="w" if first_write else "a",
            header=first_write,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
            float_format="%.17g",
        )
        processed_rows += len(chunk)
    if processed_rows != 64_901:
        raise RuntimeError(f"Build produced {processed_rows:,} rows instead of 64,901")
    temporary_path.replace(output_path)

    return write_build_manifest(config_path)

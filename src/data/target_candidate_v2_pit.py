"""Point-in-time extraction and validation for ``target_candidate_v2`` variant B.

The module intentionally does not feed the modeling pipeline.  It builds an
auditable target-vintage artifact from raw SEC Company Facts and submissions
metadata for feature years 2011--2022.  The target definition is fixed; this
layer only validates reporting-entity continuity, fiscal periods, semantic
concept consistency and provenance.

SEC Company Facts exposes filing-level ``fy`` and ``fp`` fields derived from
DocumentFiscalYearFocus and DocumentFiscalPeriodFocus.  Filing ``reportDate``
from submissions metadata is used as DocumentPeriodEndDate.  Company Facts is
lossy with respect to XBRL presentation roles and context identifiers, so
unresolved choices are marked ambiguous instead of being coerced to class 0.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml

from src.data.revenue_statement_resolver import (
    admissible_revenue_label,
    is_income_statement_metadata,
    resolve_primary_statement_revenue,
)


BASE_DIR = Path(__file__).resolve().parents[2]
COMPANYFACTS_DIR = BASE_DIR / "data" / "raw" / "companyfacts"
SUBMISSIONS_DIR = BASE_DIR / "data" / "raw" / "sec_submissions"
RESEARCH_UNIVERSE_PATH = BASE_DIR / "data" / "processed" / "research_universe.csv"
CONFIG_PATH = BASE_DIR / "configs" / "target_candidate_v2_pit.yaml"
REVENUE_STATEMENT_EVIDENCE_DIR = (
    BASE_DIR / "data" / "raw" / "sec_filings" / "revenue_statement_evidence"
)

OUTPUT_ROWS_PATH = BASE_DIR / "data" / "interim" / "target_candidate_v2_pit_b.csv"
OUTPUT_REVISIONS_PATH = BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_revision_deltas.csv"
OUTPUT_OUTLIERS_PATH = BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_revision_outliers.csv"
OUTPUT_SAMPLE_PATH = BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_manual_review_sample.csv"
OUTPUT_AUDIT_JSON_PATH = BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_audit.json"
OUTPUT_AUDIT_MD_PATH = BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_audit.md"

PRIMITIVES = (
    "assets",
    "liabilities",
    "current_assets",
    "current_liabilities",
    "revenues",
    "net_income",
    "operating_cash_flow",
)
FLOW_PRIMITIVES = {"revenues", "net_income", "operating_cash_flow"}
BALANCE_PRIMITIVES = {"assets", "liabilities", "current_assets", "current_liabilities"}
TARGET_SIGNALS = (
    "D1_roa",
    "D2_ocf_assets",
    "D3_current_ratio",
    "D4_liabilities_assets",
    "D5_revenues",
)


@dataclass(frozen=True)
class Scope:
    feature_year_start: int
    feature_year_end: int
    train_end_year: int
    validation_years: frozenset[int]
    allowed_forms: frozenset[str]
    annual_period_min_days: int
    annual_period_max_days: int
    period_start_tolerance_days: int
    minimum_denominator_usd: float


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config.get("primitive_concepts"), dict):
        raise ValueError(f"Missing primitive_concepts in {path}")
    return config


def parse_scope(config: dict[str, Any]) -> Scope:
    raw = config.get("scope", {})
    return Scope(
        feature_year_start=int(raw.get("feature_year_start", 2011)),
        feature_year_end=int(raw.get("feature_year_end", 2022)),
        train_end_year=int(raw.get("train_end_year", 2020)),
        validation_years=frozenset(int(value) for value in raw.get("validation_years", [2021, 2022])),
        allowed_forms=frozenset(str(value).upper() for value in raw.get("allowed_forms", ["10-K"])),
        annual_period_min_days=int(raw.get("annual_period_min_days", 300)),
        annual_period_max_days=int(raw.get("annual_period_max_days", 400)),
        period_start_tolerance_days=int(raw.get("period_start_tolerance_days", 14)),
        minimum_denominator_usd=float(raw.get("minimum_denominator_usd", 1_000.0)),
    )


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def safe_int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def normalize_cik10(value: Any) -> str:
    text = str(value).strip()
    if text.upper().startswith("CIK"):
        text = text[3:]
    if not text.isdigit() or len(text) > 10:
        raise ValueError(f"Invalid CIK: {value!r}")
    return text.zfill(10)


def split_for_year(year: int, scope: Scope) -> str:
    if year <= scope.train_end_year:
        return "train"
    if year in scope.validation_years:
        return "validation"
    return "out_of_scope"


def semicolon(values: Iterable[Any]) -> str:
    return ";".join(sorted({str(value) for value in values if str(value)}))


def required_tags(config: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for policy in config["primitive_concepts"].values():
        for strategy in policy.get("strategies", []):
            tags.update(str(tag) for tag in strategy.get("concepts", []))
            for key in ("minuend", "subtrahend"):
                if strategy.get(key):
                    tags.add(str(strategy[key]))
            tags.update(str(tag) for tag in strategy.get("requires_absent_concepts", []))
            tags.update(str(tag) for tag in strategy.get("requires_zero_or_absent_concepts", []))
        tags.update(str(tag) for tag in policy.get("prohibited_partial_concepts", []))
    return tags


def submission_metadata(cik10: str) -> dict[str, dict[str, Any]]:
    path = SUBMISSIONS_DIR / f"CIK{cik10}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, dict[str, Any]] = {}
    fields = {
        "form": "form",
        "filingDate": "filing_date",
        "reportDate": "report_date",
        "acceptanceDateTime": "accepted_at",
        "primaryDocument": "primary_document",
        "isXBRL": "is_xbrl",
    }

    def ingest(table: dict[str, Any]) -> None:
        accessions = table.get("accessionNumber", [])
        for index, accession in enumerate(accessions):
            item: dict[str, Any] = {}
            for source, target in fields.items():
                values = table.get(source, [])
                item[target] = values[index] if index < len(values) else ""
            result[str(accession)] = item

    ingest(payload.get("filings", {}).get("recent", {}))
    for shard in payload.get("filings", {}).get("files", []):
        shard_name = str(shard.get("name", "") or "")
        shard_path = SUBMISSIONS_DIR / shard_name
        if not shard_name or not shard_path.exists():
            continue
        try:
            shard_payload = json.loads(shard_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # Historical SEC submission shards expose the arrays at top level.
        # Accept the nested shape as well to keep the reader forward-compatible.
        ingest(shard_payload.get("filings", {}).get("recent", shard_payload))
    return result


def fact_record(tag: str, fact: dict[str, Any], scope: Scope) -> dict[str, Any] | None:
    form = str(fact.get("form", "") or "").upper()
    if form not in scope.allowed_forms:
        return None
    accession = str(fact.get("accn", "") or "")
    filed = parse_date(fact.get("filed"))
    end = parse_date(fact.get("end"))
    if not accession or filed is None or end is None:
        return None
    try:
        value = float(fact.get("val"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return {
        "tag": tag,
        "value": value,
        "accn": accession,
        "form": form,
        "filed": filed.isoformat(),
        "start": str(fact.get("start", "") or ""),
        "end": end.isoformat(),
        # Company Facts fy/fp are filing-focus metadata derived from the DEI
        # DocumentFiscalYearFocus and DocumentFiscalPeriodFocus facts.
        "document_fiscal_year_focus": safe_int(fact.get("fy")),
        "document_fiscal_period_focus": str(fact.get("fp", "") or ""),
        "frame": str(fact.get("frame", "") or ""),
    }


def annual_duration(record: dict[str, Any]) -> int | None:
    start = parse_date(record.get("start"))
    end = parse_date(record.get("end"))
    if start is None or end is None:
        return None
    return (end - start).days + 1


def record_supports_report_end(record: dict[str, Any], report_end: date, scope: Scope) -> bool:
    if parse_date(record.get("end")) != report_end:
        return False
    if record.get("document_fiscal_period_focus") != "FY":
        return False
    start = parse_date(record.get("start"))
    if start is None:
        return True
    duration = annual_duration(record)
    return duration is not None and scope.annual_period_min_days <= duration <= scope.annual_period_max_days


def choose_report_end(
    records: list[dict[str, Any]],
    submission_report_date: Any,
    scope: Scope,
) -> tuple[date | None, str]:
    # submissions.reportDate is the filing-level representation of
    # DocumentPeriodEndDate. It is accepted only when supported by a proper
    # annual/instant Company Facts context in the same accession.
    submitted = parse_date(submission_report_date)
    if submitted is not None and any(record_supports_report_end(record, submitted, scope) for record in records):
        return submitted, "submission_report_date_supported"

    supported_ends: list[date] = []
    for record in records:
        end = parse_date(record.get("end"))
        if end is not None and record_supports_report_end(record, end, scope):
            supported_ends.append(end)
    if not supported_ends:
        return None, "document_period_end_unresolved"
    return max(supported_ends), "inferred_from_annual_context"


def anchor_sort_key(anchor: dict[str, Any]) -> tuple[str, str, str]:
    accepted = str(anchor.get("accepted_at", "") or "")
    filed = str(anchor.get("filed", "") or "")
    return (accepted or f"{filed}T23:59:59Z", filed, str(anchor["accn"]))


def build_anchors(
    facts_root: dict[str, Any],
    submissions: dict[str, dict[str, Any]],
    config: dict[str, Any],
    scope: Scope,
) -> list[dict[str, Any]]:
    records_by_accession: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for tag in required_tags(config):
        units = facts_root.get("us-gaap", {}).get(tag, {}).get("units", {})
        for fact in units.get("USD", []) if isinstance(units, dict) else []:
            if not isinstance(fact, dict):
                continue
            record = fact_record(tag, fact, scope)
            if record is not None:
                records_by_accession[record["accn"]].append(record)

    anchors_by_end: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for accession, records in records_by_accession.items():
        submission = submissions.get(accession, {})
        if submission and str(submission.get("form", "")).upper() not in scope.allowed_forms:
            continue
        report_end, report_end_reason = choose_report_end(records, submission.get("report_date"), scope)
        if report_end is None:
            continue

        current_context_records = [
            record for record in records if record_supports_report_end(record, report_end, scope)
        ]
        fiscal_focus_counts = Counter(
            record["document_fiscal_year_focus"]
            for record in current_context_records
            if record.get("document_fiscal_year_focus") is not None
        )
        period_focus_counts = Counter(
            record["document_fiscal_period_focus"]
            for record in current_context_records
            if record.get("document_fiscal_period_focus")
        )
        fiscal_focus = fiscal_focus_counts.most_common(1)[0][0] if fiscal_focus_counts else None
        period_focus = period_focus_counts.most_common(1)[0][0] if period_focus_counts else ""
        filed_values = sorted({str(record.get("filed", "")) for record in records if record.get("filed")})
        filed = filed_values[0] if filed_values else str(submission.get("filing_date", "") or "")
        anchors_by_end[report_end].append(
            {
                "accn": accession,
                "records": records,
                "report_end": report_end,
                "document_period_end_date": report_end.isoformat(),
                "document_period_end_reason": report_end_reason,
                "document_fiscal_year_focus": fiscal_focus,
                "document_fiscal_period_focus": period_focus,
                "filed": filed,
                "accepted_at": str(submission.get("accepted_at", "") or ""),
                "primary_document": str(submission.get("primary_document", "") or ""),
            }
        )

    # Later filings can repeat an old report end. The anchor is the earliest
    # original 10-K whose own DocumentPeriodEndDate equals that report end.
    anchors = [sorted(candidates, key=anchor_sort_key)[0] for candidates in anchors_by_end.values()]
    anchors.sort(key=lambda anchor: (anchor["report_end"], anchor_sort_key(anchor)))
    return resolve_fiscal_year_sequence(anchors, scope)


def resolve_fiscal_year_sequence(anchors: list[dict[str, Any]], scope: Scope) -> list[dict[str, Any]]:
    """Resolve isolated erroneous/duplicate fiscal-focus years conservatively.

    Standard 52/53-week periods remain eligible.  When consecutive report ends
    are 300--400 days apart, resolved years must advance by one even if a filer
    duplicated DocumentFiscalYearFocus.  Nonannual gaps are never repaired.
    """

    previous: dict[str, Any] | None = None
    for anchor in anchors:
        focus = safe_int(anchor.get("document_fiscal_year_focus"))
        resolved = focus if focus is not None else anchor["report_end"].year
        reason = "document_fiscal_year_focus"
        if previous is not None:
            gap = (anchor["report_end"] - previous["report_end"]).days
            if scope.annual_period_min_days <= gap <= scope.annual_period_max_days:
                expected = int(previous["resolved_fiscal_year"]) + 1
                if resolved != expected:
                    resolved = expected
                    reason = "sequential_annual_context_adjustment"
        anchor["resolved_fiscal_year"] = int(resolved)
        anchor["resolved_fiscal_year_reason"] = reason
        previous = anchor

    counts = Counter(int(anchor["resolved_fiscal_year"]) for anchor in anchors)
    for anchor in anchors:
        anchor["resolved_fiscal_year_count"] = counts[int(anchor["resolved_fiscal_year"])]
    return anchors


def empty_selection(status: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, "value": None, **extra}


def select_tag_context(
    anchor: dict[str, Any],
    tag: str,
    expected_end: date,
    expected_start: date | None,
    period_type: str,
    scope: Scope,
    role: str,
) -> dict[str, Any]:
    tagged = [record for record in anchor["records"] if record["tag"] == tag]
    if not tagged:
        return empty_selection("missing", "concept_absent", tag=tag, role=role)

    end_matches = [record for record in tagged if parse_date(record.get("end")) == expected_end]
    if not end_matches:
        return empty_selection("missing", "expected_period_end_absent", tag=tag, role=role)

    fy_matches = [
        record for record in end_matches if record.get("document_fiscal_period_focus") == "FY"
    ]
    if not fy_matches:
        return empty_selection("ambiguous", "document_fiscal_period_focus_not_fy", tag=tag, role=role)

    candidates: list[dict[str, Any]] = []
    if period_type == "instant":
        candidates = [record for record in fy_matches if parse_date(record.get("start")) is None]
        if not candidates:
            return empty_selection("ambiguous", "instant_context_absent", tag=tag, role=role)
        score = lambda record: (0 if record.get("frame") else 1, str(record.get("frame", "")))
    elif period_type == "duration":
        for record in fy_matches:
            duration = annual_duration(record)
            if duration is None or not scope.annual_period_min_days <= duration <= scope.annual_period_max_days:
                continue
            start = parse_date(record.get("start"))
            start_distance = abs((start - expected_start).days) if start is not None and expected_start else 0
            candidates.append({**record, "duration_days": duration, "start_distance_days": start_distance})
        if not candidates:
            return empty_selection("ambiguous", "annual_duration_context_absent", tag=tag, role=role)
        if expected_start is not None:
            minimum_distance = min(int(record["start_distance_days"]) for record in candidates)
            if minimum_distance > scope.period_start_tolerance_days:
                return empty_selection(
                    "ambiguous",
                    "annual_period_start_outside_tolerance",
                    tag=tag,
                    role=role,
                    minimum_start_distance_days=minimum_distance,
                )
        score = lambda record: (
            int(record.get("start_distance_days", 0)),
            abs(int(record.get("duration_days", 365)) - 365),
            0 if record.get("frame") else 1,
            str(record.get("start", "")),
        )
    else:
        raise ValueError(f"Unknown period_type: {period_type}")

    candidates.sort(key=score)
    best_score = score(candidates[0])
    best = [record for record in candidates if score(record) == best_score]
    distinct_values = {float(record["value"]) for record in best}
    if len(distinct_values) != 1:
        return empty_selection(
            "ambiguous",
            "multiple_best_context_values",
            tag=tag,
            role=role,
            candidate_count=len(best),
        )

    record = best[0]
    return {
        "status": "selected",
        "reason": "exact_validated_context",
        "role": role,
        "value": float(record["value"]),
        "tag": tag,
        "strategy": "",
        "accn": anchor["accn"],
        "filed": anchor.get("filed", ""),
        "accepted_at": anchor.get("accepted_at", ""),
        "start": record.get("start", ""),
        "end": record.get("end", ""),
        "duration_days": annual_duration(record),
        "document_fiscal_year_focus": record.get("document_fiscal_year_focus"),
        "document_fiscal_period_focus": record.get("document_fiscal_period_focus", ""),
        "document_period_end_date": anchor.get("document_period_end_date", ""),
        "frame": record.get("frame", ""),
        "candidate_count": len(best),
    }


def select_strategy_role(
    anchor: dict[str, Any],
    strategy: dict[str, Any],
    expected_end: date,
    expected_start: date | None,
    period_type: str,
    scope: Scope,
    role: str,
) -> dict[str, Any]:
    strategy_name = str(strategy["name"])
    if strategy.get("derived") == "subtraction":
        minuend = select_tag_context(
            anchor,
            str(strategy["minuend"]),
            expected_end,
            expected_start,
            period_type,
            scope,
            role,
        )
        subtrahend = select_tag_context(
            anchor,
            str(strategy["subtrahend"]),
            expected_end,
            expected_start,
            period_type,
            scope,
            role,
        )
        if "ambiguous" in {minuend["status"], subtrahend["status"]}:
            return empty_selection(
                "ambiguous",
                "derived_component_ambiguous",
                role=role,
                strategy=strategy_name,
                component_reasons=semicolon([minuend.get("reason"), subtrahend.get("reason")]),
            )
        if "selected" not in {minuend["status"]} or "selected" not in {subtrahend["status"]}:
            return empty_selection(
                "missing",
                "derived_component_missing",
                role=role,
                strategy=strategy_name,
                component_reasons=semicolon([minuend.get("reason"), subtrahend.get("reason")]),
            )
        value = float(minuend["value"]) - float(subtrahend["value"])
        if value < 0:
            return empty_selection(
                "ambiguous",
                "derived_liabilities_negative",
                role=role,
                strategy=strategy_name,
            )
        return {
            **minuend,
            "value": value,
            "tag": f"derived:{strategy['minuend']}-{strategy['subtrahend']}",
            "strategy": strategy_name,
            "source_tags": f"{strategy['minuend']};{strategy['subtrahend']}",
            "source_values": f"{float(minuend['value'])};{float(subtrahend['value'])}",
            "source_accessions": f"{minuend['accn']};{subtrahend['accn']}",
            "source_starts": f"{minuend.get('start', '')};{subtrahend.get('start', '')}",
            "source_ends": f"{minuend.get('end', '')};{subtrahend.get('end', '')}",
            "reason": "validated_derived_strategy",
        }

    concepts = [str(tag) for tag in strategy.get("concepts", [])]
    if len(concepts) != 1:
        raise ValueError(f"Strategy {strategy_name} must define exactly one direct concept")
    selected = select_tag_context(
        anchor,
        concepts[0],
        expected_end,
        expected_start,
        period_type,
        scope,
        role,
    )
    selected["strategy"] = strategy_name
    return selected


def relative_difference(left: float, right: float, floor: float = 1_000.0) -> float:
    return abs(left - right) / max(abs(left), abs(right), floor)


def strategy_evaluations(
    policy: dict[str, Any],
    anchor: dict[str, Any],
    period_specs: dict[str, tuple[date, date | None]],
    scope: Scope,
) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    period_type = str(policy["period_type"])
    for strategy in sorted(policy.get("strategies", []), key=lambda item: int(item["priority"])):
        prohibited = {str(tag) for tag in strategy.get("requires_absent_concepts", [])}
        zero_or_absent = {
            str(tag) for tag in strategy.get("requires_zero_or_absent_concepts", [])
        }
        conflicting_roles: dict[str, str] = {}
        if prohibited:
            for role, (expected_end, _) in period_specs.items():
                for record in anchor["records"]:
                    if (
                        record.get("tag") in prohibited
                        and parse_date(record.get("end")) == expected_end
                        and record.get("document_fiscal_period_focus") == "FY"
                        and (
                            period_type == "instant"
                            or (
                                annual_duration(record) is not None
                                and scope.annual_period_min_days
                                <= int(annual_duration(record))
                                <= scope.annual_period_max_days
                            )
                        )
                    ):
                        conflicting_roles[role] = "partial_revenue_complement_present"
        if zero_or_absent:
            for role, (expected_end, _) in period_specs.items():
                for record in anchor["records"]:
                    if (
                        record.get("tag") in zero_or_absent
                        and parse_date(record.get("end")) == expected_end
                        and record.get("document_fiscal_period_focus") == "FY"
                        and abs(float(record.get("value", 0.0))) > 1e-12
                    ):
                        conflicting_roles[role] = "nonzero_nci_blocks_liabilities_fallback"
        roles = {}
        for role, (expected_end, expected_start) in period_specs.items():
            if role in conflicting_roles:
                roles[role] = empty_selection(
                    "ambiguous",
                    conflicting_roles[role],
                    role=role,
                    strategy=str(strategy["name"]),
                )
            else:
                roles[role] = select_strategy_role(
                    anchor,
                    strategy,
                    expected_end,
                    expected_start,
                    period_type,
                    scope,
                    role,
                )
        evaluations.append(
            {
                "name": str(strategy["name"]),
                "priority": int(strategy["priority"]),
                "equivalence_group": str(strategy.get("equivalence_group", "") or ""),
                "roles": roles,
            }
        )
    return evaluations


def semantic_disagreement(
    evaluations: list[dict[str, Any]],
    roles: tuple[str, ...],
    tolerance: float,
) -> bool:
    complete = [
        evaluation
        for evaluation in evaluations
        if all(evaluation["roles"][role]["status"] == "selected" for role in roles)
    ]
    for index, left in enumerate(complete):
        for right in complete[index + 1 :]:
            for role in roles:
                if relative_difference(
                    float(left["roles"][role]["value"]),
                    float(right["roles"][role]["value"]),
                ) > tolerance:
                    return True
    return False


def select_primitive_pair(
    primitive: str,
    policy: dict[str, Any],
    anchor_t1: dict[str, Any],
    anchor_t: dict[str, Any],
    anchor_tm1: dict[str, Any] | None,
    scope: Scope,
    revenue_evidence_directory: Path | None = None,
) -> dict[str, Any]:
    period_specs = {
        "comparative_t": (
            anchor_t["report_end"],
            anchor_tm1["report_end"] + timedelta(days=1) if anchor_tm1 else None,
        ),
        "current_t1": (anchor_t1["report_end"], anchor_t["report_end"] + timedelta(days=1)),
    }
    if primitive == "revenues":
        tag_to_strategy: dict[str, str] = {}
        tag_requirements: dict[str, set[str]] = {}
        for strategy in sorted(
            policy.get("strategies", []), key=lambda item: int(item["priority"])
        ):
            for tag in strategy.get("concepts", []):
                tag_to_strategy.setdefault(str(tag), str(strategy["name"]))
                tag_requirements.setdefault(str(tag), set()).update(
                    str(item) for item in strategy.get("requires_absent_concepts", [])
                )
        configured_tags = set(tag_to_strategy)
        target_ends = {anchor_t["report_end"], anchor_t1["report_end"]}
        relevant_records = [
            record
            for record in anchor_t1["records"]
            if record.get("tag") in configured_tags
            and parse_date(record.get("end"))
            in target_ends
        ]
        relevant_ends = {parse_date(record.get("end")) for record in relevant_records}
        if not target_ends.issubset(relevant_ends):
            return {
                "status": "missing",
                "reason": "primitive_not_reported_for_both_periods",
            }
        present_tags = {
            str(record.get("tag"))
            for record in anchor_t1["records"]
            if parse_date(record.get("end")) in target_ends
        }
        allowed_tags = {
            tag
            for tag in configured_tags
            if not (tag_requirements.get(tag, set()) & present_tags)
        }
        if not allowed_tags or not any(
            record.get("tag") in allowed_tags for record in relevant_records
        ):
            return {
                "status": "ambiguous",
                "reason": "component_revenue_without_absent_complement",
            }
        if revenue_evidence_directory is None or not (
            revenue_evidence_directory / "FilingSummary.xml"
        ).exists():
            return {
                "status": "ambiguous",
                "reason": "primary_statement_evidence_unavailable",
            }
        return resolve_primary_statement_revenue(
            directory=revenue_evidence_directory,
            anchor=anchor_t1,
            comparative_end=anchor_t["report_end"],
            comparative_start=(
                anchor_tm1["report_end"] + timedelta(days=1) if anchor_tm1 else None
            ),
            current_end=anchor_t1["report_end"],
            current_start=anchor_t["report_end"] + timedelta(days=1),
            allowed_tags=allowed_tags,
            tag_to_strategy={tag: tag_to_strategy[tag] for tag in allowed_tags},
            annual_min_days=scope.annual_period_min_days,
            annual_max_days=scope.annual_period_max_days,
            start_tolerance_days=scope.period_start_tolerance_days,
        )
    evaluations = strategy_evaluations(policy, anchor_t1, period_specs, scope)
    roles = ("comparative_t", "current_t1")
    complete = [
        evaluation
        for evaluation in evaluations
        if all(evaluation["roles"][role]["status"] == "selected" for role in roles)
    ]

    if complete:
        chosen = sorted(complete, key=lambda evaluation: evaluation["priority"])[0]
        blocking = [
            evaluation
            for evaluation in evaluations
            if evaluation["priority"] <= chosen["priority"]
            and any(evaluation["roles"][role]["status"] == "ambiguous" for role in roles)
        ]
        if blocking:
            return {
                "status": "ambiguous",
                "reason": "higher_priority_context_ambiguous",
                "candidate_strategies": semicolon(evaluation["name"] for evaluation in blocking),
            }
        result = {
            "status": "selected",
            "reason": "same_validated_strategy_both_periods",
            "strategy": chosen["name"],
            "comparative_t": chosen["roles"]["comparative_t"],
            "current_t1": chosen["roles"]["current_t1"],
        }
        if primitive == "revenues" and len(complete) > 1:
            tolerance = float(policy.get("material_concept_disagreement_ratio", 0.02))
            if semantic_disagreement(complete, roles, tolerance):
                result["semantic_diagnostic"] = "lower_priority_revenue_concepts_disagree"
                result["competing_strategies"] = semicolon(
                    evaluation["name"] for evaluation in complete if evaluation is not chosen
                )
        return result

    # Cross-tag use is permitted only for an explicit semantic equivalence
    # group and only when each role has exactly one unambiguous alternative.
    by_role: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for role in roles:
        by_role[role] = sorted(
            [
                (evaluation, evaluation["roles"][role])
                for evaluation in evaluations
                if evaluation["roles"][role]["status"] == "selected"
                and evaluation["equivalence_group"]
            ],
            key=lambda item: item[0]["priority"],
        )
    if by_role["comparative_t"] and by_role["current_t1"]:
        compatible = [
            (comp_eval, comp, curr_eval, curr)
            for comp_eval, comp in by_role["comparative_t"]
            for curr_eval, curr in by_role["current_t1"]
            if comp_eval["equivalence_group"] == curr_eval["equivalence_group"]
        ]
        if compatible:
            comp_eval, comp, curr_eval, curr = sorted(
                compatible,
                key=lambda item: (item[0]["priority"] + item[2]["priority"], item[0]["priority"], item[2]["priority"]),
            )[0]
            return {
                "status": "selected",
                "reason": "controlled_cross_tag_equivalence",
                "strategy": f"{comp_eval['name']}->{curr_eval['name']}",
                "comparative_t": comp,
                "current_t1": curr,
            }

    ambiguous_reasons = []
    for evaluation in evaluations:
        for role in roles:
            selection = evaluation["roles"][role]
            if selection["status"] == "ambiguous":
                ambiguous_reasons.append(selection.get("reason", ""))
    both_roles_have_selected = all(
        any(evaluation["roles"][role]["status"] == "selected" for evaluation in evaluations)
        for role in roles
    )
    if ambiguous_reasons or both_roles_have_selected:
        return {
            "status": "ambiguous",
            "reason": "no_common_semantic_strategy",
            "detail_reasons": semicolon(ambiguous_reasons),
        }
    return {"status": "missing", "reason": "primitive_not_reported_for_both_periods"}


def select_primitive_single_period(
    primitive: str,
    policy: dict[str, Any],
    anchor: dict[str, Any],
    previous_anchor: dict[str, Any] | None,
    scope: Scope,
) -> dict[str, Any]:
    specs = {
        "current": (
            anchor["report_end"],
            previous_anchor["report_end"] + timedelta(days=1) if previous_anchor else None,
        )
    }
    evaluations = strategy_evaluations(policy, anchor, specs, scope)
    selected = [
        evaluation for evaluation in evaluations if evaluation["roles"]["current"]["status"] == "selected"
    ]
    if selected:
        chosen = sorted(selected, key=lambda evaluation: evaluation["priority"])[0]
        result = dict(chosen["roles"]["current"])
        result["strategy"] = chosen["name"]
        if primitive == "revenues" and len(selected) > 1:
            tolerance = float(policy.get("material_concept_disagreement_ratio", 0.02))
            if semantic_disagreement(selected, ("current",), tolerance):
                result["semantic_diagnostic"] = "lower_priority_revenue_concepts_disagree"
                result["competing_strategies"] = semicolon(
                    evaluation["name"] for evaluation in selected if evaluation is not chosen
                )
        return result
    if any(
        evaluation["roles"]["current"]["status"] == "ambiguous" for evaluation in evaluations
    ):
        return empty_selection("ambiguous", "single_period_context_ambiguous")
    return empty_selection("missing", "single_period_primitive_missing")


def safe_ratio(numerator: float | None, denominator: float | None, minimum: float) -> float | None:
    if numerator is None or denominator is None or denominator <= minimum:
        return None
    return numerator / denominator


def target_metrics(values: dict[str, float | None], minimum: float) -> dict[str, float | None]:
    return {
        "roa": safe_ratio(values.get("net_income"), values.get("assets"), minimum),
        "ocf_to_assets": safe_ratio(values.get("operating_cash_flow"), values.get("assets"), minimum),
        "current_ratio": safe_ratio(
            values.get("current_assets"), values.get("current_liabilities"), minimum
        ),
        "liabilities_to_assets": safe_ratio(
            values.get("liabilities"), values.get("assets"), minimum
        ),
        "revenues": (
            values.get("revenues")
            if values.get("revenues") is not None and float(values["revenues"]) > minimum
            else None
        ),
    }


def target_candidate_v2(
    comparative_t: dict[str, float | None],
    current_t1: dict[str, float | None],
    minimum: float,
) -> tuple[dict[str, int | None], int | None, int | None, dict[str, float | None], dict[str, float | None]]:
    base = target_metrics(comparative_t, minimum)
    nxt = target_metrics(current_t1, minimum)
    signals: dict[str, int | None] = {}
    signals["D1_roa"] = (
        None if base["roa"] is None or nxt["roa"] is None else int(nxt["roa"] - base["roa"] <= -0.03)
    )
    signals["D2_ocf_assets"] = (
        None
        if base["ocf_to_assets"] is None or nxt["ocf_to_assets"] is None
        else int(nxt["ocf_to_assets"] - base["ocf_to_assets"] <= -0.03)
    )
    current_ratio_valid = (
        base["current_ratio"] is not None
        and nxt["current_ratio"] is not None
        and base["current_ratio"] > 0
        and nxt["current_ratio"] >= 0
    )
    signals["D3_current_ratio"] = (
        None if not current_ratio_valid else int(nxt["current_ratio"] / base["current_ratio"] <= 0.80)
    )
    signals["D4_liabilities_assets"] = (
        None
        if base["liabilities_to_assets"] is None or nxt["liabilities_to_assets"] is None
        else int(nxt["liabilities_to_assets"] - base["liabilities_to_assets"] >= 0.10)
    )
    signals["D5_revenues"] = (
        None
        if base["revenues"] is None or nxt["revenues"] is None
        else int(nxt["revenues"] / base["revenues"] - 1.0 <= -0.10)
    )
    if any(value is None for value in signals.values()):
        return signals, None, None, base, nxt
    score = sum(int(value) for value in signals.values())
    return signals, score, int(score >= 3), base, nxt


def confirmed_continuity_exclusion(
    cik10: str,
    feature_year: int,
    anchor_t1_accession: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    exclusions = config.get("reporting_entity_continuity", {}).get("confirmed_exclusions", [])
    for exclusion in exclusions:
        if (
            normalize_cik10(exclusion.get("cik10", "")) == cik10
            and int(exclusion.get("feature_year")) == feature_year
            and str(exclusion.get("anchor_t1_accession", "")) == anchor_t1_accession
        ):
            return exclusion
    return None


def continuity_ambiguity_screen(
    a_values: dict[str, float | None],
    b_values: dict[str, float | None],
    config: dict[str, Any],
    minimum: float,
) -> tuple[bool, list[str]]:
    rules = config.get("reporting_entity_continuity", {}).get("ambiguity_screen", {})
    balance_threshold = float(rules.get("balance_sheet_relative_change", 0.50))
    revenues_threshold = float(rules.get("revenues_relative_change", 0.50))
    income_threshold = float(rules.get("income_or_ocf_change_to_assets", 0.20))
    minimum_components = int(rules.get("minimum_material_components", 3))
    material: list[str] = []

    for primitive in BALANCE_PRIMITIVES:
        current = a_values.get(primitive)
        comparative = b_values.get(primitive)
        if current is None or comparative is None:
            continue
        if abs(comparative - current) / max(abs(current), minimum) > balance_threshold:
            material.append(primitive)

    if a_values.get("revenues") is not None and b_values.get("revenues") is not None:
        if abs(float(b_values["revenues"]) - float(a_values["revenues"])) / max(
            abs(float(a_values["revenues"])), minimum
        ) > revenues_threshold:
            material.append("revenues")

    asset_scale = a_values.get("assets")
    if asset_scale is not None and abs(asset_scale) > minimum:
        for primitive in ("net_income", "operating_cash_flow"):
            current = a_values.get(primitive)
            comparative = b_values.get(primitive)
            if current is None or comparative is None:
                continue
            if abs(comparative - current) / abs(asset_scale) > income_threshold:
                material.append(primitive)

    return len(set(material)) >= minimum_components, sorted(set(material))


def semantic_vintage_ambiguity_screen(
    first_release_values: dict[str, float | None],
    comparative_values: dict[str, float | None],
    config: dict[str, Any],
) -> list[str]:
    """Detect filer XBRL sign errors that Company Facts cannot disambiguate.

    A later comparative which is the exact opposite of the first-release
    signed amount is much more plausibly an XBRL sign/presentation error than a
    restatement to the same absolute value.  The rule only withholds the target;
    it never changes the value or assigns class zero.
    """

    policy = config.get("semantic_vintage_validation", {})
    tolerance = float(policy.get("sign_inversion_relative_tolerance", 1e-9))
    minimum = float(policy.get("minimum_absolute_value_usd", 1000.0))
    reasons: list[str] = []
    for primitive in policy.get("signed_primitives", []):
        current = first_release_values.get(str(primitive))
        comparative = comparative_values.get(str(primitive))
        if current is None or comparative is None:
            continue
        current = float(current)
        comparative = float(comparative)
        scale = max(abs(current), abs(comparative))
        if (
            scale >= minimum
            and current * comparative < 0
            and abs(abs(current) - abs(comparative)) / scale <= tolerance
        ):
            reasons.append(f"{primitive}:cross_vintage_exact_sign_inversion")
    return reasons


def provenance_columns(prefix: str, selection: dict[str, Any]) -> dict[str, Any]:
    keys = (
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
    )
    return {f"{prefix}_{key}": selection.get(key, "") for key in keys}


def anchor_columns(prefix: str, anchor: dict[str, Any] | None) -> dict[str, Any]:
    fields = (
        "accn",
        "filed",
        "accepted_at",
        "primary_document",
        "document_period_end_date",
        "document_period_end_reason",
        "document_fiscal_year_focus",
        "document_fiscal_period_focus",
        "resolved_fiscal_year",
        "resolved_fiscal_year_reason",
        "resolved_fiscal_year_count",
    )
    source = anchor or {}
    return {f"{prefix}_{field}": source.get(field, "") for field in fields}


def choose_year_anchor(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not candidates:
        return None
    # A duplicate resolved year is itself a hard-exclude. Keeping a stable
    # representative here only lets the audit retain complete provenance.
    return sorted(candidates, key=lambda anchor: (anchor["report_end"], anchor_sort_key(anchor)))[-1]


def process_company(
    company: dict[str, Any],
    config: dict[str, Any],
    scope: Scope,
) -> list[dict[str, Any]]:
    cik10 = normalize_cik10(company["cik10"])
    path = COMPANYFACTS_DIR / f"CIK{cik10}.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    anchors = build_anchors(payload.get("facts", {}), submission_metadata(cik10), config, scope)
    by_year: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for anchor in anchors:
        by_year[int(anchor["resolved_fiscal_year"])].append(anchor)

    policies = config["primitive_concepts"]
    output: list[dict[str, Any]] = []
    for feature_year in range(scope.feature_year_start, scope.feature_year_end + 1):
        anchor_t = choose_year_anchor(by_year.get(feature_year, []))
        if anchor_t is None:
            continue
        anchor_t1 = choose_year_anchor(by_year.get(feature_year + 1, []))
        anchor_tm1 = choose_year_anchor(by_year.get(feature_year - 1, []))
        row: dict[str, Any] = {
            "cik10": cik10,
            "company_name": company.get("company_name", ""),
            "primary_ticker": company.get("primary_ticker", ""),
            "research_sector": company.get("research_sector", ""),
            "sic": company.get("sic", ""),
            "sic_int": company.get("sic_int", ""),
            "sic_description": company.get("sic_description", ""),
            "sic_major_group": company.get("sic_major_group", ""),
            "feature_year": feature_year,
            "target_year": feature_year + 1,
            "split": split_for_year(feature_year, scope),
            **anchor_columns("anchor_t", anchor_t),
            **anchor_columns("anchor_t1", anchor_t1),
        }
        hard_reasons: list[str] = []
        ambiguous_reasons: list[str] = []
        missing_reasons: list[str] = []

        if len(by_year.get(feature_year, [])) != 1:
            hard_reasons.append("fiscal_period_ambiguous_multiple_anchor_t")
        if anchor_t1 is None:
            missing_reasons.append("anchor_t1_missing")
            row.update(
                {
                    "fiscal_period_gap_days": np.nan,
                    "hard_exclude_flag": False,
                    "hard_exclude_reasons": "",
                    "ambiguous_flag": False,
                    "ambiguous_reasons": "",
                    "missing_reasons": semicolon(missing_reasons),
                    "target_status": "missing",
                    "deterioration_score_1y": pd.NA,
                    "target_candidate_v2": pd.NA,
                }
            )
            output.append(row)
            continue

        if len(by_year.get(feature_year + 1, [])) != 1:
            hard_reasons.append("fiscal_period_ambiguous_multiple_anchor_t1")
        gap_days = (anchor_t1["report_end"] - anchor_t["report_end"]).days
        row["fiscal_period_gap_days"] = gap_days
        if not scope.annual_period_min_days <= gap_days <= scope.annual_period_max_days:
            hard_reasons.append("fiscal_period_transition_or_nonannual_gap")
        if anchor_t.get("document_fiscal_period_focus") != "FY":
            hard_reasons.append("anchor_t_document_fiscal_period_focus_not_fy")
        if anchor_t1.get("document_fiscal_period_focus") != "FY":
            hard_reasons.append("anchor_t1_document_fiscal_period_focus_not_fy")

        confirmed = confirmed_continuity_exclusion(cik10, feature_year, anchor_t1["accn"], config)
        if confirmed is not None:
            hard_reasons.append(str(confirmed["reason"]))
            row["reporting_entity_exclusion_evidence"] = confirmed.get("evidence", "")
        else:
            row["reporting_entity_exclusion_evidence"] = ""

        a_selections: dict[str, dict[str, Any]] = {}
        pair_selections: dict[str, dict[str, Any]] = {}
        a_values: dict[str, float | None] = {}
        comparative_values: dict[str, float | None] = {}
        current_values: dict[str, float | None] = {}
        for primitive in PRIMITIVES:
            a_selection = select_primitive_single_period(
                primitive,
                policies[primitive],
                anchor_t,
                anchor_tm1,
                scope,
            )
            a_selections[primitive] = a_selection
            a_values[primitive] = (
                float(a_selection["value"]) if a_selection.get("status") == "selected" else None
            )
            row.update(provenance_columns(f"A_current_t_{primitive}", a_selection))

            pair = select_primitive_pair(
                primitive,
                policies[primitive],
                anchor_t1,
                anchor_t,
                anchor_tm1,
                scope,
                (
                    REVENUE_STATEMENT_EVIDENCE_DIR
                    / cik10
                    / str(anchor_t1["accn"]).replace("-", "")
                    if primitive == "revenues"
                    else None
                ),
            )
            pair_selections[primitive] = pair
            row[f"B_{primitive}_status"] = pair.get("status", "")
            row[f"B_{primitive}_reason"] = pair.get("reason", "")
            row[f"B_{primitive}_strategy"] = pair.get("strategy", "")
            row[f"B_{primitive}_semantic_diagnostic"] = pair.get("semantic_diagnostic", "")
            row[f"B_{primitive}_competing_strategies"] = pair.get("competing_strategies", "")
            row[f"B_{primitive}_statement_candidate_count"] = pair.get(
                "statement_candidate_count", ""
            )
            row[f"B_{primitive}_statement_candidates_json"] = pair.get(
                "statement_candidates_json", ""
            )
            if pair.get("status") == "selected":
                comparative = pair["comparative_t"]
                current = pair["current_t1"]
                comparative_values[primitive] = float(comparative["value"])
                current_values[primitive] = float(current["value"])
                row.update(provenance_columns(f"B_comparative_t_{primitive}", comparative))
                row.update(provenance_columns(f"B_current_t1_{primitive}", current))
            else:
                comparative_values[primitive] = None
                current_values[primitive] = None
                if pair.get("status") == "ambiguous":
                    ambiguous_reasons.append(f"{primitive}:{pair.get('reason', 'ambiguous')}")
                else:
                    missing_reasons.append(f"{primitive}:{pair.get('reason', 'missing')}")

        continuity_ambiguous, material_components = continuity_ambiguity_screen(
            a_values,
            comparative_values,
            config,
            scope.minimum_denominator_usd,
        )
        row["reporting_entity_material_revision_components"] = semicolon(material_components)
        if confirmed is None and continuity_ambiguous:
            ambiguous_reasons.append("reporting_entity_continuity_material_rebasing_unresolved")

        sign_ambiguities = semantic_vintage_ambiguity_screen(a_values, comparative_values, config)
        ambiguous_reasons.extend(sign_ambiguities)
        row["semantic_vintage_ambiguity_reasons"] = semicolon(sign_ambiguities)

        signals, score, target, base_metrics, next_metrics = target_candidate_v2(
            comparative_values,
            current_values,
            scope.minimum_denominator_usd,
        )
        for signal, value in signals.items():
            row[signal] = value
        for metric, value in base_metrics.items():
            row[f"B_comparative_t_{metric}_metric"] = value
        for metric, value in next_metrics.items():
            row[f"B_current_t1_{metric}_metric"] = value

        if hard_reasons:
            target_status = "hard_exclude"
            score = None
            target = None
        elif ambiguous_reasons:
            target_status = "ambiguous"
            score = None
            target = None
        elif target is None:
            target_status = "missing"
        else:
            target_status = "available"

        row.update(
            {
                "hard_exclude_flag": bool(hard_reasons),
                "hard_exclude_reasons": semicolon(hard_reasons),
                "ambiguous_flag": bool(ambiguous_reasons),
                "ambiguous_reasons": semicolon(ambiguous_reasons),
                "missing_reasons": semicolon(missing_reasons),
                "target_status": target_status,
                "deterioration_score_1y": score,
                "target_candidate_v2": target,
            }
        )
        output.append(row)
    return output


def process_company_safe(
    company: dict[str, Any],
    config: dict[str, Any],
    scope: Scope,
) -> list[dict[str, Any]]:
    try:
        return process_company(company, config, scope)
    except Exception as error:  # pragma: no cover - surfaced as a fatal build error
        return [
            {
                "cik10": company.get("cik10", ""),
                "company_name": company.get("company_name", ""),
                "fatal_error": repr(error),
            }
        ]


def build_revision_deltas(rows: pd.DataFrame, scope: Scope) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    for _, row in rows.iterrows():
        base = {
            primitive: (
                float(row[f"A_current_t_{primitive}_value"])
                if pd.notna(row.get(f"A_current_t_{primitive}_value"))
                else None
            )
            for primitive in PRIMITIVES
        }
        comparative = {
            primitive: (
                float(row[f"B_comparative_t_{primitive}_value"])
                if pd.notna(row.get(f"B_comparative_t_{primitive}_value"))
                else None
            )
            for primitive in PRIMITIVES
        }
        common = {
            "cik10": row["cik10"],
            "company_name": row.get("company_name", ""),
            "feature_year": int(row["feature_year"]),
            "split": row.get("split", ""),
            "research_sector": row.get("research_sector", ""),
            "sic": row.get("sic", ""),
            "target_status": row.get("target_status", ""),
            "anchor_t_accession": row.get("anchor_t_accn", ""),
            "anchor_t1_accession": row.get("anchor_t1_accn", ""),
        }
        for primitive in PRIMITIVES:
            current = base[primitive]
            revised = comparative[primitive]
            if current is None or revised is None:
                continue
            delta = revised - current
            if primitive in {"net_income", "operating_cash_flow"}:
                scale = abs(base["assets"]) if base["assets"] is not None else None
            else:
                scale = abs(current)
            output.append(
                {
                    **common,
                    "kind": "primitive",
                    "variable": primitive,
                    "current_t_first_release": current,
                    "comparative_t_from_t1": revised,
                    "revision_delta": delta,
                    "scaled_revision_delta": (
                        delta / scale if scale is not None and scale > scope.minimum_denominator_usd else np.nan
                    ),
                    "current_tag": row.get(f"A_current_t_{primitive}_tag", ""),
                    "comparative_tag": row.get(f"B_comparative_t_{primitive}_tag", ""),
                }
            )

        base_metrics = target_metrics(base, scope.minimum_denominator_usd)
        comparative_metrics = target_metrics(comparative, scope.minimum_denominator_usd)
        for metric in ("roa", "ocf_to_assets", "current_ratio", "liabilities_to_assets", "revenues"):
            current = base_metrics[metric]
            revised = comparative_metrics[metric]
            if current is None or revised is None:
                continue
            delta = revised - current
            scaled = (
                delta / abs(current)
                if metric == "revenues" and abs(current) > scope.minimum_denominator_usd
                else delta
            )
            output.append(
                {
                    **common,
                    "kind": "metric",
                    "variable": metric,
                    "current_t_first_release": current,
                    "comparative_t_from_t1": revised,
                    "revision_delta": delta,
                    "scaled_revision_delta": scaled,
                    "current_tag": "",
                    "comparative_tag": "",
                }
            )
    return pd.DataFrame(output)


def reason_counts(frame: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for value in frame.get(column, pd.Series(dtype=str)).fillna(""):
        counter.update(reason for reason in str(value).split(";") if reason)
    return [
        {"reason": reason, "observation_count": int(count)}
        for reason, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def coverage_summary(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split, subset in [("all", frame), *[(name, frame[frame["split"].eq(name)]) for name in ("train", "validation")]]:
        denominator = len(subset)
        eligible = subset[~subset["hard_exclude_flag"].fillna(False)]
        row: dict[str, Any] = {
            "split": split,
            "candidate_rows": denominator,
            "hard_exclude_n": int(subset["hard_exclude_flag"].fillna(False).sum()),
            "ambiguous_n": int(subset["target_status"].eq("ambiguous").sum()),
            "available_target_n": int(subset["target_status"].eq("available").sum()),
            "target_coverage_all": (
                float(subset["target_status"].eq("available").mean()) if denominator else np.nan
            ),
            "target_coverage_after_hard_exclude": (
                float(eligible["target_status"].eq("available").mean()) if len(eligible) else np.nan
            ),
        }
        for signal in TARGET_SIGNALS:
            row[f"{signal}_coverage_all"] = float(subset[signal].notna().mean()) if denominator else np.nan
        rows.append(row)
    return rows


def class_balance(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for split, subset in [("all", frame), *[(name, frame[frame["split"].eq(name)]) for name in ("train", "validation")]]:
        available = subset[subset["target_status"].eq("available")]
        positives = int(pd.to_numeric(available["target_candidate_v2"], errors="coerce").eq(1).sum())
        rows.append(
            {
                "split": split,
                "available_n": int(len(available)),
                "positive_n": positives,
                "positive_rate": float(positives / len(available)) if len(available) else np.nan,
            }
        )
    return rows


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def provenance_integrity(
    frame: pd.DataFrame,
    config: dict[str, Any],
    scope: Scope,
) -> dict[str, Any]:
    """Check every selected B pair against the anchor and semantic policy.

    The extractor already applies these constraints during selection.  This
    second pass is deliberately redundant: it makes any accidental provenance,
    period or strategy regression visible in the audit artifact.
    """

    violations: Counter[str] = Counter()
    rows_with_violation: set[tuple[str, int]] = set()
    missing_anchor_filed_pairs = 0
    missing_anchor_accepted_pairs = 0
    selected_pairs = 0

    def flag(name: str, row: pd.Series) -> None:
        violations[name] += 1
        rows_with_violation.add((cell_text(row.get("cik10")), int(row["feature_year"])))

    for _, row in frame.iterrows():
        anchor_accession = cell_text(row.get("anchor_t1_accn"))
        anchor_t_end = cell_text(row.get("anchor_t_document_period_end_date"))
        anchor_t1_end = cell_text(row.get("anchor_t1_document_period_end_date"))
        anchor_filed = cell_text(row.get("anchor_t1_filed"))
        anchor_accepted = cell_text(row.get("anchor_t1_accepted_at"))

        for primitive in PRIMITIVES:
            if cell_text(row.get(f"B_{primitive}_status")) != "selected":
                continue
            selected_pairs += 1
            if not anchor_filed:
                missing_anchor_filed_pairs += 1
            if not anchor_accepted:
                missing_anchor_accepted_pairs += 1
            policy = config["primitive_concepts"][primitive]
            strategies = {
                str(strategy["name"]): strategy for strategy in policy.get("strategies", [])
            }
            role_strategies: dict[str, str] = {}

            for role, expected_role, expected_end in (
                ("comparative_t", "comparative_t", anchor_t_end),
                ("current_t1", "current_t1", anchor_t1_end),
            ):
                prefix = f"B_{role}_{primitive}"
                accession = cell_text(row.get(f"{prefix}_accn"))
                role_strategy = cell_text(row.get(f"{prefix}_strategy"))
                role_strategies[role] = role_strategy
                if not accession or accession != anchor_accession:
                    flag("accession_not_anchor_t1", row)
                if cell_text(row.get(f"{prefix}_end")) != expected_end:
                    flag(f"{role}_period_end_mismatch", row)
                if cell_text(row.get(f"{prefix}_role")) != expected_role:
                    flag(f"{role}_role_mismatch", row)
                if cell_text(row.get(f"{prefix}_document_fiscal_period_focus")) != "FY":
                    flag(f"{role}_document_fiscal_period_focus_not_fy", row)
                if cell_text(row.get(f"{prefix}_document_period_end_date")) != anchor_t1_end:
                    flag(f"{role}_document_period_end_not_anchor_t1", row)
                if cell_text(row.get(f"{prefix}_filed")) != anchor_filed:
                    flag(f"{role}_filed_not_anchor_t1", row)
                if cell_text(row.get(f"{prefix}_accepted_at")) != anchor_accepted:
                    flag(f"{role}_accepted_not_anchor_t1", row)
                if role_strategy not in strategies:
                    flag(f"{role}_strategy_not_allowed", row)

                source_accessions = [
                    value
                    for value in cell_text(row.get(f"{prefix}_source_accessions")).split(";")
                    if value
                ]
                if source_accessions and any(value != anchor_accession for value in source_accessions):
                    flag(f"{role}_derived_source_accession_not_anchor_t1", row)

                if policy["period_type"] == "instant":
                    if cell_text(row.get(f"{prefix}_start")):
                        flag(f"{role}_instant_has_start", row)
                else:
                    duration = pd.to_numeric(row.get(f"{prefix}_duration_days"), errors="coerce")
                    if pd.isna(duration) or not (
                        scope.annual_period_min_days
                        <= float(duration)
                        <= scope.annual_period_max_days
                    ):
                        flag(f"{role}_duration_not_annual", row)

                if primitive == "revenues":
                    if cell_text(row.get(f"{prefix}_reason")) != (
                        "primary_statement_consolidated_revenue_confirmed"
                    ):
                        flag(f"{role}_revenue_not_statement_confirmed", row)
                    statement_file = cell_text(row.get(f"{prefix}_statement_file"))
                    statement_label = cell_text(row.get(f"{prefix}_statement_label"))
                    statement_concepts = cell_text(
                        row.get(f"{prefix}_statement_concepts")
                    )
                    statement_metadata = {
                        "short_name": cell_text(
                            row.get(f"{prefix}_statement_short_name")
                        ),
                        "long_name": cell_text(
                            row.get(f"{prefix}_statement_long_name")
                        ),
                        "role": cell_text(row.get(f"{prefix}_statement_role_uri")),
                    }
                    if not statement_file:
                        flag(f"{role}_revenue_statement_file_missing", row)
                    if not admissible_revenue_label(statement_label):
                        flag(f"{role}_revenue_statement_label_not_admissible", row)
                    if statement_concepts != f"us-gaap:{cell_text(row.get(f'{prefix}_tag'))}":
                        flag(f"{role}_revenue_statement_concept_not_exact_tag", row)
                    candidate_count = pd.to_numeric(
                        row.get(f"{prefix}_statement_candidate_count"), errors="coerce"
                    )
                    if pd.isna(candidate_count) or int(candidate_count) != 1:
                        flag(f"{role}_revenue_statement_candidate_not_unique", row)
                    if not is_income_statement_metadata(statement_metadata):
                        flag(f"{role}_revenue_statement_role_not_income", row)

            comparative_strategy = strategies.get(role_strategies.get("comparative_t", ""), {})
            current_strategy = strategies.get(role_strategies.get("current_t1", ""), {})
            if role_strategies.get("comparative_t") != role_strategies.get("current_t1"):
                comparative_group = str(comparative_strategy.get("equivalence_group", "") or "")
                current_group = str(current_strategy.get("equivalence_group", "") or "")
                if not comparative_group or comparative_group != current_group:
                    flag("cross_tag_without_semantic_equivalence", row)
            if primitive == "revenues":
                for field in (
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
                ):
                    if cell_text(
                        row.get(f"B_comparative_t_revenues_{field}")
                    ) != cell_text(row.get(f"B_current_t1_revenues_{field}")):
                        flag(f"revenue_{field}_differs_between_roles", row)

    return {
        "selected_primitive_pairs_checked": int(selected_pairs),
        "rows_with_any_violation": int(len(rows_with_violation)),
        "violation_count": int(sum(violations.values())),
        "selected_pairs_missing_anchor_filed": int(missing_anchor_filed_pairs),
        "selected_pairs_missing_anchor_accepted_at": int(missing_anchor_accepted_pairs),
        "available_target_rows_missing_anchor_filed": int(
            (
                frame["target_status"].eq("available")
                & frame["anchor_t1_filed"].map(cell_text).eq("")
            ).sum()
        ),
        "available_target_rows_missing_anchor_accepted_at": int(
            (
                frame["target_status"].eq("available")
                & frame["anchor_t1_accepted_at"].map(cell_text).eq("")
            ).sum()
        ),
        "violations": [
            {"reason": reason, "count": int(count)}
            for reason, count in sorted(violations.items())
        ],
    }


def semantic_diagnostic_counts(frame: pd.DataFrame) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for primitive in PRIMITIVES:
        column = f"B_{primitive}_semantic_diagnostic"
        if column not in frame:
            continue
        for diagnostic in frame[column].fillna(""):
            if diagnostic:
                counter[f"{primitive}:{diagnostic}"] += 1
    return [
        {"diagnostic": diagnostic, "observation_count": int(count)}
        for diagnostic, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def revision_summary(revisions: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    remaining = revisions[revisions["target_status"].eq("available")]
    for (kind, variable), subset in remaining.groupby(["kind", "variable"], dropna=False):
        delta = pd.to_numeric(subset["revision_delta"], errors="coerce").dropna()
        scaled = pd.to_numeric(subset["scaled_revision_delta"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if delta.empty:
            continue
        row = {
            "kind": str(kind),
            "variable": str(variable),
            "n": int(len(delta)),
            "exact_zero_n": int(np.isclose(delta, 0.0, atol=1e-12).sum()),
            "exact_zero_rate": float(np.isclose(delta, 0.0, atol=1e-12).mean()),
        }
        for quantile in (0.0, 0.01, 0.05, 0.5, 0.95, 0.99, 1.0):
            label = f"q{int(quantile * 100):02d}"
            row[f"delta_{label}"] = float(delta.quantile(quantile))
            row[f"scaled_{label}"] = float(scaled.quantile(quantile)) if not scaled.empty else np.nan
        rows.append(row)
    return rows


def manual_review_sample(frame: pd.DataFrame, outliers: pd.DataFrame) -> pd.DataFrame:
    provenance = [
        "cik10",
        "company_name",
        "feature_year",
        "split",
        "target_status",
        "target_candidate_v2",
        "deterioration_score_1y",
        "anchor_t_accn",
        "anchor_t1_accn",
        "anchor_t1_primary_document",
        "hard_exclude_reasons",
        "ambiguous_reasons",
        "reporting_entity_material_revision_components",
    ]
    for primitive in PRIMITIVES:
        provenance.extend(
            [
                f"B_comparative_t_{primitive}_value",
                f"B_comparative_t_{primitive}_tag",
                f"B_comparative_t_{primitive}_start",
                f"B_comparative_t_{primitive}_end",
                f"B_current_t1_{primitive}_value",
                f"B_current_t1_{primitive}_tag",
                f"B_current_t1_{primitive}_start",
                f"B_current_t1_{primitive}_end",
            ]
        )
    provenance = [column for column in provenance if column in frame.columns]

    samples: list[pd.DataFrame] = []
    available = frame[frame["target_status"].eq("available")]
    if not available.empty:
        random_available = available.sample(min(20, len(available)), random_state=20260817).copy()
        random_available["review_basis"] = "deterministic_random_available"
        samples.append(random_available)
    ambiguous = frame[frame["target_status"].eq("ambiguous")]
    if not ambiguous.empty:
        random_ambiguous = ambiguous.sample(min(10, len(ambiguous)), random_state=20260818).copy()
        random_ambiguous["review_basis"] = "deterministic_random_ambiguous"
        samples.append(random_ambiguous)
    if not outliers.empty:
        keys = outliers[["cik10", "feature_year"]].drop_duplicates().head(20)
        largest = frame.merge(keys, on=["cik10", "feature_year"], how="inner").copy()
        largest["review_basis"] = "largest_remaining_revision_delta"
        samples.append(largest)
    if not samples:
        return pd.DataFrame(columns=[*provenance, "review_basis"])
    result = pd.concat(samples, ignore_index=True).drop_duplicates(
        ["cik10", "feature_year", "review_basis"]
    )
    return result[[*provenance, "review_basis"]]


def markdown_audit(audit: dict[str, Any]) -> str:
    lines = [
        "# Audyt semantic and period validation — target_candidate_v2, wariant B",
        "",
        "Status: wynik przed zamrożeniem targetu. Target nie został zamrożony i nie trenowano modeli.",
        "",
        "Zakres: train 2011–2020 i validation 2021–2022. Raport t+1 za 2023 jest używany wyłącznie jako źródło targetu dla feature year 2022.",
        "",
        "## Coverage",
        "",
        "| Split | Kandydaci | Hard-exclude | Ambiguous | Target dostępny | Coverage ogółem | Coverage po hard-exclude |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in audit["coverage"]:
        lines.append(
            f"| {row['split']} | {row['candidate_rows']:,} | {row['hard_exclude_n']:,} | "
            f"{row['ambiguous_n']:,} | {row['available_target_n']:,} | "
            f"{row['target_coverage_all']:.2%} | {row['target_coverage_after_hard_exclude']:.2%} |"
        )
    lines.extend(
        [
            "",
            "## Class balance",
            "",
            "| Split | N dostępne | Pozytywne | Udział pozytywnej |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in audit["class_balance"]:
        lines.append(
            f"| {row['split']} | {row['available_n']:,} | {row['positive_n']:,} | {row['positive_rate']:.2%} |"
        )
    lines.extend(["", "## Hard-exclude według przyczyny", ""])
    for row in audit["hard_exclude_reasons"]:
        lines.append(f"- {row['reason']}: {row['observation_count']:,}")
    lines.extend(["", "## Ambiguous według przyczyny", ""])
    for row in audit["ambiguous_reasons"]:
        lines.append(f"- {row['reason']}: {row['observation_count']:,}")
    provenance = audit["provenance_integrity"]
    lines.extend(
        [
            "",
            "## Integralność provenance i okresów",
            "",
            f"- sprawdzone pary primitive–okres: {provenance['selected_primitive_pairs_checked']:,}",
            f"- obserwacje z co najmniej jednym naruszeniem: {provenance['rows_with_any_violation']:,}",
            f"- łączna liczba naruszeń: {provenance['violation_count']:,}",
            f"- dostępne targety bez filed: {provenance['available_target_rows_missing_anchor_filed']:,}",
            f"- dostępne targety bez accepted_at: {provenance['available_target_rows_missing_anchor_accepted_at']:,}",
        ]
    )
    for row in provenance["violations"]:
        lines.append(f"- {row['reason']}: {row['count']:,}")
    lines.extend(
        [
            "",
            "Kontrola obejmuje zgodność accession z anchor t+1, role current/comparative, "
            "końce okresów, FY, roczny duration, filed/accepted timestamp, dozwoloną strategię "
            "semantyczną i provenance składników wartości pochodnych.",
            "Brak accepted_at oznacza, że lokalny główny plik SEC Submissions odsyła do "
            "niepobranego historycznego shardu. Timestamp nie jest imputowany; accession i filed "
            "pozostają zachowane.",
            "",
            "## Diagnostyki semantyczne (nie są automatycznie brakami)",
            "",
        ]
    )
    for row in audit["semantic_diagnostics"]:
        lines.append(f"- {row['diagnostic']}: {row['observation_count']:,}")
    lines.extend(
        [
            "",
            "## Revision deltas po walidacji (tylko target dostępny)",
            "",
            "| Rodzaj | Zmienna | N | Dokładnie 0 | Q01 scaled | Mediana scaled | Q99 scaled |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in audit["revision_summary_remaining_available"]:
        lines.append(
            f"| {row['kind']} | {row['variable']} | {row['n']:,} | "
            f"{row['exact_zero_rate']:.2%} | {row['scaled_q01']:.4g} | "
            f"{row['scaled_q50']:.4g} | {row['scaled_q99']:.4g} |"
        )
    lines.extend(
        [
            "",
            "## Artefakty audytu",
            "",
            f"- `{OUTPUT_ROWS_PATH.relative_to(BASE_DIR)}`",
            f"- `{OUTPUT_REVISIONS_PATH.relative_to(BASE_DIR)}`",
            f"- `{OUTPUT_OUTLIERS_PATH.relative_to(BASE_DIR)}`",
            f"- `{OUTPUT_SAMPLE_PATH.relative_to(BASE_DIR)}`",
            "",
            "Company Facts nie zawiera pełnego contextRef ani presentation role. Nierozstrzygnięte przypadki są dlatego oznaczane jako ambiguous/NA, a nie jako 0.",
            "",
        ]
    )
    return "\n".join(lines)


def build_target_candidate_v2_pit(
    config_path: Path = CONFIG_PATH,
    universe_path: Path = RESEARCH_UNIVERSE_PATH,
) -> dict[str, Any]:
    config = load_config(config_path)
    scope = parse_scope(config)
    universe = pd.read_csv(universe_path, dtype=str).fillna("")
    limit = int(os.environ.get("PIT_TARGET_LIMIT", "0"))
    if limit:
        universe = universe.head(limit)
    companies = universe.to_dict("records")
    workers = max(1, min(int(os.environ.get("PIT_TARGET_WORKERS", "4")), os.cpu_count() or 1))

    all_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = executor.map(
            lambda company: process_company_safe(company, config, scope),
            companies,
            chunksize=4,
        )
        for index, result in enumerate(results, start=1):
            all_rows.extend(result)
            if index % 100 == 0:
                print(f"PIT target progress: {index}/{len(companies)}", flush=True)

    frame = pd.DataFrame(all_rows)
    if "fatal_error" in frame.columns and frame["fatal_error"].notna().any():
        fatal = frame[frame["fatal_error"].notna()][["cik10", "company_name", "fatal_error"]]
        raise RuntimeError(f"Company parse failures:\n{fatal.to_string(index=False)}")
    if frame.empty:
        raise RuntimeError("No target rows were built")
    frame = frame.sort_values(["cik10", "feature_year"]).reset_index(drop=True)

    for path in (
        OUTPUT_ROWS_PATH,
        OUTPUT_REVISIONS_PATH,
        OUTPUT_OUTLIERS_PATH,
        OUTPUT_SAMPLE_PATH,
        OUTPUT_AUDIT_JSON_PATH,
        OUTPUT_AUDIT_MD_PATH,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT_ROWS_PATH, index=False)

    revisions = build_revision_deltas(frame, scope)
    revisions.to_csv(OUTPUT_REVISIONS_PATH, index=False)
    remaining = revisions[revisions["target_status"].eq("available")].copy()
    remaining["abs_scaled_revision_delta"] = pd.to_numeric(
        remaining["scaled_revision_delta"], errors="coerce"
    ).abs()
    outliers = (
        remaining.sort_values("abs_scaled_revision_delta", ascending=False)
        .groupby(["kind", "variable"], group_keys=False)
        .head(20)
    )
    outliers.to_csv(OUTPUT_OUTLIERS_PATH, index=False)
    manual_review_sample(frame, outliers).to_csv(OUTPUT_SAMPLE_PATH, index=False)

    audit = {
        "scope": {
            "feature_year_start": scope.feature_year_start,
            "feature_year_end": scope.feature_year_end,
            "test_2023_2024_used": False,
            "models_trained": False,
            "target_frozen": False,
        },
        "candidate_rows": int(len(frame)),
        "coverage": coverage_summary(frame),
        "class_balance": class_balance(frame),
        "hard_exclude_reasons": reason_counts(frame, "hard_exclude_reasons"),
        "ambiguous_reasons": reason_counts(frame, "ambiguous_reasons"),
        "semantic_diagnostics": semantic_diagnostic_counts(frame),
        "provenance_integrity": provenance_integrity(frame, config, scope),
        "revision_summary_remaining_available": revision_summary(revisions),
        "output_paths": [
            str(path.relative_to(BASE_DIR))
            for path in (
                OUTPUT_ROWS_PATH,
                OUTPUT_REVISIONS_PATH,
                OUTPUT_OUTLIERS_PATH,
                OUTPUT_SAMPLE_PATH,
            )
        ],
    }
    OUTPUT_AUDIT_JSON_PATH.write_text(json.dumps(audit, indent=2, allow_nan=False), encoding="utf-8")
    OUTPUT_AUDIT_MD_PATH.write_text(markdown_audit(audit), encoding="utf-8")
    return audit

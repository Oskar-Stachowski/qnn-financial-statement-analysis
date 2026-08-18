"""Fail-closed validation of consolidated annual revenue on SEC statements.

Company Facts is used for values and accession-level annual periods. SEC's
FilingSummary and rendered primary statement provide presentation membership,
filing labels and the statement row concept. A revenue pair is returned only
when both current and comparative values are confirmed on one admissible row
of a primary income/operations statement in the same accession.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any, Iterable
from xml.etree import ElementTree

import pandas as pd


INCOME_STATEMENT_POSITIVE = (
    "statementofincome",
    "statement of income",
    "statements of income",
    "statement of consolidated income",
    "statements of consolidated income",
    "statement of operations",
    "statements of operations",
    "statement of operation",
    "statements of operation",
    "statement of consolidated operations",
    "statements of consolidated operations",
    "consolidated results of operations",
    "statement of earnings",
    "statements of earnings",
    "statement of consolidated earnings",
    "statements of consolidated earnings",
    "statement of loss",
    "statements of loss",
    "statement of comprehensive operations",
    "statement of comprehensive income",
    "statements of comprehensive income",
    "statement of consolidated comprehensive income",
    "statements of consolidated comprehensive income",
    "statement of comprehensive loss",
    "statements of comprehensive loss",
    "statement of consolidated comprehensive loss",
    "statements of consolidated comprehensive loss",
    "statement of revenues and expenses",
    "statements of revenues and expenses",
)
INCOME_STATEMENT_NEGATIVE = (
    "parenthetical",
    "detail",
    "disaggregation",
    "segment",
    "note",
    "schedule",
    "pro forma",
    "supplemental",
    "supplementary",
    "unaudited",
)
PROHIBITED_REVENUE_LABEL_TERMS = (
    "unbilled",
    "deferred",
    "contract asset",
    "contract liability",
    "project revenue",
    "collaboration revenue",
    "segment revenue",
    "external customer",
    "license fee",
    "licence fee",
    "professional service",
    "engineering and support",
    "material sale",
    "artifact sale",
    "rental revenue",
    "construction material",
    "grant and rebate",
)
ADMISSIBLE_REVENUE_LABELS = (
    re.compile(r"^(total\s+)?(net\s+|operating\s+)?(sales|revenue|revenues)(,?\s*net)?$"),
    re.compile(r"^(total\s+)?(sales|revenue|revenues)\s+from\s+operations$"),
    re.compile(r"^(total\s+)?(net\s+)?(sales|revenue|revenues)\s+from\s+contracts\s+with\s+customers$"),
    re.compile(r"^(total\s+)?sales\s+and\s+(service|services)\s+revenues?$"),
    re.compile(r"^(total\s+)?product\s+and\s+(service|services)\s+revenues?$"),
    re.compile(r"^(total\s+)?(net\s+)?(sales|revenue|revenues)\s*[-–—,]\s*net$"),
    re.compile(r"^revenue\s+\(less agency commissions\)$"),
    re.compile(
        r"^revenue\s+from\s+contract\s+with\s+customer,?\s+"
        r"(including|excluding)\s+assessed\s+tax$"
    ),
    re.compile(r"^(total\s+)?service\s+revenues?\s+and\s+sales$"),
)


def normalized_space(value: str) -> str:
    return " ".join(str(value).replace("\xa0", " ").split())


def normalized_label(value: str) -> str:
    result = normalized_space(value).lower()
    result = re.sub(r"\[[^\]]+\]|\([^)]*note[^)]*\)", "", result)
    result = re.sub(r"^[\-–—:;,.\s]+|[\-–—:;,.\s]+$", "", result)
    return normalized_space(result)


def admissible_revenue_label(value: str) -> bool:
    label = normalized_label(value)
    if not label or any(term in label for term in PROHIBITED_REVENUE_LABEL_TERMS):
        return False
    return any(pattern.fullmatch(label) for pattern in ADMISSIBLE_REVENUE_LABELS)


def element_text(element: ElementTree.Element, name: str) -> str:
    child = element.find(f".//{name}")
    return "" if child is None or child.text is None else child.text.strip()


def is_income_statement_metadata(metadata: dict[str, str]) -> bool:
    combined = " ".join(metadata.values()).lower()
    if any(item in combined for item in INCOME_STATEMENT_NEGATIVE):
        return False
    if any(item in combined for item in INCOME_STATEMENT_POSITIVE):
        return True
    # Entity-defined role names frequently reverse the word order used by the
    # standard SEC labels (for example "Statements of Consolidated Operations"
    # or "Consolidated Results of Operations").  These token-level fallbacks
    # remain restricted to a statement role and explicitly avoid a standalone
    # comprehensive-income statement.
    statement_like = "statement" in combined or "results of" in combined
    if statement_like and "operations" in combined:
        return True
    if statement_like and "earnings" in combined:
        return True
    if statement_like and ("profit and loss" in combined or "profit or loss" in combined):
        return True
    return statement_like and "income" in combined


def income_statement_priority(metadata: dict[str, str]) -> int:
    """Prefer the operating/income statement over an OCI-only companion."""
    combined = " ".join(metadata.values()).lower()
    if "comprehensive" in combined and not any(
        item in combined for item in ("operations", "earnings", "profit", "statementofincome")
    ):
        return 1
    return 0


def filing_summary_reports(path: Path) -> list[dict[str, str]]:
    try:
        root = ElementTree.fromstring(path.read_bytes())
    except (ElementTree.ParseError, OSError):
        return []
    reports: list[dict[str, str]] = []
    for report in root.findall(".//Report"):
        metadata = {
            "html_file_name": element_text(report, "HtmlFileName"),
            "short_name": element_text(report, "ShortName"),
            "long_name": element_text(report, "LongName"),
            "role": element_text(report, "Role"),
            "menu_category": element_text(report, "MenuCategory"),
        }
        if metadata["html_file_name"] and is_income_statement_metadata(metadata):
            metadata["statement_priority"] = str(income_statement_priority(metadata))
            reports.append(metadata)
    unique: dict[str, dict[str, str]] = {}
    for report in reports:
        unique[report["html_file_name"]] = report
    reports = list(unique.values())
    if not reports:
        return []
    best_priority = min(int(report["statement_priority"]) for report in reports)
    return [
        report
        for report in reports
        if int(report["statement_priority"]) == best_priority
    ]


@dataclass
class Cell:
    kind: str
    css_class: str
    text: str
    concepts: tuple[str, ...]
    colspan: int


@dataclass
class HtmlRow:
    css_class: str
    cells: tuple[Cell, ...]


class ReportTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.report_table_depth = 0
        self.rows: list[HtmlRow] = []
        self.row_class = ""
        self.cells: list[Cell] | None = None
        self.cell_kind = ""
        self.cell_class = ""
        self.cell_text: list[str] = []
        self.cell_concepts: list[str] = []
        self.cell_colspan = 1
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): str(value or "") for key, value in attrs}
        lowered = tag.lower()
        if self.hidden_depth:
            self.hidden_depth += 1
            return
        if self.cell_kind and re.search(
            r"display\s*:\s*none", attributes.get("style", ""), flags=re.IGNORECASE
        ):
            self.hidden_depth = 1
            return
        if lowered == "table":
            if self.report_table_depth:
                self.report_table_depth += 1
            elif "report" in attributes.get("class", "").lower().split():
                self.report_table_depth = 1
            return
        if self.report_table_depth != 1:
            return
        if lowered == "tr":
            self.row_class = attributes.get("class", "")
            self.cells = []
        elif lowered in {"th", "td"} and self.cells is not None:
            self.cell_kind = lowered
            self.cell_class = attributes.get("class", "")
            self.cell_text = []
            self.cell_concepts = []
            try:
                self.cell_colspan = max(1, int(attributes.get("colspan", "1")))
            except ValueError:
                self.cell_colspan = 1
        elif lowered == "a" and self.cell_kind:
            match = re.search(r"defref_([A-Za-z0-9_-]+)", attributes.get("onclick", ""))
            if match:
                identifier = match.group(1)
                namespace, _, concept = identifier.partition("_")
                self.cell_concepts.append(f"{namespace}:{concept}" if concept else namespace)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self.hidden_depth:
            self.hidden_depth -= 1
            return
        if lowered == "table" and self.report_table_depth:
            self.report_table_depth -= 1
            return
        if self.report_table_depth != 1:
            return
        if lowered in {"th", "td"} and self.cells is not None and self.cell_kind:
            self.cells.append(
                Cell(
                    kind=self.cell_kind,
                    css_class=self.cell_class,
                    text=normalized_space(" ".join(self.cell_text)),
                    concepts=tuple(dict.fromkeys(self.cell_concepts)),
                    colspan=self.cell_colspan,
                )
            )
            self.cell_kind = ""
            self.cell_class = ""
            self.cell_text = []
            self.cell_concepts = []
            self.cell_colspan = 1
        elif lowered == "tr" and self.cells is not None:
            self.rows.append(HtmlRow(self.row_class, tuple(self.cells)))
            self.cells = None
            self.row_class = ""

    def handle_data(self, data: str) -> None:
        if self.report_table_depth == 1 and self.cell_kind:
            self.cell_text.append(data)


def parse_date_cell(value: str) -> date | None:
    cleaned = normalized_space(value)
    # Older SEC-rendered R-reports (especially filings generated in 2015)
    # commonly use ``Dec. 31, 2014`` and analogous dotted abbreviations.
    # pandas does not parse those consistently, which previously created the
    # artificial 2013 coverage collapse despite visible annual values.
    cleaned = re.sub(
        r"\b(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.",
        lambda match: "Sep" if match.group(1).lower() == "sept" else match.group(1),
        cleaned,
        flags=re.IGNORECASE,
    )
    if not re.search(r"\b(19|20)\d{2}\b", cleaned):
        return None
    parsed = pd.to_datetime(cleaned, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def monetary_scale(rows: Iterable[HtmlRow]) -> tuple[float, str]:
    # SEC-rendered statements frequently state both a monetary scale and a
    # separate share-count scale in their title.  Looking across every header
    # makes e.g. "USD ($) shares in Thousands" incorrectly multiply dollar
    # revenues by 1,000.  The left title cell is the only scale authority here;
    # share/per-share clauses are removed before interpreting the money scale.
    title = ""
    for row in rows:
        if row.cells and row.cells[0].kind == "th":
            candidate = normalized_space(row.cells[0].text)
            if candidate:
                title = candidate.lower()
                break
    monetary_text = re.sub(
        r"\b(?:share|shares|share data|shares data)\s+in\s+"
        r"(?:billions|millions|thousands)\b",
        "",
        title,
    )
    monetary_text = re.sub(
        r"\bper[ -]share(?: data)?\s+in\s+"
        r"(?:billions|millions|thousands)\b",
        "",
        monetary_text,
    )
    for word, scale in (
        ("billions", 1_000_000_000.0),
        ("millions", 1_000_000.0),
        ("thousands", 1_000.0),
    ):
        if re.search(rf"(?:\$\s*in|\bin)\s+{word}\b", monetary_text):
            return scale, word
    return 1.0, "units"


def parse_amount(value: str, scale: float) -> float | None:
    cleaned = normalized_space(value)
    if not cleaned or cleaned in {"-", "—", "–"}:
        return None
    # Footnote markers are presentation metadata, not part of the number.
    cleaned = re.sub(r"\[\s*\d+[A-Za-z]?\s*\]", "", cleaned)
    amount_match = re.search(
        r"(?P<currency>\$\s*)?(?P<parenthesized>\(\s*)?"
        r"(?P<number>-?\s*\d[\d,]*(?:\.\d+)?)\s*\)?",
        cleaned,
    )
    if amount_match is None:
        return None
    negative = bool(amount_match.group("parenthesized"))
    numeric = amount_match.group("number").replace(",", "").replace(" ", "")
    try:
        amount = float(numeric) * scale
    except ValueError:
        return None
    return -abs(amount) if negative else amount


def report_rows(path: Path, metadata: dict[str, str]) -> list[dict[str, Any]]:
    parser = ReportTableParser()
    try:
        parser.feed(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return []
    scale, scale_label = monetary_scale(parser.rows)
    date_rows: list[tuple[HtmlRow, list[date]]] = []
    for row in parser.rows:
        parsed = [parse_date_cell(cell.text) for cell in row.cells]
        dates = [item for item in parsed if item is not None]
        if dates:
            date_rows.append((row, dates))
    if not date_rows:
        return []
    period_row, periods = max(date_rows, key=lambda item: len(item[1]))
    period_spans: list[tuple[date, int, int]] = []
    column = 0
    for cell in period_row.cells:
        width = max(1, cell.colspan)
        parsed_date = parse_date_cell(cell.text)
        if parsed_date is not None:
            period_spans.append((parsed_date, column, column + width))
        column += width
    period_date_counts = Counter(period for period, _, _ in period_spans)
    output: list[dict[str, Any]] = []
    for row in parser.rows:
        if not row.cells or row.cells[0].kind != "td":
            continue
        label_cell = row.cells[0]
        concepts = tuple(
            dict.fromkeys(
                concept for cell in row.cells for concept in cell.concepts
            )
        )
        if not concepts:
            continue
        numeric_spans: list[tuple[int, int, Cell]] = []
        column = 0
        for cell in row.cells[1:]:
            width = max(1, cell.colspan)
            numeric_spans.append((column, column + width, cell))
            column += width
        # A common SEC R-report layout has a title header with ``rowspan=2``
        # and ``colspan=2``.  The second header row therefore contains only
        # the date cells, while each data row contains an extra footnote cell
        # between the label and the monetary values.  A flat HTML-row parser
        # cannot infer the occupied columns from the preceding rowspan and a
        # span-only mapping shifts every amount by one year.  When the row has
        # exactly one explicitly numeric presentation cell per (unique) date,
        # ordered alignment is unambiguous and is safer than reconstructing a
        # browser table grid.  Rows with repeated dates/dimensions still fail
        # closed below.
        presentation_value_cells = [
            cell
            for cell in row.cells[1:]
            if any(
                token.lower().startswith("num")
                for token in cell.css_class.split()
            )
        ]
        ordered_amounts: dict[str, float | None] | None = None
        if (
            len(presentation_value_cells) == len(period_spans)
            and all(count == 1 for count in period_date_counts.values())
        ):
            ordered_amounts = {
                period.isoformat(): parse_amount(cell.text, scale)
                for (period, _, _), cell in zip(
                    period_spans, presentation_value_cells, strict=True
                )
            }
        amounts: dict[str, float | None] = {}
        for period, start_column, end_column in period_spans:
            # Repeated dates normally indicate dimension/segment columns.  The
            # rendered table does not expose enough context here to identify a
            # consolidated column safely, so the date is deliberately unusable.
            if period_date_counts[period] != 1:
                amounts[period.isoformat()] = None
                continue
            if ordered_amounts is not None:
                amounts[period.isoformat()] = ordered_amounts[period.isoformat()]
                continue
            period_amounts = [
                amount
                for cell_start, cell_end, cell in numeric_spans
                if cell_start < end_column and cell_end > start_column
                for amount in [parse_amount(cell.text, scale)]
                if amount is not None
            ]
            unique_amounts = list(dict.fromkeys(period_amounts))
            amounts[period.isoformat()] = (
                unique_amounts[0] if len(unique_amounts) == 1 else None
            )
        output.append(
            {
                **metadata,
                "statement_file": path.name,
                "statement_label": label_cell.text,
                "statement_label_normalized": normalized_label(label_cell.text),
                "statement_row_class": row.css_class,
                "statement_scale": scale,
                "statement_scale_label": scale_label,
                "statement_concepts": ";".join(concepts),
                "amounts": amounts,
            }
        )
    return output


def evidence_rows(directory: Path) -> list[dict[str, Any]]:
    reports = filing_summary_reports(directory / "FilingSummary.xml")
    rows: list[dict[str, Any]] = []
    for report in reports:
        rows.extend(report_rows(directory / report["html_file_name"], report))
    return rows


def amount_equal(left: float, right: float, scale: float) -> bool:
    tolerance = max(1.0, scale * 0.51, abs(right) * 1e-9)
    return abs(left - right) <= tolerance


def economic_revenue_line(row: dict[str, Any]) -> bool:
    """Return whether a primary-statement row can be a revenue complement.

    This screen is intentionally broader than the admissible-total screen.  A
    product, licensing, royalty, or financial-services revenue row must be
    visible to the complement check even though it can never be selected as a
    consolidated total on its own.
    """
    label = normalized_label(str(row.get("statement_label", "")))
    concepts = [
        concept.split(":", 1)[-1].lower()
        for concept in str(row.get("statement_concepts", "")).split(";")
        if concept
    ]
    if not label or any(
        term in label
        for term in (
            "cost of",
            "costs of",
            "expense",
            "marketing",
            "selling",
            "deferred revenue",
            "unearned revenue",
            "contract asset",
            "contract liability",
        )
    ):
        return False
    economic_concepts = [
        concept
        for concept in concepts
        if not any(
            term in concept
            for term in (
                "abstract",
                "cost",
                "expense",
                "deferred",
                "unearned",
                "contractasset",
                "contractliability",
            )
        )
        and ("revenue" in concept or "sales" in concept)
    ]
    return bool(economic_concepts) and bool(
        re.search(r"\b(revenue|revenues|sales)\b", label)
    )


def alternate_gross_net_revenue_basis(
    chosen: dict[str, Any], other: dict[str, Any]
) -> bool:
    """Recognise a disclosed gross-tax basis next to the selected net basis."""
    chosen_label = normalized_label(str(chosen.get("statement_label", "")))
    other_label = normalized_label(str(other.get("statement_label", "")))
    chosen_is_net = "net" in chosen_label or "excluding assessed tax" in chosen_label
    other_is_gross_tax = any(
        phrase in other_label
        for phrase in (
            "including excise tax",
            "including excise taxes",
            "including assessed tax",
            "before excise tax",
            "before excise taxes",
        )
    )
    return chosen_is_net and other_is_gross_tax


def matching_annual_fact(
    records: list[dict[str, Any]],
    tag: str,
    expected_end: date,
    expected_start: date | None,
    expected_value: float,
    annual_min_days: int,
    annual_max_days: int,
    start_tolerance_days: int,
    scale: float,
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for record in records:
        if record.get("tag") != tag or record.get("end") != expected_end.isoformat():
            continue
        if record.get("document_fiscal_period_focus") != "FY":
            continue
        try:
            start = date.fromisoformat(str(record.get("start", "")))
        except ValueError:
            continue
        duration = (expected_end - start).days + 1
        if not annual_min_days <= duration <= annual_max_days:
            continue
        if expected_start is not None and abs((start - expected_start).days) > start_tolerance_days:
            continue
        if amount_equal(float(record["value"]), expected_value, scale):
            matches.append({**record, "duration_days": duration})
    if not matches:
        return None
    matches.sort(
        key=lambda item: (
            0 if item.get("frame") else 1,
            abs(int(item["duration_days"]) - 365),
            str(item.get("start", "")),
        )
    )
    return matches[0]


def resolve_primary_statement_revenue(
    *,
    directory: Path,
    anchor: dict[str, Any],
    comparative_end: date,
    comparative_start: date | None,
    current_end: date,
    current_start: date | None,
    allowed_tags: set[str],
    tag_to_strategy: dict[str, str],
    annual_min_days: int,
    annual_max_days: int,
    start_tolerance_days: int,
) -> dict[str, Any]:
    rows = evidence_rows(directory)
    plausible_rows: list[dict[str, Any]] = []
    for row in rows:
        if not admissible_revenue_label(row["statement_label"]):
            continue
        full_concepts = [
            concept
            for concept in str(row.get("statement_concepts", "")).split(";")
            if concept
        ]
        # FilingSummary statements often contain a section-heading row such as
        # ``Revenues`` tagged only with ``RevenuesAbstract``.  It is not an
        # economic line item.  Every other admissible row must participate in
        # the uniqueness test even when one exact annual value did not parse:
        # otherwise a hidden/custom total could be silently ignored in favour
        # of a component-like standard-tag row.
        if full_concepts and all(
            concept.split(":", 1)[-1].endswith("Abstract")
            for concept in full_concepts
        ):
            continue
        comparative_value = row["amounts"].get(comparative_end.isoformat())
        current_value = row["amounts"].get(current_end.isoformat())
        plausible_rows.append(
            {
                "comparative_value": (
                    float(comparative_value) if comparative_value is not None else None
                ),
                "current_value": float(current_value) if current_value is not None else None,
                **{key: value for key, value in row.items() if key != "amounts"},
            }
        )

    if plausible_rows:
        best_statement_priority = min(
            int(row.get("statement_priority", 0)) for row in plausible_rows
        )
        plausible_rows = [
            row
            for row in plausible_rows
            if int(row.get("statement_priority", 0)) == best_statement_priority
        ]
    unique_rows: dict[
        tuple[str, str, str, float | None, float | None], dict[str, Any]
    ] = {}
    for row in plausible_rows:
        key = (
            row["statement_file"],
            row["statement_label_normalized"],
            row["statement_concepts"],
            row["comparative_value"],
            row["current_value"],
        )
        unique_rows[key] = row
    plausible_rows = list(unique_rows.values())

    def candidate_provenance(items: list[dict[str, Any]]) -> str:
        return json.dumps(
            [
                {
                    "statement_file": item.get("statement_file", ""),
                    "short_name": item.get("short_name", ""),
                    "long_name": item.get("long_name", ""),
                    "role": item.get("role", ""),
                    "label": item.get("statement_label", ""),
                    "concepts": item.get("statement_concepts", ""),
                    "row_class": item.get("statement_row_class", ""),
                    "scale": item.get("statement_scale", ""),
                    "scale_label": item.get("statement_scale_label", ""),
                    "statement_priority": item.get("statement_priority", ""),
                    "comparative_end": comparative_end.isoformat(),
                    "comparative_value": item.get("comparative_value"),
                    "current_end": current_end.isoformat(),
                    "current_value": item.get("current_value"),
                }
                for item in items
            ],
            separators=(",", ":"),
            ensure_ascii=False,
        )

    if not plausible_rows:
        return {
            "status": "ambiguous",
            "reason": "primary_statement_revenue_not_confirmed",
            "statement_candidate_count": 0,
            "statement_candidates_json": "[]",
        }
    if len(plausible_rows) != 1:
        return {
            "status": "ambiguous",
            "reason": "multiple_primary_statement_revenue_rows",
            "statement_candidate_count": len(plausible_rows),
            "statement_candidates_json": candidate_provenance(plausible_rows),
        }

    chosen = plausible_rows[0]
    if chosen["comparative_value"] is None or chosen["current_value"] is None:
        return {
            "status": "ambiguous",
            "reason": "primary_statement_revenue_annual_values_not_confirmed",
            "statement_candidate_count": 1,
            "statement_candidates_json": candidate_provenance([chosen]),
        }

    # A row such as ``Net sales`` is not necessarily the issuer-level total:
    # the same primary statement may separately report licensing, royalty, or
    # financial-services revenue.  Those component rows deliberately fail the
    # admissible-total label screen, so they need a separate, broader check.
    # Accept a non-explicit total only when no complement is present or when
    # its value is demonstrably the sum of all non-overlapping revenue lines.
    # Otherwise fail closed rather than treating one business line as total
    # consolidated revenue.
    chosen_label = normalized_label(str(chosen.get("statement_label", "")))
    if not re.search(r"\btotal\b", chosen_label):
        complement_rows: list[dict[str, Any]] = []
        seen_complements: set[tuple[str, str, float, float]] = set()
        for row in rows:
            if row.get("statement_file") != chosen.get("statement_file"):
                continue
            if int(row.get("statement_priority", 0)) != int(
                chosen.get("statement_priority", 0)
            ):
                continue
            if not economic_revenue_line(row):
                continue
            comparative_value = row["amounts"].get(comparative_end.isoformat())
            current_value = row["amounts"].get(current_end.isoformat())
            if comparative_value is None or current_value is None:
                continue
            complement = {
                "comparative_value": float(comparative_value),
                "current_value": float(current_value),
                **{key: value for key, value in row.items() if key != "amounts"},
            }
            identity = (
                str(complement.get("statement_label_normalized", "")),
                str(complement.get("statement_concepts", "")),
                float(complement["comparative_value"]),
                float(complement["current_value"]),
            )
            chosen_identity = (
                str(chosen.get("statement_label_normalized", "")),
                str(chosen.get("statement_concepts", "")),
                float(chosen["comparative_value"]),
                float(chosen["current_value"]),
            )
            if identity == chosen_identity or identity in seen_complements:
                continue
            seen_complements.add(identity)
            if alternate_gross_net_revenue_basis(chosen, complement):
                continue
            # Identical values under a secondary label/tag are an alternative
            # presentation of the same total, not an additive component.
            if amount_equal(
                float(complement["comparative_value"]),
                float(chosen["comparative_value"]),
                float(chosen["statement_scale"]),
            ) and amount_equal(
                float(complement["current_value"]),
                float(chosen["current_value"]),
                float(chosen["statement_scale"]),
            ):
                continue
            complement_rows.append(complement)

        if complement_rows:
            comparative_sum = sum(
                float(item["comparative_value"]) for item in complement_rows
            )
            current_sum = sum(float(item["current_value"]) for item in complement_rows)
            chosen_is_confirmed_sum = amount_equal(
                comparative_sum,
                float(chosen["comparative_value"]),
                float(chosen["statement_scale"]),
            ) and amount_equal(
                current_sum,
                float(chosen["current_value"]),
                float(chosen["statement_scale"]),
            )
            if not chosen_is_confirmed_sum:
                return {
                    "status": "ambiguous",
                    "reason": "component_revenue_without_confirmed_consolidated_total",
                    "statement_candidate_count": 1 + len(complement_rows),
                    "statement_candidates_json": candidate_provenance(
                        [chosen, *complement_rows]
                    ),
                }
    full_concepts = [
        concept
        for concept in str(chosen["statement_concepts"]).split(";")
        if concept
    ]
    # Extension concepts can be legitimate totals, but Company Facts does not
    # provide enough presentation semantics to validate them consistently.
    # They therefore block a standard-tag candidate rather than being guessed.
    standard_concepts = [
        concept.split(":", 1)[1]
        for concept in full_concepts
        if concept.startswith("us-gaap:")
        and concept.split(":", 1)[1] in allowed_tags
    ]
    if len(full_concepts) != 1 or len(set(standard_concepts)) != 1:
        return {
            "status": "ambiguous",
            "reason": "primary_statement_revenue_concept_not_admissible",
            "statement_candidate_count": 1,
            "statement_candidates_json": candidate_provenance([chosen]),
        }
    tag = standard_concepts[0]
    comparative_value = chosen["comparative_value"]
    current_value = chosen["current_value"]
    comparative_fact = matching_annual_fact(
        anchor["records"], tag, comparative_end, comparative_start,
        float(comparative_value), annual_min_days, annual_max_days,
        start_tolerance_days, float(chosen["statement_scale"]),
    )
    current_fact = matching_annual_fact(
        anchor["records"], tag, current_end, current_start,
        float(current_value), annual_min_days, annual_max_days,
        start_tolerance_days, float(chosen["statement_scale"]),
    )
    if comparative_fact is None or current_fact is None:
        return {
            "status": "ambiguous",
            "reason": "primary_statement_revenue_fact_context_not_confirmed",
            "statement_candidate_count": 1,
            "statement_candidates_json": candidate_provenance([chosen]),
        }
    chosen.update(
        {
            "tag": tag,
            "strategy": tag_to_strategy[tag],
            "comparative_fact": comparative_fact,
            "current_fact": current_fact,
        }
    )

    def selection(role: str, fact: dict[str, Any], value: float) -> dict[str, Any]:
        return {
            "status": "selected",
            "reason": "primary_statement_consolidated_revenue_confirmed",
            "role": role,
            "value": value,
            "tag": chosen["tag"],
            "strategy": chosen["strategy"],
            "accn": anchor["accn"],
            "filed": anchor.get("filed", ""),
            "accepted_at": anchor.get("accepted_at", ""),
            "start": fact.get("start", ""),
            "end": fact.get("end", ""),
            "duration_days": fact.get("duration_days"),
            "document_fiscal_year_focus": fact.get("document_fiscal_year_focus"),
            "document_fiscal_period_focus": fact.get("document_fiscal_period_focus", ""),
            "document_period_end_date": anchor.get("document_period_end_date", ""),
            "frame": fact.get("frame", ""),
            "candidate_count": 1,
            "statement_file": chosen["statement_file"],
            "statement_short_name": chosen["short_name"],
            "statement_long_name": chosen["long_name"],
            "statement_role_uri": chosen["role"],
            "statement_label": chosen["statement_label"],
            "statement_concepts": chosen["statement_concepts"],
            "statement_row_class": chosen["statement_row_class"],
            "statement_priority": chosen.get("statement_priority", ""),
            "statement_scale": chosen["statement_scale"],
            "statement_scale_label": chosen["statement_scale_label"],
            "statement_candidate_count": 1,
        }

    return {
        "status": "selected",
        "reason": "primary_statement_consolidated_revenue_confirmed",
        "strategy": chosen["strategy"],
        "comparative_t": selection(
            "comparative_t", chosen["comparative_fact"], chosen["comparative_value"]
        ),
        "current_t1": selection(
            "current_t1", chosen["current_fact"], chosen["current_value"]
        ),
        "statement_candidate_count": 1,
        "statement_candidates_json": candidate_provenance([chosen]),
        "semantic_diagnostic": "primary_statement_revenue_confirmed",
    }

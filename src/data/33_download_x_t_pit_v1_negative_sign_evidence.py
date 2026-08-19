"""Download narrow primary-statement evidence for X_t v1 sign review.

Only development observations (feature years 2011--2022) whose selected
current_t primitive has an economically suspicious negative sign are in
scope.  The exact frozen-universe anchor accession is used.  The script does
not alter X_t, the frozen universe, or the frozen target.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import time
from typing import Any
from xml.etree import ElementTree

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

import pandas as pd
import requests

from src.data.research_universe_target_application import verify_frozen_inputs
from src.data.x_t_pit import BASE_DIR, CONFIG_PATH, configured_path, load_config


PRIMITIVES = (
    "assets",
    "liabilities",
    "current_assets",
    "current_liabilities",
    "revenues",
)
REPORT_PATH = BASE_DIR / "data/reports/x_t_pit_v1_negative_sign_evidence.json"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}
REQUEST_TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 5
MINIMUM_REQUEST_INTERVAL_SECONDS = 0.25

BALANCE_POSITIVE = (
    "balance sheet",
    "balance sheets",
    "statement of financial position",
    "statements of financial position",
    "statement of financial condition",
    "statements of financial condition",
)
BALANCE_NEGATIVE = (
    "parenthetical",
    "detail",
    "disclosure",
    "note",
    "schedule",
    "supplemental",
    "supplementary",
    "segment",
    "pro forma",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def element_text(element: ElementTree.Element, name: str) -> str:
    child = element.find(f".//{name}")
    return "" if child is None or child.text is None else child.text.strip()


def statement_reports(summary: Path) -> list[dict[str, str]]:
    root = ElementTree.fromstring(summary.read_bytes())
    reports: list[dict[str, str]] = []
    for report in root.findall(".//Report"):
        metadata = {
            "html_file_name": element_text(report, "HtmlFileName"),
            "short_name": element_text(report, "ShortName"),
            "long_name": element_text(report, "LongName"),
            "role": element_text(report, "Role"),
            "menu_category": element_text(report, "MenuCategory"),
        }
        if metadata["html_file_name"]:
            reports.append(metadata)
    return reports


def balance_reports(summary: Path) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for report in statement_reports(summary):
        combined = " ".join(report.values()).lower()
        if any(term in combined for term in BALANCE_NEGATIVE):
            continue
        if not any(term in combined for term in BALANCE_POSITIVE):
            continue
        is_statement = (
            report["menu_category"].strip().lower() == "statements"
            or "- statement -" in report["long_name"].lower()
            or "statement" in report["short_name"].lower()
            or "balance sheet" in report["short_name"].lower()
        )
        if is_statement:
            selected.append(report)
    unique = {item["html_file_name"]: item for item in selected}
    return list(unique.values())


def valid_evidence(path: Path, payload: bytes | None = None) -> bool:
    try:
        content = payload if payload is not None else path.read_bytes()
    except OSError:
        return False
    if not content:
        return False
    if path.name == "FilingSummary.xml":
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError:
            return False
        return root.tag.rsplit("}", 1)[-1] == "FilingSummary"
    return bool(
        re.search(
            br"<table\b[^>]*\bclass\s*=\s*['\"][^'\"]*\breport\b[^'\"]*['\"]",
            content.lower(),
        )
    )


def get(session: requests.Session, url: str) -> bytes:
    error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 404:
                raise FileNotFoundError(url)
            response.raise_for_status()
            return response.content
        except FileNotFoundError:
            raise
        except Exception as caught:
            error = caught
            if attempt < MAX_ATTEMPTS:
                time.sleep(float(attempt * 2))
    assert error is not None
    raise error


def download(session: requests.Session, url: str, path: Path) -> str:
    if path.is_file() and valid_evidence(path):
        return "cached"
    payload = get(session, url)
    if not valid_evidence(path, payload):
        raise ValueError(f"Invalid SEC statement evidence: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    time.sleep(MINIMUM_REQUEST_INTERVAL_SECONDS)
    return "downloaded"


def download_document(session: requests.Session, url: str, path: Path) -> str:
    if path.is_file() and path.stat().st_size:
        return "cached"
    payload = get(session, url)
    if not payload:
        raise ValueError(f"Empty SEC document: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    time.sleep(MINIMUM_REQUEST_INTERVAL_SECONDS)
    return "downloaded"


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def primary_10k_filename(index_html: str) -> str:
    """Return the document whose filing-index Type column is exactly 10-K."""

    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", index_html, flags=re.I | re.S):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.I | re.S)
        if len(cells) < 4:
            continue
        values = [strip_html(cell) for cell in cells]
        if values[-2].upper() != "10-K":
            continue
        hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", row, flags=re.I)
        if hrefs:
            return Path(hrefs[0]).name
    return ""


def suspicious_cases(raw_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = [
        "research_universe_company_year_id",
        "cik10",
        "company_name_historical",
        "feature_year",
        "anchor_accession",
    ]
    columns.extend(
        column
        for primitive in PRIMITIVES
        for column in (
            f"current_t_{primitive}_value",
            f"current_t_{primitive}_status",
            f"current_t_{primitive}_statement_file",
        )
    )
    frame = pd.read_csv(raw_path, usecols=columns, low_memory=False)
    frame = frame.loc[frame["feature_year"].between(2011, 2022)].copy()
    cases: list[dict[str, Any]] = []
    for primitive in PRIMITIVES:
        values = pd.to_numeric(frame[f"current_t_{primitive}_value"], errors="coerce")
        selected = frame[f"current_t_{primitive}_status"].eq("selected")
        for row in frame.loc[selected & values.lt(0)].to_dict("records"):
            cases.append(
                {
                    "research_universe_company_year_id": row[
                        "research_universe_company_year_id"
                    ],
                    "cik10": str(row["cik10"]).zfill(10),
                    "company_name_historical": row["company_name_historical"],
                    "feature_year": int(row["feature_year"]),
                    "anchor_accession": row["anchor_accession"],
                    "primitive": primitive,
                    "selected_value": row[f"current_t_{primitive}_value"],
                    "selected_statement_file": row.get(
                        f"current_t_{primitive}_statement_file", ""
                    ),
                }
            )
    case_frame = pd.DataFrame(cases)
    anchors = (
        case_frame.groupby(
            [
                "research_universe_company_year_id",
                "cik10",
                "company_name_historical",
                "feature_year",
                "anchor_accession",
            ],
            as_index=False,
        )
        .agg(
            primitives=("primitive", lambda values: sorted(set(values))),
            revenue_statement_files=(
                "selected_statement_file",
                lambda values: sorted(
                    {
                        str(value)
                        for value in values
                        if pd.notna(value) and str(value).strip()
                    }
                ),
            ),
        )
    )
    return case_frame, anchors


def locate_summary(
    session: requests.Session,
    directory: Path,
    accession: str,
    cik10: str,
) -> tuple[str, str]:
    destination = directory / "FilingSummary.xml"
    candidates = list(
        dict.fromkeys(
            [
                str(int(cik10)),
                str(int(accession[:10])),
            ]
        )
    )
    if destination.is_file() and valid_evidence(destination):
        return candidates[0], "cached"
    compact = accession.replace("-", "")
    for archive_cik in candidates:
        url = f"{SEC_ARCHIVES}/{archive_cik}/{compact}/FilingSummary.xml"
        try:
            return archive_cik, download(session, url, destination)
        except FileNotFoundError:
            continue
    raise FileNotFoundError(
        f"FilingSummary.xml unavailable for {accession}; archive CIKs={candidates}"
    )


def main() -> None:
    config = load_config(CONFIG_PATH)
    frozen_before = verify_frozen_inputs(config)
    raw_path = configured_path(config, "outputs", "raw_artifact")
    cases, anchors = suspicious_cases(raw_path)
    cache_root = configured_path(config, "sources", "revenue_statement_evidence")
    session = requests.Session()
    session.headers.update(HEADERS)
    results: list[dict[str, Any]] = []
    for row in anchors.to_dict("records"):
        cik10 = str(row["cik10"]).zfill(10)
        accession = str(row["anchor_accession"])
        directory = cache_root / cik10 / accession.replace("-", "")
        result = {**row, "status": "pending", "reports": []}
        try:
            archive_cik, summary_status = locate_summary(
                session, directory, accession, cik10
            )
            reports: list[dict[str, str]] = []
            if any(
                primitive != "revenues" for primitive in row["primitives"]
            ):
                reports.extend(balance_reports(directory / "FilingSummary.xml"))
            requested_revenue_files = set(row["revenue_statement_files"])
            if requested_revenue_files:
                reports.extend(
                    report
                    for report in statement_reports(directory / "FilingSummary.xml")
                    if report["html_file_name"] in requested_revenue_files
                )
            reports = list(
                {report["html_file_name"]: report for report in reports}.values()
            )
            base_url = (
                f"{SEC_ARCHIVES}/{archive_cik}/{accession.replace('-', '')}"
            )
            for report in reports:
                filename = report["html_file_name"]
                report["download_status"] = download(
                    session, f"{base_url}/{filename}", directory / filename
                )
                report["sha256"] = sha256(directory / filename)
            index_name = f"{accession}-index.html"
            index_path = directory / index_name
            index_status = download_document(
                session, f"{base_url}/{index_name}", index_path
            )
            primary_name = primary_10k_filename(
                index_path.read_text(encoding="latin-1", errors="ignore")
            )
            if not primary_name:
                raise RuntimeError(f"Cannot identify primary 10-K for {accession}")
            primary_path = directory / primary_name
            primary_status = download_document(
                session, f"{base_url}/{primary_name}", primary_path
            )
            result.update(
                {
                    "status": "available" if reports else "statement_not_identified",
                    "archive_cik": str(archive_cik).zfill(10),
                    "summary_status": summary_status,
                    "summary_sha256": sha256(directory / "FilingSummary.xml"),
                    "filing_index_file": index_name,
                    "filing_index_status": index_status,
                    "filing_index_sha256": sha256(index_path),
                    "primary_10k_file": primary_name,
                    "primary_10k_status": primary_status,
                    "primary_10k_sha256": sha256(primary_path),
                    "reports": reports,
                }
            )
        except Exception as error:
            result.update({"status": "error", "error": repr(error)})
        results.append(result)
        print(
            f"negative-sign evidence {len(results)}/{len(anchors)} "
            f"{accession}: {result['status']}",
            flush=True,
        )
    frozen_after = verify_frozen_inputs(config)
    if frozen_after != frozen_before:
        raise RuntimeError("Frozen target or universe changed during evidence download")
    payload = {
        "artifact_id": "x_t_pit_v1_negative_sign_evidence",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "development_years": [2011, 2022],
        "test_years_inspected": False,
        "primitive_cases": int(len(cases)),
        "company_years": int(cases["research_universe_company_year_id"].nunique()),
        "status_counts": dict(sorted(Counter(item["status"] for item in results).items())),
        "frozen_inputs": frozen_before,
        "results": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(REPORT_PATH)


if __name__ == "__main__":
    main()

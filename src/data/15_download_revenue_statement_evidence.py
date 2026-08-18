"""Download SEC statement evidence required by the fail-closed revenue resolver.

For each unique PIT-B t+1 anchor with at least one revenue candidate, cache the
filing directory index, FilingSummary.xml and only the SEC-rendered reports
identified as primary income/operations statements. The target definition is
not touched by this utility.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import threading
import time
from typing import Any
from xml.etree import ElementTree

import pandas as pd
import requests

try:
    from src.data.revenue_statement_resolver import filing_summary_reports
except ModuleNotFoundError:  # direct ``python src/data/...py`` execution
    from revenue_statement_resolver import filing_summary_reports


BASE_DIR = Path(__file__).resolve().parents[2]
ROWS_PATH = BASE_DIR / "data" / "interim" / "target_candidate_v2_pit_b.csv"
CACHE_DIR = BASE_DIR / "data" / "raw" / "sec_filings" / "revenue_statement_evidence"
REPORT_PATH = BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_revenue_evidence_downloads.json"
HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}
REQUEST_TIMEOUT_SECONDS = 60
REQUEST_DELAY_SECONDS = 0.11
MAX_ATTEMPTS = 6
MAX_WORKERS = 4
# One globally serialized request start per second.  The large historical
# backfill proved to be throttled at a higher sustained rate from this client;
# any 429 additionally activates the shared cooldown below.
MINIMUM_REQUEST_INTERVAL_SECONDS = 1.0
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_BLOCK_UNTIL = 0.0
_CONSECUTIVE_429 = 0
_THREAD_LOCAL = threading.local()


def http_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        _THREAD_LOCAL.session = session
    return session


def filing_base(cik10: str, accession: str) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik10)}/{accession.replace('-', '')}"
    )


def local_directory(cik10: str, accession: str) -> Path:
    return CACHE_DIR / str(cik10).zfill(10) / accession.replace("-", "")


def get(url: str) -> requests.Response:
    global _BLOCK_UNTIL, _CONSECUTIVE_429, _LAST_REQUEST_AT
    error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with _RATE_LOCK:
                now = time.monotonic()
                delay = max(
                    MINIMUM_REQUEST_INTERVAL_SECONDS - (now - _LAST_REQUEST_AT),
                    _BLOCK_UNTIL - now,
                )
                if delay > 0:
                    time.sleep(delay)
                _LAST_REQUEST_AT = time.monotonic()
            response = http_session().get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 404:
                raise FileNotFoundError(f"SEC archive resource absent: {url}")
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "").strip()
                try:
                    cooldown = float(retry_after)
                except ValueError:
                    cooldown = 0.0
                with _RATE_LOCK:
                    now = time.monotonic()
                    if now < _BLOCK_UNTIL:
                        # Several requests can already be in flight when the
                        # first 429 activates the block. Their responses belong
                        # to the same throttling incident and must not each
                        # double the shared cooldown.
                        cooldown = max(cooldown, _BLOCK_UNTIL - now)
                    else:
                        _CONSECUTIVE_429 += 1
                        cooldown = max(
                            cooldown,
                            min(600.0, 60.0 * (2 ** (_CONSECUTIVE_429 - 1))),
                        )
                    _BLOCK_UNTIL = max(_BLOCK_UNTIL, now + cooldown)
                raise requests.HTTPError(
                    f"429 Too Many Requests; shared cooldown {cooldown:.0f}s for {url}",
                    response=response,
                )
            response.raise_for_status()
            with _RATE_LOCK:
                _CONSECUTIVE_429 = 0
            return response
        except FileNotFoundError:
            raise
        except Exception as caught:
            error = caught
            if attempt < MAX_ATTEMPTS:
                time.sleep(attempt)
    assert error is not None
    raise error


def valid_evidence_payload(path: Path, payload: bytes | None = None) -> bool:
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
    lowered = content.lower()
    return bool(
        re.search(
            br"<table\b[^>]*\bclass\s*=\s*['\"][^'\"]*\breport\b[^'\"]*['\"]",
            lowered,
        )
    )


def download(url: str, path: Path) -> str:
    if path.exists() and valid_evidence_payload(path):
        return "cached"
    had_invalid_cache = path.exists()
    response = get(url)
    if not valid_evidence_payload(path, response.content):
        raise ValueError(f"Invalid SEC statement evidence payload: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(response.content)
    return "replaced_invalid" if had_invalid_cache else "downloaded"


def candidate_anchors() -> pd.DataFrame:
    columns = [
        "cik10",
        "feature_year",
        "anchor_t1_accn",
        "anchor_t1_primary_document",
        "B_revenues_status",
    ]
    rows = pd.read_csv(ROWS_PATH, usecols=columns, dtype={"cik10": str}, low_memory=False)
    rows = rows[
        rows["anchor_t1_accn"].notna()
        & rows["B_revenues_status"].isin(["selected", "ambiguous"])
    ].copy()
    rows["cik10"] = rows["cik10"].str.zfill(10)
    anchors = rows.drop_duplicates(["cik10", "anchor_t1_accn"]).sort_values(
        ["cik10", "anchor_t1_accn"]
    )
    if os.environ.get("REVENUE_EVIDENCE_RETRY_ERRORS_ONLY", "").strip() == "1":
        if not REPORT_PATH.exists():
            raise RuntimeError("Cannot retry errors: prior download report is absent")
        prior = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        error_keys = {
            (str(item["cik10"]).zfill(10), str(item["accession"]))
            for item in prior.get("results", [])
            if item.get("status") == "error"
        }
        anchors = anchors[
            anchors.apply(
                lambda row: (str(row["cik10"]).zfill(10), str(row["anchor_t1_accn"]))
                in error_keys,
                axis=1,
            )
        ]
    return anchors


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    anchors = candidate_anchors()
    limit_text = os.environ.get("REVENUE_EVIDENCE_LIMIT", "").strip()
    if limit_text:
        anchors = anchors.head(int(limit_text))
    def process(row: pd.Series) -> dict[str, Any]:
        cik10 = str(row["cik10"]).zfill(10)
        accession = str(row["anchor_t1_accn"])
        directory = local_directory(cik10, accession)
        base_url = filing_base(cik10, accession)
        result: dict[str, Any] = {
            "cik10": cik10,
            "accession": accession,
            "feature_year": int(row["feature_year"]),
            "base_url": base_url,
            "status": "pending",
            "reports": [],
        }
        try:
            summary_name = "FilingSummary.xml"
            summary_path = directory / summary_name
            result["summary_status"] = download(
                f"{base_url}/{summary_name}", summary_path
            )
            # Use exactly the same statement-membership policy as the resolver;
            # this prevents download-time and resolution-time semantic drift.
            reports = filing_summary_reports(summary_path)
            for report in reports:
                name = report["html_file_name"]
                report["download_status"] = download(
                    f"{base_url}/{name}", directory / name
                )
            result["reports"] = reports
            result["status"] = (
                "statement_reports_downloaded" if reports else "income_statement_not_identified"
            )
        except Exception as error:  # every failure remains auditable
            result["status"] = "error"
            result["error"] = repr(error)
        return result

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process, row) for _, row in anchors.iterrows()]
        for position, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if position % 250 == 0 or position == len(anchors):
                print(f"Revenue statement evidence: {position}/{len(anchors)}", flush=True)
    results.sort(key=lambda item: (item["cik10"], item["accession"]))

    report = {
        "anchor_count": int(len(anchors)),
        "status_counts": {
            str(status): int(count)
            for status, count in pd.Series(
                [item["status"] for item in results]
            ).value_counts().items()
        },
        "results": results,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))


if __name__ == "__main__":
    main()

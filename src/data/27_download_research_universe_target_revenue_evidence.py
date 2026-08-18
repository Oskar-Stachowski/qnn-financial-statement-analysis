"""Download missing primary-statement evidence for the target application.

The downloader uses the frozen fail-closed revenue statement membership
function. Existing evidence is validated and reused; only absent/invalid files
are fetched. It never selects a concept based on coverage or target value.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import sys
import threading
import time
from typing import Any
from xml.etree import ElementTree

import pandas as pd
import requests


if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.data.research_universe_target_application import (
    BASE_DIR,
    configured_path,
    load_application_config,
    verify_frozen_inputs,
    write_json_atomic,
)
from src.data.revenue_statement_resolver import filing_summary_reports


HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}
REQUEST_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 6
MAX_WORKERS = 6
MINIMUM_REQUEST_INTERVAL_SECONDS = float(
    os.environ.get("TARGET_REVENUE_EVIDENCE_INTERVAL_SECONDS", "0.15")
)
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_BLOCK_UNTIL = 0.0
_THREAD_LOCAL = threading.local()


def session() -> requests.Session:
    current = getattr(_THREAD_LOCAL, "session", None)
    if current is None:
        current = requests.Session()
        current.headers.update(HEADERS)
        _THREAD_LOCAL.session = current
    return current


def get(url: str) -> requests.Response:
    global _BLOCK_UNTIL, _LAST_REQUEST_AT
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
            response = session().get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 404:
                raise FileNotFoundError(url)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "").strip()
                try:
                    cooldown = float(retry_after)
                except ValueError:
                    cooldown = 0.0
                cooldown = max(cooldown, min(300.0, 30.0 * (2 ** (attempt - 1))))
                with _RATE_LOCK:
                    _BLOCK_UNTIL = max(_BLOCK_UNTIL, time.monotonic() + cooldown)
                raise requests.HTTPError(
                    f"429; shared cooldown {cooldown:.0f}s for {url}", response=response
                )
            response.raise_for_status()
            return response
        except FileNotFoundError:
            raise
        except Exception as caught:
            error = caught
            if attempt < MAX_ATTEMPTS:
                time.sleep(float(attempt))
    assert error is not None
    raise error


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


def download(url: str, path: Path) -> str:
    if path.is_file() and valid_evidence(path):
        return "cached"
    invalid_cache = path.exists()
    response = get(url)
    if not valid_evidence(path, response.content):
        raise ValueError(f"Invalid statement evidence: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_bytes(response.content)
    temporary.replace(path)
    return "replaced_invalid" if invalid_cache else "downloaded"


def filing_base(cik10: str, accession: str) -> str:
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{int(cik10)}/{accession.replace('-', '')}"
    )


def candidate_anchors(config: dict[str, Any]) -> pd.DataFrame:
    path = configured_path(config, "outputs", "working_artifact")
    columns = [
        "cik10",
        "feature_year",
        "anchor_t1_accn",
        "B_revenues_status",
        "B_revenues_reason",
    ]
    rows = pd.read_csv(path, usecols=columns, dtype={"cik10": "string"}, low_memory=False)
    rows["cik10"] = rows["cik10"].str.zfill(10)
    rows = rows.loc[
        rows["anchor_t1_accn"].notna()
        & rows["B_revenues_status"].eq("ambiguous")
        & rows["B_revenues_reason"].eq("primary_statement_evidence_unavailable")
    ].copy()
    return rows.drop_duplicates(["cik10", "anchor_t1_accn"]).sort_values(
        ["cik10", "anchor_t1_accn"]
    )


def process_anchor(row: pd.Series, cache_dir: Path) -> dict[str, Any]:
    cik10 = str(row["cik10"]).zfill(10)
    accession = str(row["anchor_t1_accn"])
    compact_accession = accession.replace("-", "")
    directory = cache_dir / cik10 / compact_accession
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
        summary_path = directory / "FilingSummary.xml"
        result["summary_status"] = download(
            f"{base_url}/FilingSummary.xml", summary_path
        )
        reports = filing_summary_reports(summary_path)
        for report in reports:
            name = report["html_file_name"]
            report["download_status"] = download(
                f"{base_url}/{name}", directory / name
            )
        result["reports"] = reports
        result["status"] = (
            "statement_reports_available"
            if reports
            else "income_statement_not_identified"
        )
    except FileNotFoundError as error:
        result["status"] = "not_found"
        result["error"] = repr(error)
    except Exception as error:
        result["status"] = "error"
        result["error"] = repr(error)
    return result


def main() -> None:
    config = load_application_config()
    frozen_before = verify_frozen_inputs(config)
    anchors = candidate_anchors(config)
    limit = int(os.environ.get("TARGET_REVENUE_EVIDENCE_LIMIT", "0"))
    if limit:
        anchors = anchors.head(limit)
    cache_dir = configured_path(
        config, "application_cache", "revenue_statement_evidence"
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    workers = max(
        1,
        min(int(os.environ.get("TARGET_REVENUE_EVIDENCE_WORKERS", MAX_WORKERS)), 8),
    )
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(process_anchor, row, cache_dir)
            for _, row in anchors.iterrows()
        ]
        for index, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if index % 100 == 0 or index == len(futures):
                print(f"Revenue statement evidence: {index}/{len(futures)}", flush=True)
    results.sort(key=lambda item: (item["cik10"], item["accession"]))
    frozen_after = verify_frozen_inputs(config)
    if frozen_before != frozen_after:
        raise RuntimeError("Frozen inputs changed during evidence download")

    report = {
        "application_id": config["application"]["id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_anchors": int(len(anchors)),
        "status_counts": dict(
            sorted(Counter(item["status"] for item in results).items())
        ),
        "results": results,
        "frozen_inputs": frozen_after,
    }
    path = configured_path(config, "outputs", "revenue_evidence_download_report")
    write_json_atomic(report, path)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key not in {"results", "frozen_inputs"}},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

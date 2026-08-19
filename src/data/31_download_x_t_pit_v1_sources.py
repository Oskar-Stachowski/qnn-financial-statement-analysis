"""Download only missing SEC primary-statement evidence for raw X_t v1.

The candidate list comes from the development-only X_t audit.  Existing cache
files are validated and reused.  The downloader never changes the frozen
universe, frozen target, X_t feature policy, or any resolved feature value.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any
from xml.etree import ElementTree

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

import pandas as pd
import requests

from src.data.research_universe_target_application import verify_frozen_inputs
from src.data.revenue_statement_resolver import filing_summary_reports
from src.data.x_t_pit import (
    BASE_DIR,
    CONFIG_PATH,
    configured_path,
    load_config,
    load_universe,
)


SOURCE_GAPS_PATH = BASE_DIR / "data/reports/x_t_pit_v1_source_gaps.csv"
REPORT_PATH = BASE_DIR / "data/reports/x_t_pit_v1_source_download.json"
REGISTRANT_EVIDENCE_ROOT = (
    BASE_DIR / "data/raw/sec_historical_universe/registrant_role_evidence"
)
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}
REQUEST_TIMEOUT_SECONDS = 90
MAX_ATTEMPTS = 6
MAX_WORKERS = 6
MINIMUM_REQUEST_INTERVAL_SECONDS = float(
    os.environ.get("X_T_SOURCE_INTERVAL_SECONDS", "0.16")
)
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_BLOCK_UNTIL = 0.0
_THREAD_LOCAL = threading.local()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
                cooldown = max(cooldown, min(600.0, 30.0 * (2 ** (attempt - 1))))
                with _RATE_LOCK:
                    _BLOCK_UNTIL = max(_BLOCK_UNTIL, time.monotonic() + cooldown)
                raise requests.HTTPError(
                    f"429; shared cooldown {cooldown:.0f}s for {url}",
                    response=response,
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


def write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def download(url: str, path: Path) -> str:
    if path.is_file() and valid_evidence(path):
        return "cached"
    invalid_cache = path.exists()
    response = get(url)
    if not valid_evidence(path, response.content):
        raise ValueError(f"Invalid statement evidence: {url}")
    write_atomic(path, response.content)
    return "replaced_invalid" if invalid_cache else "downloaded"


def archive_cik_candidates(
    cik10: str,
    accession: str,
    accession_to_ciks: dict[str, list[str]],
) -> list[str]:
    candidates = [str(int(cik10))]
    source_path = REGISTRANT_EVIDENCE_ROOT / accession / "source.json"
    if source_path.exists():
        try:
            source = json.loads(source_path.read_text(encoding="utf-8"))
            candidates.append(str(int(source.get("archive_cik", "0"))))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    candidates.extend(str(int(item)) for item in accession_to_ciks.get(accession, []))
    return list(dict.fromkeys(item for item in candidates if item != "0"))


def locate_summary(
    cik_candidates: list[str],
    accession: str,
    destination: Path,
) -> tuple[str, str]:
    if destination.is_file() and valid_evidence(destination):
        return cik_candidates[0], "cached"
    compact = accession.replace("-", "")
    for archive_cik in cik_candidates:
        url = f"{SEC_ARCHIVES}/{archive_cik}/{compact}/FilingSummary.xml"
        try:
            return archive_cik, download(url, destination)
        except FileNotFoundError:
            continue
    raise FileNotFoundError(
        f"FilingSummary.xml unavailable for {accession}; archive CIKs={cik_candidates}"
    )


def process_anchor(
    row: dict[str, Any],
    cache_root: Path,
    accession_to_ciks: dict[str, list[str]],
) -> dict[str, Any]:
    cik10 = str(row["cik10"]).zfill(10)
    accession = str(row["anchor_accession"])
    directory = cache_root / cik10 / accession.replace("-", "")
    result: dict[str, Any] = {
        "cik10": cik10,
        "accession": accession,
        "feature_year": int(row["feature_year"]),
        "status": "pending",
        "reports": [],
    }
    try:
        candidates = archive_cik_candidates(cik10, accession, accession_to_ciks)
        archive_cik, summary_status = locate_summary(
            candidates, accession, directory / "FilingSummary.xml"
        )
        base_url = (
            f"{SEC_ARCHIVES}/{archive_cik}/{accession.replace('-', '')}"
        )
        reports = filing_summary_reports(directory / "FilingSummary.xml")
        for report in reports:
            filename = report["html_file_name"]
            report["download_status"] = download(
                f"{base_url}/{filename}", directory / filename
            )
        result.update(
            {
                "archive_cik": str(archive_cik).zfill(10),
                "base_url": base_url,
                "summary_status": summary_status,
                "reports": reports,
                "status": (
                    "statement_reports_available"
                    if reports
                    else "income_statement_not_identified"
                ),
            }
        )
    except FileNotFoundError as error:
        result["status"] = "not_found"
        result["error"] = repr(error)
    except Exception as error:
        result["status"] = "error"
        result["error"] = repr(error)
    return result


def candidate_anchors(config: dict[str, Any] | None = None) -> pd.DataFrame:
    config = config or load_config(CONFIG_PATH)
    gaps = pd.read_csv(SOURCE_GAPS_PATH, dtype=str, low_memory=False).fillna("")
    gaps = gaps.loc[
        gaps["source_type"].eq("primary_statement_revenue_evidence")
        & ~gaps["prior_download_status"].eq("not_found")
    ][["cik10", "feature_year", "anchor_accession"]].copy()

    # The methodological audit is development-only, but the raw artifact also
    # needs mechanically complete source acquisition for 2023--2024.  Reading
    # only the source-availability reason does not inspect feature values,
    # coverage, outliers, targets, or model results and cannot affect policy.
    raw_path = configured_path(config, "outputs", "raw_artifact")
    if raw_path.exists():
        test_parts: list[pd.DataFrame] = []
        for chunk in pd.read_csv(
            raw_path,
            usecols=[
                "cik10",
                "feature_year",
                "anchor_accession",
                "current_t_revenues_reason",
            ],
            dtype=str,
            chunksize=5_000,
            keep_default_na=False,
            low_memory=False,
        ):
            years = pd.to_numeric(chunk["feature_year"], errors="coerce")
            selected = chunk.loc[
                years.between(2023, 2024)
                & chunk["current_t_revenues_reason"].eq(
                    "primary_statement_evidence_unavailable"
                ),
                ["cik10", "feature_year", "anchor_accession"],
            ]
            test_parts.append(selected)
        if test_parts:
            gaps = pd.concat([gaps, *test_parts], ignore_index=True)

    # A completed or interrupted inventory remains the durable candidate log,
    # including files that have since become present in the cache.
    if REPORT_PATH.exists():
        try:
            prior = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            prior_rows = pd.DataFrame(
                [
                    {
                        "cik10": item.get("cik10", ""),
                        "feature_year": item.get("feature_year", ""),
                        "anchor_accession": item.get("accession", ""),
                    }
                    for item in prior.get("results", [])
                ]
            )
            gaps = pd.concat([gaps, prior_rows], ignore_index=True)
        except (OSError, json.JSONDecodeError):
            pass

    gaps["cik10"] = gaps["cik10"].str.zfill(10)
    gaps["feature_year"] = pd.to_numeric(gaps["feature_year"], errors="raise").astype(int)
    gaps = gaps.drop_duplicates(["cik10", "anchor_accession"]).sort_values(
        ["feature_year", "cik10", "anchor_accession"]
    )

    # Filing-level XBRL does not imply that a secondary statement scope is
    # tagged.  Only statement scopes with validated XBRL availability need
    # primary-statement XBRL evidence.
    eligible, _ = load_universe(config)
    eligible_xbrl = eligible.loc[
        eligible["statement_scope_xbrl_status"].eq("available"),
        ["cik10", "accession"],
    ].drop_duplicates()
    eligible_keys = set(
        zip(
            eligible_xbrl["cik10"].astype(str).str.zfill(10),
            eligible_xbrl["accession"].astype(str),
            strict=True,
        )
    )
    gaps = gaps.loc[
        [
            (str(cik).zfill(10), str(accession)) in eligible_keys
            for cik, accession in zip(
                gaps["cik10"], gaps["anchor_accession"], strict=True
            )
        ]
    ]
    retry_only = os.environ.get("X_T_SOURCE_RETRY_ERRORS_ONLY", "").strip() == "1"
    if retry_only:
        if not REPORT_PATH.exists():
            raise RuntimeError("Cannot retry errors: prior X_t download report is absent")
        prior = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        retry_keys = {
            (str(item["cik10"]).zfill(10), str(item["accession"]))
            for item in prior.get("results", [])
            if item.get("status") == "error"
        }
        gaps = gaps.loc[
            [
                (str(cik).zfill(10), str(accession)) in retry_keys
                for cik, accession in zip(
                    gaps["cik10"], gaps["anchor_accession"], strict=True
                )
            ]
        ]
    limit = int(os.environ.get("X_T_SOURCE_LIMIT", "0"))
    return gaps.head(limit) if limit else gaps


def reusable_prior_results(
    anchors: pd.DataFrame,
    cache_root: Path,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Reuse only checkpoint entries whose local evidence still validates."""

    if not REPORT_PATH.exists() or os.environ.get(
        "X_T_SOURCE_RETRY_ERRORS_ONLY", ""
    ).strip() == "1":
        return {}
    try:
        prior = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    allowed = {
        (str(row.cik10).zfill(10), str(row.anchor_accession))
        for row in anchors.itertuples(index=False)
    }
    reusable: dict[tuple[str, str], dict[str, Any]] = {}
    for item in prior.get("results", []):
        cik10 = str(item.get("cik10", "")).zfill(10)
        accession = str(item.get("accession", ""))
        key = (cik10, accession)
        if key not in allowed:
            continue
        status = str(item.get("status", ""))
        if status == "not_found":
            reusable[key] = item
            continue
        directory = cache_root / cik10 / accession.replace("-", "")
        summary = directory / "FilingSummary.xml"
        if not summary.is_file() or not valid_evidence(summary):
            continue
        reports = item.get("reports", [])
        if status == "income_statement_not_identified":
            if not reports and not filing_summary_reports(summary):
                reusable[key] = item
            continue
        if status != "statement_reports_available" or not reports:
            continue
        report_paths = [
            directory / str(report.get("html_file_name", ""))
            for report in reports
        ]
        if all(path.is_file() and valid_evidence(path) for path in report_paths):
            reusable[key] = item
    return reusable


def write_report(
    results: list[dict[str, Any]],
    *,
    expected: int,
    frozen_inputs: dict[str, str],
    complete: bool,
) -> None:
    ordered = sorted(results, key=lambda item: (item["cik10"], item["accession"]))
    report = {
        "artifact_id": "x_t_pit_v1_source_download",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_anchors": expected,
        "processed_anchors": len(ordered),
        "complete": complete,
        "status_counts": dict(sorted(Counter(item["status"] for item in ordered).items())),
        "results": ordered,
        "frozen_inputs": frozen_inputs,
    }
    write_atomic(
        REPORT_PATH,
        (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"),
    )


def main() -> None:
    config = load_config(CONFIG_PATH)
    frozen_before = verify_frozen_inputs(config)
    anchors = candidate_anchors(config)
    universe = pd.read_csv(
        configured_path(config, "frozen_inputs", "universe_artifact"),
        usecols=["accession", "cik10"],
        dtype=str,
        low_memory=False,
    ).fillna("")
    accession_to_ciks = {
        accession: sorted(set(group["cik10"].str.zfill(10)))
        for accession, group in universe.groupby("accession")
    }
    cache_root = configured_path(config, "sources", "revenue_statement_evidence")
    cache_root.mkdir(parents=True, exist_ok=True)
    # More waiting workers hide SEC response latency; the shared request-rate
    # limiter still caps aggregate traffic at 6.25 requests/second by default.
    workers = max(1, min(int(os.environ.get("X_T_SOURCE_WORKERS", MAX_WORKERS)), 12))
    prior = reusable_prior_results(anchors, cache_root)
    remaining = [
        row
        for row in anchors.to_dict("records")
        if (str(row["cik10"]).zfill(10), str(row["anchor_accession"])) not in prior
    ]
    results: list[dict[str, Any]] = list(prior.values())
    if prior:
        print(
            f"X_t revenue evidence: reusing {len(prior)}/{len(anchors)} "
            "validated checkpoint entries",
            flush=True,
        )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                process_anchor,
                row,
                cache_root,
                accession_to_ciks,
            ): (str(row["cik10"]), str(row["anchor_accession"]))
            for row in remaining
        }
        try:
            for number, future in enumerate(
                as_completed(futures), start=len(results) + 1
            ):
                results.append(future.result())
                if number % 100 == 0 or number == len(anchors):
                    write_report(
                        results,
                        expected=len(anchors),
                        frozen_inputs=frozen_before,
                        complete=number == len(anchors),
                    )
                    counts = Counter(item["status"] for item in results)
                    print(
                        f"X_t revenue evidence: {number}/{len(anchors)} "
                        f"status={dict(sorted(counts.items()))}",
                        flush=True,
                    )
        finally:
            write_report(
                results,
                expected=len(anchors),
                frozen_inputs=frozen_before,
                complete=len(results) == len(anchors),
            )
    frozen_after = verify_frozen_inputs(config)
    if frozen_after != frozen_before:
        raise RuntimeError("Frozen target or universe changed during source download")
    print(f"Report: {REPORT_PATH.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()

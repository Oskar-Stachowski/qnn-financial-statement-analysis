"""Prepare compact SEC inputs for frozen-universe target application.

Existing full Company Facts and SEC Submissions caches are projected locally.
Only missing eligible CIKs are requested from SEC. The projection preserves
exactly the tags and filing metadata consumed by frozen PIT-B v1.0.0, reducing
disk use without changing the resolver.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Callable

import requests


if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.data.research_universe_target_application import (
    BASE_DIR,
    configured_path,
    load_application_config,
    load_eligible_universe,
    verify_frozen_inputs,
    write_json_atomic,
)
from src.data.target_candidate_v2_pit import load_config, required_tags


FULL_COMPANYFACTS_DIR = BASE_DIR / "data/raw/companyfacts"
FULL_SUBMISSIONS_DIR = BASE_DIR / "data/raw/sec_submissions"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
SUBMISSION_URL = "https://data.sec.gov/submissions/CIK{cik10}.json"
SUBMISSION_SHARD_URL = "https://data.sec.gov/submissions/{name}"
HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json",
}
SUBMISSION_FIELDS = (
    "accessionNumber",
    "form",
    "filingDate",
    "reportDate",
    "acceptanceDateTime",
    "primaryDocument",
    "isXBRL",
)
REQUEST_TIMEOUT_SECONDS = 60
MINIMUM_REQUEST_INTERVAL_SECONDS = 0.13
MAX_ATTEMPTS = 6
MAX_WORKERS = 4
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0
_THREAD_LOCAL = threading.local()


def session() -> requests.Session:
    current = getattr(_THREAD_LOCAL, "session", None)
    if current is None:
        current = requests.Session()
        current.headers.update(HEADERS)
        _THREAD_LOCAL.session = current
    return current


def get_json(url: str) -> dict[str, Any]:
    global _LAST_REQUEST_AT
    error: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with _RATE_LOCK:
                delay = MINIMUM_REQUEST_INTERVAL_SECONDS - (
                    time.monotonic() - _LAST_REQUEST_AT
                )
                if delay > 0:
                    time.sleep(delay)
                _LAST_REQUEST_AT = time.monotonic()
            response = session().get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code == 404:
                raise FileNotFoundError(url)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError(f"Non-object SEC JSON response: {url}")
            return payload
        except FileNotFoundError:
            raise
        except Exception as caught:
            error = caught
            if attempt < MAX_ATTEMPTS:
                time.sleep(min(60.0, float(2 ** (attempt - 1))))
    assert error is not None
    raise error


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def projected_companyfacts(
    payload: dict[str, Any], allowed_tags: set[str]
) -> dict[str, Any]:
    us_gaap = payload.get("facts", {}).get("us-gaap", {})
    if not isinstance(us_gaap, dict):
        us_gaap = {}
    return {
        "cik": payload.get("cik"),
        "entityName": payload.get("entityName", ""),
        "facts": {
            "us-gaap": {
                tag: us_gaap[tag]
                for tag in sorted(allowed_tags)
                if tag in us_gaap
            }
        },
    }


def projected_submission_table(table: dict[str, Any]) -> dict[str, list[Any]]:
    return {
        field: list(table.get(field, []))
        if isinstance(table.get(field, []), list)
        else []
        for field in SUBMISSION_FIELDS
    }


def projected_main_submission(payload: dict[str, Any]) -> dict[str, Any]:
    filings = payload.get("filings", {})
    return {
        "cik": payload.get("cik"),
        "name": payload.get("name", ""),
        "filings": {
            "recent": projected_submission_table(filings.get("recent", {})),
            "files": [
                {
                    "name": str(item.get("name", "") or ""),
                    "filingCount": item.get("filingCount"),
                    "filingFrom": str(item.get("filingFrom", "") or ""),
                    "filingTo": str(item.get("filingTo", "") or ""),
                }
                for item in filings.get("files", [])
                if item.get("name")
            ],
        },
    }


def projected_submission_shard(payload: dict[str, Any]) -> dict[str, list[Any]]:
    table = payload.get("filings", {}).get("recent", payload)
    return projected_submission_table(table if isinstance(table, dict) else {})


def json_is_valid(path: Path) -> bool:
    try:
        return isinstance(read_json(path), dict)
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def prepare_one(
    key: str,
    destination: Path,
    existing_source: Path | None,
    url: str,
    projector: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, str]:
    if destination.is_file() and json_is_valid(destination):
        return {"key": key, "status": "cached_application"}
    try:
        if existing_source is not None and existing_source.is_file():
            payload = read_json(existing_source)
            status = "projected_existing_cache"
        else:
            payload = get_json(url)
            status = "downloaded_and_projected"
        write_json_atomic(projector(payload), destination)
        return {"key": key, "status": status}
    except FileNotFoundError:
        return {"key": key, "status": "not_found", "url": url}
    except Exception as error:
        return {
            "key": key,
            "status": "error",
            "url": url,
            "error": repr(error),
        }


def run_parallel(
    label: str,
    tasks: list[tuple[Any, ...]],
    function: Callable[..., dict[str, str]],
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    workers = max(1, min(int(os.environ.get("TARGET_INPUT_WORKERS", MAX_WORKERS)), 8))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(function, *task) for task in tasks]
        for index, future in enumerate(as_completed(futures), start=1):
            results.append(future.result())
            if index % 100 == 0 or index == len(tasks):
                print(f"{label}: {index}/{len(tasks)}", flush=True)
    results.sort(key=lambda item: item["key"])
    return results


def relevant_shards(main_paths: list[Path]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for path in main_paths:
        if not path.is_file():
            continue
        payload = read_json(path)
        for item in payload.get("filings", {}).get("files", []):
            name = str(item.get("name", "") or "")
            filing_from = str(item.get("filingFrom", "") or "")
            filing_to = str(item.get("filingTo", "") or "")
            if (
                name
                and (not filing_to or filing_to >= "2009-01-01")
                and (not filing_from or filing_from <= "2027-12-31")
            ):
                result[name] = {
                    "filing_from": filing_from,
                    "filing_to": filing_to,
                }
    return result


def summary(results: list[dict[str, str]]) -> dict[str, Any]:
    counts = Counter(item["status"] for item in results)
    return {
        "total": len(results),
        "status_counts": dict(sorted(counts.items())),
        "errors": [
            item for item in results if item["status"] in {"error", "not_found"}
        ],
    }


def main() -> None:
    config = load_application_config()
    frozen_before = verify_frozen_inputs(config)
    eligible = load_eligible_universe(config)
    companyfacts_dir = configured_path(config, "application_cache", "companyfacts")
    submissions_dir = configured_path(config, "application_cache", "submissions")
    companyfacts_dir.mkdir(parents=True, exist_ok=True)
    submissions_dir.mkdir(parents=True, exist_ok=True)

    target_config = load_config(
        configured_path(config, "frozen_inputs", "target_config")
    )
    allowed_tags = required_tags(target_config)
    xbrl_available = eligible["xbrl_submission_available"]
    if not str(xbrl_available.dtype).lower().startswith("bool"):
        xbrl_available = xbrl_available.fillna("").astype(str).str.lower().eq("true")
    eligible = eligible.assign(xbrl_submission_available=xbrl_available)
    cik_xbrl = (
        eligible.groupby("cik10")["xbrl_submission_available"]
        .any()
        .to_dict()
    )
    ciks = sorted(eligible["cik10"].unique())

    companyfacts_tasks: list[tuple[Any, ...]] = []
    structurally_skipped: list[dict[str, str]] = []
    for cik10 in ciks:
        source = FULL_COMPANYFACTS_DIR / f"CIK{cik10}.json"
        destination = companyfacts_dir / f"CIK{cik10}.json"
        if not source.exists() and not destination.exists() and not bool(cik_xbrl[cik10]):
            structurally_skipped.append(
                {"key": cik10, "status": "skipped_no_eligible_xbrl_submission"}
            )
            continue
        companyfacts_tasks.append(
            (
                cik10,
                destination,
                source,
                COMPANYFACTS_URL.format(cik10=cik10),
                lambda payload, tags=allowed_tags: projected_companyfacts(payload, tags),
            )
        )
    companyfacts_results = run_parallel(
        "Company Facts projection", companyfacts_tasks, prepare_one
    )
    companyfacts_results.extend(structurally_skipped)
    companyfacts_results.sort(key=lambda item: item["key"])

    ciks_with_facts = [
        cik10
        for cik10 in ciks
        if (companyfacts_dir / f"CIK{cik10}.json").is_file()
    ]
    submission_tasks = [
        (
            cik10,
            submissions_dir / f"CIK{cik10}.json",
            FULL_SUBMISSIONS_DIR / f"CIK{cik10}.json",
            SUBMISSION_URL.format(cik10=cik10),
            projected_main_submission,
        )
        for cik10 in ciks_with_facts
    ]
    submission_results = run_parallel(
        "SEC main submissions projection", submission_tasks, prepare_one
    )

    main_paths = [submissions_dir / f"CIK{cik10}.json" for cik10 in ciks_with_facts]
    shard_metadata = relevant_shards(main_paths)
    shard_tasks = [
        (
            name,
            submissions_dir / name,
            FULL_SUBMISSIONS_DIR / name,
            SUBMISSION_SHARD_URL.format(name=name),
            projected_submission_shard,
        )
        for name in sorted(shard_metadata)
    ]
    shard_results = run_parallel(
        "SEC historical submission shards", shard_tasks, prepare_one
    )

    frozen_after = verify_frozen_inputs(config)
    if frozen_before != frozen_after:
        raise RuntimeError("Frozen inputs changed while preparing application cache")
    report = {
        "application_id": config["application"]["id"],
        "eligible_ciks": len(ciks),
        "required_us_gaap_tags": sorted(allowed_tags),
        "companyfacts": summary(companyfacts_results),
        "main_submissions": summary(submission_results),
        "historical_submission_shards": summary(shard_results),
        "frozen_inputs": frozen_after,
    }
    report_path = configured_path(config, "outputs", "input_download_report")
    write_json_atomic(report, report_path)
    print(json.dumps({key: value for key, value in report.items() if key != "frozen_inputs"}, indent=2))


if __name__ == "__main__":
    main()

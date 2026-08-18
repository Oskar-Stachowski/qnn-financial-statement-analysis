"""Download only SEC submission shards needed by PIT-B anchor provenance.

This utility does not rebuild or modify the research universe.  It reads the
current PIT-B artifact, identifies anchors with missing ``accepted_at`` and
downloads only historical SEC submission shards whose published date range
contains the anchor's filed date.
"""

from __future__ import annotations

import json
from pathlib import Path
import time

import pandas as pd
import requests


BASE_DIR = Path(__file__).resolve().parents[2]
ROWS_PATH = BASE_DIR / "data" / "interim" / "target_candidate_v2_pit_b.csv"
SUBMISSIONS_DIR = BASE_DIR / "data" / "raw" / "sec_submissions"
REPORT_PATH = BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_sec_shards.json"
URL_TEMPLATE = "https://data.sec.gov/submissions/{name}"
REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 0.13
HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}


def required_shards() -> dict[str, dict[str, str]]:
    columns = [
        "cik10",
        "anchor_t_filed",
        "anchor_t_accepted_at",
        "anchor_t1_filed",
        "anchor_t1_accepted_at",
    ]
    rows = pd.read_csv(ROWS_PATH, usecols=columns, dtype={"cik10": str}, low_memory=False)
    required: dict[str, dict[str, str]] = {}
    for _, row in rows.iterrows():
        cik10 = str(row["cik10"]).zfill(10)
        main_path = SUBMISSIONS_DIR / f"CIK{cik10}.json"
        if not main_path.exists():
            continue
        payload: dict | None = None
        for role in ("anchor_t", "anchor_t1"):
            if pd.notna(row[f"{role}_accepted_at"]):
                continue
            filed = str(row[f"{role}_filed"] or "")
            if not filed or filed == "nan":
                continue
            if payload is None:
                payload = json.loads(main_path.read_text(encoding="utf-8"))
            for metadata in payload.get("filings", {}).get("files", []):
                if str(metadata.get("filingFrom", "")) <= filed <= str(
                    metadata.get("filingTo", "")
                ):
                    name = str(metadata.get("name", "") or "")
                    if name:
                        required[name] = {
                            "cik10": cik10,
                            "filing_from": str(metadata.get("filingFrom", "")),
                            "filing_to": str(metadata.get("filingTo", "")),
                        }
    return required


def main() -> None:
    SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    required = required_shards()
    downloaded = 0
    cached = 0
    errors: list[dict[str, str]] = []

    for index, name in enumerate(sorted(required), start=1):
        path = SUBMISSIONS_DIR / name
        if path.exists():
            cached += 1
            continue
        url = URL_TEMPLATE.format(name=name)
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload = response.json()
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            downloaded += 1
        except Exception as error:  # network failures are reported, never hidden
            errors.append({"name": name, "url": url, "error": repr(error)})
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)
        if index % 100 == 0:
            print(f"SEC shard progress: {index}/{len(required)}", flush=True)

    report = {
        "required_shards": len(required),
        "downloaded": downloaded,
        "already_cached": cached,
        "errors": errors,
        "source": "https://data.sec.gov/submissions/",
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

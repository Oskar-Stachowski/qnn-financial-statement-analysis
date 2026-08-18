"""Download SEC 10-K source documents selected for the PIT-B revenue review.

This is an audit helper. It does not alter the target, research universe, or
production extraction. Documents are cached so the manual semantic review can
be reproduced from the exact accession used by target variant B.
"""

from __future__ import annotations

import json
from pathlib import Path
import time

import pandas as pd
import requests


BASE_DIR = Path(__file__).resolve().parents[2]
SAMPLE_PATH = (
    BASE_DIR
    / "data"
    / "reports"
    / "target_candidate_v2_pit_b_freeze_gate_revenue_manual_review.csv"
)
OUTPUT_DIR = BASE_DIR / "data" / "raw" / "sec_filings" / "revenue_review"
REPORT_PATH = (
    BASE_DIR
    / "data"
    / "reports"
    / "target_candidate_v2_pit_b_revenue_review_downloads.json"
)
REQUEST_TIMEOUT_SECONDS = 60
REQUEST_DELAY_SECONDS = 0.15
HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}


def filing_url(cik10: str, accession: str, primary_document: str) -> str:
    cik = str(int(cik10))
    accession_directory = accession.replace("-", "")
    return (
        "https://www.sec.gov/Archives/edgar/data/"
        f"{cik}/{accession_directory}/{primary_document}"
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    sample = pd.read_csv(SAMPLE_PATH, dtype={"cik10": str})
    results: list[dict[str, object]] = []

    for _, row in sample.iterrows():
        cik10 = str(row["cik10"]).zfill(10)
        accession = str(row["anchor_t1_accession"])
        primary_document = str(row["anchor_t1_primary_document"])
        url = filing_url(cik10, accession, primary_document)
        suffix = Path(primary_document).suffix or ".htm"
        output_path = OUTPUT_DIR / f"{cik10}_{accession}_{int(row['feature_year'])}{suffix}"
        result: dict[str, object] = {
            "cik10": cik10,
            "feature_year": int(row["feature_year"]),
            "accession": accession,
            "primary_document": primary_document,
            "url": url,
            "path": str(output_path.relative_to(BASE_DIR)),
        }
        if output_path.exists() and output_path.stat().st_size > 0:
            result["status"] = "cached"
        else:
            try:
                response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT_SECONDS)
                response.raise_for_status()
                output_path.write_bytes(response.content)
                result["status"] = "downloaded"
                result["bytes"] = len(response.content)
            except Exception as error:  # audit failures must remain visible
                result["status"] = "error"
                result["error"] = repr(error)
            finally:
                time.sleep(REQUEST_DELAY_SECONDS)
        results.append(result)

    report = {
        "sample_rows": int(len(sample)),
        "downloaded": sum(result["status"] == "downloaded" for result in results),
        "cached": sum(result["status"] == "cached" for result in results),
        "errors": sum(result["status"] == "error" for result in results),
        "documents": results,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "documents"}, indent=2))


if __name__ == "__main__":
    main()

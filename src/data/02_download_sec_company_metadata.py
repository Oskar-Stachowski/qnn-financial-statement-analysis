"""
Download SEC company metadata by unique CIK.

Input:
- data/interim/sec_unique_ciks.csv

Output:
- data/raw/sec_submissions/CIK{cik10}.json
- data/interim/sec_company_metadata.csv

This script uses unique CIKs from the ticker-CIK mapping step and downloads
official SEC submissions metadata for each company.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import time

import pandas as pd
import requests


SEC_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{cik10}.json"
REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 0.12

HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}


BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
INTERIM_DIR = BASE_DIR / "data" / "interim"
SUBMISSIONS_CACHE_DIR = RAW_DIR / "sec_submissions"

UNIQUE_CIKS_PATH = INTERIM_DIR / "sec_unique_ciks.csv"
OUTPUT_PATH = INTERIM_DIR / "sec_company_metadata.csv"

RAW_DIR.mkdir(parents=True, exist_ok=True)
INTERIM_DIR.mkdir(parents=True, exist_ok=True)
SUBMISSIONS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def format_list(value: object) -> str:
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def load_or_download_submission(cik10: str, cache_path: Path) -> dict:
    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    source_url = SEC_SUBMISSIONS_URL_TEMPLATE.format(cik10=cik10)
    try:
        response = requests.get(
            source_url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    finally:
        time.sleep(REQUEST_DELAY_SECONDS)

    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def build_metadata_record(
    row: pd.Series,
    payload: dict,
    source_url: str,
    cache_path: Path,
    downloaded_at: str,
) -> dict:
    return {
        "cik": row["cik"],
        "cik10": row["cik10"],
        "name_from_ticker_map": row["name"],
        "name_from_sec": payload.get("name"),
        "entity_type": payload.get("entityType"),
        "sic": payload.get("sic"),
        "sic_description": payload.get("sicDescription"),
        "fiscal_year_end": payload.get("fiscalYearEnd"),
        "tickers": format_list(payload.get("tickers")),
        "exchanges": format_list(payload.get("exchanges")),
        "source_url": source_url,
        "cache_path": str(cache_path),
        "download_status": "success",
        "downloaded_at": downloaded_at,
        "error_message": "",
    }


def build_error_record(
    row: pd.Series,
    source_url: str,
    cache_path: Path,
    downloaded_at: str,
    error: Exception,
) -> dict:
    return {
        "cik": row["cik"],
        "cik10": row["cik10"],
        "name_from_ticker_map": row["name"],
        "name_from_sec": "",
        "entity_type": "",
        "sic": "",
        "sic_description": "",
        "fiscal_year_end": "",
        "tickers": "",
        "exchanges": "",
        "source_url": source_url,
        "cache_path": str(cache_path),
        "download_status": "error",
        "downloaded_at": downloaded_at,
        "error_message": str(error)[:500],
    }


def main() -> None:
    unique_ciks = pd.read_csv(UNIQUE_CIKS_PATH, dtype={"cik10": str})
    unique_ciks["cik10"] = unique_ciks["cik10"].astype(str).str.zfill(10)
    unique_ciks = unique_ciks.drop_duplicates(subset=["cik10"]).sort_values("cik10")

    records = []

    for _, row in unique_ciks.iterrows():
        cik10 = row["cik10"]
        source_url = SEC_SUBMISSIONS_URL_TEMPLATE.format(cik10=cik10)
        cache_path = SUBMISSIONS_CACHE_DIR / f"CIK{cik10}.json"
        downloaded_at = datetime.now(timezone.utc).isoformat()

        try:
            payload = load_or_download_submission(cik10, cache_path)
            record = build_metadata_record(
                row=row,
                payload=payload,
                source_url=source_url,
                cache_path=cache_path,
                downloaded_at=downloaded_at,
            )
        except Exception as error:
            record = build_error_record(
                row=row,
                source_url=source_url,
                cache_path=cache_path,
                downloaded_at=downloaded_at,
                error=error,
            )

        records.append(record)

    metadata = pd.DataFrame(records)
    metadata.to_csv(OUTPUT_PATH, index=False, encoding="utf-8")

    print(f"Read unique CIKs: {UNIQUE_CIKS_PATH}")
    print(f"Saved company metadata: {OUTPUT_PATH}")
    print(f"Rows:   {len(metadata):,}")
    print(f"Errors: {(metadata['download_status'] == 'error').sum():,}")


if __name__ == "__main__":
    main()

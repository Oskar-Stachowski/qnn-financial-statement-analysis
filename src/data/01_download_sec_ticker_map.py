"""
Download SEC ticker-CIK mapping.

Input:
- SEC company_tickers.json

Output:
- data/raw/sec_company_tickers.json
- data/interim/sec_ticker_cik_map.csv

This script does not assign sectors or industries.
Sector/SIC metadata should be downloaded in a separate step using SEC submissions API.
"""

from datetime import datetime, timezone
from pathlib import Path
import json

import pandas as pd
import requests


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "gzip, deflate",
}


BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
INTERIM_DIR = BASE_DIR / "data" / "interim"

RAW_DIR.mkdir(parents=True, exist_ok=True)
INTERIM_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    response = requests.get(SEC_TICKERS_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    payload = response.json()

    raw_path = RAW_DIR / "sec_company_tickers.json"
    with raw_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    df = pd.DataFrame(payload.values())

    df = df.rename(
        columns={
            "cik_str": "cik",
            "ticker": "ticker",
            "title": "name",
        }
    )

    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["cik"] = df["cik"].astype(int)
    df["cik10"] = df["cik"].astype(str).str.zfill(10)
    df["source"] = "SEC company_tickers.json"
    downloaded_at = datetime.now(timezone.utc).isoformat()
    df["downloaded_at"] = downloaded_at

    df = df.drop_duplicates(subset=["ticker", "cik10"])

    df = df[["ticker", "cik", "cik10", "name", "downloaded_at"]].sort_values("ticker")

    output_path = INTERIM_DIR / "sec_ticker_cik_map.csv"
    df.to_csv(output_path, index=False, encoding="utf-8")

    unique_ciks = (
        df[["cik", "cik10", "name"]]
        .drop_duplicates(subset=["cik10"])
        .sort_values("cik10")
    )

    unique_ciks_path = INTERIM_DIR / "sec_unique_ciks.csv"
    unique_ciks.to_csv(unique_ciks_path, index=False, encoding="utf-8")

    print(f"Saved raw JSON: {raw_path}")
    print(f"Saved CSV map:  {output_path}")
    print(f"Saved unique CIKs: {unique_ciks_path}")
    print(df.head(10))

    print(f"Rows:           {len(df):,}")
    print(f"Unique CIKs:    {df['cik10'].nunique():,}")
    print(f"Unique tickers: {df['ticker'].nunique():,}")


if __name__ == "__main__":
    main()

"""
Download SEC Company Facts JSON files for the research universe.

Input:
- data/processed/research_universe.csv

Output:
- data/raw/companyfacts/CIK{cik10}.json

This script is the next data-pipeline step after 04_build_research_universe.py.
It reads CIK10 values from the research universe, downloads SEC Company Facts
JSON files, and keeps a simple local cache.
"""

from pathlib import Path
import csv
import json
import logging
import time

import requests


BASE_DIR = Path(__file__).resolve().parents[2]
PROCESSED_DIR = BASE_DIR / "data" / "processed"
RAW_DIR = BASE_DIR / "data" / "raw"

INPUT_PATH = PROCESSED_DIR / "research_universe.csv"
OUTPUT_DIR = RAW_DIR / "companyfacts"

COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept": "application/json",
}

REQUEST_TIMEOUT_SECONDS = 30
REQUEST_DELAY_SECONDS = 0.1
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.0
PROGRESS_EVERY_FILES = 100

LOGGER = logging.getLogger(__name__)


def normalize_cik(cik: str | int) -> str:
    """Return a SEC CIK padded to 10 digits."""
    text = str(cik).strip()
    if text.upper().startswith("CIK"):
        text = text[3:]
    text = text.strip()

    if not text.isdigit():
        raise ValueError(f"Invalid CIK: {cik!r}")
    if len(text) > 10:
        raise ValueError(f"CIK is longer than 10 digits: {cik!r}")

    return text.zfill(10)


def read_research_universe_ciks(input_path: Path) -> list[str]:
    """Read unique cik10 values from the research-universe CSV."""
    with input_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "cik10" not in (reader.fieldnames or []):
            raise ValueError(f"Missing required column 'cik10' in {input_path}")

        ciks = [
            normalize_cik(row["cik10"])
            for row in reader
            if row.get("cik10")
        ]

    return sorted(set(ciks))


def fetch_company_facts(cik10: str) -> bytes:
    """Download one SEC Company Facts JSON file."""
    url = COMPANY_FACTS_URL_TEMPLATE.format(cik10=cik10)

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.content
        except requests.HTTPError as error:
            status_code = error.response.status_code if error.response else None
            should_retry = status_code == 429 or (
                status_code is not None and 500 <= status_code < 600
            )
            if not should_retry or attempt == MAX_RETRIES:
                raise
        except requests.RequestException:
            if attempt == MAX_RETRIES:
                raise

        time.sleep(BACKOFF_FACTOR * (2**attempt))

    raise RuntimeError("unreachable retry state")


def company_facts_path(cik10: str) -> Path:
    return OUTPUT_DIR / f"CIK{cik10}.json"


def write_company_facts_json(output_path: Path, content: bytes) -> None:
    payload = json.loads(content)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def migrate_legacy_companyfacts_files() -> int:
    """Rename old {cik10}.json files to CIK{cik10}.json."""
    migrated = 0

    for legacy_path in OUTPUT_DIR.glob("*.json"):
        if legacy_path.name.startswith("CIK"):
            continue

        cik10 = normalize_cik(legacy_path.stem)
        readable_path = company_facts_path(cik10)

        if readable_path.exists():
            continue

        legacy_path.rename(readable_path)
        migrated += 1

    return migrated


def count_cached_companyfacts_files() -> int:
    return sum(1 for _ in OUTPUT_DIR.glob("CIK*.json"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not INPUT_PATH.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_PATH}. "
            "Run 04_build_research_universe.py first."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ciks = read_research_universe_ciks(INPUT_PATH)
    migrated = migrate_legacy_companyfacts_files()
    existing_files = count_cached_companyfacts_files()

    successes = 0
    errors = 0
    skipped = 0

    for cik10 in ciks:
        output_path = company_facts_path(cik10)

        if output_path.exists():
            skipped += 1
            continue

        try:
            content = fetch_company_facts(cik10)
        except requests.RequestException as error:
            errors += 1
            LOGGER.error("Failed to download Company Facts for CIK %s: %s", cik10, error)
        else:
            write_company_facts_json(output_path, content)
            successes += 1
            created_files = existing_files + successes
            if created_files % PROGRESS_EVERY_FILES == 0:
                print(f"Company Facts files created: {created_files:,} / {len(ciks):,}")
        finally:
            time.sleep(REQUEST_DELAY_SECONDS)

    print(f"Read research universe: {INPUT_PATH}")
    print(f"Saved Company Facts to: {OUTPUT_DIR}")
    print(f"CIKs:                   {len(ciks):,}")
    print(f"Existing at start:      {existing_files:,}")
    print(f"Renamed legacy files:   {migrated:,}")
    print(f"Downloaded:             {successes:,}")
    print(f"Skipped cached:         {skipped:,}")
    print(f"Errors:                 {errors:,}")


if __name__ == "__main__":
    main()

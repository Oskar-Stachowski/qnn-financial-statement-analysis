"""Download SEC Company Facts JSON files with a simple local cache."""

from __future__ import annotations

import argparse
import csv
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
DEFAULT_OUTPUT_DIR = Path("data/raw/companyfacts")
DEFAULT_USER_AGENT = (
    "qnn-financial-statement-analysis/0.1 "
    "(academic research; set SEC_USER_AGENT with contact email)"
)
SEC_MAX_REQUESTS_PER_SECOND = 10.0

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadSummary:
    successes: int = 0
    errors: int = 0
    skipped: int = 0


class RateLimiter:
    """Sequential limiter for SEC's 10 requests/second fair-access rule."""

    def __init__(self, requests_per_second: float = SEC_MAX_REQUESTS_PER_SECOND) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        if requests_per_second > SEC_MAX_REQUESTS_PER_SECOND:
            raise ValueError(
                f"requests_per_second must not exceed SEC limit of {SEC_MAX_REQUESTS_PER_SECOND:g}"
            )
        self._min_interval = 1.0 / requests_per_second
        self._last_request_at: float | None = None

    def wait(self) -> None:
        if self._last_request_at is None:
            self._last_request_at = time.monotonic()
            return

        elapsed = time.monotonic() - self._last_request_at
        remaining = self._min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_at = time.monotonic()


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


def read_ciks_from_csv(input_path: str | Path) -> list[str]:
    """Read CIK values from a CSV file.

    If the file has a column named ``cik`` (case-insensitive), that column is
    used. Otherwise the first column is treated as the CIK source.
    """
    path = Path(input_path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return []

        cik_index = _find_cik_column(header)
        if cik_index is None:
            cik_index = 0
            rows = [header]
        else:
            rows = []

        rows.extend(row for row in reader)

    return [row[cik_index].strip() for row in rows if len(row) > cik_index and row[cik_index].strip()]


def download_company_facts(
    ciks: Iterable[str | int],
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    *,
    force: bool = False,
    user_agent: str | None = None,
    requests_per_second: float = SEC_MAX_REQUESTS_PER_SECOND,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
) -> DownloadSummary:
    """Download SEC Company Facts JSON files for the given CIK values."""
    resolved_user_agent = user_agent or os.environ.get("SEC_USER_AGENT") or DEFAULT_USER_AGENT
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    successes = 0
    errors = 0
    skipped = 0
    limiter = RateLimiter(requests_per_second)

    for raw_cik in ciks:
        try:
            cik = normalize_cik(raw_cik)
        except ValueError as exc:
            errors += 1
            LOGGER.error("%s", exc)
            continue

        target_file = output_path / f"{cik}.json"
        if target_file.exists() and not force:
            skipped += 1
            LOGGER.info("Skipping cached Company Facts for CIK %s", cik)
            continue

        try:
            content = _fetch_company_facts(
                cik,
                user_agent=resolved_user_agent,
                limiter=limiter,
                max_retries=max_retries,
                backoff_factor=backoff_factor,
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            errors += 1
            LOGGER.error("Failed to download Company Facts for CIK %s: %s", cik, exc)
            continue

        target_file.write_bytes(content)
        successes += 1
        LOGGER.info("Saved Company Facts for CIK %s to %s", cik, target_file)

    summary = DownloadSummary(successes=successes, errors=errors, skipped=skipped)
    LOGGER.info(
        "SEC Company Facts download finished: successes=%s errors=%s skipped=%s",
        summary.successes,
        summary.errors,
        summary.skipped,
    )
    return summary


def _fetch_company_facts(
    cik: str,
    *,
    user_agent: str,
    limiter: RateLimiter,
    max_retries: int,
    backoff_factor: float,
) -> bytes:
    url = BASE_URL.format(cik=cik)
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "application/json",
        },
    )

    for attempt in range(max_retries + 1):
        try:
            limiter.wait()
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            if not _should_retry_http(exc.code) or attempt == max_retries:
                raise
            _sleep_before_retry(attempt, backoff_factor)
        except (URLError, TimeoutError):
            if attempt == max_retries:
                raise
            _sleep_before_retry(attempt, backoff_factor)

    raise RuntimeError("unreachable retry state")


def _find_cik_column(header: list[str]) -> int | None:
    for index, column_name in enumerate(header):
        normalized = column_name.strip().lower()
        if normalized in {"cik", "central index key"}:
            return index
    return None


def _should_retry_http(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


def _sleep_before_retry(attempt: int, backoff_factor: float) -> None:
    delay = backoff_factor * (2**attempt)
    if delay > 0:
        time.sleep(delay)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download SEC Company Facts JSON files.")
    parser.add_argument("--input", required=True, help="CSV file with a CIK column or CIKs in the first column.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="Output cache directory.")
    parser.add_argument("--force", action="store_true", help="Re-download files already present in the cache.")
    parser.add_argument(
        "--user-agent",
        default=None,
        help="SEC User-Agent header. Defaults to SEC_USER_AGENT env var or a project default.",
    )
    parser.add_argument(
        "--requests-per-second",
        type=float,
        default=SEC_MAX_REQUESTS_PER_SECOND,
        help="Request limit. SEC fair access currently allows up to 10 requests/second.",
    )
    args = parser.parse_args(argv)
    if args.requests_per_second > SEC_MAX_REQUESTS_PER_SECOND:
        parser.error(f"--requests-per-second must not exceed {SEC_MAX_REQUESTS_PER_SECOND:g}")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    ciks = read_ciks_from_csv(args.input)
    summary = download_company_facts(
        ciks,
        output_dir=args.output,
        force=args.force,
        user_agent=args.user_agent,
        requests_per_second=args.requests_per_second,
    )
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

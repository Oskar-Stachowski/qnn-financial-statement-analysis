"""Download the minimum SEC source material for the filing-first universe.

The SEC Financial Statement Data Set quarterly ZIP files are several gigabytes
in aggregate.  This script uses HTTP byte ranges and ZIP central-directory
metadata to extract only ``sub.txt``.  It therefore avoids redownloading the
facts, numbers, presentation, and tag tables that are irrelevant to universe
membership.

For original 10-K filings not represented completely in SUB, only the leading
SEC submission header is downloaded from EDGAR.  Every downloaded source is
cached; reruns are incremental.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import threading
import time
from typing import Any
import zipfile

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests

from historical_research_universe import (
    load_policy,
    parse_master_index,
    parse_scope,
    read_fsds_sub,
    utc_now_iso,
)


BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw" / "sec_historical_universe"
INDEX_DIR = RAW_DIR / "full_index"
SUB_DIR = RAW_DIR / "fsds_sub"
HEADER_DIR = RAW_DIR / "filing_headers"
SIC_LIST_PATH = RAW_DIR / "sec_sic_code_list.html"
MANIFEST_PATH = BASE_DIR / "data" / "reports" / "research_universe_pit_sources.json"

REQUEST_TIMEOUT_SECONDS = 60
REQUEST_DELAY_SECONDS = 0.11
MAX_RANGE_BYTES = 2 * 1024 * 1024
MAX_HEADER_BYTES = 2 * 1024 * 1024
HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "identity",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_complete_sec_header(path: Path) -> bool:
    if not path.exists() or not path.stat().st_size:
        return False
    with path.open("rb") as stream:
        stream.seek(max(path.stat().st_size - 64, 0))
        return b"</SEC-HEADER>" in stream.read().upper()


def aggregate_paths_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        if not has_complete_sec_header(path):
            continue
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_path(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


class PoliteSession:
    """Small rate-limited SEC client with explicit, bounded retries."""

    def __init__(self) -> None:
        self.local = threading.local()
        self.lock = threading.Lock()
        self.last_request_at = 0.0
        self.request_count = 0
        self.bytes_received = 0

    def _session(self) -> requests.Session:
        if not hasattr(self.local, "session"):
            self.local.session = requests.Session()
        return self.local.session

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        merged_headers = dict(HEADERS)
        merged_headers.update(kwargs.pop("headers", {}))
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with self.lock:
                    elapsed = time.monotonic() - self.last_request_at
                    if elapsed < REQUEST_DELAY_SECONDS:
                        time.sleep(REQUEST_DELAY_SECONDS - elapsed)
                    self.last_request_at = time.monotonic()
                    self.request_count += 1
                response = self._session().get(
                    url,
                    headers=merged_headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    **kwargs,
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    response.close()
                    time.sleep(1.0 * (attempt + 1))
                    continue
                return response
            except requests.RequestException as error:
                last_error = error
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"SEC request failed after three attempts: {url}") from last_error


class HttpRangeReader(io.RawIOBase):
    """Seekable read-only HTTP object backed by bounded Range requests."""

    def __init__(self, url: str, client: PoliteSession) -> None:
        self.url = url
        self.client = client
        self.position = 0
        response = client.get(
            url,
            headers={"Range": "bytes=0-0"},
            stream=True,
        )
        try:
            if response.status_code != 206:
                raise RuntimeError(
                    f"SEC server did not honor HTTP Range for {url}: "
                    f"status={response.status_code}"
                )
            content_range = response.headers.get("Content-Range", "")
            if "/" not in content_range:
                raise RuntimeError(f"Missing total size in Content-Range: {content_range}")
            self.length = int(content_range.rsplit("/", 1)[1])
            one_byte = response.raw.read(1)
            client.bytes_received += len(one_byte)
        finally:
            response.close()

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self.position + offset
        elif whence == io.SEEK_END:
            position = self.length + offset
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        if position < 0:
            raise ValueError("Negative seek position")
        self.position = min(position, self.length)
        return self.position

    def read(self, size: int = -1) -> bytes:
        if self.position >= self.length:
            return b""
        if size is None or size < 0:
            size = self.length - self.position
        if size == 0:
            return b""
        size = min(size, MAX_RANGE_BYTES, self.length - self.position)
        start = self.position
        end = start + size - 1
        response = self.client.get(
            self.url,
            headers={"Range": f"bytes={start}-{end}"},
            stream=True,
        )
        try:
            if response.status_code != 206:
                raise RuntimeError(
                    f"SEC server stopped honoring Range for {self.url}: "
                    f"status={response.status_code}"
                )
            payload = response.content
            with self.client.lock:
                self.client.bytes_received += len(payload)
        finally:
            response.close()
        if len(payload) > size:
            payload = payload[:size]
        self.position += len(payload)
        return payload


def download_text(client: PoliteSession, url: str, path: Path) -> str:
    if path.exists() and path.stat().st_size:
        return "cached"
    response = client.get(url)
    try:
        response.raise_for_status()
        payload = response.content
        with client.lock:
            client.bytes_received += len(payload)
    finally:
        response.close()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return "downloaded"


def extract_remote_sub(client: PoliteSession, url: str, path: Path) -> str:
    if path.exists() and path.stat().st_size:
        return "cached"
    remote = HttpRangeReader(url, client)
    with zipfile.ZipFile(remote) as archive:
        candidates = [name for name in archive.namelist() if name.lower() == "sub.txt"]
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one sub.txt in {url}; found {candidates}")
        payload = archive.read(candidates[0])
    if not payload.startswith(b"adsh\t"):
        raise RuntimeError(f"Extracted SUB has an unexpected header: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return "downloaded"


def download_submission_header(
    client: PoliteSession,
    url: str,
    path: Path,
) -> str:
    if path.exists() and path.stat().st_size:
        if has_complete_sec_header(path):
            return "cached"
    response = client.get(
        url,
        headers={"Range": f"bytes=0-{MAX_HEADER_BYTES - 1}"},
        stream=True,
    )
    try:
        response.raise_for_status()
        payload = bytearray()
        for chunk in response.iter_content(chunk_size=16 * 1024):
            if not chunk:
                continue
            remaining = MAX_HEADER_BYTES - len(payload)
            payload.extend(chunk[:remaining])
            upper = bytes(payload).upper()
            closing = upper.find(b"</SEC-HEADER>")
            if closing >= 0:
                payload = payload[: closing + len(b"</SEC-HEADER>")]
                break
            if len(payload) >= MAX_HEADER_BYTES:
                break
        with client.lock:
            client.bytes_received += len(payload)
    finally:
        response.close()
    if not payload:
        raise RuntimeError(f"Empty SEC submission header: {url}")
    if b"</SEC-HEADER>" not in bytes(payload).upper():
        raise RuntimeError(
            f"SEC submission header exceeds the {MAX_HEADER_BYTES:,}-byte safety bound: {url}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(bytes(payload))
    temporary.replace(path)
    return "downloaded"


def headers_needed(master: pd.DataFrame, sub: pd.DataFrame) -> pd.DataFrame:
    columns = ["accession", "sic", "accepted", "period", "fy", "fp"]
    registrants_per_accession = master.groupby("accession")["cik10_master"].transform(
        "nunique"
    )
    joined = master.assign(
        joint_filing=registrants_per_accession.gt(1)
    ).merge(sub[columns], on="accession", how="left", validate="many_to_one")
    missing_sub = joined["sic"].isna()
    incomplete = (
        joined["sic"].fillna("").eq("")
        | joined["accepted"].fillna("").eq("")
        | (
            joined["period"].fillna("").eq("")
            & joined["fy"].fillna("").eq("")
        )
    )
    return joined[missing_sub | incomplete | joined["joint_filing"]][
        ["accession", "archive_filename"]
    ].drop_duplicates("accession")


def main() -> None:
    policy = load_policy()
    scope = parse_scope(policy)
    client = PoliteSession()
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    SUB_DIR.mkdir(parents=True, exist_ok=True)
    HEADER_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    source_records: list[dict[str, object]] = []
    master_frames: list[pd.DataFrame] = []
    sub_frames: list[pd.DataFrame] = []
    errors: list[dict[str, str]] = []

    sic_url = policy["sources"]["sic_list_url"]
    sic_status = download_text(client, sic_url, SIC_LIST_PATH)
    source_records.append(
        {
            "kind": "official_sec_sic_code_list",
            "period": "static_reference",
            "url": sic_url,
            "path": str(SIC_LIST_PATH.relative_to(BASE_DIR)),
            "status": sic_status,
            "bytes": SIC_LIST_PATH.stat().st_size,
            "sha256": sha256_path(SIC_LIST_PATH),
        }
    )

    for year in range(scope.filing_index_year_start, scope.filing_index_year_end + 1):
        for quarter in range(1, 5):
            label = f"{year}q{quarter}"
            index_path = INDEX_DIR / f"{label}_master.idx"
            sub_path = SUB_DIR / f"{label}_sub.txt"
            index_url = policy["sources"]["full_index_url"].format(
                year=year, quarter=quarter
            )
            sub_url = policy["sources"]["fsds_url"].format(
                year=year, quarter=quarter
            )
            try:
                index_status = download_text(client, index_url, index_path)
                sub_status = extract_remote_sub(client, sub_url, sub_path)
                master_frames.append(
                    parse_master_index(
                        index_path.read_text(encoding="latin-1"),
                        index_year=year,
                        index_quarter=quarter,
                        qualifying_forms=scope.qualifying_forms,
                    )
                )
                sub_frames.append(
                    read_fsds_sub(sub_path, source_year=year, source_quarter=quarter)
                )
                source_records.extend(
                    [
                        {
                            "kind": "master_index",
                            "period": label,
                            "url": index_url,
                            "path": str(index_path.relative_to(BASE_DIR)),
                            "status": index_status,
                            "bytes": index_path.stat().st_size,
                            "sha256": sha256_path(index_path),
                        },
                        {
                            "kind": "fsds_sub_only",
                            "period": label,
                            "url": sub_url,
                            "path": str(sub_path.relative_to(BASE_DIR)),
                            "status": sub_status,
                            "bytes": sub_path.stat().st_size,
                            "sha256": sha256_path(sub_path),
                        },
                    ]
                )
            except Exception as error:
                errors.append({"period": label, "error": repr(error)})
                print(f"ERROR {label}: {error!r}", flush=True)
                continue
            print(
                f"SEC source progress {label}: index={index_status}, sub={sub_status}",
                flush=True,
            )

    if errors:
        raise RuntimeError(f"Historical SEC source download failed: {errors}")
    master = pd.concat(master_frames, ignore_index=True)
    sub = pd.concat(sub_frames, ignore_index=True)
    sub = sub.sort_values(["fsds_source_year", "fsds_source_quarter"]).drop_duplicates(
        "accession", keep="last"
    )

    needed = headers_needed(master, sub)
    print(
        f"Same-accession header fallbacks required: {len(needed):,}",
        flush=True,
    )
    header_downloaded = 0
    header_cached = 0
    header_lock = threading.Lock()

    def fetch_header(row: object) -> tuple[str, str, str, str | None]:
        accession = str(getattr(row, "accession"))
        archive_filename = str(getattr(row, "archive_filename"))
        path = HEADER_DIR / f"{accession}.txt"
        url = policy["sources"]["sec_archive_url"].format(
            filename=archive_filename
        )
        try:
            status = download_submission_header(client, url, path)
        except Exception as error:
            return accession, url, "error", repr(error)
        return accession, url, status, None

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(fetch_header, row) for row in needed.itertuples(index=False)]
        for position, future in enumerate(as_completed(futures), start=1):
            accession, url, status, error = future.result()
            with header_lock:
                if error:
                    errors.append(
                        {"accession": accession, "url": url, "error": error}
                    )
                    print(f"ERROR header {accession}: {error}", flush=True)
                else:
                    header_downloaded += int(status == "downloaded")
                    header_cached += int(status == "cached")
                if position % 500 == 0 or position == len(needed):
                    print(
                        f"SEC header progress {position:,}/{len(needed):,}",
                        flush=True,
                    )

    required_header_paths = [
        HEADER_DIR / f"{accession}.txt" for accession in needed["accession"]
    ]
    complete_header_count = sum(
        has_complete_sec_header(path)
        for path in required_header_paths
    )
    manifest = {
        "created_at": utc_now_iso(),
        "policy_id": policy["historical_universe"]["id"],
        "policy_version": policy["historical_universe"]["version"],
        "source_strategy": {
            "filing_census": "SEC quarterly master.idx",
            "historical_metadata": "quarterly FSDS sub.txt",
            "fsds_transfer": "HTTP Range extraction of sub.txt only",
            "header_fallback": "bounded leading bytes of same EDGAR accession",
        },
        "master_10k_rows": int(len(master)),
        "master_unique_accessions": int(master["accession"].nunique()),
        "fsds_10k_rows": int(len(sub)),
        "fallback_headers_required": int(len(needed)),
        "fallback_headers_complete": complete_header_count,
        "fallback_headers_complete_bytes": sum(
            path.stat().st_size
            for path in required_header_paths
            if has_complete_sec_header(path)
        ),
        "fallback_headers_aggregate_sha256": aggregate_paths_sha256(
            required_header_paths
        ),
        "fallback_headers_downloaded_this_run": header_downloaded,
        "fallback_headers_cached_this_run": header_cached,
        "http_requests_this_run": client.request_count,
        "http_bytes_received_this_run": client.bytes_received,
        "sources": source_records,
        "errors": errors,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key != "sources"}, indent=2))
    if errors:
        print(
            f"WARNING: {len(errors)} same-accession headers remain unavailable; "
            "their registrants will be retained as ambiguous/NA",
            flush=True,
        )


if __name__ == "__main__":
    main()

"""Download narrowly scoped SEC evidence for the registrant-role audit.

Only accessions that are both eligible in the historical universe and marked
as joint filings are considered.  The script does not download Company Facts,
does not construct X_t, and does not read or modify the frozen PIT-B target.

For every unique joint accession it caches:

* the EDGAR directory index and filing index page;
* the compressed XBRL package when the accession has XBRL; or
* the primary original 10-K only for the small non-XBRL subset.

The full primary document is intentionally not downloaded for every XBRL
filing.  The XBRL package carries the entity identifiers and statement
structure needed for the all-case screen; primary documents are reserved for
the later targeted manual review.

Reruns are incremental and all downloaded files are covered by a manifest.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import threading
import time
from typing import Any

import pandas as pd
import requests


BASE_DIR = Path(__file__).resolve().parents[2]
UNIVERSE_PATH = BASE_DIR / "data" / "processed" / "research_universe_pit.csv"
EVIDENCE_DIR = (
    BASE_DIR / "data" / "raw" / "sec_historical_universe" / "registrant_role_evidence"
)
MANIFEST_PATH = (
    BASE_DIR / "data" / "reports" / "research_universe_pit_registrant_evidence.json"
)

SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
HEADERS = {
    "User-Agent": "Oskar Stachowski oskar.g.stachowski@gmail.com",
    "Accept-Encoding": "identity",
}
REQUEST_TIMEOUT_SECONDS = 90
REQUEST_DELAY_SECONDS = 0.13


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now_iso() -> str:
    return pd.Timestamp.now(tz="UTC").isoformat()


class PoliteSession:
    """Globally rate-limited SEC client with bounded retries."""

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

    def get(self, url: str) -> requests.Response:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                with self.lock:
                    elapsed = time.monotonic() - self.last_request_at
                    if elapsed < REQUEST_DELAY_SECONDS:
                        time.sleep(REQUEST_DELAY_SECONDS - elapsed)
                    self.last_request_at = time.monotonic()
                    self.request_count += 1
                response = self._session().get(
                    url,
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                if response.status_code in {429, 500, 502, 503, 504}:
                    response.close()
                    time.sleep(float(attempt + 1))
                    continue
                return response
            except requests.RequestException as error:
                last_error = error
                time.sleep(float(attempt + 1))
        raise RuntimeError(f"SEC request failed after four attempts: {url}") from last_error


def download(client: PoliteSession, url: str, path: Path) -> str:
    if path.exists() and path.stat().st_size:
        return "cached"
    response = client.get(url)
    try:
        response.raise_for_status()
        payload = response.content
    finally:
        response.close()
    with client.lock:
        client.bytes_received += len(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return "downloaded"


def strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def primary_10k_filename(index_html: str) -> str:
    """Return the document whose filing-index Type column is exactly 10-K."""

    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", index_html, flags=re.I | re.S):
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.I | re.S)
        if len(cells) < 4:
            continue
        values = [strip_html(cell) for cell in cells]
        if values[-2].upper() != "10-K":
            continue
        hrefs = re.findall(r"href=[\"']([^\"']+)[\"']", row, flags=re.I)
        if hrefs:
            return Path(hrefs[0]).name
    return ""


def archive_cik_candidates(rows: pd.DataFrame) -> list[str]:
    primary = rows.loc[
        rows["registrant_role"].eq("primary_xbrl_registrant"), "cik10"
    ].astype(str)
    all_ciks = rows["cik10"].astype(str)
    ordered = list(primary) + list(all_ciks)
    return list(dict.fromkeys(str(int(cik)) for cik in ordered if cik.isdigit()))


def select_index_directory(
    client: PoliteSession,
    accession: str,
    cik_candidates: list[str],
    accession_dir: Path,
) -> tuple[str, str, dict[str, Any]]:
    accession_compact = accession.replace("-", "")
    cached = accession_dir / "index.json"
    if cached.exists() and cached.stat().st_size:
        payload = json.loads(cached.read_text(encoding="utf-8"))
        source = json.loads((accession_dir / "source.json").read_text(encoding="utf-8"))
        return source["archive_cik"], source["base_url"], payload

    errors: list[str] = []
    for cik in cik_candidates:
        base_url = f"{SEC_ARCHIVES}/{cik}/{accession_compact}"
        response = client.get(f"{base_url}/index.json")
        try:
            if response.status_code == 200:
                payload_bytes = response.content
                with client.lock:
                    client.bytes_received += len(payload_bytes)
                payload = response.json()
                accession_dir.mkdir(parents=True, exist_ok=True)
                temporary = cached.with_suffix(".json.tmp")
                temporary.write_bytes(payload_bytes)
                temporary.replace(cached)
                source = {"archive_cik": cik, "base_url": base_url}
                (accession_dir / "source.json").write_text(
                    json.dumps(source, indent=2), encoding="utf-8"
                )
                return cik, base_url, payload
            errors.append(f"{cik}:{response.status_code}")
        finally:
            response.close()
    raise RuntimeError(
        f"No EDGAR directory found for {accession}; attempts={','.join(errors)}"
    )


def download_accession(
    client: PoliteSession,
    accession: str,
    rows: pd.DataFrame,
    include_primary_all: bool,
) -> dict[str, Any]:
    accession_dir = EVIDENCE_DIR / accession
    accession_dir.mkdir(parents=True, exist_ok=True)
    archive_cik, base_url, directory = select_index_directory(
        client, accession, archive_cik_candidates(rows), accession_dir
    )
    items = {
        str(item.get("name", "")): item
        for item in directory.get("directory", {}).get("item", [])
    }
    index_name = f"{accession}-index.html"
    if index_name not in items:
        alternatives = [name for name in items if name.endswith("-index.html")]
        if len(alternatives) != 1:
            raise RuntimeError(f"Cannot identify filing index for {accession}")
        index_name = alternatives[0]
    index_path = accession_dir / index_name
    index_status = download(client, f"{base_url}/{index_name}", index_path)
    primary_name = primary_10k_filename(index_path.read_text(encoding="latin-1"))
    if not primary_name or primary_name not in items:
        raise RuntimeError(f"Cannot identify primary 10-K document for {accession}")

    wanted: dict[str, str] = {}
    instance_names = sorted(
        {
            str(value)
            for value in rows["xbrl_instance"].dropna()
            if str(value).strip() and str(value) in items
        }
    )
    if len(instance_names) == 1:
        xbrl_zip_names = sorted(name for name in items if name.endswith("-xbrl.zip"))
        if len(xbrl_zip_names) == 1:
            wanted["xbrl_package"] = xbrl_zip_names[0]
        else:
            wanted["xbrl_instance"] = instance_names[0]
    elif len(instance_names) > 1:
        raise RuntimeError(f"Multiple FSDS instance names for {accession}: {instance_names}")
    else:
        wanted["primary_10k"] = primary_name
    if include_primary_all:
        wanted["primary_10k"] = primary_name

    files: dict[str, Any] = {}
    for role, filename in wanted.items():
        path = accession_dir / filename
        status = download(client, f"{base_url}/{filename}", path)
        files[role] = {
            "filename": filename,
            "status": status,
            "bytes": path.stat().st_size,
            "sha256": sha256_path(path),
        }
    files["filing_index"] = {
        "filename": index_name,
        "status": index_status,
        "bytes": index_path.stat().st_size,
        "sha256": sha256_path(index_path),
    }
    return {
        "accession": accession,
        "feature_year": int(rows["feature_year"].iloc[0]),
        "archive_cik": archive_cik.zfill(10),
        "eligible_registrants": int(len(rows)),
        "eligible_ciks": sorted(rows["cik10"].astype(str).tolist()),
        "accession_registrant_count": int(rows["accession_registrant_count"].max()),
        "primary_10k_filename": primary_name,
        "files": files,
        "status": "complete",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--include-primary-all",
        action="store_true",
        help="also cache the primary 10-K for every XBRL joint accession",
    )
    args = parser.parse_args()
    universe = pd.read_csv(UNIVERSE_PATH, dtype={"cik10": str}, low_memory=False)
    joint = universe.loc[
        universe["membership_status"].eq("eligible")
        & universe["joint_filing_flag"].fillna(False)
    ].copy()
    grouped = list(joint.groupby("accession", sort=True))
    client = PoliteSession()
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(
                download_accession,
                client,
                accession,
                rows,
                args.include_primary_all,
            ): accession
            for accession, rows in grouped
        }
        for number, future in enumerate(as_completed(futures), start=1):
            accession = futures[future]
            try:
                records.append(future.result())
            except Exception as error:  # preserve a complete audit trail
                failures.append({"accession": accession, "error": repr(error)})
            if number % 25 == 0 or number == len(futures):
                print(
                    f"completed={number}/{len(futures)} "
                    f"failures={len(failures)} requests={client.request_count}"
                )

    manifest = {
        "created_at": utc_now_iso(),
        "scope": (
            "eligible joint_filing_flag=True accessions; primary 10-K for all"
            if args.include_primary_all
            else "eligible joint_filing_flag=True accessions; compressed XBRL or non-XBRL primary"
        ),
        "universe_path": str(UNIVERSE_PATH.relative_to(BASE_DIR)),
        "universe_sha256": sha256_path(UNIVERSE_PATH),
        "accessions_expected": len(grouped),
        "accessions_complete": len(records),
        "accessions_failed": len(failures),
        "requests_this_run": client.request_count,
        "bytes_received_this_run": client.bytes_received,
        "records": sorted(records, key=lambda item: item["accession"]),
        "failures": sorted(failures, key=lambda item: item["accession"]),
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in manifest.items() if key not in {"records"}}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

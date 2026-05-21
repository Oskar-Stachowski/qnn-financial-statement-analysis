"""
Inventory XBRL tags from SEC Company Facts JSON files.

Input:
- data/raw/companyfacts/CIK{cik10}.json

Output:
- data/reports/xbrl_tag_inventory.csv

This script does not map XBRL tags to financial variables. It only summarizes
which tags, units and filing forms are present in the downloaded SEC Company
Facts files.
"""

from collections import defaultdict
from pathlib import Path
import csv
import json


BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
REPORTS_DIR = BASE_DIR / "data" / "reports"

COMPANYFACTS_DIR = RAW_DIR / "companyfacts"
OUTPUT_PATH = REPORTS_DIR / "xbrl_tag_inventory.csv"

PROGRESS_EVERY_FILES = 100


OUTPUT_COLUMNS = [
    "namespace",
    "tag",
    "label",
    "description",
    "units",
    "forms",
    "company_count",
    "company_year_count",
    "fact_count",
]


def normalize_cik10(value: object, source_path: Path) -> str:
    if value is None:
        return source_path.stem.replace("CIK", "")

    text = str(value).strip()
    if text.upper().startswith("CIK"):
        text = text[3:]

    return text.zfill(10)


def get_company_year(fact: dict) -> str:
    fiscal_year = fact.get("fy")
    if fiscal_year not in (None, ""):
        return str(fiscal_year)

    end_date = str(fact.get("end", ""))
    if len(end_date) >= 4 and end_date[:4].isdigit():
        return end_date[:4]

    return ""


def sorted_semicolon(values: set[str]) -> str:
    return ";".join(sorted(value for value in values if value))


def update_inventory(
    inventory: dict,
    namespace: str,
    tag: str,
    tag_payload: dict,
    cik10: str,
) -> None:
    key = (namespace, tag)
    record = inventory[key]

    if not record["label"]:
        record["label"] = str(tag_payload.get("label", "") or "")
    if not record["description"]:
        record["description"] = str(tag_payload.get("description", "") or "")

    record["companies"].add(cik10)

    units = tag_payload.get("units", {})
    if not isinstance(units, dict):
        return

    for unit, facts in units.items():
        record["units"].add(str(unit))

        if not isinstance(facts, list):
            continue

        record["fact_count"] += len(facts)

        for fact in facts:
            if not isinstance(fact, dict):
                continue

            form = str(fact.get("form", "") or "")
            company_year = get_company_year(fact)

            if form:
                record["forms"].add(form)
            if company_year:
                record["company_years"].add((cik10, company_year))


def inventory_companyfacts_file(path: Path, inventory: dict) -> None:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    cik10 = normalize_cik10(payload.get("cik"), path)
    facts = payload.get("facts", {})

    if not isinstance(facts, dict):
        return

    for namespace, namespace_payload in facts.items():
        if not isinstance(namespace_payload, dict):
            continue

        for tag, tag_payload in namespace_payload.items():
            if not isinstance(tag_payload, dict):
                continue

            update_inventory(
                inventory=inventory,
                namespace=str(namespace),
                tag=str(tag),
                tag_payload=tag_payload,
                cik10=cik10,
            )


def build_inventory_rows(inventory: dict) -> list[dict]:
    rows = []

    for (namespace, tag), record in inventory.items():
        rows.append(
            {
                "namespace": namespace,
                "tag": tag,
                "label": record["label"],
                "description": record["description"],
                "units": sorted_semicolon(record["units"]),
                "forms": sorted_semicolon(record["forms"]),
                "company_count": len(record["companies"]),
                "company_year_count": len(record["company_years"]),
                "fact_count": record["fact_count"],
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            row["namespace"],
            row["tag"],
        ),
    )


def write_inventory(rows: list[dict]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if not COMPANYFACTS_DIR.exists():
        raise FileNotFoundError(
            f"Company Facts directory not found: {COMPANYFACTS_DIR}. "
            "Run download_sec.py first."
        )

    input_files = sorted(COMPANYFACTS_DIR.glob("CIK*.json"))
    if not input_files:
        raise FileNotFoundError(f"No Company Facts JSON files found in {COMPANYFACTS_DIR}")

    print(f"Found Company Facts files: {len(input_files):,}")

    inventory = defaultdict(
        lambda: {
            "label": "",
            "description": "",
            "units": set(),
            "forms": set(),
            "companies": set(),
            "company_years": set(),
            "fact_count": 0,
        }
    )

    errors = 0

    for index, path in enumerate(input_files, start=1):
        try:
            inventory_companyfacts_file(path, inventory)
        except (OSError, json.JSONDecodeError) as error:
            errors += 1
            print(f"Failed to inventory {path}: {error}")

        if index % PROGRESS_EVERY_FILES == 0:
            print(f"Inventoried Company Facts files: {index:,} / {len(input_files):,}")

    rows = build_inventory_rows(inventory)
    write_inventory(rows)

    print(f"Read Company Facts files: {len(input_files):,}")
    print(f"Inventory rows:           {len(rows):,}")
    print(f"Errors:                   {errors:,}")
    print(f"Saved XBRL inventory:     {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

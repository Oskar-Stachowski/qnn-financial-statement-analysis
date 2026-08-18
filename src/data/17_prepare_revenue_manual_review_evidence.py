"""Create a human-readable inspection sheet for the final revenue review.

No adjudication is performed here.  The output exposes the exact SEC-rendered
primary statement, all revenue/sales rows on that statement, and the selected
provenance so a reviewer can compare the consolidated line directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

try:
    from src.data.revenue_manual_review import assert_expected_review_keys
    from src.data.revenue_statement_resolver import (
        filing_summary_reports,
        is_income_statement_metadata,
        report_rows,
    )
except ModuleNotFoundError:  # direct script execution
    from revenue_manual_review import assert_expected_review_keys
    from revenue_statement_resolver import (
        filing_summary_reports,
        is_income_statement_metadata,
        report_rows,
    )


BASE_DIR = Path(__file__).resolve().parents[2]
PREFIX = (
    BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_final_revenue_resolver"
)
REVIEW_PATH = Path(f"{PREFIX}_manual_review_template.csv")
ROWS_PATH = Path(f"{PREFIX}_manual_review_statement_rows.csv")
SHEET_PATH = Path(f"{PREFIX}_manual_review_sheet.md")
EVIDENCE_ROOT = BASE_DIR / "data" / "raw" / "sec_filings" / "revenue_statement_evidence"


def resolve_statement_path(value: object) -> Path:
    """Resolve a repository-relative statement path inside the evidence cache."""

    relative = Path(str(value))
    if relative.is_absolute():
        raise RuntimeError(f"Manual-review statement path must be relative: {value}")
    path = (BASE_DIR / relative).resolve(strict=True)
    root = EVIDENCE_ROOT.resolve(strict=True)
    try:
        path.relative_to(root)
    except ValueError as error:
        raise RuntimeError(
            f"Statement path escapes the evidence cache: {value}"
        ) from error
    return path


def validate_row_provenance(row: pd.Series, path: Path) -> None:
    cik10 = str(row["cik10"]).zfill(10)
    accession = str(row["anchor_t1_accn"])
    accession_compact = accession.replace("-", "")
    expected_directory = (EVIDENCE_ROOT / cik10 / accession_compact).resolve()
    if path.parent != expected_directory:
        raise RuntimeError(
            f"Statement path does not match CIK/accession for {cik10} t={row['feature_year']}"
        )
    if path.name != str(row["B_comparative_t_revenues_statement_file"]):
        raise RuntimeError(
            f"Statement file does not match resolver provenance for {cik10} "
            f"t={row['feature_year']}"
        )
    for column in (
        "B_comparative_t_revenues_accn",
        "B_current_t1_revenues_accn",
    ):
        if str(row[column]) != accession:
            raise RuntimeError(
                f"{column} does not match anchor accession for {cik10} "
                f"t={row['feature_year']}"
            )


def main() -> None:
    review = pd.read_csv(REVIEW_PATH, dtype={"cik10": str})
    review = assert_expected_review_keys(review, label="manual-review template")
    statement_rows: list[dict[str, object]] = []
    sections: list[str] = [
        "# Direct primary-statement review — PIT-B revenues",
        "",
        "Arkusz kontrolny; decyzje manualne pozostają w pliku CSV. Wartości pochodzą z dokładnego SEC-rendered statement wskazanego przez FilingSummary dla anchor accession t+1.",
        "",
    ]
    for review_id, row in review.reset_index(drop=True).iterrows():
        path = resolve_statement_path(row["local_statement_path"])
        validate_row_provenance(row, path)
        directory = path.parent
        filing_summary_path = directory / "FilingSummary.xml"
        if not filing_summary_path.exists():
            raise RuntimeError(
                f"Missing FilingSummary.xml for review row {review_id}: {directory}"
            )
        metadata_by_file = {
            item["html_file_name"]: item
            for item in filing_summary_reports(filing_summary_path)
        }
        metadata = metadata_by_file.get(path.name)
        if metadata is None:
            raise RuntimeError(
                f"Statement {path.name} is absent from FilingSummary.xml for review row "
                f"{review_id}"
            )
        if not is_income_statement_metadata(metadata):
            raise RuntimeError(
                f"Statement {path.name} is not a primary income/operations statement "
                f"for review row {review_id}"
            )
        parsed_rows = report_rows(path, metadata)
        if not parsed_rows:
            raise RuntimeError(f"No parsable statement rows for review row {review_id}")
        revenue_rows = [
            item
            for item in parsed_rows
            if any(
                term in str(item.get("statement_label", "")).lower()
                for term in ("revenue", "sales")
            )
        ]
        if not revenue_rows:
            raise RuntimeError(
                f"No parsable revenue/sales rows for review row {review_id}: {path}"
            )
        for statement_row in revenue_rows:
            statement_rows.append(
                {
                    "review_id": review_id,
                    "cik10": row["cik10"],
                    "feature_year": int(row["feature_year"]),
                    "statement_file": path.name,
                    "statement_short_name": metadata.get("short_name", ""),
                    "statement_role": metadata.get("role", ""),
                    "row_label": statement_row.get("statement_label", ""),
                    "row_concepts": statement_row.get("statement_concepts", ""),
                    "row_class": statement_row.get("statement_row_class", ""),
                    "scale": statement_row.get("statement_scale", ""),
                    "scale_label": statement_row.get("statement_scale_label", ""),
                    "amounts_json": json.dumps(
                        statement_row.get("amounts", {}), separators=(",", ":")
                    ),
                }
            )
        sections.extend(
            [
                f"## {review_id:02d}. {row['company_name']} — t={int(row['feature_year'])}",
                "",
                f"- Kategoria: `{row['review_category']}`; sektor: `{row['research_sector']}`; SIC: `{row['sic']}`.",
                f"- Anchor: `{row['anchor_t1_accn']}`; statement: `{metadata.get('short_name', '')}`; file: `{path.name}`.",
                f"- Resolver: `{row['B_comparative_t_revenues_statement_label']}` / `{row['B_comparative_t_revenues_statement_concepts']}`; comparative `{row['B_comparative_t_revenues_value']}`; current `{row['B_current_t1_revenues_value']}`.",
                f"- [SEC statement]({row['statement_url']})",
                "",
                "| Wiersz statement | Concept | Annual values by end date |",
                "|---|---|---|",
            ]
        )
        for statement_row in revenue_rows:
            values = json.dumps(statement_row.get("amounts", {}), separators=(",", ":"))
            sections.append(
                f"| {statement_row.get('statement_label', '')} | "
                f"`{statement_row.get('statement_concepts', '')}` | `{values}` |"
            )
        sections.append("")

    pd.DataFrame(statement_rows).to_csv(ROWS_PATH, index=False)
    SHEET_PATH.write_text("\n".join(sections), encoding="utf-8")
    print(f"Review rows: {len(review):,}")
    print(f"Saved: {ROWS_PATH.relative_to(BASE_DIR)}")
    print(f"Saved: {SHEET_PATH.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()

"""Attach human semantic adjudication to the stratified PIT-B revenue sample.

Judgements use the financial-statement line shown in the exact anchor 10-K.
They do not use the resulting D5, score, or target direction as a criterion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
REVIEW_PATH = (
    BASE_DIR
    / "data"
    / "reports"
    / "target_candidate_v2_pit_b_freeze_gate_revenue_manual_review.csv"
)
DOWNLOAD_REPORT = (
    BASE_DIR
    / "data"
    / "reports"
    / "target_candidate_v2_pit_b_revenue_review_downloads.json"
)

# (CIK, feature year): (preferred source, outcome, evidence note)
# The preferred source is decided from the statement label and whether the fact
# is consolidated total revenue or a component/segment/other-income measure.
REVIEWS: dict[tuple[str, int], tuple[str, str, str]] = {
    ("0001038277", 2020): ("selected", "selected_is_consolidated_total", "Selected fact is shown as Total Revenues / Total consolidated; alternative is a small non-total item."),
    ("0000907242", 2017): ("alternative", "alternative_is_comparable_net_total", "Selected comparative is Gross revenues; alternative is the comparable Net revenues line."),
    ("0001418819", 2017): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenue; alternative is Engineering and support services only."),
    ("0000798528", 2011): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenue; alternative is Artifact sales and other only."),
    ("0001326200", 2011): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenues; alternative is Service revenues only."),
    ("0001416876", 2011): ("selected", "selected_is_consolidated_total", "Selected fact is Total Revenue; alternative is Rental Revenue only."),
    ("0000013156", 2016): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenue; alternative is Product sales and service only."),
    ("0000861459", 2015): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenue; alternative is Construction Materials only."),
    ("0000018926", 2021): ("alternative", "alternative_is_primary_statement_total", "Alternative is consolidated Operating revenue; selected fact is a contract-revenue amount after divestiture adjustments."),
    ("0001701108", 2022): ("alternative", "alternative_is_consolidated_total", "Selected fact is Collaboration revenue only; alternative is Total revenues."),
    ("0001704720", 2020): ("selected", "selected_is_operating_revenue_total", "Selected fact is Total operating revenues; alternative adds other income and segment/elimination effects."),
    ("0001616543", 2021): ("alternative", "alternative_is_consolidated_total", "Selected fact is a small Revenue, net component; alternative is Total revenue."),
    ("0000888981", 2020): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenues; alternative is Licenses, royalties and fees only."),
    ("0001355839", 2020): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenue; alternative is Technology service revenue only."),
    ("0000880242", 2011): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenue; alternative is Product revenue only."),
    ("0000886163", 2015): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenues; alternative is Material sales only."),
    ("0001058811", 2011): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenues; alternative is Product sales only."),
    ("0001005284", 2015): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenue; alternative is Material sales only."),
    ("0001019034", 2012): ("selected", "selected_is_consolidated_total", "Selected fact is Total Revenue; alternative is Services only."),
    ("0001039280", 2016): ("selected", "selected_is_consolidated_total", "Selected fact is Total net revenues; alternative is Services only."),
    ("0001141240", 2011): ("alternative", "alternative_is_consolidated_total", "Selected fact is Products only; alternative is Total revenue."),
    ("0000006845", 2016): ("selected", "selected_is_consolidated_total", "Selected fact is Net sales total; alternative is a much smaller component."),
    ("0001396536", 2015): ("alternative", "alternative_is_consolidated_total", "Selected fact is Project revenue only; alternative is Total Revenues."),
    ("0000857005", 2014): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenue / GAAP revenue; alternative is Professional services only."),
    ("0001429764", 2018): ("selected", "selected_is_consolidated_total", "Selected fact is Total Revenues; alternative is Grant and rebate only."),
    ("0001038277", 2018): ("selected", "selected_is_consolidated_total", "Selected fact is Total Revenues / Total consolidated; alternative is a small non-total item."),
    ("0000040533", 2016): ("alternative", "alternative_is_primary_statement_total", "Selected fact matches Unbilled revenue, not annual revenue; alternative is consolidated Revenue."),
    ("0000799233", 2020): ("selected", "selected_is_consolidated_total", "Selected fact is Operating revenue; alternative is a small component."),
    ("0000812796", 2017): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenues; alternative is Contract revenue only."),
    ("0001490873", 2020): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenue; alternative is a non-total revenue line."),
    ("0000087050", 2017): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenues; alternative is License fees only."),
    ("0000798528", 2016): ("selected", "selected_is_consolidated_total", "Selected fact is Total revenue; alternative is Recovered cargo sales and other only."),
}


def main() -> None:
    frame = pd.read_csv(REVIEW_PATH, dtype={"cik10": str})
    review_columns = (
        "manual_review_outcome",
        "manual_preferred_economic_concept",
        "manual_evidence_url",
        "manual_notes",
    )
    for column in review_columns:
        frame[column] = frame[column].astype(object)
    downloads = json.loads(DOWNLOAD_REPORT.read_text(encoding="utf-8"))["documents"]
    urls = {
        (str(item["cik10"]).zfill(10), int(item["feature_year"])): str(item["url"])
        for item in downloads
    }
    if len(REVIEWS) != len(frame):
        raise RuntimeError(f"Expected {len(frame)} manual reviews, found {len(REVIEWS)}")

    for index, row in frame.iterrows():
        key = (str(row["cik10"]).zfill(10), int(row["feature_year"]))
        preferred, outcome, note = REVIEWS[key]
        frame.at[index, "manual_review_outcome"] = outcome
        frame.at[index, "manual_preferred_economic_concept"] = preferred
        frame.at[index, "manual_evidence_url"] = urls[key]
        frame.at[index, "manual_notes"] = note

    frame.to_csv(REVIEW_PATH, index=False)
    print(
        frame.groupby("manual_preferred_economic_concept").size().to_string()
    )


if __name__ == "__main__":
    main()

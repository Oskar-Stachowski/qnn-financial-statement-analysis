"""Validate the completed 60-row PIT-B revenue manual review.

The script never creates review decisions and never converts pending rows to
passes.  A reviewer must explicitly complete the versioned review CSV.  This
validator then confirms the exact frozen sample, immutable provenance, all
required checks, and internally consistent pass/fail outcomes before the
freeze-gate report may be compiled.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

try:
    from src.data.revenue_manual_review import (
        EXPECTED_REVIEW_KEY_SHA256,
        validate_completed_review,
    )
except ModuleNotFoundError:  # direct script execution
    from revenue_manual_review import (
        EXPECTED_REVIEW_KEY_SHA256,
        validate_completed_review,
    )


BASE_DIR = Path(__file__).resolve().parents[2]
PREFIX = (
    BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_final_revenue_resolver"
)
REVIEW_TEMPLATE_PATH = Path(f"{PREFIX}_manual_review_template.csv")
REVIEW_PATH = Path(f"{PREFIX}_manual_review.csv")


def main() -> None:
    template = pd.read_csv(REVIEW_TEMPLATE_PATH, dtype={"cik10": str})
    review = pd.read_csv(REVIEW_PATH, dtype={"cik10": str})
    validated = validate_completed_review(review, template=template)

    passes = int(validated["manual_review_outcome"].eq("pass").sum())
    failures = int(validated["manual_review_outcome"].eq("fail").sum())
    selection_errors = int(validated["manual_selection_error"].sum())
    print(f"Validated direct-statement reviews: {len(validated)}")
    print(f"Key manifest SHA-256: {EXPECTED_REVIEW_KEY_SHA256}")
    print(f"Passes: {passes}; failures: {failures}")
    print(f"Selection errors: {selection_errors}")


if __name__ == "__main__":
    main()

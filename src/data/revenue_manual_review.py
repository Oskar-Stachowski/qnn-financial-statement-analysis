"""Validation helpers for the fixed PIT-B revenue manual-review sample.

The reviewed sample is a methodological input, not a value that may silently
change when optional files happen to be present.  These helpers pin its exact
company-year keys and validate explicit human adjudications without inferring
any decision from target values.
"""

from __future__ import annotations

import hashlib

import pandas as pd


KEY_COLUMNS = ("cik10", "feature_year")
EXPECTED_REVIEW_COUNT = 60
EXPECTED_REVIEW_KEY_SHA256 = (
    "4ac3efed4de7163a3af46900c352ec43110ce12e09308d5ffd58f0a377e0f768"
)
REQUIRED_CHECK_COLUMNS = (
    "manual_statement_is_primary_consolidated",
    "manual_row_is_total_revenue",
    "manual_current_value_matches",
    "manual_comparative_value_matches",
    "manual_provenance_matches",
)
MANUAL_BOOLEAN_COLUMNS = (*REQUIRED_CHECK_COLUMNS, "manual_selection_error")
MANUAL_COLUMNS = (
    "manual_review_outcome",
    *MANUAL_BOOLEAN_COLUMNS,
    "manual_notes",
)
TRUE_VALUES = {"true", "1", "yes"}
FALSE_VALUES = {"false", "0", "no"}


def normalize_review_keys(frame: pd.DataFrame, *, label: str) -> pd.DataFrame:
    """Return a copy with strict, normalized CIK and feature-year keys."""

    missing_columns = [column for column in KEY_COLUMNS if column not in frame]
    if missing_columns:
        raise RuntimeError(f"{label} is missing key columns: {missing_columns}")

    normalized = frame.copy()
    cik = normalized["cik10"].astype("string").str.strip()
    invalid_cik = cik.isna() | ~cik.str.fullmatch(r"\d{1,10}", na=False)
    if invalid_cik.any():
        raise RuntimeError(f"{label} contains invalid CIK values")
    normalized["cik10"] = cik.str.zfill(10)

    years = pd.to_numeric(normalized["feature_year"], errors="coerce")
    invalid_year = years.isna() | years.mod(1).ne(0)
    if invalid_year.any():
        raise RuntimeError(f"{label} contains invalid feature years")
    normalized["feature_year"] = years.astype(int)

    if normalized[list(KEY_COLUMNS)].duplicated().any():
        raise RuntimeError(f"{label} contains duplicate company-year keys")
    return normalized


def review_key_digest(frame: pd.DataFrame, *, label: str) -> str:
    """Calculate the stable SHA-256 digest of sorted company-year keys."""

    normalized = normalize_review_keys(frame, label=label)
    keys = sorted(
        f"{cik}|{year}"
        for cik, year in zip(normalized["cik10"], normalized["feature_year"])
    )
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def assert_expected_review_keys(frame: pd.DataFrame, *, label: str) -> pd.DataFrame:
    """Require the exact prereviewed 60-company-year manifest."""

    normalized = normalize_review_keys(frame, label=label)
    if len(normalized) != EXPECTED_REVIEW_COUNT:
        raise RuntimeError(
            f"{label} must contain exactly {EXPECTED_REVIEW_COUNT} observations; "
            f"found {len(normalized)}"
        )
    digest = review_key_digest(normalized, label=label)
    if digest != EXPECTED_REVIEW_KEY_SHA256:
        raise RuntimeError(
            f"{label} key manifest changed: expected "
            f"{EXPECTED_REVIEW_KEY_SHA256}, found {digest}. A changed sample "
            "requires a new explicit human review."
        )
    return normalized


def strict_boolean(series: pd.Series, *, column: str, label: str) -> pd.Series:
    """Parse a completed manual-review boolean without treating NA as false."""

    values = series.astype("string").str.strip().str.lower()
    allowed = TRUE_VALUES | FALSE_VALUES
    invalid = values.isna() | ~values.isin(allowed)
    if invalid.any():
        examples = sorted(values[invalid].fillna("<NA>").unique().tolist())
        raise RuntimeError(
            f"{label} column {column} contains non-boolean values: {examples}"
        )
    return values.isin(TRUE_VALUES)


def _canonical_values(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna("").str.strip()


def validate_completed_review(
    review: pd.DataFrame,
    *,
    template: pd.DataFrame | None = None,
    label: str = "completed manual review",
) -> pd.DataFrame:
    """Validate explicit decisions and, when provided, immutable provenance."""

    completed = assert_expected_review_keys(review, label=label)
    missing_columns = [column for column in MANUAL_COLUMNS if column not in completed]
    if missing_columns:
        raise RuntimeError(f"{label} is missing decision columns: {missing_columns}")

    if template is not None:
        source = assert_expected_review_keys(template, label="manual-review template")
        immutable_columns = [
            column for column in source.columns if column not in MANUAL_COLUMNS
        ]
        missing_immutable = [
            column for column in immutable_columns if column not in completed
        ]
        if missing_immutable:
            raise RuntimeError(
                f"{label} is missing immutable template columns: {missing_immutable}"
            )
        source = source.sort_values(list(KEY_COLUMNS)).reset_index(drop=True)
        candidate = completed.sort_values(list(KEY_COLUMNS)).reset_index(drop=True)
        changed = [
            column
            for column in immutable_columns
            if not _canonical_values(source[column]).equals(
                _canonical_values(candidate[column])
            )
        ]
        if changed:
            raise RuntimeError(
                f"{label} changed immutable sample/provenance columns: {changed}"
            )

    outcomes = (
        completed["manual_review_outcome"].astype("string").str.strip().str.lower()
    )
    invalid_outcomes = outcomes.isna() | ~outcomes.isin({"pass", "fail"})
    if invalid_outcomes.any():
        examples = sorted(outcomes[invalid_outcomes].fillna("<NA>").unique().tolist())
        raise RuntimeError(f"{label} contains invalid review outcomes: {examples}")
    completed["manual_review_outcome"] = outcomes

    for column in MANUAL_BOOLEAN_COLUMNS:
        completed[column] = strict_boolean(
            completed[column], column=column, label=label
        )

    notes = completed["manual_notes"].astype("string").fillna("").str.strip()
    if notes.eq("").any():
        raise RuntimeError(f"{label} contains empty manual notes")
    completed["manual_notes"] = notes

    required_pass = completed[list(REQUIRED_CHECK_COLUMNS)].all(axis=1)
    selection_error = completed["manual_selection_error"]
    pass_rows = completed["manual_review_outcome"].eq("pass")
    inconsistent_pass = pass_rows & (~required_pass | selection_error)
    inconsistent_fail = ~pass_rows & required_pass & ~selection_error
    if inconsistent_pass.any() or inconsistent_fail.any():
        raise RuntimeError(
            f"{label} contains outcomes inconsistent with explicit review checks"
        )
    return completed

"""Temporal cross-validation splits downstream of the approved sample policy.

This module defines indices only.  It does not load data, access test years,
preprocess features, train models, or use ``economic_group_id`` as a predictor.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True, order=True)
class TemporalFold:
    """One expanding-window train/validation definition."""

    name: str
    train_start: int
    train_end: int
    validation_start: int
    validation_end: int

    def __post_init__(self) -> None:
        if self.train_start > self.train_end:
            raise ValueError("train_start must not exceed train_end.")
        if self.validation_start > self.validation_end:
            raise ValueError("validation_start must not exceed validation_end.")
        if self.train_end >= self.validation_start:
            raise ValueError("Training years must be strictly earlier than validation years.")

    @property
    def train_years(self) -> tuple[int, ...]:
        return tuple(range(self.train_start, self.train_end + 1))

    @property
    def validation_years(self) -> tuple[int, ...]:
        return tuple(range(self.validation_start, self.validation_end + 1))


MAIN_EXPANDING_WINDOW_FOLDS: tuple[TemporalFold, ...] = tuple(
    TemporalFold(
        name=f"fold_{validation_year}",
        train_start=2011,
        # The target for feature year t is observed with the t+1 filing.  A
        # one-feature-year embargo avoids using labels contemporaneous with the
        # validation feature filing; an exact timestamp cutoff is applied below.
        train_end=validation_year - 2,
        validation_start=validation_year,
        validation_end=validation_year,
    )
    for validation_year in range(2015, 2021)
)


@dataclass(frozen=True)
class PointInTimeFoldAudit:
    """Label-availability cutoff applied to one temporal fold."""

    validation_prediction_cutoff: pd.Timestamp
    base_train_rows: int
    label_unavailable_rows_excluded: int


def validate_expanding_folds(folds: Sequence[TemporalFold]) -> None:
    """Validate ordering, expanding windows, and disjoint validation years."""

    if not folds:
        raise ValueError("At least one temporal fold is required.")
    names = [fold.name for fold in folds]
    if len(names) != len(set(names)):
        raise ValueError("Temporal fold names must be unique.")
    validation_years: list[int] = []
    previous_train_years: set[int] = set()
    for position, fold in enumerate(folds):
        train_years = set(fold.train_years)
        if position and not previous_train_years < train_years:
            raise ValueError("Training windows must expand strictly from fold to fold.")
        previous_train_years = train_years
        validation_years.extend(fold.validation_years)
    if len(validation_years) != len(set(validation_years)):
        raise ValueError("Validation years must not occur in more than one fold.")
    if validation_years != sorted(validation_years):
        raise ValueError("Validation years must be in chronological order.")


def iter_temporal_folds(
    frame: pd.DataFrame,
    *,
    folds: Sequence[TemporalFold] = MAIN_EXPANDING_WINDOW_FOLDS,
    year_column: str = "feature_year",
) -> Iterator[tuple[TemporalFold, pd.DataFrame, pd.DataFrame]]:
    """Yield copies of temporal train and validation partitions.

    The input must contain only years assigned to at least one training or
    validation window.  This fail-closed check prevents accidental inclusion of
    external validation or test rows in the CV pool.
    """

    validate_expanding_folds(folds)
    if year_column not in frame:
        raise KeyError(f"Missing year column: {year_column!r}")
    years = pd.to_numeric(frame[year_column], errors="raise").astype(int)
    allowed_years = {
        year
        for fold in folds
        for year in (*fold.train_years, *fold.validation_years)
    }
    unexpected_years = sorted(set(years) - allowed_years)
    if unexpected_years:
        raise ValueError(
            f"Rows outside the temporal CV pool are not allowed: {unexpected_years!r}"
        )
    for fold in folds:
        train_mask = years.between(fold.train_start, fold.train_end)
        validation_mask = years.between(fold.validation_start, fold.validation_end)
        if (train_mask & validation_mask).any():
            raise AssertionError(f"Overlapping row assignments in {fold.name}.")
        train = frame.loc[train_mask].copy()
        validation = frame.loc[validation_mask].copy()
        if train.empty or validation.empty:
            raise ValueError(f"Fold {fold.name} has an empty partition.")
        if int(train[year_column].max()) >= int(validation[year_column].min()):
            raise AssertionError(f"Temporal leakage detected in {fold.name}.")
        yield fold, train, validation


def purge_overlapping_training_groups(
    train_frame: pd.DataFrame,
    validation_frame: pd.DataFrame,
    *,
    group_column: str = "economic_group_id",
) -> tuple[pd.DataFrame, tuple[str, ...]]:
    """Remove train rows whose economic group occurs in validation.

    Validation rows are never changed.  This operation defines an unseen-group
    robustness estimand and is not the main temporal CV policy.
    """

    for frame_name, frame in (("train", train_frame), ("validation", validation_frame)):
        if group_column not in frame:
            raise KeyError(f"Missing {group_column!r} in {frame_name} frame.")
        if frame[group_column].isna().any():
            raise ValueError(f"Missing {group_column!r} in {frame_name} frame.")
    validation_groups = set(validation_frame[group_column].astype(str))
    train_groups = set(train_frame[group_column].astype(str))
    overlapping_groups = tuple(sorted(train_groups & validation_groups))
    keep = ~train_frame[group_column].astype(str).isin(overlapping_groups)
    purged_train = train_frame.loc[keep].copy()
    if set(purged_train[group_column].astype(str)) & validation_groups:
        raise AssertionError("Group purge failed to remove all overlap.")
    return purged_train, overlapping_groups


def iter_point_in_time_folds(
    frame: pd.DataFrame,
    *,
    folds: Sequence[TemporalFold] = MAIN_EXPANDING_WINDOW_FOLDS,
    year_column: str = "feature_year",
    label_available_at_column: str = "target_available_at",
    prediction_timestamp_column: str = "prediction_timestamp",
) -> Iterator[
    tuple[TemporalFold, pd.DataFrame, pd.DataFrame, PointInTimeFoldAudit]
]:
    """Yield temporal folds with a conservative target-availability cutoff.

    Training rows first obey the feature-year embargo encoded in ``folds``.  A
    training row is then retained only if its target was available no later than
    the earliest prediction timestamp in the validation year.  This produces one
    fixed training set for the whole validation fold and avoids cross-sectional
    look-ahead from late filers.
    """

    required = {label_available_at_column, prediction_timestamp_column}
    missing_columns = sorted(required - set(frame.columns))
    if missing_columns:
        raise KeyError(f"Missing point-in-time columns: {missing_columns!r}")
    for fold, base_train, validation in iter_temporal_folds(
        frame, folds=folds, year_column=year_column
    ):
        label_available_at = pd.to_datetime(
            base_train[label_available_at_column], errors="coerce", utc=True
        )
        train_prediction_at = pd.to_datetime(
            base_train[prediction_timestamp_column], errors="coerce", utc=True
        )
        prediction_at = pd.to_datetime(
            validation[prediction_timestamp_column], errors="coerce", utc=True
        )
        if label_available_at.isna().any():
            raise ValueError(f"Missing training label availability in {fold.name}.")
        if train_prediction_at.isna().any():
            raise ValueError(f"Missing training prediction timestamp in {fold.name}.")
        if prediction_at.isna().any():
            raise ValueError(f"Missing validation prediction timestamp in {fold.name}.")
        if not train_prediction_at.lt(label_available_at).all():
            raise AssertionError(
                f"Prediction must strictly precede target availability in {fold.name}."
            )
        cutoff = prediction_at.min()
        safe_mask = label_available_at.le(cutoff)
        train = base_train.loc[safe_mask].copy()
        if train.empty:
            raise ValueError(f"Fold {fold.name} has no point-in-time-safe training rows.")
        retained_label_times = label_available_at.loc[safe_mask]
        if retained_label_times.max() > cutoff:
            raise AssertionError(f"Label-availability leakage detected in {fold.name}.")
        retained_prediction_times = train_prediction_at.loc[safe_mask]
        if not retained_prediction_times.lt(retained_label_times).all():
            raise AssertionError(
                f"Prediction/target ordering failed after filtering in {fold.name}."
            )
        audit = PointInTimeFoldAudit(
            validation_prediction_cutoff=cutoff,
            base_train_rows=len(base_train),
            label_unavailable_rows_excluded=int((~safe_mask).sum()),
        )
        yield fold, train, validation, audit


def fold_timeline(
    folds: Sequence[TemporalFold] = MAIN_EXPANDING_WINDOW_FOLDS,
    *,
    first_year: int = 2011,
    last_year: int = 2020,
) -> pd.DataFrame:
    """Return a tabular TR/VA timeline for readable audit output."""

    validate_expanding_folds(folds)
    years = list(range(first_year, last_year + 1))
    rows: list[dict[str, str]] = []
    for fold in folds:
        row = {"fold": fold.name}
        for year in years:
            if year in fold.train_years:
                row[str(year)] = "TR"
            elif year in fold.validation_years:
                row[str(year)] = "VA"
            elif fold.train_end < year < fold.validation_start:
                row[str(year)] = "EM"
            else:
                row[str(year)] = "·"
        rows.append(row)
    return pd.DataFrame(rows).set_index("fold")

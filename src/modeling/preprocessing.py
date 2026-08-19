"""Leakage-safe preprocessing for the frozen point-in-time financial features.

The module deliberately contains no data loading, target access, sampling, cross-
validation, or model fitting.  Callers must provide an already approved sample and
must call :meth:`FinancialPreprocessor.fit` only on a training partition (or on a
training fold inside future cross-validation).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


FEATURE_BLOCKS: dict[str, tuple[str, ...]] = {
    "L": (
        "log_assets_t",
        "roa_t",
        "ocf_to_assets_t",
        "current_ratio_t",
        "liabilities_to_assets_t",
        "working_capital_to_assets_t",
        "accruals_to_assets_t",
    ),
    "D": (
        "asset_growth_1y",
        "delta_roa_1y",
        "delta_ocf_to_assets_1y",
        "current_ratio_change_1y",
        "delta_liabilities_to_assets_1y",
    ),
    "R": (
        "log1p_revenues_t",
        "profit_margin_t",
        "ocf_margin_t",
        "asset_turnover_t",
        "revenue_growth_1y",
    ),
}

FROZEN_BLOCK_COMPARISONS: tuple[tuple[str, ...], ...] = (
    ("L",),
    ("L", "D"),
    ("L", "D", "R"),
)


class NotFittedError(RuntimeError):
    """Raised when transform is requested before fit."""


def features_for_blocks(blocks: Iterable[str]) -> tuple[str, ...]:
    """Return frozen features for an ordered block combination.

    Only the three pre-registered nested combinations L, L+D, and L+D+R are
    accepted.  This prevents an accidental redefinition of the frozen blocks.
    """

    normalized = tuple(str(block) for block in blocks)
    if normalized not in FROZEN_BLOCK_COMPARISONS:
        raise ValueError(
            f"Unsupported block combination {normalized!r}; expected one of "
            f"{FROZEN_BLOCK_COMPARISONS!r}."
        )
    return tuple(feature for block in normalized for feature in FEATURE_BLOCKS[block])


@dataclass(frozen=True)
class PreprocessingPolicy:
    """Configuration whose fitted statistics must come only from training data."""

    lower_quantile: float = 0.01
    upper_quantile: float = 0.99
    add_missing_indicators: bool = True
    indicator_suffix: str = "__missing"
    near_constant_dominant_share: float = 0.995
    zero_scale_tolerance: float = 1e-12

    def __post_init__(self) -> None:
        if not 0.0 <= self.lower_quantile < self.upper_quantile <= 1.0:
            raise ValueError("Quantiles must satisfy 0 <= lower < upper <= 1.")
        if not 0.5 < self.near_constant_dominant_share <= 1.0:
            raise ValueError("near_constant_dominant_share must be in (0.5, 1].")
        if self.zero_scale_tolerance < 0:
            raise ValueError("zero_scale_tolerance must be non-negative.")
        if not self.indicator_suffix:
            raise ValueError("indicator_suffix must not be empty.")


class FinancialPreprocessor:
    """Winsorize, median-impute, standardize, and append missing indicators.

    Fitting policy
    --------------
    * Per-feature medians and quantile caps use finite, observed training values.
    * Scaling mean and population standard deviation use the training matrix after
      winsorization and median imputation.
    * One binary indicator is created for every input financial feature, preserving
      a deterministic schema even if a particular training fold has no missing value.
    * Indicators remain binary and are never winsorized or scaled.

    Transformation never drops rows and never mutates the caller's DataFrame.
    Infinite values are rejected; missing values must be represented by NaN.
    """

    def __init__(
        self,
        features: Sequence[str],
        *,
        policy: PreprocessingPolicy | None = None,
    ) -> None:
        normalized = tuple(str(feature) for feature in features)
        if not normalized:
            raise ValueError("At least one feature is required.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Feature names must be unique.")
        self.features = normalized
        self.policy = policy or PreprocessingPolicy()
        self._is_fitted = False

    @classmethod
    def for_blocks(
        cls,
        blocks: Iterable[str],
        *,
        policy: PreprocessingPolicy | None = None,
    ) -> FinancialPreprocessor:
        """Construct a transformer for L, L+D, or L+D+R."""

        return cls(features_for_blocks(blocks), policy=policy)

    def _numeric_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("Expected a pandas DataFrame.")
        if frame.columns.has_duplicates:
            raise ValueError("Input DataFrame contains duplicate columns.")
        missing_columns = [feature for feature in self.features if feature not in frame]
        if missing_columns:
            raise KeyError(f"Missing required columns: {missing_columns!r}")
        numeric = frame.loc[:, self.features].apply(pd.to_numeric, errors="raise").astype(float)
        if np.isinf(numeric.to_numpy()).any():
            raise ValueError("Infinite values are not allowed; use NaN for missing data.")
        return numeric.copy()

    def _require_fitted(self) -> None:
        if not self._is_fitted:
            raise NotFittedError("FinancialPreprocessor must be fitted before transform.")

    def fit(self, train_frame: pd.DataFrame) -> FinancialPreprocessor:
        """Fit all statistics on the supplied training rows only."""

        train = self._numeric_frame(train_frame)
        if train.empty:
            raise ValueError("Cannot fit on an empty training frame.")
        all_missing = train.columns[train.notna().sum(axis=0).eq(0)].tolist()
        if all_missing:
            raise ValueError(f"Training features are entirely missing: {all_missing!r}")

        self.feature_names_in_ = tuple(train.columns)
        self.n_samples_seen_ = len(train)
        self.missing_count_ = train.isna().sum(axis=0).astype(int)
        self.missing_rate_ = train.isna().mean(axis=0).astype(float)
        self.medians_ = train.median(axis=0, skipna=True).astype(float)
        self.lower_bounds_ = train.quantile(
            self.policy.lower_quantile, axis=0, numeric_only=True
        ).astype(float)
        self.upper_bounds_ = train.quantile(
            self.policy.upper_quantile, axis=0, numeric_only=True
        ).astype(float)

        winsorized = train.clip(
            lower=self.lower_bounds_, upper=self.upper_bounds_, axis="columns"
        )
        imputed = winsorized.fillna(self.medians_)
        self.centers_ = imputed.mean(axis=0).astype(float)
        raw_scales = imputed.std(axis=0, ddof=0).astype(float)
        self.constant_features_ = tuple(
            raw_scales.index[raw_scales.le(self.policy.zero_scale_tolerance)]
        )
        self.scales_ = raw_scales.mask(
            raw_scales.le(self.policy.zero_scale_tolerance), 1.0
        )

        dominant_shares: dict[str, float] = {}
        for feature in self.features:
            frequencies = imputed[feature].value_counts(normalize=True, dropna=False)
            dominant_shares[feature] = float(frequencies.iloc[0]) if len(frequencies) else np.nan
        self.dominant_share_ = pd.Series(dominant_shares, dtype=float)
        self.near_constant_features_ = tuple(
            feature
            for feature in self.features
            if feature in self.constant_features_
            or self.dominant_share_[feature] >= self.policy.near_constant_dominant_share
        )
        self.indicator_names_ = tuple(
            f"{feature}{self.policy.indicator_suffix}" for feature in self.features
        ) if self.policy.add_missing_indicators else tuple()
        self._is_fitted = True
        return self

    def transform_stages(self, frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
        """Return non-mutating intermediate stages for diagnostics and testing."""

        self._require_fitted()
        raw = self._numeric_frame(frame)
        if self.policy.add_missing_indicators:
            indicators = raw.isna().astype("int8")
            indicators.columns = self.indicator_names_
        else:
            indicators = pd.DataFrame(index=raw.index)
        winsorized = raw.clip(
            lower=self.lower_bounds_, upper=self.upper_bounds_, axis="columns"
        )
        imputed = winsorized.fillna(self.medians_)
        scaled = (imputed - self.centers_) / self.scales_
        transformed = scaled.copy()
        if self.policy.add_missing_indicators:
            transformed = pd.concat([scaled, indicators], axis=1)
        return {
            "raw": raw,
            "winsorized": winsorized,
            "imputed": imputed,
            "scaled": scaled,
            "indicators": indicators,
            "transformed": transformed,
        }

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Apply frozen training parameters without refitting or dropping rows."""

        return self.transform_stages(frame)["transformed"]

    def fit_transform(self, train_frame: pd.DataFrame) -> pd.DataFrame:
        """Fit on and transform the same training frame."""

        return self.fit(train_frame).transform(train_frame)

    def get_feature_names_out(self) -> tuple[str, ...]:
        """Return financial feature names followed by binary indicator names."""

        self._require_fitted()
        return (*self.feature_names_in_, *self.indicator_names_)

    def parameters_frame(self) -> pd.DataFrame:
        """Return fitted statistics in a serialization-friendly audit table."""

        self._require_fitted()
        return pd.DataFrame(
            {
                "median": self.medians_,
                "winsor_lower": self.lower_bounds_,
                "winsor_upper": self.upper_bounds_,
                "scaling_center": self.centers_,
                "scaling_scale": self.scales_,
                "train_missing_n": self.missing_count_,
                "train_missing_rate": self.missing_rate_,
                "dominant_share_after_imputation": self.dominant_share_,
                "constant_after_imputation": [
                    feature in self.constant_features_ for feature in self.features
                ],
                "near_constant_after_imputation": [
                    feature in self.near_constant_features_ for feature in self.features
                ],
            },
            index=pd.Index(self.features, name="feature"),
        )

    def fitted_state(self) -> dict[str, Any]:
        """Return immutable-value parameters suitable for audit serialization."""

        self._require_fitted()
        return {
            "features": list(self.feature_names_in_),
            "n_samples_seen": self.n_samples_seen_,
            "policy": {
                "lower_quantile": self.policy.lower_quantile,
                "upper_quantile": self.policy.upper_quantile,
                "add_missing_indicators": self.policy.add_missing_indicators,
                "indicator_suffix": self.policy.indicator_suffix,
                "near_constant_dominant_share": self.policy.near_constant_dominant_share,
                "zero_scale_tolerance": self.policy.zero_scale_tolerance,
            },
            "parameters": self.parameters_frame().reset_index().to_dict(orient="records"),
            "output_features": list(self.get_feature_names_out()),
        }

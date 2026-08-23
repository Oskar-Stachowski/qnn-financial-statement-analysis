"""Synthetic-only smoke checks for the secondary-analysis pre-execution package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.modeling.preprocessing import (
    FinancialPreprocessor,
    PreprocessingPolicy,
    features_for_blocks,
)
from src.modeling.secondary_analysis_runner import atomic_write_json
from src.modeling.secondary_analysis_schemas import (
    DEFAULT_CONFIG,
    ROOT,
    canonical_sha256,
    load_config,
    require,
    validate_config,
    validate_synthetic_smoke,
)


def synthetic_frame(rows: int = 72) -> pd.DataFrame:
    rng = np.random.default_rng(20260818)
    features = features_for_blocks(("L", "D", "R"))
    frame = pd.DataFrame(
        rng.normal(size=(rows, len(features))), columns=features
    )
    for index, feature in enumerate(features):
        frame.loc[(np.arange(rows) + index) % 19 == 0, feature] = np.nan
    frame.loc[0, list(features[:9])] = np.nan
    frame["economic_group_id"] = [f"group_{index % 18:02d}" for index in range(rows)]
    frame["research_universe_company_year_id"] = [f"synthetic_{index:04d}" for index in range(rows)]
    for signal in range(1, 6):
        frame[f"D{signal}"] = rng.integers(0, 2, size=rows)
    frame["deterioration_score_1y"] = frame[[f"D{i}" for i in range(1, 6)]].sum(axis=1)
    frame["target_label"] = (frame["deterioration_score_1y"] >= 3).astype(int)
    return frame


def target_variants(frame: pd.DataFrame) -> dict[str, np.ndarray]:
    score = frame["deterioration_score_1y"].to_numpy(dtype=np.int64)
    operating = np.maximum(
        frame["D1"].to_numpy(dtype=np.int64),
        frame["D2"].to_numpy(dtype=np.int64),
    )
    alternative = operating + frame[["D3", "D4", "D5"]].sum(axis=1).to_numpy(dtype=np.int64)
    return {
        "deterioration_score_at_least_2": (score >= 2).astype(np.int64),
        "deterioration_score_at_least_4": (score >= 4).astype(np.int64),
        "operating_performance_max_D1_D2_alternative_score_at_least_3": (
            alternative >= 3
        ).astype(np.int64),
    }


def run_smoke(config_path: Path, output_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    counts = validate_config(config)
    frame = synthetic_frame()
    features = features_for_blocks(("L", "D", "R"))
    train = frame.iloc[:54].copy()
    validation = frame.iloc[54:].copy()
    checks: list[dict[str, Any]] = []

    main = FinancialPreprocessor.for_blocks(("L", "D", "R"))
    x_train = main.fit_transform(train)
    x_validation = main.transform(validation)
    require(x_train.shape == (54, 34), "Synthetic main preprocessing shape mismatch.")
    require(x_validation.shape == (18, 34), "Synthetic validation shape mismatch.")
    require(np.isfinite(x_train.to_numpy()).all(), "Synthetic main matrix is nonfinite.")
    checks.append({"id": "main_preprocessing_C", "status": "PASS"})

    no_indicators = FinancialPreprocessor.for_blocks(
        ("L", "D", "R"), policy=PreprocessingPolicy(add_missing_indicators=False)
    )
    b_train = no_indicators.fit_transform(train)
    require(b_train.shape == (54, 17), "Preprocessing-B shape mismatch.")
    checks.append({"id": "B_without_missing_indicators", "status": "PASS"})

    complete_case = frame.loc[frame.loc[:, features].notna().all(axis=1)]
    sparse = frame.loc[frame.loc[:, features].notna().sum(axis=1) >= 11]
    require(0 < len(complete_case) < len(frame), "Complete-case filter was not exercised.")
    require(0 < len(sparse) < len(frame), "Sparse-row filter was not exercised.")
    checks.append({"id": "row_filter_variants", "status": "PASS"})

    validation_groups = set(validation["economic_group_id"])
    purged_train = train.loc[~train["economic_group_id"].isin(validation_groups)]
    require(
        set(purged_train["economic_group_id"]).isdisjoint(validation_groups),
        "Purged-group synthetic invariant failed.",
    )
    checks.append({"id": "purged_economic_group_cv", "status": "PASS"})

    variants = target_variants(frame)
    require(set(variants) == set(config["secondary_development_analyses"]["robustness"]["label_runs_ordered"]), "Label variant roster mismatch.")
    require(all(set(values) <= {0, 1} for values in variants.values()), "Synthetic label is not binary.")
    checks.append({"id": "label_robustness_definitions", "status": "PASS"})

    pca = PCA(n_components=4, svd_solver="full", whiten=False)
    train_components = pca.fit_transform(x_train.to_numpy(dtype=np.float64))
    validation_components = pca.transform(x_validation.to_numpy(dtype=np.float64))
    scaler = StandardScaler(with_mean=True, with_std=True)
    train_angles = np.pi / 3.0 * np.clip(
        scaler.fit_transform(train_components), -3.0, 3.0
    )
    validation_angles = np.pi / 3.0 * np.clip(
        scaler.transform(validation_components), -3.0, 3.0
    )
    require(train_angles.shape == (54, 4), "Synthetic PCA train shape mismatch.")
    require(validation_angles.shape == (18, 4), "Synthetic PCA validation shape mismatch.")
    require(np.isfinite(validation_angles).all(), "Synthetic PCA angles are nonfinite.")
    estimator = LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000, tol=1e-6)
    estimator.fit(train_angles, train["target_label"].to_numpy(dtype=np.int64))
    scores = estimator.decision_function(validation_angles)
    require(scores.shape == (18,) and np.isfinite(scores).all(), "Synthetic PCA control failed.")
    checks.append({"id": "pca_matched_fixed_l2_control", "status": "PASS"})

    task_identity = {
        "stage": "robustness",
        "analysis_id": "no_winsorization",
        "family": "xgboost",
        "fold_id": "fold_2015",
        "training_seed": 20260818,
    }
    require(canonical_sha256(task_identity) == canonical_sha256(dict(task_identity)), "Task identity is not deterministic.")
    require(counts == {
        "pca_matched_control_fold_fits": 12,
        "global_winner_robustness_fold_fits": 48,
        "qnn_structural_fold_fits": 24,
    }, "Frozen task budgets changed.")
    checks.append({"id": "deterministic_task_identity_and_budgets", "status": "PASS"})

    payload = {
        "schema_version": 1,
        "status": "PASS",
        "checks": checks,
        "generated_rows": len(frame),
        "financial_features": len(features),
        "protected_feature_years_opened": False,
        "project_data_read": False,
        "project_model_fit_performed": False,
    }
    validate_synthetic_smoke(payload, config)
    atomic_write_json(output_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "data/model_runs/secondary_development_v1_0_0/secondary_analysis_synthetic_smoke.json",
    )
    args = parser.parse_args()
    result = run_smoke(args.config.resolve(), args.output.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

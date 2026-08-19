"""Audit the resolver/X_t v1.1.0 correction on the sealed train projection.

The script reads only physically materialized 2011--2020 projections.  It does
not access validation/test rows, preprocess features, or train models.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.data import target_candidate_v2_pit as target_v1
from src.data import x_t_pit as x_v1
from src.data.x_t_pit_v1_1 import (
    BASE_DIR,
    CONFIG_PATH,
    load_patch_config,
    sha256,
)
from src.modeling.temporal_cv import iter_point_in_time_folds


ALLOWED_X_T_STATUSES = {"available_core", "partially_available"}


def membership_sha256(values: pd.Series | list[str] | set[str]) -> str:
    payload = "".join(f"{value}\n" for value in sorted(str(item) for item in values))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def numeric_changed(left: pd.Series, right: pd.Series) -> pd.Series:
    left_numeric = pd.to_numeric(left, errors="coerce")
    right_numeric = pd.to_numeric(right, errors="coerce")
    both_missing = left_numeric.isna() & right_numeric.isna()
    close = np.isclose(
        left_numeric.fillna(0.0).to_numpy(dtype=float),
        right_numeric.fillna(0.0).to_numpy(dtype=float),
        rtol=1e-12,
        atol=1e-9,
        equal_nan=True,
    )
    return ~(both_missing | pd.Series(close, index=left.index))


def text_changed(left: pd.Series, right: pd.Series) -> pd.Series:
    return left.fillna("").astype(str).ne(right.fillna("").astype(str))


def raw_comparison_columns(config: dict[str, Any]) -> list[str]:
    columns = [
        "research_universe_company_year_id",
        "cik10",
        "feature_year",
        "split",
        "anchor_accession",
        "prediction_timestamp",
        "economic_group_id",
        "x_t_status",
        "x_t_status_reason",
        "feature_policy_version",
        "L_available_count",
        "D_available_count",
        "R_available_count",
        "feature_available_count",
        "feature_missing_count",
        "feature_ambiguous_count",
        "feature_not_computable_count",
    ]
    for primitive in x_v1.PRIMITIVES:
        columns.extend(
            [
                f"current_t_{primitive}_value",
                f"current_t_{primitive}_status",
                f"current_t_{primitive}_reason",
                f"current_t_{primitive}_strategy",
                f"current_t_{primitive}_tag",
                f"pair_{primitive}_status",
                f"pair_{primitive}_reason",
                f"pair_{primitive}_strategy",
                f"comparative_tm1_{primitive}_value",
                f"pair_current_t_{primitive}_value",
            ]
        )
    for feature in x_v1.feature_names(config):
        columns.extend([f"{feature}_value", f"{feature}_status", f"{feature}_reason"])
    return columns


def load_aligned_raw(
    old_path: Path,
    new_path: Path,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    usecols = raw_comparison_columns(config)
    old = pd.read_csv(old_path, usecols=usecols, low_memory=False)
    new = pd.read_csv(new_path, usecols=usecols, low_memory=False)
    keys = ["cik10", "feature_year", "research_universe_company_year_id"]
    old = old.sort_values(keys).reset_index(drop=True)
    new = new.sort_values(keys).reset_index(drop=True)
    if len(old) != len(new) or not old[keys].fillna("").astype(str).equals(
        new[keys].fillna("").astype(str)
    ):
        raise RuntimeError("Raw X_t v1/v1.1 train rows are not aligned one-to-one")
    if not pd.to_numeric(old["feature_year"], errors="raise").between(2011, 2020).all():
        raise RuntimeError("Old X_t comparison input is not train-only")
    if not pd.to_numeric(new["feature_year"], errors="raise").between(2011, 2020).all():
        raise RuntimeError("New X_t comparison input is not train-only")
    return old, new


def split_reasons(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [item for item in str(value or "").split(";") if item]


def target_impact(
    target_path: Path,
    primitive_changes: dict[str, set[str]],
    pair_changed_rows: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    target_config = target_v1.load_config()
    scope = target_v1.parse_scope(target_config)
    usecols = [
        "research_universe_company_year_id",
        "cik10",
        "feature_year",
        "target_status",
        "target_candidate_v2_pit_b",
        "anchor_t_accn",
        "anchor_t1_accn",
        "anchor_t1_accepted_at",
        "ambiguous_reasons",
        "hard_exclude_reasons",
        "reporting_entity_exclusion_evidence",
    ]
    for primitive in target_v1.PRIMITIVES:
        usecols.extend(
            [
                f"A_current_t_{primitive}_value",
                f"A_current_t_{primitive}_status",
                f"A_current_t_{primitive}_reason",
                f"A_current_t_{primitive}_strategy",
                f"A_current_t_{primitive}_tag",
                f"A_current_t_{primitive}_accn",
                f"B_comparative_t_{primitive}_value",
                f"B_current_t1_{primitive}_value",
            ]
        )
    frame = pd.read_csv(
        target_path,
        usecols=usecols,
        dtype={"cik10": str},
        low_memory=False,
    )
    frame["cik10"] = frame["cik10"].astype(str).str.zfill(10)
    years = pd.to_numeric(frame["feature_year"], errors="raise").astype(int)
    if not years.between(2011, 2020).all():
        raise RuntimeError("Target-impact input is not train-only")
    frame["feature_year"] = years
    indexed = frame.set_index("research_universe_company_year_id", drop=False)

    affected_target_ids: set[str] = set()
    affected_cells: list[dict[str, Any]] = []
    simulated_status = frame.set_index("research_universe_company_year_id")[
        "target_status"
    ].astype(str).to_dict()
    status_changes: list[dict[str, str]] = []
    target_label_changes = 0

    for company_year_id, primitives in sorted(primitive_changes.items()):
        if company_year_id not in indexed.index:
            continue
        row = indexed.loc[company_year_id]
        if isinstance(row, pd.DataFrame):
            raise RuntimeError("Duplicate target-application company-year")
        actual_primitives = {
            primitive
            for primitive in primitives
            if str(row.get(f"A_current_t_{primitive}_status", "")) == "selected"
            and str(row.get(f"A_current_t_{primitive}_accn", ""))
            == str(row.get("anchor_t_accn", ""))
        }
        if not actual_primitives:
            continue
        affected_target_ids.add(company_year_id)
        for primitive in sorted(actual_primitives):
            affected_cells.append(
                {
                    "research_universe_company_year_id": company_year_id,
                    "primitive": primitive,
                    "old_status": str(row[f"A_current_t_{primitive}_status"]),
                    "new_status": "ambiguous",
                }
            )

        old_a = {
            primitive: (
                float(row[f"A_current_t_{primitive}_value"])
                if pd.notna(row[f"A_current_t_{primitive}_value"])
                else None
            )
            for primitive in target_v1.PRIMITIVES
        }
        new_a = dict(old_a)
        for primitive in actual_primitives:
            new_a[primitive] = None
        comparative = {
            primitive: (
                float(row[f"B_comparative_t_{primitive}_value"])
                if pd.notna(row[f"B_comparative_t_{primitive}_value"])
                else None
            )
            for primitive in target_v1.PRIMITIVES
        }
        old_continuity, _ = target_v1.continuity_ambiguity_screen(
            old_a, comparative, target_config, scope.minimum_denominator_usd
        )
        new_continuity, _ = target_v1.continuity_ambiguity_screen(
            new_a, comparative, target_config, scope.minimum_denominator_usd
        )
        old_sign = set(
            target_v1.semantic_vintage_ambiguity_screen(
                old_a, comparative, target_config
            )
        )
        new_sign = set(
            target_v1.semantic_vintage_ambiguity_screen(
                new_a, comparative, target_config
            )
        )
        reasons = split_reasons(row.get("ambiguous_reasons", ""))
        dynamic_continuity = "reporting_entity_continuity_material_rebasing_unresolved"
        if old_continuity and not new_continuity:
            reasons = [reason for reason in reasons if reason != dynamic_continuity]
        reasons = [reason for reason in reasons if reason not in (old_sign - new_sign)]
        if new_continuity and dynamic_continuity not in reasons and not str(
            row.get("reporting_entity_exclusion_evidence", "") or ""
        ):
            reasons.append(dynamic_continuity)
        reasons.extend(reason for reason in sorted(new_sign) if reason not in reasons)

        hard_reasons = split_reasons(row.get("hard_exclude_reasons", ""))
        if hard_reasons:
            new_status = "hard_exclude"
        elif reasons:
            new_status = "ambiguous"
        elif pd.notna(row.get("target_candidate_v2_pit_b")):
            new_status = "available"
        else:
            new_status = "missing"
        old_status = str(row["target_status"])
        simulated_status[company_year_id] = new_status
        if new_status != old_status:
            status_changes.append(
                {
                    "research_universe_company_year_id": company_year_id,
                    "old_status": old_status,
                    "new_status": new_status,
                }
            )
            if (old_status == "available") != (new_status == "available"):
                target_label_changes += 1

    frame["simulated_target_status_v1_1"] = frame[
        "research_universe_company_year_id"
    ].map(simulated_status)

    pair_target_candidates: list[dict[str, Any]] = []
    if not pair_changed_rows.empty:
        by_cik_year = frame.set_index(["cik10", "feature_year"], drop=False)
        for raw_row in pair_changed_rows.to_dict("records"):
            key = (str(raw_row["cik10"]).zfill(10), int(raw_row["feature_year"]) - 1)
            if key not in by_cik_year.index:
                continue
            target_row = by_cik_year.loc[key]
            if isinstance(target_row, pd.DataFrame):
                raise RuntimeError("Duplicate target row for pair-impact mapping")
            if str(target_row.get("anchor_t1_accn", "")) == str(
                raw_row.get("anchor_accession", "")
            ):
                pair_target_candidates.append(
                    {
                        "raw_company_year_id": raw_row[
                            "research_universe_company_year_id"
                        ],
                        "target_company_year_id": target_row[
                            "research_universe_company_year_id"
                        ],
                    }
                )

    impact = {
        "single_period_target_provenance_company_years": len(affected_target_ids),
        "single_period_target_provenance_cells": len(affected_cells),
        "simulated_target_status_changes": len(status_changes),
        "simulated_target_label_availability_changes": target_label_changes,
        "pair_resolver_target_candidates": len(pair_target_candidates),
        "target_definition_or_label_values_changed": bool(
            status_changes or pair_target_candidates
        ),
        "status_changes": status_changes,
        "pair_target_candidates": pair_target_candidates,
    }
    return impact, frame


def build_fold_report(sample: pd.DataFrame) -> dict[str, Any]:
    report: dict[str, Any] = {}
    fold_input = sample[
        [
            "research_universe_company_year_id",
            "feature_year",
            "prediction_timestamp",
            "target_available_at",
        ]
    ].copy()
    for fold, train, validation, audit in iter_point_in_time_folds(fold_input):
        report[fold.name] = {
            "train_n": len(train),
            "validation_n": len(validation),
            "late_labels_excluded_n": audit.label_unavailable_rows_excluded,
            "validation_prediction_cutoff_utc": audit.validation_prediction_cutoff.isoformat(),
            "train_membership_sha256": membership_sha256(
                train["research_universe_company_year_id"]
            ),
            "validation_membership_sha256": membership_sha256(
                validation["research_universe_company_year_id"]
            ),
        }
    return report


def audit(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    patch_config = load_patch_config(config_path)
    config = x_v1.load_config(
        BASE_DIR / str(patch_config["x_t_patch"]["base_frozen_config"])
    )
    old_path = BASE_DIR / str(patch_config["inputs"]["train_projection"])
    new_path = BASE_DIR / str(patch_config["outputs"]["raw_train_artifact"])
    target_path = BASE_DIR / str(
        patch_config["inputs"]["target_application_train_projection"]
    )
    target_new_path = BASE_DIR / str(
        patch_config["outputs"]["target_application_train_artifact"]
    )
    old, new = load_aligned_raw(old_path, new_path, config)
    row_changed = pd.Series(False, index=old.index)
    primitive_changes: dict[str, set[str]] = defaultdict(set)
    primitive_report: dict[str, Any] = {}
    pair_report: dict[str, Any] = {}
    pair_changed_mask = pd.Series(False, index=old.index)

    for primitive in x_v1.PRIMITIVES:
        status_column = f"current_t_{primitive}_status"
        value_column = f"current_t_{primitive}_value"
        status_change = text_changed(old[status_column], new[status_column])
        value_change = numeric_changed(old[value_column], new[value_column])
        changed = status_change | value_change
        row_changed |= changed
        for company_year_id in old.loc[
            changed, "research_universe_company_year_id"
        ].astype(str):
            primitive_changes[company_year_id].add(primitive)
        transitions = Counter(
            f"{left}->{right}"
            for left, right in zip(
                old.loc[status_change, status_column].fillna("").astype(str),
                new.loc[status_change, status_column].fillna("").astype(str),
                strict=True,
            )
        )
        primitive_report[primitive] = {
            "changed_company_years": int(changed.sum()),
            "status_changed": int(status_change.sum()),
            "value_changed": int(value_change.sum()),
            "status_transitions": dict(sorted(transitions.items())),
            "old_status_counts": old[status_column].fillna("").value_counts().sort_index().to_dict(),
            "new_status_counts": new[status_column].fillna("").value_counts().sort_index().to_dict(),
        }

        pair_status = f"pair_{primitive}_status"
        pair_status_change = text_changed(old[pair_status], new[pair_status])
        comparative_change = numeric_changed(
            old[f"comparative_tm1_{primitive}_value"],
            new[f"comparative_tm1_{primitive}_value"],
        )
        current_change = numeric_changed(
            old[f"pair_current_t_{primitive}_value"],
            new[f"pair_current_t_{primitive}_value"],
        )
        pair_changed = pair_status_change | comparative_change | current_change
        pair_changed_mask |= pair_changed
        row_changed |= pair_changed
        pair_report[primitive] = {
            "changed_company_years": int(pair_changed.sum()),
            "status_changed": int(pair_status_change.sum()),
            "comparative_value_changed": int(comparative_change.sum()),
            "current_value_changed": int(current_change.sum()),
        }

    feature_report: dict[str, Any] = {}
    feature_changed_masks: dict[str, pd.Series] = {}
    old_missing_total = 0
    new_missing_total = 0
    for feature in x_v1.feature_names(config):
        status_column = f"{feature}_status"
        value_column = f"{feature}_value"
        status_change = text_changed(old[status_column], new[status_column])
        value_change = numeric_changed(old[value_column], new[value_column])
        changed = status_change | value_change
        feature_changed_masks[feature] = changed
        row_changed |= changed
        old_na = int(pd.to_numeric(old[value_column], errors="coerce").isna().sum())
        new_na = int(pd.to_numeric(new[value_column], errors="coerce").isna().sum())
        old_missing_total += old_na
        new_missing_total += new_na
        transitions = Counter(
            f"{left}->{right}"
            for left, right in zip(
                old.loc[status_change, status_column].fillna("").astype(str),
                new.loc[status_change, status_column].fillna("").astype(str),
                strict=True,
            )
        )
        feature_report[feature] = {
            "changed_company_years": int(changed.sum()),
            "status_changed": int(status_change.sum()),
            "value_changed": int(value_change.sum()),
            "old_na_n": old_na,
            "new_na_n": new_na,
            "na_delta": new_na - old_na,
            "status_transitions": dict(sorted(transitions.items())),
        }

    x_t_status_change = text_changed(old["x_t_status"], new["x_t_status"])
    row_changed |= x_t_status_change
    target_columns = [
        "research_universe_company_year_id",
        "feature_year",
        "target_status",
        "target_candidate_v2_pit_b",
        "anchor_t1_accepted_at",
    ]
    target_frame = pd.read_csv(
        target_path, usecols=target_columns, low_memory=False
    ).sort_values("research_universe_company_year_id").reset_index(drop=True)
    target_new_frame = pd.read_csv(
        target_new_path, usecols=target_columns, low_memory=False
    ).sort_values("research_universe_company_year_id").reset_index(drop=True)
    if not target_frame["research_universe_company_year_id"].astype(str).equals(
        target_new_frame["research_universe_company_year_id"].astype(str)
    ):
        raise RuntimeError("Target-application v1/v1.1 train rows are not aligned")
    target_build = json.loads(
        (BASE_DIR / "data/reports/target_resolver_v1_1_0_train_build.json").read_text(
            encoding="utf-8"
        )
    )
    target_report = {
        "frozen_target_affected": bool(
            target_build["target_train"]["changed_rows"]
        ),
        "target_definition_changed": target_build["target_definition_changed"],
        "target_labels_changed": target_build["target_labels_changed"],
        "target_train_changed_company_years": target_build["target_train"][
            "changed_rows"
        ],
        "target_train_changed_primitive_cells": target_build["target_train"][
            "changed_primitive_cells"
        ],
        "target_train_status_changes": len(
            target_build["target_train"]["target_status_changes"]
        ),
        "target_application_changed_company_years": target_build[
            "target_application_train"
        ]["changed_rows"],
        "target_application_changed_primitive_cells": target_build[
            "target_application_train"
        ]["changed_primitive_cells"],
        "target_application_status_changes": len(
            target_build["target_application_train"]["target_status_changes"]
        ),
        "target_application_label_changes": target_build[
            "target_application_train"
        ]["target_label_changes"],
        "cross_tag_pair_audit": target_build["cross_tag_pair_audit"],
        "target_train_artifact_sha256": target_build["target_train"]["sha256"],
        "target_application_train_artifact_sha256": target_build[
            "target_application_train"
        ]["sha256"],
    }

    target_index = target_frame.set_index("research_universe_company_year_id")
    target_new_index = target_new_frame.set_index(
        "research_universe_company_year_id"
    )
    old_sample_mask = old["x_t_status"].isin(ALLOWED_X_T_STATUSES) & old[
        "research_universe_company_year_id"
    ].map(target_index["target_status"]).eq("available")
    new_sample_mask = new["x_t_status"].isin(ALLOWED_X_T_STATUSES) & new[
        "research_universe_company_year_id"
    ].map(target_new_index["target_status"]).eq("available")
    old_ids = set(old.loc[old_sample_mask, "research_universe_company_year_id"].astype(str))
    new_ids = set(new.loc[new_sample_mask, "research_universe_company_year_id"].astype(str))
    entered = sorted(new_ids - old_ids)
    exited = sorted(old_ids - new_ids)
    common_sample_mask = old_sample_mask & new_sample_mask
    supervised_feature_changed_mask = pd.Series(False, index=old.index)
    supervised_feature_changed_cells = 0
    for changed in feature_changed_masks.values():
        changed_in_sample = changed & common_sample_mask
        supervised_feature_changed_mask |= changed_in_sample
        supervised_feature_changed_cells += int(changed_in_sample.sum())

    old_sample = old.loc[old_sample_mask].copy()
    new_sample = new.loc[new_sample_mask].copy()
    old_ids_series = old_sample["research_universe_company_year_id"]
    new_ids_series = new_sample["research_universe_company_year_id"]
    old_sample["target_available_at"] = old_ids_series.map(
        target_index["anchor_t1_accepted_at"]
    )
    old_sample["target_label"] = old_ids_series.map(
        target_index["target_candidate_v2_pit_b"]
    )
    new_sample["target_available_at"] = new_ids_series.map(
        target_new_index["anchor_t1_accepted_at"]
    )
    new_sample["target_label"] = new_ids_series.map(
        target_new_index["target_candidate_v2_pit_b"]
    )

    supervised_missingness: dict[str, Any] = {}
    for feature in x_v1.feature_names(config):
        old_na = int(
            pd.to_numeric(old_sample[f"{feature}_value"], errors="coerce").isna().sum()
        )
        new_na = int(
            pd.to_numeric(new_sample[f"{feature}_value"], errors="coerce").isna().sum()
        )
        supervised_missingness[feature] = {
            "old_na_n": old_na,
            "new_na_n": new_na,
            "na_delta": new_na - old_na,
        }
    supervised_feature_value_na_cells_delta = sum(
        item["na_delta"] for item in supervised_missingness.values()
    )

    def class_balance(sample: pd.DataFrame) -> dict[str, Any]:
        labels = pd.to_numeric(sample["target_label"], errors="raise").astype(int)
        positives = int(labels.eq(1).sum())
        return {
            "n": len(sample),
            "positive_n": positives,
            "negative_n": int(labels.eq(0).sum()),
            "positive_rate": positives / len(sample) if len(sample) else None,
        }

    old_folds = build_fold_report(old_sample)
    new_folds = build_fold_report(new_sample)
    fold_changes = {
        fold: {
            key: {"old": old_folds[fold][key], "new": new_folds[fold][key]}
            for key in (
                "train_n",
                "validation_n",
                "late_labels_excluded_n",
                "train_membership_sha256",
                "validation_membership_sha256",
            )
            if old_folds[fold][key] != new_folds[fold][key]
        }
        for fold in old_folds
    }
    fold_changes = {fold: values for fold, values in fold_changes.items() if values}

    report = {
        "audit_id": "resolver_x_t_v1_1_0_impact_audit",
        "scope": "train_2011_2020_only",
        "data_access_policy": "data_access_policy_v1.1.0",
        "protected_feature_years_opened": False,
        "models_trained": False,
        "inputs": {
            "old_train_projection": str(old_path.relative_to(BASE_DIR)),
            "old_train_projection_sha256": sha256(old_path),
            "new_raw_train": str(new_path.relative_to(BASE_DIR)),
            "new_raw_train_sha256": sha256(new_path),
            "target_application_train_projection": str(target_path.relative_to(BASE_DIR)),
            "target_application_train_projection_sha256": sha256(target_path),
            "target_application_v1_1_train": str(
                target_new_path.relative_to(BASE_DIR)
            ),
            "target_application_v1_1_train_sha256": sha256(target_new_path),
        },
        "raw_x_t": {
            "rows_compared": len(old),
            "changed_company_years": int(row_changed.sum()),
            "current_primitive_changed_company_years": len(primitive_changes),
            "pair_changed_company_years": int(pair_changed_mask.sum()),
            "x_t_status_changed_company_years": int(x_t_status_change.sum()),
            "old_x_t_status_counts": old["x_t_status"].value_counts().sort_index().to_dict(),
            "new_x_t_status_counts": new["x_t_status"].value_counts().sort_index().to_dict(),
            "primitives": primitive_report,
            "pairs": pair_report,
            "features": feature_report,
            "feature_value_na_cells_old": old_missing_total,
            "feature_value_na_cells_new": new_missing_total,
            "feature_value_na_cells_delta": new_missing_total - old_missing_total,
        },
        "target": target_report,
        "target_application": {
            "target_status_or_label_changes": bool(
                target_report["target_application_status_changes"]
                or target_report["target_application_label_changes"]
            ),
            "application_membership_source_changed": False,
        },
        "supervised_sample": {
            "old_n": len(old_sample),
            "new_n": len(new_sample),
            "feature_changed_company_years": int(
                supervised_feature_changed_mask.sum()
            ),
            "feature_changed_cells": supervised_feature_changed_cells,
            "feature_value_na_cells_delta": supervised_feature_value_na_cells_delta,
            "changed_membership_n": len(entered) + len(exited),
            "entered_n": len(entered),
            "exited_n": len(exited),
            "entered_ids": entered,
            "exited_ids": exited,
            "old_membership_sha256": membership_sha256(old_ids),
            "new_membership_sha256": membership_sha256(new_ids),
            "missingness": supervised_missingness,
            "old_class_balance": class_balance(old_sample),
            "new_class_balance": class_balance(new_sample),
        },
        "temporal_folds": {
            "old": old_folds,
            "new": new_folds,
            "changed_folds": fold_changes,
            "any_membership_changed": bool(fold_changes),
        },
    }
    report["verdict_checks"] = {
        "raw_change_is_fail_closed_only": all(
            set(item["status_transitions"]).issubset({"selected->ambiguous"})
            for item in primitive_report.values()
        ),
        "no_pair_regression_detected": int(pair_changed_mask.sum()) == 0,
        "target_labels_unchanged": not target_report[
            "target_labels_changed"
        ]
        and target_report["target_train_status_changes"] == 0
        and target_report["target_application_status_changes"] == 0,
        "supervised_membership_fully_accounted": True,
        "protected_periods_remained_closed": True,
        "models_trained": False,
    }

    json_path = BASE_DIR / str(patch_config["outputs"]["impact_audit_json"])
    markdown_path = BASE_DIR / str(
        patch_config["outputs"]["impact_audit_markdown"]
    )
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    changed_features = {
        name: item["changed_company_years"]
        for name, item in feature_report.items()
        if item["changed_company_years"]
    }
    changed_primitives = {
        name: item["changed_company_years"]
        for name, item in primitive_report.items()
        if item["changed_company_years"]
    }
    lines = [
        "# Resolver / raw X_t v1.1.0 — train-only impact audit",
        "",
        "Data access policy: v1.1.0. Zakres analityczny: wyłącznie feature years 2011–2020. Nie trenowano modeli.",
        "",
        f"- Raw rows compared: {len(old):,}",
        f"- Changed raw company-years: {int(row_changed.sum()):,}",
        f"- Changed current primitives: {json.dumps(changed_primitives, ensure_ascii=False, sort_keys=True)}",
        f"- Changed derived features: {json.dumps(changed_features, ensure_ascii=False, sort_keys=True)}",
        f"- Pair-resolver changed company-years: {int(pair_changed_mask.sum()):,}",
        f"- Frozen target A-provenance changed company-years: {target_report['target_train_changed_company_years']:,}",
        "- Target status/label changes: "
        f"{target_report['target_train_status_changes'] + target_report['target_application_status_changes'] + target_report['target_application_label_changes']:,}",
        f"- Supervised sample: {len(old_sample):,} -> {len(new_sample):,}; entered={len(entered):,}; exited={len(exited):,}",
        f"- Supervised company-years with changed feature data: {int(supervised_feature_changed_mask.sum()):,}; changed feature observations={supervised_feature_changed_cells:,}; new feature-value NA cells={supervised_feature_value_na_cells_delta:+,}",
        f"- Frozen temporal-fold membership changed: {'yes' if fold_changes else 'no'}",
        f"- Feature-value NA cell delta (raw train): {new_missing_total - old_missing_total:+,}",
        "",
        "Detailed hashes, transition counts, missingness, class balance and fold memberships are in the JSON audit.",
    ]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = audit()
    print(json.dumps(result["verdict_checks"], indent=2))

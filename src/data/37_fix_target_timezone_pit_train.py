"""Normalize train-only SEC acceptance timestamps and audit temporal folds.

This script reads only physically isolated 2011--2020 artifacts.  It changes
timestamp representations, never target definitions, labels, feature values,
or model inputs.  No estimator is imported or fitted.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from src.data.sec_timestamps import normalize_sec_acceptance_timestamp
from src.modeling.temporal_cv import (
    iter_point_in_time_folds,
    iter_temporal_folds,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs/timezone_pit_fix_v1_0_0.yaml"
ID_COLUMN = "research_universe_company_year_id"
ALLOWED_X_T_STATUSES = {"available_core", "partially_available"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def membership_sha256(values: Any) -> str:
    payload = "".join(f"{value}\n" for value in sorted(str(item) for item in values))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if config.get("scope", {}).get("permitted_feature_years") != [2011, 2020]:
        raise RuntimeError("Timezone fix is not constrained to train 2011--2020.")
    return config


def _timestamp_columns(header: list[str]) -> list[int]:
    return [
        index
        for index, name in enumerate(header)
        if name == "accepted_at" or name.endswith("_accepted_at")
    ]


def load_accession_timestamp_map(raw_x_path: Path) -> dict[str, str]:
    """Load canonical instants already frozen for train X_t anchor accessions."""

    frame = pd.read_csv(
        raw_x_path,
        usecols=["feature_year", "anchor_accession", "prediction_timestamp"],
        dtype={"anchor_accession": str, "prediction_timestamp": str},
        low_memory=False,
    )
    years = pd.to_numeric(frame["feature_year"], errors="raise").astype(int)
    if not years.between(2011, 2020).all():
        raise RuntimeError("X_t accession timestamp source is not train-only.")
    parsed = pd.to_datetime(frame["prediction_timestamp"], errors="raise", utc=True)
    frame["canonical_timestamp"] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    grouped = frame.groupby("anchor_accession", dropna=True)["canonical_timestamp"].nunique()
    conflicts = grouped[grouped.gt(1)]
    if not conflicts.empty:
        raise RuntimeError(
            "Frozen X_t contains conflicting instants for the same accession: "
            f"{conflicts.index.astype(str).tolist()[:5]}"
        )
    return (
        frame.dropna(subset=["anchor_accession"])
        .drop_duplicates("anchor_accession")
        .set_index("anchor_accession")["canonical_timestamp"]
        .astype(str)
        .to_dict()
    )


def _paired_accession_index(header: list[str], timestamp_name: str) -> int | None:
    candidates: list[str] = []
    if timestamp_name == "universe_anchor_accepted_at":
        candidates.append("universe_anchor_accession")
    if timestamp_name == "membership_available_at":
        candidates.extend(("universe_anchor_accession", "anchor_accession"))
    if timestamp_name == "accepted_at":
        candidates.extend(("accn", "accession"))
    if timestamp_name.endswith("_accepted_at"):
        stem = timestamp_name[: -len("_accepted_at")]
        candidates.extend((f"{stem}_accn", f"{stem}_accession"))
    for candidate in candidates:
        if candidate in header:
            return header.index(candidate)
    return None


def rewrite_target_artifact(
    source: Path,
    destination: Path,
    accession_timestamps: dict[str, str],
) -> dict[str, Any]:
    """Rewrite only SEC-derived timestamp cells in one train-only CSV."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    rows = 0
    changed_rows = 0
    changed_cells = 0
    accession_resolved_cells = 0
    with source.open("r", encoding="utf-8", newline="") as input_stream, temporary.open(
        "w", encoding="utf-8", newline=""
    ) as output_stream:
        reader = csv.reader(input_stream)
        writer = csv.writer(output_stream, lineterminator="\n")
        try:
            header = next(reader)
        except StopIteration as error:
            raise RuntimeError(f"Empty target artifact: {source}") from error
        if "feature_year" not in header:
            raise RuntimeError(f"Missing feature_year in {source}")
        year_index = header.index("feature_year")
        timestamp_indexes = _timestamp_columns(header)
        accession_indexes = {
            index: _paired_accession_index(header, header[index])
            for index in timestamp_indexes
        }
        membership_available_index = (
            header.index("membership_available_at")
            if "membership_available_at" in header
            else None
        )
        membership_precision_index = (
            header.index("membership_available_at_precision")
            if "membership_available_at_precision" in header
            else None
        )
        writer.writerow(header)
        for row in reader:
            if len(row) != len(header):
                raise RuntimeError(f"Malformed CSV row {rows + 2} in {source}")
            year = int(row[year_index])
            if not 2011 <= year <= 2020:
                raise RuntimeError(
                    f"Forbidden feature year {year} in train-only input {source}"
                )
            row_changed = False
            for index in timestamp_indexes:
                accession_index = accession_indexes[index]
                accession = row[accession_index] if accession_index is not None else ""
                if accession and accession in accession_timestamps:
                    normalized = accession_timestamps[accession]
                    accession_resolved_cells += 1
                else:
                    normalized = normalize_sec_acceptance_timestamp(row[index])
                if normalized != row[index]:
                    row[index] = normalized
                    changed_cells += 1
                    row_changed = True
            if (
                membership_available_index is not None
                and membership_precision_index is not None
                and row[membership_precision_index] == "timestamp"
            ):
                membership_accession_index = _paired_accession_index(
                    header, "membership_available_at"
                )
                accession = (
                    row[membership_accession_index]
                    if membership_accession_index is not None
                    else ""
                )
                if accession and accession in accession_timestamps:
                    normalized = accession_timestamps[accession]
                    accession_resolved_cells += 1
                else:
                    normalized = normalize_sec_acceptance_timestamp(
                        row[membership_available_index]
                    )
                if normalized != row[membership_available_index]:
                    row[membership_available_index] = normalized
                    changed_cells += 1
                    row_changed = True
            writer.writerow(row)
            rows += 1
            changed_rows += int(row_changed)
    temporary.replace(destination)
    try:
        displayed_path = str(destination.relative_to(ROOT))
    except ValueError:
        displayed_path = str(destination)
    return {
        "path": displayed_path,
        "rows": rows,
        "timestamp_columns": len(timestamp_indexes),
        "changed_rows": changed_rows,
        "changed_timestamp_cells": changed_cells,
        "accession_resolved_timestamp_cells": accession_resolved_cells,
        "non_timestamp_cells_changed": 0,
        "sha256": sha256(destination),
    }


def _load_target_projection(path: Path) -> pd.DataFrame:
    columns = [
        ID_COLUMN,
        "feature_year",
        "membership_status",
        "economic_group_id",
        "target_status",
        "target_candidate_v2_pit_b",
        "anchor_t1_accn",
        "anchor_t1_accepted_at",
    ]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    years = pd.to_numeric(frame["feature_year"], errors="raise").astype(int)
    if not years.between(2011, 2020).all():
        raise RuntimeError(f"Target projection is not train-only: {path}")
    frame["feature_year"] = years
    if frame[ID_COLUMN].duplicated().any():
        raise RuntimeError(f"Duplicate target identity in {path}")
    return frame


def _load_raw_projection(path: Path) -> pd.DataFrame:
    columns = [
        ID_COLUMN,
        "feature_year",
        "membership_status",
        "economic_group_id",
        "prediction_timestamp",
        "x_t_status",
    ]
    frame = pd.read_csv(path, usecols=columns, low_memory=False)
    years = pd.to_numeric(frame["feature_year"], errors="raise").astype(int)
    if not years.between(2011, 2020).all():
        raise RuntimeError(f"Raw X_t projection is not train-only: {path}")
    frame["feature_year"] = years
    if frame[ID_COLUMN].duplicated().any():
        raise RuntimeError(f"Duplicate X_t identity in {path}")
    return frame


def _supervised_sample(raw: pd.DataFrame, target: pd.DataFrame) -> pd.DataFrame:
    renamed = target.rename(
        columns={
            "feature_year": "target_feature_year",
            "membership_status": "target_membership_status",
            "economic_group_id": "target_economic_group_id",
            "target_candidate_v2_pit_b": "target_label",
            "anchor_t1_accepted_at": "target_available_at",
        }
    )
    sample = raw.merge(renamed, on=ID_COLUMN, how="left", validate="one_to_one")
    alignment = (
        sample["feature_year"].eq(sample["target_feature_year"])
        & sample["economic_group_id"].astype(str).eq(
            sample["target_economic_group_id"].astype(str)
        )
    )
    if not alignment.all():
        raise RuntimeError("Raw X_t and target identity metadata disagree.")
    keep = (
        sample["membership_status"].eq("eligible")
        & sample["target_membership_status"].eq("eligible")
        & sample["target_status"].eq("available")
        & sample["x_t_status"].isin(ALLOWED_X_T_STATUSES)
    )
    return sample.loc[keep].sort_values(
        ["feature_year", ID_COLUMN], kind="mergesort"
    ).reset_index(drop=True)


def _baseline_fold_memberships(sample: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Reproduce pre-fix behavior without the new strict own-row invariant."""

    result: dict[str, dict[str, Any]] = {}
    for fold, base_train, validation in iter_temporal_folds(sample):
        target_available_at = pd.to_datetime(
            base_train["target_available_at"], errors="raise", utc=True
        )
        validation_prediction_at = pd.to_datetime(
            validation["prediction_timestamp"], errors="raise", utc=True
        )
        cutoff = validation_prediction_at.min()
        train = base_train.loc[target_available_at.le(cutoff)]
        result[fold.name] = {
            "train_ids": set(train[ID_COLUMN].astype(str)),
            "validation_ids": set(validation[ID_COLUMN].astype(str)),
            "cutoff": cutoff,
        }
    return result


def _fixed_fold_memberships(sample: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for fold, train, validation, audit in iter_point_in_time_folds(sample):
        target_at = pd.to_datetime(train["target_available_at"], errors="raise", utc=True)
        prediction_at = pd.to_datetime(
            train["prediction_timestamp"], errors="raise", utc=True
        )
        cutoff = audit.validation_prediction_cutoff
        own_order_violations = int((~prediction_at.lt(target_at)).sum())
        cutoff_violations = int((~target_at.le(cutoff)).sum())
        if own_order_violations or cutoff_violations:
            raise RuntimeError(f"PIT invariant failed in {fold.name}")
        result[fold.name] = {
            "train_ids": set(train[ID_COLUMN].astype(str)),
            "validation_ids": set(validation[ID_COLUMN].astype(str)),
            "cutoff": cutoff,
            "own_order_violations": own_order_violations,
            "cutoff_violations": cutoff_violations,
            "late_labels_excluded_n": audit.label_unavailable_rows_excluded,
        }
    return result


def audit(
    old_target_path: Path,
    new_target_path: Path,
    raw_x_path: Path,
    *,
    raw_x_sha256_before: str,
) -> dict[str, Any]:
    old_target = _load_target_projection(old_target_path)
    new_target = _load_target_projection(new_target_path)
    raw = _load_raw_projection(raw_x_path)
    old_indexed = old_target.sort_values(ID_COLUMN).reset_index(drop=True)
    new_indexed = new_target.sort_values(ID_COLUMN).reset_index(drop=True)
    if not old_indexed[ID_COLUMN].equals(new_indexed[ID_COLUMN]):
        raise RuntimeError("Target overlay membership changed during timezone fix.")
    label_columns = ["target_status", "target_candidate_v2_pit_b"]
    labels_unchanged = old_indexed[label_columns].fillna("").astype(str).equals(
        new_indexed[label_columns].fillna("").astype(str)
    )
    if not labels_unchanged:
        raise RuntimeError("Target labels or statuses changed during timezone fix.")
    raw_x_sha256_after = sha256(raw_x_path)
    if raw_x_sha256_after != raw_x_sha256_before:
        raise RuntimeError("Raw X_t changed during timezone fix.")

    old_sample = _supervised_sample(raw, old_target)
    new_sample = _supervised_sample(raw, new_target)
    if not old_sample[ID_COLUMN].equals(new_sample[ID_COLUMN]):
        raise RuntimeError("Supervised sample membership changed during timezone fix.")
    if not old_sample["target_label"].fillna("").astype(str).equals(
        new_sample["target_label"].fillna("").astype(str)
    ):
        raise RuntimeError("Supervised target labels changed during timezone fix.")

    all_prediction_at = pd.to_datetime(
        new_sample["prediction_timestamp"], errors="raise", utc=True
    )
    all_target_at = pd.to_datetime(
        new_sample["target_available_at"], errors="raise", utc=True
    )
    supervised_own_order_violations = int(
        (~all_prediction_at.lt(all_target_at)).sum()
    )
    if supervised_own_order_violations:
        raise RuntimeError(
            "prediction_timestamp < target_available_at fails in fixed sample."
        )

    old_folds = _baseline_fold_memberships(old_sample)
    new_folds = _fixed_fold_memberships(new_sample)
    fold_report: list[dict[str, Any]] = []
    changed_memberships: list[dict[str, Any]] = []
    new_target_lookup = new_sample.set_index(ID_COLUMN)
    old_target_lookup = old_sample.set_index(ID_COLUMN)
    for fold_name in old_folds:
        old_fold = old_folds[fold_name]
        new_fold = new_folds[fold_name]
        removed = sorted(old_fold["train_ids"] - new_fold["train_ids"])
        added = sorted(new_fold["train_ids"] - old_fold["train_ids"])
        if old_fold["validation_ids"] != new_fold["validation_ids"]:
            raise RuntimeError(f"Validation membership changed in {fold_name}")
        for direction, identifiers in (("removed", removed), ("added", added)):
            for identifier in identifiers:
                old_row = old_target_lookup.loc[identifier]
                new_row = new_target_lookup.loc[identifier]
                changed_memberships.append(
                    {
                        "fold": fold_name,
                        "change": direction,
                        "research_universe_company_year_id": identifier,
                        "feature_year": int(new_row["feature_year"]),
                        "anchor_t1_accn": str(new_row["anchor_t1_accn"]),
                        "prediction_timestamp": str(new_row["prediction_timestamp"]),
                        "target_available_at_before": str(
                            old_row["target_available_at"]
                        ),
                        "target_available_at_after": str(
                            new_row["target_available_at"]
                        ),
                    }
                )
        fold_report.append(
            {
                "id": fold_name,
                "pit_safe_train_n_before": len(old_fold["train_ids"]),
                "pit_safe_train_n_after": len(new_fold["train_ids"]),
                "validation_n": len(new_fold["validation_ids"]),
                "train_membership_sha256_before": membership_sha256(
                    old_fold["train_ids"]
                ),
                "train_membership_sha256_after": membership_sha256(
                    new_fold["train_ids"]
                ),
                "validation_membership_sha256": membership_sha256(
                    new_fold["validation_ids"]
                ),
                "validation_prediction_cutoff": str(new_fold["cutoff"]),
                "removed_company_years": removed,
                "added_company_years": added,
                "prediction_before_target_violations": new_fold[
                    "own_order_violations"
                ],
                "target_after_cutoff_violations": new_fold["cutoff_violations"],
                "late_labels_excluded_n": new_fold["late_labels_excluded_n"],
            }
        )

    labels = pd.to_numeric(new_sample["target_label"], errors="raise").astype(int)
    return {
        "scope": "train_2011_2020_only",
        "protected_feature_years_opened": False,
        "models_trained": False,
        "target_definition_changed": False,
        "target_labels_unchanged": labels_unchanged,
        "target_statuses_unchanged": labels_unchanged,
        "x_t_artifact_unchanged": raw_x_sha256_before == raw_x_sha256_after,
        "raw_x_t_sha256_before": raw_x_sha256_before,
        "raw_x_t_sha256_after": raw_x_sha256_after,
        "supervised_sample_n": len(new_sample),
        "supervised_membership_sha256": membership_sha256(new_sample[ID_COLUMN]),
        "positive_n": int(labels.eq(1).sum()),
        "negative_n": int(labels.eq(0).sum()),
        "supervised_prediction_before_target_violations": (
            supervised_own_order_violations
        ),
        "all_six_folds_pass_label_availability": all(
            row["prediction_before_target_violations"] == 0
            and row["target_after_cutoff_violations"] == 0
            for row in fold_report
        ),
        "folds": fold_report,
        "changed_memberships": changed_memberships,
    }


def build(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    config = load_config(config_path)
    inputs = {name: ROOT / value for name, value in config["inputs"].items()}
    outputs = {name: ROOT / value for name, value in config["outputs"].items()}
    raw_x_sha256_before = sha256(inputs["raw_x_t_train"])
    accession_timestamps = load_accession_timestamp_map(inputs["raw_x_t_train"])
    target_train = rewrite_target_artifact(
        inputs["target_train"], outputs["target_train"], accession_timestamps
    )
    target_application = rewrite_target_artifact(
        inputs["target_application_train"],
        outputs["target_application_train"],
        accession_timestamps,
    )
    result = audit(
        inputs["target_application_train"],
        outputs["target_application_train"],
        inputs["raw_x_t_train"],
        raw_x_sha256_before=raw_x_sha256_before,
    )
    result["artifacts"] = {
        "target_train": target_train,
        "target_application_train": target_application,
    }
    report_path = outputs["audit_report"]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    result["audit_report"] = {
        "path": str(report_path.relative_to(ROOT)),
        "sha256": sha256(report_path),
    }
    return result


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, ensure_ascii=False))

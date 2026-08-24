"""Fail-closed execution for the preregistered protected-period extension.

The CLI intentionally accepts only named, zero-argument actions.  It never
accepts an arbitrary data path, year, model identity, output directory or
metric.  Access to protected content is enabled only by committed, reviewed
scope and gate artifacts checked by the corresponding action.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import date, datetime
from functools import partial
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yaml
from scipy.special import expit
from sklearn.decomposition import PCA
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from src.data import target_candidate_v2_pit as target_v1
from src.data import target_resolver_v1_1 as target_patch
from src.data import x_t_pit as x_v1
from src.data import x_t_pit_v1_1 as x_patch
from src.modeling.preprocessing import FinancialPreprocessor, features_for_blocks
from src.modeling.production_runner import (
    BLOCK_AGNOSTIC,
    BLOCK_PARTS,
    FoldTask,
    ProductionExperimentRunner,
    SubprocessFoldExecutor,
    atomic_write_json,
    canonical_sha256,
    file_sha256,
    membership_sha256,
)
from src.modeling.model_execution_contract import load_contract


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "configs/protected_period_execution_contract_v1_0_0.yaml"
EXECUTION_REPAIR_PATH = ROOT / "configs/protected_period_execution_repair_v1_0_1.yaml"
ACCESS_MANIFEST_PATH = ROOT / "configs/protected_period_access_manifest_v1_0_0.yaml"
SPENT_GATE_MANIFEST_PATH = ROOT / "configs/protected_period_spent_gate_v1_0_0.yaml"
SPENT_REVIEW_PATH = ROOT / "configs/protected_period_access_review_v1_0_1_result.json"
SPENT_GATE_RESULT_PATH = ROOT / "configs/protected_period_spent_gate_recheck_v1_0_1_result.json"
SPENT_EXECUTION_EVIDENCE_PATH = (
    ROOT / "configs/protected_period_spent_execution_v1_0_0_result.json"
)
SPENT_FREEZE_RESULT_PATH = ROOT / "configs/protected_period_spent_freeze_v1_0_0_result.json"
SECOND_GATE_MANIFEST_PATH = ROOT / "configs/protected_period_second_integrity_gate_v1_0_0.yaml"
SECOND_GATE_REVIEW_PATH = ROOT / "configs/protected_period_second_integrity_review_v1_0_0_result.json"
SECOND_GATE_RESULT_PATH = ROOT / "configs/protected_period_second_integrity_gate_v1_0_0_result.json"
FEATURE_ACCESS_MANIFEST_PATH = ROOT / "configs/protected_period_feature_access_manifest_v1_0_0.yaml"
FEATURE_REVIEW_PATH = ROOT / "configs/protected_period_feature_access_review_v1_0_0_result.json"
FEATURE_GATE_RESULT_PATH = ROOT / "configs/protected_period_feature_gate_v1_0_0_result.json"
FEATURE_EXECUTION_EVIDENCE_PATH = ROOT / "configs/protected_period_feature_execution_v1_0_0_result.json"
FEATURE_AUDIT_RESULT_PATH = ROOT / "configs/protected_period_feature_execution_audit_v1_0_0_result.json"
LABEL_ACCESS_MANIFEST_PATH = ROOT / "configs/protected_period_label_access_manifest_v1_0_0.yaml"
LABEL_REVIEW_PATH = ROOT / "configs/protected_period_label_access_review_v1_0_0_result.json"
LABEL_GATE_RESULT_PATH = ROOT / "configs/protected_period_label_gate_v1_0_0_result.json"
HOLDOUT_EVALUATION_EVIDENCE_PATH = ROOT / "configs/protected_period_holdout_evaluation_v1_0_0_result.json"
HOLDOUT_FREEZE_RESULT_PATH = ROOT / "configs/protected_period_holdout_freeze_v1_0_0_result.json"

DATA_ROOT = ROOT / "data/protected_period_extension_v1"
RUN_ROOT = ROOT / "data/model_runs/protected_period_extension_v1"
REPORT_ROOT = ROOT / "reports/protected_period_extension_v1"
SPENT_REPORT_PATH = REPORT_ROOT / "spent_report_v1_0_0.json"
HOLDOUT_REPORT_PATH = REPORT_ROOT / "holdout_report_v1_0_0.json"

FULL_X_T_PATH = ROOT / "data/processed/x_t_pit_v1_raw.csv"
FULL_TARGET_APPLICATION_PATH = (
    ROOT / "data/processed/research_universe_pit_v1_1_0_target_pit_b_v1_0_0.csv"
)
FROZEN_TRAIN_X_T_PATH = ROOT / "data/processed/x_t_pit_v1_1_0_train.csv"
FROZEN_TRAIN_TARGET_PATH = (
    ROOT / "data/processed/research_universe_pit_v1_1_0_target_pit_b_v1_2_0_train.csv"
)
SPENT_BASE_X_T_PATH = DATA_ROOT / "spent/x_t_v1_base_through_2022.csv"
SPENT_REBUILT_X_T_PATH = DATA_ROOT / "spent/x_t_v1_1_rebuild_through_2022.csv"
SPENT_CORRECTED_X_T_PATH = DATA_ROOT / "spent/x_t_v1_1_corrected_through_2022.csv"
SPENT_TARGET_V1_PATH = DATA_ROOT / "spent/target_application_v1_through_2022.csv"
SPENT_TARGET_CORRECTED_PATH = DATA_ROOT / "spent/target_application_v1_1_through_2022.csv"
HOLDOUT_BASE_X_T_PATH = DATA_ROOT / "holdout/x_t_v1_base_through_2024.csv"
HOLDOUT_REBUILT_X_T_PATH = DATA_ROOT / "holdout/x_t_v1_1_rebuild_through_2024.csv"
HOLDOUT_CORRECTED_X_T_PATH = DATA_ROOT / "holdout/x_t_v1_1_corrected_through_2024.csv"
HOLDOUT_TARGET_BASE_PATH = DATA_ROOT / "holdout/target_candidate_v2_pit_b_2023_2024_v1.csv"
HOLDOUT_TARGET_CORRECTED_PATH = DATA_ROOT / "holdout/target_candidate_v2_pit_b_2023_2024_v1_1.csv"

CLASSICAL_PYTHON = ROOT / ".venv-classical/bin/python"
QNN_PYTHON = ROOT / ".venv-qnn-mlp/bin/python"
RUNNER_CONFIG_PATH = ROOT / "configs/production_experiment_runner_v1_0_1_lightning.yaml"
BASE_EXECUTION_CONTRACT_PATH = ROOT / "configs/model_execution_contract_v1_2_1_lightning_scientific_patch.yaml"
PRIMARY_ROSTER_PATH = ROOT / "data/model_runs/post_coarse_v1_3_0/final_primary_development_ranking.json"
QNN_ANSATZ_PATH = ROOT / "data/model_runs/post_coarse_v1_3_0/qnn_selected_ansatz.json"
CALIBRATION_ROOT = ROOT / "data/model_runs/post_coarse_v1_3_0"

SEEDS = (20260818, 20260819, 20260820)
DETERMINISTIC_FAMILIES = {"dummy_prior", "fixed_l2_logistic", "rbf_svm"}
FEATURES = tuple(features_for_blocks(("L", "D", "R")))


class ProtectedExtensionError(RuntimeError):
    """Fail-closed protected-path error."""


def _load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProtectedExtensionError(f"Expected mapping: {path}")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProtectedExtensionError(f"Expected JSON object: {path}")
    return value


def _sha(path: Path) -> str:
    return file_sha256(path)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtectedExtensionError(message)


def _verified_file(path: Path, sha256: str) -> Path:
    _require(path.is_file(), f"Missing exact file: {path}")
    _require(_sha(path) == sha256, f"SHA-256 mismatch: {path}")
    return path


def _verify_frozen_implementation(contract: Mapping[str, Any]) -> None:
    implementation = contract.get("implementation")
    _require(isinstance(implementation, Mapping), "Implementation freeze is absent.")
    for name, item in implementation.items():
        _require(isinstance(item, Mapping), "Invalid implementation freeze item.")
        actual = _sha(ROOT / str(item["path"]))
        expected = str(item["sha256"])
        if actual == expected:
            continue
        _require(
            name == "successor_runner_evaluator_and_verifiers"
            and EXECUTION_REPAIR_PATH.is_file(),
            f"Unreviewed implementation change: {item['path']}",
        )
        repair_document = _load_yaml(EXECUTION_REPAIR_PATH)
        repair = repair_document["repair"]
        failure = repair_document["failure"]
        repair_identity = repair_document["execution_repair"]
        _require(
            repair["superseded_runner_sha256"] == expected
            and repair["repaired_runner_sha256"] == actual
            and repair_identity["methodology_changed"] is False
            and failure["model_fit_started_before_failure"] is False,
            "Execution repair authority mismatch.",
        )


def scope_sha256(scope: Mapping[str, Any]) -> str:
    definition = scope.get("definition")
    _require(isinstance(definition, Mapping), "Scope lacks a definition mapping.")
    return canonical_sha256(definition)


def _reviewed_scope(
    manifest_path: Path,
    review_path: Path,
    scope_name: str,
    expected_review_verdict: str,
) -> tuple[str, str]:
    manifest = _load_yaml(manifest_path)
    review = _load_json(review_path)
    scopes = manifest.get("scopes")
    _require(isinstance(scopes, Mapping) and scope_name in scopes, "Unknown access scope.")
    scope = scopes[scope_name]
    actual = scope_sha256(scope)
    _require(actual == scope.get("definition_sha256"), "Stored scope hash mismatch.")
    _require(review.get("verdict") == expected_review_verdict, "Access review did not pass.")
    _require(review.get("subject_manifest_sha256") == _sha(manifest_path), "Review subject mismatch.")
    reviewed = review.get("scopes") or {}
    item = reviewed.get(scope_name) if isinstance(reviewed, Mapping) else None
    _require(isinstance(item, Mapping), "Scope is absent from review result.")
    _require(item.get("verdict") == "PASS", "Scope review did not pass.")
    _require(item.get("definition_sha256") == actual, "Reviewed scope hash mismatch.")
    return str(scope.get("id")), actual


def _require_gate(
    result_path: Path,
    verdict: str,
    manifest_path: Path,
    scope_id: str,
    scope_hash: str,
) -> dict[str, Any]:
    result = _load_json(result_path)
    _require(result.get("verdict") == verdict, f"Required gate verdict is not {verdict}.")
    _require(result.get("gate_manifest_sha256") == _sha(manifest_path), "Gate manifest hash mismatch.")
    _require(result.get("scope_id") == scope_id, "Gate scope ID mismatch.")
    _require(result.get("scope_sha256") == scope_hash, "Gate scope hash mismatch.")
    return result


def route_csv_through_year(
    source: Path,
    destination: Path,
    *,
    year_field_index: int,
    expected_year_field: bytes,
    maximum_feature_year: int,
) -> int:
    """Copy permitted records after decoding only one early routing field."""

    _require(maximum_feature_year in {2022, 2024}, "Unsupported protected route.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    selected = 0
    with source.open("rb") as input_stream, temporary.open("wb") as output_stream:
        header = input_stream.readline()
        _require(
            x_patch._csv_prefix_field(header, year_field_index) == expected_year_field,
            "Unexpected protected CSV routing field.",
        )
        output_stream.write(header)
        for raw_line in input_stream:
            raw_year = x_patch._csv_prefix_field(raw_line, year_field_index).strip().strip(b'"')
            _require(len(raw_year) == 4 and raw_year.isdigit(), "Invalid year routing key.")
            year = int(raw_year)
            _require(2011 <= year <= 2024, "Unexpected feature year in mixed artifact.")
            if year <= maximum_feature_year:
                output_stream.write(raw_line)
                selected += 1
    os.replace(temporary, destination)
    return selected


def _extended_x_t_config(maximum_feature_year: int) -> tuple[dict[str, Any], dict[str, Any], Any]:
    patch_config = x_patch.load_patch_config()
    config = x_patch.resolved_v1_1_config(patch_config)
    config["x_t"].update(
        {
            "feature_year_start": 2011,
            "feature_year_end": maximum_feature_year,
            "development_year_start": 2011,
            "development_year_end": maximum_feature_year,
            "test_years": [],
        }
    )
    semantic_config = x_patch.semantic_v1_1.load_config(
        ROOT / str(patch_config["inputs"]["primitive_policy"])
    )
    base_scope = x_patch.semantic_v1_1.parse_scope(semantic_config)
    pit = config["point_in_time"]
    scope = replace(
        base_scope,
        feature_year_start=2011,
        feature_year_end=maximum_feature_year,
        annual_period_min_days=int(pit["annual_period_min_days"]),
        annual_period_max_days=int(pit["annual_period_max_days"]),
        period_start_tolerance_days=int(pit["period_start_tolerance_days"]),
        minimum_denominator_usd=0.0,
    )
    return config, semantic_config, scope


def _validate_corrected_x_t(path: Path, config: Mapping[str, Any], maximum_feature_year: int, expected_rows: int) -> None:
    columns = ["research_universe_company_year_id", "feature_year", "feature_policy_version"]
    seen: set[str] = set()
    rows = 0
    for frame in pd.read_csv(path, usecols=columns, dtype=str, chunksize=4000, low_memory=False):
        years = pd.to_numeric(frame["feature_year"], errors="raise").astype(int)
        _require(years.between(2011, maximum_feature_year).all(), "Corrected X_t year escaped scope.")
        _require(frame["feature_policy_version"].eq("1.1.0").all(), "Feature policy mismatch.")
        ids = frame["research_universe_company_year_id"].astype(str)
        _require(not ids.duplicated().any() and not any(item in seen for item in ids), "Duplicate X_t ID.")
        seen.update(ids)
        rows += len(frame)
    _require(rows == expected_rows, "Corrected X_t row count differs from routed base.")
    _require(list(pd.read_csv(path, nrows=0).columns) == x_v1.output_columns(config), "X_t schema changed.")


def build_corrected_x_t(
    *,
    maximum_feature_year: int,
    base_projection: Path,
    rebuild_path: Path,
    corrected_path: Path,
) -> dict[str, Any]:
    contract = _load_yaml(CONTRACT_PATH)
    source = contract["data_sources"]["full_x_t_v1"]
    _verified_file(ROOT / source["path"], str(source["sha256"]))
    expected_rows = route_csv_through_year(
        FULL_X_T_PATH,
        base_projection,
        year_field_index=2,
        expected_year_field=b"feature_year",
        maximum_feature_year=maximum_feature_year,
    )
    config, semantic_config, scope = _extended_x_t_config(maximum_feature_year)
    projection_columns = list(x_v1.METADATA_COLUMNS)
    for primitive in x_patch._REVIEWED_PRIMITIVES:
        projection_columns.extend(
            [
                f"current_t_{primitive}_reason",
                f"current_t_{primitive}_tag",
                f"current_t_{primitive}_strategy",
                f"current_t_{primitive}_accn",
            ]
        )
    projection = pd.read_csv(
        base_projection,
        usecols=list(dict.fromkeys(projection_columns)),
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    _require(len(projection) == expected_rows, "Routed X_t changed while parsing.")
    source_rows = x_patch.source_rows_from_projection(projection)
    period_ends = {
        (str(row["cik10"]).zfill(10), int(row["feature_year"])): date.fromisoformat(str(row["period_end"]))
        for row in source_rows
        if str(row.get("period_end", ""))
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        grouped[str(row["cik10"]).zfill(10)].append(row)
    items = [(cik, grouped[cik]) for cik in sorted(grouped)]
    worker = partial(
        x_patch._process_company,
        config=config,
        semantic_config=semantic_config,
        scope=scope,
        period_ends=period_ends,
        companyfacts_root=ROOT / "data/raw/research_universe_target_application/companyfacts",
        evidence_root=ROOT / "data/raw/sec_filings/revenue_statement_evidence",
        negative_sign_review=x_patch.reconstructed_negative_reviews(projection),
    )
    rebuild_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = rebuild_path.with_suffix(rebuild_path.suffix + ".tmp")
    first = True
    processed = 0
    buffer: list[dict[str, Any]] = []
    workers = max(1, int(os.environ.get("PROTECTED_X_T_WORKERS", "6")))
    with ProcessPoolExecutor(max_workers=workers) as executor:
        for company_rows in executor.map(worker, items, chunksize=8):
            buffer.extend(company_rows)
            if len(buffer) < 500:
                continue
            chunk = pd.DataFrame(buffer).reindex(columns=x_v1.output_columns(config))
            chunk.to_csv(temporary, mode="w" if first else "a", header=first, index=False, lineterminator="\n", float_format="%.17g")
            first = False
            processed += len(chunk)
            buffer = []
    if buffer:
        chunk = pd.DataFrame(buffer).reindex(columns=x_v1.output_columns(config))
        chunk.to_csv(temporary, mode="w" if first else "a", header=first, index=False, lineterminator="\n", float_format="%.17g")
        processed += len(chunk)
    _require(processed == expected_rows, "Protected X_t rebuild row count mismatch.")
    os.replace(temporary, rebuild_path)
    correction = x_patch.materialize_fail_closed_correction(
        base_projection, rebuild_path, corrected_path, config
    )
    _validate_corrected_x_t(corrected_path, config, maximum_feature_year, expected_rows)
    return {
        "maximum_feature_year": maximum_feature_year,
        "rows": expected_rows,
        "base_projection_sha256": _sha(base_projection),
        "rebuild_sha256": _sha(rebuild_path),
        "corrected_sha256": _sha(corrected_path),
        "correction": correction,
    }


def build_corrected_spent_target_application() -> dict[str, Any]:
    contract = _load_yaml(CONTRACT_PATH)
    source = contract["data_sources"]["full_target_application_v1"]
    _verified_file(ROOT / source["path"], str(source["sha256"]))
    rows = route_csv_through_year(
        FULL_TARGET_APPLICATION_PATH,
        SPENT_TARGET_V1_PATH,
        year_field_index=3,
        expected_year_field=b"feature_year",
        maximum_feature_year=2022,
    )
    _by_key, by_id = target_patch.load_single_period_corrections(
        SPENT_BASE_X_T_PATH, SPENT_CORRECTED_X_T_PATH
    )
    config = target_v1.load_config()
    result = target_patch.patch_target_csv(
        SPENT_TARGET_V1_PATH,
        SPENT_TARGET_CORRECTED_PATH,
        by_id,
        key_mode="id",
        config=config,
        scope=target_v1.parse_scope(config),
        application=True,
    )
    _require(int(result["rows"]) == rows, "Spent target-application row count mismatch.")
    _require(int(result["target_label_changes"]) == 0, "Resolver correction changed a frozen target label.")
    return result


def _read_modeling_inputs(maximum_feature_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw_new_path = SPENT_CORRECTED_X_T_PATH if maximum_feature_year == 2022 else HOLDOUT_CORRECTED_X_T_PATH
    financial = list(FEATURES)
    raw_columns = [
        "research_universe_company_year_id",
        "cik10",
        "feature_year",
        "membership_status",
        "economic_group_id",
        "prediction_timestamp",
        "x_t_status",
        *[f"{feature}_value" for feature in financial],
    ]
    target_columns = [
        "research_universe_company_year_id",
        "cik10",
        "feature_year",
        "membership_status",
        "economic_group_id",
        "target_status",
        "target_candidate_v2_pit_b",
        "anchor_t1_accepted_at",
    ]
    historical_raw = pd.read_csv(FROZEN_TRAIN_X_T_PATH, usecols=raw_columns, low_memory=False)
    protected_raw = pd.read_csv(raw_new_path, usecols=raw_columns, low_memory=False)
    protected_raw["feature_year"] = pd.to_numeric(protected_raw["feature_year"], errors="raise").astype(int)
    protected_raw = protected_raw.loc[protected_raw["feature_year"].between(2021, maximum_feature_year)]
    raw = pd.concat([historical_raw, protected_raw], ignore_index=True)

    historical_target = pd.read_csv(FROZEN_TRAIN_TARGET_PATH, usecols=target_columns, low_memory=False)
    protected_target = pd.read_csv(SPENT_TARGET_CORRECTED_PATH, usecols=target_columns, low_memory=False)
    protected_target["feature_year"] = pd.to_numeric(protected_target["feature_year"], errors="raise").astype(int)
    protected_target = protected_target.loc[protected_target["feature_year"].between(2021, 2022)]
    target = pd.concat([historical_target, protected_target], ignore_index=True)
    return raw, target


def load_labeled_sample(maximum_feature_year: int = 2022) -> pd.DataFrame:
    raw, target = _read_modeling_inputs(maximum_feature_year)
    _require(not raw["research_universe_company_year_id"].duplicated().any(), "Duplicate raw identity.")
    _require(not target["research_universe_company_year_id"].duplicated().any(), "Duplicate target identity.")
    target = target.rename(
        columns={
            "feature_year": "target_feature_year",
            "cik10": "target_cik10",
            "membership_status": "target_membership_status",
            "economic_group_id": "target_economic_group_id",
            "target_candidate_v2_pit_b": "target_label",
            "anchor_t1_accepted_at": "target_available_at",
        }
    )
    sample = raw.merge(target, how="left", on="research_universe_company_year_id", validate="one_to_one")
    aligned = (
        pd.to_numeric(sample["feature_year"], errors="raise").astype(int)
        == pd.to_numeric(sample["target_feature_year"], errors="raise").astype(int)
    ) & (sample["economic_group_id"].astype(str) == sample["target_economic_group_id"].astype(str))
    _require(aligned.fillna(False).all(), "Feature/target alignment mismatch.")
    keep = (
        sample["membership_status"].eq("eligible")
        & sample["target_membership_status"].eq("eligible")
        & sample["target_status"].eq("available")
        & sample["x_t_status"].isin(["available_core", "partially_available"])
    )
    sample = sample.loc[keep].copy()
    sample = sample.rename(columns={f"{feature}_value": feature for feature in FEATURES})
    sample["feature_year"] = pd.to_numeric(sample["feature_year"], errors="raise").astype(int)
    sample["target_label"] = pd.to_numeric(sample["target_label"], errors="raise").astype(int)
    sample["cik10"] = sample["cik10"].astype(str).str.zfill(10)
    sample["research_universe_company_year_id"] = sample["research_universe_company_year_id"].astype(str)
    sample["economic_group_id"] = sample["economic_group_id"].astype(str)
    for column in ("prediction_timestamp", "target_available_at"):
        parsed = pd.to_datetime(sample[column], errors="coerce", utc=True, format="mixed")
        _require(not parsed.isna().any(), f"Invalid {column}.")
        sample[column] = parsed
    _require(sample["prediction_timestamp"].lt(sample["target_available_at"]).all(), "Own target was available before prediction.")
    return sample.sort_values(["feature_year", "research_universe_company_year_id"], kind="mergesort").reset_index(drop=True)


def load_blind_holdout_features() -> pd.DataFrame:
    raw, _target = _read_modeling_inputs(2024)
    raw["feature_year"] = pd.to_numeric(raw["feature_year"], errors="raise").astype(int)
    frame = raw.loc[
        raw["feature_year"].isin([2023, 2024])
        & raw["membership_status"].eq("eligible")
        & raw["x_t_status"].isin(["available_core", "partially_available"])
    ].copy()
    frame = frame.rename(columns={f"{feature}_value": feature for feature in FEATURES})
    frame["cik10"] = frame["cik10"].astype(str).str.zfill(10)
    frame["research_universe_company_year_id"] = frame["research_universe_company_year_id"].astype(str)
    frame["economic_group_id"] = frame["economic_group_id"].astype(str)
    frame["prediction_timestamp"] = pd.to_datetime(frame["prediction_timestamp"], errors="coerce", utc=True, format="mixed")
    _require(not frame["prediction_timestamp"].isna().any(), "Invalid holdout prediction timestamp.")
    _require(not frame["research_universe_company_year_id"].duplicated().any(), "Duplicate blind identity.")
    return frame.sort_values(["feature_year", "research_universe_company_year_id"], kind="mergesort").reset_index(drop=True)


def frozen_roster() -> list[dict[str, Any]]:
    contract = _load_yaml(CONTRACT_PATH)
    roster_authority = contract["roster"]["source"]
    _verified_file(ROOT / roster_authority["path"], str(roster_authority["sha256"]))
    payload = _load_json(PRIMARY_ROSTER_PATH)
    representatives = payload.get("family_representatives")
    _require(isinstance(representatives, list) and len(representatives) == 9, "Primary roster must contain nine families.")
    calibrations = {
        (x["identity"]["family"], x["identity"]["configuration_id"], x["identity"]["feature_block"]): x
        for x in payload.get("calibration_and_threshold", [])
    }
    result: list[dict[str, Any]] = []
    for row in representatives:
        key = (row["family"], row["configuration_id"], row["feature_block"])
        _require(key in calibrations, f"Missing calibration for {key}.")
        calibration = dict(calibrations[key])
        for field in ("calibration_artifact", "threshold_artifact"):
            path = CALIBRATION_ROOT / calibration[field]
            _verified_file(path, str(calibration[field.replace("artifact", "sha256")]))
        result.append(
            {
                "family": row["family"],
                "stage": row["stage"],
                "configuration_id": row["configuration_id"],
                "feature_block": row["feature_block"],
                "parameters": row["parameters"],
                "calibration": calibration,
            }
        )
    _require([row["family"] for row in result] == contract["roster"]["family_order"], "Roster family order changed.")
    return result


def _calibration_values(item: Mapping[str, Any]) -> tuple[float, float, float]:
    calibration = item["calibration"]
    calibration_path = CALIBRATION_ROOT / str(calibration["calibration_artifact"])
    threshold_path = CALIBRATION_ROOT / str(calibration["threshold_artifact"])
    _verified_file(calibration_path, str(calibration["calibration_sha256"]))
    _verified_file(threshold_path, str(calibration["threshold_sha256"]))
    calibration_payload = _load_json(calibration_path)
    threshold_payload = _load_json(threshold_path)
    return (
        float.fromhex(str(calibration_payload["coef_float64_hex"])),
        float.fromhex(str(calibration_payload["intercept_float64_hex"])),
        float.fromhex(str(threshold_payload["threshold_float64_hex"])),
    )


def apply_frozen_calibration(raw_scores: Sequence[float], item: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    coefficient, intercept, threshold = _calibration_values(item)
    probabilities = expit(coefficient * np.asarray(raw_scores, dtype=np.float64) + intercept).astype(np.float64)
    _require(np.isfinite(probabilities).all(), "Nonfinite calibrated probability.")
    return probabilities, (probabilities >= threshold).astype(np.int64)


def _prepare_arrays(
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    *,
    item: Mapping[str, Any],
    output_dir: Path,
    year: int,
) -> tuple[np.ndarray, np.ndarray, str, str | None, list[str]]:
    block = str(item["feature_block"])
    if block == BLOCK_AGNOSTIC:
        return (
            np.empty((len(train), 0), dtype=np.float64),
            np.empty((len(evaluation), 0), dtype=np.float64),
            canonical_sha256({"mode": "none_dummy_prior"}),
            None,
            [],
        )
    preprocessor = FinancialPreprocessor.for_blocks(BLOCK_PARTS[block])
    x_train_frame = preprocessor.fit_transform(train)
    x_eval_frame = preprocessor.transform(evaluation)
    expected = [*features_for_blocks(BLOCK_PARTS[block]), *[f"{x}__missing" for x in features_for_blocks(BLOCK_PARTS[block])]]
    _require(list(x_train_frame.columns) == expected and list(x_eval_frame.columns) == expected, "Predictor order changed.")
    pre_payload = {
        "schema_version": 1,
        "fit_scope": f"protected_refit_train_through_{year - 2}",
        "feature_block": block,
        "state": preprocessor.fitted_state(),
    }
    pre_path = output_dir / "preprocessing" / f"prediction_{year}" / f"{block.replace('+', '_')}.json"
    pre_sha = atomic_write_json(pre_path, pre_payload)
    x_train = x_train_frame.to_numpy(dtype=np.float64, copy=True)
    x_eval = x_eval_frame.to_numpy(dtype=np.float64, copy=True)
    pca_sha: str | None = None
    names = list(expected)
    if item["family"] == "qnn":
        qubits = int(item["parameters"]["qubits_pca"])
        _require(qubits in {4, 6}, "Unregistered QNN PCA dimension.")
        pca = PCA(n_components=qubits, svd_solver="full", whiten=False)
        train_components = pca.fit_transform(x_train)
        eval_components = pca.transform(x_eval)
        scaler = StandardScaler(with_mean=True, with_std=True)
        train_components = scaler.fit_transform(train_components)
        eval_components = scaler.transform(eval_components)
        x_train = np.pi / 3.0 * np.clip(train_components, -3.0, 3.0)
        x_eval = np.pi / 3.0 * np.clip(eval_components, -3.0, 3.0)
        pca_payload = {
            "schema_version": 1,
            "fit_scope": f"protected_refit_train_through_{year - 2}",
            "feature_block": block,
            "qubits": qubits,
            "preprocessing_sha256": pre_sha,
            "components_float64_hex": [[float(v).hex() for v in row] for row in pca.components_],
            "explained_variance_float64_hex": [float(v).hex() for v in pca.explained_variance_],
            "pca_mean_float64_hex": [float(v).hex() for v in pca.mean_],
            "component_scaler_mean_float64_hex": [float(v).hex() for v in scaler.mean_],
            "component_scaler_scale_float64_hex": [float(v).hex() for v in scaler.scale_],
            "clipping": [-3.0, 3.0],
            "angle_multiplier_float64_hex": float(np.pi / 3.0).hex(),
        }
        pca_path = output_dir / "pca" / f"prediction_{year}" / f"{block.replace('+', '_')}_q{qubits}.json"
        pca_sha = atomic_write_json(pca_path, pca_payload)
        names = [f"pca_angle_{i + 1}" for i in range(qubits)]
    _require(np.isfinite(x_train).all() and np.isfinite(x_eval).all(), "Nonfinite preprocessed input.")
    return x_train, x_eval, pre_sha, pca_sha, names


def _executor(output_dir: Path) -> tuple[SubprocessFoldExecutor, Mapping[str, Any], str]:
    executor = SubprocessFoldExecutor(
        root=ROOT,
        classical_python=CLASSICAL_PYTHON,
        qnn_python=QNN_PYTHON,
        runner_config_path=RUNNER_CONFIG_PATH,
        contract_path=BASE_EXECUTION_CONTRACT_PATH,
    )
    contract = load_contract(BASE_EXECUTION_CONTRACT_PATH)
    qnn_policy = _load_yaml(ROOT / "configs/model_stage_v1.yaml")["qnn"]["resource_policy"]
    executor.configure_qnn_ledger(
        output_dir / "qnn_resource_ledger.json",
        maximum_attempts=int(qnn_policy["maximum_total_fit_attempts"]),
        maximum_runtime_seconds=float(qnn_policy["maximum_total_cpu_hours"]) * 3600.0,
    )
    ansatz = str(_load_json(QNN_ANSATZ_PATH)["selected_ansatz_id"])
    return executor, contract, ansatz


def _one_model_prediction(
    *,
    executor: SubprocessFoldExecutor,
    base_contract: Mapping[str, Any],
    ansatz: str,
    item: Mapping[str, Any],
    train: pd.DataFrame,
    evaluation: pd.DataFrame,
    year: int,
    output_dir: Path,
    include_labels: bool,
) -> dict[str, Any]:
    x_train, x_eval, preprocessing_sha, pca_sha, predictor_names = _prepare_arrays(
        train, evaluation, item=item, output_dir=output_dir, year=year
    )
    y_train = train["target_label"].to_numpy(dtype=np.int64)
    sample_weight = ProductionExperimentRunner._sample_weight(
        y_train, str(item["parameters"].get("imbalance", "none"))
    )
    family = str(item["family"])
    seeds = (SEEDS[0],) if family in DETERMINISTIC_FAMILIES else SEEDS
    component_scores: list[np.ndarray] = []
    component_results: list[dict[str, Any]] = []
    for seed in seeds:
        role = "qnn_mlp" if family in {"pytorch_mlp", "qnn"} else "classical"
        fold_id = f"protected_refit_prediction_{year}"
        checkpoint_identity: dict[str, Any] = {
            "family": family,
            "configuration_id": item["configuration_id"],
            "parameters_sha256": canonical_sha256(item["parameters"]),
            "feature_block": item["feature_block"],
            "fold_id": fold_id,
            "training_seed": seed,
            "train_membership_sha256": membership_sha256(train["research_universe_company_year_id"].tolist()),
            "validation_membership_sha256": membership_sha256(evaluation["research_universe_company_year_id"].tolist()),
            "preprocessing_sha256": preprocessing_sha,
            "pca_sha256_if_applicable": pca_sha,
            "software_environment_sha256": executor.environment_hashes[role],
            "device_identity": base_contract["qnn_executable_identity"]["device_identity"] if family == "qnn" else "cpu",
        }
        if family == "pytorch_mlp":
            checkpoint_identity["epochs"] = int(item["parameters"]["epochs"])
        task = FoldTask(
            stage=str(item["stage"]),
            family=family,
            feature_block=str(item["feature_block"]),
            configuration_id=str(item["configuration_id"]),
            parameters=dict(item["parameters"]),
            training_seed=seed,
            fold_id=fold_id,
            validation_feature_year=year,
            selected_ansatz_id=ansatz if family == "qnn" else None,
            train_membership_sha256=checkpoint_identity["train_membership_sha256"],
            validation_membership_sha256=checkpoint_identity["validation_membership_sha256"],
            preprocessing_sha256=preprocessing_sha,
            pca_sha256_if_applicable=pca_sha,
            software_environment_role=role,
            checkpoint_identity=checkpoint_identity,
        )
        fit_dir = output_dir / "fits" / f"prediction_{year}" / family / str(item["configuration_id"]) / str(item["feature_block"]).replace("+", "_") / f"seed_{seed}"
        timeout = int(base_contract["execution_failure_state_machine"]["timeouts_cumulative_wall_seconds_per_fold_fit"][family])
        execution = executor.execute(
            task,
            x_train=x_train,
            y_train=y_train,
            x_validation=x_eval,
            sample_weight=sample_weight,
            checkpoint_path=fit_dir / "checkpoint.pt",
            timeout_seconds=timeout,
        )
        _require(execution.status == "COMPLETE" and execution.raw_scores is not None, f"Protected refit failed: {family}/{year}/{seed}: {execution.status}/{execution.failure_code}")
        scores = np.asarray(execution.raw_scores, dtype=np.float64)
        component_scores.append(scores)
        score_path = fit_dir / "raw_scores.npy"
        score_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(score_path, scores, allow_pickle=False)
        component_results.append(
            {
                "seed": seed,
                "task_identity_sha256": task.identity_sha256,
                "raw_scores_sha256": _sha(score_path),
                "attempts": execution.attempts,
                "software_environment_sha256": execution.software_environment_sha256,
            }
        )
    averaged = np.asarray(
        [math.fsum(float(scores[index]) for scores in component_scores) / len(component_scores) for index in range(len(evaluation))],
        dtype=np.float64,
    )
    probabilities, predicted = apply_frozen_calibration(averaged, item)
    rows: list[dict[str, Any]] = []
    for position, (_, observation) in enumerate(evaluation.iterrows()):
        row = {
            "feature_year": year,
            "research_universe_company_year_id": str(observation["research_universe_company_year_id"]),
            "cik10": str(observation["cik10"]).zfill(10),
            "economic_group_id": str(observation["economic_group_id"]),
            "prediction_timestamp": pd.Timestamp(observation["prediction_timestamp"]).isoformat(),
            "raw_score": float(averaged[position]),
            "raw_score_float64_hex": float(averaged[position]).hex(),
            "calibrated_probability": float(probabilities[position]),
            "calibrated_probability_float64_hex": float(probabilities[position]).hex(),
            "predicted_label": int(predicted[position]),
        }
        if include_labels:
            row["target_label"] = int(observation["target_label"])
        rows.append(row)
    identity = {key: item[key] for key in ("family", "configuration_id", "feature_block")}
    slug = "__".join(str(identity[key]) for key in ("family", "configuration_id", "feature_block")).replace("+", "_")
    prediction_path = output_dir / "predictions" / f"prediction_{year}" / f"{slug}.json"
    prediction_sha = atomic_write_json(
        prediction_path,
        {
            "schema_version": 1,
            "identity": identity,
            "year": year,
            "include_labels": include_labels,
            "canonical_key": ["feature_year", "research_universe_company_year_id"],
            "rows": rows,
        },
    )
    return {
        "identity": identity,
        "year": year,
        "status": "COMPLETE",
        "train_rows": len(train),
        "prediction_rows": len(evaluation),
        "train_membership_sha256": membership_sha256(train["research_universe_company_year_id"].tolist()),
        "prediction_membership_sha256": membership_sha256(evaluation["research_universe_company_year_id"].tolist()),
        "predictor_names": predictor_names,
        "preprocessing_sha256": preprocessing_sha,
        "pca_sha256": pca_sha,
        "seed_components": component_results,
        "prediction_path": str(prediction_path.relative_to(ROOT)),
        "prediction_sha256": prediction_sha,
        "calibration_sha256": item["calibration"]["calibration_sha256"],
        "threshold_sha256": item["calibration"]["threshold_sha256"],
    }


def _execution_state(path: Path, action: str, authority: Mapping[str, Any]) -> dict[str, Any]:
    if path.exists():
        existing = _load_json(path)
        _require(existing.get("action") == action and existing.get("authority") == authority, "Execution state identity mismatch.")
        _require(existing.get("status") == "STARTED", "One-shot action already reached a terminal state.")
        return existing
    value = {
        "schema_version": 1,
        "action": action,
        "status": "STARTED",
        "started_at_utc": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
        "authority": dict(authority),
    }
    atomic_write_json(path, value)
    return value


def _finish_execution_state(path: Path, state: Mapping[str, Any], status: str, evidence_sha256: str) -> None:
    value = dict(state)
    value.update(
        {
            "status": status,
            "completed_at_utc": datetime.now(tz=ZoneInfo("UTC")).isoformat(),
            "evidence_sha256": evidence_sha256,
        }
    )
    atomic_write_json(path, value)


def run_predictions(
    *,
    action: str,
    years: Sequence[int],
    labeled_sample: pd.DataFrame,
    evaluations: Mapping[int, pd.DataFrame],
    output_dir: Path,
    include_labels: bool,
    scope_id: str,
    scope_hash: str,
    gate_result_path: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    authority = {
        "contract_sha256": _sha(CONTRACT_PATH),
        "runner_sha256": _sha(Path(__file__)),
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "gate_result_sha256": _sha(gate_result_path),
    }
    state_path = output_dir / "one_shot_execution_state.json"
    state = _execution_state(state_path, action, authority)
    executor, base_contract, ansatz = _executor(output_dir)
    results: list[dict[str, Any]] = []
    for year in years:
        train_max = year - 2
        evaluation = evaluations[year]
        cutoff = evaluation["prediction_timestamp"].min()
        train = labeled_sample.loc[
            labeled_sample["feature_year"].between(2011, train_max)
            & labeled_sample["target_available_at"].le(cutoff)
        ].copy()
        _require(not train.empty and not evaluation.empty, "Empty preregistered refit partition.")
        for item in frozen_roster():
            results.append(
                _one_model_prediction(
                    executor=executor,
                    base_contract=base_contract,
                    ansatz=ansatz,
                    item=item,
                    train=train,
                    evaluation=evaluation,
                    year=year,
                    output_dir=output_dir,
                    include_labels=include_labels,
                )
            )
    evidence = {
        "schema_version": 1,
        "action": action,
        "status": "COMPLETE",
        "authority": authority,
        "years": list(years),
        "roster_size": 9,
        "model_year_results": results,
        "model_fit_performed": True,
        "tuning_performed": False,
        "reselection_performed": False,
        "recalibration_performed": False,
        "rethresholding_performed": False,
        "targets_in_prediction_files": include_labels,
    }
    evidence_path = output_dir / "execution_evidence.json"
    evidence_sha = atomic_write_json(evidence_path, evidence)
    _finish_execution_state(state_path, state, "COMPLETE", evidence_sha)
    evidence["execution_evidence_path"] = str(evidence_path.relative_to(ROOT))
    evidence["execution_evidence_sha256"] = evidence_sha
    return evidence


def _metric_values(labels: np.ndarray, probabilities: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    _require(set(labels.tolist()) <= {0, 1} and len(set(labels.tolist())) == 2, "Metric input is degenerate.")
    return {
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "f1_frozen_threshold": float(f1_score(labels, predicted, zero_division=0)),
        "precision_frozen_threshold": float(precision_score(labels, predicted, zero_division=0)),
        "recall_frozen_threshold": float(recall_score(labels, predicted, zero_division=0)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
    }


def _cluster_bootstrap(
    frame: pd.DataFrame,
    *,
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    groups = sorted(frame["economic_group_id"].astype(str).unique())
    by_group = {group: frame.index[frame["economic_group_id"].astype(str).eq(group)].to_numpy() for group in groups}
    generator = np.random.default_rng(seed)
    collected: dict[str, list[float]] = {name: [] for name in ("pr_auc", "roc_auc", "f1_frozen_threshold")}
    degenerate = 0
    for _ in range(replicates):
        sampled = generator.choice(groups, size=len(groups), replace=True)
        indexes = np.concatenate([by_group[str(group)] for group in sampled])
        labels = frame.loc[indexes, "target_label"].to_numpy(dtype=np.int64)
        if len(np.unique(labels)) != 2:
            degenerate += 1
            continue
        probabilities = frame.loc[indexes, "calibrated_probability"].to_numpy(dtype=np.float64)
        predicted = frame.loc[indexes, "predicted_label"].to_numpy(dtype=np.int64)
        metrics = _metric_values(labels, probabilities, predicted)
        for name in collected:
            collected[name].append(metrics[name])
    _require(replicates - degenerate >= int(replicates * 0.95), "Too many degenerate bootstrap replicates.")
    return {
        "replicates": replicates,
        "valid_replicates": replicates - degenerate,
        "degenerate_replicates": degenerate,
        "percentile_interval": [2.5, 97.5],
        "intervals": {
            name: {
                "lower": float(np.percentile(values, 2.5)),
                "upper": float(np.percentile(values, 97.5)),
            }
            for name, values in collected.items()
        },
    }


def generate_evaluation_report(
    evidence: Mapping[str, Any],
    report_path: Path,
    *,
    period_label: str,
    prior_exposure_disclosure: str,
) -> str:
    contract = _load_yaml(CONTRACT_PATH)
    metrics_rows: list[dict[str, Any]] = []
    for index, item in enumerate(evidence["model_year_results"]):
        prediction_path = ROOT / str(item["prediction_path"])
        _verified_file(prediction_path, str(item["prediction_sha256"]))
        payload = _load_json(prediction_path)
        frame = pd.DataFrame(payload["rows"])
        _require("target_label" in frame, "Evaluation report received sealed predictions.")
        labels = frame["target_label"].to_numpy(dtype=np.int64)
        probabilities = frame["calibrated_probability"].to_numpy(dtype=np.float64)
        predicted = frame["predicted_label"].to_numpy(dtype=np.int64)
        metrics_rows.append(
            {
                "identity": item["identity"],
                "year": int(item["year"]),
                "n": len(frame),
                "positive_n": int(labels.sum()),
                "metrics": _metric_values(labels, probabilities, predicted),
                "cluster_bootstrap": _cluster_bootstrap(
                    frame,
                    replicates=int(contract["evaluation"]["bootstrap_replicates"]),
                    seed=int(contract["evaluation"]["bootstrap_seed"]) + index,
                ),
            }
        )
    report = {
        "schema_version": 1,
        "status": "COMPLETE",
        "period_label": period_label,
        "prior_exposure_disclosure": prior_exposure_disclosure,
        "fully_unseen_claimed": False,
        "selection_or_tuning_performed": False,
        "evaluation_contract_sha256": _sha(CONTRACT_PATH),
        "runner_sha256": _sha(Path(__file__)),
        "execution_evidence_sha256": evidence["execution_evidence_sha256"],
        "metric_rows": metrics_rows,
    }
    return atomic_write_json(report_path, report)


def verify_spent_gate() -> dict[str, Any]:
    scope_id, scope_hash = _reviewed_scope(
        ACCESS_MANIFEST_PATH,
        SPENT_REVIEW_PATH,
        "spent_gate_verifier_scope",
        "SPENT_ACCESS_MANIFEST_REVIEW_PASS",
    )
    gate = _load_yaml(SPENT_GATE_MANIFEST_PATH)
    contract = _load_yaml(CONTRACT_PATH)
    _require(gate["gate"]["id"] == "DATA_ACCESS_GATE_2021_2022_REOPEN_V1", "Gate ID mismatch.")
    _require(gate["authority"]["contract_sha256"] == _sha(CONTRACT_PATH), "Gate contract mismatch.")
    _require(contract["terminal_variant"] == "GATED_FULL_HOLDOUT", "Terminal variant mismatch.")
    _verify_frozen_implementation(contract)
    for item in contract["opaque_pre_gate_files"]:
        _verified_file(ROOT / item["path"], str(item["sha256"]))
    for path in contract["required_source_directories"]:
        _require((ROOT / path).is_dir(), f"Required restored source directory is absent: {path}")
    frozen_roster()
    result = {
        "schema_version": 1,
        "verdict": "DATA_ACCESS_GATE_2021_2022_REOPEN_PASS",
        "gate_manifest_sha256": _sha(SPENT_GATE_MANIFEST_PATH),
        "access_manifest_sha256": _sha(ACCESS_MANIFEST_PATH),
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "protected_values_deserialized": False,
        "protected_row_counts_read": False,
        "opened_scope": "spent_post_gate_execution_scope_only",
    }
    atomic_write_json(SPENT_GATE_RESULT_PATH, result)
    return result


def run_spent() -> dict[str, Any]:
    scope_id, scope_hash = _reviewed_scope(
        ACCESS_MANIFEST_PATH,
        SPENT_REVIEW_PATH,
        "spent_post_gate_execution_scope",
        "SPENT_ACCESS_MANIFEST_REVIEW_PASS",
    )
    _require_gate(
        SPENT_GATE_RESULT_PATH,
        "DATA_ACCESS_GATE_2021_2022_REOPEN_PASS",
        SPENT_GATE_MANIFEST_PATH,
        str(_load_json(SPENT_GATE_RESULT_PATH)["scope_id"]),
        str(_load_json(SPENT_GATE_RESULT_PATH)["scope_sha256"]),
    )
    x_t = build_corrected_x_t(
        maximum_feature_year=2022,
        base_projection=SPENT_BASE_X_T_PATH,
        rebuild_path=SPENT_REBUILT_X_T_PATH,
        corrected_path=SPENT_CORRECTED_X_T_PATH,
    )
    target = build_corrected_spent_target_application()
    sample = load_labeled_sample(2022)
    evaluations = {year: sample.loc[sample["feature_year"].eq(year)].copy() for year in (2021, 2022)}
    evidence = run_predictions(
        action="spent_evaluation_2021_2022",
        years=(2021, 2022),
        labeled_sample=sample,
        evaluations=evaluations,
        output_dir=RUN_ROOT / "spent",
        include_labels=True,
        scope_id=scope_id,
        scope_hash=scope_hash,
        gate_result_path=SPENT_GATE_RESULT_PATH,
    )
    evidence["input_build"] = {"x_t": x_t, "target_application": target}
    evidence["period_label"] = "design-exposed/spent development"
    evidence["access_manifest_sha256"] = _sha(ACCESS_MANIFEST_PATH)
    evidence["scope_id"] = scope_id
    evidence["scope_sha256"] = scope_hash
    evidence_sha = atomic_write_json(SPENT_EXECUTION_EVIDENCE_PATH, evidence)
    evidence["execution_evidence_sha256"] = evidence_sha
    report_sha = generate_evaluation_report(
        evidence,
        SPENT_REPORT_PATH,
        period_label="design-exposed/spent development",
        prior_exposure_disclosure="Target, feature, missingness and sample-design aggregates for 2021-2022 were exposed before this frozen evaluation.",
    )
    evidence["report_path"] = str(SPENT_REPORT_PATH.relative_to(ROOT))
    evidence["report_sha256"] = report_sha
    atomic_write_json(SPENT_EXECUTION_EVIDENCE_PATH, evidence)
    return {"verdict": "SPENT_EXECUTION_COMPLETE", "evidence": str(SPENT_EXECUTION_EVIDENCE_PATH.relative_to(ROOT))}


def verify_spent_freeze() -> dict[str, Any]:
    scope_id, scope_hash = _reviewed_scope(
        ACCESS_MANIFEST_PATH,
        SPENT_REVIEW_PATH,
        "spent_post_execution_freeze_scope",
        "SPENT_ACCESS_MANIFEST_REVIEW_PASS",
    )
    evidence = _load_json(SPENT_EXECUTION_EVIDENCE_PATH)
    contract = _load_yaml(CONTRACT_PATH)
    _verify_frozen_implementation(contract)
    _verified_file(SPENT_REPORT_PATH, str(evidence["report_sha256"]))
    _require(evidence.get("period_label") == "design-exposed/spent development", "Spent label is absent.")
    _require(evidence.get("roster_size") == 9 and len(evidence.get("model_year_results", [])) == 18, "Spent roster is incomplete.")
    for item in evidence["model_year_results"]:
        _verified_file(ROOT / item["prediction_path"], str(item["prediction_sha256"]))
        _require(item["status"] == "COMPLETE", "Incomplete spent model-year result.")
    report = _load_json(SPENT_REPORT_PATH)
    _require(
        report.get("runner_sha256")
        == _sha(Path(__file__)),
        "Spent report runner hash changed.",
    )
    result = {
        "schema_version": 1,
        "verdict": "SPENT_REPORT_FREEZE_PASS",
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "access_manifest_sha256": _sha(ACCESS_MANIFEST_PATH),
        "execution_evidence_sha256": _sha(SPENT_EXECUTION_EVIDENCE_PATH),
        "report_sha256": _sha(SPENT_REPORT_PATH),
        "roster_complete": True,
        "exact_refit_schedule_complete": True,
        "tuning_performed": False,
        "terminal_variant": "GATED_FULL_HOLDOUT",
    }
    atomic_write_json(SPENT_FREEZE_RESULT_PATH, result)
    return result


def verify_second_integrity_gate() -> dict[str, Any]:
    scope_id, scope_hash = _reviewed_scope(
        SECOND_GATE_MANIFEST_PATH,
        SECOND_GATE_REVIEW_PATH,
        "second_integrity_gate_scope",
        "INTEGRITY_ALLOWLIST_REVIEW_PASS",
    )
    manifest = _load_yaml(SECOND_GATE_MANIFEST_PATH)
    freeze = _load_json(SPENT_FREEZE_RESULT_PATH)
    _require(freeze.get("verdict") == "SPENT_REPORT_FREEZE_PASS", "Spent freeze did not pass.")
    _require(manifest["authority"]["spent_freeze_sha256"] == _sha(SPENT_FREEZE_RESULT_PATH), "Spent freeze authority mismatch.")
    evidence = _load_json(SPENT_EXECUTION_EVIDENCE_PATH)
    _require(evidence.get("tuning_performed") is False and evidence.get("reselection_performed") is False, "Spent execution changed methodology.")
    for item in evidence["model_year_results"]:
        _verified_file(ROOT / item["prediction_path"], str(item["prediction_sha256"]))
    result = {
        "schema_version": 1,
        "verdict": "MODEL_EXECUTION_V1_2_INTEGRITY_PASS",
        "gate_manifest_sha256": _sha(SECOND_GATE_MANIFEST_PATH),
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "performance_values_read_by_gate": False,
        "roster_complete": True,
        "code_calibration_threshold_hashes_complete": True,
        "holdout_2023_2024_remained_sealed": True,
    }
    atomic_write_json(SECOND_GATE_RESULT_PATH, result)
    return result


def verify_feature_gate() -> dict[str, Any]:
    scope_id, scope_hash = _reviewed_scope(
        FEATURE_ACCESS_MANIFEST_PATH,
        FEATURE_REVIEW_PATH,
        "feature_gate_verifier_scope",
        "FEATURE_ACCESS_MANIFEST_REVIEW_PASS",
    )
    manifest = _load_yaml(FEATURE_ACCESS_MANIFEST_PATH)
    contract = _load_yaml(CONTRACT_PATH)
    _require(_load_json(SECOND_GATE_RESULT_PATH).get("verdict") == "MODEL_EXECUTION_V1_2_INTEGRITY_PASS", "Second integrity gate did not pass.")
    _require(manifest["authority"]["p1_contract_sha256"] == _sha(CONTRACT_PATH), "P1 contract changed.")
    _verify_frozen_implementation(contract)
    result = {
        "schema_version": 1,
        "verdict": "DATA_ACCESS_GATE_2023_2024_FEATURE_APPLICATION_PASS",
        "gate_manifest_sha256": _sha(FEATURE_ACCESS_MANIFEST_PATH),
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "target_values_opened": False,
        "target_statistics_opened": False,
    }
    atomic_write_json(FEATURE_GATE_RESULT_PATH, result)
    return result


def run_holdout_features() -> dict[str, Any]:
    scope_id, scope_hash = _reviewed_scope(
        FEATURE_ACCESS_MANIFEST_PATH,
        FEATURE_REVIEW_PATH,
        "feature_post_gate_execution_scope",
        "FEATURE_ACCESS_MANIFEST_REVIEW_PASS",
    )
    gate = _load_json(FEATURE_GATE_RESULT_PATH)
    _require(gate.get("verdict") == "DATA_ACCESS_GATE_2023_2024_FEATURE_APPLICATION_PASS", "Feature gate did not pass.")
    x_t = build_corrected_x_t(
        maximum_feature_year=2024,
        base_projection=HOLDOUT_BASE_X_T_PATH,
        rebuild_path=HOLDOUT_REBUILT_X_T_PATH,
        corrected_path=HOLDOUT_CORRECTED_X_T_PATH,
    )
    labeled = load_labeled_sample(2022)
    blind = load_blind_holdout_features()
    evaluations = {year: blind.loc[blind["feature_year"].eq(year)].copy() for year in (2023, 2024)}
    evidence = run_predictions(
        action="blind_holdout_feature_application_2023_2024",
        years=(2023, 2024),
        labeled_sample=labeled,
        evaluations=evaluations,
        output_dir=RUN_ROOT / "holdout_blind",
        include_labels=False,
        scope_id=scope_id,
        scope_hash=scope_hash,
        gate_result_path=FEATURE_GATE_RESULT_PATH,
    )
    evidence.update(
        {
            "corrected_x_t": x_t,
            "scope_id": scope_id,
            "scope_sha256": scope_hash,
            "targets_opened": False,
            "target_statistics_opened": False,
        }
    )
    atomic_write_json(FEATURE_EXECUTION_EVIDENCE_PATH, evidence)
    return {"verdict": "BLIND_FEATURE_APPLICATION_COMPLETE"}


def verify_feature_execution() -> dict[str, Any]:
    scope_id, scope_hash = _reviewed_scope(
        FEATURE_ACCESS_MANIFEST_PATH,
        FEATURE_REVIEW_PATH,
        "feature_post_execution_audit_scope",
        "FEATURE_ACCESS_MANIFEST_REVIEW_PASS",
    )
    evidence = _load_json(FEATURE_EXECUTION_EVIDENCE_PATH)
    _require(evidence.get("targets_opened") is False and evidence.get("targets_in_prediction_files") is False, "Blind execution opened labels.")
    _require(len(evidence.get("model_year_results", [])) == 18, "Blind roster is incomplete.")
    for item in evidence["model_year_results"]:
        path = _verified_file(ROOT / item["prediction_path"], str(item["prediction_sha256"]))
        payload = _load_json(path)
        _require(all("target_label" not in row for row in payload["rows"]), "Prediction file contains a target.")
    result = {
        "schema_version": 1,
        "verdict": "FEATURE_APPLICATION_EXECUTION_PASS",
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "execution_evidence_sha256": _sha(FEATURE_EXECUTION_EVIDENCE_PATH),
        "roster_complete": True,
        "targets_remained_sealed": True,
    }
    atomic_write_json(FEATURE_AUDIT_RESULT_PATH, result)
    return result


def _build_holdout_target() -> dict[str, Any]:
    feature_evidence = _load_json(FEATURE_EXECUTION_EVIDENCE_PATH)
    ciks: set[str] = set()
    for item in feature_evidence["model_year_results"]:
        payload = _load_json(ROOT / item["prediction_path"])
        ciks.update(str(row["cik10"]).zfill(10) for row in payload["rows"])
    universe = pd.read_csv(ROOT / "data/processed/research_universe.csv", dtype=str).fillna("")
    universe["cik10"] = universe["cik10"].astype(str).str.zfill(10)
    companies = universe.loc[universe["cik10"].isin(ciks)].drop_duplicates("cik10").to_dict("records")
    config = target_v1.load_config()
    scope = replace(target_v1.parse_scope(config), feature_year_start=2023, feature_year_end=2024)
    worker = partial(target_v1.process_company_safe, config=config, scope=scope)
    rows: list[dict[str, Any]] = []
    workers = max(1, int(os.environ.get("PROTECTED_TARGET_WORKERS", "6")))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for result in executor.map(worker, companies, chunksize=4):
            rows.extend(result)
    frame = pd.DataFrame(rows).sort_values(["cik10", "feature_year"]).reset_index(drop=True)
    _require(not frame.empty and set(pd.to_numeric(frame["feature_year"]).astype(int)) <= {2023, 2024}, "Holdout target build escaped scope.")
    HOLDOUT_TARGET_BASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(HOLDOUT_TARGET_BASE_PATH, index=False, lineterminator="\n", float_format="%.17g")
    by_key, _by_id = target_patch.load_single_period_corrections(HOLDOUT_BASE_X_T_PATH, HOLDOUT_CORRECTED_X_T_PATH)
    patched = target_patch.patch_target_csv(
        HOLDOUT_TARGET_BASE_PATH,
        HOLDOUT_TARGET_CORRECTED_PATH,
        by_key,
        key_mode="cik_year",
        config=config,
        scope=scope,
        application=False,
    )
    cross_tag_audit = target_patch.audit_target_cross_tag_pairs(
        HOLDOUT_TARGET_CORRECTED_PATH
    )
    _require(
        int(cross_tag_audit["newly_blocked_pairs"]) == 0,
        "Holdout target pair resolver requires a versioned repair.",
    )
    return {
        "base_target_sha256": _sha(HOLDOUT_TARGET_BASE_PATH),
        "corrected_target_sha256": _sha(HOLDOUT_TARGET_CORRECTED_PATH),
        "rows": int(patched["rows"]),
        "target_status_changes_from_resolver_correction": len(patched["target_status_changes"]),
        "target_label_changes_from_resolver_correction": int(patched["target_label_changes"]),
        "selected_cross_tag_pairs_checked": int(
            cross_tag_audit["selected_cross_tag_pairs_checked"]
        ),
        "newly_blocked_cross_tag_pairs": int(
            cross_tag_audit["newly_blocked_pairs"]
        ),
    }


def verify_label_gate() -> dict[str, Any]:
    scope_id, scope_hash = _reviewed_scope(
        LABEL_ACCESS_MANIFEST_PATH,
        LABEL_REVIEW_PATH,
        "label_gate_verifier_scope",
        "LABEL_ACCESS_MANIFEST_REVIEW_PASS",
    )
    manifest = _load_yaml(LABEL_ACCESS_MANIFEST_PATH)
    contract = _load_yaml(CONTRACT_PATH)
    audit = _load_json(FEATURE_AUDIT_RESULT_PATH)
    _require(audit.get("verdict") == "FEATURE_APPLICATION_EXECUTION_PASS", "Feature execution audit did not pass.")
    _require(manifest["authority"]["prediction_evidence_sha256"] == _sha(FEATURE_EXECUTION_EVIDENCE_PATH), "Prediction evidence changed.")
    _verify_frozen_implementation(contract)
    result = {
        "schema_version": 1,
        "verdict": "DATA_ACCESS_GATE_2023_2024_LABEL_REVEAL_PASS",
        "gate_manifest_sha256": _sha(LABEL_ACCESS_MANIFEST_PATH),
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "labels_opened_before_pass": False,
    }
    atomic_write_json(LABEL_GATE_RESULT_PATH, result)
    return result


def _evaluate_holdout_once(*, scope_id: str, scope_hash: str) -> dict[str, Any]:
    target_build = _build_holdout_target()
    target = pd.read_csv(HOLDOUT_TARGET_CORRECTED_PATH, dtype={"cik10": str}, low_memory=False)
    target["cik10"] = target["cik10"].astype(str).str.zfill(10)
    target["feature_year"] = pd.to_numeric(target["feature_year"], errors="raise").astype(int)
    label_col = "target_candidate_v2_pit_b" if "target_candidate_v2_pit_b" in target else "target_candidate_v2"
    available = target.loc[target["target_status"].eq("available"), ["cik10", "feature_year", label_col]].copy()
    available = available.rename(columns={label_col: "target_label"})
    available["target_label"] = pd.to_numeric(available["target_label"], errors="raise").astype(int)
    blind = _load_json(FEATURE_EXECUTION_EVIDENCE_PATH)
    evaluated_results: list[dict[str, Any]] = []
    for item in blind["model_year_results"]:
        payload = _load_json(ROOT / item["prediction_path"])
        frame = pd.DataFrame(payload["rows"])
        frame["cik10"] = frame["cik10"].astype(str).str.zfill(10)
        merged = frame.merge(available, on=["cik10", "feature_year"], how="inner", validate="many_to_one")
        _require(not merged.empty, "No evaluable holdout labels aligned to predictions.")
        out_path = RUN_ROOT / "holdout_evaluation" / "labeled_predictions" / Path(item["prediction_path"]).name
        out_sha = atomic_write_json(out_path, {"schema_version": 1, "identity": item["identity"], "year": item["year"], "rows": merged.to_dict("records")})
        new_item = dict(item)
        new_item.update({"prediction_path": str(out_path.relative_to(ROOT)), "prediction_sha256": out_sha, "prediction_rows": len(merged)})
        evaluated_results.append(new_item)
    evidence = {
        "schema_version": 1,
        "action": "one_shot_holdout_evaluation_2023_2024",
        "status": "COMPLETE",
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "target_build": target_build,
        "model_year_results": evaluated_results,
        "roster_size": 9,
        "tuning_performed": False,
        "reselection_performed": False,
        "recalibration_performed": False,
        "rethresholding_performed": False,
    }
    evidence_sha = atomic_write_json(HOLDOUT_EVALUATION_EVIDENCE_PATH, evidence)
    evidence["execution_evidence_sha256"] = evidence_sha
    report_sha = generate_evaluation_report(
        evidence,
        HOLDOUT_REPORT_PATH,
        period_label="final temporal model-performance holdout 2023-2024",
        prior_exposure_disclosure="Aggregate target statistics for 2023-2024 were exposed before the frozen one-shot evaluation; this period is not described as fully unseen.",
    )
    evidence["report_path"] = str(HOLDOUT_REPORT_PATH.relative_to(ROOT))
    evidence["report_sha256"] = report_sha
    atomic_write_json(HOLDOUT_EVALUATION_EVIDENCE_PATH, evidence)
    return {"verdict": "HOLDOUT_EVALUATION_COMPLETE"}


def evaluate_holdout() -> dict[str, Any]:
    scope_id, scope_hash = _reviewed_scope(
        LABEL_ACCESS_MANIFEST_PATH,
        LABEL_REVIEW_PATH,
        "label_post_gate_evaluation_scope",
        "LABEL_ACCESS_MANIFEST_REVIEW_PASS",
    )
    _require(
        _load_json(LABEL_GATE_RESULT_PATH).get("verdict")
        == "DATA_ACCESS_GATE_2023_2024_LABEL_REVEAL_PASS",
        "Label gate did not pass.",
    )
    authority = {
        "contract_sha256": _sha(CONTRACT_PATH),
        "runner_sha256": _sha(Path(__file__)),
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "label_gate_result_sha256": _sha(LABEL_GATE_RESULT_PATH),
        "blind_prediction_evidence_sha256": _sha(FEATURE_EXECUTION_EVIDENCE_PATH),
    }
    state_path = RUN_ROOT / "holdout_evaluation/one_shot_execution_state.json"
    state = _execution_state(
        state_path,
        "one_shot_holdout_evaluation_2023_2024",
        authority,
    )
    try:
        result = _evaluate_holdout_once(scope_id=scope_id, scope_hash=scope_hash)
    except Exception as error:
        failure_sha = atomic_write_json(
            RUN_ROOT / "holdout_evaluation/one_shot_failure.json",
            {
                "schema_version": 1,
                "action": "one_shot_holdout_evaluation_2023_2024",
                "status": "FAILED",
                "authority": authority,
                "exception_type": type(error).__name__,
                "message": str(error),
                "rerun_allowed": False,
            },
        )
        _finish_execution_state(state_path, state, "FAILED", failure_sha)
        raise
    _finish_execution_state(
        state_path,
        state,
        "COMPLETE",
        _sha(HOLDOUT_EVALUATION_EVIDENCE_PATH),
    )
    return result


def verify_holdout_freeze() -> dict[str, Any]:
    scope_id, scope_hash = _reviewed_scope(
        LABEL_ACCESS_MANIFEST_PATH,
        LABEL_REVIEW_PATH,
        "label_post_evaluation_freeze_scope",
        "LABEL_ACCESS_MANIFEST_REVIEW_PASS",
    )
    evidence = _load_json(HOLDOUT_EVALUATION_EVIDENCE_PATH)
    _verified_file(HOLDOUT_REPORT_PATH, str(evidence["report_sha256"]))
    _require(len(evidence.get("model_year_results", [])) == 18, "Holdout evaluation roster is incomplete.")
    for item in evidence["model_year_results"]:
        _verified_file(ROOT / item["prediction_path"], str(item["prediction_sha256"]))
    report = _load_json(HOLDOUT_REPORT_PATH)
    _require(report.get("fully_unseen_claimed") is False and "exposed" in report.get("prior_exposure_disclosure", ""), "Prior-exposure disclosure is missing.")
    result = {
        "schema_version": 1,
        "verdict": "HOLDOUT_REPORT_FREEZE_PASS",
        "scope_id": scope_id,
        "scope_sha256": scope_hash,
        "evaluation_evidence_sha256": _sha(HOLDOUT_EVALUATION_EVIDENCE_PATH),
        "report_sha256": _sha(HOLDOUT_REPORT_PATH),
        "prediction_label_evaluator_hashes_complete": True,
        "one_shot_execution_complete": True,
        "methodology_changed": False,
        "prior_exposure_disclosed": True,
    }
    atomic_write_json(HOLDOUT_FREEZE_RESULT_PATH, result)
    return result


ACTIONS = {
    "verify-spent-gate": verify_spent_gate,
    "run-spent": run_spent,
    "verify-spent-freeze": verify_spent_freeze,
    "verify-second-integrity-gate": verify_second_integrity_gate,
    "verify-feature-gate": verify_feature_gate,
    "run-holdout-features": run_holdout_features,
    "verify-feature-execution": verify_feature_execution,
    "verify-label-gate": verify_label_gate,
    "evaluate-holdout": evaluate_holdout,
    "verify-holdout-freeze": verify_holdout_freeze,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=tuple(ACTIONS))
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = build_parser().parse_args(argv)
    result = ACTIONS[arguments.action]()
    print(json.dumps({"action": arguments.action, "verdict": result.get("verdict", result.get("status"))}, sort_keys=True))


if __name__ == "__main__":
    main()

"""Apply two frozen research artifacts without changing either component.

The module combines historical research universe v1.1.0 with the frozen
``target_candidate_v2_pit_b`` resolver and artifact v1.0.0. Existing frozen
target rows are reused byte-for-byte at the row/value level; company-years not
covered by the original target artifact are evaluated by the same frozen code
against a compact projection of the same SEC Company Facts/Submissions inputs.

No feature matrix is built and unavailable targets are never mapped to zero.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
import math
import numbers
import os
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml

from src.data import target_candidate_v2_pit as frozen_target


BASE_DIR = Path(__file__).resolve().parents[2]
APPLICATION_CONFIG_PATH = BASE_DIR / "configs/research_universe_target_application.yaml"

UNIVERSE_METADATA_COLUMNS = (
    "research_universe_company_year_id",
    "accession",
    "cik10",
    "feature_year",
    "company_name_historical",
    "historical_sic",
    "historical_sic_description",
    "historical_sic_source",
    "research_sector",
    "membership_status",
    "membership_reason",
    "filed",
    "accepted_at",
    "membership_available_at",
    "registrant_role_resolved",
    "economic_statement_scope_id",
    "economic_group_id",
    "representative_cik",
    "linked_co_registrant_ciks",
    "resolution_evidence",
    "in_old_current_snapshot_universe",
    "recovered_vs_old_universe",
    "later_inactive_delisted_or_unmapped_proxy",
    "development_or_test",
    "xbrl_submission_available",
)

TARGET_METADATA_COLUMNS = {
    "company_name",
    "primary_ticker",
    "research_sector",
    "sic",
    "sic_int",
    "sic_description",
    "sic_major_group",
    "split",
}

TARGET_STATUSES = {
    "available",
    "missing",
    "ambiguous",
    "hard_exclude",
    "not_computable",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return payload


def load_application_config(path: Path = APPLICATION_CONFIG_PATH) -> dict[str, Any]:
    config = load_yaml(path)
    if "application" not in config or "frozen_inputs" not in config:
        raise ValueError(f"Incomplete target-application config: {path}")
    return config


def configured_path(config: dict[str, Any], section: str, key: str) -> Path:
    return BASE_DIR / str(config[section][key])


def manifest_artifact(manifest: dict[str, Any], path: str) -> dict[str, Any]:
    for artifact in manifest.get("non_versioned_reproduction_checks", []):
        if artifact.get("path") == path:
            return artifact
    raise KeyError(f"Artifact {path!r} absent from freeze manifest")


def verify_versioned_components(manifest: dict[str, Any]) -> None:
    for group in manifest.get("versioned_components", {}).values():
        for component in group:
            path = BASE_DIR / str(component["path"])
            if not path.is_file():
                raise FileNotFoundError(path)
            actual = sha256(path)
            if actual != str(component["sha256"]):
                raise RuntimeError(
                    f"Frozen component changed: {path.relative_to(BASE_DIR)}; "
                    f"expected {component['sha256']}, got {actual}"
                )


def verify_frozen_inputs(config: dict[str, Any]) -> dict[str, Any]:
    frozen_inputs = config["frozen_inputs"]
    universe_manifest_path = BASE_DIR / str(frozen_inputs["universe_manifest"])
    target_manifest_path = BASE_DIR / str(frozen_inputs["target_manifest"])
    universe_manifest = load_yaml(universe_manifest_path)
    target_manifest = load_yaml(target_manifest_path)

    universe = universe_manifest["historical_research_universe"]
    target = target_manifest["target"]
    if (universe["id"], str(universe["version"]), universe["status"]) != (
        "research_universe_pit",
        "1.1.0",
        "frozen",
    ):
        raise RuntimeError("Unexpected historical-universe freeze identity")
    if (target["id"], str(target["version"]), target["status"]) != (
        "target_candidate_v2_pit_b",
        "1.0.0",
        "frozen",
    ):
        raise RuntimeError("Unexpected target freeze identity")

    verify_versioned_components(universe_manifest)
    verify_versioned_components(target_manifest)

    universe_relative = str(frozen_inputs["universe_artifact"])
    target_relative = str(frozen_inputs["target_artifact"])
    universe_artifact = manifest_artifact(universe_manifest, universe_relative)
    target_artifact = manifest_artifact(target_manifest, target_relative)
    universe_path = BASE_DIR / universe_relative
    target_path = BASE_DIR / target_relative
    actual_universe_hash = sha256(universe_path)
    actual_target_hash = sha256(target_path)
    if actual_universe_hash != universe_artifact["sha256"]:
        raise RuntimeError("Frozen historical-universe artifact hash changed")
    if actual_target_hash != target_artifact["sha256"]:
        raise RuntimeError("Frozen PIT-B target artifact hash changed")

    return {
        "universe_manifest_path": str(frozen_inputs["universe_manifest"]),
        "universe_manifest_sha256": sha256(universe_manifest_path),
        "universe_artifact_path": universe_relative,
        "universe_artifact_sha256": actual_universe_hash,
        "universe_rows_all_statuses": int(universe_artifact["data_rows"]),
        "universe_eligible_rows": int(universe_manifest["final_membership"]["eligible"]),
        "target_manifest_path": str(frozen_inputs["target_manifest"]),
        "target_manifest_sha256": sha256(target_manifest_path),
        "target_artifact_path": target_relative,
        "target_artifact_sha256": actual_target_hash,
        "target_artifact_rows": int(target_artifact["data_rows"]),
    }


def application_split(feature_year: int) -> str:
    if feature_year <= 2020:
        return "train"
    if feature_year <= 2022:
        return "validation"
    return "test"


def load_eligible_universe(config: dict[str, Any]) -> pd.DataFrame:
    path = configured_path(config, "frozen_inputs", "universe_artifact")
    frame = pd.read_csv(
        path,
        usecols=list(UNIVERSE_METADATA_COLUMNS),
        dtype={"cik10": "string", "representative_cik": "string"},
        low_memory=False,
    )
    eligible = frame.loc[frame["membership_status"].eq("eligible")].copy()
    eligible["cik10"] = eligible["cik10"].str.zfill(10)
    eligible["representative_cik"] = eligible["representative_cik"].str.zfill(10)
    eligible["feature_year"] = pd.to_numeric(
        eligible["feature_year"], errors="raise"
    ).astype(int)
    if len(eligible) != 64_901:
        raise RuntimeError(f"Expected 64,901 eligible rows, got {len(eligible):,}")
    if eligible.duplicated(["cik10", "feature_year"]).any():
        raise RuntimeError("Eligible universe contains duplicate CIK-years")
    return eligible.sort_values(["cik10", "feature_year"]).reset_index(drop=True)


def target_company_records(eligible: pd.DataFrame, ciks: Iterable[str]) -> list[dict[str, Any]]:
    selected = eligible.loc[eligible["cik10"].isin(set(ciks))].copy()
    first = selected.sort_values(["cik10", "feature_year"]).groupby(
        "cik10", as_index=False
    ).first()
    return [
        {
            "cik10": row.cik10,
            "company_name": row.company_name_historical,
            "primary_ticker": "",
            "research_sector": row.research_sector,
            "sic": row.historical_sic,
            "sic_int": row.historical_sic,
            "sic_description": row.historical_sic_description,
            "sic_major_group": (
                int(float(row.historical_sic)) // 100
                if pd.notna(row.historical_sic)
                else ""
            ),
        }
        for row in first.itertuples(index=False)
    ]


def compute_uncovered_target_rows(
    eligible: pd.DataFrame,
    frozen_rows: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    frozen_keys = set(
        frozen_rows[["cik10", "feature_year"]].itertuples(index=False, name=None)
    )
    uncovered = eligible.loc[
        ~eligible[["cik10", "feature_year"]].apply(tuple, axis=1).isin(frozen_keys)
    ]
    ciks = sorted(uncovered["cik10"].unique())
    if not ciks:
        return pd.DataFrame(columns=frozen_rows.columns)

    target_config = frozen_target.load_config(
        configured_path(config, "frozen_inputs", "target_config")
    )
    base_scope = frozen_target.parse_scope(target_config)
    scope = replace(
        base_scope,
        feature_year_start=int(config["application"]["feature_year_start"]),
        feature_year_end=int(config["application"]["feature_year_end"]),
    )

    frozen_target.COMPANYFACTS_DIR = configured_path(
        config, "application_cache", "companyfacts"
    )
    frozen_target.SUBMISSIONS_DIR = configured_path(
        config, "application_cache", "submissions"
    )
    frozen_target.REVENUE_STATEMENT_EVIDENCE_DIR = configured_path(
        config, "application_cache", "revenue_statement_evidence"
    )

    companies = target_company_records(eligible, ciks)
    workers = max(
        1,
        min(
            int(os.environ.get("UNIVERSE_TARGET_WORKERS", "4")),
            os.cpu_count() or 1,
        ),
    )
    all_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = executor.map(
            lambda company: frozen_target.process_company_safe(
                company, target_config, scope
            ),
            companies,
            chunksize=4,
        )
        for index, result in enumerate(results, start=1):
            all_rows.extend(result)
            if index % 100 == 0 or index == len(companies):
                print(
                    f"Frozen PIT-B application progress: {index}/{len(companies)} CIKs",
                    flush=True,
                )

    computed = pd.DataFrame(all_rows)
    if computed.empty:
        return pd.DataFrame(columns=frozen_rows.columns)
    if "fatal_error" in computed.columns and computed["fatal_error"].notna().any():
        fatal = computed.loc[
            computed["fatal_error"].notna(), ["cik10", "company_name", "fatal_error"]
        ]
        raise RuntimeError(f"Frozen target resolver failures:\n{fatal.to_string(index=False)}")
    computed["cik10"] = computed["cik10"].astype("string").str.zfill(10)
    computed["feature_year"] = pd.to_numeric(
        computed["feature_year"], errors="raise"
    ).astype(int)
    uncovered_keys = set(
        uncovered[["cik10", "feature_year"]].itertuples(index=False, name=None)
    )
    mask = computed[["cik10", "feature_year"]].apply(tuple, axis=1).isin(
        uncovered_keys
    )
    return computed.loc[mask].copy()


def authoritative_universe_metadata(eligible: pd.DataFrame) -> pd.DataFrame:
    result = eligible.copy()
    result = result.rename(
        columns={
            "accession": "universe_anchor_accession",
            "filed": "universe_anchor_filed",
            "accepted_at": "universe_anchor_accepted_at",
        }
    )
    result["company_name"] = result["company_name_historical"]
    result["primary_ticker"] = ""
    result["sic"] = result["historical_sic"]
    result["sic_int"] = result["historical_sic"]
    result["sic_description"] = result["historical_sic_description"]
    result["sic_major_group"] = (
        pd.to_numeric(result["historical_sic"], errors="coerce") // 100
    ).astype("Int64")
    result["split"] = result["feature_year"].map(application_split)
    return result


def assemble_application_artifact(
    eligible: pd.DataFrame,
    frozen_rows: pd.DataFrame,
    computed_rows: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    frozen_rows = frozen_rows.copy()
    frozen_rows["cik10"] = frozen_rows["cik10"].astype("string").str.zfill(10)
    frozen_rows["feature_year"] = pd.to_numeric(
        frozen_rows["feature_year"], errors="raise"
    ).astype(int)
    eligible_keys = set(
        eligible[["cik10", "feature_year"]].itertuples(index=False, name=None)
    )
    cached = frozen_rows.loc[
        frozen_rows[["cik10", "feature_year"]].apply(tuple, axis=1).isin(
            eligible_keys
        )
    ].copy()
    cached["target_application_source"] = "frozen_target_artifact_v1.0.0"
    computed_rows = computed_rows.copy()
    computed_rows["target_application_source"] = "frozen_resolver_v1.0.0"

    target_rows = pd.concat([cached, computed_rows], ignore_index=True, sort=False)
    if target_rows.duplicated(["cik10", "feature_year"]).any():
        raise RuntimeError("Multiple target rows for one eligible CIK-year")

    target_columns = [
        column
        for column in target_rows.columns
        if column not in TARGET_METADATA_COLUMNS
        and column not in {"cik10", "feature_year"}
    ]
    result = authoritative_universe_metadata(eligible).merge(
        target_rows[["cik10", "feature_year", *target_columns]],
        on=["cik10", "feature_year"],
        how="left",
        validate="one_to_one",
    )
    # The target artifact has hundreds of provenance columns. Defragment once
    # before adding application-level fields to avoid repeated block inserts.
    result = result.copy()

    has_target_row = result["target_application_source"].notna()
    anchor_match = (
        result["anchor_t_accn"].fillna("").astype(str)
        == result["universe_anchor_accession"].fillna("").astype(str)
    )
    result["universe_anchor_matches_target_anchor_t"] = has_target_row & anchor_match
    result["target_application_reason"] = "applied"

    application_companyfacts = configured_path(
        config, "application_cache", "companyfacts"
    )
    missing_row = ~has_target_row
    missing_companyfacts = result["cik10"].map(
        lambda cik: not (application_companyfacts / f"CIK{cik}.json").is_file()
    )
    result.loc[missing_row & missing_companyfacts, "target_application_reason"] = (
        "companyfacts_unavailable"
    )
    result.loc[missing_row & ~missing_companyfacts, "target_application_reason"] = (
        "anchor_t_not_reconstructable_by_frozen_target_policy"
    )
    result.loc[has_target_row & ~anchor_match, "target_application_reason"] = (
        "universe_anchor_target_anchor_mismatch"
    )

    not_computable = missing_row | (has_target_row & ~anchor_match)
    result.loc[not_computable, "target_status"] = "not_computable"
    result.loc[missing_row, "target_application_source"] = "not_computable"
    for column in (
        *frozen_target.TARGET_SIGNALS,
        "deterioration_score_1y",
        "target_candidate_v2",
    ):
        result.loc[not_computable, column] = pd.NA
    result["target_candidate_v2_pit_b"] = result["target_candidate_v2"]
    result["target_available"] = result["target_status"].eq("available")
    result["target_application_id"] = config["application"]["id"]
    result["research_universe_version"] = "1.1.0"
    result["target_definition_version"] = "1.0.0"
    return result.sort_values(["cik10", "feature_year"]).reset_index(drop=True)


def validate_application_artifact(frame: pd.DataFrame) -> None:
    if len(frame) != 64_901:
        raise RuntimeError(f"Expected 64,901 application rows, got {len(frame):,}")
    if frame.duplicated(["cik10", "feature_year"]).any():
        raise RuntimeError("Application artifact contains duplicate CIK-years")
    if not frame["membership_status"].eq("eligible").all():
        raise RuntimeError("Non-eligible observation entered target application")
    actual_statuses = set(frame["target_status"].dropna().astype(str))
    if not actual_statuses.issubset(TARGET_STATUSES):
        raise RuntimeError(f"Unexpected target statuses: {sorted(actual_statuses)}")
    if frame["target_status"].isna().any():
        raise RuntimeError("Target status is missing")

    available = frame["target_status"].eq("available")
    target = pd.to_numeric(frame["target_candidate_v2_pit_b"], errors="coerce")
    score = pd.to_numeric(frame["deterioration_score_1y"], errors="coerce")
    if not target.loc[available].isin([0, 1]).all():
        raise RuntimeError("Available target is not binary")
    if score.loc[available].isna().any():
        raise RuntimeError("Available target lacks deterioration score")
    if frame.loc[available, list(frozen_target.TARGET_SIGNALS)].isna().any().any():
        raise RuntimeError("Available target lacks at least one D1-D5 signal")
    if target.loc[~available].notna().any():
        raise RuntimeError("Unavailable target was assigned a class")
    if not frame.loc[available, "universe_anchor_matches_target_anchor_t"].all():
        raise RuntimeError("Available target does not match the universe anchor")
    representative = frame["representative_cik"].astype("string").str.zfill(10)
    cik10 = frame["cik10"].astype("string").str.zfill(10)
    if not representative.eq(cik10).all():
        raise RuntimeError("Eligible universe row is not the statement-scope representative")


def atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def build_application_artifact(final: bool = False) -> dict[str, Any]:
    config = load_application_config()
    frozen_hashes_before = verify_frozen_inputs(config)
    eligible = load_eligible_universe(config)
    frozen_rows = pd.read_csv(
        configured_path(config, "frozen_inputs", "target_artifact"),
        dtype={"cik10": "string"},
        low_memory=False,
    )
    computed = compute_uncovered_target_rows(eligible, frozen_rows, config)
    result = assemble_application_artifact(eligible, frozen_rows, computed, config)
    validate_application_artifact(result)

    output_key = "final_artifact" if final else "working_artifact"
    output_path = configured_path(config, "outputs", output_key)
    atomic_csv(result, output_path)
    frozen_hashes_after = verify_frozen_inputs(config)
    if frozen_hashes_before != frozen_hashes_after:
        raise RuntimeError("A frozen input changed during target application")

    return {
        "application_id": config["application"]["id"],
        "output": str(output_path.relative_to(BASE_DIR)),
        "output_sha256": sha256(output_path),
        "output_bytes": output_path.stat().st_size,
        "rows": int(len(result)),
        "status_counts": {
            str(status): int(count)
            for status, count in result["target_status"].value_counts().items()
        },
        "frozen_inputs": frozen_hashes_after,
    }


def write_json_atomic(payload: dict[str, Any], path: Path) -> None:
    def json_safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_safe(item) for item in value]
        if isinstance(value, numbers.Real) and not isinstance(value, (bool, int)):
            return float(value) if math.isfinite(float(value)) else None
        return value

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(json_safe(payload), indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(path)

"""Build the filing-first historical point-in-time research universe.

The output contains one earliest original 10-K anchor per CIK and fiscal year.
It retains eligible, excluded, and ambiguous rows so membership is auditable.
Universe membership is deliberately independent of both feature availability
and frozen PIT-B target availability.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import yaml

from historical_research_universe import (
    add_comparison_statuses,
    build_historical_anchors,
    load_policy,
    load_official_sic_description_map,
    load_sic_description_map,
    parse_master_index,
    parse_scope,
    parse_submission_header_registrants,
    read_fsds_sub,
    utc_now_iso,
)
from registrant_role_resolution import apply_registrant_role_resolution


BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw" / "sec_historical_universe"
INDEX_DIR = RAW_DIR / "full_index"
SUB_DIR = RAW_DIR / "fsds_sub"
HEADER_DIR = RAW_DIR / "filing_headers"
SOURCE_MANIFEST_PATH = BASE_DIR / "data" / "reports" / "research_universe_pit_sources.json"
POLICY_PATH = BASE_DIR / "configs" / "research_universe_pit.yaml"

OLD_UNIVERSE_PATH = BASE_DIR / "data" / "processed" / "research_universe.csv"
CURRENT_TICKER_PATH = BASE_DIR / "data" / "interim" / "sec_ticker_cik_map.csv"
SIC_DESCRIPTION_PATH = BASE_DIR / "data" / "interim" / "sec_company_classified.csv"
OFFICIAL_SIC_DESCRIPTION_PATH = RAW_DIR / "sec_sic_code_list.html"
FROZEN_TARGET_PATH = BASE_DIR / "data" / "interim" / "target_candidate_v2_pit_b.csv"
FROZEN_TARGET_MANIFEST_PATH = (
    BASE_DIR / "configs" / "target_candidate_v2_pit_b_freeze_manifest.yaml"
)

CANDIDATES_PATH = BASE_DIR / "data" / "interim" / "research_universe_pit_candidates.csv"
UNRESOLVED_PATH = BASE_DIR / "data" / "interim" / "research_universe_pit_unresolved.csv"
OUTPUT_PATH = BASE_DIR / "data" / "processed" / "research_universe_pit.csv"
BUILD_MANIFEST_PATH = BASE_DIR / "data" / "reports" / "research_universe_pit_build.json"
REGISTRANT_RESOLUTION_DETAIL_PATH = (
    BASE_DIR
    / "data"
    / "reports"
    / "research_universe_pit_registrant_role_detail.csv"
)
REGISTRANT_RESOLUTION_AUDIT_PATH = (
    BASE_DIR
    / "data"
    / "reports"
    / "research_universe_pit_registrant_role_audit.json"
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_to_csv(frame: pd.DataFrame, path: Path) -> None:
    """Write a CSV atomically so an interrupted build cannot truncate canonical data."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def verify_frozen_target_artifact() -> str:
    manifest = yaml.safe_load(FROZEN_TARGET_MANIFEST_PATH.read_text(encoding="utf-8"))
    checks = manifest["non_versioned_reproduction_checks"]
    expected = next(
        item["sha256"]
        for item in checks
        if item["path"] == "data/interim/target_candidate_v2_pit_b.csv"
    )
    actual = sha256_path(FROZEN_TARGET_PATH)
    if actual != expected:
        raise ValueError(
            "Frozen PIT-B target artifact hash differs from freeze manifest; "
            "historical-universe build stopped without modifying it"
        )
    return actual


def verify_registrant_resolution_artifact() -> str:
    audit = json.loads(
        REGISTRANT_RESOLUTION_AUDIT_PATH.read_text(encoding="utf-8")
    )
    relative = str(REGISTRANT_RESOLUTION_DETAIL_PATH.relative_to(BASE_DIR))
    expected = audit["artifacts"][relative]["sha256"]
    actual = sha256_path(REGISTRANT_RESOLUTION_DETAIL_PATH)
    if actual != expected:
        raise ValueError(
            "Registrant-resolution detail differs from its audit manifest; "
            "historical-universe build stopped"
        )
    expected_counts = {
        "confirmed_shared_statement_duplicate_observations": 132,
        "verified_nonoperating_coissuer_observations": 28,
        "ambiguous_observations": 6,
    }
    for field, expected_count in expected_counts.items():
        if int(audit[field]) != expected_count:
            raise ValueError(
                f"Unexpected registrant audit count for {field}: {audit[field]}"
            )
    return actual


def read_sources() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    policy = load_policy()
    scope = parse_scope(policy)
    master_frames: list[pd.DataFrame] = []
    sub_frames: list[pd.DataFrame] = []
    for year in range(scope.filing_index_year_start, scope.filing_index_year_end + 1):
        for quarter in range(1, 5):
            label = f"{year}q{quarter}"
            index_path = INDEX_DIR / f"{label}_master.idx"
            sub_path = SUB_DIR / f"{label}_sub.txt"
            if not index_path.exists() or not sub_path.exists():
                raise FileNotFoundError(
                    f"Missing historical SEC source for {label}; run "
                    "20_download_historical_universe_sources.py first"
                )
            master_frames.append(
                parse_master_index(
                    index_path.read_text(encoding="latin-1"),
                    index_year=year,
                    index_quarter=quarter,
                    qualifying_forms=scope.qualifying_forms,
                )
            )
            sub_frames.append(
                read_fsds_sub(sub_path, source_year=year, source_quarter=quarter)
            )
    master = pd.concat(master_frames, ignore_index=True)
    sub = pd.concat(sub_frames, ignore_index=True)

    header_rows: list[dict[str, str]] = []
    complete_header_accessions: set[str] = set()
    for path in sorted(HEADER_DIR.glob("*.txt")):
        text = path.read_text(encoding="latin-1")
        if "</SEC-HEADER>" not in text.upper():
            continue
        complete_header_accessions.add(path.stem)
        for parsed in parse_submission_header_registrants(text):
            parsed["accession"] = parsed.get("accession_header", "") or path.stem
            parsed["submission_header_path"] = str(path.relative_to(BASE_DIR))
            header_rows.append(parsed)
    headers = pd.DataFrame(header_rows)
    if not headers.empty:
        headers = headers.sort_values("submission_header_path").drop_duplicates(
            ["accession", "cik10_header"], keep="last"
        )
        expected_pairs = set(
            master.loc[
                master["accession"].isin(complete_header_accessions),
                ["accession", "cik10_master"],
            ].itertuples(index=False, name=None)
        )
        parsed_pairs = set(
            headers[["accession", "cik10_header"]].itertuples(
                index=False, name=None
            )
        )
        if expected_pairs != parsed_pairs:
            missing = sorted(expected_pairs - parsed_pairs)[:10]
            extra = sorted(parsed_pairs - expected_pairs)[:10]
            raise ValueError(
                "Submission-header registrants do not match master index; "
                f"missing sample={missing}, extra sample={extra}"
            )
    return master, sub, headers


def add_activity_proxies(universe: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    result = universe.copy()
    last_feature_year = candidates.groupby("cik10")["feature_year"].max()
    result["last_observed_qualifying_10k_feature_year"] = result["cik10"].map(
        last_feature_year
    )
    result["later_qualifying_10k_observed"] = (
        result["last_observed_qualifying_10k_feature_year"] > result["feature_year"]
    )
    result["no_later_10k_through_index_end"] = (
        result["last_observed_qualifying_10k_feature_year"]
        .eq(result["feature_year"])
    )
    result["later_inactive_delisted_or_unmapped_proxy"] = (
        result["membership_status"].eq("eligible")
        & ~result["in_current_ticker_snapshot"]
        & result["no_later_10k_through_index_end"]
    )
    return result


def validate_output(universe: pd.DataFrame) -> None:
    if universe.duplicated(["cik10", "feature_year"]).any():
        raise ValueError("Historical universe contains duplicate CIK-year anchors")
    if not universe["form"].eq("10-K").all():
        raise ValueError("Non-original 10-K entered the historical universe")
    if not universe["x_t_status"].eq("not_built").all():
        raise ValueError("Feature status changed during universe construction")
    statuses = set(universe["membership_status"].unique())
    if not statuses.issubset({"eligible", "excluded", "ambiguous"}):
        raise ValueError(f"Unexpected membership statuses: {statuses}")
    if (
        universe["membership_status"].eq("eligible")
        & universe["historical_sic"].isna()
    ).any():
        raise ValueError("Eligible observation lacks historical SIC")
    allowed_roles = {
        "single_filer_xbrl_registrant",
        "single_filer_non_xbrl_registrant",
        "joint_primary_registrant",
        "joint_co_registrant",
    }
    actual_roles = set(universe["registrant_role"].unique())
    if not actual_roles.issubset(allowed_roles):
        raise ValueError(f"Unexpected resolved registrant roles: {actual_roles}")
    eligible = universe[universe["membership_status"].eq("eligible")]
    if eligible.duplicated(["feature_year", "economic_statement_scope_id"]).any():
        raise ValueError("Duplicate eligible economic statement scope-year")
    if eligible["economic_statement_scope_id"].fillna("").eq("").any():
        raise ValueError("Eligible row lacks economic statement scope")
    if not eligible["cik10"].eq(eligible["representative_cik"]).all():
        raise ValueError("Eligible row is not its scope representative")


def main() -> None:
    policy = load_policy()
    scope = parse_scope(policy)
    frozen_target_hash = verify_frozen_target_artifact()
    registrant_resolution_hash = verify_registrant_resolution_artifact()
    master, sub, headers = read_sources()
    sic_descriptions = load_sic_description_map(SIC_DESCRIPTION_PATH)
    sic_descriptions.update(
        load_official_sic_description_map(OFFICIAL_SIC_DESCRIPTION_PATH)
    )
    anchors, unresolved = build_historical_anchors(
        master, sub, headers, sic_descriptions, policy
    )
    membership_before_entity_resolution = (
        anchors["membership_status"].value_counts().to_dict()
    )
    resolution_detail = pd.read_csv(
        REGISTRANT_RESOLUTION_DETAIL_PATH,
        dtype={"cik10": str},
        low_memory=False,
    )
    filing_registrants = master[["accession", "cik10_master"]].rename(
        columns={"cik10_master": "cik10"}
    )
    anchors, entity_resolution = apply_registrant_role_resolution(
        anchors,
        resolution_detail,
        filing_registrants,
    )
    membership_after_entity_resolution = (
        anchors["membership_status"].value_counts().to_dict()
    )
    candidates = add_comparison_statuses(
        anchors,
        OLD_UNIVERSE_PATH,
        CURRENT_TICKER_PATH,
        FROZEN_TARGET_PATH,
    )
    candidates = add_activity_proxies(candidates, anchors)
    candidates["universe_policy_id"] = policy["historical_universe"]["id"]
    candidates["universe_policy_version"] = policy["historical_universe"]["version"]
    candidates["development_or_test"] = candidates["feature_year"].map(
        lambda year: (
            "development_train_validation"
            if year <= scope.development_feature_year_end
            else "mechanical_test_year_application"
        )
    )
    candidates = candidates.sort_values(
        ["feature_year", "membership_status", "research_sector", "historical_sic", "cik10"]
    ).reset_index(drop=True)
    validate_output(candidates)

    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUILD_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    atomic_to_csv(candidates, CANDIDATES_PATH)
    atomic_to_csv(unresolved, UNRESOLVED_PATH)
    atomic_to_csv(candidates, OUTPUT_PATH)

    frozen_target_hash_after = verify_frozen_target_artifact()
    if frozen_target_hash_after != frozen_target_hash:
        raise ValueError("Frozen target changed during historical-universe build")

    manifest = {
        "created_at": utc_now_iso(),
        "policy_id": policy["historical_universe"]["id"],
        "policy_version": policy["historical_universe"]["version"],
        "policy_sha256": sha256_path(POLICY_PATH),
        "source_manifest_sha256": sha256_path(SOURCE_MANIFEST_PATH),
        "registrant_resolution_detail_sha256": registrant_resolution_hash,
        "canonical_output_includes": ["eligible", "excluded", "ambiguous"],
        "consumer_rule": "use only membership_status == eligible",
        "feature_status": "not_built",
        "target_definition": "target_candidate_v2_pit_b_v1.0.0_frozen_unchanged",
        "target_artifact_sha256_verified": frozen_target_hash,
        "target_artifact_sha256_verified_after_build": frozen_target_hash_after,
        "membership_before_entity_resolution": membership_before_entity_resolution,
        "membership_after_entity_resolution": membership_after_entity_resolution,
        "entity_resolution": entity_resolution,
        "master_rows": int(len(master)),
        "fsds_rows": int(len(sub)),
        "header_fallback_rows": int(len(headers)),
        "company_year_anchors": int(len(candidates)),
        "unique_ciks": int(candidates["cik10"].nunique()),
        "eligible_company_years": int(candidates["membership_status"].eq("eligible").sum()),
        "eligible_unique_ciks": int(
            candidates.loc[candidates["membership_status"].eq("eligible"), "cik10"].nunique()
        ),
        "ambiguous_company_years": int(candidates["membership_status"].eq("ambiguous").sum()),
        "excluded_company_years": int(candidates["membership_status"].eq("excluded").sum()),
        "unresolved_filing_rows": int(len(unresolved)),
        "outputs": {
            "canonical": {
                "path": str(OUTPUT_PATH.relative_to(BASE_DIR)),
                "bytes": OUTPUT_PATH.stat().st_size,
                "sha256": sha256_path(OUTPUT_PATH),
            },
            "candidates": {
                "path": str(CANDIDATES_PATH.relative_to(BASE_DIR)),
                "bytes": CANDIDATES_PATH.stat().st_size,
                "sha256": sha256_path(CANDIDATES_PATH),
            },
            "unresolved": {
                "path": str(UNRESOLVED_PATH.relative_to(BASE_DIR)),
                "bytes": UNRESOLVED_PATH.stat().st_size,
                "sha256": sha256_path(UNRESOLVED_PATH),
            },
        },
    }
    atomic_write_text(BUILD_MANIFEST_PATH, json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

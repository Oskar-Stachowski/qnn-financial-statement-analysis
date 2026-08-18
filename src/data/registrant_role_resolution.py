"""Apply audited registrant-role and economic-entity decisions to the PIT universe.

The resolver changes research-universe membership only through accession-level
decisions established by the registrant-role freeze-gate audit.  It never reads
target values or model features.  Rows removed from the eligible population are
retained in the canonical artifact as excluded/ambiguous provenance records.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


EXPECTED_AUDIT_ACTION_COUNTS = {
    "retain_one_economic_entity": 4368,
    "exclude_duplicate_registrant_row": 132,
    "exclude_nonoperating_issuer": 28,
    "mark_ambiguous": 6,
}


def resolved_registrant_role(row: pd.Series) -> str:
    """Split the historical combined source role without changing membership."""

    joint = bool(row["joint_filing_flag"])
    primary = str(row["registrant_role_source"]) == "primary_xbrl_registrant"
    if joint and primary:
        return "joint_primary_registrant"
    if joint:
        return "joint_co_registrant"
    if primary:
        return "single_filer_xbrl_registrant"
    return "single_filer_non_xbrl_registrant"


def connected_economic_group_map(
    filing_registrants: pd.DataFrame,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return stable CIK components and accession-level co-registrant lists."""

    required = {"accession", "cik10"}
    missing = required - set(filing_registrants.columns)
    if missing:
        raise ValueError(f"Missing filing-registrant columns: {sorted(missing)}")
    pairs = filing_registrants[list(required)].dropna().drop_duplicates().copy()
    pairs["accession"] = pairs["accession"].astype(str)
    pairs["cik10"] = pairs["cik10"].astype(str).str.zfill(10)
    parent = {cik: cik for cik in pairs["cik10"].unique()}

    def find(cik: str) -> str:
        while parent[cik] != cik:
            parent[cik] = parent[parent[cik]]
            cik = parent[cik]
        return cik

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root == right_root:
            return
        smaller, larger = sorted((left_root, right_root))
        parent[larger] = smaller

    accession_members: dict[str, str] = {}
    for accession, rows in pairs.groupby("accession", sort=True):
        ciks = sorted(rows["cik10"].unique())
        accession_members[str(accession)] = ";".join(ciks)
        if len(ciks) > 1:
            for cik in ciks[1:]:
                union(ciks[0], cik)

    group_map = {cik: "economic_group_" + find(cik) for cik in parent}
    return group_map, accession_members


def _validated_resolution_detail(
    detail: pd.DataFrame,
    expected_action_counts: Mapping[str, int] = EXPECTED_AUDIT_ACTION_COUNTS,
) -> pd.DataFrame:
    required = {
        "accession",
        "feature_year",
        "cik10",
        "registrant_role_resolved",
        "scope_status",
        "scope_reason",
        "statement_entity_ciks",
        "economic_entity_status",
        "recommended_membership_action",
        "economic_entity_reason",
        "economic_statement_scope_id",
        "manual_evidence",
    }
    missing = required - set(detail.columns)
    if missing:
        raise ValueError(f"Registrant-resolution detail lacks: {sorted(missing)}")
    result = detail.copy()
    result["cik10"] = result["cik10"].astype(str).str.zfill(10)
    result["feature_year"] = pd.to_numeric(
        result["feature_year"], errors="raise"
    ).astype(int)
    keys = ["accession", "feature_year", "cik10"]
    if result.duplicated(keys).any():
        raise ValueError("Registrant-resolution detail has duplicate accession-year-CIK")
    counts = result["recommended_membership_action"].value_counts().to_dict()
    if counts != dict(expected_action_counts):
        raise ValueError(
            "Registrant-resolution action counts differ from the approved audit: "
            f"expected={dict(expected_action_counts)}, actual={counts}"
        )
    return result


def _ambiguous_reason(row: pd.Series) -> str:
    reason = str(row.get("economic_entity_reason", ""))
    if reason == "statement_entity_is_not_an_eligible_company_year":
        return "statement_scope_owner_not_eligible_under_historical_policy"
    if reason == "statements_belong_to_nonregistrant_parent":
        return "statement_scope_owner_is_nonregistrant_parent"
    return "registrant_statement_scope_ambiguous"


def apply_registrant_role_resolution(
    universe: pd.DataFrame,
    resolution_detail: pd.DataFrame,
    filing_registrants: pd.DataFrame,
    *,
    expected_action_counts: Mapping[str, int] = EXPECTED_AUDIT_ACTION_COUNTS,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply the audited resolver and return the canonical rows plus diagnostics."""

    result = universe.copy()
    result["cik10"] = result["cik10"].astype(str).str.zfill(10)
    result["membership_status_pre_entity_resolution"] = result[
        "membership_status"
    ]
    result["membership_reason_pre_entity_resolution"] = result[
        "membership_reason"
    ].fillna("")
    result = result.rename(columns={"registrant_role": "registrant_role_source"})
    result["registrant_role_resolved"] = result.apply(
        resolved_registrant_role, axis=1
    )
    result["registrant_role"] = result["registrant_role_resolved"]

    group_map, accession_members = connected_economic_group_map(filing_registrants)
    result["joint_accession_registrant_ciks"] = result["accession"].map(
        accession_members
    ).fillna(result["cik10"])
    result["linked_co_registrant_ciks"] = result.apply(
        lambda row: ";".join(
            cik
            for cik in str(row["joint_accession_registrant_ciks"]).split(";")
            if cik and cik != row["cik10"]
        ),
        axis=1,
    )
    result["economic_group_id"] = result["cik10"].map(group_map)
    result["economic_group_id"] = result["economic_group_id"].fillna(
        "economic_group_" + result["cik10"]
    )

    detail = _validated_resolution_detail(
        resolution_detail, expected_action_counts=expected_action_counts
    )
    keys = ["accession", "feature_year", "cik10"]
    audited_keys = detail[keys].merge(
        result[keys + ["membership_status_pre_entity_resolution"]],
        on=keys,
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if not audited_keys["_merge"].eq("both").all():
        raise ValueError("Audited registrant rows do not all match rebuilt anchors")
    if not audited_keys["membership_status_pre_entity_resolution"].eq(
        "eligible"
    ).all():
        raise ValueError("Registrant audit contains a row not eligible before resolution")

    rename = {
        "registrant_role_resolved": "audited_registrant_role_resolved",
        "scope_status": "registrant_scope_status",
        "scope_reason": "registrant_scope_reason",
        "statement_entity_ciks": "statement_entity_ciks",
        "economic_entity_status": "economic_entity_status",
        "recommended_membership_action": "registrant_resolution_action",
        "economic_entity_reason": "economic_entity_reason",
        "economic_statement_scope_id": "economic_statement_scope_id",
        "manual_evidence": "manual_resolution_evidence",
    }
    selected = detail[keys + list(rename)].rename(columns=rename)
    result = result.merge(selected, on=keys, how="left", validate="one_to_one")
    audited = result["registrant_resolution_action"].notna()
    if not (
        result.loc[audited, "registrant_role_resolved"]
        == result.loc[audited, "audited_registrant_role_resolved"]
    ).all():
        raise ValueError("Production role split differs from the registrant audit")

    non_joint = ~result["joint_filing_flag"].astype(bool)
    result.loc[non_joint, "registrant_scope_status"] = "resolved_single_filer"
    result.loc[non_joint, "registrant_scope_reason"] = (
        "exactly_one_registrant_in_original_10k"
    )
    result.loc[non_joint, "economic_entity_status"] = (
        "separate_reporting_entity_with_own_statements"
    )
    result.loc[non_joint, "registrant_resolution_action"] = (
        "retain_one_economic_entity"
    )
    result.loc[non_joint, "economic_entity_reason"] = "single_filer_original_10k"
    result.loc[non_joint, "economic_statement_scope_id"] = (
        result.loc[non_joint, "accession"] + ":" + result.loc[non_joint, "cik10"]
    )

    outside_joint_audit = (
        result["joint_filing_flag"].astype(bool)
        & result["registrant_resolution_action"].isna()
    )
    result.loc[outside_joint_audit, "registrant_scope_status"] = (
        "not_audited_outside_pre_resolution_eligible_population"
    )
    result.loc[outside_joint_audit, "registrant_scope_reason"] = (
        "joint_scope_not_required_for_pre_resolution_noneligible_row"
    )
    result.loc[outside_joint_audit, "economic_entity_status"] = "not_resolved"
    result.loc[outside_joint_audit, "registrant_resolution_action"] = (
        "preserve_pre_resolution_noneligible_status"
    )
    result.loc[outside_joint_audit, "economic_entity_reason"] = (
        "outside_registrant_audit_eligible_scope"
    )

    resolved_scopes = result[
        result["economic_statement_scope_id"].fillna("").ne("")
    ].copy()
    representative_actions = {
        "retain_one_economic_entity",
        "exclude_nonoperating_issuer",
    }
    representatives = resolved_scopes[
        resolved_scopes["registrant_resolution_action"].isin(representative_actions)
    ]
    representative_counts = representatives.groupby(
        "economic_statement_scope_id"
    )["cik10"].nunique()
    bad_representatives = representative_counts[representative_counts.ne(1)]
    if not bad_representatives.empty:
        raise ValueError(
            "Economic statement scope has a non-unique representative: "
            f"{bad_representatives.head().to_dict()}"
        )
    representative_map: Mapping[str, str] = (
        representatives.drop_duplicates("economic_statement_scope_id")
        .set_index("economic_statement_scope_id")["cik10"]
        .to_dict()
    )
    scope_members = (
        resolved_scopes.groupby("economic_statement_scope_id")["cik10"]
        .agg(lambda values: ";".join(sorted(set(values))))
        .to_dict()
    )
    result["representative_cik"] = result["economic_statement_scope_id"].map(
        representative_map
    )
    result["same_statement_scope_ciks"] = result[
        "economic_statement_scope_id"
    ].map(scope_members)

    evidence = result["manual_resolution_evidence"].fillna("").astype(str)
    fallback_evidence = (
        result["registrant_scope_reason"].fillna("").astype(str)
        + " | "
        + result["economic_entity_reason"].fillna("").astype(str)
    ).str.strip(" |")
    result["resolution_evidence"] = evidence.where(evidence.ne(""), fallback_evidence)

    duplicate = result["registrant_resolution_action"].eq(
        "exclude_duplicate_registrant_row"
    )
    nonoperating = result["registrant_resolution_action"].eq(
        "exclude_nonoperating_issuer"
    )
    ambiguous = result["registrant_resolution_action"].eq("mark_ambiguous")
    result.loc[duplicate, "membership_status"] = "excluded"
    result.loc[duplicate, "membership_reason"] = (
        "duplicate_registrant_same_statement_scope"
    )
    result.loc[nonoperating, "membership_status"] = "excluded"
    result.loc[nonoperating, "membership_reason"] = (
        "nominal_nonoperating_finance_coissuer"
    )
    result.loc[ambiguous, "membership_status"] = "ambiguous"
    result.loc[ambiguous, "membership_reason"] = result.loc[ambiguous].apply(
        _ambiguous_reason, axis=1
    )
    result["entity_resolution_membership_changed"] = (
        result["membership_status"]
        != result["membership_status_pre_entity_resolution"]
    )

    eligible = result[result["membership_status"].eq("eligible")]
    if eligible["economic_statement_scope_id"].fillna("").eq("").any():
        raise ValueError("Eligible row lacks economic_statement_scope_id")
    if eligible["representative_cik"].fillna("").eq("").any():
        raise ValueError("Eligible row lacks representative CIK")
    if eligible.duplicated(["feature_year", "economic_statement_scope_id"]).any():
        raise ValueError("More than one eligible row exists for a statement scope-year")
    if not eligible["cik10"].eq(eligible["representative_cik"]).all():
        raise ValueError("Eligible row is not the representative of its statement scope")

    diagnostics = {
        "audit_rows_matched": int(len(detail)),
        "audit_action_counts": dict(expected_action_counts),
        "duplicate_rows_removed_from_eligible": int(duplicate.sum()),
        "nonoperating_coissuers_removed_from_eligible": int(nonoperating.sum()),
        "rows_changed_to_ambiguous": int(ambiguous.sum()),
        "eligible_statement_scope_year_duplicates": int(
            eligible.duplicated(
                ["feature_year", "economic_statement_scope_id"], keep=False
            ).sum()
        ),
        "eligible_distinct_statement_scope_years": int(
            eligible[["feature_year", "economic_statement_scope_id"]]
            .drop_duplicates()
            .shape[0]
        ),
        "eligible_distinct_representative_ciks": int(
            eligible["representative_cik"].nunique()
        ),
        "eligible_distinct_economic_groups": int(
            eligible["economic_group_id"].nunique()
        ),
    }
    result = result.drop(columns=["audited_registrant_role_resolved"])
    return result, diagnostics

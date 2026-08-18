"""Audit the application of frozen PIT-B to frozen historical universe.

The audit is descriptive only. It cannot change target or membership and does
not build X_t or use model results.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np
import pandas as pd


if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.data import target_candidate_v2_pit as frozen_target
from src.data.research_universe_target_application import (
    BASE_DIR,
    APPLICATION_CONFIG_PATH,
    configured_path,
    load_application_config,
    sha256,
    validate_application_artifact,
    verify_frozen_inputs,
    write_json_atomic,
)


SIGNALS = tuple(frozen_target.TARGET_SIGNALS)
FINANCIAL_AUDIT_COLUMNS = (
    "log_assets_t",
    "roa_t",
    "ocf_assets_t",
    "current_ratio_t",
    "liabilities_assets_t",
    "log_revenues_t",
)


def as_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.fillna("").astype(str).str.lower().isin({"true", "1", "yes"})


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = numerator / denominator
    return result.where(denominator.abs().gt(1_000.0)).replace([np.inf, -np.inf], np.nan)


def add_audit_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    primitive_columns = {
        primitive: pd.to_numeric(
            result.get(f"A_current_t_{primitive}_value"), errors="coerce"
        )
        for primitive in frozen_target.PRIMITIVES
    }
    assets = primitive_columns["assets"]
    revenues = primitive_columns["revenues"]
    result["assets_t"] = assets
    result["log_assets_t"] = np.log(assets.where(assets.gt(1_000.0)))
    result["roa_t"] = safe_divide(primitive_columns["net_income"], assets)
    result["ocf_assets_t"] = safe_divide(
        primitive_columns["operating_cash_flow"], assets
    )
    result["current_ratio_t"] = safe_divide(
        primitive_columns["current_assets"], primitive_columns["current_liabilities"]
    )
    result["liabilities_assets_t"] = safe_divide(
        primitive_columns["liabilities"], assets
    )
    result["log_revenues_t"] = np.log(revenues.where(revenues.gt(1_000.0)))
    result["recovered_flag"] = as_bool(result["recovered_vs_old_universe"])
    result["inactive_proxy_flag"] = as_bool(
        result["later_inactive_delisted_or_unmapped_proxy"]
    )
    result["non_xbrl_role_flag"] = result["registrant_role_resolved"].eq(
        "single_filer_non_xbrl_registrant"
    )

    size = pd.Series("assets_unavailable_or_nonpositive", index=result.index, dtype="string")
    labels = ["Q1_smallest", "Q2", "Q3", "Q4_largest"]
    valid = assets.gt(1_000.0)
    for _, subset in result.loc[valid].groupby("feature_year"):
        percentile = subset["assets_t"].rank(method="average", pct=True)
        size.loc[subset.index] = pd.cut(
            percentile,
            bins=[0.0, 0.25, 0.50, 0.75, 1.0],
            labels=labels,
            include_lowest=True,
        ).astype("string")
    result["assets_size_quartile"] = size
    return result


def status_distribution(frame: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    working = frame.copy()
    for group in groups:
        working[group] = working[group].fillna("NA")
    grouped = (
        working.groupby(groups, dropna=False)
        .agg(
            eligible_company_years=("cik10", "size"),
            available=("target_status", lambda values: int(values.eq("available").sum())),
            missing=("target_status", lambda values: int(values.eq("missing").sum())),
            ambiguous=("target_status", lambda values: int(values.eq("ambiguous").sum())),
            hard_exclude=(
                "target_status",
                lambda values: int(values.eq("hard_exclude").sum()),
            ),
            not_computable=(
                "target_status",
                lambda values: int(values.eq("not_computable").sum()),
            ),
            positive=(
                "target_candidate_v2_pit_b",
                lambda values: int(pd.to_numeric(values, errors="coerce").eq(1).sum()),
            ),
        )
        .reset_index()
    )
    grouped["target_coverage"] = grouped["available"] / grouped["eligible_company_years"]
    grouped["positive_rate_among_available"] = (
        grouped["positive"] / grouped["available"].replace(0, np.nan)
    )
    return grouped


def reason_distribution(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    definitions = (
        ("missing", "missing_reasons"),
        ("ambiguous", "ambiguous_reasons"),
        ("hard_exclude", "hard_exclude_reasons"),
        ("not_computable", "target_application_reason"),
    )
    for status, column in definitions:
        subset = frame.loc[frame["target_status"].eq(status), column].fillna("")
        counter: Counter[str] = Counter()
        for value in subset:
            reasons = [item for item in str(value).split(";") if item]
            counter.update(reasons or ["reason_not_recorded"])
        denominator = int(frame["target_status"].eq(status).sum())
        for reason, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
            rows.append(
                {
                    "target_status": status,
                    "reason": reason,
                    "observation_count": int(count),
                    "share_of_status": float(count / denominator) if denominator else np.nan,
                }
            )
    return pd.DataFrame(rows)


def standardized_mean_difference(left: pd.Series, reference: pd.Series) -> float:
    left = pd.to_numeric(left, errors="coerce").dropna()
    reference = pd.to_numeric(reference, errors="coerce").dropna()
    if len(left) < 2 or len(reference) < 2:
        return np.nan
    pooled = np.sqrt((left.var(ddof=1) + reference.var(ddof=1)) / 2.0)
    if not np.isfinite(pooled) or pooled == 0:
        return 0.0 if np.isclose(left.mean(), reference.mean()) else np.nan
    return float((left.mean() - reference.mean()) / pooled)


def smd_table(frame: pd.DataFrame) -> list[dict[str, Any]]:
    reference = frame.loc[frame["target_status"].eq("available")]
    rows: list[dict[str, Any]] = []
    for status in ("missing", "ambiguous", "hard_exclude", "not_computable"):
        subset = frame.loc[frame["target_status"].eq(status)]
        for column in FINANCIAL_AUDIT_COLUMNS:
            rows.append(
                {
                    "target_status": status,
                    "variable": column,
                    "available_nonmissing_n": int(reference[column].notna().sum()),
                    "status_nonmissing_n": int(subset[column].notna().sum()),
                    "standardized_mean_difference_vs_available": standardized_mean_difference(
                        subset[column], reference[column]
                    ),
                }
            )
    return rows


def coverage_range(table: pd.DataFrame, exclude: Iterable[str] = ()) -> float:
    subset = table.loc[~table.iloc[:, 0].astype(str).isin(set(exclude))]
    values = pd.to_numeric(subset["target_coverage"], errors="coerce").dropna()
    return float(values.max() - values.min()) if len(values) else np.nan


def two_group_gap(frame: pd.DataFrame, column: str) -> dict[str, Any]:
    table = status_distribution(frame, [column])
    rates = {
        str(row[column]): float(row["target_coverage"])
        for _, row in table.iterrows()
    }
    values = list(rates.values())
    return {
        "groups": rates,
        "absolute_coverage_gap": abs(values[0] - values[1]) if len(values) == 2 else np.nan,
    }


def signal_coverage(frame: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for signal in SIGNALS:
        available = frame[signal].notna()
        rows.append(
            {
                "signal": signal,
                "available_n": int(available.sum()),
                "coverage": float(available.mean()),
                "signal_positive_n": int(
                    pd.to_numeric(frame.loc[available, signal], errors="coerce").eq(1).sum()
                ),
            }
        )
    return rows


def frozen_overlap_check(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    frozen_path = configured_path(config, "frozen_inputs", "target_artifact")
    frozen = pd.read_csv(frozen_path, dtype={"cik10": "string"}, low_memory=False)
    frozen["cik10"] = frozen["cik10"].str.zfill(10)
    frozen["feature_year"] = pd.to_numeric(frozen["feature_year"], errors="raise").astype(int)
    overlap = frame[["cik10", "feature_year"]].merge(
        frozen[["cik10", "feature_year"]],
        on=["cik10", "feature_year"],
        how="inner",
    )
    keys = set(overlap.itertuples(index=False, name=None))
    left_all = frame.loc[
        frame[["cik10", "feature_year"]].apply(tuple, axis=1).isin(keys)
    ].sort_values(["cik10", "feature_year"])
    anchor_mismatch_rows = int(
        (~as_bool(left_all["universe_anchor_matches_target_anchor_t"])).sum()
    )
    left = left_all.loc[
        as_bool(left_all["universe_anchor_matches_target_anchor_t"])
    ].copy()
    mapped_keys = set(
        left[["cik10", "feature_year"]].itertuples(index=False, name=None)
    )
    right = frozen.loc[
        frozen[["cik10", "feature_year"]].apply(tuple, axis=1).isin(mapped_keys)
    ].sort_values(["cik10", "feature_year"])
    common = [
        column
        for column in frozen.columns
        if column in left.columns
        and column not in {"cik10", "feature_year"}
        and column not in {
            "company_name",
            "primary_ticker",
            "research_sector",
            "sic",
            "sic_int",
            "sic_description",
            "sic_major_group",
            "split",
        }
    ]
    left = left.set_index(["cik10", "feature_year"])[common]
    right = right.set_index(["cik10", "feature_year"])[common]
    if not left.index.equals(right.index):
        raise RuntimeError("Frozen target overlap keys are not aligned")
    mismatches: list[dict[str, Any]] = []
    mismatch_cells = 0
    for column in common:
        left_values = left[column]
        right_values = right[column]
        if pd.api.types.is_numeric_dtype(left_values) or pd.api.types.is_numeric_dtype(
            right_values
        ):
            left_numeric = pd.to_numeric(left_values, errors="coerce")
            right_numeric = pd.to_numeric(right_values, errors="coerce")
            different = ~(
                np.isclose(
                    left_numeric.fillna(0.0),
                    right_numeric.fillna(0.0),
                    rtol=0.0,
                    atol=1e-12,
                )
                & left_numeric.isna().eq(right_numeric.isna())
            )
        else:
            different = left_values.fillna("").astype(str).ne(
                right_values.fillna("").astype(str)
            )
        count = int(different.sum())
        if count:
            mismatches.append({"column": column, "mismatch_cells": count})
            mismatch_cells += count
    return {
        "overlap_rows_total": int(len(left_all)),
        "overlap_rows": int(len(left)),
        "anchor_mismatch_rows_withheld_as_not_computable": anchor_mismatch_rows,
        "columns_checked": int(len(common)),
        "mismatch_cells": int(mismatch_cells),
        "mismatched_columns": mismatches,
    }


def tree_digest(paths: Iterable[Path], base: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    files = sorted({path for path in paths if path.is_file()})
    total_bytes = 0
    for path in files:
        relative = str(path.relative_to(base))
        file_hash = sha256(path)
        size = path.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\n")
        total_bytes += size
    return {
        "files": len(files),
        "bytes": int(total_bytes),
        "aggregate_sha256": digest.hexdigest(),
    }


def used_cache_inventory(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    companyfacts_dir = configured_path(config, "application_cache", "companyfacts")
    submissions_dir = configured_path(config, "application_cache", "submissions")
    revenue_dir = configured_path(
        config, "application_cache", "revenue_statement_evidence"
    )
    ciks = sorted(frame["cik10"].unique())
    companyfacts = [companyfacts_dir / f"CIK{cik}.json" for cik in ciks]
    submissions: list[Path] = []
    for cik in ciks:
        main = submissions_dir / f"CIK{cik}.json"
        submissions.append(main)
        if not main.is_file():
            continue
        payload = json.loads(main.read_text(encoding="utf-8"))
        for item in payload.get("filings", {}).get("files", []):
            name = str(item.get("name", "") or "")
            if name:
                submissions.append(submissions_dir / name)

    revenue_paths: list[Path] = []
    anchors = frame.loc[
        frame["anchor_t1_accn"].notna()
        & frame["B_revenues_status"].isin(["selected", "ambiguous"]),
        ["cik10", "anchor_t1_accn"],
    ].drop_duplicates()
    for row in anchors.itertuples(index=False):
        directory = revenue_dir / row.cik10 / str(row.anchor_t1_accn).replace("-", "")
        if directory.is_dir():
            revenue_paths.extend(directory.iterdir())
    return {
        "companyfacts_projection": tree_digest(companyfacts, companyfacts_dir),
        "submissions_projection": tree_digest(submissions, submissions_dir),
        "revenue_statement_evidence": tree_digest(revenue_paths, revenue_dir),
    }


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records"))


def format_percent(value: Any) -> str:
    """Format audit rates without treating unavailable denominators as zero."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "NA"
    return f"{numeric:.2%}" if np.isfinite(numeric) else "NA"


def format_decimal(value: Any, digits: int = 3) -> str:
    """Format finite diagnostics while preserving an explicit NA state."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "NA"
    return f"{numeric:.{digits}f}" if np.isfinite(numeric) else "NA"


def markdown_report(audit: dict[str, Any]) -> str:
    overall = audit["overall"]
    lines = [
        "# Audyt zastosowania frozen universe v1.1.0 + frozen target v1.0.0",
        "",
        "Target i membership zostały zastosowane bez zmian. Nie zbudowano `X_t` i nie użyto wyników modeli.",
        "",
        "## Wynik ogólny",
        "",
        f"- eligible company-years: **{overall['eligible_company_years']:,}**",
        f"- target available: **{overall['target_available']:,}** ({format_percent(overall['target_coverage'])})",
        f"- positive class: **{overall['positive_n']:,}** ({format_percent(overall['positive_rate_among_available'])} dostępnych)",
        f"- missing: {overall['missing']:,}",
        f"- ambiguous: {overall['ambiguous']:,}",
        f"- hard-exclude: {overall['hard_exclude']:,}",
        f"- not computable: {overall['not_computable']:,}",
        "",
        "## Coverage według roku",
        "",
        "| Rok | Eligible | Available | Coverage | Positive | Positive rate | Missing | Ambiguous | Hard-exclude | Not computable |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in audit["coverage_by_year"]:
        lines.append(
            f"| {int(row['feature_year'])} | {int(row['eligible_company_years']):,} | "
            f"{int(row['available']):,} | {format_percent(row['target_coverage'])} | "
            f"{int(row['positive']):,} | {format_percent(row.get('positive_rate_among_available'))} | "
            f"{int(row['missing']):,} | {int(row['ambiguous']):,} | "
            f"{int(row['hard_exclude']):,} | {int(row['not_computable']):,} |"
        )
    lines.extend(
        [
            "",
            "## Coverage D1–D5",
            "",
            "| Sygnał | Available N | Coverage | Positive signal N |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in audit["signal_coverage"]:
        lines.append(
            f"| {row['signal']} | {row['available_n']:,} | {format_percent(row['coverage'])} | {row['signal_positive_n']:,} |"
        )
    lines.extend(["", "## Najczęstsze przyczyny niedostępności", ""])
    for row in audit["status_reasons"][:40]:
        lines.append(
            f"- `{row['target_status']}` — `{row['reason']}`: {row['observation_count']:,} ({format_percent(row['share_of_status'])})"
        )
    selection = audit["selection_bias_assessment"]
    lines.extend(
        [
            "",
            "## Selection bias i informative censoring",
            "",
            f"- complete-case selection bias: **{selection['complete_case_selection_bias']}**",
            f"- informative censoring: **{selection['informative_censoring']}**",
            f"- coverage range według roku: {format_percent(selection['coverage_range_by_year'])}",
            f"- coverage range według sektora: {format_percent(selection['coverage_range_by_sector'])}",
            f"- coverage range według obserwowanych kwartylów assets: {format_percent(selection['coverage_range_by_observed_size_quartile'])}",
            f"- największe |SMD| względem available: {format_decimal(selection['maximum_absolute_smd'])}",
            f"- recovered-vs-old coverage gap: {format_percent(selection['recovered_gap']['absolute_coverage_gap'])}",
            f"- inactive-proxy coverage gap: {format_percent(selection['inactive_proxy_gap']['absolute_coverage_gap'])}",
            f"- non-XBRL-role coverage gap: {format_percent(selection['non_xbrl_role_gap']['absolute_coverage_gap'])}",
            "",
            "Ocena jest ograniczeniem interpretacyjnym; nie zmienia universe ani targetu.",
            "",
            "## Kontrole reprodukowalności",
            "",
            f"- frozen target overlap rows: {audit['frozen_overlap']['overlap_rows']:,}",
            f"- frozen target mismatch cells: {audit['frozen_overlap']['mismatch_cells']:,}",
            f"- provenance violations: {audit['provenance_integrity']['violation_count']:,}",
            f"- unavailable rows assigned class: {audit['build_checks']['unavailable_rows_with_class']:,}",
            f"- artifact SHA-256: `{audit['artifact']['sha256']}`",
            "",
            f"## Werdykt: {audit['verdict']}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    config = load_application_config()
    frozen_before = verify_frozen_inputs(config)
    artifact_path = configured_path(config, "outputs", "final_artifact")
    frame = pd.read_csv(
        artifact_path,
        dtype={"cik10": "string", "representative_cik": "string"},
        low_memory=False,
    )
    frame["cik10"] = frame["cik10"].str.zfill(10)
    frame["representative_cik"] = frame["representative_cik"].str.zfill(10)
    validate_application_artifact(frame)
    frame = add_audit_features(frame)

    by_year = status_distribution(frame, ["feature_year"])
    by_sector = status_distribution(frame, ["research_sector"])
    by_sic = status_distribution(
        frame, ["historical_sic", "historical_sic_description"]
    )
    by_size = status_distribution(frame, ["assets_size_quartile"])
    by_recovered = status_distribution(frame, ["recovered_flag"])
    reasons = reason_distribution(frame)
    signals = signal_coverage(frame)
    smds = smd_table(frame)

    target_config = frozen_target.load_config(
        configured_path(config, "frozen_inputs", "target_config")
    )
    scope = replace(
        frozen_target.parse_scope(target_config),
        feature_year_start=2011,
        feature_year_end=2024,
    )
    provenance = frozen_target.provenance_integrity(frame, target_config, scope)
    overlap = frozen_overlap_check(frame, config)
    frozen_after = verify_frozen_inputs(config)
    if frozen_before != frozen_after:
        raise RuntimeError("Frozen input changed during audit")

    available = frame["target_status"].eq("available")
    positive = pd.to_numeric(
        frame.loc[available, "target_candidate_v2_pit_b"], errors="coerce"
    ).eq(1)
    status_counts = frame["target_status"].value_counts()
    max_abs_smd = max(
        (
            abs(float(row["standardized_mean_difference_vs_available"]))
            for row in smds
            if pd.notna(row["standardized_mean_difference_vs_available"])
        ),
        default=np.nan,
    )
    observed_size = by_size.loc[
        ~by_size["assets_size_quartile"].eq("assets_unavailable_or_nonpositive")
    ]
    thresholds = config["audit"]
    complete_thresholds = thresholds["complete_case_high_risk_thresholds"]
    year_range = coverage_range(by_year)
    sector_range = coverage_range(by_sector)
    size_range = coverage_range(observed_size)
    complete_high = (
        max(year_range, sector_range, size_range)
        >= float(complete_thresholds["coverage_range"])
        or max_abs_smd
        >= float(complete_thresholds["absolute_standardized_mean_difference"])
    )
    recovered_gap = two_group_gap(frame, "recovered_flag")
    inactive_gap = two_group_gap(frame, "inactive_proxy_flag")
    non_xbrl_gap = two_group_gap(frame, "non_xbrl_role_flag")
    censor_thresholds = thresholds["informative_censoring_high_risk_thresholds"]
    censor_high = (
        recovered_gap["absolute_coverage_gap"]
        >= float(censor_thresholds["recovered_coverage_gap"])
        or inactive_gap["absolute_coverage_gap"]
        >= float(censor_thresholds["inactive_proxy_coverage_gap"])
        or non_xbrl_gap["absolute_coverage_gap"]
        >= float(censor_thresholds["non_xbrl_coverage_gap"])
    )

    unavailable_with_class = int(
        pd.to_numeric(
            frame.loc[~available, "target_candidate_v2_pit_b"], errors="coerce"
        ).notna().sum()
    )
    checks = {
        "exactly_64901_eligible_rows": len(frame) == 64_901,
        "membership_all_eligible": bool(frame["membership_status"].eq("eligible").all()),
        "unique_cik_year": not bool(frame.duplicated(["cik10", "feature_year"]).any()),
        "unavailable_rows_with_class": unavailable_with_class,
        "frozen_overlap_mismatch_cells": overlap["mismatch_cells"],
        "provenance_violation_count": provenance["violation_count"],
        "frozen_hashes_unchanged": frozen_before == frozen_after,
    }
    correct = (
        checks["exactly_64901_eligible_rows"]
        and checks["membership_all_eligible"]
        and checks["unique_cik_year"]
        and unavailable_with_class == 0
        and overlap["mismatch_cells"] == 0
        and provenance["violation_count"] == 0
        and checks["frozen_hashes_unchanged"]
    )

    audit = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "application_id": config["application"]["id"],
        "frozen_components": frozen_after,
        "scope": {
            "feature_years": [2011, 2024],
            "membership_filter": "membership_status == eligible",
            "models_used": False,
            "x_t_built": False,
            "unavailable_mapped_to_zero": False,
        },
        "overall": {
            "eligible_company_years": int(len(frame)),
            "target_available": int(available.sum()),
            "target_coverage": float(available.mean()),
            "positive_n": int(positive.sum()),
            "positive_rate_among_available": float(positive.mean()) if len(positive) else np.nan,
            "missing": int(status_counts.get("missing", 0)),
            "ambiguous": int(status_counts.get("ambiguous", 0)),
            "hard_exclude": int(status_counts.get("hard_exclude", 0)),
            "not_computable": int(status_counts.get("not_computable", 0)),
        },
        "signal_coverage": signals,
        "coverage_by_year": records(by_year),
        "coverage_by_sector": records(by_sector),
        "coverage_by_sic": records(by_sic),
        "coverage_by_size": records(by_size),
        "coverage_recovered_vs_old": records(by_recovered),
        "status_reasons": records(reasons),
        "standardized_mean_differences": smds,
        "selection_bias_assessment": {
            "complete_case_selection_bias": "high_risk" if complete_high else "material_risk_below_predefined_high_threshold",
            "informative_censoring": "high_risk" if censor_high else "material_risk_below_predefined_high_threshold",
            "coverage_range_by_year": year_range,
            "coverage_range_by_sector": sector_range,
            "coverage_range_by_observed_size_quartile": size_range,
            "maximum_absolute_smd": max_abs_smd,
            "recovered_gap": recovered_gap,
            "inactive_proxy_gap": inactive_gap,
            "non_xbrl_role_gap": non_xbrl_gap,
        },
        "frozen_overlap": overlap,
        "provenance_integrity": provenance,
        "build_checks": checks,
        "artifact": {
            "path": str(artifact_path.relative_to(BASE_DIR)),
            "rows": int(len(frame)),
            "bytes": artifact_path.stat().st_size,
            "sha256": sha256(artifact_path),
        },
        "cache_inventory": used_cache_inventory(frame, config),
        "verdict": (
            "FROZEN UNIVERSE v1.1.0 + FROZEN TARGET v1.0.0 CORRECTLY AND REPRODUCIBLY BUILT"
            if correct
            else "FROZEN UNIVERSE v1.1.0 + FROZEN TARGET v1.0.0 NOT CORRECTLY AND REPRODUCIBLY BUILT"
        ),
    }

    output_tables = {
        "coverage_by_year": by_year,
        "coverage_by_sector": by_sector,
        "coverage_by_sic": by_sic,
        "coverage_by_size": by_size,
        "status_reasons": reasons,
    }
    for key, table in output_tables.items():
        path = configured_path(config, "outputs", key)
        path.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(path, index=False)

    audit_json_path = configured_path(config, "outputs", "audit_json")
    audit_md_path = configured_path(config, "outputs", "audit_markdown")
    write_json_atomic(audit, audit_json_path)
    audit_md_path.write_text(markdown_report(audit), encoding="utf-8")

    code_paths = [
        APPLICATION_CONFIG_PATH,
        BASE_DIR / "src/data/research_universe_target_application.py",
        BASE_DIR / "src/data/25_prepare_research_universe_target_inputs.py",
        BASE_DIR / "src/data/26_apply_frozen_target_to_historical_universe.py",
        BASE_DIR / "src/data/27_download_research_universe_target_revenue_evidence.py",
        BASE_DIR / "src/data/28_audit_research_universe_target_application.py",
    ]
    report_paths = [
        audit_json_path,
        audit_md_path,
        *[configured_path(config, "outputs", key) for key in output_tables],
    ]
    reproduction = {
        "application_id": config["application"]["id"],
        "created_at": audit["created_at"],
        "frozen_components": frozen_after,
        "code_and_configuration": [
            {
                "path": str(path.relative_to(BASE_DIR)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in code_paths
        ],
        "artifact": audit["artifact"],
        "cache_inventory": audit["cache_inventory"],
        "audit_outputs": [
            {
                "path": str(path.relative_to(BASE_DIR)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in report_paths
        ],
        "build_checks": checks,
        "verdict": audit["verdict"],
        "notes": [
            "The reproduction manifest intentionally does not hash itself.",
            "The two frozen component manifests and artifacts were read-only inputs.",
            "Raw caches are excluded from Git and controlled by aggregate content digests.",
        ],
    }
    write_json_atomic(
        reproduction, configured_path(config, "outputs", "reproduction_manifest")
    )
    print(json.dumps({"overall": audit["overall"], "verdict": audit["verdict"]}, indent=2))


if __name__ == "__main__":
    main()

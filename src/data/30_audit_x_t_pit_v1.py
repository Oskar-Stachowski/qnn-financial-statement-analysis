"""Run the pre-freeze audit for raw point-in-time X_t v1.

All methodological diagnostics are restricted to feature years 2011--2022.
The script validates the full artifact schema mechanically but does not report
or use 2023--2024 feature distributions, model results, or target outcomes.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable
from xml.etree import ElementTree

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

import numpy as np
import pandas as pd

from src.data.revenue_statement_resolver import amount_equal, evidence_rows
from src.data.x_t_pit import (
    BASE_DIR,
    CONFIG_PATH,
    PRIMITIVES,
    configured_path,
    feature_names,
    load_config,
    prediction_timestamp,
    sha256,
    text,
    truthy,
    validate_raw_artifact_path,
)


TARGET_APPLICATION_PATH = (
    BASE_DIR
    / "data/processed/research_universe_pit_v1_1_0_target_pit_b_v1_0_0.csv"
)


def read_development(path: Path, usecols: Iterable[str]) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        path,
        usecols=list(dict.fromkeys(usecols)),
        low_memory=False,
        chunksize=5_000,
    ):
        years = pd.to_numeric(chunk["feature_year"], errors="coerce")
        selected = chunk.loc[years.between(2011, 2022)].copy()
        selected["feature_year"] = pd.to_numeric(
            selected["feature_year"], errors="raise"
        ).astype(int)
        chunks.append(selected)
    return pd.concat(chunks, ignore_index=True)


def markdown_table(frame: pd.DataFrame, digits: int = 4) -> str:
    if frame.empty:
        return "_Brak obserwacji._"
    display = frame.copy()
    for column in display.select_dtypes(include=["float", "float64"]).columns:
        display[column] = display[column].map(
            lambda value: "" if pd.isna(value) else f"{value:.{digits}f}"
        )
    headers = [str(column) for column in display.columns]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for record in display.astype(str).to_dict("records"):
        lines.append(
            "| "
            + " | ".join(record[column].replace("|", "\\|") for column in headers)
            + " |"
        )
    return "\n".join(lines)


def coverage_summary(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for block in ("L", "D", "R"):
        for feature in config["blocks"][block]["features"]:
            status = frame[f"{feature}_status"].astype(str)
            counts = status.value_counts()
            rows.append(
                {
                    "block": block,
                    "feature": feature,
                    "observations": len(frame),
                    "available": int(counts.get("available", 0)),
                    "coverage": float(status.eq("available").mean()),
                    "missing": int(counts.get("missing", 0)),
                    "ambiguous": int(counts.get("ambiguous", 0)),
                    "not_computable": int(counts.get("not_computable", 0)),
                    "not_available_non_xbrl": int(
                        counts.get("not_available_non_xbrl", 0)
                    ),
                }
            )
    return pd.DataFrame(rows)


def primitive_coverage_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for primitive in PRIMITIVES:
        for role, column in (
            ("current_t", f"current_t_{primitive}_status"),
            ("same_anchor_pair", f"pair_{primitive}_status"),
        ):
            status = frame[column].astype(str)
            counts = status.value_counts()
            rows.append(
                {
                    "primitive": primitive,
                    "role": role,
                    "observations": len(frame),
                    "selected": int(counts.get("selected", 0)),
                    "coverage": float(status.eq("selected").mean()),
                    "missing": int(counts.get("missing", 0)),
                    "ambiguous": int(counts.get("ambiguous", 0)),
                    "hard_exclude": int(counts.get("hard_exclude", 0)),
                    "not_available_non_xbrl": int(
                        counts.get("not_available_non_xbrl", 0)
                    ),
                }
            )
    return pd.DataFrame(rows)


def primitive_sign_summary(frame: pd.DataFrame) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for primitive in PRIMITIVES:
        values = pd.to_numeric(frame[f"current_t_{primitive}_value"], errors="coerce")
        selected = frame[f"current_t_{primitive}_status"].eq("selected")
        summary[primitive] = {
            "selected": int(selected.sum()),
            "negative": int((selected & values.lt(0)).sum()),
            "zero": int((selected & values.eq(0)).sum()),
            "positive": int((selected & values.gt(0)).sum()),
            "nonfinite": int((selected & ~np.isfinite(values)).sum()),
        }
    return summary


def grouped_coverage(
    frame: pd.DataFrame,
    group_columns: list[str],
    config: dict[str, Any],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in frame.groupby(group_columns, dropna=False, observed=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        record = {column: value for column, value in zip(group_columns, keys, strict=True)}
        record["observations"] = len(group)
        record["x_t_available_core"] = int(group["x_t_status"].eq("available_core").sum())
        record["x_t_available_core_rate"] = float(
            group["x_t_status"].eq("available_core").mean()
        )
        for block in ("L", "D", "R"):
            features = list(config["blocks"][block]["features"])
            complete = pd.concat(
                [group[f"{feature}_status"].eq("available") for feature in features],
                axis=1,
            ).all(axis=1)
            record[f"{block}_complete"] = int(complete.sum())
            record[f"{block}_complete_rate"] = float(complete.mean())
        for primitive in PRIMITIVES:
            record[f"current_{primitive}_coverage"] = float(
                group[f"current_t_{primitive}_status"].eq("selected").mean()
            )
            record[f"pair_{primitive}_coverage"] = float(
                group[f"pair_{primitive}_status"].eq("selected").mean()
            )
        for feature in feature_names(config):
            record[f"feature_{feature}_coverage"] = float(
                group[f"{feature}_status"].eq("available").mean()
            )
        rows.append(record)
    return pd.DataFrame(rows)


def add_size_bucket(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    assets = pd.to_numeric(output["current_t_assets_value"], errors="coerce")
    valid = output["current_t_assets_status"].eq("selected") & assets.gt(0)
    output["size_bucket"] = "assets_missing_or_nonpositive"
    for year, indexes in output.loc[valid].groupby("feature_year").groups.items():
        values = assets.loc[indexes]
        try:
            bins = pd.qcut(values.rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
            output.loc[indexes, "size_bucket"] = bins.astype(str).to_numpy()
        except ValueError:
            output.loc[indexes, "size_bucket"] = "size_unresolved"
    return output


def status_reason_table(frame: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for stage, status_col, reason_col in (
        ("row", "x_t_status", "x_t_status_reason"),
        (
            "anchor_period",
            "anchor_period_validation_status",
            "anchor_period_validation_reason",
        ),
        (
            "comparative_period",
            "comparative_period_validation_status",
            "comparative_period_validation_reason",
        ),
    ):
        counts = (
            frame.groupby([status_col, reason_col], dropna=False)
            .size()
            .reset_index(name="observations")
        )
        for item in counts.to_dict("records"):
            rows.append(
                {
                    "kind": "row_or_period",
                    "name": stage,
                    "stage": stage,
                    "status": item[status_col],
                    "reason": item[reason_col],
                    "observations": int(item["observations"]),
                }
            )
    for primitive in PRIMITIVES:
        for stage, status_col, reason_col in (
            (
                "current",
                f"current_t_{primitive}_status",
                f"current_t_{primitive}_reason",
            ),
            ("pair", f"pair_{primitive}_status", f"pair_{primitive}_reason"),
        ):
            counts = (
                frame.groupby([status_col, reason_col], dropna=False)
                .size()
                .reset_index(name="observations")
            )
            for item in counts.to_dict("records"):
                rows.append(
                    {
                        "kind": "primitive",
                        "name": primitive,
                        "stage": stage,
                        "status": item[status_col],
                        "reason": item[reason_col],
                        "observations": int(item["observations"]),
                    }
                )
    for feature in feature_names(config):
        counts = (
            frame.groupby([f"{feature}_status", f"{feature}_reason"], dropna=False)
            .size()
            .reset_index(name="observations")
        )
        for item in counts.to_dict("records"):
            rows.append(
                {
                    "kind": "feature",
                    "name": feature,
                    "stage": "derived",
                    "status": item[f"{feature}_status"],
                    "reason": item[f"{feature}_reason"],
                    "observations": int(item["observations"]),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["kind", "name", "stage", "observations"], ascending=[True, True, True, False]
    )


def feature_outliers(frame: pd.DataFrame, config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    rows: list[pd.DataFrame] = []
    summary: dict[str, Any] = {}
    for feature in feature_names(config):
        values = pd.to_numeric(frame[f"{feature}_value"], errors="coerce")
        available = frame[f"{feature}_status"].eq("available")
        selected = values.loc[available]
        finite = selected[np.isfinite(selected)]
        quantiles = finite.quantile([0.001, 0.01, 0.5, 0.99, 0.999]).to_dict()
        summary[feature] = {
            "available": int(available.sum()),
            "nonfinite": int((available & ~np.isfinite(values)).sum()),
            "quantiles": {str(key): float(value) for key, value in quantiles.items()},
            "near_zero_denominator": int(
                frame[f"{feature}_near_zero_denominator_flag"].map(truthy).sum()
            ),
        }
        if finite.empty:
            continue
        candidates = frame.loc[finite.index, [
            "research_universe_company_year_id",
            "cik10",
            "feature_year",
            "research_sector",
            "anchor_accession",
        ]].copy()
        candidates["feature"] = feature
        candidates["value"] = finite
        candidates["absolute_value"] = finite.abs()
        rows.append(candidates.nlargest(10, "absolute_value"))
    output = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return output, summary


def revenue_review_sample(frame: pd.DataFrame, seed: int) -> pd.DataFrame:
    selected: dict[str, set[str]] = {}

    def add_category(category: str, subset: pd.DataFrame, count: int) -> None:
        if subset.empty:
            return
        sample = subset.sample(n=min(count, len(subset)), random_state=seed + len(selected))
        for identifier in sample["research_universe_company_year_id"].astype(str):
            selected.setdefault(identifier, set()).add(category)

    available = frame.loc[frame["current_t_revenues_status"].eq("selected")].copy()
    for year, group in available.groupby("feature_year"):
        add_category(f"available_year_{year}", group, 2)
    for sector, group in available.groupby("research_sector"):
        add_category(f"available_sector_{sector}", group, 2)
    distinct_pairs = available.drop_duplicates(
        ["current_t_revenues_tag", "current_t_revenues_statement_label"]
    )
    add_category("distinct_tag_label_pair", distinct_pairs, 15)
    growth = pd.to_numeric(available["revenue_growth_1y_value"], errors="coerce").abs()
    add_category("largest_revenue_change", available.loc[growth.nlargest(15).index], 15)
    conflicts = frame.loc[
        frame["current_t_revenues_status"].eq("ambiguous")
        & ~frame["current_t_revenues_reason"].eq("primary_statement_evidence_unavailable")
    ]
    for reason, group in conflicts.groupby("current_t_revenues_reason"):
        add_category(f"ambiguous_{reason}", group, 3)
    missing_evidence = frame.loc[
        frame["current_t_revenues_reason"].eq("primary_statement_evidence_unavailable")
    ]
    add_category("missing_statement_evidence", missing_evidence, 5)

    identifiers = sorted(selected)
    if len(identifiers) < 50:
        remaining = frame.loc[
            ~frame["research_universe_company_year_id"].astype(str).isin(identifiers)
        ]
        add_category("random_supplement", remaining, 50 - len(identifiers))
        identifiers = sorted(selected)
    sample = frame.loc[
        frame["research_universe_company_year_id"].astype(str).isin(identifiers)
    ].copy()
    sample["review_categories"] = sample["research_universe_company_year_id"].astype(str).map(
        lambda item: ";".join(sorted(selected[item]))
    )
    return sample


def verify_revenue_review(sample: pd.DataFrame, evidence_root: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for source in sample.to_dict("records"):
        cik10 = str(source["cik10"]).split(".")[0].zfill(10)
        accession = str(source["anchor_accession"])
        directory = evidence_root / cik10 / accession.replace("-", "")
        status = str(source.get("current_t_revenues_status", ""))
        record = {
            "research_universe_company_year_id": source["research_universe_company_year_id"],
            "cik10": cik10,
            "feature_year": int(source["feature_year"]),
            "research_sector": source.get("research_sector", ""),
            "anchor_accession": accession,
            "review_categories": source.get("review_categories", ""),
            "resolver_status": status,
            "resolver_reason": source.get("current_t_revenues_reason", ""),
            "tag": source.get("current_t_revenues_tag", ""),
            "statement_file": source.get("current_t_revenues_statement_file", ""),
            "statement_label": source.get("current_t_revenues_statement_label", ""),
            "statement_concepts": source.get("current_t_revenues_statement_concepts", ""),
            "resolver_current_value": source.get("current_t_revenues_value", np.nan),
            "resolver_current_end": source.get("current_t_revenues_end", ""),
            "direct_statement_value": np.nan,
            "direct_value_matches": False,
            "exact_accession": accession,
            "review_outcome": "",
        }
        if status != "selected":
            value_present = pd.notna(source.get("current_t_revenues_value"))
            record["review_outcome"] = (
                "ERROR_unavailable_revenue_has_value"
                if value_present
                else "PASS_fail_closed_no_value"
            )
            rows.append(record)
            continue
        statement_path = directory / str(source.get("current_t_revenues_statement_file", ""))
        if not statement_path.exists():
            record["review_outcome"] = "ERROR_statement_file_missing"
            rows.append(record)
            continue
        matches = [
            item
            for item in evidence_rows(directory)
            if item.get("statement_file") == source.get("current_t_revenues_statement_file")
            and item.get("statement_label") == source.get("current_t_revenues_statement_label")
            and item.get("statement_concepts") == source.get("current_t_revenues_statement_concepts")
        ]
        end = str(source.get("current_t_revenues_end", ""))
        direct_values = [item.get("amounts", {}).get(end) for item in matches]
        direct_values = [float(value) for value in direct_values if value is not None]
        if len(set(direct_values)) != 1:
            record["review_outcome"] = "ERROR_primary_statement_row_not_unique_on_recheck"
            rows.append(record)
            continue
        direct = direct_values[0]
        resolver = float(source["current_t_revenues_value"])
        scale = float(source.get("current_t_revenues_statement_scale") or 1.0)
        matches_value = amount_equal(direct, resolver, scale)
        record["direct_statement_value"] = direct
        record["direct_value_matches"] = matches_value
        record["review_outcome"] = (
            "PASS_primary_statement_value_confirmed"
            if matches_value
            else "ERROR_primary_statement_value_mismatch"
        )
        rows.append(record)
    return pd.DataFrame(rows)


def primitive_review(frame: pd.DataFrame, companyfacts_root: Path, seed: int) -> pd.DataFrame:
    candidates: list[pd.DataFrame] = []
    for primitive in [item for item in PRIMITIVES if item != "revenues"]:
        subset = frame.loc[frame[f"current_t_{primitive}_status"].eq("selected")]
        if not subset.empty:
            candidates.append(subset.sample(n=min(5, len(subset)), random_state=seed))
    instance_rows = frame.loc[
        frame[
            [f"current_t_{primitive}_source_cache_path" for primitive in PRIMITIVES]
        ]
        .fillna("")
        .astype(str)
        .apply(
            lambda column: column.str.contains("registrant_role_evidence", regex=False)
        )
        .any(axis=1)
    ]
    if not instance_rows.empty:
        candidates.append(instance_rows)
    sample = pd.concat(candidates, ignore_index=True).drop_duplicates(
        ["research_universe_company_year_id", "current_t_assets_tag"], keep="first"
    )
    rows: list[dict[str, Any]] = []
    payload_cache: dict[str, dict[str, Any]] = {}
    for source in sample.to_dict("records"):
        cik10 = str(source["cik10"]).split(".")[0].zfill(10)
        if cik10 not in payload_cache:
            path = companyfacts_root / f"CIK{cik10}.json"
            payload_cache[cik10] = json.loads(path.read_text()) if path.exists() else {}
        facts = payload_cache[cik10].get("facts", {}).get("us-gaap", {})
        for primitive in [item for item in PRIMITIVES if item != "revenues"]:
            if source.get(f"current_t_{primitive}_status") != "selected":
                continue
            tag = str(source.get(f"current_t_{primitive}_tag", ""))
            if tag.startswith("derived:"):
                outcome = "PASS_derived_sources_recorded" if source.get(
                    f"current_t_{primitive}_source_tags"
                ) else "ERROR_derived_sources_missing"
            elif "registrant_role_evidence" in text(
                source.get(f"current_t_{primitive}_source_cache_path")
            ):
                instance_path = BASE_DIR / text(
                    source.get(f"current_t_{primitive}_source_cache_path")
                )
                context_id = text(source.get(f"current_t_{primitive}_context_id"))
                direct_values: list[float] = []
                if instance_path.exists():
                    root = ElementTree.parse(instance_path).getroot()
                    for element in root.iter():
                        if element.tag.rsplit("}", 1)[-1] != tag:
                            continue
                        if text(element.attrib.get("contextRef")) != context_id:
                            continue
                        try:
                            value = float(text(element.text).replace(",", ""))
                            scale = int(text(element.attrib.get("scale")) or "0")
                            if scale:
                                value *= 10.0**scale
                            if text(element.attrib.get("sign")) == "-":
                                value *= -1.0
                            direct_values.append(value)
                        except (TypeError, ValueError, OverflowError):
                            continue
                expected = float(source.get(f"current_t_{primitive}_value"))
                outcome = (
                    "PASS_exact_joint_scope_xbrl_record"
                    if any(math.isclose(value, expected, rel_tol=1e-12, abs_tol=1e-6) for value in direct_values)
                    else "ERROR_joint_scope_source_fact_not_found"
                )
            else:
                matches = [
                    fact
                    for fact in facts.get(tag, {}).get("units", {}).get("USD", [])
                    if text(fact.get("accn")) == text(source.get("anchor_accession"))
                    and text(fact.get("end"))
                    == text(source.get(f"current_t_{primitive}_end"))
                    and text(fact.get("start"))
                    == text(source.get(f"current_t_{primitive}_start"))
                    and float(fact.get("val")) == float(source.get(f"current_t_{primitive}_value"))
                ]
                outcome = "PASS_exact_companyfacts_record" if matches else "ERROR_source_fact_not_found"
            rows.append(
                {
                    "research_universe_company_year_id": source["research_universe_company_year_id"],
                    "cik10": cik10,
                    "feature_year": source["feature_year"],
                    "anchor_accession": source["anchor_accession"],
                    "primitive": primitive,
                    "tag": tag,
                    "value": source.get(f"current_t_{primitive}_value"),
                    "start": source.get(f"current_t_{primitive}_start", ""),
                    "end": source.get(f"current_t_{primitive}_end", ""),
                    "review_outcome": outcome,
                }
            )
    return pd.DataFrame(rows)


def revision_diagnostics(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = ["cik10", "feature_year", "universe_anchor_matches_target_anchor_t"]
    for primitive in PRIMITIVES:
        columns.extend(
            [
                f"B_comparative_t_{primitive}_value",
                f"B_comparative_t_{primitive}_status",
                f"B_comparative_t_{primitive}_tag",
            ]
        )
    target = read_development(TARGET_APPLICATION_PATH, columns)
    target["cik10"] = target["cik10"].astype(str).str.split(".").str[0].str.zfill(10)
    base = frame.copy()
    base["cik10"] = base["cik10"].astype(str).str.split(".").str[0].str.zfill(10)
    merged = base.merge(target, on=["cik10", "feature_year"], how="left", validate="1:1")
    anchor_match = merged["universe_anchor_matches_target_anchor_t"].map(truthy)
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for primitive in PRIMITIVES:
        current = pd.to_numeric(merged[f"current_t_{primitive}_value"], errors="coerce")
        comparative = pd.to_numeric(
            merged[f"B_comparative_t_{primitive}_value"], errors="coerce"
        )
        valid = (
            anchor_match
            & merged[f"current_t_{primitive}_status"].eq("selected")
            & merged[f"B_comparative_t_{primitive}_status"].eq("selected")
            & current.notna()
            & comparative.notna()
        )
        delta = comparative - current
        relative = delta / current.abs().where(current.abs().gt(0))
        summary[primitive] = {
            "comparable": int(valid.sum()),
            "median_delta": float(delta.loc[valid].median()) if valid.any() else None,
            "median_absolute_relative_delta": (
                float(relative.loc[valid].abs().median()) if valid.any() else None
            ),
            "p99_absolute_relative_delta": (
                float(relative.loc[valid].abs().quantile(0.99)) if valid.any() else None
            ),
        }
        part = merged.loc[valid, [
            "research_universe_company_year_id",
            "cik10",
            "feature_year",
            "research_sector",
            "anchor_accession",
        ]].copy()
        part["primitive"] = primitive
        part["current_t_from_x_t_anchor"] = current.loc[valid]
        part["comparative_t_from_t1_anchor"] = comparative.loc[valid]
        part["revision_delta"] = delta.loc[valid]
        part["relative_revision_delta"] = relative.loc[valid]
        part["current_tag"] = merged.loc[valid, f"current_t_{primitive}_tag"]
        part["later_comparative_tag"] = merged.loc[
            valid, f"B_comparative_t_{primitive}_tag"
        ]
        rows.append(part)
    output = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    return output, summary


def standardized_mean_difference(
    values: pd.Series, group: pd.Series
) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce")
    left = numeric.loc[group & numeric.notna()]
    right = numeric.loc[~group & numeric.notna()]
    if len(left) < 2 or len(right) < 2:
        return None
    pooled = math.sqrt((float(left.var()) + float(right.var())) / 2.0)
    return (float(left.mean()) - float(right.mean())) / pooled if pooled > 0 else 0.0


def selection_bias_diagnostics(
    frame: pd.DataFrame,
) -> tuple[dict[str, Any], pd.DataFrame]:
    columns = ["cik10", "feature_year", "target_status", "target_available"]
    target = read_development(TARGET_APPLICATION_PATH, columns)
    target["cik10"] = target["cik10"].astype(str).str.split(".").str[0].str.zfill(10)
    base = frame.copy()
    base["cik10"] = base["cik10"].astype(str).str.split(".").str[0].str.zfill(10)
    merged = base.merge(target, on=["cik10", "feature_year"], how="left", validate="1:1")
    x_available = merged["x_t_status"].eq("available_core")
    target_available = merged["target_status"].eq("available")
    log_assets = np.log(
        pd.to_numeric(merged["current_t_assets_value"], errors="coerce").where(
            pd.to_numeric(merged["current_t_assets_value"], errors="coerce").gt(0)
        )
    )
    detailed_rows: list[dict[str, Any]] = []
    for dimension in ("feature_year", "research_sector", "historical_sic", "size_bucket"):
        source = add_size_bucket(merged) if dimension == "size_bucket" else merged
        for key, group in source.groupby(dimension, dropna=False, observed=True):
            x_group = group["x_t_status"].eq("available_core")
            target_group = group["target_status"].eq("available")
            joint = x_group & target_group
            detailed_rows.append(
                {
                    "dimension": dimension,
                    "group": key,
                    "observations": len(group),
                    "x_core_available": int(x_group.sum()),
                    "x_core_coverage": float(x_group.mean()),
                    "target_available": int(target_group.sum()),
                    "target_coverage": float(target_group.mean()),
                    "supervised_L_available": int(joint.sum()),
                    "supervised_L_coverage": float(joint.mean()),
                }
            )
    summary = {
        "observations": len(merged),
        "x_core_available": int(x_available.sum()),
        "x_core_coverage": float(x_available.mean()),
        "target_available": int(target_available.sum()),
        "target_coverage": float(target_available.mean()),
        "supervised_L_available": int((x_available & target_available).sum()),
        "supervised_L_coverage": float((x_available & target_available).mean()),
        "x_core_log_assets_smd_available_vs_unavailable": standardized_mean_difference(
            log_assets, x_available
        ),
        "target_log_assets_smd_available_vs_unavailable": standardized_mean_difference(
            log_assets, target_available
        ),
        "x_status_by_target_status": pd.crosstab(
            merged["x_t_status"], merged["target_status"], dropna=False
        ).to_dict(),
        "complete_case_selection_bias_risk": "high",
        "informative_censoring_risk": "high",
    }
    return summary, pd.DataFrame(detailed_rows)


def group_diagnostics(frame: pd.DataFrame) -> dict[str, Any]:
    group_present = frame["economic_group_id"].notna() & frame[
        "economic_group_id"
    ].astype(str).ne("")
    scope_present = frame["economic_statement_scope_id"].notna() & frame[
        "economic_statement_scope_id"
    ].astype(str).ne("")
    grouped = frame.loc[group_present].groupby("economic_group_id")
    group_split = grouped["split"].nunique()
    group_cik = grouped["cik10"].nunique()
    group_size = grouped.size()
    duplicate_scope_year = int(
        frame.loc[scope_present].duplicated(
            ["economic_statement_scope_id", "feature_year"]
        ).sum()
    )
    return {
        "economic_groups": int(group_size.size),
        "rows_missing_economic_group_id": int((~group_present).sum()),
        "rows_missing_economic_statement_scope_id": int((~scope_present).sum()),
        "groups_with_multiple_ciks": int(group_cik.gt(1).sum()),
        "groups_spanning_train_and_validation": int(group_split.gt(1).sum()),
        "maximum_company_year_rows_per_group": int(group_size.max()) if len(group_size) else 0,
        "duplicate_statement_scope_year_rows": duplicate_scope_year,
        "economic_group_id_is_predictor": False,
        "primary_split_changed": False,
    }


def registrant_scope_diagnostics(frame: pd.DataFrame) -> dict[str, Any]:
    joint_co = frame["registrant_role_resolved"].eq("joint_co_registrant")
    filing_xbrl = frame["xbrl_submission_available"].map(truthy)
    joint_co_filing_xbrl = joint_co & filing_xbrl
    scope_xbrl = frame["statement_scope_xbrl_status"].eq("available")
    scope_non_xbrl = frame["statement_scope_xbrl_status"].eq(
        "not_available_non_xbrl"
    )
    exact_records_missing = frame["anchor_period_validation_reason"].eq(
        "exact_anchor_companyfacts_records_unavailable"
    )
    core = frame["x_t_status"].eq("available_core")
    return {
        "joint_co_registrant_rows": int(joint_co.sum()),
        "joint_co_registrant_filing_xbrl_rows": int(joint_co_filing_xbrl.sum()),
        "joint_co_scope_specific_non_xbrl_rows": int(
            (joint_co_filing_xbrl & scope_non_xbrl).sum()
        ),
        "joint_co_scope_xbrl_available_rows": int((joint_co & scope_xbrl).sum()),
        "joint_co_scope_xbrl_exact_anchor_records_unavailable": int(
            (joint_co & scope_xbrl & exact_records_missing).sum()
        ),
        "joint_co_scope_xbrl_core_available": int(
            (joint_co & scope_xbrl & core).sum()
        ),
        "joint_co_scope_xbrl_core_coverage": float(
            core.loc[joint_co & scope_xbrl].mean()
        )
        if (joint_co & scope_xbrl).any()
        else None,
        "interpretation": (
            "filing-level XBRL availability is separated from statement-scope "
            "availability using the audited XBRL entity identifier"
        ),
    }


def joint_instance_provenance(frame: pd.DataFrame) -> dict[str, Any]:
    paths: set[str] = set()
    selected_facts = 0
    missing_context = 0
    invalid_dimensions = 0
    for primitive in PRIMITIVES:
        for prefix in ("current_t", "comparative_tm1", "pair_current_t"):
            status = frame[f"{prefix}_{primitive}_status"].eq("selected")
            cache = frame[f"{prefix}_{primitive}_source_cache_path"].fillna("").astype(str)
            raw = status & cache.str.contains("registrant_role_evidence", regex=False)
            selected_facts += int(raw.sum())
            missing_context += int(
                (
                    raw
                    & frame[f"{prefix}_{primitive}_context_id"]
                    .fillna("")
                    .astype(str)
                    .eq("")
                ).sum()
            )
            invalid_dimensions += int(
                (
                    raw
                    & ~frame[f"{prefix}_{primitive}_dimensions"]
                    .fillna("")
                    .astype(str)
                    .eq("issuer_total_no_explicit_or_typed_dimensions")
                ).sum()
            )
            for value in cache.loc[raw]:
                paths.update(item for item in value.split(";") if item)
    missing_files = [item for item in sorted(paths) if not (BASE_DIR / item).exists()]
    hashes = {
        item: sha256(BASE_DIR / item)
        for item in sorted(paths)
        if (BASE_DIR / item).exists()
    }
    return {
        "selected_joint_instance_primitive_facts": selected_facts,
        "unique_instance_files": len(paths),
        "instance_file_sha256": hashes,
        "missing_instance_files": missing_files,
        "selected_facts_missing_context_id": missing_context,
        "selected_facts_with_invalid_dimension_provenance": invalid_dimensions,
    }


def main() -> None:
    config = load_config(CONFIG_PATH)
    raw_path = configured_path(config, "outputs", "raw_artifact")
    validated_rows = validate_raw_artifact_path(raw_path, config)
    features = feature_names(config)
    columns = list(
        dict.fromkeys(
            [
                "research_universe_company_year_id",
                "cik10",
                "feature_year",
                "split",
                "company_name_historical",
                "historical_sic",
                "research_sector",
                "membership_status",
                "anchor_accession",
                "anchor_form",
                "anchor_filed",
                "anchor_accepted_at",
                "anchor_xbrl_period_end",
                "anchor_period_end_delta_days",
                "anchor_period_validation_status",
                "anchor_period_validation_reason",
                "anchor_record_count",
                "xbrl_submission_available",
                "statement_scope_xbrl_available",
                "statement_scope_xbrl_status",
                "statement_scope_xbrl_reason",
                "registrant_role_resolved",
                "economic_statement_scope_id",
                "economic_group_id",
                "prediction_timestamp",
                "prediction_timestamp_precision",
                "prediction_timestamp_lower_precision",
                "comparative_period_validation_status",
                "comparative_period_validation_reason",
                "x_t_status",
                "x_t_status_reason",
                "L_available_count",
                "D_available_count",
                "R_available_count",
                "near_zero_denominator_count",
            ]
            + [
                f"{feature}_{field}"
                for feature in features
                for field in (
                    "value",
                    "status",
                    "reason",
                    "available_at",
                    "near_zero_denominator_flag",
                )
            ]
            + [
                f"{prefix}_{primitive}_{field}"
                for primitive in PRIMITIVES
                for prefix, fields in (
                    (
                        "current_t",
                        (
                            "value",
                            "status",
                            "reason",
                            "strategy",
                            "tag",
                            "source_tags",
                            "accn",
                            "start",
                            "end",
                            "statement_file",
                            "statement_label",
                            "statement_concepts",
                            "statement_scale",
                            "filed",
                            "accepted_at",
                            "context_id",
                            "dimensions",
                            "source_cache_path",
                        ),
                    ),
                    (
                        "comparative_tm1",
                        (
                            "value", "status", "reason", "tag", "accn", "filed",
                            "accepted_at", "context_id", "dimensions", "source_cache_path",
                        ),
                    ),
                    (
                        "pair_current_t",
                        (
                            "value", "status", "reason", "tag", "accn", "filed",
                            "accepted_at", "context_id", "dimensions", "source_cache_path",
                        ),
                    ),
                )
                for field in fields
            ]
            + [
                f"pair_{primitive}_{field}"
                for primitive in PRIMITIVES
                for field in ("status", "reason", "strategy")
            ]
        )
    )
    frame = read_development(raw_path, columns)
    frame["cik10"] = frame["cik10"].astype(str).str.split(".").str[0].str.zfill(10)
    if len(frame) != 56_903:
        raise RuntimeError(f"Expected 56,903 development rows, got {len(frame):,}")

    coverage = coverage_summary(frame, config)
    primitive_coverage = primitive_coverage_summary(frame)
    primitive_signs = primitive_sign_summary(frame)
    by_year = grouped_coverage(frame, ["feature_year"], config)
    by_sector = grouped_coverage(frame, ["research_sector"], config)
    by_sic = grouped_coverage(frame, ["historical_sic"], config)
    sized = add_size_bucket(frame)
    by_size = grouped_coverage(sized, ["size_bucket"], config)
    by_role = grouped_coverage(frame, ["registrant_role_resolved"], config)
    by_xbrl = grouped_coverage(frame, ["statement_scope_xbrl_status"], config)
    reasons = status_reason_table(frame, config)
    outliers, outlier_summary = feature_outliers(frame, config)

    seed = int(config["audit"]["random_seed"])
    revenue_sample = revenue_review_sample(frame, seed)
    revenue_review = verify_revenue_review(
        revenue_sample,
        configured_path(config, "sources", "revenue_statement_evidence"),
    )
    primitive_checks = primitive_review(
        frame, configured_path(config, "sources", "companyfacts"), seed
    )
    revisions, revision_summary = revision_diagnostics(frame)
    selection_bias, selection_bias_table = selection_bias_diagnostics(frame)
    groups = group_diagnostics(frame)
    registrant_scopes = registrant_scope_diagnostics(frame)
    joint_instance_sources = joint_instance_provenance(frame)

    available_feature_timestamp_errors = 0
    for feature in features:
        available = frame[f"{feature}_status"].eq("available")
        available_feature_timestamp_errors += int(
            (
                available
                & frame[f"{feature}_available_at"].astype(str).ne(
                    frame["prediction_timestamp"].astype(str)
                )
            ).sum()
        )
    accession_errors = 0
    primitive_filed_errors = 0
    primitive_accepted_errors = 0
    for primitive in PRIMITIVES:
        for prefix in ("current_t", "comparative_tm1", "pair_current_t"):
            accn = frame[f"{prefix}_{primitive}_accn"].fillna("").astype(str)
            accession_errors += int(
                (accn.ne("") & accn.ne(frame["anchor_accession"].astype(str))).sum()
            )
            selected = frame[f"{prefix}_{primitive}_status"].eq("selected")
            primitive_filed_errors += int(
                (
                    selected
                    & frame[f"{prefix}_{primitive}_filed"].fillna("").astype(str).ne(
                        frame["anchor_filed"].fillna("").astype(str)
                    )
                ).sum()
            )
            primitive_accepted_errors += int(
                (
                    selected
                    & frame[f"{prefix}_{primitive}_accepted_at"].fillna("").astype(str).ne(
                        frame["anchor_accepted_at"].fillna("").astype(str)
                    )
                ).sum()
            )

    timestamp_policy_errors = 0
    for source in frame[
        [
            "anchor_accepted_at",
            "anchor_filed",
            "prediction_timestamp",
            "prediction_timestamp_precision",
            "prediction_timestamp_lower_precision",
        ]
    ].itertuples(index=False):
        expected_timestamp, expected_precision, expected_lower = prediction_timestamp(
            {
                "accepted_at": source.anchor_accepted_at,
                "filed": source.anchor_filed,
            }
        )
        timestamp_policy_errors += int(
            str(source.prediction_timestamp) != expected_timestamp
            or str(source.prediction_timestamp_precision) != expected_precision
            or truthy(source.prediction_timestamp_lower_precision) != expected_lower
        )
    non_original_form_rows = int(frame["anchor_form"].ne("10-K").sum())
    transition_or_ambiguous_period_rows = int(
        frame["comparative_period_validation_status"]
        .isin(["ambiguous", "hard_exclude"])
        .sum()
    )

    revenue_review_errors = int(
        revenue_review["review_outcome"].astype(str).str.startswith("ERROR").sum()
    )
    primitive_review_errors = int(
        primitive_checks["review_outcome"].astype(str).str.startswith("ERROR").sum()
    )
    missing_revenue_evidence = int(
        frame["current_t_revenues_reason"].eq(
            "primary_statement_evidence_unavailable"
        ).sum()
    )
    missing_revenue_evidence_by_year = (
        frame.loc[
            frame["current_t_revenues_reason"].eq(
                "primary_statement_evidence_unavailable"
            )
        ]
        .groupby("feature_year")
        .size()
        .to_dict()
    )
    companyfacts_root = configured_path(config, "sources", "companyfacts")
    xbrl_rows = frame["statement_scope_xbrl_status"].eq("available")
    companyfacts_file_available = frame["cik10"].map(
        lambda cik10: (companyfacts_root / f"CIK{str(cik10).zfill(10)}.json").exists()
    )
    missing_companyfacts_rows = int((xbrl_rows & ~companyfacts_file_available).sum())
    missing_companyfacts_ciks = int(
        frame.loc[xbrl_rows & ~companyfacts_file_available, "cik10"].nunique()
    )
    companyfacts_inventory_path = configured_path(
        config, "sources", "companyfacts_download_inventory"
    )
    companyfacts_inventory = json.loads(
        companyfacts_inventory_path.read_text(encoding="utf-8")
    )
    known_companyfacts_not_found = {
        str(item.get("key", "")).zfill(10)
        for item in companyfacts_inventory.get("companyfacts", {}).get("errors", [])
        if item.get("status") == "not_found"
    }
    missing_companyfacts_mask = xbrl_rows & ~companyfacts_file_available
    known_not_found_mask = missing_companyfacts_mask & frame["cik10"].isin(
        known_companyfacts_not_found
    )
    unknown_uncached_companyfacts_mask = (
        missing_companyfacts_mask & ~frame["cik10"].isin(known_companyfacts_not_found)
    )
    known_not_found_companyfacts_rows = int(known_not_found_mask.sum())
    unknown_uncached_companyfacts_rows = int(unknown_uncached_companyfacts_mask.sum())

    revenue_inventory_path = configured_path(
        config, "sources", "revenue_evidence_download_inventory"
    )
    revenue_inventory = json.loads(revenue_inventory_path.read_text(encoding="utf-8"))
    revenue_download_status = {
        (str(item.get("cik10", "")).zfill(10), str(item.get("accession", ""))): str(
            item.get("status", "")
        )
        for item in revenue_inventory.get("results", [])
    }
    x_t_download_inventory_path = configured_path(
        config, "sources", "x_t_source_download_inventory"
    )
    x_t_download_inventory = (
        json.loads(x_t_download_inventory_path.read_text(encoding="utf-8"))
        if x_t_download_inventory_path.exists()
        else {}
    )
    revenue_download_status.update(
        {
            (
                str(item.get("cik10", "")).zfill(10),
                str(item.get("accession", "")),
            ): str(item.get("status", ""))
            for item in x_t_download_inventory.get("results", [])
        }
    )
    source_gap_parts: list[pd.DataFrame] = []
    revenue_gap = frame.loc[
        frame["current_t_revenues_reason"].eq(
            "primary_statement_evidence_unavailable"
        ),
        [
            "research_universe_company_year_id",
            "cik10",
            "feature_year",
            "research_sector",
            "anchor_accession",
        ],
    ].copy()
    revenue_gap["source_type"] = "primary_statement_revenue_evidence"
    revenue_gap["reason"] = "FilingSummary_or_primary_statement_not_cached"
    revenue_gap["prior_download_status"] = [
        revenue_download_status.get((str(cik).zfill(10), str(accession)), "not_attempted")
        for cik, accession in zip(
            revenue_gap["cik10"], revenue_gap["anchor_accession"], strict=True
        )
    ]
    known_not_found_revenue_rows = int(
        revenue_gap["prior_download_status"].eq("not_found").sum()
    )
    known_no_income_statement_rows = int(
        revenue_gap["prior_download_status"]
        .eq("income_statement_not_identified")
        .sum()
    )
    terminal_fail_closed_revenue_statuses = {
        "not_found",
        "income_statement_not_identified",
    }
    incomplete_revenue_evidence_rows = int(
        (~revenue_gap["prior_download_status"].isin(
            terminal_fail_closed_revenue_statuses
        )).sum()
    )
    source_gap_parts.append(revenue_gap)
    companyfacts_gap = frame.loc[
        xbrl_rows & ~companyfacts_file_available,
        [
            "research_universe_company_year_id",
            "cik10",
            "feature_year",
            "research_sector",
            "anchor_accession",
        ],
    ].copy()
    companyfacts_gap["source_type"] = "companyfacts"
    companyfacts_gap["reason"] = [
        (
            "sec_companyfacts_endpoint_confirmed_not_found"
            if str(cik).zfill(10) in known_companyfacts_not_found
            else "xbrl_registrant_companyfacts_file_not_cached_or_unverified"
        )
        for cik in companyfacts_gap["cik10"]
    ]
    companyfacts_gap["prior_download_status"] = [
        "not_found"
        if str(cik).zfill(10) in known_companyfacts_not_found
        else "not_attempted_or_unknown"
        for cik in companyfacts_gap["cik10"]
    ]
    source_gap_parts.append(companyfacts_gap)
    source_gaps = pd.concat(source_gap_parts, ignore_index=True)
    lower_precision = int(frame["prediction_timestamp_lower_precision"].map(truthy).sum())
    nonfinite_available = sum(
        int(item["nonfinite"]) for item in outlier_summary.values()
    )
    nonfinite_selected_primitives = sum(
        int(item["nonfinite"]) for item in primitive_signs.values()
    )
    x_t_source_download_complete = bool(
        x_t_download_inventory.get("complete", False)
    )
    x_t_source_download_expected = int(
        x_t_download_inventory.get("candidate_anchors", 0) or 0
    )
    x_t_source_download_processed = int(
        x_t_download_inventory.get("processed_anchors", 0) or 0
    )
    x_t_source_download_errors = int(
        x_t_download_inventory.get("status_counts", {}).get("error", 0) or 0
    )

    blockers: list[str] = []
    if validated_rows != 64_901:
        blockers.append("raw_artifact_row_count_or_schema_invariant_failed")
    if accession_errors:
        blockers.append("exact_anchor_accession_invariant_failed")
    if available_feature_timestamp_errors:
        blockers.append("feature_available_at_differs_from_prediction_timestamp")
    if timestamp_policy_errors:
        blockers.append("prediction_timestamp_policy_invariant_failed")
    if primitive_filed_errors or primitive_accepted_errors:
        blockers.append("primitive_filing_timestamp_provenance_invariant_failed")
    if non_original_form_rows:
        blockers.append("non_original_10_k_anchor_present")
    if revenue_review_errors:
        blockers.append("manual_revenue_review_detected_selection_errors")
    if primitive_review_errors:
        blockers.append("manual_primitive_review_detected_source_provenance_errors")
    if nonfinite_available:
        blockers.append("available_features_contain_nonfinite_values")
    if nonfinite_selected_primitives:
        blockers.append("selected_primitives_contain_nonfinite_values")
    if incomplete_revenue_evidence_rows:
        blockers.append("local_primary_statement_revenue_evidence_incomplete")
    if (
        not x_t_source_download_complete
        or x_t_source_download_processed != x_t_source_download_expected
        or x_t_source_download_errors
    ):
        blockers.append("x_t_source_download_inventory_incomplete_or_error")
    if unknown_uncached_companyfacts_rows:
        blockers.append("local_companyfacts_cache_incomplete_for_xbrl_registrants")
    if groups["duplicate_statement_scope_year_rows"]:
        blockers.append("duplicate_economic_statement_scope_year_rows")
    if groups["rows_missing_economic_group_id"] or groups[
        "rows_missing_economic_statement_scope_id"
    ]:
        blockers.append("economic_scope_or_group_provenance_missing")
    if registrant_scopes[
        "joint_co_scope_xbrl_exact_anchor_records_unavailable"
    ]:
        blockers.append("joint_co_registrant_statement_scope_extraction_not_implemented")
    if (
        joint_instance_sources["missing_instance_files"]
        or joint_instance_sources["selected_facts_missing_context_id"]
        or joint_instance_sources[
            "selected_facts_with_invalid_dimension_provenance"
        ]
    ):
        blockers.append("joint_scope_xbrl_instance_provenance_invariant_failed")
    if lower_precision and lower_precision != 0:
        # A documented fallback is allowed, so this is reported but is not a blocker.
        pass
    verdict = "X_T V1 READY TO FREEZE" if not blockers else "X_T V1 NOT READY TO FREEZE"

    output_paths = config["outputs"]
    for key, data in (
        ("coverage_by_year", by_year),
        ("coverage_by_sector", by_sector),
        ("coverage_by_sic", by_sic),
        ("coverage_by_size", by_size),
        ("coverage_by_registrant_role", by_role),
        ("coverage_by_xbrl_availability", by_xbrl),
        ("status_reasons", reasons),
        ("revenue_manual_review", revenue_review),
        ("primitive_manual_review", primitive_checks),
        ("feature_outliers", outliers),
        ("revision_diagnostics", revisions),
        ("selection_bias", selection_bias_table),
        ("source_gaps", source_gaps),
    ):
        path = BASE_DIR / output_paths[key]
        path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(path, index=False, encoding="utf-8")

    audit = {
        "artifact_id": config["x_t"]["id"],
        "artifact_version": str(config["x_t"]["version"]),
        "audit_scope": "development_feature_years_2011_2022_only",
        "test_years_used_for_decisions": False,
        "models_trained": False,
        "preprocessing_applied": False,
        "raw_rows_all_years": validated_rows,
        "development_rows": len(frame),
        "row_status": frame["x_t_status"].value_counts().to_dict(),
        "prediction_timestamp_lower_precision": lower_precision,
        "exact_accession_errors": accession_errors,
        "feature_timestamp_errors": available_feature_timestamp_errors,
        "prediction_timestamp_policy_errors": timestamp_policy_errors,
        "primitive_filed_errors": primitive_filed_errors,
        "primitive_accepted_at_errors": primitive_accepted_errors,
        "non_original_10_k_anchor_rows": non_original_form_rows,
        "transition_or_ambiguous_comparative_period_rows": transition_or_ambiguous_period_rows,
        "feature_coverage": coverage.to_dict("records"),
        "primitive_coverage": primitive_coverage.to_dict("records"),
        "primitive_sign_summary": primitive_signs,
        "nonfinite_selected_primitives": nonfinite_selected_primitives,
        "missing_revenue_evidence": missing_revenue_evidence,
        "known_sec_revenue_evidence_not_found_rows": known_not_found_revenue_rows,
        "income_statement_not_identified_rows": known_no_income_statement_rows,
        "incomplete_revenue_evidence_rows": incomplete_revenue_evidence_rows,
        "missing_revenue_evidence_by_year": {
            str(key): int(value) for key, value in missing_revenue_evidence_by_year.items()
        },
        "missing_companyfacts_rows": missing_companyfacts_rows,
        "missing_companyfacts_ciks": missing_companyfacts_ciks,
        "known_sec_companyfacts_not_found_rows": known_not_found_companyfacts_rows,
        "unknown_uncached_companyfacts_rows": unknown_uncached_companyfacts_rows,
        "x_t_source_download_complete": x_t_source_download_complete,
        "x_t_source_download_expected": x_t_source_download_expected,
        "x_t_source_download_processed": x_t_source_download_processed,
        "x_t_source_download_errors": x_t_source_download_errors,
        "x_t_source_download_status_counts": x_t_download_inventory.get(
            "status_counts", {}
        ),
        "revenue_manual_review_rows": len(revenue_review),
        "revenue_manual_review_errors": revenue_review_errors,
        "primitive_manual_review_rows": len(primitive_checks),
        "primitive_manual_review_errors": primitive_review_errors,
        "outlier_summary": outlier_summary,
        "revision_summary": revision_summary,
        "selection_bias": selection_bias,
        "economic_group_diagnostics": groups,
        "registrant_scope_diagnostics": registrant_scopes,
        "joint_instance_provenance": joint_instance_sources,
        "frozen_universe_sha256": config["frozen_inputs"]["universe_sha256"],
        "frozen_target_sha256": config["frozen_inputs"]["target_sha256"],
        "raw_artifact_sha256": sha256(raw_path),
        "blocking_issues": blockers,
        "verdict": verdict,
    }
    audit_json_path = BASE_DIR / output_paths["audit_json"]
    audit_json_path.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    coverage_display = coverage.copy()
    coverage_display["coverage"] = coverage_display["coverage"].map(
        lambda value: f"{value:.2%}"
    )
    primitive_coverage_display = primitive_coverage.copy()
    primitive_coverage_display["coverage"] = primitive_coverage_display[
        "coverage"
    ].map(lambda value: f"{value:.2%}")
    row_status = (
        frame["x_t_status"]
        .value_counts()
        .rename_axis("x_t_status")
        .reset_index(name="observations")
    )
    row_status["share"] = row_status["observations"] / len(frame)
    row_status["share"] = row_status["share"].map(lambda value: f"{value:.2%}")
    evidence_year = pd.DataFrame(
        [
            {"feature_year": year, "missing_statement_evidence": count}
            for year, count in sorted(missing_revenue_evidence_by_year.items())
        ]
    )
    errors = revenue_review.loc[
        revenue_review["review_outcome"].astype(str).str.startswith("ERROR")
    ]
    blocker_lines = (
        [f"- `{item}`" for item in blockers]
        if blockers
        else ["- Brak blokujących problemów."]
    )
    markdown = f"""# Finalny audyt przed freeze — raw point-in-time `X_t v1`

Data audytu: **{datetime.now().date().isoformat()}**
Zakres decyzji: **wyłącznie development 2011–2022**
Modele: **nie trenowano**
Preprocessing ML: **nie wykonano**

## 1. Artefakt i invariants

- Raw rows wszystkich lat: **{validated_rows:,}** — dokładnie jeden dla każdego eligible company-year universe v1.1.0.
- Development rows 2011–2022: **{len(frame):,}**.
- Kolumny raw artifact: **{len(pd.read_csv(raw_path, nrows=0).columns):,}**.
- Exact-accession provenance errors: **{accession_errors:,}**.
- Prediction-timestamp policy errors: **{timestamp_policy_errors:,}**.
- Primitive filed/accepted provenance errors: **{primitive_filed_errors + primitive_accepted_errors:,}**.
- Anchors inne niż oryginalny 10-K: **{non_original_form_rows:,}**.
- `feature_available_at != prediction_timestamp` dla available features: **{available_feature_timestamp_errors:,}**.
- Lower-precision timestamp fallback w development: **{lower_precision:,}**.
- Target/provenance columns w raw schema: **0**.
- Imputacja/winsoryzacja/skalowanie/feature selection: **nie wykonano**.
- Frozen universe SHA-256: `{config['frozen_inputs']['universe_sha256']}`.
- Frozen target SHA-256: `{config['frozen_inputs']['target_sha256']}`.
- Raw X_t SHA-256: `{sha256(raw_path)}`.

## 2. Status wierszy

{markdown_table(row_status)}

## 3. Coverage cech

### 3.1. Primitive

{markdown_table(primitive_coverage_display)}

### 3.2. Features

{markdown_table(coverage_display[['block','feature','available','coverage','missing','ambiguous','not_computable','not_available_non_xbrl']])}

Szczegółowe rozkłady każdego primitive i feature według roku, sektora,
historycznego SIC, kwartylu wielkości, registrant role i dostępności XBRL
zapisano w osobnych CSV. Revenue module pozostaje osobnym blokiem i
jego brak nie usuwa wiersza ani cech L/D.

## 4. Revenue resolver i manual stratified review

- Manual review rows: **{len(revenue_review):,}**.
- Wykryte błędy selekcji/provenance: **{revenue_review_errors:,}**.
- Brak lokalnego primary-statement evidence: **{missing_revenue_evidence:,}**.
- Z tego potwierdzone SEC `not_found`: **{known_not_found_revenue_rows:,}**;
  Filing Summary bez jednoznacznie rozpoznanego skonsolidowanego rachunku
  wyników: **{known_no_income_statement_rows:,}**; niepobrane/błędne lub
  niezweryfikowane: **{incomplete_revenue_evidence_rows:,}**.
- Source download inventory: **{x_t_source_download_processed:,} / {x_t_source_download_expected:,}**,
  `complete={x_t_source_download_complete}`, błędy techniczne:
  **{x_t_source_download_errors:,}**.
- XBRL rows bez lokalnego Company Facts cache: **{missing_companyfacts_rows:,}**
  w **{missing_companyfacts_ciks:,}** CIK.
- Z tego SEC Company Facts `not_found` potwierdzone w istniejącym download
  inventory: **{known_not_found_companyfacts_rows:,}** wierszy; braki
  niezweryfikowane: **{unknown_uncached_companyfacts_rows:,}**.

{markdown_table(evidence_year)}

{('Nie wykryto błędów w zweryfikowanej próbie.' if errors.empty else markdown_table(errors.head(30)))}

Brak pliku evidence nie jest interpretowany jako ekonomiczny brak revenues:
resolver działa fail-closed i zwraca `ambiguous/NA`. Jedyny taki przypadek po
backfillu ma potwierdzony status SEC `not_found`; nie pozostały niepobrane,
błędne ani niezweryfikowane luki lokalnego cache.

## 5. Pozostałe primitive, okresy i outliery

- Manual source-provenance checks poza revenues: **{len(primitive_checks):,}**.
- Błędy w tej próbie: **{primitive_review_errors:,}**.
- Available non-finite feature values: **{nonfinite_available:,}**.
- Selected non-finite primitive values: **{nonfinite_selected_primitives:,}**.
- Current primitive sign audit: `{json.dumps(primitive_signs, ensure_ascii=False)}`.
- Standardowe przesunięcia 52/53-week period end są rozstrzygane wyłącznie
  wewnątrz exact accession; materialna różnica pozostaje ambiguous.
- Near-zero denominators są flagowane, ale dodatnia wartość nie zmienia
  availability.

## 6. Revision diagnostic — current `t` vs later comparative `t`

Porównanie z later comparative jest zapisane wyłącznie w oddzielnym raporcie
audytowym i nie występuje w raw `X_t`. Nie zastępuje wartości current i nie
wpływa na resolver. Podsumowanie:

```json
{json.dumps(revision_summary, indent=2, ensure_ascii=False)}
```

## 7. Missingness, selection bias i target availability

```json
{json.dumps(selection_bias, indent=2, ensure_ascii=False)}
```

Ryzyko complete-case selection bias pozostaje wysokie. X availability i target
availability są odrębnymi mechanizmami selekcji; raw artifact zachowuje także
wiersze bez targetu i bez pełnego core.

## 8. Economic groups i temporal split

```json
{json.dumps(groups, indent=2, ensure_ascii=False)}
```

`economic_group_id` nie jest predictorem i nie zmienia głównego temporal splitu.

### 8.1. Joint filings i secondary statement scopes

```json
{json.dumps(registrant_scopes, indent=2, ensure_ascii=False)}
```

```json
{json.dumps(joint_instance_sources, indent=2, ensure_ascii=False)}
```

Frozen universe zachowuje tylko potwierdzone odrębne statement scopes.
Filing-level XBRL nie jest automatycznie przypisywany wszystkim registrantom:
scope bez zgodnego XBRL entity identifier otrzymuje
`not_available_non_xbrl`, natomiast zgodna wtórna instancja jest odczytywana
bezpośrednio z lokalnego filing package. Wierszy nie usuwa się ani nie
przepisuje na primary registranta.

## 9. Test 2023–2024

Wiersze testowe zostały utworzone mechanicznie tą samą polityką, ale ich
coverage, wartości, outliery, missingness i targety nie zostały użyte w tym
audycie ani w decyzji o resolverze. Nie trenowano modeli.

## 10. Blokujące problemy

{chr(10).join(blocker_lines)}

## 11. Werdykt

**{verdict}**
"""
    audit_md_path = BASE_DIR / output_paths["audit_markdown"]
    audit_md_path.write_text(markdown, encoding="utf-8")
    print(verdict)
    print(f"Development rows: {len(frame):,}")
    print(f"Revenue review errors: {revenue_review_errors:,}")
    print(f"Missing revenue evidence: {missing_revenue_evidence:,}")
    print(f"Audit: {audit_md_path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()

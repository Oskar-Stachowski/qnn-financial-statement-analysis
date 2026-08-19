"""Versioned train-only target/application correction for resolver v1.1.0."""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.data import primitive_resolver_v1_1 as resolver_v1_1
from src.data import target_candidate_v2_pit as target_v1
from src.data import x_t_pit as x_v1
from src.data.x_t_pit_v1_1 import (
    BASE_DIR,
    CONFIG_PATH,
    load_patch_config,
    restricted_companyfacts_root,
    sha256,
)


TARGET_PROVENANCE_FIELDS = (
    "value",
    "status",
    "reason",
    "strategy",
    "tag",
    "source_tags",
    "source_values",
    "source_accessions",
    "source_starts",
    "source_ends",
    "accn",
    "start",
    "end",
    "duration_days",
    "filed",
    "accepted_at",
    "role",
    "document_fiscal_year_focus",
    "document_fiscal_period_focus",
    "document_period_end_date",
    "frame",
    "candidate_count",
    "statement_file",
    "statement_short_name",
    "statement_long_name",
    "statement_role_uri",
    "statement_label",
    "statement_concepts",
    "statement_row_class",
    "statement_priority",
    "statement_scale",
    "statement_scale_label",
    "statement_candidate_count",
)


def _reasons(value: Any) -> list[str]:
    if value is None or pd.isna(value):
        return []
    return [item for item in str(value).split(";") if item]


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    return float(value)


def load_single_period_corrections(
    base_x_path: Path,
    corrected_x_path: Path,
) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[str, dict[str, Any]]]:
    columns = [
        "research_universe_company_year_id",
        "cik10",
        "feature_year",
        "anchor_accession",
    ]
    for primitive in x_v1.PRIMITIVES:
        columns.extend(
            f"current_t_{primitive}_{field}" for field in x_v1.PROVENANCE_FIELDS
        )
    base = pd.read_csv(
        base_x_path,
        usecols=columns,
        dtype={"cik10": str},
        low_memory=False,
    )
    corrected = pd.read_csv(
        corrected_x_path,
        usecols=columns,
        dtype={"cik10": str},
        low_memory=False,
    )
    if not base[
        ["research_universe_company_year_id", "feature_year"]
    ].fillna("").astype(str).equals(
        corrected[
            ["research_universe_company_year_id", "feature_year"]
        ].fillna("").astype(str)
    ):
        raise RuntimeError("X_t corrections are not aligned")
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    by_id: dict[str, dict[str, Any]] = {}
    for index in base.index:
        primitive_updates: dict[str, dict[str, Any]] = {}
        for primitive in x_v1.PRIMITIVES:
            if not (
                str(base.at[index, f"current_t_{primitive}_status"]) == "selected"
                and str(corrected.at[index, f"current_t_{primitive}_status"])
                == "ambiguous"
                and str(corrected.at[index, f"current_t_{primitive}_reason"])
                == "higher_priority_context_ambiguous"
            ):
                continue
            primitive_updates[primitive] = {
                "expected_old_status": str(
                    base.at[index, f"current_t_{primitive}_status"]
                ),
                "expected_old_strategy": str(
                    base.at[index, f"current_t_{primitive}_strategy"]
                ),
                "expected_old_tag": str(
                    base.at[index, f"current_t_{primitive}_tag"]
                ),
                "new": {
                    field: corrected.at[index, f"current_t_{primitive}_{field}"]
                    for field in TARGET_PROVENANCE_FIELDS
                },
            }
        if not primitive_updates:
            continue
        cik10 = str(base.at[index, "cik10"]).zfill(10)
        year = int(base.at[index, "feature_year"])
        item = {
            "research_universe_company_year_id": str(
                base.at[index, "research_universe_company_year_id"]
            ),
            "cik10": cik10,
            "feature_year": year,
            "anchor_accession": str(base.at[index, "anchor_accession"]),
            "primitives": primitive_updates,
        }
        by_key[(cik10, year)] = item
        by_id[item["research_universe_company_year_id"]] = item
    return by_key, by_id


def recompute_target_diagnostics(
    original: dict[str, Any],
    corrected: dict[str, Any],
    config: dict[str, Any],
    scope: target_v1.Scope,
) -> None:
    old_a = {
        primitive: _optional_float(original.get(f"A_current_t_{primitive}_value"))
        for primitive in target_v1.PRIMITIVES
    }
    new_a = {
        primitive: _optional_float(corrected.get(f"A_current_t_{primitive}_value"))
        for primitive in target_v1.PRIMITIVES
    }
    comparative = {
        primitive: _optional_float(corrected.get(f"B_comparative_t_{primitive}_value"))
        for primitive in target_v1.PRIMITIVES
    }
    current = {
        primitive: _optional_float(corrected.get(f"B_current_t1_{primitive}_value"))
        for primitive in target_v1.PRIMITIVES
    }
    old_continuity, _ = target_v1.continuity_ambiguity_screen(
        old_a, comparative, config, scope.minimum_denominator_usd
    )
    new_continuity, new_components = target_v1.continuity_ambiguity_screen(
        new_a, comparative, config, scope.minimum_denominator_usd
    )
    old_sign = set(
        target_v1.semantic_vintage_ambiguity_screen(old_a, comparative, config)
    )
    new_sign = set(
        target_v1.semantic_vintage_ambiguity_screen(new_a, comparative, config)
    )
    reasons = _reasons(original.get("ambiguous_reasons"))
    continuity_reason = "reporting_entity_continuity_material_rebasing_unresolved"
    if old_continuity and not new_continuity:
        reasons = [reason for reason in reasons if reason != continuity_reason]
    reasons = [reason for reason in reasons if reason not in (old_sign - new_sign)]
    if (
        new_continuity
        and continuity_reason not in reasons
        and not str(corrected.get("reporting_entity_exclusion_evidence", "") or "")
    ):
        reasons.append(continuity_reason)
    reasons.extend(reason for reason in sorted(new_sign) if reason not in reasons)
    corrected["reporting_entity_material_revision_components"] = target_v1.semicolon(
        new_components
    )
    corrected["semantic_vintage_ambiguity_reasons"] = target_v1.semicolon(new_sign)

    signals, score, label, base_metrics, next_metrics = target_v1.target_candidate_v2(
        comparative, current, scope.minimum_denominator_usd
    )
    corrected.update(signals)
    for metric, value in base_metrics.items():
        corrected[f"B_comparative_t_{metric}_metric"] = value
    for metric, value in next_metrics.items():
        corrected[f"B_current_t1_{metric}_metric"] = value
    hard_reasons = _reasons(corrected.get("hard_exclude_reasons"))
    if hard_reasons:
        status = "hard_exclude"
        score = None
        label = None
    elif reasons:
        status = "ambiguous"
        score = None
        label = None
    elif label is None:
        status = "missing"
    else:
        status = "available"
    corrected["ambiguous_flag"] = bool(reasons)
    corrected["ambiguous_reasons"] = target_v1.semicolon(reasons)
    corrected["target_status"] = status
    corrected["deterioration_score_1y"] = score
    corrected["target_candidate_v2"] = label
    if "target_candidate_v2_pit_b" in corrected:
        corrected["target_candidate_v2_pit_b"] = label
    if "target_available" in corrected:
        corrected["target_available"] = status == "available"


def patch_target_csv(
    source_path: Path,
    output_path: Path,
    corrections: dict[Any, dict[str, Any]],
    *,
    key_mode: str,
    config: dict[str, Any],
    scope: target_v1.Scope,
    application: bool,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    first_write = True
    rows = 0
    changed_rows = 0
    changed_cells = 0
    status_changes: list[dict[str, str]] = []
    label_changes = 0
    for frame in pd.read_csv(
        source_path,
        dtype={"cik10": str},
        chunksize=500,
        low_memory=False,
    ):
        frame["cik10"] = frame["cik10"].astype(str).str.zfill(10)
        for column in frame.columns:
            if column.startswith("A_current_t_") or column in {
                "ambiguous_reasons",
                "semantic_vintage_ambiguity_reasons",
                "reporting_entity_material_revision_components",
                "target_status",
                "target_candidate_v2",
                "target_candidate_v2_pit_b",
            }:
                frame[column] = frame[column].astype(object)
        for index in frame.index:
            if key_mode == "id":
                key: Any = str(frame.at[index, "research_universe_company_year_id"])
            else:
                key = (str(frame.at[index, "cik10"]), int(frame.at[index, "feature_year"]))
            correction = corrections.get(key)
            if correction is None:
                continue
            if str(frame.at[index, "anchor_t_accn"]) != correction["anchor_accession"]:
                continue
            if application and (
                str(frame.at[index, "target_status"]) == "not_computable"
                or not bool(frame.at[index, "universe_anchor_matches_target_anchor_t"])
            ):
                continue
            original = frame.loc[index].to_dict()
            corrected = dict(original)
            applied_primitive = False
            for primitive, primitive_correction in correction["primitives"].items():
                if not (
                    str(corrected.get(f"A_current_t_{primitive}_status", ""))
                    == primitive_correction["expected_old_status"]
                    and str(corrected.get(f"A_current_t_{primitive}_strategy", ""))
                    == primitive_correction["expected_old_strategy"]
                    and str(corrected.get(f"A_current_t_{primitive}_tag", ""))
                    == primitive_correction["expected_old_tag"]
                ):
                    continue
                selection = primitive_correction["new"]
                for field in TARGET_PROVENANCE_FIELDS:
                    column = f"A_current_t_{primitive}_{field}"
                    if column in corrected:
                        value = selection[field]
                        corrected[column] = "" if pd.isna(value) else value
                changed_cells += 1
                applied_primitive = True
            if not applied_primitive:
                continue
            recompute_target_diagnostics(original, corrected, config, scope)
            old_status = str(original.get("target_status", ""))
            new_status = str(corrected.get("target_status", ""))
            if old_status != new_status:
                status_changes.append(
                    {
                        "key": str(key),
                        "old_status": old_status,
                        "new_status": new_status,
                    }
                )
            old_label = original.get("target_candidate_v2_pit_b", original.get("target_candidate_v2"))
            new_label = corrected.get("target_candidate_v2_pit_b", corrected.get("target_candidate_v2"))
            old_label_numeric = _optional_float(old_label)
            new_label_numeric = _optional_float(new_label)
            if not (
                old_label_numeric is None
                and new_label_numeric is None
            ) and old_label_numeric != new_label_numeric:
                label_changes += 1
            for column, value in corrected.items():
                if column in frame.columns:
                    frame.at[index, column] = value
            changed_rows += 1
        if application:
            frame["target_definition_version"] = "1.1.0"
            if "target_resolver_version" not in frame:
                frame = pd.concat(
                    [
                        frame,
                        pd.Series(
                            "1.1.0",
                            index=frame.index,
                            name="target_resolver_version",
                        ),
                    ],
                    axis=1,
                )
            else:
                frame["target_resolver_version"] = "1.1.0"
            if "target_application_source" in frame:
                frame["target_application_source"] = (
                    frame["target_application_source"]
                    .astype(str)
                    .str.replace("v1.0.0", "v1.1.0", regex=False)
                )
        frame.to_csv(
            temporary_path,
            mode="w" if first_write else "a",
            header=first_write,
            index=False,
            encoding="utf-8",
            lineterminator="\n",
            float_format="%.17g",
        )
        first_write = False
        rows += len(frame)
    temporary_path.replace(output_path)
    return {
        "rows": rows,
        "changed_rows": changed_rows,
        "changed_primitive_cells": changed_cells,
        "target_status_changes": status_changes,
        "target_label_changes": label_changes,
        "sha256": sha256(output_path),
    }


def audit_target_cross_tag_pairs(target_train_path: Path) -> dict[str, Any]:
    config = target_v1.load_config()
    scope = target_v1.parse_scope(config)
    columns = [
        "cik10",
        "feature_year",
        "anchor_t_accn",
        "anchor_t1_accn",
        "anchor_t_document_period_end_date",
        "anchor_t1_document_period_end_date",
    ]
    for primitive in ("assets", "liabilities"):
        columns.extend(
            [
                f"B_{primitive}_status",
                f"B_{primitive}_reason",
                f"B_{primitive}_strategy",
            ]
        )
    frame = pd.read_csv(
        target_train_path,
        usecols=columns,
        dtype={"cik10": str},
        low_memory=False,
    ).fillna("")
    frame["cik10"] = frame["cik10"].astype(str).str.zfill(10)
    candidates: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for row in frame.to_dict("records"):
        for primitive in ("assets", "liabilities"):
            if not (
                row[f"B_{primitive}_status"] == "selected"
                and row[f"B_{primitive}_reason"]
                == "controlled_cross_tag_equivalence"
            ):
                continue
            accession = str(row["anchor_t1_accn"])
            cik10 = str(row["cik10"])
            facts_root = restricted_companyfacts_root(
                BASE_DIR / "data/raw/companyfacts" / f"CIK{cik10}.json",
                allowed_accessions={accession},
                required_tags=target_v1.required_tags(config),
            )
            records = x_v1.records_by_accession(facts_root, config, scope).get(
                accession, []
            )
            if not records:
                raise RuntimeError(f"Cross-tag target evidence unavailable: {cik10}")
            anchor_t1 = {
                "accn": accession,
                "records": records,
                "report_end": date.fromisoformat(
                    str(row["anchor_t1_document_period_end_date"])
                ),
            }
            anchor_t = {
                "report_end": date.fromisoformat(
                    str(row["anchor_t_document_period_end_date"])
                )
            }
            result = resolver_v1_1.select_primitive_pair(
                primitive,
                config["primitive_concepts"][primitive],
                anchor_t1,
                anchor_t,
                None,
                scope,
            )
            item = {
                "cik10": cik10,
                "feature_year": int(row["feature_year"]),
                "primitive": primitive,
                "old_strategy": row[f"B_{primitive}_strategy"],
                "new_status": result.get("status"),
                "new_reason": result.get("reason"),
                "new_strategy": result.get("strategy", ""),
            }
            candidates.append(item)
            if (
                result.get("status") == "ambiguous"
                and result.get("reason") == "higher_priority_context_ambiguous"
            ):
                blocked.append(item)
    return {
        "selected_cross_tag_pairs_checked": len(candidates),
        "newly_blocked_pairs": len(blocked),
        "candidates": candidates,
        "blocked": blocked,
    }


def build(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    patch_config = load_patch_config(config_path)
    base_x = BASE_DIR / str(patch_config["inputs"]["train_projection"])
    corrected_x = BASE_DIR / str(patch_config["outputs"]["raw_train_artifact"])
    target_v1_path = BASE_DIR / str(
        patch_config["inputs"]["frozen_target_train_projection"]
    )
    application_v1_path = BASE_DIR / str(
        patch_config["inputs"]["target_application_train_projection"]
    )
    corrections_by_key, corrections_by_id = load_single_period_corrections(
        base_x, corrected_x
    )
    cross_tag = audit_target_cross_tag_pairs(target_v1_path)
    if cross_tag["newly_blocked_pairs"]:
        raise RuntimeError(
            "Target pair resolver is affected; pair/label rebuild must precede freeze"
        )
    config = target_v1.load_config()
    scope = target_v1.parse_scope(config)
    target_output = BASE_DIR / str(patch_config["outputs"]["target_train_artifact"])
    application_output = BASE_DIR / str(
        patch_config["outputs"]["target_application_train_artifact"]
    )
    target_result = patch_target_csv(
        target_v1_path,
        target_output,
        corrections_by_key,
        key_mode="cik_year",
        config=config,
        scope=scope,
        application=False,
    )
    application_result = patch_target_csv(
        application_v1_path,
        application_output,
        corrections_by_id,
        key_mode="id",
        config=config,
        scope=scope,
        application=True,
    )
    result = {
        "artifact_id": "target_candidate_v2_pit_b_resolver_correction",
        "artifact_version": "1.1.0",
        "scope": "train_2011_2020_only",
        "historical_v1_modified": False,
        "target_definition_changed": False,
        "target_labels_changed": bool(
            target_result["target_label_changes"]
            or application_result["target_label_changes"]
        ),
        "cross_tag_pair_audit": cross_tag,
        "target_train": target_result,
        "target_application_train": application_result,
        "models_trained": False,
        "protected_feature_years_opened": False,
    }
    report_path = BASE_DIR / "data/reports/target_resolver_v1_1_0_train_build.json"
    report_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, ensure_ascii=False, default=str))

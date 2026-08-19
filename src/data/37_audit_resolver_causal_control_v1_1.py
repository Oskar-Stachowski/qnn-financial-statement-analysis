"""Same-source causal control for the resolver v1.1.0 train correction.

For every primitive cell admitted to the correction, replay the frozen v1
resolver on the same accession-restricted source records.  The correction is
causally isolated only when that control reproduces the exact frozen selection
while the v1.1 candidate is ambiguous because of the new priority barrier.
Only the physical 2011--2020 projection is read.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date
import json
import math
from pathlib import Path
from types import FunctionType
from typing import Any

import pandas as pd

from src.data import target_candidate_v2_pit as target_v1
from src.data import x_t_pit as x_v1
from src.data import x_t_pit_v1_1 as patch


BASE_DIR = Path(__file__).resolve().parents[2]
REPORT_PATH = BASE_DIR / "data/reports/resolver_x_t_v1_1_0_causal_control.json"
COMPARE_FIELDS = ("status", "strategy", "tag", "accn")


def _same_numeric(left: Any, right: Any) -> bool:
    left_value = pd.to_numeric(pd.Series([left]), errors="coerce").iloc[0]
    right_value = pd.to_numeric(pd.Series([right]), errors="coerce").iloc[0]
    if pd.isna(left_value) and pd.isna(right_value):
        return True
    return bool(
        pd.notna(left_value)
        and pd.notna(right_value)
        and math.isclose(
            float(left_value),
            float(right_value),
            rel_tol=1e-12,
            abs_tol=1e-9,
        )
    )


def _control_processor() -> Any:
    globals_v1 = dict(x_v1.process_eligible_row.__globals__)
    globals_v1["apply_negative_sign_review"] = (
        patch._apply_reconstructed_negative_review
    )
    processor = FunctionType(
        x_v1.process_eligible_row.__code__,
        globals_v1,
        name="process_eligible_row_same_source_v1_control",
        argdefs=x_v1.process_eligible_row.__defaults__,
        closure=x_v1.process_eligible_row.__closure__,
    )
    processor.__kwdefaults__ = x_v1.process_eligible_row.__kwdefaults__
    return processor


def audit() -> dict[str, Any]:
    patch_config = patch.load_patch_config()
    base_path = BASE_DIR / str(patch_config["inputs"]["train_projection"])
    candidate_path = BASE_DIR / str(
        patch_config["outputs"]["source_rebuild_candidate"]
    )

    columns = list(x_v1.METADATA_COLUMNS)
    for primitive in patch._REVIEWED_PRIMITIVES:
        columns.extend(
            f"current_t_{primitive}_{field}"
            for field in ("reason", "tag", "strategy", "accn")
        )
    for primitive in x_v1.PRIMITIVES:
        columns.extend(
            f"current_t_{primitive}_{field}"
            for field in (*COMPARE_FIELDS, "reason", "value")
        )
    base = pd.read_csv(
        base_path,
        usecols=list(dict.fromkeys(columns)),
        dtype={"cik10": str},
        low_memory=False,
    )
    candidate_columns = ["research_universe_company_year_id", "feature_year"]
    for primitive in x_v1.PRIMITIVES:
        candidate_columns.extend(
            [
                f"current_t_{primitive}_status",
                f"current_t_{primitive}_reason",
            ]
        )
    candidate = pd.read_csv(
        candidate_path,
        usecols=candidate_columns,
        low_memory=False,
    )
    ids = base["research_universe_company_year_id"].astype(str)
    if not ids.equals(candidate["research_universe_company_year_id"].astype(str)):
        raise RuntimeError("Causal-control inputs are not aligned")
    for name, frame in (("base", base), ("candidate", candidate)):
        years = pd.to_numeric(frame["feature_year"], errors="raise").astype(int)
        if not years.between(2011, 2020).all():
            raise RuntimeError(f"{name} causal-control input is not train-only")

    changes: dict[str, set[str]] = defaultdict(set)
    primitive_counts: Counter[str] = Counter()
    for primitive in x_v1.PRIMITIVES:
        mask = (
            base[f"current_t_{primitive}_status"].eq("selected")
            & candidate[f"current_t_{primitive}_status"].eq("ambiguous")
            & candidate[f"current_t_{primitive}_reason"].eq(
                "higher_priority_context_ambiguous"
            )
        )
        primitive_counts[primitive] = int(mask.sum())
        for company_year_id in ids[mask]:
            changes[str(company_year_id)].add(primitive)

    config = patch.resolved_v1_1_config(patch_config)
    semantic_config = target_v1.load_config(
        BASE_DIR / str(patch_config["inputs"]["primitive_policy"])
    )
    base_scope = target_v1.parse_scope(semantic_config)
    pit = config["point_in_time"]
    scope = replace(
        base_scope,
        feature_year_start=2011,
        feature_year_end=2020,
        annual_period_min_days=int(pit["annual_period_min_days"]),
        annual_period_max_days=int(pit["annual_period_max_days"]),
        period_start_tolerance_days=int(pit["period_start_tolerance_days"]),
        minimum_denominator_usd=0.0,
    )
    sources = patch.source_rows_from_projection(base)
    period_ends = {
        (str(row["cik10"]).zfill(10), int(row["feature_year"])): date.fromisoformat(
            str(row["period_end"])
        )
        for row in sources
        if str(row.get("period_end", ""))
    }
    source_by_id = {
        str(row["research_universe_company_year_id"]): row for row in sources
    }
    base_by_id = base.set_index("research_universe_company_year_id")
    negative_reviews = patch.reconstructed_negative_reviews(base)
    processor = _control_processor()

    by_cik: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for company_year_id in changes:
        source = source_by_id[company_year_id]
        by_cik[str(source["cik10"]).zfill(10)].append(source)

    mismatches: list[dict[str, Any]] = []
    checked_cells = 0
    for cik10, company_rows in sorted(by_cik.items()):
        allowed_accessions = {
            str(source.get("accession", "")) for source in company_rows
        }
        companyfacts_path = (
            BASE_DIR
            / str(patch_config["inputs"]["companyfacts"])
            / f"CIK{cik10}.json"
        )
        facts_root = patch.restricted_companyfacts_root(
            companyfacts_path,
            allowed_accessions=allowed_accessions,
            required_tags=target_v1.required_tags(semantic_config),
        )
        accession_records = x_v1.records_by_accession(
            facts_root, semantic_config, scope
        )
        for source in company_rows:
            accession = str(source.get("accession", ""))
            if accession not in accession_records:
                instance_records = x_v1.scope_xbrl_instance_records(
                    source, semantic_config, scope
                )
                if instance_records:
                    accession_records[accession].extend(instance_records)
            control = processor(
                source,
                config=config,
                semantic_config=semantic_config,
                scope=scope,
                accession_records=accession_records,
                period_ends=period_ends,
                companyfacts_relative_path=str(
                    companyfacts_path.relative_to(BASE_DIR)
                ),
                evidence_root=(
                    BASE_DIR
                    / str(patch_config["inputs"]["revenue_statement_evidence"])
                ),
                negative_sign_review=negative_reviews,
            )
            company_year_id = str(source["research_universe_company_year_id"])
            frozen = base_by_id.loc[company_year_id]
            for primitive in sorted(changes[company_year_id]):
                checked_cells += 1
                differences: dict[str, dict[str, Any]] = {}
                for field in COMPARE_FIELDS:
                    frozen_value = frozen[f"current_t_{primitive}_{field}"]
                    control_value = control[f"current_t_{primitive}_{field}"]
                    left = "" if pd.isna(frozen_value) else str(frozen_value)
                    right = "" if pd.isna(control_value) else str(control_value)
                    if left != right:
                        differences[field] = {"frozen": left, "control": right}
                value_field = f"current_t_{primitive}_value"
                if not _same_numeric(frozen[value_field], control[value_field]):
                    differences["value"] = {
                        "frozen": frozen[value_field],
                        "control": control[value_field],
                    }
                if differences:
                    mismatches.append(
                        {
                            "research_universe_company_year_id": company_year_id,
                            "primitive": primitive,
                            "differences": differences,
                        }
                    )

    report = {
        "audit_id": "resolver_x_t_v1_1_0_same_source_causal_control",
        "scope": "train_2011_2020_only",
        "data_access_policy": "data_access_policy_v1.1.0",
        "protected_feature_years_opened": False,
        "models_trained": False,
        "frozen_v1_train_projection": str(base_path.relative_to(BASE_DIR)),
        "frozen_v1_train_projection_sha256": patch.sha256(base_path),
        "v1_1_source_candidate": str(candidate_path.relative_to(BASE_DIR)),
        "v1_1_source_candidate_sha256": patch.sha256(candidate_path),
        "changed_company_years_checked": len(changes),
        "primitive_cells_checked": checked_cells,
        "primitive_cells_by_name": {
            key: value for key, value in sorted(primitive_counts.items()) if value
        },
        "exact_frozen_selection_matches": checked_cells - len(mismatches),
        "mismatch_n": len(mismatches),
        "mismatches": mismatches,
        "causal_isolation_passed": checked_cells > 0 and not mismatches,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return report


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2, ensure_ascii=False))

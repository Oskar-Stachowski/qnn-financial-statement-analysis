"""Refresh explicitly selected raw X_t rows after source-only backfills.

The refresh reuses the exact same row constructor as the full build, rewrites
the artifact through a temporary file, validates all 64,901 rows, and only
then replaces the prior artifact atomically.  It never changes policy,
membership, target data, or any row not named on the command line.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

import pandas as pd

from src.data import target_candidate_v2_pit as semantic
from src.data.research_universe_target_application import verify_frozen_inputs
from src.data.x_t_pit import (
    BASE_DIR,
    CONFIG_PATH,
    configured_path,
    load_config,
    load_negative_sign_review,
    load_universe,
    output_columns,
    process_company,
    sha256,
    validate_raw_artifact_path,
    write_build_manifest,
)


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "company_year_ids",
        nargs="+",
        help="Exact research_universe_company_year_id values to recompute",
    )
    args = parser.parse_args()
    requested = set(args.company_year_ids)

    config = load_config(CONFIG_PATH)
    frozen_before = verify_frozen_inputs(config)
    raw_path = configured_path(config, "outputs", "raw_artifact")
    # The pre-refresh artifact may legitimately predate the newly completed
    # manual sign review.  All other invariants are enforced here; the full
    # sign-review invariant is enforced on the rewritten temporary artifact.
    validate_raw_artifact_path(
        raw_path, config, enforce_negative_sign_review=False
    )
    before_sha256 = sha256(raw_path)

    semantic_config = semantic.load_config(
        configured_path(config, "frozen_inputs", "primitive_policy_source")
    )
    base_scope = semantic.parse_scope(semantic_config)
    pit = config["point_in_time"]
    scope = replace(
        base_scope,
        feature_year_start=int(config["x_t"]["feature_year_start"]),
        feature_year_end=int(config["x_t"]["feature_year_end"]),
        annual_period_min_days=int(pit["annual_period_min_days"]),
        annual_period_max_days=int(pit["annual_period_max_days"]),
        period_start_tolerance_days=int(pit["period_start_tolerance_days"]),
        minimum_denominator_usd=0.0,
    )
    eligible, period_ends = load_universe(config)
    selected = eligible.loc[
        eligible["research_universe_company_year_id"].isin(requested)
    ].copy()
    observed = set(selected["research_universe_company_year_id"].astype(str))
    if observed != requested:
        raise RuntimeError(
            f"Requested eligible IDs not resolved: {sorted(requested - observed)}"
        )

    replacements: dict[str, dict[str, Any]] = {}
    negative_sign_review = load_negative_sign_review(config)
    for cik10, group in selected.groupby("cik10", sort=True):
        rows = process_company(
            (str(cik10), group.to_dict("records")),
            config=config,
            semantic_config=semantic_config,
            scope=scope,
            period_ends=period_ends,
            companyfacts_root=configured_path(config, "sources", "companyfacts"),
            evidence_root=configured_path(
                config, "sources", "revenue_statement_evidence"
            ),
            negative_sign_review=negative_sign_review,
        )
        replacements.update(
            {
                str(row["research_universe_company_year_id"]): row
                for row in rows
            }
        )
    if set(replacements) != requested:
        raise RuntimeError("Row constructor did not return every requested ID")

    columns = output_columns(config)
    temporary = raw_path.with_suffix(raw_path.suffix + ".refresh.tmp")
    old_rows: dict[str, dict[str, str]] = {}
    found: set[str] = set()
    first = True
    for chunk in pd.read_csv(
        raw_path,
        dtype=str,
        keep_default_na=False,
        chunksize=2_000,
        low_memory=False,
    ):
        mask = chunk["research_universe_company_year_id"].isin(requested)
        for index in chunk.index[mask]:
            identifier = str(chunk.at[index, "research_universe_company_year_id"])
            old_rows[identifier] = chunk.loc[index].to_dict()
            replacement = replacements[identifier]
            for column in columns:
                chunk.at[index, column] = csv_value(replacement.get(column, ""))
            found.add(identifier)
        chunk.to_csv(
            temporary,
            mode="w" if first else "a",
            header=first,
            index=False,
            encoding="utf-8",
        )
        first = False
    if found != requested:
        raise RuntimeError(f"Raw artifact IDs not found: {sorted(requested - found)}")

    validate_raw_artifact_path(temporary, config)
    temporary.replace(raw_path)
    frozen_after = verify_frozen_inputs(config)
    if frozen_after != frozen_before:
        raise RuntimeError("Frozen target or universe changed during row refresh")
    manifest = write_build_manifest(CONFIG_PATH)

    changed_columns = {
        identifier: [
            column
            for column in columns
            if old_rows[identifier].get(column, "")
            != csv_value(replacements[identifier].get(column, ""))
        ]
        for identifier in sorted(requested)
    }
    report = {
        "artifact_id": "x_t_pit_v1_targeted_source_refresh",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "refreshed_company_year_ids": sorted(requested),
        "changed_columns": changed_columns,
        "raw_artifact_sha256_before": before_sha256,
        "raw_artifact_sha256_after": manifest["raw_artifact_sha256"],
        "raw_artifact_rows": manifest["raw_artifact_rows"],
        "frozen_inputs": frozen_after,
    }
    report_path = BASE_DIR / "data/reports/x_t_pit_v1_targeted_source_refresh.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Refreshed rows: {len(requested):,}")
    print(f"SHA-256: {manifest['raw_artifact_sha256']}")
    print(f"Report: {report_path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()

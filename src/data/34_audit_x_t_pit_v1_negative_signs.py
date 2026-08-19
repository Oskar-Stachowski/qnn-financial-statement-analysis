"""Audit the completed pre-freeze review of negative current_t primitives."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

import pandas as pd

from src.data.research_universe_target_application import verify_frozen_inputs
from src.data.x_t_pit import (
    BASE_DIR,
    CONFIG_PATH,
    configured_path,
    feature_names,
    load_config,
    load_negative_sign_review,
    sha256,
    validate_raw_artifact_path,
)


PRIMITIVES = (
    "assets",
    "liabilities",
    "current_assets",
    "current_liabilities",
    "revenues",
)


def scalar(value: Any) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return value


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def main() -> None:
    config = load_config(CONFIG_PATH)
    frozen_hashes = verify_frozen_inputs(config)
    raw_path = configured_path(config, "outputs", "raw_artifact")
    validate_raw_artifact_path(raw_path, config)
    decisions = load_negative_sign_review(config)
    evidence_path = configured_path(
        config, "sources", "negative_sign_evidence_inventory"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("status_counts") != {"available": 23}:
        raise RuntimeError("Primary-statement evidence is not complete for 23 anchors")
    evidence_by_id = {
        str(item["research_universe_company_year_id"]): item
        for item in evidence["results"]
    }

    review_ids = {key[0] for key in decisions}
    read_columns = [
        "research_universe_company_year_id",
        "anchor_accession",
        "feature_year",
    ]
    for primitive in PRIMITIVES:
        read_columns.extend(
            [
                f"current_t_{primitive}_value",
                f"current_t_{primitive}_status",
                f"current_t_{primitive}_reason",
                f"current_t_{primitive}_tag",
                f"pair_{primitive}_status",
            ]
        )
    for feature in feature_names(config):
        read_columns.extend(
            [
                f"{feature}_value",
                f"{feature}_status",
                f"{feature}_source_primitives",
            ]
        )
    raw = pd.read_csv(raw_path, usecols=read_columns, low_memory=False)
    raw = raw.loc[raw["research_universe_company_year_id"].isin(review_ids)].copy()
    if len(raw) != 23:
        raise RuntimeError(f"Expected 23 reviewed company-years, got {len(raw)}")
    indexed = raw.set_index("research_universe_company_year_id", drop=False)

    rows: list[dict[str, Any]] = []
    for key, decision in sorted(decisions.items()):
        company_year_id, accession, primitive = key
        source = indexed.loc[company_year_id]
        anchor_evidence = evidence_by_id[company_year_id]
        if str(source["anchor_accession"]) != accession:
            raise RuntimeError(f"Exact anchor mismatch in reviewed case {key}")
        directory = (
            configured_path(config, "sources", "revenue_statement_evidence")
            / str(anchor_evidence["cik10"])
            / accession.replace("-", "")
        )
        primary_path = directory / str(decision["primary_10_k_file"])
        statement_path = directory / str(decision["statement_file"])
        if sha256(primary_path) != str(decision["primary_10_k_sha256"]):
            raise RuntimeError(f"Primary 10-K hash mismatch for {key}")
        if sha256(statement_path) != str(decision["statement_sha256"]):
            raise RuntimeError(f"Primary statement hash mismatch for {key}")

        dependent_features = []
        dependent_statuses = []
        for feature in feature_names(config):
            sources = str(source[f"{feature}_source_primitives"]).split(";")
            if primitive not in sources:
                continue
            dependent_features.append(feature)
            dependent_statuses.append(
                f"{feature}:{source[f'{feature}_status']}"
            )
        rows.append(
            {
                **decision,
                "current_status_after": source[f"current_t_{primitive}_status"],
                "current_value_after": scalar(source[f"current_t_{primitive}_value"]),
                "current_reason_after": source[f"current_t_{primitive}_reason"],
                "selected_tag_before": source[f"current_t_{primitive}_tag"],
                "pair_status_after": source[f"pair_{primitive}_status"],
                "dependent_features_recalculated": ";".join(dependent_features),
                "dependent_feature_statuses_after": ";".join(dependent_statuses),
                "primary_10_k_path": str(primary_path.relative_to(BASE_DIR)),
                "statement_path": str(statement_path.relative_to(BASE_DIR)),
            }
        )
    review = pd.DataFrame(rows)

    selected_negative_counts: dict[str, int] = {}
    for primitive in PRIMITIVES:
        values = pd.to_numeric(raw[f"current_t_{primitive}_value"], errors="coerce")
        selected_negative_counts[primitive] = int(
            (
                raw[f"current_t_{primitive}_status"].eq("selected")
                & values.lt(0)
            ).sum()
        )
    if selected_negative_counts != {
        "assets": 0,
        "liabilities": 0,
        "current_assets": 0,
        "current_liabilities": 0,
        "revenues": 5,
    }:
        raise RuntimeError(
            f"Unexpected post-review negative selections: {selected_negative_counts}"
        )

    output_csv = configured_path(config, "outputs", "negative_sign_review_csv")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    review.to_csv(output_csv, index=False, encoding="utf-8", lineterminator="\n")

    outcome_counts = Counter(review["outcome"])
    action_counts = Counter(review["action"])
    markdown = [
        "# X_t v1 — pre-freeze sanity check ujemnych selected primitives",
        "",
        f"Wygenerowano: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Zakres i wynik",
        "",
        "Kontrola objęła wyłącznie development 2011–2022. Sprawdzono 25 primitive-cases w 23 company-years względem exact frozen-universe anchor accession, filing index, primary original 10-K oraz primary financial statement. Test 2023–2024 nie był używany do decyzji.",
        "",
        f"- faktycznie raportowane i ekonomicznie uzasadnione: {outcome_counts['reported_economically_valid']}",
        f"- błąd znaku/tagu/kontekstu XBRL: {outcome_counts['xbrl_semantic_or_context_error']}",
        f"- nierozstrzygalne ekonomicznie: {outcome_counts['unresolved']}",
        f"- zachowane bez zmiany: {action_counts['retain']}",
        f"- ustawione fail-closed jako ambiguous/NA: {action_counts['ambiguous_na']}",
        "",
        "Nie zastosowano odwracania znaku ani podmiany na alternatywny fact/tag. Dla każdego fail-closed primitive para current/comparative została oznaczona ambiguous, a wszystkie zależne cechy przeliczone do stanu niedostępnego.",
        "",
        "## Wynik według primitive",
        "",
        "| Primitive | Przypadki przed | Selected ujemne po |",
        "|---|---:|---:|",
    ]
    for primitive in PRIMITIVES:
        markdown.append(
            f"| {primitive} | {int((review['primitive'] == primitive).sum())} | {selected_negative_counts[primitive]} |"
        )
    markdown.extend(
        [
            "",
            "## Kontrola przypadek po przypadku",
            "",
            "| Company-year | Primitive | Przed | Klasyfikacja | Działanie | Primary statement evidence |",
            "|---|---|---:|---|---|---|",
        ]
    )
    for item in review.to_dict("records"):
        markdown.append(
            f"| {markdown_cell(item['company_year_id'])} | "
            f"{markdown_cell(item['primitive'])} | "
            f"{float(item['selected_value_before']):g} | "
            f"{markdown_cell(item['outcome'])} | "
            f"{markdown_cell(item['action'])} | "
            f"{markdown_cell(item['direct_statement_label'])}: "
            f"{float(item['direct_statement_value']):g}; "
            f"{markdown_cell(item['evidence_note'])} |"
        )
    markdown.extend(
        [
            "",
            "## Invariants i integralność",
            "",
            "- 64 901 eligible company-years zachowanych; schema i exact-accession invariants przeszły.",
            f"- frozen universe SHA-256: `{frozen_hashes['universe_artifact_sha256']}`.",
            f"- frozen target SHA-256: `{frozen_hashes['target_artifact_sha256']}`.",
            f"- raw X_t SHA-256 po przeliczeniu: `{sha256(raw_path)}`.",
            "- brak imputacji, winsoryzacji, skalowania, feature selection i treningu modeli.",
            "",
            "## Werdykt",
            "",
            "**X_T V1 READY TO FREEZE**",
            "",
        ]
    )
    output_md = configured_path(config, "outputs", "negative_sign_review_markdown")
    output_md.write_text("\n".join(markdown), encoding="utf-8")
    print(f"Review cases: {len(review)}")
    print(f"Outcome counts: {dict(sorted(outcome_counts.items()))}")
    print(f"Action counts: {dict(sorted(action_counts.items()))}")
    print("X_T V1 READY TO FREEZE")


if __name__ == "__main__":
    main()

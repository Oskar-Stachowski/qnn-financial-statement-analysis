"""Audit the filing-first point-in-time research universe."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from historical_research_universe import normalize_cik, utc_now_iso


BASE_DIR = Path(__file__).resolve().parents[2]
UNIVERSE_PATH = BASE_DIR / "data" / "processed" / "research_universe_pit.csv"
UNRESOLVED_PATH = BASE_DIR / "data" / "interim" / "research_universe_pit_unresolved.csv"
OLD_UNIVERSE_PATH = BASE_DIR / "data" / "processed" / "research_universe.csv"
CURRENT_TICKER_PATH = BASE_DIR / "data" / "interim" / "sec_ticker_cik_map.csv"
CURRENT_CLASSIFICATION_PATH = (
    BASE_DIR / "data" / "interim" / "sec_company_classified.csv"
)
REPORT_PATH = BASE_DIR / "data" / "reports" / "research_universe_pit_audit.md"
JSON_PATH = BASE_DIR / "data" / "reports" / "research_universe_pit_audit.json"
YEAR_TABLE_PATH = BASE_DIR / "data" / "reports" / "research_universe_pit_by_year.csv"
SECTOR_TABLE_PATH = (
    BASE_DIR / "data" / "reports" / "research_universe_pit_by_sector_year.csv"
)
SIC_TABLE_PATH = BASE_DIR / "data" / "reports" / "research_universe_pit_by_sic.csv"
BUILD_MANIFEST_PATH = BASE_DIR / "data" / "reports" / "research_universe_pit_build.json"
FROZEN_TARGET_PATH = BASE_DIR / "data" / "interim" / "target_candidate_v2_pit_b.csv"
FROZEN_TARGET_MANIFEST_PATH = (
    BASE_DIR / "configs" / "target_candidate_v2_pit_b_freeze_manifest.yaml"
)

DEVELOPMENT_END = 2022


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_frozen_target() -> str:
    manifest = yaml.safe_load(
        FROZEN_TARGET_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    expected = next(
        item["sha256"]
        for item in manifest["non_versioned_reproduction_checks"]
        if item["path"] == "data/interim/target_candidate_v2_pit_b.csv"
    )
    actual = sha256_path(FROZEN_TARGET_PATH)
    if actual != expected:
        raise ValueError("Frozen PIT-B target hash differs from freeze manifest")
    return actual


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(frame.to_json(orient="records"))


def markdown_table(frame: pd.DataFrame) -> str:
    display = frame.copy().fillna("")
    columns = [str(column) for column in display.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in display.itertuples(index=False, name=None):
        values = [str(value).replace("|", "\\|") for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def yearly_table(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for year, group in frame.groupby("feature_year", sort=True):
        eligible = group[group["membership_status"].eq("eligible")]
        eligible_pre = group[
            group["membership_status_pre_entity_resolution"].eq("eligible")
        ]
        rows.append(
            {
                "year": int(year),
                "anchors": len(group),
                "eligible_company_years": len(eligible),
                "eligible_pre_entity_resolution": len(eligible_pre),
                "removed_by_entity_resolution": len(eligible_pre) - len(eligible),
                "eligible_companies": eligible["cik10"].nunique(),
                "excluded": group["membership_status"].eq("excluded").sum(),
                "ambiguous": group["membership_status"].eq("ambiguous").sum(),
                "recovered_vs_old": eligible["recovered_vs_old_universe"].sum(),
                "recovered_share_pct": round(
                    100 * eligible["recovered_vs_old_universe"].mean(), 2
                )
                if len(eligible)
                else 0.0,
                "absent_current_ticker": (~eligible["in_current_ticker_snapshot"]).sum(),
                "inactive_delisted_unmapped_proxy": eligible[
                    "later_inactive_delisted_or_unmapped_proxy"
                ].sum(),
            }
        )
    return pd.DataFrame(rows)


def value_count_table(
    series: pd.Series, label: str, total: int | None = None
) -> pd.DataFrame:
    counts = series.fillna("NA").astype(str).value_counts(dropna=False)
    denominator = total if total is not None else len(series)
    return pd.DataFrame(
        {
            label: counts.index,
            "n": counts.values,
            "share_pct": (100 * counts.values / denominator).round(2),
        }
    )


def comparison_with_old(
    universe: pd.DataFrame, old: pd.DataFrame, current_classification: pd.DataFrame
) -> tuple[dict[str, object], pd.DataFrame]:
    old = old.copy()
    old["cik10"] = old["cik10"].map(normalize_cik)
    old = old[["cik10"]].drop_duplicates()
    current_classification = current_classification.copy()
    current_classification["cik10"] = current_classification["cik10"].map(
        normalize_cik
    )
    current_classification["current_snapshot_sic"] = pd.to_numeric(
        current_classification["sic_int"], errors="coerce"
    )
    current_classification["current_snapshot_eligible"] = (
        current_classification["include_in_research_universe"]
        .astype(str)
        .str.lower()
        .eq("true")
    )
    current_classification = current_classification[
        [
            "cik10",
            "current_snapshot_sic",
            "research_sector",
            "current_snapshot_eligible",
        ]
    ].rename(columns={"research_sector": "current_snapshot_sector"})
    merged = universe.merge(
        current_classification, on="cik10", how="left", validate="many_to_one"
    )
    overlap = merged[merged["current_snapshot_sic"].notna()].copy()
    overlap["sic_changed_vs_current_snapshot"] = (
        pd.to_numeric(overlap["historical_sic"], errors="coerce")
        != overlap["current_snapshot_sic"]
    )
    overlap["sector_changed_vs_current_snapshot"] = (
        overlap["research_sector"] != overlap["current_snapshot_sector"]
    )
    overlap["historical_eligible"] = overlap["membership_status"].eq("eligible")
    overlap["eligibility_changed_vs_current_snapshot"] = (
        overlap["historical_eligible"] != overlap["current_snapshot_eligible"]
    )
    eligible = universe[universe["membership_status"].eq("eligible")]
    eligible_ciks = set(eligible["cik10"])
    old_ciks = set(old["cik10"])
    recovered = eligible[~eligible["cik10"].isin(old_ciks)]
    summary = {
        "old_current_snapshot_unique_ciks": len(old_ciks),
        "new_pit_eligible_unique_ciks": len(eligible_ciks),
        "recovered_unique_ciks": len(eligible_ciks - old_ciks),
        "recovered_unique_ciks_absent_current_ticker": recovered.loc[
            ~recovered["in_current_ticker_snapshot"], "cik10"
        ].nunique(),
        "recovered_unique_ciks_present_current_ticker": recovered.loc[
            recovered["in_current_ticker_snapshot"], "cik10"
        ].nunique(),
        "old_snapshot_ciks_without_eligible_anchor_2011_2024": len(
            old_ciks - eligible_ciks
        ),
        "eligible_company_years": len(eligible),
        "recovered_eligible_company_years": int(
            eligible["recovered_vs_old_universe"].sum()
        ),
        "recovered_company_years_absent_current_ticker": int(
            (~recovered["in_current_ticker_snapshot"]).sum()
        ),
        "recovered_company_years_present_current_ticker": int(
            recovered["in_current_ticker_snapshot"].sum()
        ),
        "recovered_company_year_share_pct": round(
            100 * eligible["recovered_vs_old_universe"].mean(), 2
        ),
        "overlap_company_years_with_changed_sic": int(
            overlap["sic_changed_vs_current_snapshot"].sum()
        ),
        "overlap_company_years_with_changed_sector": int(
            overlap["sector_changed_vs_current_snapshot"].sum()
        ),
        "overlap_company_years_with_changed_eligibility": int(
            overlap["eligibility_changed_vs_current_snapshot"].sum()
        ),
        "currently_eligible_but_historically_not_eligible_company_years": int(
            (
                overlap["current_snapshot_eligible"]
                & ~overlap["historical_eligible"]
            ).sum()
        ),
        "currently_not_eligible_but_historically_eligible_company_years": int(
            (
                ~overlap["current_snapshot_eligible"]
                & overlap["historical_eligible"]
            ).sum()
        ),
        "current_snapshot_cik_years_historically_excluded": int(
            overlap["membership_status"].eq("excluded").sum()
        ),
        "current_snapshot_cik_years_historically_ambiguous": int(
            overlap["membership_status"].eq("ambiguous").sum()
        ),
    }
    changed = (
        overlap[
            overlap["sic_changed_vs_current_snapshot"]
            | overlap["sector_changed_vs_current_snapshot"]
            | overlap["eligibility_changed_vs_current_snapshot"]
        ]
        .groupby(
            [
                "current_snapshot_eligible",
                "historical_eligible",
                "current_snapshot_sector",
                "research_sector",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="company_years")
        .sort_values("company_years", ascending=False)
        .head(20)
    )
    return summary, changed


def main() -> None:
    frozen_target_hash = verify_frozen_target()
    build_manifest = json.loads(BUILD_MANIFEST_PATH.read_text(encoding="utf-8"))
    universe = pd.read_csv(
        UNIVERSE_PATH,
        dtype={
            "cik10": str,
            "representative_cik": str,
            "linked_co_registrant_ciks": str,
            "same_statement_scope_ciks": str,
            "joint_accession_registrant_ciks": str,
        },
        low_memory=False,
    )
    old = pd.read_csv(OLD_UNIVERSE_PATH, dtype={"cik10": str}, low_memory=False)
    current_classification = pd.read_csv(
        CURRENT_CLASSIFICATION_PATH, dtype={"cik10": str}, low_memory=False
    )
    unresolved = (
        pd.read_csv(UNRESOLVED_PATH, dtype={"cik10": str}, low_memory=False)
        if UNRESOLVED_PATH.exists() and UNRESOLVED_PATH.stat().st_size
        else pd.DataFrame()
    )
    development = universe[universe["feature_year"].le(DEVELOPMENT_END)].copy()
    test_years = universe[universe["feature_year"].gt(DEVELOPMENT_END)].copy()
    eligible = universe[universe["membership_status"].eq("eligible")].copy()
    eligible_development = development[
        development["membership_status"].eq("eligible")
    ].copy()
    unresolved_resolution = (
        unresolved.groupby(
            ["feature_year_resolution_status", "observed_fiscal_year"],
            dropna=False,
        )
        .size()
        .reset_index(name="filing_rows")
        if not unresolved.empty
        else pd.DataFrame(
            columns=[
                "feature_year_resolution_status",
                "observed_fiscal_year",
                "filing_rows",
            ]
        )
    )

    yearly = yearly_table(universe)
    sector = (
        eligible.groupby(["feature_year", "research_sector"])
        .size()
        .reset_index(name="company_years")
        .sort_values(["feature_year", "research_sector"])
    )
    sector_total = value_count_table(eligible["research_sector"], "sector")
    sic = (
        eligible.groupby(["historical_sic", "historical_sic_description"], dropna=False)
        .agg(company_years=("cik10", "size"), unique_ciks=("cik10", "nunique"))
        .reset_index()
        .sort_values(["company_years", "historical_sic"], ascending=[False, True])
    )
    membership_reasons = (
        universe[~universe["membership_status"].eq("eligible")]
        .groupby(["membership_status", "membership_reason"], dropna=False)
        .size()
        .reset_index(name="company_years")
        .sort_values(["membership_status", "company_years"], ascending=[True, False])
    )
    target_status = (
        eligible_development["target_status"]
        .fillna("not_computed")
        .value_counts()
        .rename_axis("target_status")
        .reset_index(name="eligible_company_years")
    )
    x_status = value_count_table(eligible["x_t_status"], "x_t_status")
    comparison, changed_sectors = comparison_with_old(
        universe, old, current_classification
    )

    proxy = eligible[eligible["later_inactive_delisted_or_unmapped_proxy"]]
    membership_before = value_count_table(
        universe["membership_status_pre_entity_resolution"],
        "membership_status_pre_entity_resolution",
    )
    membership_after = value_count_table(
        universe["membership_status"], "membership_status"
    )
    changed_by_resolution = universe[
        universe["entity_resolution_membership_changed"]
    ].copy()
    entity_resolution_changes = (
        changed_by_resolution.groupby(
            [
                "membership_status_pre_entity_resolution",
                "membership_status",
                "registrant_resolution_action",
                "membership_reason",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="company_years")
        .sort_values("company_years", ascending=False)
    )
    role_counts = value_count_table(
        eligible["registrant_role_resolved"], "registrant_role_resolved"
    )
    eligible_scope_duplicate_rows = int(
        eligible.duplicated(
            ["feature_year", "economic_statement_scope_id"], keep=False
        ).sum()
    )
    eligible_nonrepresentative_rows = int(
        (~eligible["cik10"].eq(eligible["representative_cik"])).sum()
    )
    eligible_missing_scope_rows = int(
        eligible["economic_statement_scope_id"].fillna("").eq("").sum()
    )
    eligible_missing_group_rows = int(
        eligible["economic_group_id"].fillna("").eq("").sum()
    )
    duplicate_exclusions = int(
        universe["membership_reason"]
        .eq("duplicate_registrant_same_statement_scope")
        .sum()
    )
    nonoperating_exclusions = int(
        universe["membership_reason"]
        .eq("nominal_nonoperating_finance_coissuer")
        .sum()
    )
    entity_ambiguities = int(
        changed_by_resolution["membership_status"].eq("ambiguous").sum()
    )
    allowed_roles = {
        "single_filer_xbrl_registrant",
        "single_filer_non_xbrl_registrant",
        "joint_primary_registrant",
        "joint_co_registrant",
    }
    freeze_ready = all(
        [
            eligible_scope_duplicate_rows == 0,
            eligible_nonrepresentative_rows == 0,
            eligible_missing_scope_rows == 0,
            eligible_missing_group_rows == 0,
            duplicate_exclusions == 132,
            nonoperating_exclusions == 28,
            entity_ambiguities == 6,
            set(universe["registrant_role_resolved"].unique()).issubset(
                allowed_roles
            ),
            universe["x_t_status"].eq("not_built").all(),
            frozen_target_hash
            == build_manifest["target_artifact_sha256_verified_after_build"],
        ]
    )
    current_snapshot_date = "unknown"
    if CURRENT_TICKER_PATH.exists():
        tickers = pd.read_csv(CURRENT_TICKER_PATH, usecols=["downloaded_at"], dtype=str)
        dates = sorted(tickers["downloaded_at"].dropna().unique())
        current_snapshot_date = ", ".join(dates)

    audit = {
        "created_at": utc_now_iso(),
        "universe_policy": "research_universe_pit v1.1.0",
        "target": "target_candidate_v2_pit_b v1.0.0 frozen and unchanged",
        "scope": {
            "development_train_validation": [2011, 2022],
            "mechanical_test_year_application": [2023, 2024],
            "test_used_for_methodological_decisions": False,
        },
        "overall": {
            "company_year_anchors": len(universe),
            "unique_ciks_all_statuses": universe["cik10"].nunique(),
            "eligible_company_years": len(eligible),
            "eligible_unique_ciks": eligible["cik10"].nunique(),
            "excluded_company_years": int(
                universe["membership_status"].eq("excluded").sum()
            ),
            "ambiguous_company_years": int(
                universe["membership_status"].eq("ambiguous").sum()
            ),
            "unresolved_filing_rows_outside_company_year_panel": len(unresolved),
            "resolved_out_of_scope_filing_rows": int(
                unresolved["feature_year_resolution_status"]
                .eq("resolved_out_of_scope")
                .sum()
            ),
            "truly_unresolved_feature_year_filing_rows": int(
                unresolved["feature_year_resolution_status"].eq("unresolved").sum()
            ),
            "development_eligible_company_years": len(eligible_development),
            "test_year_eligible_company_years_mechanical_only": int(
                test_years["membership_status"].eq("eligible").sum()
            ),
            "joint_filing_eligible_company_years": int(
                eligible["joint_filing_flag"].sum()
            ),
            "joint_filing_eligible_unique_ciks": int(
                eligible.loc[eligible["joint_filing_flag"], "cik10"].nunique()
            ),
            "eligible_company_years_with_multiple_original_10k_candidates": int(
                eligible["anchor_candidate_count"].gt(1).sum()
            ),
            "eligible_max_original_10k_candidates": int(
                eligible["anchor_candidate_count"].max()
            ),
            "accepted_timestamp_available_company_years": int(
                universe["membership_available_at_precision"].eq("timestamp").sum()
            ),
            "filed_date_fallback_company_years": int(
                universe["membership_available_at_precision"].eq("date").sum()
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
            "eligible_statement_scope_year_duplicate_rows": (
                eligible_scope_duplicate_rows
            ),
            "eligible_nonrepresentative_rows": eligible_nonrepresentative_rows,
            "eligible_missing_statement_scope_rows": eligible_missing_scope_rows,
            "eligible_missing_economic_group_rows": eligible_missing_group_rows,
        },
        "registrant_role_entity_resolution": {
            "membership_before": records(membership_before),
            "membership_after": records(membership_after),
            "changes": records(entity_resolution_changes),
            "duplicate_registrant_rows_excluded": duplicate_exclusions,
            "nominal_nonoperating_coissuers_excluded": nonoperating_exclusions,
            "unresolved_rows_changed_to_ambiguous": entity_ambiguities,
            "freeze_gate_ready": freeze_ready,
        },
        "recovered_and_activity": {
            **comparison,
            "eligible_absent_from_current_ticker_company_years": int(
                (~eligible["in_current_ticker_snapshot"]).sum()
            ),
            "eligible_absent_from_current_ticker_unique_ciks": int(
                eligible.loc[~eligible["in_current_ticker_snapshot"], "cik10"].nunique()
            ),
            "later_inactive_delisted_or_unmapped_proxy_company_years": len(proxy),
            "later_inactive_delisted_or_unmapped_proxy_unique_ciks": proxy[
                "cik10"
            ].nunique(),
            "proxy_definition": (
                "eligible; absent from current SEC ticker snapshot; no later original "
                "10-K observed through the 2025 filing index"
            ),
            "current_ticker_snapshot_downloaded_at": current_snapshot_date,
            "confirmed_delisting_count_available": False,
        },
        "yearly": records(yearly),
        "sector_distribution": records(sector),
        "sic_distribution": records(sic),
        "membership_reasons": records(membership_reasons),
        "filings_outside_company_year_panel": records(unresolved_resolution),
        "target_status_development": records(target_status),
        "x_t_status": records(x_status),
        "registrant_roles": records(role_counts),
        "historical_sic_sources": records(
            value_count_table(
                universe["historical_sic_source"], "historical_sic_source"
            )
        ),
        "historical_classification_changes": records(changed_sectors),
        "methodological_assessment": {
            "survivorship_bias_old_universe": "material and empirically confirmed",
            "historical_classification_bias_old_universe": (
                "material if current SIC/sector is backcast; historical anchor SIC is now used"
            ),
            "new_universe_membership_depends_on_current_ticker": False,
            "new_universe_membership_depends_on_target_t1": False,
            "new_universe_membership_depends_on_x_t_availability": False,
            "economic_group_id_changes_membership": False,
            "economic_group_id_overrides_temporal_split": False,
            "delisting_status_limitation": (
                "SEC-only sources identify a conservative inactive/delisted/unmapped "
                "proxy, not exchange-confirmed delisting events"
            ),
        },
        "frozen_target_sha256_verified": frozen_target_hash,
        "freeze_gate_verdict": (
            "RESEARCH UNIVERSE READY TO FREEZE"
            if freeze_ready
            else "RESEARCH UNIVERSE NOT READY TO FREEZE"
        ),
    }

    lines = [
        "# Audyt historycznego point-in-time research universe",
        "",
        f"Wygenerowano: `{audit['created_at']}`.",
        "",
        "## Wynik",
        "",
        (
            "Nowy universe jest zbudowany filing-first z census oryginalnych 10-K SEC. "
            "CIK i historyczny SIC pochodzą z tego samego anchor filing; bieżąca lista "
            "tickerów nie jest warunkiem membership. Status membership, `X_t` i targetu "
            "są rozdzielone. Zamrożony `target_candidate_v2_pit_b v1.0.0` nie został "
            "przeliczony ani zmieniony."
        ),
        "",
        "Testowe feature years 2023–2024 zostały objęte wyłącznie mechanicznym "
        "zastosowaniem zamrożonej polityki universe; nie użyto ich do podjęcia ani "
        "zmiany decyzji metodologicznej.",
        "",
        "## Registrant-role / economic-entity resolution",
        "",
        "Role źródłowe zostały rozdzielone na cztery jednoznaczne wartości. "
        "Wspólny accession nie tworzy kilku eligible obserwacji dla jednego "
        "statement scope. Wiersze usunięte z populacji eligible pozostają w "
        "kanonicznym pliku jako provenance `excluded` albo `ambiguous`.",
        "",
        "Membership przed zastosowaniem resolvera:",
        "",
        markdown_table(membership_before),
        "",
        "Membership po zastosowaniu resolvera:",
        "",
        markdown_table(membership_after),
        "",
        "Zmiany membership:",
        "",
        markdown_table(entity_resolution_changes),
        "",
        f"- Wykluczono {duplicate_exclusions:,} potwierdzone duplicate registrant rows.",
        f"- Wykluczono {nonoperating_exclusions:,} nominalnych/non-operating finance co-issuerów na podstawie bezpośredniego dowodu z filingu.",
        f"- {entity_ambiguities:,} nierozstrzygniętych obserwacji zmieniono na `ambiguous`.",
        f"- Eligible statement scope-year duplicates: {eligible_scope_duplicate_rows:,}.",
        f"- Eligible wiersze niebędące representative CIK: {eligible_nonrepresentative_rows:,}.",
        f"- Distinct eligible statement scope-years: {audit['overall']['eligible_distinct_statement_scope_years']:,}; representative CIKs: {audit['overall']['eligible_distinct_representative_ciks']:,}; economic groups: {audit['overall']['eligible_distinct_economic_groups']:,}.",
        "",
        "`economic_group_id` wyłącznie identyfikuje powiązane ekonomicznie "
        "statement scopes. Nie zmienia membership i nie zastępuje temporal splitu; "
        "ma służyć clustered inference, leakage diagnostics i opcjonalnemu "
        "group-aware CV.",
        "",
        "## Liczebność według roku",
        "",
        markdown_table(yearly),
        "",
        "## Odzyskane spółki i survivorship bias",
        "",
        f"- Stary universe: {comparison['old_current_snapshot_unique_ciks']:,} CIK.",
        f"- Nowy PIT universe: {comparison['new_pit_eligible_unique_ciks']:,} kwalifikujących się CIK i {comparison['eligible_company_years']:,} spółka-lat.",
        f"- Odzyskano {comparison['recovered_unique_ciks']:,} CIK oraz {comparison['recovered_eligible_company_years']:,} spółka-lat nieobecnych w starym universe.",
        f"- Z odzyskanych CIK {comparison['recovered_unique_ciks_absent_current_ticker']:,} nie występuje w current ticker snapshot (komponent survivorship/inactivity/unmapped), a {comparison['recovered_unique_ciks_present_current_ticker']:,} nadal występuje, lecz było pominiętych przez starą bieżącą klasyfikację/filtry.",
        f"- Odzyskane obserwacje stanowią {comparison['recovered_company_year_share_pct']:.2f}% nowego universe.",
        f"- {comparison['old_snapshot_ciks_without_eligible_anchor_2011_2024']:,} CIK starego snapshotu nie ma kwalifikującego historycznego anchoru w badanym zakresie albo historycznie nie spełnia polityki sektorowej.",
        "",
        (
            "Wniosek: survivorship bias starego universe był istotny — current-company "
            "snapshot usuwał historycznych registrantów. Nowa definicja usuwa ten warunek "
            "z membership, ale nie gwarantuje dostępności X_t ani targetu."
        ),
        "",
        "## Spółki później nieaktywne / delistowane",
        "",
        f"Konserwatywny proxy obejmuje {len(proxy):,} spółka-lat i {proxy['cik10'].nunique():,} unikalnych CIK. Proxy oznacza jednocześnie: brak na current ticker snapshot (`{current_snapshot_date}`) oraz brak późniejszego oryginalnego 10-K do końca indeksu 2025.",
        "",
        (
            "To nie jest potwierdzona data delistingu: SEC filing index sam nie rozróżnia "
            "delistingu, M&A, likwidacji i braku mapowania tickera. Membership zachowuje "
            "te obserwacje; do potwierdzenia zdarzeń potrzebne byłoby osobne historyczne "
            "źródło giełdowe/CRSP."
        ),
        "",
        "## Sektory",
        "",
        markdown_table(sector_total),
        "",
        "Rozkład sektor–rok:",
        "",
        markdown_table(sector),
        "",
        "## SIC (20 najczęstszych)",
        "",
        markdown_table(sic.head(20)),
        "",
        "## Ambiguous i excluded",
        "",
        markdown_table(membership_reasons),
        "",
        "",
        "Filingi poza panelem spółka–rok:",
        "",
        markdown_table(unresolved_resolution),
        "",
        f"Łącznie {len(unresolved):,} filingów pozostaje poza panelem: {int(unresolved['feature_year_resolution_status'].eq('resolved_out_of_scope').sum()):,} ma jednoznaczny rok poza zakresem 2011–2024, a {int(unresolved['feature_year_resolution_status'].eq('unresolved').sum()):,} nie ma wiarygodnego roku i nie jest zgadywane.",
        "",
        "## Joint filings i co-registranci",
        "",
        f"{int(eligible['joint_filing_flag'].sum()):,} kwalifikujących spółka-lat ({eligible.loc[eligible['joint_filing_flag'], 'cik10'].nunique():,} CIK) pochodzi z accession obejmującego więcej niż jednego registranta. Każdy odrębny pełny annual statement scope pozostaje osobną reporting entity, ale dla współdzielonego scope zachowany jest tylko jeden eligible representative CIK. SIC nadal pochodzi z historycznego bloku `FILER` danego CIK.",
        "",
        markdown_table(role_counts),
        "",
        "## Wiele oryginalnych 10-K dla CIK–roku",
        "",
        f"{int(eligible['anchor_candidate_count'].gt(1).sum()):,} eligible CIK–lat ma więcej niż jeden kandydat oryginalnego 10-K (maksimum {int(eligible['anchor_candidate_count'].max())}). Zgodnie z polityką anchor jest najwcześniejszym accepted filing; liczba kandydatów i rank pozostają w provenance. Nie zmieniano wyboru na podstawie danych finansowych ani targetu.",
        "",
        "## Historyczna klasyfikacja a stary snapshot",
        "",
        f"W części wspólnej {comparison['overlap_company_years_with_changed_sic']:,} spółka-lat ma historyczny SIC inny niż SIC z bieżącego snapshotu, {comparison['overlap_company_years_with_changed_sector']:,} ma inną etykietę sektorową, a w {comparison['overlap_company_years_with_changed_eligibility']:,} zmienia się sam status eligible/excluded.",
        "",
        f"Bieżący snapshot uznaje za eligible {comparison['currently_eligible_but_historically_not_eligible_company_years']:,} spółka-lat, które historycznie nie były eligible; odwrotnie, {comparison['currently_not_eligible_but_historically_eligible_company_years']:,} historycznych spółka-lat zostałoby utraconych przez zastosowanie bieżącej klasyfikacji.",
        "",
        markdown_table(changed_sectors),
        "",
        "## Rozdzielenie statusów",
        "",
        "`membership_status` wynika z kwalifikującego anchor 10-K, jego historycznego SIC oraz zamkniętej polityki registrant-role/economic-entity. `x_t_status` pozostaje `not_built`. Dostępność targetu jest tylko dołączoną informacją i nie wpływa na membership.",
        "",
        "Target status w kwalifikującej populacji development 2011–2022:",
        "",
        markdown_table(target_status),
        "",
        "X_t status:",
        "",
        markdown_table(x_status),
        "",
        "## Ocena metodologiczna",
        "",
        "- Stary universe: istotne ryzyko survivorship bias oraz historical-classification bias zostało potwierdzone empirycznie.",
        "- Nowy universe: membership jest historyczne i filing-first; brak t+1, targetu albo przyszłego filingu nie usuwa obserwacji t.",
        "- Brak historycznego SIC lub konflikt source-of-record skutkuje `ambiguous`, nigdy zgadywaniem sektora.",
        "- Current ticker i exchange służą wyłącznie do audytu; nie są filtrami.",
        f"- Zamrożony target ma nadal hash `{frozen_target_hash}` zgodny z freeze manifestem.",
        "- Finalny X_t nadal nie istnieje i nie trenowano modeli.",
        "",
        "## Źródła",
        "",
        "- SEC EDGAR quarterly master index: census filingów i historyczna ścieżka accession.",
        "- SEC Financial Statement Data Sets, `SUB`: CIK, SIC, okres i accepted timestamp obowiązujące dla danego submission.",
        "- SEC submission header tego samego accession: fallback oraz osobne bloki `FILER` dla joint filings.",
        "- Oficjalna tabela kodów SIC SEC: wyłącznie opis statycznego kodu; nie źródło membership ani bieżącego SIC spółki.",
        "",
        "## Freeze gate",
        "",
        "Audyt nie zamraża universe automatycznie. Weryfikuje jedynie gotowość "
        "zaimplementowanej wersji 1.1.0.",
        "",
        f"**{audit['freeze_gate_verdict']}**",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    JSON_PATH.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    yearly.to_csv(YEAR_TABLE_PATH, index=False)
    sector.to_csv(SECTOR_TABLE_PATH, index=False)
    sic.to_csv(SIC_TABLE_PATH, index=False)
    print(json.dumps({"overall": audit["overall"], "recovered_and_activity": audit["recovered_and_activity"]}, indent=2))
    print(f"Saved: {REPORT_PATH}")
    print(f"Saved: {JSON_PATH}")
    print(f"Saved: {YEAR_TABLE_PATH}")
    print(f"Saved: {SECTOR_TABLE_PATH}")
    print(f"Saved: {SIC_TABLE_PATH}")


if __name__ == "__main__":
    main()

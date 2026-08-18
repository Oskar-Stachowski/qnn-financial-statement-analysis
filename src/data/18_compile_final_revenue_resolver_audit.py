"""Compile the post-review revenue resolver audit and freeze-gate verdict."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

try:
    from src.data.revenue_manual_review import validate_completed_review
except ModuleNotFoundError:  # direct script execution
    from revenue_manual_review import validate_completed_review


BASE_DIR = Path(__file__).resolve().parents[2]
ROWS_PATH = BASE_DIR / "data" / "interim" / "target_candidate_v2_pit_b.csv"
BUILD_AUDIT_PATH = (
    BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_audit.json"
)
PREFIX = (
    BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_final_revenue_resolver"
)
REPORT_PATH = Path(f"{PREFIX}.md")
REVIEW_PATH = Path(f"{PREFIX}_manual_review.csv")
REVIEW_TEMPLATE_PATH = Path(f"{PREFIX}_manual_review_template.csv")
STATUS_ORDER = ("available", "missing", "ambiguous", "hard_exclude")
FIXED_SELECTION_ERRORS = (
    {
        "cik10": "0000091440",
        "feature_year": 2016,
        "company_name": "Snap-on Inc",
        "previous_error": (
            "Net sales was selected although Financial services revenue was a "
            "separate revenue-bearing line and no consolidated total was presented."
        ),
    },
    {
        "cik10": "0001083522",
        "feature_year": 2011,
        "company_name": "JONES SODA CO.",
        "previous_error": (
            "Product sales revenue was selected although Licensing revenue was a "
            "separate revenue-bearing line and no consolidated total was presented."
        ),
    },
)


def pct(numerator: int | float, denominator: int | float) -> str:
    return f"{numerator / denominator:.2%}" if denominator else "NA"


def table(suffix: str) -> pd.DataFrame:
    return pd.read_csv(f"{PREFIX}_{suffix}.csv")


def main() -> None:
    frame = pd.read_csv(ROWS_PATH, dtype={"cik10": str}, low_memory=False)
    audit = json.loads(Path(f"{PREFIX}.json").read_text(encoding="utf-8"))
    build_audit = json.loads(BUILD_AUDIT_PATH.read_text(encoding="utf-8"))
    review = pd.read_csv(REVIEW_PATH, dtype={"cik10": str})
    review_template = pd.read_csv(REVIEW_TEMPLATE_PATH, dtype={"cik10": str})
    review = validate_completed_review(review, template=review_template)
    if (
        int(frame["feature_year"].min()) != 2011
        or int(frame["feature_year"].max()) != 2022
    ):
        raise RuntimeError("Report scope must be feature years 2011--2022")

    by_year = table("status_by_year")
    by_sector = table("status_by_sector")
    by_sic = table("status_by_sic")
    by_assets = table("status_by_assets_size")
    by_missing_t = table("status_by_missing_primitives_t")
    features = table("feature_summary")
    revenue_reasons = table("revenue_reason_counts")
    primitive_status = table("primitive_status")
    signal_coverage = table("signal_coverage")
    sole_missing_signal = table("sole_missing_signal")

    total = len(frame)
    available = frame[frame["target_status"].eq("available")]
    positives = int(available["target_candidate_v2"].sum())
    revenue_ambiguous = int(frame["B_revenues_status"].eq("ambiguous").sum())
    provenance = build_audit["provenance_integrity"]
    available_year_range = float(
        by_year["available_rate"].max() - by_year["available_rate"].min()
    )
    available_sector_range = float(
        by_sector["available_rate"].max() - by_sector["available_rate"].min()
    )
    observed_size = by_assets[~by_assets["assets_size_quartile"].eq("missing")]
    available_size_range = float(
        observed_size["available_rate"].max() - observed_size["available_rate"].min()
    )
    non_available_smd = pd.to_numeric(
        features[~features["status"].eq("available")]["smd_vs_available"],
        errors="coerce",
    ).abs()
    max_abs_smd = (
        float(non_available_smd.max()) if non_available_smd.notna().any() else 0.0
    )
    complete_case_risk = (
        "high"
        if max_abs_smd >= 0.50
        or max(available_year_range, available_sector_range, available_size_range)
        >= 0.20
        else "material"
        if max_abs_smd >= 0.25
        or max(available_year_range, available_sector_range, available_size_range)
        >= 0.10
        else "limited"
    )
    selection_errors = review[review["manual_selection_error"]]
    incomplete_manual_checks = review[
        ~review["manual_statement_is_primary_consolidated"]
        | ~review["manual_row_is_total_revenue"]
        | ~review["manual_current_value_matches"]
        | ~review["manual_comparative_value_matches"]
        | ~review["manual_provenance_matches"]
    ]
    blockers: list[str] = []
    if len(selection_errors):
        blockers.append(
            f"manual review detected {len(selection_errors)} selection errors"
        )
    failed_outcomes = int(review["manual_review_outcome"].eq("fail").sum())
    if failed_outcomes:
        blockers.append(f"manual review contains {failed_outcomes} failed outcomes")
    if len(incomplete_manual_checks):
        blockers.append(
            f"{len(incomplete_manual_checks)} manual rows failed at least one required check"
        )
    if int(provenance["rows_with_any_violation"]):
        blockers.append(
            f"provenance integrity has {provenance['rows_with_any_violation']} rows with violations"
        )
    fixed_error_rows: list[pd.Series] = []
    for issue in FIXED_SELECTION_ERRORS:
        matched = frame[
            frame["cik10"].astype(str).str.zfill(10).eq(issue["cik10"])
            & frame["feature_year"].eq(issue["feature_year"])
        ]
        if len(matched) != 1:
            blockers.append(
                f"selection-error regression row missing: {issue['cik10']} t={issue['feature_year']}"
            )
            continue
        fixed_row = matched.iloc[0]
        fixed_error_rows.append(fixed_row)
        if not (
            fixed_row["B_revenues_status"] == "ambiguous"
            and fixed_row["B_revenues_reason"]
            == "component_revenue_without_confirmed_consolidated_total"
            and pd.isna(fixed_row["D5_revenues"])
        ):
            blockers.append(
                f"selection-error regression not fixed: {issue['cik10']} t={issue['feature_year']}"
            )
    verdict = "TARGET B NOT READY TO FREEZE" if blockers else "TARGET B READY TO FREEZE"

    lines = [
        "# Final revenue-resolver audit — target_candidate_v2 PIT B",
        "",
        "Audyt obejmuje wyłącznie feature years 2011–2022 (train 2011–2020, validation 2021–2022). Nie trenowano modeli, nie zmieniono D1–D5, progów ani `score >= 3`, nie użyto feature years 2023–2024 i nie zamrożono targetu.",
        "",
        "## Coverage i class balance",
        "",
        "| Split | N | D5 available | D5 coverage | Target available | Target coverage | Positive N | Positive rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    coverage = {row["split"]: row for row in audit["coverage"]}
    balance = {row["split"]: row for row in audit["class_balance"]}
    for split in ("all", "train", "validation"):
        cov = coverage[split]
        bal = balance[split]
        lines.append(
            f"| {split} | {cov['rows']:,} | {cov['D5_available']:,} | {cov['D5_coverage']:.2%} | "
            f"{cov['target_available']:,} | {cov['target_coverage']:.2%} | "
            f"{bal['positive']:,} | {bal['positive_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "| Target status | N | Udział |",
            "|---|---:|---:|",
        ]
    )
    for status in STATUS_ORDER:
        count = int(frame["target_status"].eq(status).sum())
        lines.append(f"| {status} | {count:,} | {pct(count, total)} |")
    lines.extend(
        [
            "",
            f"Wśród {len(available):,} dostępnych targetów jest {positives:,} obserwacji pozytywnych ({pct(positives, len(available))}). Brakującego lub ambiguous targetu nie przypisano do klasy 0.",
            "",
            "### Coverage sygnałów D1–D5",
            "",
            "| Sygnał | Available | Coverage | Sole missing blocker | Udział niedostępnych non-hard-exclude |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    all_signal_coverage = signal_coverage[signal_coverage["split"].eq("all")].set_index(
        "signal"
    )
    sole_missing_by_signal = sole_missing_signal.set_index("signal")
    for signal in (
        "D1_roa",
        "D2_ocf_assets",
        "D3_current_ratio",
        "D4_liabilities_assets",
        "D5_revenues",
    ):
        lines.append(
            f"| {signal} | {int(all_signal_coverage.at[signal, 'available']):,} | "
            f"{all_signal_coverage.at[signal, 'coverage']:.2%} | "
            f"{int(sole_missing_by_signal.at[signal, 'sole_missing_observations']):,} | "
            f"{sole_missing_by_signal.at[signal, 'share_of_non_hard_excluded_unavailable']:.2%} |"
        )
    lines.extend(
        [
            "",
            "### Status primitives wariantu B",
            "",
            "| Primitive | Selected | Missing | Ambiguous | Not evaluated |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for primitive in primitive_status["primitive"].drop_duplicates():
        counts = (
            primitive_status[primitive_status["primitive"].eq(primitive)]
            .set_index("status")["observation_count"]
            .to_dict()
        )
        lines.append(
            f"| {primitive} | {int(counts.get('selected', 0)):,} | "
            f"{int(counts.get('missing', 0)):,} | {int(counts.get('ambiguous', 0)):,} | "
            f"{int(counts.get('not_evaluated', 0)):,} |"
        )
    lines.extend(
        [
            "",
            "## Semantyczna selekcja revenues",
            "",
            "Resolver dopuszcza wyłącznie jeden roczny wiersz na głównym statement of operations/income wskazanym przez FilingSummary. Wymaga admissible issuer-level revenue label, dokładnie jednego namespaced standardowego conceptu, tego samego annual current/comparative context i zgodności wartości z Company Facts w tym samym anchor accession. Jeżeli etykieta nie wskazuje jawnie totalu, wszystkie pozostałe revenue-bearing lines muszą być nieobecne albo wybrany wiersz musi być potwierdzoną sumą komponentów. Segment/component/dimension, extension total, kilka wiarygodnych wierszy albo niezgodny kontekst powodują `ambiguous/NA`.",
            "",
            f"Ambiguous revenues: **{revenue_ambiguous:,}** ({pct(revenue_ambiguous, total)} populacji).",
            "",
            "| Revenue status/reason | N |",
            "|---|---:|",
        ]
    )
    for _, row in revenue_reasons.iterrows():
        status = "NA" if pd.isna(row["B_revenues_status"]) else row["B_revenues_status"]
        reason = "NA" if pd.isna(row["B_revenues_reason"]) else row["B_revenues_reason"]
        lines.append(f"| {status}: `{reason}` | {int(row['observation_count']):,} |")

    lines.extend(
        [
            "",
            "## Manual stratified review",
            "",
            f"Bezpośrednio sprawdzono {len(review):,} obserwacji względem dokładnego SEC-rendered primary issuer-level consolidated/combined statement. Próba obejmuje {review['feature_year'].nunique()} lat, {review['research_sector'].nunique()} sektorów, {review['B_current_t1_revenues_tag'].nunique()} wybranych tagów oraz {review.get('old_concept_pair', pd.Series(dtype=object)).nunique()} historycznych par konfliktowych.",
            "",
            "| Kategoria próby | N |",
            "|---|---:|",
        ]
    )
    category_counts: dict[str, int] = {}
    for categories in review["review_category"].fillna(""):
        for category in str(categories).split(";"):
            if category:
                category_counts[category] = category_counts.get(category, 0) + 1
    for category, count in sorted(category_counts.items()):
        lines.append(f"| {category} | {count:,} |")
    lines.extend(
        [
            "",
            f"Błędy selekcji wykryte w review: **{len(selection_errors)}**. Wiersze z niezaliczonym dowolnym testem statement/total/value/provenance: **{len(incomplete_manual_checks)}**.",
        ]
    )
    if len(selection_errors):
        lines.extend(
            [
                "",
                "| Spółka | t | Statement | Wybrany wiersz | Błąd |",
                "|---|---:|---|---|---|",
            ]
        )
        for _, row in selection_errors.iterrows():
            lines.append(
                f"| {row['company_name']} | {int(row['feature_year'])} | "
                f"[{row['B_comparative_t_revenues_statement_short_name']}]({row['statement_url']}) | "
                f"{row['B_comparative_t_revenues_statement_label']} | {row['manual_notes']} |"
            )

    lines.extend(
        [
            "",
            "### Błędy selekcji wykryte i naprawione podczas iteracji",
            "",
            "Ręczny review poprzedniej iteracji ujawnił dwa błędy tej samej klasy. Oba są objęte testami regresyjnymi i w finalnym buildzie kończą jako `ambiguous/NA`:",
            "",
            "| Spółka | t | Wykryty błąd | Status po poprawce |",
            "|---|---:|---|---|",
        ]
    )
    fixed_by_key = {
        (str(row["cik10"]).zfill(10), int(row["feature_year"])): row
        for row in fixed_error_rows
    }
    for issue in FIXED_SELECTION_ERRORS:
        fixed_row = fixed_by_key.get((issue["cik10"], issue["feature_year"]))
        final_status = (
            "regression row unavailable"
            if fixed_row is None
            else f"{fixed_row['B_revenues_status']}: `{fixed_row['B_revenues_reason']}`; D5=NA"
        )
        lines.append(
            f"| {issue['company_name']} | {issue['feature_year']} | "
            f"{issue['previous_error']} | {final_status} |"
        )

    lines.extend(
        [
            "",
            "## Provenance integrity",
            "",
            f"Sprawdzono {provenance['selected_primitive_pairs_checked']:,} selected primitive pairs. Rows with any violation: **{provenance['rows_with_any_violation']:,}**; łączna liczba naruszeń: **{provenance['violation_count']:,}**.",
            "",
            "## Missingness i selection bias po finalnej selekcji revenues",
            "",
            "### Rok",
            "",
            "| Rok | N | Available | Missing | Ambiguous | Hard-exclude |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in by_year.iterrows():
        lines.append(
            f"| {int(row['feature_year'])} | {int(row['total']):,} | {row['available_rate']:.2%} | "
            f"{row['missing_rate']:.2%} | {row['ambiguous_rate']:.2%} | {row['hard_exclude_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "### Sektor",
            "",
            "| Sektor | N | Available | Missing | Ambiguous |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for _, row in by_sector.iterrows():
        lines.append(
            f"| {row['research_sector']} | {int(row['total']):,} | {row['available_rate']:.2%} | "
            f"{row['missing_rate']:.2%} | {row['ambiguous_rate']:.2%} |"
        )
    largest_sic = by_sic[by_sic["total"].ge(30)].nsmallest(10, "available_rate")
    lines.extend(
        [
            "",
            "### Najniższe coverage według SIC (N≥30)",
            "",
            "| SIC | Opis | N | Available | Missing | Ambiguous |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for _, row in largest_sic.iterrows():
        lines.append(
            f"| {row['sic']} | {row['sic_description']} | {int(row['total']):,} | "
            f"{row['available_rate']:.2%} | {row['missing_rate']:.2%} | {row['ambiguous_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "### Wielkość spółki",
            "",
            "| Assets-size group | N | Available | Missing | Ambiguous |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for _, row in by_assets.iterrows():
        lines.append(
            f"| {row['assets_size_quartile']} | {int(row['total']):,} | {row['available_rate']:.2%} | "
            f"{row['missing_rate']:.2%} | {row['ambiguous_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "### Cechy finansowe dostępne w t",
            "",
            "| Cecha | Available median | Missing median | Ambiguous median | SMD missing vs available | SMD ambiguous vs available |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for feature in features["feature"].drop_duplicates():
        subset = features[features["feature"].eq(feature)].set_index("status")
        lines.append(
            f"| {feature} | {subset.at['available', 'median']:.4f} | {subset.at['missing', 'median']:.4f} | "
            f"{subset.at['ambiguous', 'median']:.4f} | {subset.at['missing', 'smd_vs_available']:.3f} | "
            f"{subset.at['ambiguous', 'smd_vs_available']:.3f} |"
        )
    lines.extend(
        [
            "",
            "### Liczba brakujących primitives w t",
            "",
            "| Missing primitives t | N | Available | Missing | Ambiguous |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in by_missing_t.iterrows():
        lines.append(
            f"| {int(row['missing_primitives_t'])} | {int(row['total']):,} | {row['available_rate']:.2%} | "
            f"{row['missing_rate']:.2%} | {row['ambiguous_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "### Ocena ryzyk",
            "",
            f"- **Complete-case selection bias: {complete_case_risk} risk.** Rozstęp coverage wynosi {available_year_range:.1%} między latami, {available_sector_range:.1%} między sektorami i {available_size_range:.1%} między obserwowanymi kwartylami assets; największe |SMD| cech finansowych t dla grup niedostępnych względem available wynosi {max_abs_smd:.3f}. Complete cases nie są losową podpróbą.",
            "- **Survivorship bias: nadal istotne ryzyko upstream.** Research universe nie został w tym zadaniu zmieniony i nadal opiera się na bieżącej liście spółek/SIC/sektora. Problem musi być rozwiązany przed finalnym X_t, ale nie jest błędem semantycznej selekcji targetu B.",
            "- **Informative censoring: istotne ryzyko.** Brak anchor t+1, brak annual primitives oraz nierozstrzygnięta prezentacja revenue mogą być związane z delistingiem, M&A, fazą pre-revenue i kondycją finansową. Target pozostaje NA; braków nie imputowano jako 0.",
            "",
            "## Freeze-gate",
            "",
        ]
    )
    if blockers:
        lines.append("Blokujące problemy:")
        lines.append("")
        lines.extend(f"- {blocker}." for blocker in blockers)
        lines.append("")
    else:
        lines.extend(
            [
                "Manual review nie wykazał błędów selekcji, a automatyczny audit provenance nie wykazał naruszeń. Missingness pozostaje ważnym ograniczeniem populacyjnym i wymaga raportowania/robustness, lecz nie podważa semantycznej poprawności finalnego fail-closed resolvera revenues.",
                "",
                "### Specyfikacja gotowa do osobnego aktu zamrożenia",
                "",
                "- `D1_ROA = 1`, gdy ROA spada o co najmniej 3 p.p.",
                "- `D2_OCF/assets = 1`, gdy OCF/assets spada o co najmniej 3 p.p.",
                "- `D3_current_ratio = 1`, gdy current ratio spada o co najmniej 20%.",
                "- `D4_liabilities/assets = 1`, gdy liabilities/assets rośnie o co najmniej 10 p.p.",
                "- `D5_revenues = 1`, gdy revenues spadają o co najmniej 10%.",
                "- `deterioration_score_1y = D1 + D2 + D3 + D4 + D5`; `target_candidate_v2 = 1` dla `score >= 3`.",
                "- `missing`, `ambiguous` i `hard-exclude` pozostają NA i nigdy nie są mapowane na 0.",
                "- Obowiązkowe robustness checks: `score >= 2`, `score >= 4` oraz `operating_performance=max(D1,D2)` z alternative score `>= 3`.",
                "",
            ]
        )
    lines.extend(
        [f"**{verdict}**", "", "Target nie został automatycznie zamrożony.", ""]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    final = {
        **audit,
        "manual_review": {
            **audit["manual_review"],
            "status": "complete",
            "selection_errors": len(selection_errors),
            "failed_required_checks": len(incomplete_manual_checks),
            "selection_errors_found_and_fixed_during_iteration": len(
                FIXED_SELECTION_ERRORS
            ),
        },
        "provenance_integrity": provenance,
        "selection_bias_assessment": {
            "complete_case_selection_bias": f"{complete_case_risk}_risk",
            "available_rate_range_by_year": available_year_range,
            "available_rate_range_by_sector": available_sector_range,
            "available_rate_range_by_assets_quartile": available_size_range,
            "max_abs_smd_non_available_vs_available": max_abs_smd,
            "survivorship_bias": "material_upstream_risk",
            "informative_censoring": "material_risk",
        },
        "verdict": verdict,
        "target_frozen": False,
    }
    Path(f"{PREFIX}_final.json").write_text(
        json.dumps(final, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(verdict)
    print(f"Saved: {REPORT_PATH.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()

"""Compile the final human-readable freeze-gate report for PIT-B.

The report is diagnostic only. It does not freeze or redefine the target,
train models, use feature years 2023--2024, or rebuild the research universe.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
ROWS_PATH = BASE_DIR / "data" / "interim" / "target_candidate_v2_pit_b.csv"
PREFIX = BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_freeze_gate"
REPORT_PATH = Path(f"{PREFIX}.md")
REVIEW_PATH = Path(f"{PREFIX}_revenue_manual_review.csv")
REVENUE_PATH = Path(f"{PREFIX}_revenue_concept_sensitivity.csv")
SHARDS_PATH = BASE_DIR / "data" / "reports" / "target_candidate_v2_pit_b_sec_shards.json"
UNIVERSE_PATH = BASE_DIR / "data" / "processed" / "research_universe.csv"
TICKER_MAP_PATH = BASE_DIR / "data" / "interim" / "sec_ticker_cik_map.csv"
METADATA_PATH = BASE_DIR / "data" / "interim" / "sec_company_metadata.csv"

SIGNALS = (
    "D1_roa",
    "D2_ocf_assets",
    "D3_current_ratio",
    "D4_liabilities_assets",
    "D5_revenues",
)
STATUS_ORDER = ("available", "missing", "ambiguous", "hard_exclude")


def pct(numerator: int | float, denominator: int | float) -> str:
    return f"{numerator / denominator:.2%}" if denominator else "NA"


def reason_count(path: Path, reason: str) -> int:
    table = pd.read_csv(path)
    match = table[table["reason"].eq(reason)]
    return int(match["observation_count"].iloc[0]) if len(match) else 0


def load_table(suffix: str) -> pd.DataFrame:
    return pd.read_csv(f"{PREFIX}_{suffix}.csv")


def main() -> None:
    frame = pd.read_csv(ROWS_PATH, dtype={"cik10": str}, low_memory=False)
    revenue = pd.read_csv(REVENUE_PATH, dtype={"cik10": str})
    review = pd.read_csv(REVIEW_PATH, dtype={"cik10": str})
    audit = json.loads(Path(f"{PREFIX}.json").read_text(encoding="utf-8"))
    shards = json.loads(SHARDS_PATH.read_text(encoding="utf-8"))
    by_year = load_table("status_by_year")
    by_sector = load_table("status_by_sector")
    by_sic_major = load_table("status_by_sic_major")
    by_assets = load_table("status_by_assets_size")
    by_missing_t = load_table("status_by_missing_primitives_t")
    features = load_table("feature_summary")
    signals = load_table("signal_coverage")
    primitive_status = load_table("primitive_status")

    assert int(frame["feature_year"].min()) == 2011
    assert int(frame["feature_year"].max()) == 2022
    assert set(frame["target_status"].dropna()) == set(STATUS_ORDER)
    assert not review["manual_review_outcome"].eq("pending").any()

    total = len(frame)
    status = frame["target_status"].value_counts()
    unavailable = total - int(status["available"])
    available = frame[frame["target_status"].eq("available")]
    positives = int(available["target_candidate_v2"].sum())

    missing_patterns = frame[list(SIGNALS)].isna()
    sole_missing = {
        signal: int(
            (
                missing_patterns[signal]
                & ~missing_patterns[[item for item in SIGNALS if item != signal]].any(axis=1)
            ).sum()
        )
        for signal in SIGNALS
    }

    missing_path = Path(f"{PREFIX}_missing_reasons.csv")
    ambiguous_path = Path(f"{PREFIX}_ambiguous_reasons.csv")
    hard_path = Path(f"{PREFIX}_hard_exclude_reasons.csv")
    revenue_missing = reason_count(
        missing_path, "revenues:primitive_not_reported_for_both_periods"
    )
    revenue_ambiguous = reason_count(
        ambiguous_path, "revenues:higher_priority_context_ambiguous"
    ) + reason_count(ambiguous_path, "revenues:no_common_semantic_strategy")

    lines = [
        "# Final freeze-gate audit — target_candidate_v2 PIT wariant B",
        "",
        "**Werdykt: TARGET B NOT READY TO FREEZE.**",
        "",
        "Audyt jest ograniczony do feature years 2011–2022 (train 2011–2020, validation 2021–2022). Definicja targetu nie została zmieniona, modeli nie trenowano, research universe nie przebudowano i target nie został zamrożony.",
        "",
        "## 1. Populacja PIT B i pokrycie",
        "",
        "| Status | N | Udział | Polityka |",
        "|---|---:|---:|---|",
        f"| available | {int(status['available']):,} | {pct(status['available'], total)} | wszystkie 5 sygnałów jednoznacznie dostępne |",
        f"| missing | {int(status['missing']):,} | {pct(status['missing'], total)} | brak anchor t+1 albo wymaganej primitive; target pozostaje NA |",
        f"| ambiguous | {int(status['ambiguous']):,} | {pct(status['ambiguous'], total)} | nierozstrzygnięta semantyka/ciągłość; target pozostaje NA |",
        f"| hard-exclude | {int(status['hard_exclude']):,} | {pct(status['hard_exclude'], total)} | transition/ambiguous fiscal period albo potwierdzona zmiana reporting entity |",
        "",
        f"Wśród {len(available):,} dostępnych targetów klasa dodatnia ma {positives:,} obserwacji ({pct(positives, len(available))}). Brakującego targetu nigdzie nie oznaczono jako 0.",
        "",
        "| Split | N | Available | Coverage | Positive N | Positive rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for split in ("train", "validation"):
        subset = frame[frame["split"].eq(split)]
        subset_available = subset[subset["target_status"].eq("available")]
        subset_positive = int(subset_available["target_candidate_v2"].sum())
        lines.append(
            f"| {split} | {len(subset):,} | {len(subset_available):,} | "
            f"{pct(len(subset_available), len(subset))} | {subset_positive:,} | "
            f"{pct(subset_positive, len(subset_available))} |"
        )

    lines.extend(
        [
            "",
            "### Dlaczego coverage wynosi 75,81%",
            "",
            f"Łącznie {unavailable:,} obserwacji ({pct(unavailable, total)}) nie trafia do complete case. Największym ograniczeniem jest D5: sam brak D5 przy dostępnych pozostałych czterech sygnałach dotyczy {sole_missing['D5_revenues']:,} wierszy ({pct(sole_missing['D5_revenues'], unavailable)} wszystkich niedostępnych targetów).",
            "",
            "| Sygnał | Coverage | Brak sygnału | Jedyny brakujący sygnał |",
            "|---|---:|---:|---:|",
        ]
    )
    signal_labels = {
        "D1_roa": "D1 ROA",
        "D2_ocf_assets": "D2 OCF/assets",
        "D3_current_ratio": "D3 current ratio",
        "D4_liabilities_assets": "D4 liabilities/assets",
        "D5_revenues": "D5 revenues",
    }
    for signal in SIGNALS:
        row = signals[(signals["signal"].eq(signal)) & (signals["target_status"].eq("all"))].iloc[0]
        missing_n = total - int(row["available_n"])
        lines.append(
            f"| {signal_labels[signal]} | {row['coverage']:.2%} | {missing_n:,} | {sole_missing[signal]:,} |"
        )
    lines.extend(
        [
            "",
            f"Na poziomie przyczyn revenue odpowiada za {revenue_missing:,} braków i {revenue_ambiguous:,} przypadków ambiguous, razem {revenue_missing + revenue_ambiguous:,} wierszy ({pct(revenue_missing + revenue_ambiguous, unavailable)} niedostępnej części populacji). Pozostałe główne przyczyny to brak current liabilities (973), current assets (927), net income (516), liabilities (239), assets (234) i OCF (163); przyczyny mogą współwystępować.",
            "",
            f"Brak anchor t+1 dotyczy 419 obserwacji ({pct(419, total)}). Reporting-entity continuity pozostaje nierozstrzygnięte w 423 obserwacjach; 121 wierszy jest hard-exclude.",
            "",
            "## 2. Selekcja według czasu, branży i wielkości",
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
            "Coverage jest najniższe w latach 2011–2016 (70,68–72,38%), rośnie do 80,48% w 2019 r., a w latach 2020–2022 utrzymuje się w pobliżu 78,3–78,6%. Wzorzec jest zgodny z historyczną ewolucją XBRL i nie jest losowy względem roku.",
            "",
            "### Sektor i SIC",
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
    lines.extend(
        [
            "",
            "| SIC major group | N | Available | Missing | Ambiguous |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for _, row in by_sic_major.iterrows():
        lines.append(
            f"| {row['sic_major_group']} | {int(row['total']):,} | {row['available_rate']:.2%} | "
            f"{row['missing_rate']:.2%} | {row['ambiguous_rate']:.2%} |"
        )
    lines.extend(
        [
            "",
            "Najniższe coverage w liczniejszych dokładnych kodach SIC (N≥50) występuje m.in. dla 1531 — Operative Builders (1,66%), 7359 — Services–Miscellaneous Equipment Rental and Leasing (25,76%), 1000 — Metal Mining (26,40%), 1040 — Gold and Silver Ores (29,07%) oraz 2834 — Pharmaceutical Preparations (51,55%). To pokazuje silną koncentrację braków w budownictwie, wydobyciu i spółkach farmaceutycznych/pre-revenue.",
            "",
            "### Wielkość spółki (kwartyle w obrębie roku)",
            "",
            "| Assets size | N | Available | Missing | Ambiguous |",
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
            "Coverage rośnie od 56,46% w Q1 assets do 89,38% w Q4. Zależność od wielkości jest silna i nie wynika wyłącznie z braku revenue.",
            "",
            "### Cechy finansowe dostępne w t",
            "",
            "| Cecha | Available median | Missing median | Ambiguous median | SMD missing vs available |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    feature_order = (
        "log10 assets t",
        "log10 positive revenues t",
        "ROA t",
        "OCF/assets t",
        "current ratio t",
        "liabilities/assets t",
        "revenues/assets t",
    )
    for feature in feature_order:
        subset = features[features["feature"].eq(feature)].set_index("status")
        lines.append(
            f"| {feature} | {subset.at['available', 'median']:.4f} | {subset.at['missing', 'median']:.4f} | "
            f"{subset.at['ambiguous', 'median']:.4f} | {subset.at['missing', 'smd_vs_available']:.3f} |"
        )
    lines.extend(
        [
            "",
            "Grupa missing jest wyraźnie mniejsza (SMD log assets = −0,926), ma gorsze ROA (SMD −0,510) i OCF/assets (−0,610) oraz niższe revenues/assets (−0,339). Oznacza to selekcję powiązaną z kondycją finansową w t, nie tylko techniczny brak XBRL.",
            "",
            "### Liczba brakujących primitives w t",
            "",
            "| Brakujące primitives t | N | Available | Missing | Ambiguous |",
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
            "Przy kompletnych siedmiu primitives w t target jest dostępny w 91,52% przypadków. Przy jednym braku udział spada do 9,07%, a przy dwóch do 1,53%.",
            "",
            "### Ocena ryzyk selekcji",
            "",
            "- **Complete-case selection bias: wysokie ryzyko.** Dostępność silnie zależy od wielkości, sektora, roku oraz obserwowanej już kondycji finansowej w t. Kierunku obciążenia estymat nie da się wiarygodnie wyznaczyć bez historycznego universe i analizy wag/bounds.",
            "- **Survivorship bias: wysokie i obecnie niekwantyfikowalne ryzyko.** W samej ramie 419 obserwacji nie ma anchor t+1, ale upstream universe pomija część historycznie notowanych podmiotów, więc ta liczba jest dolnym ograniczeniem.",
            "- **Informative censoring: wysokie ryzyko.** Brak t+1 oraz brak przychodów/pełnych sprawozdań jest prawdopodobnie związany z upadłością, delistingiem, M&A, fazą pre-revenue i słabą kondycją. Braków nie wolno traktować jak losowych ani imputować jako target 0.",
            "",
            "## 3. Diagnostyka 1 809 rozbieżnych conceptów revenue",
            "",
            "Alternatywa została wybrana mechanicznie jako następna kompletna strategia w z góry ustalonej kolejności semantycznej — bez użycia D5, score lub targetu.",
            "",
            "| Wynik porównania | Zmiany | Mianownik | Udział |",
            "|---|---:|---:|---:|",
            f"| D5 | {int(revenue['d5_changed'].sum()):,} | {int(revenue['d5_evaluable'].sum()):,} | {pct(revenue['d5_changed'].sum(), revenue['d5_evaluable'].sum())} |",
            f"| deterioration_score | {int(revenue['score_changed'].sum()):,} | {int(revenue['score_evaluable'].sum()):,} | {pct(revenue['score_changed'].sum(), revenue['score_evaluable'].sum())} |",
            f"| target wśród available | {int(revenue['available_target_changed'].sum()):,} | {int((revenue['target_status'].eq('available') & revenue['score_evaluable']).sum()):,} | {pct(revenue['available_target_changed'].sum(), (revenue['target_status'].eq('available') & revenue['score_evaluable']).sum())} |",
            "",
            "D5 zmienia się 100 razy z 0→1 i 78 razy z 1→0. Wśród dostępnych targetów 19 etykiet zmienia się z 0→1, a 20 z 1→0. Efekt nie ma jednostronnego kierunku.",
            "",
            "### Ręczny stratified review",
            "",
            "Próba obejmuje 32 obserwacje ze zmianą D5 lub targetu, wszystkie 8 par strategii, cztery sektory oraz trzy przedziały lat. Nie jest estymatorem częstości błędu dla całych 1 809 przypadków, ponieważ celowo nadreprezentuje przypadki graniczne.",
            "",
            f"W 25/32 przypadkach concept wybrany według obecnego priorytetu reprezentował właściwy skonsolidowany total. W 7/32 ({pct(7, 32)}) właściwszy ekonomicznie był concept alternatywny.",
            "",
            "| Spółka (t) | Para | Dlaczego alternatywa jest właściwsza | Filing |",
            "|---|---|---|---|",
        ]
    )
    wrong = review[review["manual_preferred_economic_concept"].eq("alternative")]
    for _, row in wrong.iterrows():
        lines.append(
            f"| {row['company_name']} ({int(row['feature_year'])}) | {row['concept_pair']} | "
            f"{row['manual_notes']} | [SEC 10-K]({row['manual_evidence_url']}) |"
        )
    lines.extend(
        [
            "",
            "Wynik ręcznej kontroli dowodzi, że sama hierarchia tagów nie wystarcza: ten sam wysoko priorytetowy tag może oznaczać total, komponent, segment, unbilled revenue albo wartość po specyficznej korekcie prezentacyjnej. Nie można więc rozwiązać 1 809 przypadków przez globalny wybór jednego taga ani przez wybór wariantu dającego wygodniejszy target.",
            "",
            "## 4. accepted_at i SEC Submissions shards",
            "",
            f"Pobrano i przetworzono {int(shards['required_shards']):,} wymaganych historycznych shardów SEC Submissions; błędy pobrania: {len(shards['errors'])}. Po uzupełnieniu tylko 3 unikalne accessions nadal nie mają accepted_at (3 użycia jako anchor t oraz 1 użycie jako anchor t+1): Walmart 2011, Honeywell 2011 i Salesforce accession 0001108524-21-000014.",
            "",
            "Konserwatywny fallback: pozostawić surowe `accepted_at` jako NA, ustawić `accepted_at_source = filed_date_conservative_fallback`, a pochodne `feature_available_at` zdefiniować jako **00:00:00 America/New_York w następnym dniu kalendarzowym po SEC filed date**. To jest jawna granica dostępności, a nie imputacja domniemanej godziny przyjęcia.",
            "",
            "## 5. Research universe i survivorship",
            "",
            "Obecny `research_universe.csv` obejmuje 3 730 CIK i został zbudowany z listy `company_tickers.json` pobranej 20 maja 2026 r. Następnie używa bieżących pól SEC submissions (`sic`, `sicDescription`, `entityType`, tickers, exchanges) do klasyfikacji całej historii 2011–2022.",
            "",
            "W konsekwencji może pomijać spółki historycznie notowane, ale dziś nieobecne na liście tickerów, oraz przypisywać wcześniejszym latom dzisiejszy SIC/sektor. Jest to bezpośrednie źródło survivorship bias i historical-classification bias. Problem musi zostać rozwiązany przed budową finalnego X_t przez historyczny, point-in-time universe i klasyfikację spółka–rok. Nie zmienia to samej matematycznej definicji targetu, ale obecna populacja nie może być traktowana jako finalna populacja badania.",
            "",
            "## 6. Werdykt freeze-gate",
            "",
            "**TARGET B NOT READY TO FREEZE.**",
            "",
            "Blokujący problem:",
            "",
            "- Resolver revenue nadal może wybrać pozycję niebędącą skonsolidowanym annual revenue. W 1 809 diagnostykach alternatywa zmienia 178 sygnałów D5, 165 scores i 39 dostępnych etykiet; ręczny stratified review potwierdził błędny wybór najwyższego priorytetu w 7/32 przypadkach. Przed zamrożeniem wybór revenue musi uwzględniać rolę/etykietę pozycji w primary financial statements albo nierozstrzygnięte przypadki muszą być oznaczane jako ambiguous, po czym coverage i selection bias trzeba przeliczyć ponownie.",
            "",
            "Target nie został zamrożony.",
            "",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved: {REPORT_PATH.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()

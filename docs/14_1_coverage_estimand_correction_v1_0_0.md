# Korekta coverage i estimandu v1.0.0

Data: **2026-08-25**

Status: **CURRENT_SUCCESSOR_CORRECTION**

## Cel i zakres korekty

Niniejszy dokument koryguje sposób łączenia statystyk coverage z populacją
badawczą w historycznym audycie gotowości
`docs/14_thesis_readiness_audit_v1_0_5.md`. Audyt zestawił finalne filing-first
universe z wartością `52,46%`, która dotyczyła wcześniejszej populacji
freeze-gate targetu. Nie jest to coverage finalnego universe ani finalnej próby
modelowej.

Historyczny audyt i zamrożona specyfikacja targetu pozostają niezmienione jako
dowód chronologii. W bieżących audytach, dokumentacji i pracy pierwszeństwo ma
niniejsza korekta oraz finalne artefakty aplikacji targetu i selection flow.

## Poprawne mianowniki i wartości

| Zakres | Populacja bazowa | Target dostępny / próba końcowa | Coverage względem populacji bazowej | Rola |
|---|---:|---:|---:|---|
| Historyczny freeze-gate targetu, train + validation | 26 917 | 14 122 | 52,46% | Wyłącznie historyczna kontrola zamrożenia |
| Finalne filing-first universe, lata 2011–2024 | 64 901 | 26 602 z dostępnym targetem | 40,99% | Opis pełnego finalnego universe |
| Pula train 2011–2020 przed filtrem targetu | 47 938 | 19 784 z dostępnym targetem | 41,27% | Selection flow próby modelowej |
| Pula train 2011–2020 po filtrze targetu i `x_t_status` | 47 938 | 19 671 w próbie modelowej | 41,03% | Główna próba modelowa |

W train 2011–2020 filtr dostępności targetu usuwa `28 154` obserwacje, a
dodatkowy wymóg dopuszczalnego `x_t_status` usuwa `113`. Głównym mechanizmem
selekcji jest zatem dostępność porównywalnej etykiety PIT-B, a nie dostępność
cech.

## Bieżący estimand

Główne wyniki modelowe estymują jakość predykcyjną wśród kwalifikujących się
obserwacji emitent–rok z filing-first universe, dla których:

1. dostępna jest porównywalna etykieta PIT-B skonstruowana z kompletu sygnałów
   D1–D5;
2. `x_t_status` dopuszcza obserwację do modelowania;
3. obserwacja należy do właściwej roli okresu raportowego.

Estimand jest warunkowy względem dostępności targetu i cech. Nie obejmuje
automatycznie wszystkich emitentów SEC ani wszystkich kwalifikujących się
company-years z filing-first universe. Zróżnicowanie dostępności targetu według
roku, sektora, wielkości i historii raportowania oznacza wysokie ryzyko
selection bias oraz informative censoring. Wyniki nie identyfikują efektu
przyczynowego.

Role okresów pozostają rozdzielone:

- 2015–2020: development-only pooled OOF, conditional-on-selection;
- 2021–2022: secondary design-exposed/spent-development evidence;
- 2023–2024: temporal holdout z obowiązkowym prior-exposure disclosure.

Nie wolno łączyć tych ról w jeden pooled estimand.

## Źródła liczbowe

- `data/reports/research_universe_target_application_audit.md` — finalne
  universe `64 901`, target available `26 602`, coverage `40,99%`;
- `reports/classical_eda_for_thesis/tables/01_selection_flow.csv` — przepływ
  `47 938 → 19 784 → 19 671`;
- `docs/04_9_target_candidate_v2_pit_b_frozen_specification.md` — historyczny
  freeze-gate `14 122 / 26 917 = 52,46%`;
- `docs/07_1_supervised_ml_pipeline_v1_frozen_specification.md` — warunkowy
  estimand oraz finalna próba supervised.

## Reguła dla kolejnych audytów

Wartości `52,46%` lub `52,5%` nie mogą być przypisywane finalnemu filing-first
universe ani finalnej próbie modelowej. Są poprawne wyłącznie wtedy, gdy tekst
jednoznacznie identyfikuje starszą populację freeze-gate `14 122 / 26 917`.
Kolejny audyt ma traktować tę korektę jako successor wobec odpowiedniego
fragmentu audytu v1.0.5.

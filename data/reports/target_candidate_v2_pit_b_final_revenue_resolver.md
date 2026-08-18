# Final revenue-resolver audit — target_candidate_v2 PIT B

Audyt obejmuje wyłącznie feature years 2011–2022 (train 2011–2020, validation 2021–2022). Nie trenowano modeli, nie zmieniono D1–D5, progów ani `score >= 3`, nie użyto feature years 2023–2024 i nie zamrożono targetu.

## Coverage i class balance

| Split | N | D5 available | D5 coverage | Target available | Target coverage | Positive N | Positive rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| all | 26,917 | 14,987 | 55.68% | 14,122 | 52.46% | 2,167 | 15.34% |
| train | 20,656 | 11,896 | 57.59% | 11,145 | 53.96% | 1,561 | 14.01% |
| validation | 6,261 | 3,091 | 49.37% | 2,977 | 47.55% | 606 | 20.36% |

| Target status | N | Udział |
|---|---:|---:|
| available | 14,122 | 52.46% |
| missing | 4,221 | 15.68% |
| ambiguous | 8,453 | 31.40% |
| hard_exclude | 121 | 0.45% |

Wśród 14,122 dostępnych targetów jest 2,167 obserwacji pozytywnych (15.34%). Brakującego lub ambiguous targetu nie przypisano do klasy 0.

### Coverage sygnałów D1–D5

| Sygnał | Available | Coverage | Sole missing blocker | Udział niedostępnych non-hard-exclude |
|---|---:|---:|---:|---:|
| D1_roa | 25,103 | 93.26% | 370 | 2.92% |
| D2_ocf_assets | 25,612 | 95.15% | 30 | 0.24% |
| D3_current_ratio | 25,241 | 93.77% | 177 | 1.40% |
| D4_liabilities_assets | 25,837 | 95.99% | 74 | 0.58% |
| D5_revenues | 14,987 | 55.68% | 9,761 | 77.02% |

### Status primitives wariantu B

| Primitive | Selected | Missing | Ambiguous | Not evaluated |
|---|---:|---:|---:|---:|
| assets | 26,264 | 234 | 0 | 419 |
| liabilities | 26,197 | 239 | 62 | 419 |
| current_assets | 25,571 | 927 | 0 | 419 |
| current_liabilities | 25,525 | 973 | 0 | 419 |
| revenues | 15,491 | 3,111 | 7,896 | 419 |
| net_income | 25,501 | 516 | 481 | 419 |
| operating_cash_flow | 25,974 | 163 | 361 | 419 |

## Semantyczna selekcja revenues

Resolver dopuszcza wyłącznie jeden roczny wiersz na głównym statement of operations/income wskazanym przez FilingSummary. Wymaga admissible issuer-level revenue label, dokładnie jednego namespaced standardowego conceptu, tego samego annual current/comparative context i zgodności wartości z Company Facts w tym samym anchor accession. Jeżeli etykieta nie wskazuje jawnie totalu, wszystkie pozostałe revenue-bearing lines muszą być nieobecne albo wybrany wiersz musi być potwierdzoną sumą komponentów. Segment/component/dimension, extension total, kilka wiarygodnych wierszy albo niezgodny kontekst powodują `ambiguous/NA`.

Ambiguous revenues: **7,896** (29.33% populacji).

| Revenue status/reason | N |
|---|---:|
| selected: `primary_statement_consolidated_revenue_confirmed` | 15,491 |
| ambiguous: `multiple_primary_statement_revenue_rows` | 4,381 |
| missing: `primitive_not_reported_for_both_periods` | 3,111 |
| ambiguous: `primary_statement_revenue_not_confirmed` | 2,083 |
| ambiguous: `primary_statement_revenue_annual_values_not_confirmed` | 995 |
| NA: `NA` | 419 |
| ambiguous: `component_revenue_without_confirmed_consolidated_total` | 247 |
| ambiguous: `primary_statement_revenue_fact_context_not_confirmed` | 111 |
| ambiguous: `primary_statement_revenue_concept_not_admissible` | 60 |
| ambiguous: `component_revenue_without_absent_complement` | 18 |
| ambiguous: `primary_statement_evidence_unavailable` | 1 |

## Manual stratified review

Bezpośrednio sprawdzono 60 obserwacji względem dokładnego SEC-rendered primary issuer-level consolidated/combined statement. Próba obejmuje 12 lat, 4 sektorów, 6 wybranych tagów oraz 7 historycznych par konfliktowych.

| Kategoria próby | N |
|---|---:|
| historical_concept_conflict | 25 |
| largest_revenue_revision_delta_absolute | 5 |
| largest_revenue_revision_delta_scaled | 5 |
| random_available_D5 | 20 |
| random_available_D5_fill | 7 |

Błędy selekcji wykryte w review: **0**. Wiersze z niezaliczonym dowolnym testem statement/total/value/provenance: **0**.

### Błędy selekcji wykryte i naprawione podczas iteracji

Ręczny review poprzedniej iteracji ujawnił dwa błędy tej samej klasy. Oba są objęte testami regresyjnymi i w finalnym buildzie kończą jako `ambiguous/NA`:

| Spółka | t | Wykryty błąd | Status po poprawce |
|---|---:|---|---|
| Snap-on Inc | 2016 | Net sales was selected although Financial services revenue was a separate revenue-bearing line and no consolidated total was presented. | ambiguous: `component_revenue_without_confirmed_consolidated_total`; D5=NA |
| JONES SODA CO. | 2011 | Product sales revenue was selected although Licensing revenue was a separate revenue-bearing line and no consolidated total was presented. | ambiguous: `component_revenue_without_confirmed_consolidated_total`; D5=NA |

## Provenance integrity

Sprawdzono 170,523 selected primitive pairs. Rows with any violation: **0**; łączna liczba naruszeń: **0**.

## Missingness i selection bias po finalnej selekcji revenues

### Rok

| Rok | N | Available | Missing | Ambiguous | Hard-exclude |
|---:|---:|---:|---:|---:|---:|
| 2011 | 1,487 | 59.38% | 17.22% | 23.34% | 0.07% |
| 2012 | 1,702 | 60.22% | 16.80% | 22.74% | 0.24% |
| 2013 | 1,789 | 61.54% | 17.78% | 20.07% | 0.61% |
| 2014 | 1,908 | 60.59% | 18.50% | 20.55% | 0.37% |
| 2015 | 2,005 | 60.70% | 18.60% | 20.05% | 0.65% |
| 2016 | 2,093 | 61.16% | 17.53% | 20.78% | 0.53% |
| 2017 | 2,193 | 44.46% | 14.00% | 40.90% | 0.64% |
| 2018 | 2,309 | 44.48% | 13.47% | 41.66% | 0.39% |
| 2019 | 2,479 | 48.65% | 12.75% | 38.08% | 0.52% |
| 2020 | 2,691 | 47.38% | 13.23% | 38.87% | 0.52% |
| 2021 | 3,060 | 47.58% | 15.39% | 36.57% | 0.46% |
| 2022 | 3,201 | 47.52% | 15.84% | 36.33% | 0.31% |

### Sektor

| Sektor | N | Available | Missing | Ambiguous |
|---|---:|---:|---:|---:|
| Extended_Candidate | 7,976 | 44.33% | 17.53% | 37.55% |
| Industrials_Manufacturing | 12,152 | 54.44% | 18.25% | 26.93% |
| Retail | 1,791 | 51.26% | 9.10% | 39.36% |
| Technology | 4,998 | 61.08% | 8.84% | 29.63% |

### Najniższe coverage według SIC (N≥30)

| SIC | Opis | N | Available | Missing | Ambiguous |
|---|---|---:|---:|---:|---:|
| 1531 | Operative Builders | 181 | 0.55% | 35.36% | 64.09% |
| 7359 | Services-Equipment Rental & Leasing, NEC | 66 | 3.03% | 28.79% | 66.67% |
| 5810 | Retail-Eating & Drinking Places | 47 | 8.51% | 2.13% | 89.36% |
| 1090 | Miscellaneous Metal Ores | 38 | 10.53% | 65.79% | 23.68% |
| 4610 | Pipe Lines (No Natural Gas) | 56 | 10.71% | 37.50% | 51.79% |
| 2911 | Petroleum Refining | 121 | 13.22% | 9.92% | 76.86% |
| 7011 | Hotels & Motels | 206 | 15.05% | 6.31% | 78.64% |
| 7350 | Services-Miscellaneous Equipment Rental & Leasing | 40 | 17.50% | 10.00% | 72.50% |
| 1000 | Metal Mining | 303 | 18.15% | 66.34% | 14.85% |
| 1040 | Gold and Silver Ores | 258 | 20.16% | 59.69% | 18.60% |

### Wielkość spółki

| Assets-size group | N | Available | Missing | Ambiguous |
|---|---:|---:|---:|---:|
| Q1_assets | 6,584 | 40.46% | 31.74% | 26.75% |
| Q2_assets | 6,576 | 54.30% | 14.86% | 30.46% |
| Q3_assets | 6,575 | 61.66% | 5.00% | 33.20% |
| Q4_assets | 6,581 | 58.15% | 4.16% | 37.52% |
| missing | 601 | 1.00% | 91.68% | 6.16% |

### Cechy finansowe dostępne w t

| Cecha | Available median | Missing median | Ambiguous median | SMD missing vs available | SMD ambiguous vs available |
|---|---:|---:|---:|---:|---:|
| log10 assets t | 8.8460 | 7.3430 | 8.8480 | -1.060 | -0.031 |
| log10 positive revenues t | 8.7974 | 7.8020 | 8.7690 | -0.666 | -0.024 |
| ROA t | 0.0352 | -0.5711 | 0.0116 | -0.511 | -0.101 |
| OCF/assets t | 0.0737 | -0.3493 | 0.0547 | -0.632 | -0.143 |
| current ratio t | 2.0634 | 2.1006 | 1.7793 | 0.462 | 0.018 |
| liabilities/assets t | 0.5209 | 0.4073 | 0.5495 | 0.401 | 0.119 |
| revenues/assets t | 0.8556 | 0.1460 | 0.6208 | -0.432 | -0.240 |

### Liczba brakujących primitives w t

| Missing primitives t | N | Available | Missing | Ambiguous |
|---:|---:|---:|---:|---:|
| 0 | 21,934 | 63.53% | 3.50% | 32.72% |
| 1 | 3,331 | 5.10% | 73.82% | 20.17% |
| 2 | 783 | 0.64% | 53.26% | 44.44% |
| 3 | 352 | 1.99% | 31.82% | 61.65% |
| 4 | 51 | 5.88% | 49.02% | 39.22% |
| 5 | 39 | 2.56% | 51.28% | 41.03% |
| 6 | 7 | 14.29% | 28.57% | 57.14% |
| 7 | 420 | 0.00% | 99.76% | 0.00% |

### Ocena ryzyk

- **Complete-case selection bias: high risk.** Rozstęp coverage wynosi 17.1% między latami, 16.8% między sektorami i 21.2% między obserwowanymi kwartylami assets; największe |SMD| cech finansowych t dla grup niedostępnych względem available wynosi 1.135. Complete cases nie są losową podpróbą.
- **Survivorship bias: nadal istotne ryzyko upstream.** Research universe nie został w tym zadaniu zmieniony i nadal opiera się na bieżącej liście spółek/SIC/sektora. Problem musi być rozwiązany przed finalnym X_t, ale nie jest błędem semantycznej selekcji targetu B.
- **Informative censoring: istotne ryzyko.** Brak anchor t+1, brak annual primitives oraz nierozstrzygnięta prezentacja revenue mogą być związane z delistingiem, M&A, fazą pre-revenue i kondycją finansową. Target pozostaje NA; braków nie imputowano jako 0.

## Freeze-gate

Manual review nie wykazał błędów selekcji, a automatyczny audit provenance nie wykazał naruszeń. Missingness pozostaje ważnym ograniczeniem populacyjnym i wymaga raportowania/robustness, lecz nie podważa semantycznej poprawności finalnego fail-closed resolvera revenues.

### Specyfikacja gotowa do osobnego aktu zamrożenia

- `D1_ROA = 1`, gdy ROA spada o co najmniej 3 p.p.
- `D2_OCF/assets = 1`, gdy OCF/assets spada o co najmniej 3 p.p.
- `D3_current_ratio = 1`, gdy current ratio spada o co najmniej 20%.
- `D4_liabilities/assets = 1`, gdy liabilities/assets rośnie o co najmniej 10 p.p.
- `D5_revenues = 1`, gdy revenues spadają o co najmniej 10%.
- `deterioration_score_1y = D1 + D2 + D3 + D4 + D5`; `target_candidate_v2 = 1` dla `score >= 3`.
- `missing`, `ambiguous` i `hard-exclude` pozostają NA i nigdy nie są mapowane na 0.
- Obowiązkowe robustness checks: `score >= 2`, `score >= 4` oraz `operating_performance=max(D1,D2)` z alternative score `>= 3`.

**TARGET B READY TO FREEZE**

Target nie został automatycznie zamrożony.

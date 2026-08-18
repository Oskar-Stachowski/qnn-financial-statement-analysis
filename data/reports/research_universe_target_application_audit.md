# Audyt zastosowania frozen universe v1.1.0 + frozen target v1.0.0

Target i membership zostały zastosowane bez zmian. Nie zbudowano `X_t` i nie użyto wyników modeli.

## Wynik ogólny

- eligible company-years: **64,901**
- target available: **26,602** (40.99%)
- positive class: **5,055** (19.00% dostępnych)
- missing: 16,076
- ambiguous: 16,386
- hard-exclude: 255
- not computable: 5,582

## Coverage według roku

| Rok | Eligible | Available | Coverage | Positive | Positive rate | Missing | Ambiguous | Hard-exclude | Not computable |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2011 | 5,662 | 1,926 | 34.02% | 364 | 18.90% | 1,271 | 866 | 10 | 1,589 |
| 2012 | 5,364 | 2,317 | 43.20% | 370 | 15.97% | 1,470 | 1,053 | 32 | 492 |
| 2013 | 5,262 | 2,397 | 45.55% | 424 | 17.69% | 1,556 | 879 | 35 | 395 |
| 2014 | 5,148 | 2,301 | 44.70% | 488 | 21.21% | 1,564 | 868 | 20 | 395 |
| 2015 | 4,851 | 2,245 | 46.28% | 508 | 22.63% | 1,458 | 779 | 24 | 345 |
| 2016 | 4,592 | 2,203 | 47.97% | 361 | 16.39% | 1,266 | 774 | 22 | 327 |
| 2017 | 4,408 | 1,550 | 35.16% | 257 | 16.58% | 1,014 | 1,489 | 18 | 337 |
| 2018 | 4,295 | 1,514 | 35.25% | 328 | 21.66% | 946 | 1,502 | 15 | 318 |
| 2019 | 4,150 | 1,642 | 39.57% | 327 | 19.91% | 848 | 1,383 | 15 | 262 |
| 2020 | 4,206 | 1,689 | 40.16% | 220 | 13.03% | 821 | 1,408 | 17 | 271 |
| 2021 | 4,542 | 1,806 | 39.76% | 442 | 24.47% | 991 | 1,481 | 19 | 245 |
| 2022 | 4,423 | 1,742 | 39.39% | 390 | 22.39% | 1,040 | 1,400 | 9 | 232 |
| 2023 | 4,142 | 1,684 | 40.66% | 343 | 20.37% | 925 | 1,316 | 11 | 206 |
| 2024 | 3,856 | 1,586 | 41.13% | 233 | 14.69% | 906 | 1,188 | 8 | 168 |

## Coverage D1–D5

| Sygnał | Available N | Coverage | Positive signal N |
|---|---:|---:|---:|
| D1_roa | 49,331 | 76.01% | 17,443 |
| D2_ocf_assets | 50,237 | 77.41% | 17,255 |
| D3_current_ratio | 49,321 | 75.99% | 14,470 |
| D4_liabilities_assets | 50,446 | 77.73% | 11,680 |
| D5_revenues | 28,611 | 44.08% | 5,017 |

## Najczęstsze przyczyny niedostępności

- `missing` — `revenues:primitive_not_reported_for_both_periods`: 6,977 (43.40%)
- `missing` — `anchor_t1_missing`: 6,375 (39.66%)
- `missing` — `current_assets:primitive_not_reported_for_both_periods`: 1,578 (9.82%)
- `missing` — `current_liabilities:primitive_not_reported_for_both_periods`: 1,418 (8.82%)
- `missing` — `reason_not_recorded`: 1,096 (6.82%)
- `missing` — `net_income:primitive_not_reported_for_both_periods`: 841 (5.23%)
- `missing` — `liabilities:primitive_not_reported_for_both_periods`: 493 (3.07%)
- `missing` — `operating_cash_flow:primitive_not_reported_for_both_periods`: 407 (2.53%)
- `missing` — `assets:primitive_not_reported_for_both_periods`: 379 (2.36%)
- `ambiguous` — `revenues:multiple_primary_statement_revenue_rows`: 8,100 (49.43%)
- `ambiguous` — `revenues:primary_statement_revenue_not_confirmed`: 4,272 (26.07%)
- `ambiguous` — `revenues:primary_statement_revenue_annual_values_not_confirmed`: 1,944 (11.86%)
- `ambiguous` — `reporting_entity_continuity_material_rebasing_unresolved`: 863 (5.27%)
- `ambiguous` — `net_income:no_common_semantic_strategy`: 604 (3.69%)
- `ambiguous` — `operating_cash_flow:no_common_semantic_strategy`: 589 (3.59%)
- `ambiguous` — `revenues:component_revenue_without_confirmed_consolidated_total`: 525 (3.20%)
- `ambiguous` — `revenues:primary_statement_revenue_fact_context_not_confirmed`: 214 (1.31%)
- `ambiguous` — `net_income:higher_priority_context_ambiguous`: 123 (0.75%)
- `ambiguous` — `liabilities:no_common_semantic_strategy`: 109 (0.67%)
- `ambiguous` — `revenues:primary_statement_revenue_concept_not_admissible`: 106 (0.65%)
- `ambiguous` — `net_income:cross_vintage_exact_sign_inversion`: 88 (0.54%)
- `ambiguous` — `operating_cash_flow:cross_vintage_exact_sign_inversion`: 67 (0.41%)
- `ambiguous` — `revenues:component_revenue_without_absent_complement`: 25 (0.15%)
- `ambiguous` — `liabilities:higher_priority_context_ambiguous`: 3 (0.02%)
- `ambiguous` — `revenues:primary_statement_evidence_unavailable`: 2 (0.01%)
- `ambiguous` — `operating_cash_flow:higher_priority_context_ambiguous`: 1 (0.01%)
- `hard_exclude` — `fiscal_period_transition_or_nonannual_gap`: 238 (93.33%)
- `hard_exclude` — `fiscal_period_ambiguous_multiple_anchor_t1`: 30 (11.76%)
- `hard_exclude` — `fiscal_period_ambiguous_multiple_anchor_t`: 8 (3.14%)
- `hard_exclude` — `reverse_acquisition_accounting_predecessor_change`: 2 (0.78%)
- `hard_exclude` — `reverse_recapitalization_accounting_predecessor_change`: 2 (0.78%)
- `hard_exclude` — `retrospective_common_control_combination_reporting_entity_change`: 1 (0.39%)
- `hard_exclude` — `reverse_asset_acquisition_accounting_predecessor_change`: 1 (0.39%)
- `hard_exclude` — `reverse_merger_accounting_predecessor_change`: 1 (0.39%)
- `not_computable` — `anchor_t_not_reconstructable_by_frozen_target_policy`: 3,226 (57.79%)
- `not_computable` — `universe_anchor_target_anchor_mismatch`: 1,522 (27.27%)
- `not_computable` — `companyfacts_unavailable`: 834 (14.94%)

## Selection bias i informative censoring

- complete-case selection bias: **high_risk**
- informative censoring: **high_risk**
- coverage range według roku: 13.96%
- coverage range według sektora: 15.74%
- coverage range według obserwowanych kwartylów assets: 25.04%
- największe |SMD| względem available: 1.147
- recovered-vs-old coverage gap: 17.94%
- inactive-proxy coverage gap: 44.32%
- non-XBRL-role coverage gap: 40.57%

Ocena jest ograniczeniem interpretacyjnym; nie zmienia universe ani targetu.

## Kontrole reprodukowalności

- frozen target overlap rows: 25,853
- frozen target mismatch cells: 0
- provenance violations: 0
- unavailable rows assigned class: 0
- artifact SHA-256: `ea42eb43018b2c8e238e2c4757260bb692e27edd5429628e28892f360f0f7f7d`

## Werdykt: FROZEN UNIVERSE v1.1.0 + FROZEN TARGET v1.0.0 CORRECTLY AND REPRODUCIBLY BUILT

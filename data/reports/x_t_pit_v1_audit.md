# Finalny audyt przed freeze — raw point-in-time `X_t v1`

Data audytu: **2026-08-19**
Zakres decyzji: **wyłącznie development 2011–2022**
Modele: **nie trenowano**
Preprocessing ML: **nie wykonano**

## 1. Artefakt i invariants

- Raw rows wszystkich lat: **64,901** — dokładnie jeden dla każdego eligible company-year universe v1.1.0.
- Development rows 2011–2022: **56,903**.
- Kolumny raw artifact: **1,072**.
- Exact-accession provenance errors: **0**.
- Prediction-timestamp policy errors: **0**.
- Primitive filed/accepted provenance errors: **0**.
- Anchors inne niż oryginalny 10-K: **0**.
- `feature_available_at != prediction_timestamp` dla available features: **0**.
- Lower-precision timestamp fallback w development: **0**.
- Target/provenance columns w raw schema: **0**.
- Imputacja/winsoryzacja/skalowanie/feature selection: **nie wykonano**.
- Frozen universe SHA-256: `a449c8145d1f46f954f12b1dfc079bb0b367c4f7f5edf3332a983ad7c1fb8182`.
- Frozen target SHA-256: `473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff`.
- Raw X_t SHA-256: `0f1b35b9ffbb1fb1c1cdfb7dff12e3efd8fb38f60b33407ff2b2a8fb6b88397f`.

## 2. Status wierszy

| x_t_status | observations | share |
|---|---|---|
| available_core | 45797 | 80.48% |
| partially_available | 6086 | 10.70% |
| not_available_non_xbrl | 3927 | 6.90% |
| missing | 727 | 1.28% |
| ambiguous | 366 | 0.64% |

## 3. Coverage cech

### 3.1. Primitive

| primitive | role | observations | selected | coverage | missing | ambiguous | hard_exclude | not_available_non_xbrl |
|---|---|---|---|---|---|---|---|---|
| assets | current_t | 56903 | 52116 | 91.59% | 672 | 188 | 0 | 3927 |
| assets | same_anchor_pair | 56903 | 47293 | 83.11% | 4728 | 955 | 0 | 3927 |
| liabilities | current_t | 56903 | 51733 | 90.91% | 968 | 275 | 0 | 3927 |
| liabilities | same_anchor_pair | 56903 | 46947 | 82.50% | 4137 | 1892 | 0 | 3927 |
| current_assets | current_t | 56903 | 49968 | 87.81% | 2820 | 188 | 0 | 3927 |
| current_assets | same_anchor_pair | 56903 | 45145 | 79.34% | 6876 | 955 | 0 | 3927 |
| current_liabilities | current_t | 56903 | 49899 | 87.69% | 2890 | 187 | 0 | 3927 |
| current_liabilities | same_anchor_pair | 56903 | 45181 | 79.40% | 6842 | 953 | 0 | 3927 |
| revenues | current_t | 56903 | 30049 | 52.81% | 8051 | 14876 | 0 | 3927 |
| revenues | same_anchor_pair | 56903 | 26426 | 46.44% | 12722 | 13828 | 0 | 3927 |
| net_income | current_t | 56903 | 50168 | 88.16% | 1579 | 1229 | 0 | 3927 |
| net_income | same_anchor_pair | 56903 | 45069 | 79.20% | 5203 | 2704 | 0 | 3927 |
| operating_cash_flow | current_t | 56903 | 50927 | 89.50% | 806 | 1243 | 0 | 3927 |
| operating_cash_flow | same_anchor_pair | 56903 | 45696 | 80.31% | 4770 | 2510 | 0 | 3927 |

### 3.2. Features

| block | feature | available | coverage | missing | ambiguous | not_computable | not_available_non_xbrl |
|---|---|---|---|---|---|---|---|
| L | log_assets_t | 51606 | 90.69% | 672 | 188 | 510 | 3927 |
| L | roa_t | 49301 | 86.64% | 1968 | 1232 | 475 | 3927 |
| L | ocf_to_assets_t | 50209 | 88.24% | 1114 | 1246 | 407 | 3927 |
| L | current_ratio_t | 48941 | 86.01% | 3818 | 190 | 27 | 3927 |
| L | liabilities_to_assets_t | 51004 | 89.63% | 1190 | 278 | 504 | 3927 |
| L | working_capital_to_assets_t | 48761 | 85.69% | 3827 | 192 | 196 | 3927 |
| L | accruals_to_assets_t | 48976 | 86.07% | 2260 | 1335 | 405 | 3927 |
| D | asset_growth_1y | 46603 | 81.90% | 4728 | 955 | 690 | 3927 |
| D | delta_roa_1y | 43945 | 77.23% | 5710 | 2707 | 614 | 3927 |
| D | delta_ocf_to_assets_1y | 44804 | 78.74% | 5138 | 2513 | 521 | 3927 |
| D | current_ratio_change_1y | 43878 | 77.11% | 7876 | 956 | 266 | 3927 |
| D | delta_liabilities_to_assets_1y | 45991 | 80.82% | 4419 | 1895 | 671 | 3927 |
| R | log1p_revenues_t | 30044 | 52.80% | 8051 | 14876 | 5 | 3927 |
| R | profit_margin_t | 28180 | 49.52% | 8642 | 15121 | 1033 | 3927 |
| R | ocf_margin_t | 28907 | 50.80% | 7930 | 15112 | 1027 | 3927 |
| R | asset_turnover_t | 29880 | 52.51% | 8082 | 14879 | 135 | 3927 |
| R | revenue_growth_1y | 25345 | 44.54% | 12722 | 13828 | 1081 | 3927 |

Szczegółowe rozkłady każdego primitive i feature według roku, sektora,
historycznego SIC, kwartylu wielkości, registrant role i dostępności XBRL
zapisano w osobnych CSV. Revenue module pozostaje osobnym blokiem i
jego brak nie usuwa wiersza ani cech L/D.

## 4. Revenue resolver i manual stratified review

- Manual review rows: **90**.
- Wykryte błędy selekcji/provenance: **0**.
- Brak lokalnego primary-statement evidence: **1**.
- Z tego potwierdzone SEC `not_found`: **1**;
  Filing Summary bez jednoznacznie rozpoznanego skonsolidowanego rachunku
  wyników: **0**; niepobrane/błędne lub
  niezweryfikowane: **0**.
- Source download inventory: **8,218 / 8,218**,
  `complete=True`, błędy techniczne:
  **0**.
- XBRL rows bez lokalnego Company Facts cache: **0**
  w **0** CIK.
- Z tego SEC Company Facts `not_found` potwierdzone w istniejącym download
  inventory: **0** wierszy; braki
  niezweryfikowane: **0**.

| feature_year | missing_statement_evidence |
|---|---|
| 2014 | 1 |

Nie wykryto błędów w zweryfikowanej próbie.

Brak pliku evidence nie jest interpretowany jako ekonomiczny brak revenues:
resolver działa fail-closed i zwraca `ambiguous/NA`. Jedyny taki przypadek po
backfillu ma potwierdzony status SEC `not_found`; nie pozostały niepobrane,
błędne ani niezweryfikowane luki lokalnego cache.

## 5. Pozostałe primitive, okresy i outliery

- Manual source-provenance checks poza revenues: **182**.
- Błędy w tej próbie: **0**.
- Available non-finite feature values: **0**.
- Selected non-finite primitive values: **0**.
- Current primitive sign audit: `{"assets": {"selected": 52116, "negative": 0, "zero": 510, "positive": 51606, "nonfinite": 0}, "liabilities": {"selected": 51733, "negative": 0, "zero": 84, "positive": 51649, "nonfinite": 0}, "current_assets": {"selected": 49968, "negative": 0, "zero": 275, "positive": 49693, "nonfinite": 0}, "current_liabilities": {"selected": 49899, "negative": 0, "zero": 29, "positive": 49870, "nonfinite": 0}, "revenues": {"selected": 30049, "negative": 5, "zero": 1039, "positive": 29005, "nonfinite": 0}, "net_income": {"selected": 50168, "negative": 28427, "zero": 24, "positive": 21717, "nonfinite": 0}, "operating_cash_flow": {"selected": 50927, "negative": 22910, "zero": 121, "positive": 27896, "nonfinite": 0}}`.
- Standardowe przesunięcia 52/53-week period end są rozstrzygane wyłącznie
  wewnątrz exact accession; materialna różnica pozostaje ambiguous.
- Near-zero denominators są flagowane, ale dodatnia wartość nie zmienia
  availability.

## 6. Revision diagnostic — current `t` vs later comparative `t`

Porównanie z later comparative jest zapisane wyłącznie w oddzielnym raporcie
audytowym i nie występuje w raw `X_t`. Nie zastępuje wartości current i nie
wpływa na resolver. Podsumowanie:

```json
{
  "assets": {
    "comparable": 45102,
    "median_delta": 0.0,
    "median_absolute_relative_delta": 0.0,
    "p99_absolute_relative_delta": 0.6745416117002587
  },
  "liabilities": {
    "comparable": 44748,
    "median_delta": 0.0,
    "median_absolute_relative_delta": 0.0,
    "p99_absolute_relative_delta": 0.962467329346273
  },
  "current_assets": {
    "comparable": 43199,
    "median_delta": 0.0,
    "median_absolute_relative_delta": 0.0,
    "p99_absolute_relative_delta": 0.9413682890622187
  },
  "current_liabilities": {
    "comparable": 43173,
    "median_delta": 0.0,
    "median_absolute_relative_delta": 0.0,
    "p99_absolute_relative_delta": 0.8665870244786806
  },
  "revenues": {
    "comparable": 23979,
    "median_delta": 0.0,
    "median_absolute_relative_delta": 0.0,
    "p99_absolute_relative_delta": 0.6224658459664878
  },
  "net_income": {
    "comparable": 43246,
    "median_delta": 0.0,
    "median_absolute_relative_delta": 0.0,
    "p99_absolute_relative_delta": 1.7088967531474348
  },
  "operating_cash_flow": {
    "comparable": 44041,
    "median_delta": 0.0,
    "median_absolute_relative_delta": 0.0,
    "p99_absolute_relative_delta": 1.5674656569702412
  }
}
```

## 7. Missingness, selection bias i target availability

```json
{
  "observations": 56903,
  "x_core_available": 45797,
  "x_core_coverage": 0.804825756111277,
  "target_available": 23332,
  "target_coverage": 0.4100311055656117,
  "supervised_L_available": 22679,
  "supervised_L_coverage": 0.39855543644447566,
  "x_core_log_assets_smd_available_vs_unavailable": 0.5073417048498345,
  "target_log_assets_smd_available_vs_unavailable": 0.5486041637363672,
  "x_status_by_target_status": {
    "ambiguous": {
      "ambiguous": 52,
      "available_core": 11989,
      "missing": 39,
      "not_available_non_xbrl": 38,
      "partially_available": 1764
    },
    "available": {
      "ambiguous": 7,
      "available_core": 22679,
      "missing": 4,
      "not_available_non_xbrl": 103,
      "partially_available": 539
    },
    "hard_exclude": {
      "ambiguous": 7,
      "available_core": 150,
      "missing": 12,
      "not_available_non_xbrl": 5,
      "partially_available": 62
    },
    "missing": {
      "ambiguous": 107,
      "available_core": 10171,
      "missing": 413,
      "not_available_non_xbrl": 82,
      "partially_available": 3472
    },
    "not_computable": {
      "ambiguous": 193,
      "available_core": 808,
      "missing": 259,
      "not_available_non_xbrl": 3699,
      "partially_available": 249
    }
  },
  "complete_case_selection_bias_risk": "high",
  "informative_censoring_risk": "high"
}
```

Ryzyko complete-case selection bias pozostaje wysokie. X availability i target
availability są odrębnymi mechanizmami selekcji; raw artifact zachowuje także
wiersze bez targetu i bez pełnego core.

## 8. Economic groups i temporal split

```json
{
  "economic_groups": 9368,
  "rows_missing_economic_group_id": 0,
  "rows_missing_economic_statement_scope_id": 0,
  "groups_with_multiple_ciks": 52,
  "groups_spanning_train_and_validation": 4012,
  "maximum_company_year_rows_per_group": 28,
  "duplicate_statement_scope_year_rows": 0,
  "economic_group_id_is_predictor": false,
  "primary_split_changed": false
}
```

`economic_group_id` nie jest predictorem i nie zmienia głównego temporal splitu.

### 8.1. Joint filings i secondary statement scopes

```json
{
  "joint_co_registrant_rows": 247,
  "joint_co_registrant_filing_xbrl_rows": 230,
  "joint_co_scope_specific_non_xbrl_rows": 226,
  "joint_co_scope_xbrl_available_rows": 4,
  "joint_co_scope_xbrl_exact_anchor_records_unavailable": 0,
  "joint_co_scope_xbrl_core_available": 2,
  "joint_co_scope_xbrl_core_coverage": 0.5,
  "interpretation": "filing-level XBRL availability is separated from statement-scope availability using the audited XBRL entity identifier"
}
```

```json
{
  "selected_joint_instance_primitive_facts": 33,
  "unique_instance_files": 2,
  "instance_file_sha256": {
    "data/raw/sec_historical_universe/registrant_role_evidence/0001047469-14-003617/denparp-20131231.xml": "d7eefef53102b9a2a674dc7ed43e624e731c1657bd07dc63cf0f9243f6ad796c",
    "data/raw/sec_historical_universe/registrant_role_evidence/0001104659-14-009852/cld-20131231.xml": "07d612d9fe0ea2d561a23096e688c088603dbe736c7e975b48bec1987ad29805"
  },
  "missing_instance_files": [],
  "selected_facts_missing_context_id": 0,
  "selected_facts_with_invalid_dimension_provenance": 0
}
```

Frozen universe zachowuje tylko potwierdzone odrębne statement scopes.
Filing-level XBRL nie jest automatycznie przypisywany wszystkim registrantom:
scope bez zgodnego XBRL entity identifier otrzymuje
`not_available_non_xbrl`, natomiast zgodna wtórna instancja jest odczytywana
bezpośrednio z lokalnego filing package. Wierszy nie usuwa się ani nie
przepisuje na primary registranta.

## 9. Test 2023–2024

Wiersze testowe zostały utworzone mechanicznie tą samą polityką, ale ich
coverage, wartości, outliery, missingness i targety nie zostały użyte w tym
audycie ani w decyzji o resolverze. Nie trenowano modeli.

## 10. Blokujące problemy

- Brak blokujących problemów.

## 11. Werdykt

**X_T V1 READY TO FREEZE**

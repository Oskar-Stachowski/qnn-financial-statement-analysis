# Frozen raw point-in-time X_t specification — v1.0.0

Data formalnego zamrożenia: **2026-08-19**
Status: **FROZEN — raw point-in-time X_t only**

## 1. Decyzja i granica zamrożenia

Raw point-in-time `X_t` zostaje formalnie zamrożony jako `x_t_pit` w wersji
`1.0.0`. Jednostką artefaktu jest każdy `eligible` company-year z frozen
historical research universe v1.1.0. Zamrożenie obejmuje:

- definicje i przypisanie cech do bloków `L`, `D` i `R`;
- exact frozen-universe anchor policy;
- primitive, semantic, period i primary-statement resolvers;
- `prediction_timestamp`, `feature_available_at` i precision flags;
- politykę comparative `t-1` z tego samego accession;
- fail-closed `missing`, `ambiguous`, `not_computable` i non-XBRL policy;
- surowe primitives, statusy i pełne provenance;
- finalne decyzje negative-sign sanity check;
- schemat raw artefaktu: **64 901 wierszy i 1 072 kolumny**;
- byte-identical raw artifact o SHA-256:

```text
0f1b35b9ffbb1fb1c1cdfb7dff12e3efd8fb38f60b33407ff2b2a8fb6b88397f
```

Zamrożenie nie obejmuje supervised sample policy, łączenia z targetem,
imputacji, missing indicators, winsoryzacji, skalowania, feature selection,
modeli, architektur, hiperparametrów ani reguł wyboru finalnego modelu.

## 2. Niezmienne zależności upstream

`X_t v1.0.0` jest zbudowany wyłącznie dla `membership_status == eligible` z:

- frozen historical research universe `research_universe_pit v1.1.0`,
  SHA-256 `a449c8145d1f46f954f12b1dfc079bb0b367c4f7f5edf3332a983ad7c1fb8182`;
- frozen target `target_candidate_v2_pit_b v1.0.0`, SHA-256
  `473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff`.

Target nie uczestniczy w konstrukcji ani availability `X_t`. Jego hash jest
kontrolowany wyłącznie jako upstream invariant. Formalny freeze `X_t` nie
zmienia żadnego bajtu targetu ani universe.

## 3. Jednostka obserwacji i zachowanie wierszy

Raw artefakt zawiera dokładnie jeden wiersz dla każdego z **64 901** eligible
company-years frozen universe. Wiersz nie jest usuwany z powodu:

- braku pojedynczej lub wielu cech;
- braku pełnego bloku `L`, `D` lub `R`;
- braku targetu `t+1`;
- statusu non-XBRL;
- późniejszego delistingu, M&A lub nieaktywności spółki.

CIK, `economic_statement_scope_id`, `economic_group_id`, historyczny SIC i
sektor pozostają metadata/provenance. Nie są automatycznie predictorami bloku
financial; `economic_group_id` nigdy nie jest cechą modelową.

## 4. Zamrożony anchor i point-in-time policy

Dla company-year `(i,t)` jedynym dozwolonym anchorem `X_t` jest exact accession
wybrany i zamrożony w research universe v1.1.0: najwcześniejszy oryginalny
`10-K` za rok `t`.

Obowiązuje:

1. wszystkie current primitives `t` pochodzą wyłącznie z exact anchor;
2. comparative primitives `t-1` mogą pochodzić wyłącznie z annual comparative
   contexts przedstawionych w tym samym exact anchor `10-K t`;
3. późniejsze `10-K`, `10-K/A`, restatements i późniejsze Company Facts nie są
   fallbackiem;
4. dane `t+1`, target provenance i status targetu nie mogą wystąpić w raw
   `X_t`;
5. annual periods muszą przejść fiscal-period validation; standardowe lata
   52/53-tygodniowe są dopuszczalne, a transition/ambiguous period działa
   fail-closed;
6. issuer-level context nie może zostać zastąpiony segment/component context;
7. current i comparative w cesze dynamicznej muszą mieć zgodną definicję
   ekonomiczną oraz jedno accession.

## 5. Timestamp i dostępność cech

Podstawowa reguła:

```text
prediction_timestamp = anchor_accepted_at
feature_available_at = prediction_timestamp
```

Timestamp accepted jest normalizowany do `America/New_York`. Jeżeli
historyczny `accepted_at` pozostaje niedostępny po sprawdzeniu źródeł, jedynym
dopuszczalnym fallbackiem jest:

```text
prediction_timestamp = 00:00 ET następnego dnia kalendarzowego po filed_date
```

Fallback otrzymuje `prediction_timestamp_lower_precision = true` i precision
`filed_date_next_day_midnight_et`. Nie wolno arbitralnie imputować godziny tego
samego dnia. Dla każdej available feature timestamp jest nie późniejszy niż i
w praktyce równy `prediction_timestamp`, ponieważ wszystkie primitives pochodzą
z tego samego anchor filing.

## 6. Zamrożone primitives i resolvery

Raw `X_t` zachowuje siedem primitives:

```text
assets
liabilities
current_assets
current_liabilities
revenues
net_income
operating_cash_flow
```

Jawne concept priorities, dopuszczalne derived strategies, annual
instant/duration validation oraz reguły zgodności current/comparative są
zamrożone przez `configs/target_candidate_v2_pit.yaml`,
`src/data/target_candidate_v2_pit.py` i `src/data/x_t_pit.py`.

Revenue resolver dodatkowo wymaga jednoznacznego potwierdzenia skonsolidowanej
annual revenue row na primary statement of operations/income exact accession.
Segment, component, project, collaboration, unbilled lub note-only revenue nie
może być wybierane heurystycznie. Brak jednoznacznego primary-statement
potwierdzenia daje `ambiguous/NA`.

## 7. Zamrożone bloki cech

### 7.1. L — core financial levels

```text
log_assets_t                  = ln(assets_t), assets_t > 0
roa_t                         = net_income_t / assets_t
ocf_to_assets_t               = operating_cash_flow_t / assets_t
current_ratio_t               = current_assets_t / current_liabilities_t
liabilities_to_assets_t       = liabilities_t / assets_t
working_capital_to_assets_t   = (current_assets_t - current_liabilities_t) / assets_t
accruals_to_assets_t          = (net_income_t - operating_cash_flow_t) / assets_t
```

Każdy mianownik musi być ściśle dodatni. Nie obowiązuje globalny próg
`1 000 USD`; wartości near-zero są wyłącznie diagnostyką.

### 7.2. D — core dynamics comparative t-1 → current t

W poniższych wzorach indeks `t-1` oznacza comparative annual value pokazane w
exact anchor `10-K t`, nie wartość pobraną z wcześniejszego lub późniejszego
filingu:

```text
asset_growth_1y                  = assets_t / assets_t-1 - 1
delta_roa_1y                     = roa_t - roa_t-1
delta_ocf_to_assets_1y           = ocf_to_assets_t - ocf_to_assets_t-1
current_ratio_change_1y          = current_ratio_t / current_ratio_t-1 - 1
delta_liabilities_to_assets_1y   = liabilities_to_assets_t - liabilities_to_assets_t-1
```

Wymagane mianowniki current/comparative są dodatnie. Brak zgodnej pary nie jest
uzupełniany innym filingiem.

### 7.3. R — revenue module

```text
log1p_revenues_t     = ln(1 + revenues_t), revenues_t >= 0
profit_margin_t      = net_income_t / revenues_t
ocf_margin_t         = operating_cash_flow_t / revenues_t
asset_turnover_t     = revenues_t / assets_t
revenue_growth_1y    = revenues_t / revenues_t-1 - 1
```

Dla marginów i growth odpowiedni denominator revenues musi być dodatni.
`asset_turnover_t` wymaga dodatnich assets. Ujemne, prawidłowo raportowane
revenues pozostają w primitive provenance, ale cechy wymagające nieujemnej lub
dodatniej revenue domain otrzymują `not_computable`.

Z góry zdefiniowane przyszłe porównania modelowe pozostają:

```text
L
L + D
L + D + R
```

Nie wolno wybierać bloków na podstawie test set 2023–2024.

## 8. Fail-closed status policy

Dozwolone feature statuses to:

```text
available
missing
ambiguous
not_computable
not_available_non_xbrl
```

Brak lub niejednoznaczność primitive propaguje się do wszystkich zależnych
cech. Nie wolno mapować braku na zero, zmieniać znaku, wybierać alternatywnego
conceptu dla poprawy coverage ani używać późniejszego filingu. Non-XBRL
registrant pozostaje w raw artefakcie z `x_t_status =
not_available_non_xbrl`. Brak ekonomicznie poprawnego mianownika daje
`not_computable`, nie imputowaną wartość.

Raw artifact nie zawiera missing indicators. Mogą powstać dopiero w osobno
zamrażanej warstwie ML, z obowiązkową ablation bez nich.

## 9. Finalny negative-sign sanity check

Przed freeze sprawdzono wszystkie 25 selected current primitive cases z:

```text
assets < 0
liabilities < 0
current_assets < 0
current_liabilities < 0
revenues < 0
```

Każdy przypadek zweryfikowano względem exact anchor filing index, primary
original 10-K i primary statement:

- **5** ujemnych revenues było faktycznie raportowanych i ekonomicznie
  uzasadnionych; zachowano je bez zmiany;
- **16** przypadków było błędem znaku, tagu lub kontekstu XBRL;
- **4** prezentacje ujemnych assets/current assets pozostały ekonomicznie
  nierozstrzygalne;
- **20** błędnych lub nierozstrzygalnych primitives ustawiono jako
  `ambiguous/NA`;
- nie odwracano heurystycznie znaku i nie podstawiano alternatywnego factu;
- wszystkie zależne features oraz same-anchor pairs zostały przeliczone.

Decyzje i hashe primary evidence są częścią frozen package w
`configs/x_t_pit_v1_negative_sign_review.yaml` oraz raportach
`x_t_pit_v1_negative_sign_*`.

## 10. Zamrożone provenance i schema invariants

Dla primitive zachowywane są co najmniej: value/status/reason, strategy,
tag/concept, source tags i values, accession, start/end, duration, filed,
accepted timestamp, role, fiscal focus, frame, candidate count, statement
metadata, context/dimensions, source cache path oraz availability precision.

Raw schema blokuje:

- target, D1–D5 i target provenance;
- `t+1` oraz anchor `t+1`;
- accession różny od frozen-universe anchor;
- niedozwolony status;
- duplicate `research_universe_company_year_id`;
- usunięcie któregokolwiek eligible wiersza;
- użycie `economic_group_id`, historycznego SIC lub sektora jako automatycznej
  cechy bloku financial.

## 11. Zakres temporalny i stan w chwili freeze

Ta sama zamrożona polityka została mechanicznie zastosowana do feature years
`2011–2024`. Decyzje metodologiczne i resolver audits korzystały wyłącznie z
development `2011–2022`; test `2023–2024` nie był używany do wyboru cech,
resolverów ani parametrów.

Finalny development audit obejmuje **56 903** wiersze. Statusy:

| `x_t_status` | Liczba |
|---|---:|
| `available_core` | 45 797 |
| `partially_available` | 6 086 |
| `not_available_non_xbrl` | 3 927 |
| `missing` | 727 |
| `ambiguous` | 366 |

Audit wykazał zero exact-accession, timestamp, filing-provenance i non-finite
errors oraz zero blocking issues. Werdykt przed formalnym freeze:
`X_T V1 READY TO FREEZE`.

## 12. Elementy jawnie niezamrożone

Następujące elementy wymagają osobnej pre-registration, audytu i freeze:

- supervised sample eligibility i sposób łączenia `X_t` z targetem;
- imputacja;
- missing indicators oraz ablation;
- winsoryzacja lub clipping;
- skalowanie;
- feature selection;
- cross-validation i group-aware diagnostics;
- modele klasyczne, quantum/hybrid, ich architektury i hiperparametry;
- progi klasyfikacji i metryki wyboru modelu.

Żaden z tych elementów nie został wykonany ani pośrednio utrwalony w raw
artefakcie.

## 13. Reprodukcja i kontrola zmian

Maszynowo czytelny manifest znajduje się w
`configs/x_t_pit_v1_freeze_manifest.yaml`. Hashuje konfigurację, semantic
resolvers, kod budowy/audytu, testy i finalne evidence. Duży raw CSV pozostaje
poza Git i jest kontrolowany przez liczbę wierszy, kolumn, rozmiar oraz
SHA-256.

Manifest celowo nie hashuje sam siebie ani freeze-lock testu, aby uniknąć
samoodniesienia. Commit zawierający manifest, specyfikację, konfigurację, kod,
testy i raporty jest autorytatywną wersją repozytorium dla freeze.

Po zamrożeniu zmiana któregokolwiek elementu objętego zakresem wymaga:

1. nowej wersji `X_t`;
2. datowanego uzasadnienia niezależnego od wyników modeli i testu;
3. ponownego raw build oraz pełnego development audit;
4. nowego manifestu i zachowania v1.0.0 jako punktu odniesienia;
5. jawnego porównania schema, coverage i obserwacji zmieniających wartości lub
   availability.

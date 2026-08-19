# Audyt obecnego feature pipeline i projekt polityki point-in-time `X_t`

Data audytu: **2026-08-18**
Status: **POLITYKA ZAAKCEPTOWANA — implementacja kandydata `X_t v1`; jeszcze nie frozen**

## 1. Decyzja w skrócie

Obecnego `data/interim/sec_facts_wide.csv` ani kodu przeniesionego do
`LEGACY/pre_pit_modeling/` nie należy używać do finalnego eksperymentu. Są
przydatne jako prototyp i diagnostyka coverage, ale nie spełniają wymagań
point-in-time.

Finalny feature pipeline powinien być zbudowany od nowa jako konsument
zamrożonego historical research universe `v1.1.0`. Dla każdego eligible
company-year musi najpierw przejąć **dokładny** anchor accession zapisany w
universe, a dopiero potem szukać faktów wyłącznie wewnątrz tego accession.
Nie wolno ponownie wybierać anchoru na podstawie dostępności lub jakości cech.

Rekomendowany główny `X_t` składa się z:

1. podstawowego bloku cech bilansowych, rentowności i cash flow;
2. zmian `t-1 -> t` obliczonych z current `t` i comparative `t-1`
   przedstawionych w tym samym anchor 10-K za `t`;
3. osobnego, opcjonalnego bloku revenue-dependent, ponieważ konserwatywna
   walidacja przychodów ma wyraźnie niższe coverage;
4. historycznego sektora/SIC jako metadata/control variables, bez
   automatycznego włączania do głównego financial feature block.

Brak jednej cechy nie może usuwać company-year z universe i nie może być
uzupełniany późniejszym filingiem. Imputacja, winsoryzacja, skalowanie i feature
selection należą do osobnej warstwy ML i muszą być dopasowywane wyłącznie na
danych treningowych lub wewnątrz foldów treningowych.

W audycie nie zmieniono ani nie zapisano ponownie:

- `target_candidate_v2_pit_b` `v1.0.0`, SHA-256
  `473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff`;
- historical research universe `v1.1.0`, SHA-256
  `a449c8145d1f46f954f12b1dfc079bb0b367c4f7f5edf3332a983ad7c1fb8182`.

Nie zbudowano `X_t`, nie trenowano modeli i nie użyto feature years 2023–2024
do wyboru polityki ani cech.

## 2. Zakres audytu i wykorzystane materiały

### 2.1. Aktywny kod i konfiguracje

- `src/data/05_inventory_xbrl_tags.py`;
- `src/data/06_parse_companyfacts.py`;
- `src/data/07_sanity_check_sec_facts.py`;
- `configs/sec_tags.yaml`;
- `configs/dataset_config.yaml`;
- `data/interim/sec_facts_long.csv` i `sec_facts_wide.csv`;
- raporty `data/reports/xbrl_*`.

### 2.2. Kod historyczny

- `LEGACY/pre_pit_modeling/src/data/modeling_dataset.py`;
- `LEGACY/pre_pit_modeling/src/data/08_build_modeling_dataset.py`;
- historyczna konfiguracja i notebook w `LEGACY/pre_pit_modeling/`.

### 2.3. Zamrożone artefakty użyte wyłącznie diagnostycznie

- `data/processed/research_universe_pit.csv`;
- `data/processed/research_universe_pit_v1_1_0_target_pit_b_v1_0_0.csv`;
- frozen target config i jego istniejący resolver primitive/statement.

Pierwotna analiza projektowa coverage obejmowała tylko train `2011–2020` i
validation `2021–2022` i nie pobierała nowych danych. Po akceptacji polityki
implementacja wykorzystała najpierw istniejące lokalne Company Facts,
Submissions, filing packages, skrypty i audyty, a następnie uzupełniła wyłącznie
brakujące primary-statement evidence. Mechaniczny source acquisition objął też
testowe anchors 2023–2024, ale ich wartości, coverage, outliery, missingness ani
targety nie były używane do decyzji o polityce lub resolverach. Sprawdzono
również oficjalną dokumentację SEC dotyczącą Company Facts, Inline XBRL,
presentation groups i timestampów EDGAR.

SEC wyjaśnia, że Company Facts agreguje fakty z wielu submissions jednego
emitenta i że struktury API są aktualizowane wraz z kolejnymi filingami. To
potwierdza, że sam bieżący plik Company Facts nie jest vintage point-in-time;
konieczne jest filtrowanie po accession. SEC wskazuje też, że presentation,
contexts, dimensions, labels i Filing Summary są częścią metadanych potrzebnych
do poprawnego renderowania i interpretowania faktów. Źródła:

- [SEC — EDGAR Application Programming Interfaces](https://www.sec.gov/search-filings/edgar-application-programming-interfaces);
- [SEC — Inline XBRL](https://www.sec.gov/data-research/structured-data/inline-xbrl);
- [SEC — EDGAR XBRL Guide](https://www.sec.gov/files/edgar/filer-information/specifications/xbrl-guide-2024-03-12.pdf);
- [SEC — Webmaster FAQ: EDGAR timestamps](https://www.sec.gov/about/webmaster-frequently-asked-questions).

## 3. Formalna jednostka obserwacji i czas predykcji

### 3.1. Jednostka

Jednostką surowego feature artifact jest eligible economic statement
scope–feature year z universe `v1.1.0`. Kluczem technicznym pozostaje
`research_universe_company_year_id`, a provenance obejmuje co najmniej CIK,
`economic_statement_scope_id`, `economic_group_id`, rok i accession.

Tylko `membership_status == eligible` może otrzymać `X_t`. Wiersze
`ambiguous` i `excluded` pozostają w artefakcie universe i w raportach, lecz
nie wchodzą do `X_t`. Membership, `x_t_status` i `target_status` są trzema
niezależnymi statusami.

### 3.2. Anchor accession

Oznaczenie `A0` używane dalej w tabelach oznacza:

```text
anchor_accession_X_t(i,t) =
    universe_v1.1.0.accession(i,t)
```

Jest to najwcześniejszy oryginalny 10-K za fiscal year `t`, już rozstrzygnięty
przez zamrożony universe według accepted timestamp, filed date i accession.

Reguły:

- akceptowany jest tylko dokładny accession `A0`;
- `10-K/A`, `10-KT`, `10-KT/A` i każdy późniejszy 10-K są niedozwolone;
- pipeline cech nie może ponownie rankować filingów;
- brak faktu w `A0` daje NA/status, nigdy fallback do innego accession;
- anchor targetu `t+1` i wszystkie jego fakty są poza przestrzenią `X_t`.

### 3.3. `feature_available_at` i `prediction_timestamp`

Oznaczenie `F0` używane dalej oznacza:

```text
feature_available_at = anchor_accepted_at
prediction_timestamp = anchor_accepted_at
```

dla przypadków z pełnym timestampem. Wszystkie fakty i cechy pochodzące z tego
samego filing package traktuje się jako dostępne atomowo w `F0`. Dla cechy
pochodnej `feature_available_at` jest maksimum timestampów jej primitive, co
w tej polityce również równa się `F0`.

SEC nie publikuje osobnego dokładnego timestampu pierwszego pojawienia się
dokumentu na stronie, a typowy lag względem EDGAR acceptance wynosi według SEC
około 1–3 minut i nie jest gwarantowany. Dla modelu o częstotliwości rocznej,
który korzysta wyłącznie z treści tego samego filingu, acceptance timestamp jest
spójnym operacyjnym punktem odcięcia. Gdyby później dodano dane rynkowe o
częstotliwości dziennej lub intraday, konieczna byłaby osobna konserwatywna
reguła synchronizacji; takich cech ten projekt nie rekomenduje.

Jeżeli `accepted_at` pozostaje niedostępny po sprawdzeniu historycznych SEC
Submissions/headerów, rekomendowany fallback wymagający zatwierdzenia to:

```text
feature_available_at_precision = filed_date
prediction_timestamp_not_before = 00:00 ET dnia kalendarzowego po filed_date
```

Nie imputuje się arbitralnej godziny w samym dniu `filed`. Alternatywą jest
oznaczenie całego `X_t` jako ambiguous; decyzja jest wymieniona w sekcji 12.

### 3.4. Current `t` i comparative `t-1`

Oznaczenie `C0` oznacza:

- current `t` i comparative `t-1` pochodzą z tego samego `A0`;
- dla stock facts current ma instant na `DocumentPeriodEndDate`, a comparative
  właściwy poprzedni annual instant;
- dla flow facts oba mają poprawne annual duration contexts, zwykle 300–400
  dni, z tolerancją początku okresu zgodną z polityką targetu;
- standardowy rok 52/53-tygodniowy jest dozwolony;
- transition/ambiguous period daje NA dla dotkniętej cechy albo całego
  accession, zależnie od zakresu problemu;
- current i comparative dla jednej zmiany muszą reprezentować tę samą pozycję
  ekonomiczną, najlepiej ten sam concept/tag i ten sam consolidated statement
  scope.

Comparative `t-1` zaprezentowane w 10-K za `t` może uwzględniać retrospektywną
reclassification znaną w `F0`. Jest to dozwolone i pożądane, bo zapewnia
porównywalną podstawę `t-1 -> t`. Nie wolno zastępować go wartością `t-1` z
wcześniejszego 10-K ani z 10-K za `t+1`.

## 4. Audyt obecnego pipeline — ustalenia

| Obszar | Obecne zachowanie | Ryzyko | Ocena i wymagana poprawka |
|---|---|---|---|
| Universe | `06_parse_companyfacts.py` czyta stare `data/processed/research_universe.csv` i deduplikuje po CIK | survivorship i historical-classification bias | **krytyczne** — czytać wyłącznie eligible rows frozen universe `v1.1.0` |
| Anchor | kandydaci są rankowani globalnie po okresie, formularzu, tagu, filed i accession | późniejszy filing może wygrać z pierwszym 10-K | **krytyczne** — accession musi zostać przejęty z universe, nie wybrany przez parser |
| Vintage Company Facts | lokalny JSON zawiera fakty dołączone przez późniejsze submissions | późniejszy comparative/restatement może wejść do `X_t` | **krytyczne** — najpierw filtr exact accession, potem concept/context |
| Timestamp | wide/long nie zachowują `accepted_at` ani formalnego `feature_available_at` | brak dowodu dostępności w chwili predykcji | **wysokie** — provenance accepted/filed/precision w każdym primitive |
| Forms | aktywna konfiguracja dopuszcza tylko `10-K` | poprawnie odrzuca `10-K/A`, ale nie gwarantuje właściwego 10-K | **częściowo poprawne** — pozostawić i dodać exact anchor invariant |
| Company-year | rok jest rekonstruowany z `fy`, frame lub end | błędny fiscal year przy transition periods i nietypowych kalendarzach | **wysokie** — używać roku i DocumentPeriodEndDate z frozen anchor |
| Context | roczność jest oceniana głównie po długości okresu/fp/frame | quarter/YTD lub zły instant może przejść ranking | **wysokie** — walidacja current/comparative względem metadanych anchoru |
| Accession primitive | różne zmienne mogą pochodzić z różnych accession; sanity check tylko flaguje problem | mieszanie vintages w jednym ratio | **krytyczne** — mieszany accession ma być niemożliwy konstrukcyjnie |
| Revenues | `sec_tags.yaml` ustawia priorytet tagów, ale nie wymaga primary consolidated statement | component/segment revenue może zastąpić total revenue | **krytyczne** — osobny fail-closed statement resolver dla anchoru `t` |
| Cash | `CashAndCashEquivalents` oraz cash including restricted są fallbackami jednej zmiennej | mieszanie różnych definicji ekonomicznych | **wysokie** — rozdzielić cechy, nie traktować tagów jako równoważnych |
| PPE | gross PPE jest fallbackiem net PPE | niespójna definicja między firmami/latami | **wysokie** — tylko net PPE albo osobne cechy gross/net |
| Intangibles | intangibles including goodwill jest fallbackiem excluding goodwill | podwójne liczenie goodwill i zmiana semantyki | **wysokie** — osobne primitive, brak cross-fallbacku |
| Liabilities | parser może wyliczyć liabilities jako total minus equity z przypadkowo wybranych faktów | NCI i mixed accession/context mogą zniekształcić wynik | **wysokie** — zastosować jawne strategie frozen primitive resolvera w obrębie `A0` |
| Operating costs | parser może zastąpić direct value przez `revenues - OperatingIncomeLoss` | tautologiczna cecha i utrata semantyki kosztów | **wysokie** — nie tworzyć tej wartości; użyć bezpośrednio operating margin |
| EBIT | `OperatingIncomeLoss` jest nazywany `ebit` | operating income nie jest ogólnie równy EBIT | **średnie/wysokie** — nazwać `operating_income`, liczyć `operating_margin` |
| Sales growth | legacy builder używa poprzedniego wiersza wide z poprzedniego roku | wartości mogą pochodzić z dwóch accession i dwóch vintages | **krytyczne** — current/comparative wyłącznie z `A0` |
| Denominatory | legacy odrzuca denominatory `<= 1 000 USD` | arbitralna zależność raw features od progu | **średnie** — w raw layer wymagać ekonomicznie poprawnego znaku; near-zero obsłużyć/flagować jawnie |
| Row filtering | legacy usuwa wiersze za missing-feature ratio, brak targetu lub next-year warning | complete-case selection oraz pośrednie użycie `t+1` przy konstrukcji `X_t` | **krytyczne** — raw `X_t` zachowuje każdy eligible row; target join i ML sample powstają później |
| Preprocessing | finalna imputacja/skaler nie istnieją, co samo w sobie nie jest leakage | brak jeszcze bezpiecznej implementacji | fit tylko train/fold; validation/test wyłącznie transform |

Wniosek: aktywnego parsera nie należy „lekko poprawiać” przez zmianę kilku
rankingów. Jego podstawową jednostką jest CIK–company-year z agregatu Company
Facts, podczas gdy finalna jednostka ma być frozen economic statement
scope–year z exact accession. Bezpieczniejsza i czytelniejsza będzie nowa,
osobna ścieżka PIT; stary kod należy zachować wyłącznie jako legacy/diagnostykę.

## 5. Polityka semantic and period validation dla `X_t`

### 5.1. Reguła ogólna

Kolejność rozstrzygania primitive jest następująca:

1. wczytaj eligible row z frozen universe;
2. przejmij exact `A0`, CIK representative i statement scope;
3. wczytaj wyłącznie filing package i fakty oznaczone tym accession;
4. potwierdź document metadata i annual current/comparative contexts;
5. potwierdź issuer-level consolidated statement membership;
6. zastosuj z góry ustaloną semantyczną kolejność conceptów;
7. jeśli wybór nie jest jednoznaczny, ustaw `ambiguous/NA`;
8. dopiero z zatwierdzonych primitive oblicz cechy pochodne.

Coverage ani wpływ na target/model nie mogą rozstrzygać wyboru conceptu.

### 5.2. Primitive wspólne z targetem

Resolver `X_t` powinien wykorzystać te same definicje ekonomiczne i priorytety
dla siedmiu wspólnych primitive, ale działać na anchorze `t`, a nie na
zamrożonym targetowym anchorze `t+1`. Nie jest to zmiana targetu.

| Primitive | Dozwolona kolejność semantyczna | Uwagi |
|---|---|---|
| Assets | `Assets`; następnie `LiabilitiesAndStockholdersEquity` jako total balance-sheet fallback | fallback tylko w tym samym consolidated balance sheet scope |
| Liabilities | `Liabilities`; następnie total minus equity including NCI; następnie total minus equity bez NCI tylko przy zero/absent minority interest | wszystkie składniki z tego samego accession, instant i statement scope |
| Current assets | `AssetsCurrent` | brak heurystycznego sumowania komponentów |
| Current liabilities | `LiabilitiesCurrent` | brak heurystycznego sumowania komponentów |
| Revenues | kolejność z frozen config, lecz tylko unique consolidated revenue row na primary statement | component/segment/project/note-only zawsze odrzucone; current-only level może istnieć bez comparative, ale growth wymaga obu |
| Net income | `NetIncomeLoss`; następnie `ProfitLoss` | dla zmiany current/comparative ten sam concept; nie mieszać parent-only z including NCI |
| Operating cash flow | `NetCashProvidedByUsedInOperatingActivities`; następnie continuing operations | dla zmiany current/comparative ten sam concept; wariant continuing nie jest zamieniany z total między okresami |

### 5.3. Context rules

- stock facts: unit USD, exact annual instant;
- flow facts: unit USD, exact annual duration;
- issuer-level/no segment dimensions albo context jednoznacznie należący do
  consolidated primary statement;
- brak automatycznego preferowania frame nad filing metadata;
- brak składania rocznej wartości z kwartalnych wartości;
- duplikaty identycznych faktów są deduplikowane z zachowaniem pełnego
  provenance; materialnie różne wartości w równie poprawnych contexts dają
  `ambiguous`;
- custom extension może być użyty dopiero po mapowaniu semantycznym opartym na
  label, calculation/presentation relationship i primary statement; w wersji
  `X_t v1` rekomendowane jest fail-closed NA zamiast automatycznego mapowania
  custom tags.

### 5.4. Provenance

Każdy primitive current i comparative musi zachować:

- `research_universe_company_year_id`, CIK, feature year;
- universe accession i representative CIK;
- concept QName/tag, label i unit;
- value, decimals/scale;
- start, end, instant/duration i context identifier;
- wszystkie explicit/typed dimensions;
- statement file, statement label, role URI i row membership;
- form, filed, accepted timestamp, timestamp precision;
- current/comparative role;
- selection strategy, candidate count i competing candidates;
- availability/status/reason;
- hash lub lokalny identyfikator źródłowego filing package.

## 6. Kandydackie cechy — rekomendowany blok główny

W tabelach `A0/F0` oznacza exact frozen-universe anchor oraz availability z
sekcji 3. `C0` oznacza same-anchor current/comparative. Każda cecha oznaczona
`A0/F0` korzysta wyłącznie z informacji dostępnych w `prediction_timestamp` i
nie używa `t+1`. Coverage jest szacunkiem na lokalnych danych development, a
nie wynikiem finalnego `X_t`.

| Cecha | Definicja ekonomiczna i formuła | Źródłowe fakty XBRL | Anchor / availability | Comparative `t-1` | Leakage i expected coverage | Decyzja |
|---|---|---|---|---|---|---|
| `log_assets_t` | logarytm wielkości: `ln(Assets_t)` dla `Assets_t > 0` | Assets resolver z sekcji 5.2 | `A0/F0` | nie | niskie po exact accession; około **80–81%** | **core** |
| `roa_t` | rentowność aktywów: `NetIncome_t / Assets_t` | `NetIncomeLoss` lub fail-closed `ProfitLoss`; Assets | `A0/F0` | nie | ryzyko parent vs NCI kontrolowane conceptem; około **77–78%** | **core** |
| `ocf_to_assets_t` | zdolność generowania gotówki: `OCF_t / Assets_t` | OCF resolver; Assets | `A0/F0` | nie | continuing vs total nie mogą być mieszane; około **79–80%** | **core** |
| `current_ratio_t` | płynność: `CurrentAssets_t / CurrentLiabilities_t` przy dodatnim mianowniku | `AssetsCurrent`, `LiabilitiesCurrent` | `A0/F0` | nie | strukturalnie niedostępne dla części emitentów; około **76–78%** | **core**, z missing indicator później |
| `liabilities_to_assets_t` | ogólna dźwignia: `Liabilities_t / Assets_t` | liabilities i assets resolver | `A0/F0` | nie | derived liabilities tylko według jawnej strategii; około **79–80%** | **core** |
| `working_capital_to_assets_t` | płynny bufor: `(CurrentAssets_t - CurrentLiabilities_t) / Assets_t` | current assets, current liabilities, assets | `A0/F0` | nie | brak current classification nie może być zerem; około **76–77%** | **core** |
| `accruals_to_assets_t` | rozbieżność earnings–cash: `(NetIncome_t - OCF_t) / Assets_t` | net income, OCF, assets | `A0/F0` | nie | signed facts i sign inversions wymagają kontroli; około **77–78%** | **core** |
| `asset_growth_1y` | wzrost skali: `Assets_t / Assets_t-1(comparative) - 1` | current i comparative Assets | `A0/F0/C0` | wymagany | wcześniejszy wide row zabroniony; konserwatywny pomiar około **81%** | **core dynamic** |
| `delta_roa_1y` | zmiana rentowności: `ROA_t - ROA_t-1(comparative)` | pary net income i assets | `A0/F0/C0` | wymagany | te same concepty w obu okresach; około **78%** | **core dynamic** |
| `delta_ocf_to_assets_1y` | zmiana cash performance: `OCF/assets_t - OCF/assets_t-1` | pary OCF i assets | `A0/F0/C0` | wymagany | nie jest leakage: używa `t-1 -> t`, target używa `t -> t+1`; około **80%** | **core dynamic** |
| `current_ratio_change_1y` | względna zmiana płynności: `CR_t / CR_t-1 - 1`, oba CR z dodatnimi mianownikami | pary current assets/liabilities | `A0/F0/C0` | wymagany | zero/ujemny comparative CR daje NA; około **77%** | **core dynamic** |
| `delta_liabilities_to_assets_1y` | zmiana dźwigni: `L/A_t - L/A_t-1` | pary liabilities i assets | `A0/F0/C0` | wymagany | ta sama strategia ekonomiczna w obu okresach; około **80%** | **core dynamic** |

Włączenie w `X_t` cech opisujących historyczną zmianę tych samych wymiarów,
które później tworzą target, jest metodologicznie poprawne. Nie korzystają one
z `t+1`; mierzą momentum znane w `prediction_timestamp`. Ich podobieństwo do
D1–D5 wymaga tylko jawnego opisania i kontroli poprawności okresów, nie ich
odrzucenia.

## 7. Blok revenue-dependent

Poniższe cechy są ekonomicznie wartościowe, ale nie powinny być warunkiem
zachowania obserwacji ani jedynym głównym zestawem cech. Każda wymaga
fail-closed resolvera consolidated annual revenues na primary statement
anchoru `t`.

| Cecha | Definicja i formuła | XBRL | Anchor / comparative | Leakage i expected coverage | Decyzja |
|---|---|---|---|---|---|
| `log1p_revenues_t` | skala działalności: `ln(1 + Revenues_t)` dla `Revenues_t >= 0` | approved consolidated revenue concept | `A0/F0`; comparative niepotrzebny | current-only proxy 68,9%, strict statement pair 48,2%; orientacyjny przedział planistyczny, nie gwarancja finalnego coverage | **retained revenue module** |
| `profit_margin_t` | `NetIncome_t / Revenues_t`, revenue dodatnie | net income + revenues | `A0/F0` | około 64,6% w current proxy, 45,2% strict pair | **retained revenue module** |
| `ocf_margin_t` | `OCF_t / Revenues_t`, revenue dodatnie | OCF + revenues | `A0/F0` | około 66,1% current proxy, 46,5% strict pair | **retained revenue module** |
| `asset_turnover_t` | `Revenues_t / Assets_t` | revenues + assets | `A0/F0` | około 68,5% current proxy, 47,9% strict pair | **retained revenue module** |
| `revenue_growth_1y` | `Revenues_t / Revenues_t-1(comparative) - 1`, comparative revenue dodatnie | ten sam approved revenue concept i statement row dla obu okresów | `A0/F0/C0` | strict statement-pair około **46,6%** | **retained revenue dynamic** |

Rekomendacja implementacyjna: zapisać blok revenue w tym samym raw artifact,
ale raportować osobno coverage i wpływ jego dostępności. W ML należy porównać
z góry zdefiniowane: model core oraz model core+revenue. Nie wolno wybierać
resolvera lub zestawu na podstawie tego, który daje lepsze wyniki testowe.

## 8. Cechy warunkowe — wymagają osobnego resolver audit

Te cechy mogą zostać dodane do raw `X_t v1`, lecz dopiero po jawnej walidacji
semantycznej i pomiarze coverage na train/validation. Obecne lokalne coverage
pochodzi ze starego, nie-PIT wide pipeline i jest wyłącznie wskazówką, nie
prognozą finalnego coverage.

| Cecha | Formuła i źródłowe tagi | Problem semantyczny / comparative | Obserwowane legacy coverage całego frozen development universe | Rekomendacja |
|---|---|---|---:|---|
| `cash_and_equivalents_to_assets_t` | `CashAndCashEquivalentsAtCarryingValue / Assets` | nie używać cash including restricted jako fallback; comparative tylko ten sam tag | 45,3% | **warunkowo dodać** po PIT audit |
| `operating_margin_t` | `OperatingIncomeLoss / Revenues` | nazywać operating income, nie EBIT; wymaga final revenue resolvera | 41,6% dla operating income primitive | **warunkowo dodać** |
| `capex_to_assets_t` | `PaymentsToAcquirePropertyPlantAndEquipment / Assets` | `PaymentsToAcquireProductiveAssets` jest szersze i nie powinno być automatycznym fallbackiem | 38,6% | **warunkowo dodać** |
| `interest_bearing_debt_to_assets_t` | `(DebtCurrent + LongTermDebtNoncurrent) / Assets` | trzeba uniknąć overlap `DebtCurrent`, `LongTermDebtCurrent`, borrowings i lease liabilities | 25–26% dla komponentów | **defer** do statement/calculation audit |
| `inventory_to_assets_t` | `InventoryNet / Assets` | ekonomicznie strukturalne zero vs brak disclosure; comparative ten sam concept | 28,1% | **warunkowo**, głównie sectors with inventory |
| `receivables_to_assets_t` | approved net current receivables / Assets | tagi accounts/other receivables nie zawsze równoważne | 37,1% | **warunkowo** |
| `ppe_net_to_assets_t` | `PropertyPlantAndEquipmentNet / Assets` | gross PPE nie jest fallbackiem net PPE | 41,4% | **warunkowo dodać** |
| `goodwill_to_assets_t` | `Goodwill / Assets` | brak disclosure może być prawdziwym zerem lub missing; nie imputować zero w raw layer | 27,5% | **warunkowo** |
| `intangibles_ex_goodwill_to_assets_t` | `IntangibleAssetsNetExcludingGoodwill / Assets` | including goodwill jest inną pozycją; custom concepts częste | 29,3% | **warunkowo** |
| `retained_earnings_to_assets_t` | `RetainedEarningsAccumulatedDeficit / Assets` | unappropriated fallback tylko po semantic confirmation | 44,6% | **warunkowo dodać** |
| `investing_cf_to_assets_t` | `NetCashProvidedByUsedInInvestingActivities / Assets` | continuing-operations fallback nie może być mieszany między okresami | 43,1% | **warunkowo dodać** |
| `financing_cf_to_assets_t` | `NetCashProvidedByUsedInFinancingActivities / Assets` | jak wyżej | 45,0% | **warunkowo dodać** |

Nie rekomenduje się rozszerzania pierwszej implementacji wszystkimi tymi
cechami naraz. Najpierw należy poprawnie wdrożyć i zamknąć audyt rdzenia; potem
dodać mały, predefiniowany extension block bez wybierania go według wyników
modeli.

## 9. Cechy odrzucone

| Cecha / konstrukcja | Powód odrzucenia z głównego `X_t` |
|---|---|
| `liabilities_to_equity` | niestabilny i nieciągły przy małym, zerowym lub ujemnym equity; znak może odwracać interpretację distress |
| `ROE` | ten sam problem mianownika; wysokie wartości często wynikają z małego/ujemnego equity, a nie poprawy ekonomicznej |
| raw dollar assets/revenues jako liniowe cechy | silna skośność i dominacja skali; przechowywać jako primitive, do modelu używać logów/ratio |
| `LiabilitiesAndStockholdersEquity` jako osobna cecha | ekonomicznie duplikat assets; zachować jako resolver fallback i kontrolę bilansową |
| `operating_costs = revenues - OperatingIncomeLoss` | tożsamość rachunkowa, nie niezależny primitive; może wprowadzić sztuczną redundancję |
| `PPEGross` jako fallback `PPENet` | różne definicje ekonomiczne i nieporównywalność |
| `IntangibleAssetsIncludingGoodwill` jako fallback ex-goodwill | podwójne liczenie goodwill i zmiana semantyki |
| cash including restricted jako fallback cash equivalents | restricted cash nie jest równoważny płynnej gotówce |
| `LongTermInvestments` | legacy coverage tylko około 3%; tag nie obejmuje jednolicie wszystkich inwestycji długoterminowych |
| Altman Z-score jako cecha główna | częściowo nakłada się na primitive, a klasyczna wersja wymaga PIT market value; lepiej pozostawić ewentualnie jako jawny robustness feature |
| Beneish M-score jako cecha główna | wymaga wielu semantycznie kruchych primitive i precyzyjnych zmian; ryzyko coverage-driven resolverów |
| bieżący ticker, giełda, current SIC lub current sector | historical-classification i survivorship leakage |
| `later_inactive_delisted_or_unmapped_proxy`, `recovered_vs_old_universe` | informacje z przyszłości względem `t`; wyłącznie audit columns |
| `target_status`, `target_available`, powody missing targetu, D1–D5 | bezpośrednie lub pośrednie target leakage |
| anchor/primitive z 10-K `t+1` | bezpośrednie temporal leakage |
| dane z 10-K/A i późniejszych restatements | niedostępne w `prediction_timestamp` i niedozwolone przez politykę |
| `economic_group_id` jako predictor | identyfikator zależności, nie cecha ekonomiczna; używać tylko do diagnostics/clustered inference |

## 10. Empiryczny expected coverage

### 10.1. Current-only proxy, development 2011–2022

Na `56 903` eligible company-years wymagano, aby selected current fact pochodził
z exact frozen-universe accession. Jest to użyteczny pomiar dla primitive
poziomu `t`, ale revenue selection w tym widoku nie ma jeszcze wszystkich
finalnych statement-level ograniczeń i dlatego jest optymistyczna.

| Primitive current `t` | Coverage |
|---|---:|
| Assets | 80,53% |
| Liabilities | 79,91% |
| Current assets | 77,46% |
| Current liabilities | 77,31% |
| Revenues — optimistic semantic proxy | 68,95% |
| Net income | 78,28% |
| Operating cash flow | 79,64% |

### 10.2. Strict same-accession pair diagnostic, development 2012–2022

Drugi pomiar wykorzystuje istniejące, zwalidowane pary PIT-B przesunięte o rok:
dla feature year `t` wartości current `t` i comparative `t-1` pochodzą z 10-K
za `t`. Wymagano zgodności tego accession z frozen-universe anchor `t`.

Pomiar obejmuje `51 241` eligible company-years 2012–2022. Jest konserwatywny:
nie obejmuje 2011 i wymaga istnienia eligible predecessor row, ponieważ
wykorzystuje istniejący artefakt target application zamiast budować `X_t`.

| Cecha | Train 2012–2020 | Validation 2021–2022 | Razem |
|---|---:|---:|---:|
| `log_assets_t` | 80,81% | 83,28% | 81,24% |
| `roa_t` | 77,30% | 81,91% | 78,11% |
| `ocf_to_assets_t` | 79,34% | 82,13% | 79,83% |
| `current_ratio_t` | 76,83% | 80,74% | 77,52% |
| `liabilities_to_assets_t` | 79,71% | 82,84% | 80,26% |
| `working_capital_to_assets_t` | 76,60% | 80,39% | 77,26% |
| `accruals_to_assets_t` | 76,76% | 81,64% | 77,62% |
| `asset_growth_1y` | 80,58% | 83,02% | 81,01% |
| `delta_roa_1y` | 77,10% | 81,68% | 77,90% |
| `delta_ocf_to_assets_1y` | 79,15% | 81,93% | 79,64% |
| `current_ratio_change_1y` | 76,56% | 80,23% | 77,21% |
| `delta_liabilities_to_assets_1y` | 79,50% | 82,60% | 80,04% |
| `log1p_revenues_t` | 49,22% | 43,40% | 48,20% |
| `profit_margin_t` | 46,02% | 41,47% | 45,22% |
| `ocf_margin_t` | 47,58% | 41,55% | 46,53% |
| `asset_turnover_t` | 48,97% | 43,05% | 47,94% |
| `revenue_growth_1y` | 47,61% | 41,55% | 46,55% |

Spadek revenue coverage w validation nie powinien prowadzić do poluzowania
resolvera. Jest sygnałem, że brak przychodów jest informacyjny i że revenue
module wymaga osobnego missingness audit.

### 10.3. Dlaczego obecne wide coverage nie jest finalne

Po połączeniu starego `sec_facts_wide.csv` z całym frozen development universe
tylko `26 037 / 56 903`, czyli **45,76%**, eligible company-years ma assets.
Nie oznacza to, że prawidłowy PIT pipeline będzie miał tak niskie coverage.
Stary wide parser był budowany dla bieżącej listy CIK i nie obejmuje dużej
części historycznych spółek odzyskanych przez universe `v1.1.0`.

Ostateczne expected/realized coverage można zamknąć dopiero po implementacji
exact-accession feature resolvera. Wyniki w tej sekcji służą do zaprojektowania
bloków, nie do doboru cech według jakości modeli.

## 11. Rozdzielenie raw PIT construction i ML preprocessing

### 11.1. Warstwa A — raw PIT `X_t`

Raw artifact powinien:

- zawierać jeden wiersz dla każdego eligible universe company-year, także gdy
  wszystkie cechy są NA;
- zachować primitive current/comparative i cechy pochodne bez imputacji,
  winsoryzacji i skalowania;
- nie wymagać dostępnego targetu;
- przechowywać osobne statusy per primitive i per feature;
- nie usuwać observation na podstawie missing-feature ratio;
- zachować wartości surowe przed transformacją oraz pełne provenance;
- zawierać mechanicznie przypisany split z frozen universe, ale nie używać
  validation/test do rozstrzygania semantic selection.

Proponowane `x_t_status` na poziomie wiersza:

```text
available_core
partially_available
missing
ambiguous
not_available_non_xbrl
hard_exclude_anchor_or_entity_context
```

Status per feature pozostaje bardziej szczegółowy. W szczególności
`not_available_non_xbrl` nie zmienia membership universe.

### 11.2. Warstwa B — join z targetem

Join odbywa się po kanonicznym frozen company-year key. Do supervised sample
wchodzą wyłącznie wiersze z targetem `available`; target missing/ambiguous/
hard-exclude/not-computable nigdy nie jest mapowany na 0. Raw `X_t` nie jest
jednak przycinany do complete cases targetu i pozostaje podstawą audytu
selection bias.

Żadne pola z target application, w tym availability i reason codes, nie mogą
zostać przekazane jako predictors.

### 11.3. Warstwa C — preprocessing ML

Rekomendowana kolejność:

1. utrwalić temporal split: train 2011–2020, validation 2021–2022, test
   2023–2024;
2. w każdym eksperymencie dopasować preprocessing tylko na supervised train;
3. w cross-validation dopasować każdy transformer osobno wewnątrz train fold;
4. zastosować gotowe transformery do validation bez refit;
5. zachować test 2023–2024 nietknięty do finalnej oceny.

Polityka preprocessing do późniejszego zatwierdzenia:

- imputacja: train-median per feature plus missing indicator; bez używania
  przyszłych lat lub pełnego panelu;
- winsoryzacja: granice wyuczone wyłącznie na train/fold, np. 1–99 percentyl;
- skalowanie: `RobustScaler` albo `StandardScaler` fit train/fold;
- categorical encoding sektora/SIC: słownik fit train; unseen category ma
  jawny poziom `unknown`, nie mapping z przyszłości;
- feature selection: wyłącznie wewnątrz training CV; żadnego wyboru po wyniku
  validation/test;
- surowy artifact nigdy nie jest nadpisywany transformowanymi wartościami.

Nie rekomenduje się obliczania median, kwantyli ani skalowania osobno dla
każdego roku z wykorzystaniem wszystkich spółek w validation/test. Taki zabieg
byłby transductive i utrudniałby interpretację point-in-time.

## 12. Zatwierdzone decyzje implementacyjne `X_t v1`

1. **Fallback timestamp.** Gdy `accepted_at` pozostaje niedostępny,
   `prediction_timestamp = 00:00 ET` następnego dnia po `filed_date`, z jawną
   flagą niższej precyzji.
2. **Zakres v1.** Trzy z góry zdefiniowane bloki: `L = core levels`,
   `D = core dynamics t-1 -> t`, `R = revenue module`. Docelowe porównania
   modeli to `L`, `L+D`, `L+D+R`; bloków nie wolno wybierać na test set.
3. **Non-XBRL registrants.** Membership zostaje zachowane, a status otrzymuje
   wartość `not_available_non_xbrl`; v1 nie obejmuje ekstrakcji HTML/PDF.
4. **Metadata.** Historyczny sektor i SIC pozostają metadata/control variables,
   ale nie trafiają automatycznie do financial feature block.
5. **Denominatory.** Obowiązuje warunek ekonomiczny `> 0`, bez globalnego progu
   1 000 USD. Near-zero jest wyłącznie diagnostyką.
6. **Missing indicators.** Nie powstają w raw `X_t`; są dozwolone dopiero w
   warstwie ML z obowiązkową ablation bez indicators.
7. **Extension block.** Nie jest implementowany w v1.
8. **Economic groups.** `economic_group_id` służy wyłącznie diagnostics,
   clustered inference i ewentualnemu group-aware CV; nigdy nie jest predictor.

## 13. Ryzyka do skontrolowania przed implementacją

### Krytyczne invariants

- każdy feature accession równa się frozen-universe accession;
- żaden accession, filed/accepted timestamp ani period end nie pochodzi z
  `t+1`;
- żaden wybrany form nie jest amendment/transition form;
- current/comparative dynamic feature ma jedno accession, poprawne dwa annual
  contexts i tę samą definicję ekonomiczną;
- revenue row jest unique, consolidated i należy do primary statement;
- segment/component contexts nie przechodzą jako issuer total;
- derived primitive nie miesza accession, statement scopes ani period types;
- późniejszy brak targetu ani next-year warning nie wpływa na raw `X_t`;
- current ticker/SIC/inactivity i inne future audit fields nie trafiają do
  model matrix;
- target columns i target provenance są blokowane schema testem.

### Obowiązkowe audyty po implementacji, przed freeze `X_t`

1. coverage każdego primitive i feature według roku, sektora, SIC, wielkości,
   registrant role i XBRL availability;
2. liczba missing/ambiguous/hard-exclude wraz z reason codes;
3. exact-accession i timestamp consistency audit;
4. manual stratified review primary statements dla revenues oraz próby innych
   semantycznie wrażliwych primitive;
5. outlier/denominator/sign audit bez winsoryzowania raw danych;
6. porównanie current `t` z comparative `t` pokazanym w anchorze `t+1`
   wyłącznie jako revision diagnostic, nigdy jako zamiana `X_t`;
7. missingness/selection bias osobno dla X availability i target availability;
8. test blokujący niezmienność hashy frozen target/universe;
9. test blokujący obecność test years w jakimkolwiek fit lub wyborze polityki;
10. audit overlap/dependence po `economic_group_id`.

## 14. Stan implementacji po akceptacji polityki

Utworzono wersjonowaną konfigurację `configs/x_t_pit_v1.yaml`, invariant/schema
tests oraz raw artifact obejmujący dokładnie wszystkie **64 901** eligible
company-years i **1 072** kolumny. Finalny SHA-256 raw artifact to
`0f1b35b9ffbb1fb1c1cdfb7dff12e3efd8fb38f60b33407ff2b2a8fb6b88397f`.
Manifest zapisano w `data/reports/x_t_pit_v1_build_manifest.json`, a kompletny
audyt sekcji 13 w `data/reports/x_t_pit_v1_audit.md`.

Źródłowy backfill został ograniczony do zidentyfikowanych luk i ponownie
wykorzystywał istniejący cache. Finalne inventory obejmuje **8 218 / 8 218**
accessionów: **7 986** z poprawnym statement package, **214** bez jednoznacznie
rozpoznanego income statement i **18** potwierdzonych `not_found`; błędów
technicznych jest **0**. Dwa wtórne joint-filing XBRL scopes wymagające
dodatkowego statement evidence zostały odświeżone tym samym konstruktorem
wiersza, a cały artefakt ponownie przeszedł walidację.

Finalny audyt development `2011–2022` wykazał:

- **56 903** obserwacje development;
- status `available_core`: **45 797 (80,48%)**;
- current assets primitive coverage: **87,81%**;
- same-anchor assets pair coverage: **83,11%**;
- current revenues coverage: **52,81%**;
- same-anchor revenues pair coverage: **46,44%**;
- manual revenue review: **90** przypadków, **0** błędów;
- manual review pozostałych primitive: **185** sprawdzeń, **0** błędów;
- exact-accession, timestamp i filing provenance errors: **0**;
- joint-co XBRL scopes bez exact-anchor records: **0**;
- nieukończone source gaps: **0**.

Końcowy negative-sign sanity check objął wszystkie **25** ujemnych selected
primitive cases w development: **5** ekonomicznie uzasadnionych ujemnych
revenues zachowano, **16** błędów znaku/tagu/kontekstu XBRL oraz **4**
nierozstrzygalne prezentacje ustawiono fail-closed jako `ambiguous/NA` bez
heurystycznego odwracania znaku. Zależne cechy zostały przeliczone, a ponowny
pełny audyt nie wykazał blockerów.

Core-X availability i target availability pozostają odrębnymi mechanizmami
selekcji. Pełny supervised L sample obejmuje **22 679 (39,86%)** obserwacji
development; ryzyka complete-case selection bias i informative censoring są
ocenione jako **wysokie** i muszą pozostać ograniczeniem metodologicznym.
Revenue module zachowuje status osobnego bloku R i nie jest warunkiem obecności
wiersza.

Audyt wydał werdykt **`X_T V1 READY TO FREEZE`**. Formalny akt zamrożenia jest
zapisany odrębnie w
`docs/06_2_raw_point_in_time_x_t_v1_frozen_specification.md`. Nie wykonano
preprocessingu ML, nie trenowano modeli i nie użyto testu 2023–2024 do wyboru
polityki, resolvera ani cech.

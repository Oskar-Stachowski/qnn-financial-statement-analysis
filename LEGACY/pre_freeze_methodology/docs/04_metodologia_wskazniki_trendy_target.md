# Decyzja metodologiczna: wskaźniki finansowe, trendy i target dla pracy magisterskiej QNN

**Plik źródłowy:** `xbrl_variable_coverage.csv`  
**Kontekst pracy:** zastosowanie hybrydowych kwantowych sieci neuronowych do klasyfikacji ryzyka finansowo-sprawozdawczego spółek publicznych na podstawie danych SEC EDGAR.  
**Wniosek główny:** najlepszy wariant metodologiczny to zbudować **klasyczny, dobrze uzasadniony zestaw wskaźników finansowych**, dodać wybrane trendy/różnice rok do roku, a jako główny target przyjąć **przyszłe pogorszenie kondycji finansowej w roku `t+1`**. Beneish M-Score i Altman Z-Score powinny być traktowane jako **proxy / eksperymenty pomocnicze**, a nie jako jedyne źródło prawdy o fraudzie lub bankructwie.

---

## 1. Wniosek z pokrycia zmiennych XBRL

W pliku coverage są dane roczne z formularzy `10-K`. Najlepsze pokrycie mają pozycje podstawowe: aktywa, zobowiązania, aktywa i zobowiązania krótkoterminowe, zysk netto, kapitał własny, gotówka, EBIT, cash flow operacyjny i retained earnings. To wystarcza do bardzo solidnego zestawu wskaźników kondycji finansowej.

**Zmienne o bardzo dobrym pokryciu, które powinny tworzyć rdzeń datasetu:**  
`assets` (99.7%), `liabilities` (99.5%), `liabilities_and_equity` (99.6%), `current_assets` (97.2%), `current_liabilities` (96.8%), `net_income` (97.8%), `equity` (99.0%), `cash` (98.9%), `ebit` (91.0%), `retained_earnings` (97.6%), `operating_cash_flow` (99.1%), `investing_cash_flow` (93.3%), `financing_cash_flow` (97.8%).

**Zmienne o średnim pokryciu, nadal przydatne do wskaźników dodatkowych i Beneish/rotacji:**  
`revenues` (88.0%), `accounts_receivable` (78.9%), `operating_costs` (84.0%), `ppe` (86.9%), `depreciation_amortization` (73.6%), `capex` (82.0%).

**Zmienne warunkowe, dobre raczej do eksperymentów dodatkowych lub po filtracji próby:**  
`inventory` (59.2%), `cost_of_revenue` (63.6%), `intangible_assets` (63.1%), `goodwill` (58.1%), `long_term_debt` (56.2%), `short_term_debt` (53.2%), `interest_expense` (59.0%).

**Zmienna do wykluczenia z MVP ze względu na bardzo niskie pokrycie:**  
`long_term_investments` (6.3%).

### Pełna tabela pokrycia

| Zmienna XBRL | Company-year coverage | Rekomendacja |
|---|---:|---|
| `assets` | 99.7% | rdzeń datasetu / cechy główne / target |
| `liabilities_and_equity` | 99.6% | rdzeń datasetu / cechy główne / target |
| `liabilities` | 99.5% | rdzeń datasetu / cechy główne / target |
| `operating_cash_flow` | 99.1% | rdzeń datasetu / cechy główne / target |
| `equity` | 99.0% | rdzeń datasetu / cechy główne / target |
| `cash` | 98.9% | rdzeń datasetu / cechy główne / target |
| `net_income` | 97.8% | rdzeń datasetu / cechy główne / target |
| `financing_cash_flow` | 97.8% | rdzeń datasetu / cechy główne / target |
| `retained_earnings` | 97.6% | rdzeń datasetu / cechy główne / target |
| `current_assets` | 97.2% | rdzeń datasetu / cechy główne / target |
| `current_liabilities` | 96.8% | rdzeń datasetu / cechy główne / target |
| `investing_cash_flow` | 93.3% | rdzeń datasetu / cechy główne / target |
| `ebit` | 91.0% | rdzeń datasetu / cechy główne / target |
| `revenues` | 88.0% | cecha rekomendowana, ale z kontrolą braków |
| `ppe` | 86.9% | cecha rekomendowana, ale z kontrolą braków |
| `operating_costs` | 84.0% | cecha rekomendowana, ale z kontrolą braków |
| `capex` | 82.0% | cecha rekomendowana, ale z kontrolą braków |
| `accounts_receivable` | 78.9% | cecha rekomendowana, ale z kontrolą braków |
| `depreciation_amortization` | 73.6% | cecha rekomendowana, ale z kontrolą braków |
| `cost_of_revenue` | 63.6% | cecha warunkowa lub eksperyment dodatkowy |
| `intangible_assets` | 63.1% | cecha warunkowa lub eksperyment dodatkowy |
| `inventory` | 59.2% | cecha warunkowa lub eksperyment dodatkowy |
| `interest_expense` | 59.0% | cecha warunkowa lub eksperyment dodatkowy |
| `goodwill` | 58.1% | cecha warunkowa lub eksperyment dodatkowy |
| `long_term_debt` | 56.2% | cecha warunkowa lub eksperyment dodatkowy |
| `short_term_debt` | 53.2% | cecha warunkowa lub eksperyment dodatkowy |
| `long_term_investments` | 6.3% | raczej wykluczyć z MVP |


---

## 2. Wskaźniki finansowe do wyliczenia

### 2.1. Wskaźniki główne — obowiązkowe w MVP

To jest zestaw, który powinien być liczony najpierw. Ma najlepszy stosunek: sens finansowy / dostępność danych / zgodność z QNN.

| Grupa | Wskaźnik | Wzór roboczy | Źródłowe zmienne XBRL | Rola w pracy |
|---|---|---|---|---|
| Płynność | `current_ratio` | `current_assets / current_liabilities` | `current_assets`, `current_liabilities` | podstawowa zdolność regulowania zobowiązań krótkoterminowych |
| Płynność | `cash_ratio` | `cash / current_liabilities` | `cash`, `current_liabilities` | bardziej konserwatywna płynność |
| Płynność / struktura | `working_capital_to_assets` | `(current_assets - current_liabilities) / assets` | `current_assets`, `current_liabilities`, `assets` | składnik distress, silny kandydat do targetu i cech |
| Zadłużenie | `liabilities_to_assets` | `liabilities / assets` | `liabilities`, `assets` | główny wskaźnik dźwigni finansowej |
| Zadłużenie | `equity_to_assets` | `equity / assets` | `equity`, `assets` | stabilność finansowania kapitałem własnym |
| Zadłużenie | `liabilities_to_equity` | `liabilities / equity` | `liabilities`, `equity` | ryzyko nadmiernej dźwigni; uważać na ujemny kapitał |
| Rentowność | `roa` | `net_income / avg_assets` | `net_income`, `assets` | podstawowa rentowność aktywów; bardzo ważna dla targetu |
| Rentowność | `roe` | `net_income / avg_equity` | `net_income`, `equity` | rentowność kapitału; uważać na mały/ujemny mianownik |
| Rentowność | `net_margin` | `net_income / revenues` | `net_income`, `revenues` | jakość wyniku netto wobec sprzedaży |
| Rentowność operacyjna | `operating_margin` | `ebit / revenues` | `ebit`, `revenues` | wynik operacyjny, mniej zależny od finansowania i podatków |
| Efektywność | `asset_turnover` | `revenues / avg_assets` | `revenues`, `assets` | efektywność wykorzystania aktywów |
| Cash flow | `ocf_to_assets` | `operating_cash_flow / avg_assets` | `operating_cash_flow`, `assets` | gotówkowa kondycja operacyjna |
| Cash flow | `ocf_margin` | `operating_cash_flow / revenues` | `operating_cash_flow`, `revenues` | gotówka operacyjna na jednostkę sprzedaży |
| Jakość wyniku | `accruals_to_assets` | `(net_income - operating_cash_flow) / avg_assets` | `net_income`, `operating_cash_flow`, `assets` | prosta miara różnicy między zyskiem księgowym a gotówką |
| Skala / kontrolna | `log_assets` | `log(assets)` | `assets` | kontrola rozmiaru spółki, przydatna dla modeli klasycznych |

**Uwaga implementacyjna:** dla wskaźników opartych na pozycjach przepływowych, np. `revenues`, `net_income`, `operating_cash_flow`, najlepiej używać średniego stanu aktywów lub kapitału: `avg_assets = (assets_t + assets_t-1) / 2`, `avg_equity = (equity_t + equity_t-1) / 2`. Jeśli brakuje roku `t-1`, można użyć wartości z roku `t`, ale oznaczyć taką obserwację flagą jakości danych.

### 2.2. Wskaźniki rekomendowane — liczyć, ale kontrolować braki

Te wskaźniki są wartościowe, ale część zmiennych ma niższe pokrycie. Najlepiej liczyć je jako osobny blok cech i porównać warianty modeli: `core_only` vs `core_plus_extended`.

| Grupa | Wskaźnik | Wzór roboczy | Źródłowe zmienne XBRL | Decyzja |
|---|---|---|---|---|
| Rotacja należności | `receivables_to_revenue` | `accounts_receivable / revenues` | `accounts_receivable`, `revenues` | liczyć; ważne dla Beneish DSRI |
| Rotacja należności | `receivables_turnover` | `revenues / avg_accounts_receivable` | `revenues`, `accounts_receivable` | liczyć warunkowo |
| Zapasy | `inventory_to_assets` | `inventory / assets` | `inventory`, `assets` | liczyć warunkowo; mocno branżowe |
| Rotacja zapasów | `inventory_turnover` | `cost_of_revenue / avg_inventory` | `cost_of_revenue`, `inventory` | tylko dla spółek z zapasami |
| Marża brutto proxy | `gross_margin_proxy` | `(revenues - cost_of_revenue) / revenues` | `revenues`, `cost_of_revenue` | liczyć, ale traktować jako proxy |
| Koszty operacyjne | `operating_cost_ratio` | `operating_costs / revenues` | `operating_costs`, `revenues` | dobra cecha kosztowa |
| Majątek trwały | `ppe_to_assets` | `ppe / assets` | `ppe`, `assets` | kontrola struktury aktywów |
| Nakłady inwestycyjne | `capex_to_assets` | `abs(capex) / avg_assets` | `capex`, `assets` | inwestycje; znak CAPEX w XBRL trzeba ujednolicić |
| Nakłady inwestycyjne | `capex_to_revenue` | `abs(capex) / revenues` | `capex`, `revenues` | dobra cecha trendu/inwestycji |
| Wartości niematerialne | `intangibles_to_assets` | `intangible_assets / assets` | `intangible_assets`, `assets` | przydatne dla jakości aktywów |
| Goodwill | `goodwill_to_assets` | `goodwill / assets` | `goodwill`, `assets` | liczyć jako cechę dodatkową, nie obowiązkową |
| Amortyzacja | `depr_amort_to_assets` | `depreciation_amortization / avg_assets` | `depreciation_amortization`, `assets` | potrzebne do Beneish DEPI |
| Zadłużenie odsetkowe | `total_debt_to_assets` | `(short_term_debt + long_term_debt) / assets` | `short_term_debt`, `long_term_debt`, `assets` | liczyć warunkowo; niższe pokrycie |
| Zadłużenie odsetkowe | `total_debt_to_equity` | `(short_term_debt + long_term_debt) / equity` | `short_term_debt`, `long_term_debt`, `equity` | uważać na ujemny kapitał |
| Obsługa długu | `interest_coverage` | `ebit / abs(interest_expense)` | `ebit`, `interest_expense` | liczyć warunkowo, bardzo cenna cecha ryzyka |

### 2.3. Wskaźniki syntetyczne / proxy

#### Altman Z-Score — rekomendacja: wersja accounting-only jako proxy distress

W danych z SEC Company Facts / XBRL nie masz bezpośrednio wartości rynkowej kapitału własnego, więc klasyczny Altman Z-Score dla spółek publicznych nie powinien być udawany jako pełny oryginalny model. Najbezpieczniej użyć **uproszczonej wersji accounting-only**, czyli `Altman_Z_proxy` / `Altman_Z_prime_proxy`.

Proponowany wariant:

```text
altman_z_proxy =
  0.717 * working_capital_to_assets
+ 0.847 * retained_earnings_to_assets
+ 3.107 * ebit_to_assets
+ 0.420 * equity_to_liabilities
+ 0.998 * asset_turnover
```

Składniki:

| Składnik | Wzór | Dostępność w Twoim CSV | Decyzja |
|---|---|---:|---|
| `working_capital_to_assets` | `(current_assets - current_liabilities) / assets` | bardzo dobra | liczyć |
| `retained_earnings_to_assets` | `retained_earnings / assets` | bardzo dobra | liczyć |
| `ebit_to_assets` | `ebit / assets` albo `ebit / avg_assets` | bardzo dobra | liczyć |
| `equity_to_liabilities` | `equity / liabilities` | bardzo dobra | liczyć |
| `asset_turnover` | `revenues / avg_assets` | dobra | liczyć |

**Zastosowanie w pracy:**
- jako cecha pomocnicza w wariancie `features_plus_proxy`, albo
- jako target pomocniczy `target_altman_distress_next_year`, ale wtedy nie dodawać `altman_z_proxy` jako cechy wejściowej w tym samym wariancie.

#### Beneish M-Score — rekomendacja: eksperyment pomocniczy, nie główny target

Beneish jest atrakcyjny tematycznie, bo dotyczy jakości sprawozdawczości, ale ma słabsze pokrycie składników i jest proxy, nie dowodem fraudu. Dlatego powinien być **wariantem rozszerzającym**, a nie rdzeniem pracy.

Klasyczne komponenty do obliczenia, jeśli dane są dostępne:

| Komponent | Wzór roboczy | Zmienne | Decyzja |
|---|---|---|---|
| `DSRI` | `(AR_t / Sales_t) / (AR_t-1 / Sales_t-1)` | `accounts_receivable`, `revenues` | liczyć, dobre pokrycie umiarkowane |
| `GMI` | `gross_margin_t-1 / gross_margin_t` | `revenues`, `cost_of_revenue` | liczyć warunkowo |
| `AQI` | `[1 - (current_assets_t + ppe_t) / assets_t] / [1 - (current_assets_t-1 + ppe_t-1) / assets_t-1]` | `current_assets`, `ppe`, `assets` | liczyć |
| `SGI` | `revenues_t / revenues_t-1` | `revenues` | liczyć |
| `DEPI` | depreciation rate `t-1 / t` | `depreciation_amortization`, `ppe` | liczyć warunkowo |
| `SGAI` | `(SGA_t / Sales_t) / (SGA_t-1 / Sales_t-1)` | najlepiej SG&A; u Ciebie tylko proxy z `operating_costs` | liczyć jako proxy albo pominąć w wariancie uproszczonym |
| `LVGI` | `(debt_or_liabilities_to_assets_t) / (debt_or_liabilities_to_assets_t-1)` | `liabilities` albo `short_term_debt + long_term_debt` | użyć `liabilities/assets` w MVP, debt-only jako wariant |
| `TATA` | `(net_income - operating_cash_flow) / assets` | `net_income`, `operating_cash_flow`, `assets` | liczyć; bardzo dobre pokrycie |

Pełny wzór klasyczny:

```text
beneish_m_score =
-4.84
+ 0.920 * DSRI
+ 0.528 * GMI
+ 0.404 * AQI
+ 0.892 * SGI
+ 0.115 * DEPI
- 0.172 * SGAI
+ 4.679 * TATA
- 0.327 * LVGI
```

Roboczy próg wysokiego ryzyka: `beneish_m_score > -2.22`.

**Zastosowanie w pracy:**
- najlepiej jako **eksperyment pomocniczy**: `target_beneish_risk_next_year`, albo
- jako cecha syntetyczna w osobnym wariancie, ale tylko jeśli target główny nie jest zbudowany z Beneish.

### 2.4. Czego nie używać w MVP

| Zmienna / wskaźnik | Decyzja | Powód |
|---|---|---|
| `long_term_investments` | wykluczyć z MVP | bardzo niskie pokrycie w CSV |
| `liabilities_and_equity` jako cecha modelu | raczej nie używać | powiela informację bilansową; lepsze jako sanity check `assets ≈ liabilities_and_equity` |
| pełne Beneish dla całej próby bez filtrów | nie jako domyślny wariant | kilka komponentów ma słabsze pokrycie i wymaga danych z `t-1` |
| canonical public-company Altman Z z market value equity | nie liczyć z samego XBRL | brak wartości rynkowej kapitału w Twoim zestawie danych |
| surowe wartości finansowe bez skalowania | nie używać bezpośrednio w QNN | QNN wymaga małej, skalowanej liczby cech; surowe poziomy zdominuje rozmiar spółki |

---

## 3. Dla których danych i wskaźników liczyć trend

### 3.1. Ogólna zasada

Trendy licz tak, żeby nie tworzyć sztucznych ekstremów i nie psuć interpretacji przy wartościach ujemnych.

| Typ zmiennej | Rekomendowana transformacja trendu | Przykład |
|---|---|---|
| dodatnie zmienne skali | `log(x_t / x_t-1)` albo `pct_change` po winsoryzacji | przychody, aktywa, zobowiązania, cash |
| wskaźniki finansowe | różnica rok do roku w punktach lub jednostkach wskaźnika | `roa_t - roa_t-1`, `current_ratio_t - current_ratio_t-1` |
| zmienne mogące być ujemne | zmiana skalowana przez aktywa lub przychody, nie procentowa | `(net_income_t - net_income_t-1) / assets_t-1` |
| wskaźniki z małym mianownikiem | winsoryzacja + flagi jakości | ROE, debt/equity, interest coverage |
| komponenty Beneish | relacje `t / t-1` zgodne z definicją indeksów | DSRI, GMI, AQI, SGI, DEPI, SGAI, LVGI |

### 3.2. Trendy obowiązkowe dla zmiennych źródłowych

| Zmienna | Trend | Decyzja | Uzasadnienie |
|---|---|---|---|
| `revenues` | `revenue_growth` | obowiązkowo | kluczowa dynamika biznesu i składnik Beneish `SGI` |
| `assets` | `asset_growth` | obowiązkowo | wzrost skali, potencjalnie nienaturalna ekspansja |
| `liabilities` | `liabilities_growth` | obowiązkowo | narastanie ryzyka finansowania |
| `equity` | `equity_change_to_assets` | obowiązkowo | erozja kapitału własnego / ujemny kapitał |
| `net_income` | `net_income_change_to_assets` | obowiązkowo | nie używać procentowej zmiany, bo zysk może być ujemny |
| `operating_cash_flow` | `ocf_change_to_assets` | obowiązkowo | pogorszenie gotówkowej jakości działalności |
| `cash` | `cash_growth` lub `cash_change_to_assets` | obowiązkowo | płynność buforowa |
| `current_assets` | `current_assets_growth` | opcjonalnie | pomocnicze do płynności |
| `current_liabilities` | `current_liabilities_growth` | opcjonalnie | szybki wzrost zobowiązań krótkoterminowych jest sygnałem ryzyka |
| `accounts_receivable` | `receivables_growth` | rekomendowane | ważne dla DSRI i jakości przychodów |
| `inventory` | `inventory_growth` | warunkowo | branżowe, ale ważne dla spółek produkcyjnych/handlowych |
| `cost_of_revenue` | `cost_of_revenue_growth` | warunkowo | potrzebne do trendu marży brutto |
| `capex` | `capex_change_to_assets` | rekomendowane | inwestycje mogą wyjaśniać zmiany aktywów i cash flow |
| `long_term_debt`, `short_term_debt` | `debt_growth` | warunkowo | użyteczne, ale pokrycie słabsze |
| `interest_expense` | `interest_expense_change_to_assets` | warunkowo | presja kosztów długu |
| `long_term_investments` | brak | nie liczyć w MVP | bardzo niskie pokrycie |

### 3.3. Trendy obowiązkowe dla wskaźników finansowych

| Wskaźnik | Trend | Decyzja | Dlaczego |
|---|---|---|---|
| `roa` | `delta_roa` | obowiązkowo | jeden z najlepszych sygnałów pogorszenia kondycji |
| `net_margin` | `delta_net_margin` | obowiązkowo | spadek rentowności sprzedaży |
| `operating_margin` | `delta_operating_margin` | obowiązkowo | pogorszenie operacyjne, mniej zależne od finansowania |
| `current_ratio` | `delta_current_ratio` | obowiązkowo | pogorszenie płynności |
| `cash_ratio` | `delta_cash_ratio` | rekomendowane | konserwatywny trend płynności |
| `working_capital_to_assets` | `delta_working_capital_to_assets` | obowiązkowo | ważne dla distress i Altman proxy |
| `liabilities_to_assets` | `delta_liabilities_to_assets` | obowiązkowo | wzrost dźwigni |
| `equity_to_assets` | `delta_equity_to_assets` | rekomendowane | erozja kapitału własnego |
| `asset_turnover` | `delta_asset_turnover` | rekomendowane | spadek efektywności aktywów |
| `ocf_to_assets` | `delta_ocf_to_assets` | obowiązkowo | spadek generowania gotówki |
| `ocf_margin` | `delta_ocf_margin` | rekomendowane | gotówkowa jakość sprzedaży |
| `accruals_to_assets` | `delta_accruals_to_assets` | rekomendowane | pogorszenie jakości wyniku |
| `interest_coverage` | `delta_interest_coverage` | warunkowo | mocny sygnał ryzyka długu, ale słabsze pokrycie |
| `gross_margin_proxy` | `delta_gross_margin_proxy` | warunkowo | potrzebne do Beneish GMI |
| `receivables_to_revenue` | `delta_receivables_to_revenue` | warunkowo | potrzebne do DSRI i jakości przychodów |
| `inventory_to_assets` | `delta_inventory_to_assets` | warunkowo | branżowe, ale użyteczne dla spółek z zapasami |
| `altman_z_proxy` | `delta_altman_z_proxy` | jako analiza pomocnicza | dobry syntetyczny sygnał pogorszenia, ale uważać na leakage |
| `beneish_m_score` | `delta_beneish_m_score` | tylko eksperyment dodatkowy | nie mieszać z targetem Beneish w tym samym wariancie cech |

### 3.4. Trendy jako cechy dla QNN

Dla QNN nie podawaj wszystkich trendów naraz. Najlepszy wariant to przygotować szeroki zestaw cech dla modeli klasycznych, a potem wybrać 4, 8 i 12 cech dla QNN.

Rekomendowane kandydaty do małowymiarowego QNN:

1. `roa`
2. `delta_roa`
3. `current_ratio`
4. `delta_current_ratio`
5. `liabilities_to_assets`
6. `delta_liabilities_to_assets`
7. `ocf_to_assets`
8. `revenue_growth`
9. `operating_margin`
10. `accruals_to_assets`
11. `asset_turnover`
12. `working_capital_to_assets`

Wariant 4-cechowy QNN: `roa`, `current_ratio`, `liabilities_to_assets`, `ocf_to_assets`.  
Wariant 8-cechowy QNN: powyższe + `revenue_growth`, `delta_roa`, `delta_current_ratio`, `accruals_to_assets`.  
Wariant 12-cechowy QNN: powyższe + `operating_margin`, `asset_turnover`, `working_capital_to_assets`, `delta_liabilities_to_assets`.

---

## 4. Metodologia targetu

### 4.1. Decyzja główna

**Główny target w pracy powinien być targetem przyszłego pogorszenia kondycji finansowej:**

```text
target_future_deterioration_1y(i, t) = 1,
jeżeli spółka i w roku t+1 spełnia co najmniej 2 z 5 kryteriów pogorszenia.
W przeciwnym razie target = 0.
```

Dlaczego to jest najlepsze:

1. Jest zgodne z osią pracy: ryzyko pogorszenia kondycji finansowej.
2. Nie wymaga zewnętrznych danych o faktycznym bankructwie ani fraudzie.
3. Można go zbudować wyłącznie z SEC/XBRL.
4. Pozwala zachować logikę predykcyjną: cechy z roku `t` przewidują stan w roku `t+1`.
5. Jest bezpieczniejszy metodologicznie niż udawanie, że Beneish oznacza prawdziwy fraud.

### 4.2. Proponowana definicja targetu głównego

Dla każdej obserwacji spółka-rok `(i, t)` tworzysz cechy z roku `t`. Następnie liczysz warunki pogorszenia w roku `t+1`.

| Kod | Kryterium w roku `t+1` | Definicja robocza | Sens finansowy |
|---|---|---|---|
| `C1_profitability` | pogorszenie rentowności | `roa_t+1 < 0` **lub** `roa_t+1 - roa_t <= -0.03` | spadek zdolności generowania zysku |
| `C2_cashflow` | pogorszenie gotówki operacyjnej | `ocf_to_assets_t+1 < 0` **lub** `ocf_to_assets_t+1 - ocf_to_assets_t <= -0.03` | zysk bez gotówki / problemy operacyjne |
| `C3_liquidity` | pogorszenie płynności | `current_ratio_t+1 < 1.0` **lub** `current_ratio_t+1 / current_ratio_t <= 0.80` | wzrost ryzyka krótkoterminowego |
| `C4_leverage` | wzrost zadłużenia | `liabilities_to_assets_t+1 >= 0.80` **lub** `liabilities_to_assets_t+1 - liabilities_to_assets_t >= 0.10` | rosnąca presja finansowania |
| `C5_revenue` | spadek skali działalności | `revenue_growth_t+1 <= -0.10` | kurczenie się biznesu |

Następnie:

```text
deterioration_score_t+1 =
  C1_profitability
+ C2_cashflow
+ C3_liquidity
+ C4_leverage
+ C5_revenue

target_future_deterioration_1y = 1 if deterioration_score_t+1 >= 2 else 0
```

**Analiza wrażliwości:** po pierwszym uruchomieniu pipeline sprawdź rozkład klas dla progów `>=1`, `>=2`, `>=3`. Jako główny wybierz próg, który daje finansowo sensowną i nieekstremalnie niezbalansowaną klasę pozytywną. Najbardziej prawdopodobny wybór to `>=2`.

### 4.3. Warianty targetu do porównania

| Wariant | Definicja | Status w pracy | Zasada anty-leakage |
|---|---|---|---|
| `target_future_deterioration_1y` | przyszłe pogorszenie według 2 z 5 kryteriów | **target główny** | cechy tylko z roku `t`, target z `t+1` |
| `target_altman_distress_next_year` | `Altman_Z_proxy_t+1` w strefie distress albo przejście do gorszej strefy | target pomocniczy / robustness check | nie używać `altman_z_proxy_t` jako cechy w tym samym wariancie albo jasno wydzielić eksperyment |
| `target_beneish_risk_next_year` | `Beneish_M_t+1 > -2.22` | eksperyment dodatkowy | nie używać komponentów Beneish z `t+1`; najlepiej nie używać pełnego Beneish jako cechy |
| `target_current_beneish_screening` | `Beneish_M_t > -2.22` | tylko screening, nie forecasting | opisać jako klasyfikację proxy stanu bieżącego, nie predykcję fraudu |
| `target_mixed_risk` | połączenie deterioration + Altman/Beneish | nie rekomenduję jako głównego | zbyt trudne do obrony i mniej czytelne |

### 4.4. Reguły, które trzeba zapisać w metodologii

1. Jednostką obserwacji jest `company-year`.
2. Cechy wejściowe pochodzą z roku `t` i ewentualnie z trendu `t` względem `t-1`.
3. Target główny dotyczy roku `t+1`.
4. Obserwacje bez pełnych danych do targetu w roku `t+1` są usuwane z eksperymentu głównego.
5. Cechy syntetyczne użyte do targetu nie powinny być jednocześnie bezpośrednio używane jako cechy w tym samym eksperymencie, jeśli grozi to mechanicznym odtwarzaniem etykiety.
6. Podział danych powinien być czasowy, np. train: wcześniejsze lata, validation: kolejny rok, test: najnowsze lata.
7. Dla modeli porównawczych i QNN używać tych samych podziałów danych i tych samych metryk.
8. Dla QNN przygotować warianty 4, 8 i 12 cech po selekcji/redukcji wymiaru.

### 4.5. Podział danych i ewaluacja

Rekomendowany split:

```text
train: najstarsze lata, np. 2015-2020/2021
validation: kolejny rok, np. 2021/2022
test: najnowsze lata, np. 2023-2024 albo 2022-2024, zależnie od dostępności
```

Jeżeli okres danych jest inny, zasada pozostaje taka sama: **model uczy się na przeszłości i jest testowany na późniejszych latach**. Random split może zawyżać wyniki, bo podobne obserwacje tej samej spółki z sąsiednich lat mogą trafić jednocześnie do train i test.

Metryki:

| Metryka | Decyzja |
|---|---|
| `ROC-AUC` | obowiązkowo |
| `PR-AUC` | obowiązkowo, szczególnie przy niezbalansowanych klasach |
| `F1-score` | obowiązkowo |
| `balanced_accuracy` | obowiązkowo |
| `precision`, `recall` | obowiązkowo |
| `confusion_matrix` | obowiązkowo w rozdziale wynikowym |
| czas treningu | obowiązkowo dla QNN vs klasyczne ML |
| stabilność między seedami | rekomendowane, szczególnie dla QNN |

---

## 5. Finalna rekomendacja eksperymentów

### Eksperyment 1 — baseline na pełnym zestawie wskaźników

- Cechy: wszystkie wskaźniki główne + trendy obowiązkowe.
- Modele: Logistic Regression, Random Forest, XGBoost/LightGBM, SVM, MLP.
- Target: `target_future_deterioration_1y`.
- Cel: ustalić mocny punkt odniesienia.

### Eksperyment 2 — modele klasyczne na cechach ograniczonych do QNN

- Cechy: dokładnie te same 4/8/12 cech, które potem dostaje QNN.
- Cel: uczciwe porównanie, bo QNN nie powinien być porównywany z Random Forest na 50 cechach, jeśli sam dostaje 8.

### Eksperyment 3 — QNN/VQC

- Cechy: warianty 4, 8, 12.
- Kodowanie: angle encoding jako MVP.
- Ansatz: prosty ansatz z rotacjami i splątaniem.
- Wynik: porównanie z modelami klasycznymi na identycznym zbiorze cech.

### Eksperyment 4 — wpływ targetu / proxy

- Wariant A: `target_future_deterioration_1y` — główny.
- Wariant B: `target_altman_distress_next_year` — robustness check.
- Wariant C: `target_beneish_risk_next_year` — eksperyment dodatkowy, jeśli pokrycie składników jest wystarczające.

### Eksperyment 5 — interpretacja i ograniczenia

- Feature importance / permutation importance / SHAP dla modeli klasycznych.
- Dla QNN: analiza wrażliwości predykcji na zmianę pojedynczej cechy.
- Dyskusja: czy QNN ma sens praktyczny, czy tylko poznawczy/metodologiczny.

---

## 6. Najkrótsza decyzja operacyjna

1. **Licz najpierw 15 wskaźników głównych** z sekcji 2.1.
2. **Dodaj trendy obowiązkowe**: `revenue_growth`, `delta_roa`, `delta_current_ratio`, `delta_liabilities_to_assets`, `delta_ocf_to_assets`, `delta_net_margin`, `delta_operating_margin`, `asset_growth`, `liabilities_growth`, `net_income_change_to_assets`.
3. **Target główny:** `target_future_deterioration_1y`, czyli co najmniej 2 z 5 sygnałów pogorszenia w roku `t+1`.
4. **Altman:** licz jako `Altman_Z_proxy`, ale traktuj jako cechę pomocniczą albo oddzielny target, nie jako prawdę o bankructwie.
5. **Beneish:** licz jako eksperyment dodatkowy; nie opieraj całej pracy wyłącznie na Beneish, bo to proxy i ma słabsze pokrycie składników.
6. **Do QNN nie podawaj wszystkiego.** Przygotuj warianty 4, 8 i 12 cech oraz porównaj z klasycznymi modelami na tych samych cechach.

---

## 7. Checklist do implementacji w notebookach

- [ ] `01_data_quality_coverage.ipynb` — raport pokrycia zmiennych i filtracja próby.
- [ ] `02_financial_ratios.ipynb` — obliczenie wskaźników głównych i dodatkowych.
- [ ] `03_trends_and_targets.ipynb` — trendy, target główny, targety pomocnicze.
- [ ] `04_feature_selection.ipynb` — warianty 4/8/12/20 cech.
- [ ] `05_classical_baselines.ipynb` — modele klasyczne.
- [ ] `06_qnn_vqc.ipynb` — QNN/VQC.
- [ ] `07_results_and_error_analysis.ipynb` — wyniki, confusion matrix, stabilność, analiza błędów.

---

## 8. Nazwy kolumn rekomendowane do finalnego datasetu

Przykładowe kolumny identyfikacyjne:

```text
cik, ticker, company_name, fiscal_year, sic, sector, form, filing_date
```

Przykładowe kolumny cech:

```text
current_ratio, cash_ratio, working_capital_to_assets,
liabilities_to_assets, equity_to_assets, liabilities_to_equity,
roa, roe, net_margin, operating_margin,
asset_turnover, ocf_to_assets, ocf_margin, accruals_to_assets,
log_assets,
revenue_growth, asset_growth, liabilities_growth,
delta_roa, delta_current_ratio, delta_liabilities_to_assets,
delta_ocf_to_assets, delta_net_margin, delta_operating_margin,
altman_z_proxy, beneish_m_score
```

Przykładowe kolumny targetów:

```text
deterioration_score_next_year,
target_future_deterioration_1y,
target_altman_distress_next_year,
target_beneish_risk_next_year
```

Przykładowe flagi jakości:

```text
has_core_ratios,
has_extended_ratios,
has_altman_proxy,
has_beneish_full,
has_negative_equity,
has_small_denominator,
missing_core_count,
missing_extended_count
```

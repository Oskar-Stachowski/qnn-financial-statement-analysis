# Instrukcja Commit 8: dataset modelowy ML/QNN

Cel commita 8: przygotowac pierwszy dataset gotowy do modelowania na podstawie oczyszczonych danych SEC Company Facts z etapu 5/commitow 06-07 oraz wykonac eksploracje danych przed eksperymentami ML/QNN.

Commit 8 powinien byc wykonany przede wszystkim w Jupyter Notebook, poniewaz jest to etap eksploracyjny i przed-eksperymentalny do pracy magisterskiej SGH. Notebook ma laczyc przygotowanie datasetu modelowego z EDA, wykresami, kontrola jakosci, dokumentacja decyzji metodologicznych i audytowalnymi outputami CSV.

Commit 8 nie powinien trenowac modeli ML/QNN. Ma przygotowac deterministyczny, audytowalny zbior obserwacji `company-year`, feature'y finansowe, target pogorszenia sytuacji finansowej w kolejnym roku oraz podzial train/validation/test.

Notebook moze zawierac komentarze metodologiczne i techniczne, ale nie powinien generowac gotowych wnioskow badawczych do pracy dyplomowej. Interpretacja wynikow i decyzje metodologiczne naleza do autora.

## 1. Wejscia

Skrypt commit 8 powinien korzystac z:

- `data/interim/sec_facts_wide.csv`,
- `data/interim/sec_facts_long.csv`, jesli potrzebny jest audyt zrodel,
- `data/reports/sec_facts_sanity_warnings.csv`,
- `data/reports/sec_facts_sanity_summary.csv`,
- `configs/dataset_config.yaml`.

Zakladany zakres danych:

- source years: `2011-2025`,
- feature years: `2011-2024`,
- target horizon: `+1 rok`,
- train: `2011-2020`,
- validation: `2021-2022`,
- test: `2023-2024`.

Rok `2025` nie jest rokiem feature'ow. Jest potrzebny tylko do policzenia targetu dla obserwacji z `2024`.

## 2. Proponowany notebook i kod pomocniczy

Glowny artefakt commita 8:

```text
notebooks/08_modeling_dataset_eda.ipynb
```

Notebook ma:

1. Wczytac dane wide z `sec_facts_wide.csv`.
2. Wczytac warningi sanity check z `sec_facts_sanity_warnings.csv`.
3. Oznaczyc obserwacje i zmienne problematyczne na podstawie warningow.
4. Wyliczyc feature'y finansowe.
5. Wyliczyc target pogorszenia w roku `t+1`.
6. Przypisac split: `train`, `validation`, `test`.
7. Zapisac dataset modelowy i raporty jakosci.
8. Wykonac eksploracje danych przed modelowaniem.
9. Wygenerowac wykresy diagnostyczne i zapisac je do plikow.

Opcjonalnie, jesli notebook stanie sie zbyt dlugi, mozna wydzielic czesc deterministycznej logiki do:

```text
src/data/08_build_modeling_dataset.py
```

W zrealizowanej wersji `src/data/08_build_modeling_dataset.py` powinien pozostac cienkim runnerem pipeline'u, a deterministyczna logika produkcji CSV/raportow powinna znajdowac sie w:

```text
src/data/modeling_dataset.py
```

Notebook powinien nadal pozostac glownym miejscem eksploracji, wykresow i decyzji przed-eksperymentalnych, a runner powinien tylko odtwarzac produkcje finalnych CSV.

## 2.1. Zakres eksploracji danych w notebooku

Notebook powinien zawierac co najmniej:

1. Podsumowanie liczby spolek i company-years przed oraz po filtrach.
2. Pokrycie kluczowych zmiennych przed i po czyszczeniu.
3. Liczbe wykluczen wedlug `check_name`.
4. Analize brakow danych po zmiennych i po latach.
5. Rozklady podstawowych zmiennych finansowych.
6. Rozklady wskaznikow finansowych przed winsoryzacja lub innym czyszczeniem outlierow.
7. Rozklady targetu lacznie i w splitach.
8. Porownanie train/validation/test pod wzgledem liczby obserwacji, sektorow i targetu.
9. Kontrole leakage: potwierdzenie, ze feature year konczy sie na `2024`, a `2025` sluzy tylko do targetu.
10. Liste decyzji, ktore powinny zostac zatwierdzone przez autora przed eksperymentami.

## 2.2. Wykresy

Notebook powinien generowac wykresy diagnostyczne, np.:

- liczba company-years po latach,
- liczba spolek po latach,
- coverage zmiennych finansowych,
- liczba warningow wedlug `check_name`,
- liczba wykluczen wedlug powodu,
- rozklady `assets`, `revenues`, `net_income`, `liabilities`,
- rozklady ratio features, np. `debt_to_assets`, `roa`, `profit_margin`, `current_ratio`,
- target distribution w `train`, `validation`, `test`,
- missing values heatmap lub bar chart,
- korelacje wybranych feature'ow.

Wykresy zapisac do katalogu:

```text
reports/figures/commit_8/
```

Nazwy plikow powinny byc stabilne i opisowe, np.:

```text
company_years_by_year.png
feature_coverage_after_cleaning.png
warnings_by_check_name.png
target_distribution_by_split.png
ratio_feature_distributions.png
```

Wykresy maja sluzyc eksploracji i dokumentacji przed-eksperymentalnej, nie jako finalne wykresy do pracy magisterskiej bez dalszej redakcji.

## 3. Outputy

Minimalne outputy:

```text
data/processed/modeling_dataset.csv
data/processed/modeling_dataset_excluded.csv
data/reports/modeling_dataset_split_summary.csv
data/reports/modeling_dataset_feature_coverage.csv
data/reports/modeling_dataset_quality_report.md
```

Output notebooka:

```text
notebooks/08_modeling_dataset_eda.ipynb
reports/figures/commit_8/*.png
```

Opcjonalnie, jesli bedzie to wygodne:

```text
data/processed/modeling_dataset_features.csv
data/processed/modeling_dataset_targets.csv
```

## 4. Reguly filtrowania warningow z commit 07

Commit 8 powinien traktowac warningi z `07` jako wejscie do regulek czyszczenia, a nie jako blad parsera.

### 4.1. Hard exclude company-year

Obserwacje `company-year` powinny byc wykluczone z datasetu glownego, jesli maja ktorykolwiek z tych warningow:

```text
wide_duplicate_company_year
long_duplicate_company_year_variable
wide_value_differs_from_long
source_form_outside_dataset_config
source_unit_outside_accepted_units
source_tag_not_in_sec_tags_config
source_filing_before_period_end
source_filing_lag_too_long
source_filing_year_after_company_year_window
flow_period_not_annual
revenues_may_be_quarterly
mixed_source_fiscal_years
mixed_source_period_ends
company_year_not_numeric
company_year_in_future
assets_negative
liabilities_and_equity_negative
liabilities_negative
assets_differs_from_liabilities_and_equity
liabilities_absurdly_above_assets
sparse_company_year
```

Te przypadki sa ryzykowne dla modelowania, bo wskazuja na problem techniczny, niespojnosc bilansu albo zbyt uboga obserwacje.

### 4.2. Feature-level cleanup, nie globalny drop

Ponizsze warningi powinny ustawic konkretna zmienna lub konkretny wskaznik na missing, ale nie powinny automatycznie usuwac calego company-year:

```text
cash_negative
cash_above_assets
accounts_receivable_above_assets
inventory_above_assets
ppe_above_assets
goodwill_above_assets
current_assets_above_assets
current_liabilities_above_liabilities
capex_negative
cost_of_revenue_negative
operating_costs_negative
cost_of_revenue_above_operating_costs
```

Przyklady:

- `cash_negative` -> nie liczyc `cash_to_assets`,
- `ppe_above_assets` -> nie liczyc feature'ow opartych na `ppe`,
- `cost_of_revenue_above_operating_costs` -> nie uzywac `cost_of_revenue` dla tej obserwacji,
- `capex_negative` -> ustawic `capex` na missing dla feature'ow.

### 4.3. Flagi diagnostyczne

Ponizsze warningi powinny zostac przeniesione do datasetu jako flagi diagnostyczne, ale nie powinny same usuwac obserwacji:

```text
large_assets_liabilities_equity_gap
mixed_source_accessions
flow_source_fp_not_fy
net_loss_abs_large_relative_to_revenues
net_profit_large_relative_to_revenues
net_loss_abs_large_relative_to_assets
net_profit_large_relative_to_assets
```

Interpretacja:

- `large_assets_liabilities_equity_gap` to ostrzezenie bilansowe, ale slabsze niz `assets_differs_from_liabilities_and_equity`.
- `mixed_source_accessions` jest akceptowalne, jesli nie wystepuje razem z `mixed_source_period_ends`.
- `flow_source_fp_not_fy` jest akceptowalne, jesli okres `start-end` ma dlugosc roczna.
- duze zyski/straty wzgledem malego mianownika powinny byc obslugiwane przez flagi i winsoryzacje, nie przez automatyczny drop.

### 4.4. Company-level coverage filters

Ponizsze warningi powinny byc uzyte do decyzji o wykluczeniu spolki z glownego datasetu albo do oznaczenia jej jako low coverage:

```text
assets_missing_for_majority_of_years
liabilities_missing_for_majority_of_years
revenues_missing_for_majority_of_years
net_income_missing_for_majority_of_years
equity_missing_for_majority_of_years
operating_cash_flow_missing_for_majority_of_years
```

Rekomendacja dla datasetu glownego:

- wymagac obecnosci `assets`, `liabilities`, `revenues`, `net_income` dla obserwacji wykorzystywanych do targetu,
- rozwazyc wykluczenie calej spolki, jesli kluczowa zmienna jest dostepna w mniej niz 50% lat.

## 5. Feature engineering

Feature'y bazowe powinny wynikac z `configs/dataset_config.yaml`.

Minimalny zestaw:

```text
current_ratio = current_assets / current_liabilities
debt_to_assets = liabilities / assets
liabilities_to_equity = liabilities / equity
roa = net_income / assets
roe = net_income / equity
profit_margin = net_income / revenues
asset_turnover = revenues / assets
sales_growth = revenues_t / revenues_t_minus_1 - 1
working_capital_to_assets = (current_assets - current_liabilities) / assets
cash_to_assets = cash / assets
```

Reguly bezpiecznego liczenia:

- nie dzielic przez zero,
- nie liczyc ratio, jesli mianownik jest missing,
- nie liczyc ratio, jesli mianownik jest niematerialnie maly,
- dla `profit_margin` wymagac dodatnich `revenues`,
- dla `roa`, `asset_turnover`, `debt_to_assets`, `working_capital_to_assets`, `cash_to_assets` wymagac dodatnich `assets`,
- dla `current_ratio` wymagac dodatnich `current_liabilities`,
- dla `liabilities_to_equity` i `roe` ostroznie traktowac ujemne lub bardzo male `equity`; zapisac flage zamiast automatycznie usuwac obserwacje.

Commit 8 nie powinien jeszcze robic skalowania pod model, PCA ani kodu QNN.

## 6. Target pogorszenia sytuacji finansowej

Target ma porownywac rok `t` z rokiem `t+1`.

Konfiguracja z `dataset_config.yaml`:

```text
roa_drop_pct: 0.20
profit_margin_drop_pct: 0.20
debt_to_assets_increase_pct: 0.10
current_ratio_drop_pct: 0.15
min_conditions_met: 2
```

Proponowana logika:

```text
roa_deteriorated = roa_next <= roa_current * (1 - roa_drop_pct)
profit_margin_deteriorated = profit_margin_next <= profit_margin_current * (1 - profit_margin_drop_pct)
debt_to_assets_deteriorated = debt_to_assets_next >= debt_to_assets_current * (1 + debt_to_assets_increase_pct)
current_ratio_deteriorated = current_ratio_next <= current_ratio_current * (1 - current_ratio_drop_pct)

financial_deterioration_next_year = liczba_spelnionych_warunkow >= min_conditions_met
```

Wazne:

- target dla `2024` wymaga danych z `2025`,
- `2025` nie moze trafic jako feature year do train/validation/test,
- obserwacje bez wystarczajacych danych do targetu powinny trafic do `modeling_dataset_excluded.csv` z powodem wykluczenia,
- nie wolno uzywac danych z roku `t+1` w feature'ach roku `t`, poza samym targetem.

## 7. Splity

Podzial musi byc zgodny z konfiguracja:

```text
train: 2011-2020
validation: 2021-2022
test: 2023-2024
```

Skrypt powinien dodac kolumne:

```text
split
```

Do raportu `modeling_dataset_split_summary.csv` zapisac:

```text
split
feature_year_min
feature_year_max
row_count
company_count
positive_target_count
positive_target_ratio
missing_target_count
```

## 8. Missing values i outliery

Commit 8 powinien przygotowac dane do modelowania i pokazac konsekwencje decyzji czyszczacych w notebooku, ale nie musi jeszcze wykonywac finalnej imputacji modelowej.

Zalecane:

- zapisac surowe feature'y po czyszczeniu technicznym,
- zapisac flagi missing/outlier,
- nie imputowac medianami globalnie w tym kroku, chyba ze zostanie to jawnie opisane w raporcie,
- winsoryzacje ratio robic tylko na podstawie train split i zastosowac te same progi do validation/test,
- zapisac progi winsoryzacji w raporcie, jesli zostana uzyte.

## 9. Raport jakosci datasetu modelowego

`modeling_dataset_quality_report.md` powinien zawierac:

- liczbe wejściowych company-years,
- liczbe wykluczonych company-years,
- najczestsze powody wykluczenia,
- liczbe obserwacji w train/validation/test,
- coverage feature'ow po czyszczeniu,
- liczbe obserwacji z targetem,
- rozklad targetu w splitach,
- liste warningow z `07`, ktore zostaly uzyte jako hard exclude,
- liste warningow z `07`, ktore zostaly uzyte jako feature-level cleanup,
- liste warningow z `07`, ktore zostaly zachowane jako flagi.

Raport nie powinien zawierac interpretacji badawczej ani wnioskow o kondycji spolek.

Notebook moze zawierac dodatkowe komentarze robocze, ale powinien jasno rozdzielac:

- fakty techniczne z danych,
- decyzje metodologiczne autora,
- robocze obserwacje eksploracyjne,
- rzeczy do sprawdzenia przed eksperymentami.

## 9.1. Kontekst pracy magisterskiej SGH

Commit 8 powinien byc przygotowany tak, zeby wspieral transparentnosc procesu badawczego:

- pokazac, jakie reguly czyszczenia zostaly zastosowane,
- pokazac, ile obserwacji zostalo usunietych i dlaczego,
- pokazac, jak powstaje target,
- pokazac, czy splity sa zgodne z metodologia,
- nie ukrywac brakow ani outlierow,
- nie generowac narracji badawczej zamiast autora.

W notebooku warto dodac sekcje:

```text
Decyzje metodologiczne do zatwierdzenia przez autora
```

Ta sekcja powinna listowac decyzje takie jak:

- minimalne progi mianownikow dla ratio,
- hard exclude vs feature-level cleanup,
- sposob traktowania spolek z niskim coverage,
- winsoryzacja lub brak winsoryzacji,
- finalna definicja targetu.

## 10. Kryteria akceptacji Commit 8

Commit 8 mozna uznac za gotowy, gdy:

1. Istnieje `notebooks/08_modeling_dataset_eda.ipynb`.
2. Notebook mozna uruchomic od poczatku do konca bez recznych krokow.
3. Istnieje `data/processed/modeling_dataset.csv`.
4. Istnieje `data/processed/modeling_dataset_excluded.csv`.
5. Istnieje `data/reports/modeling_dataset_split_summary.csv`.
6. Istnieje `data/reports/modeling_dataset_feature_coverage.csv`.
7. Istnieje `data/reports/modeling_dataset_quality_report.md`.
8. Istnieja wykresy w `reports/figures/commit_8/`.
9. Dataset nie zawiera feature years poza `2011-2024`.
10. Target dla `2024` korzysta z danych `2025`.
11. Splity sa zgodne z konfiguracja.
12. Obserwacje wykluczone maja jawny powod wykluczenia.
13. Feature'y nie uzywaja danych z przyszlosci.
14. Notebook pokazuje coverage, warningi, missing values, outliery, target i splity.
15. Notebook zawiera sekcje decyzji metodologicznych do zatwierdzenia przez autora.

## 11. Proponowany tytul commita

```text
dane: dataset modelowy
```

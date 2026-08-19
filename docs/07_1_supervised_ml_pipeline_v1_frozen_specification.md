# Supervised ML pipeline v1.0.0 — frozen specification

Status: **FROZEN**
Version: **1.0.0**
Freeze date: **2026-08-19**
Freeze verdict source: `notebooks/04_selection_bias_and_pipeline_freeze_gate.ipynb`

## 1. Cel i granica zamrożenia

Niniejszy dokument formalnie zamraża pipeline danych dla późniejszego etapu
supervised ML. Zamrożenie obejmuje supervised sample, preprocessing, frozen
feature blocks, temporal CV, primary ranking rule, clustered inference,
obowiązkowe ablations/robustness checks, odrzucenie IPW oraz politykę external
validation i testu.

Zamrożenie **nie obejmuje** rodzin modeli, architektur, hiperparametrów,
class-imbalance policy, budżetu treningowego, decision threshold, calibration ani
final refit policy. Żaden model predykcyjny nie został wytrenowany. Te elementy
muszą otrzymać osobną, późniejszą specyfikację i freeze przed otwarciem external
validation lub testu.

Autorytatywną konfiguracją maszynową jest
`configs/supervised_ml_pipeline_v1.yaml`. Manifest hashy znajduje się w
`configs/supervised_ml_pipeline_v1_freeze_manifest.yaml`.

## 2. Immutable upstream inputs

Pipeline używa bez modyfikacji:

1. `target_candidate_v2_pit_b` v1.0.0;
2. historical research universe v1.1.0;
3. raw point-in-time `X_t` v1.0.0.

Ich wersje, manifesty i artifact SHA-256 są zapisane w konfiguracji i manifeście
pipeline. Zmiana któregokolwiek upstream input wymaga nowej wersji pipeline i
ponownego audytu. Ten freeze nie nadpisuje ani nie rozszerza zakresu upstream
freeze packages.

## 3. Frozen supervised sample

Jednostką jest eligible company-year. Wiersz należy do głównej supervised sample
wyłącznie wtedy, gdy:

- `membership_status == eligible`;
- `target_status == available`;
- `x_t_status in {available_core, partially_available}`.

Brak pojedynczych frozen financial features nie usuwa wiersza. Frozen counts:

| Zakres | Lata | N |
|---|---:|---:|
| development | 2011–2022 | 23 218 |
| train/CV pool | 2011–2020 | 19 671 |
| external development validation | 2021–2022 | 3 547 |

Manifest przechowuje także SHA-256 dokładnego, posortowanego zbioru kanonicznych
`research_universe_company_year_id` dla development, train i validation. Dzięki
temu równoważna liczebność przy innej membership nie przejdzie freeze-lock testu.

Estimand jest jawnie warunkowy na dostępność targetu i dopuszczony status `X_t`.
Wyników nie wolno przedstawiać jako bezwarunkowo reprezentatywnych dla non-XBRL,
target-unavailable lub `X_t`-unavailable company-years.

## 4. Frozen feature blocks

### L

`log_assets_t`, `roa_t`, `ocf_to_assets_t`, `current_ratio_t`,
`liabilities_to_assets_t`, `working_capital_to_assets_t`,
`accruals_to_assets_t`.

### D

`asset_growth_1y`, `delta_roa_1y`, `delta_ocf_to_assets_1y`,
`current_ratio_change_1y`, `delta_liabilities_to_assets_1y`.

### R

`log1p_revenues_t`, `profit_margin_t`, `ocf_margin_t`, `asset_turnover_t`,
`revenue_growth_1y`.

Dozwolone główne porównania są dokładnie trzy: L, L+D oraz L+D+R. Wszystkie
używają tej samej głównej supervised sample. Brak R nie usuwa obserwacji z
L+D+R. `economic_group_id` nigdy nie jest predictorem.

## 5. Frozen preprocessing C

Dla każdego train partition, a w CV dla każdego fold train i feature block,
powstaje nowa instancja preprocessora. Validation jest wyłącznie transformowana.

Financial branch:

1. per-feature winsorization p1/p99, fitted na obserwowanych wartościach train;
2. per-feature train median imputation;
3. `StandardScaler` fitted na train po winsoryzacji i imputacji, ze skalą
   populacyjną (`ddof=0`).

Równoległa indicator branch tworzy jeden binary missing indicator na każdą cechę
z raw pre-imputation missingness. Indicators mają wartości 0/1, nie są
winsoryzowane ani skalowane i są dołączane po financial features.

Żadna statystyka validation nie może wpływać na quantile caps, mediany, mean ani
scale. Transformacja nie może usuwać wierszy.

## 6. Frozen PIT-safe temporal CV

Główny CV ma sześć expanding-window foldów:

| Fold | Train feature years | Embargo | Validation |
|---|---|---|---|
| fold_2015 | 2011–2013 | 2014 | 2015 |
| fold_2016 | 2011–2014 | 2015 | 2016 |
| fold_2017 | 2011–2015 | 2016 | 2017 |
| fold_2018 | 2011–2016 | 2017 | 2018 |
| fold_2019 | 2011–2017 | 2018 | 2019 |
| fold_2020 | 2011–2018 | 2019 | 2020 |

Po year-based embargo każdy training row musi dodatkowo spełnić:

`target_available_at <= min(prediction_timestamp in validation fold)`.

Przyszły rok nigdy nie może znaleźć się w training względem validation. Exact
cutoff timestamps i oczekiwane liczebności foldów są zapisane w konfiguracji.
Zmiana foldów, embargo lub cutoff rule wymaga nowej wersji pipeline.

## 7. Frozen ranking i raportowanie

Primary ranking rule to pooled OOF PR-AUC na połączonych OOF predictions z
validation years 2015–2020. Najpierw łączone są wszystkie OOF rows, następnie
liczona jest jedna primary metric.

Obowiązkowo raportuje się także PR-AUC każdego folda oraz arithmetic mean i sample
standard deviation sześciu wartości (`ddof=1`). Secondary metrics nie mogą zmienić
primary ranking.

## 8. Frozen clustered inference

Primary confidence interval powstaje przez clustered bootstrap:

- cluster: `economic_group_id`;
- 2 000 replikacji;
- resampling unique economic groups with replacement;
- każdy draw zachowuje wszystkie rows i multiplicity wylosowanej grupy;
- 95% percentile CI: quantile 2,5% i 97,5%;
- fixed seed: `20260818`;
- single-class replicate jest deterministycznie losowany ponownie, a liczba
  odrzuceń raportowana.

Row-level bootstrap nigdy nie jest głównym CI. Group ID pozostaje wyłącznie
metadata.

## 9. Frozen mandatory ablations i robustness checks

Wszystkie poniższe analizy są obowiązkowe, lecz żadna nie może zastąpić primary
ranking ani zmienić głównej sample policy:

1. **B bez missing indicators** — te same rows i pozostały preprocessing;
2. **complete-case** — block-specific exclusion, robustness only;
3. **no-winsorization** — ta sama sample, median imputation, indicators i scaling;
4. **purged economic-group CV** — z fold train usuwa grupy obecne w fold
   validation; temporal folds i validation rows pozostają bez zmian; jest to
   unseen-group estimand;
5. **sparse-row robustness** — liczba dostępnych cech jest obliczana przed
   imputacją na wszystkich 17 frozen financial features; w powtórzeniu wyklucza
   się rows z `available_feature_count <= 10`, czyli zachowuje co najmniej 11/17.

Sparse-row check stosuje filtr do train i evaluation partitions w osobnym
robustness rerun. Główna sample pozostaje bez zmian. Check nie jest alternatywną
sample policy, nie uczestniczy w primary ranking i nie może zostać aktywowany ani
wybrany po obejrzeniu testu.

## 10. Selection bias i IPW

Obowiązkowe pozostaje raportowanie composition/retention według roku, sektora,
time-t size, `x_t_status`, XBRL availability, available feature count i klasy
targetu. Non-XBRL observations pozostają poza model matrix i muszą być jawnie
opisane jako ograniczenie zakresu.

IPW dla target availability zostało diagnostycznie ocenione i odrzucone z powodu
poor positivity, extreme weights, niskiego ESS, braku jednolitej poprawy balance,
niewiarygodnego założenia MAR przy time-t-only covariates oraz braku możliwości
odtworzenia support non-XBRL/unavailable `X_t`.

IPW-weighted predictive metrics są niedozwolone w v1.0.0. Ponowne rozważenie IPW
wymaga nowej wersji pipeline i nowego audytu; nie może być decyzją podjętą na
podstawie predictive performance.

## 11. External validation i test

Lata 2021–2022 są one-shot no-tune external development validation. W pipeline
freeze dozwolono wyłącznie sprawdzenie minimalnego indeksu i liczebności; target
values i financial features nie zostały otwarte analitycznie.

External validation może zostać otwarta dopiero po osobnym zamrożeniu model
family, hyperparameters, training budget/seeds, class-imbalance policy,
threshold/calibration i final refit policy. Po obejrzeniu wyników nie wolno
dostrajać pipeline i nadal nazywać 2021–2022 niezależną validation. Niepowodzenie
oznacza no-go albo jawnie nową wersję, w której validation jest zadeklarowana jako
spent.

Test 2023–2024 nie został użyty. Nie może zostać otwarty przed pełnym freeze etapu
modelowego i nie może wybierać sample, preprocessingu, blocks, CV, metrics,
inference ani robustness policies.

## 12. Zasada zmian

Każda zmiana elementu objętego tym dokumentem wymaga:

1. nowego numeru wersji pipeline;
2. jawnego uzasadnienia metodologicznego;
3. nowego development-only audytu;
4. nowej konfiguracji, specyfikacji i manifestu;
5. aktualizacji freeze-lock tests.

Nie wolno edytować v1.0.0 in place. Manifest celowo nie hashuje samego siebie,
containing commit ani freeze-lock testu, aby uniknąć samoreferencji. Commit
zawierający freeze package jest autorytatywną wersją repozytorium.

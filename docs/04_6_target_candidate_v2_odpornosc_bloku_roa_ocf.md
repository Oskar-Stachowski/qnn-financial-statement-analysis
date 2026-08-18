# Odporność `target_candidate_v2` na blok ROA–OCF/assets

Data analizy: 2026-08-17.

> **Status metodologiczny (2026-08-18): analiza historyczna, pre-PIT.**
> Wyniki agreement, Jaccard i leave-one-component-out dotyczą wspólnej próby
> 19 957 obserwacji z wcześniejszej ekstrakcji. Uzasadniają prerejestrację
> wariantu `operating_performance = max(D1, D2)`, lecz nie zastępują jego
> ponownego obliczenia na zamrożonej populacji PIT-B. Lata 2023–2024 nie były
> użyte w tej analizie; wcześniejsze dokumenty opisowe pokazały jednak ich
> agregaty, dlatego nie są one globalnie nieoglądanym holdoutem dla targetu.

## 1. Cel i zakres

Analiza sprawdza, czy bazowy [`target_candidate_v2`](./04_3_target_candidate_v2_definicja.md) nadmiernie zależy od jednoczesnego naliczania sygnałów pogorszenia ROA i OCF/assets. Jest to analiza konstrukcji targetu, a nie próba wyboru definicji dającej najlepsze wyniki modeli.

Wykorzystano wyłącznie wspólną próbę rozwojową, dla której dostępne są wszystkie pięć sygnałów:

- train: lata `2011–2020`, `15 255` obserwacji;
- validation: lata `2021–2022`, `4 702` obserwacje;
- łącznie: `19 957` obserwacji.

Test `2023–2024` nie został wykorzystany w obliczeniach tej analizy, nie jest raportowany i nie uczestniczy w ocenie definicji targetu.

## 2. Oceniane definicje

Bazowy target:

```text
deterioration_score_1y = D1_ROA + D2_OCF_assets
                       + D3_current_ratio
                       + D4_liabilities_assets
                       + D5_revenues

target_candidate_v2 = 1, gdy deterioration_score_1y >= 3
```

Wariant agregujący blok wyników operacyjnych:

```text
operating_performance_deterioration = max(D1_ROA, D2_OCF_assets)

alternative_score = operating_performance_deterioration
                  + D3_current_ratio
                  + D4_liabilities_assets
                  + D5_revenues

alternative_target = 1, gdy alternative_score >= 3
```

Wykonano również pięć analiz leave-one-component-out (LOO). W każdej usunięto jeden sygnał z bazowego score, pozostawiając próg `>= 3`. Nie zmieniano progów samych sygnałów ani nie dostrajano minimalnego score.

## 3. Wyniki główne: train + validation

| Wariant | Pozytywne | Udział pozytywnych | Utracone pozytywne v2 | Utracona część klasy v2 | Agreement | Jaccard pozytywnych |
|---|---:|---:|---:|---:|---:|---:|
| **bazowy v2** | `3 209` | **16,08%** | `0` | 0,00% | 100,00% | 1,000 |
| **agregacja ROA–OCF** | `2 065` | **10,35%** | `1 144` | **35,65%** | 94,27% | 0,644 |
| bez D1 ROA | `1 599` | 8,01% | `1 610` | **50,17%** | 91,93% | 0,498 |
| bez D2 OCF/assets | `1 832` | 9,18% | `1 377` | **42,91%** | 93,10% | 0,571 |
| bez D3 current ratio | `2 220` | 11,12% | `989` | 30,82% | 95,04% | 0,692 |
| bez D4 liabilities/assets | `2 403` | 12,04% | `806` | 25,12% | 95,96% | 0,749 |
| bez D5 revenues | `2 279` | 11,42% | `930` | 28,98% | 95,34% | 0,710 |

Wszystkie warianty są podzbiorami klasy pozytywnej bazowego v2. Nie występuje ani jeden przypadek zmiany `0 -> 1`; zmieniają się wyłącznie etykiety `1 -> 0`.

### 3.1. Osobno train i validation

| Wariant | Train: pozytywne | Train: udział | Train: agreement | Train: Jaccard | Validation: pozytywne | Validation: udział | Validation: agreement | Validation: Jaccard |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| bazowy v2 | `2 199` | 14,41% | 100,00% | 1,000 | `1 010` | 21,48% | 100,00% | 1,000 |
| agregacja ROA–OCF | `1 428` | 9,36% | 94,95% | 0,649 | `637` | 13,55% | 92,07% | 0,631 |
| bez D1 ROA | `1 091` | 7,15% | 92,74% | 0,496 | `508` | 10,80% | 89,32% | 0,503 |
| bez D2 OCF/assets | `1 244` | 8,15% | 93,74% | 0,566 | `588` | 12,51% | 91,03% | 0,582 |
| bez D3 current ratio | `1 516` | 9,94% | 95,52% | 0,689 | `704` | 14,97% | 93,49% | 0,697 |
| bez D4 liabilities/assets | `1 602` | 10,50% | 96,09% | 0,729 | `801` | 17,04% | 95,56% | 0,793 |
| bez D5 revenues | `1 534` | 10,06% | 95,64% | 0,698 | `745` | 15,84% | 94,36% | 0,738 |

Wynik jakościowy jest taki sam w obu częściach próby: usunięcie D1 ma największy wpływ, usunięcie D2 drugi największy, a agregacja wspólnego bloku usuwa około jednej trzeciej bazowych pozytywów. Efekt agregacji jest nieco silniejszy w validation niż w train.

## 4. Rozkład czasowy

W tabeli podano udział klasy pozytywnej w danym roku. Skróty `–D1` do `–D5` oznaczają wariant LOO bez danego sygnału.

| Rok | N | v2 | Agregacja | –D1 | –D2 | –D3 | –D4 | –D5 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2011 | `1 023` | 13,00% | 6,94% | 5,28% | 6,16% | 9,29% | 9,38% | 8,50% |
| 2012 | `1 226` | 11,01% | 7,42% | 5,06% | 6,36% | 6,28% | 7,75% | 7,34% |
| 2013 | `1 241` | 12,01% | 8,06% | 6,29% | 6,77% | 8,46% | 8,62% | 8,62% |
| 2014 | `1 329` | 15,80% | 9,26% | 6,77% | 7,98% | 11,74% | 11,21% | 9,93% |
| 2015 | `1 474` | 16,55% | 12,14% | 9,63% | 10,52% | 11,40% | 12,14% | 11,80% |
| 2016 | `1 554` | 12,42% | 8,56% | 6,76% | 7,34% | 7,85% | 8,43% | 9,33% |
| 2017 | `1 658` | 12,55% | 8,87% | 6,94% | 7,84% | 8,75% | 9,05% | 9,71% |
| 2018 | `1 797` | 17,47% | 11,46% | 8,96% | 10,07% | 12,13% | 12,41% | 13,58% |
| 2019 | `1 929` | 20,01% | 12,65% | 8,97% | 11,66% | 15,55% | 15,55% | 11,46% |
| 2020 | `2 024` | 11,22% | 6,62% | 5,48% | 5,34% | 6,42% | 8,50% | 8,55% |
| 2021 | `2 289` | 22,11% | 13,89% | 11,31% | 12,45% | 14,72% | 17,39% | 17,82% |
| 2022 | `2 413` | 20,89% | 13,22% | 10,32% | 12,56% | 15,21% | 16,70% | 13,97% |

Agregacja obniża poziom pozytywów w każdym roku, ale nie usuwa podstawowego wzorca czasowego: podwyższone udziały nadal występują m.in. w latach 2019 oraz 2021–2022. Brak jednego roku, który sam odpowiadałby za wynik diagnostyki.

## 5. Rozkład sektorowy

| Sektor | N | v2 | Agregacja | –D1 | –D2 | –D3 | –D4 | –D5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Extended Candidate | `5 610` | 14,83% | 9,70% | 7,20% | 8,47% | 10,09% | 11,14% | 9,77% |
| Industrials / Manufacturing | `8 760` | 17,81% | 11,30% | 8,92% | 10,16% | 12,51% | 13,69% | 12,81% |
| Retail | `1 448` | 11,12% | 7,39% | 5,73% | 6,35% | 7,73% | 7,32% | 8,77% |
| Technology | `4 139` | 15,85% | 10,24% | 8,00% | 9,06% | 10,78% | 11,43% | 11,65% |

We wszystkich definicjach najwyższy udział pozytywnych ma grupa Industrials / Manufacturing, a najniższy Retail. Wariant agregujący nie powoduje odwrócenia rankingu sektorów, więc wynik nie jest skutkiem jednego sektora.

## 6. Obserwacje zmieniające klasę

### 6.1. Wariant agregujący ROA–OCF

Wszystkie `1 144` zmiany można opisać dokładnie jednym warunkiem:

```text
base_score = 3
D1_ROA = 1
D2_OCF_assets = 1
dokładnie jeden z D3, D4, D5 = 1
```

Po zastąpieniu dwóch punktów z D1 i D2 jednym punktem obserwacje te otrzymują `alternative_score = 2` i zmieniają klasę z `1` na `0`.

| Wzorzec D1–D5 | Interpretacja | Zmienione obserwacje | Udział zmian wariantu |
|---|---|---:|---:|
| `11001` | ROA + OCF/assets + revenues | `577` | 50,44% |
| `11100` | ROA + OCF/assets + current ratio | `344` | 30,07% |
| `11010` | ROA + OCF/assets + liabilities/assets | `223` | 19,49% |

Oznacza to, że `35,65%` bazowej klasy pozytywnej uzyskuje trzeci wymagany punkt właśnie dzięki oddzielnemu naliczeniu D1 i D2, mimo że poza blokiem wyników operacyjnych występuje tylko jeden inny wymiar pogorszenia.

### 6.2. Leave-one-component-out

Dla każdego wariantu LOO zmieniają klasę dokładnie te obserwacje, które w bazowym v2:

```text
mają base_score = 3
i mają aktywny usuwany sygnał.
```

Liczba takich obserwacji wynosi odpowiednio: D1 `1 610`, D2 `1 377`, D3 `989`, D4 `806`, D5 `930`. Ponieważ jedna obserwacja może zmieniać klasę w kilku wariantach, nie należy sumować tych wartości jako liczby unikalnych spółka-lat.

Pełna lista zmian znajduje się w pliku [`target_candidate_v2_component_robustness_changed_observations.csv`](../data/reports/target_candidate_v2_component_robustness_changed_observations.csv). Zawiera identyfikator spółki, CIK, nazwę, ticker, rok, split, sektor, wzorzec D1–D5, oba score oraz kierunek zmiany. Plik ma `6 856` wierszy danych; obserwacja występuje osobno dla każdego wariantu, w którym zmienia klasę.

### 6.3. Rozmieszczenie zmian

| Rok | Agregacja | –D1 | –D2 | –D3 | –D4 | –D5 |
|---:|---:|---:|---:|---:|---:|---:|
| 2011 | `62` | `79` | `70` | `38` | `37` | `46` |
| 2012 | `44` | `73` | `57` | `58` | `40` | `45` |
| 2013 | `49` | `71` | `65` | `44` | `42` | `42` |
| 2014 | `87` | `120` | `104` | `54` | `61` | `78` |
| 2015 | `65` | `102` | `89` | `76` | `65` | `70` |
| 2016 | `60` | `88` | `79` | `71` | `62` | `48` |
| 2017 | `61` | `93` | `78` | `63` | `58` | `47` |
| 2018 | `108` | `153` | `133` | `96` | `91` | `70` |
| 2019 | `142` | `213` | `161` | `86` | `86` | `165` |
| 2020 | `93` | `116` | `119` | `97` | `55` | `54` |
| 2021 | `188` | `247` | `221` | `169` | `108` | `98` |
| 2022 | `185` | `255` | `201` | `137` | `101` | `167` |

| Sektor | Agregacja | –D1 | –D2 | –D3 | –D4 | –D5 |
|---|---:|---:|---:|---:|---:|---:|
| Extended Candidate | `288` | `428` | `357` | `266` | `207` | `284` |
| Industrials / Manufacturing | `570` | `779` | `670` | `464` | `361` | `438` |
| Retail | `54` | `78` | `69` | `49` | `55` | `34` |
| Technology | `232` | `325` | `281` | `210` | `183` | `174` |

Większe liczby bezwzględne w późniejszych latach oraz w Industrials / Manufacturing wynikają częściowo z większej liczebności tych grup. Tabele udziałów w sekcjach 4–5 pokazują, że wrażliwość nie ogranicza się do pojedynczego roku ani sektora.

## 7. Ocena odporności i decyzja metodologiczna

1. **Zależność od wspólnej aktywacji ROA i OCF/assets jest materialna.** Po potraktowaniu ich jako jednego wymiaru liczba pozytywnych spada z `3 209` do `2 065`, a `35,65%` bazowej klasy pozytywnej zmienia etykietę. Jaccard `0,644` oznacza umiarkowaną, a nie wysoką zgodność zbiorów pozytywnych.
2. **Target nie załamuje się całkowicie po agregacji.** `2 065` obserwacji, czyli `64,35%` pozytywów v2, zachowuje klasę pozytywną. Pozostają przypadki obejmujące co najmniej dwa wymiary poza blokiem ROA–OCF lub silniejsze, czteroskładnikowe i pięcioskładnikowe pogorszenie.
3. **ROA jest najbardziej wpływowym pojedynczym komponentem, a OCF/assets drugim.** Usunięcie D1 eliminuje `50,17%`, a D2 `42,91%` bazowych pozytywów. Dla pozostałych sygnałów analogiczny zakres wynosi `25,12–30,82%`.
4. **Efekt jest przekrojowy.** Ten sam porządek wpływu widać w train i validation, a rozkłady roczne i sektorowe nie wskazują, aby rezultat był napędzany wyłącznie przez jedną grupę.
5. **LOO jest celowo surową diagnostyką.** Po usunięciu składnika nadal wymagane są trzy sygnały, ale już spośród czterech. Spadku częstości klasy pozytywnej nie należy zatem interpretować jako samodzielnego dowodu, że usunięty sygnał jest błędny.

### Rekomendacja

`target_candidate_v2` wykazuje **istotną, ale nie całkowitą zależność** od oddzielnego naliczania ROA i OCF/assets. Wynik uzasadnia pozostawienie wariantu agregującego jako obowiązkowego targetu odpornościowego w dalszej części pracy.

Na tym etapie nie ma podstaw, aby automatycznie zastąpić v2 wariantem alternatywnym: ROA i OCF/assets opisują powiązane, lecz ekonomicznie różne aspekty rentowności i generowania gotówki, a wariant alternatywny stawia też bardziej restrykcyjny warunek `3 z 4` wymiarów. Ostateczne uzasadnienie definicji powinno opierać się na interpretacji ekonomicznej i stabilności opisowej w train/validation, nie na wyniku modeli i nie na teście 2023–2024.

Praktyczne rozwiązanie do pracy magisterskiej:

- zachować `target_candidate_v2` jako target główny na obecnym etapie;
- z góry zadeklarować `alternative_target` jako test odporności na potencjalne podwójne liczenie bloku ROA–OCF/assets;
- raportować wyniki modeli dla targetu głównego oraz wariantu odpornościowego bez wybierania między nimi na podstawie testu.

Przed użyciem wartości liczbowych z tego audytu jako wyników finalnych należy odtworzyć identyczne porównania na zamrożonym PIT-B, wyłącznie dla train i validation.

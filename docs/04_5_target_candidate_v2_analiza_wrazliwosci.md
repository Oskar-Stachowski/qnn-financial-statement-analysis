# Predefiniowana analiza wrażliwości `target_candidate_v2`

Data analizy: 2026-08-17.

> **Status metodologiczny (2026-08-18): analiza historyczna, pre-PIT.**
> Analiza OAT dokumentuje decyzję podjętą przed wdrożeniem target vintage B i
> korzysta ze wspólnej próby 19 957 obserwacji wcześniejszej ekstrakcji.
> Nie jest aktualnym oszacowaniem stabilności etykiet na finalnej populacji
> PIT-B. Przed raportowaniem robustness w pracy należy odtworzyć te same,
> predefiniowane warianty na zamrożonym PIT-B, nadal bez użycia lat 2023–2024.
> Lata testowe nie uczestniczyły w tej analizie, ale były wcześniej pokazane w
> opisowych dokumentach pre-PIT, dlatego określenie „zamrożony test” poniżej
> oznacza wyłączenie z tej analizy, a nie pełny brak wcześniejszej ekspozycji.

## 1. Cel i zakres

Analiza ocenia stabilność definicji [`target_candidate_v2`](./04_3_target_candidate_v2_definicja.md) metodą OAT (`one-at-a-time`). W każdym wariancie zmieniono dokładnie jeden element definicji, a pozostałe parametry zachowano na poziomie bazowym.

Nie wykonano grid searchu ani przeszukiwania kombinacji parametrów.

Do analizy wykorzystano wyłącznie:

- train: lata `2011–2020`, `15 255` obserwacji;
- validation: lata `2021–2022`, `4 702` obserwacje.

Łączna wspólna próba rozwojowa obejmuje `19 957` obserwacji. Test `2023–2024` nie został wykorzystany ani do obliczenia poniższych porównań, ani do wyboru parametrów.

## 2. Wersja bazowa i warianty

Wersja bazowa:

```text
ROA drop                    = 3 p.p.
OCF/assets drop             = 3 p.p.
current ratio drop          = 20%
liabilities/assets increase = 10 p.p.
revenues drop               = 10%
minimal score               = 3
```

Predefiniowane zmiany OAT:

| Rodzina | Wartość łagodniejsza | Wartość bazowa | Wartość surowsza |
|---|---:|---:|---:|
| ROA | 2 p.p. | 3 p.p. | 4 p.p. |
| OCF/assets | 2 p.p. | 3 p.p. | 4 p.p. |
| current ratio | 15% | 20% | 25% |
| liabilities/assets | 7,5 p.p. | 10 p.p. | 12,5 p.p. |
| revenues | 7,5% | 10% | 15% |
| minimalny score | 2 | 3 | 4 |

Łącznie oceniono `13` definicji: wersję bazową i `12` wariantów OAT.

## 3. Miary stabilności

Dla każdego wariantu policzono:

- udział klasy pozytywnej;
- agreement: udział wszystkich etykiet identycznych z bazowym `v2`;
- Jaccard klasy pozytywnej: iloraz przecięcia i sumy zbiorów pozytywnych etykiet;
- liczbę etykiet zmienionych względem wersji bazowej.

Ponieważ zmiana jednego progu jedynie łagodzi albo zaostrza warunek, wszystkie warianty są zagnieżdżone względem bazowego targetu: łagodniejsze są nadzbiorami, a surowsze podzbiorami klasy pozytywnej `v2`.

## 4. Wyniki główne na wspólnej próbie train + validation

| Wariant | Zmieniany parametr | Pozytywne | Udział pozytywnych | Train | Validation | Agreement | Jaccard pozytywnych | Zmienione etykiety |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **bazowy v2** | wartości bazowe | `3 209` | **16,08%** | 14,41% | 21,48% | 100,00% | 1,000 | `0` |
| ROA 2 p.p. | ROA | `3 347` | 16,77% | 15,17% | 21,97% | 99,31% | 0,959 | `138` |
| ROA 4 p.p. | ROA | `3 088` | 15,47% | 13,78% | 20,97% | 99,39% | 0,962 | `121` |
| OCF/assets 2 p.p. | OCF/assets | `3 358` | 16,83% | 15,18% | 22,18% | 99,25% | 0,956 | `149` |
| OCF/assets 4 p.p. | OCF/assets | `3 082` | 15,44% | 13,82% | 20,69% | 99,36% | 0,960 | `127` |
| current ratio 15% | current ratio | `3 387` | 16,97% | 15,28% | 22,46% | 99,11% | 0,947 | `178` |
| current ratio 25% | current ratio | `3 068` | 15,37% | 13,77% | 20,59% | 99,29% | 0,956 | `141` |
| liabilities/assets 7,5 p.p. | liabilities/assets | `3 383` | 16,95% | 15,29% | 22,35% | 99,13% | 0,949 | `174` |
| liabilities/assets 12,5 p.p. | liabilities/assets | `3 059` | 15,33% | 13,67% | 20,71% | 99,25% | 0,953 | `150` |
| revenues 7,5% | revenues | `3 298` | 16,53% | 14,87% | 21,91% | 99,55% | 0,973 | `89` |
| revenues 15% | revenues | `3 042` | 15,24% | 13,67% | 20,33% | 99,16% | 0,948 | `167` |
| minimalny score ≥ 2 | agregacja | `6 308` | **31,61%** | 29,52% | 38,37% | 84,47% | 0,509 | `3 099` |
| minimalny score ≥ 4 | agregacja | `1 305` | **6,54%** | 5,66% | 9,40% | 90,46% | 0,407 | `1 904` |

Zmiany progów pięciu sygnałów przesuwają udział klasy pozytywnej jedynie do przedziału `15,24–16,97%`. Agreement pozostaje powyżej `99,1%`, a Jaccard powyżej `0,947`.

Zmiana minimalnego score ma znacznie większy wpływ: udział klasy pozytywnej zmienia się do `31,61%` albo `6,54%`, a Jaccard spada do około `0,51` lub `0,41`.

## 5. Stabilność osobno w train i validation

| Wariant | Agreement train | Jaccard train | Agreement validation | Jaccard validation |
|---|---:|---:|---:|---:|
| bazowy v2 | 100,00% | 1,000 | 100,00% | 1,000 |
| ROA 2 p.p. | 99,25% | 0,950 | 99,51% | 0,978 |
| ROA 4 p.p. | 99,36% | 0,956 | 99,49% | 0,976 |
| OCF/assets 2 p.p. | 99,24% | 0,950 | 99,30% | 0,968 |
| OCF/assets 4 p.p. | 99,41% | 0,959 | 99,21% | 0,963 |
| current ratio 15% | 99,13% | 0,943 | 99,02% | 0,956 |
| current ratio 25% | 99,35% | 0,955 | 99,11% | 0,958 |
| liabilities/assets 7,5 p.p. | 99,13% | 0,943 | 99,13% | 0,961 |
| liabilities/assets 12,5 p.p. | 99,25% | 0,948 | 99,23% | 0,964 |
| revenues 7,5% | 99,55% | 0,970 | 99,57% | 0,981 |
| revenues 15% | 99,26% | 0,949 | 98,85% | 0,947 |
| minimalny score ≥ 2 | 84,89% | 0,488 | 83,11% | 0,560 |
| minimalny score ≥ 4 | 91,24% | 0,393 | 87,92% | 0,438 |

Stabilność progów składowych jest podobna w train i validation. Wyższy udział klasy pozytywnej w validation występuje we wszystkich wariantach i nie znika po zmianie pojedynczego progu.

## 6. Rozkład według lat

Wartości w tabelach oznaczają udział klasy pozytywnej w danym roku. Rok jest feature year `t`, a target opisuje zmianę `t -> t+1`.

### 6.1. Próg ROA

| Rok | N | 2 p.p. | Bazowe 3 p.p. | 4 p.p. |
|---:|---:|---:|---:|---:|
| 2011 | 1 023 | 13,78% | 13,00% | 12,41% |
| 2012 | 1 226 | 11,66% | 11,01% | 10,60% |
| 2013 | 1 241 | 13,13% | 12,01% | 11,52% |
| 2014 | 1 329 | 16,63% | 15,80% | 14,90% |
| 2015 | 1 474 | 17,37% | 16,55% | 16,01% |
| 2016 | 1 554 | 13,51% | 12,42% | 11,84% |
| 2017 | 1 658 | 13,57% | 12,55% | 12,42% |
| 2018 | 1 797 | 17,92% | 17,47% | 16,53% |
| 2019 | 1 929 | 20,68% | 20,01% | 18,92% |
| 2020 | 2 024 | 11,56% | 11,22% | 10,67% |
| 2021 | 2 289 | 22,63% | 22,11% | 21,58% |
| 2022 | 2 413 | 21,34% | 20,89% | 20,39% |

### 6.2. Próg OCF/assets

| Rok | N | 2 p.p. | Bazowe 3 p.p. | 4 p.p. |
|---:|---:|---:|---:|---:|
| 2011 | 1 023 | 13,69% | 13,00% | 12,41% |
| 2012 | 1 226 | 11,66% | 11,01% | 10,36% |
| 2013 | 1 241 | 13,05% | 12,01% | 11,52% |
| 2014 | 1 329 | 16,70% | 15,80% | 14,75% |
| 2015 | 1 474 | 17,30% | 16,55% | 15,88% |
| 2016 | 1 554 | 13,06% | 12,42% | 12,16% |
| 2017 | 1 658 | 12,97% | 12,55% | 12,18% |
| 2018 | 1 797 | 18,03% | 17,47% | 16,92% |
| 2019 | 1 929 | 21,46% | 20,01% | 19,03% |
| 2020 | 2 024 | 11,71% | 11,22% | 10,87% |
| 2021 | 2 289 | 22,63% | 22,11% | 21,63% |
| 2022 | 2 413 | 21,76% | 20,89% | 19,81% |

### 6.3. Próg current ratio

| Rok | N | 15% | Bazowe 20% | 25% |
|---:|---:|---:|---:|---:|
| 2011 | 1 023 | 13,69% | 13,00% | 12,51% |
| 2012 | 1 226 | 11,91% | 11,01% | 10,11% |
| 2013 | 1 241 | 12,73% | 12,01% | 11,36% |
| 2014 | 1 329 | 16,78% | 15,80% | 15,27% |
| 2015 | 1 474 | 17,44% | 16,55% | 16,08% |
| 2016 | 1 554 | 13,26% | 12,42% | 11,78% |
| 2017 | 1 658 | 13,21% | 12,55% | 11,58% |
| 2018 | 1 797 | 18,42% | 17,47% | 16,69% |
| 2019 | 1 929 | 20,84% | 20,01% | 19,34% |
| 2020 | 2 024 | 12,30% | 11,22% | 10,82% |
| 2021 | 2 289 | 23,24% | 22,11% | 21,10% |
| 2022 | 2 413 | 21,72% | 20,89% | 20,10% |

### 6.4. Próg liabilities/assets

| Rok | N | 7,5 p.p. | Bazowe 10 p.p. | 12,5 p.p. |
|---:|---:|---:|---:|---:|
| 2011 | 1 023 | 13,20% | 13,00% | 12,32% |
| 2012 | 1 226 | 11,42% | 11,01% | 10,44% |
| 2013 | 1 241 | 12,97% | 12,01% | 11,28% |
| 2014 | 1 329 | 16,40% | 15,80% | 14,82% |
| 2015 | 1 474 | 17,10% | 16,55% | 15,94% |
| 2016 | 1 554 | 13,58% | 12,42% | 11,65% |
| 2017 | 1 658 | 13,39% | 12,55% | 11,88% |
| 2018 | 1 797 | 18,64% | 17,47% | 16,14% |
| 2019 | 1 929 | 21,46% | 20,01% | 19,44% |
| 2020 | 2 024 | 12,06% | 11,22% | 10,67% |
| 2021 | 2 289 | 23,02% | 22,11% | 21,14% |
| 2022 | 2 413 | 21,72% | 20,89% | 20,31% |

### 6.5. Próg revenues

| Rok | N | 7,5% | Bazowe 10% | 15% |
|---:|---:|---:|---:|---:|
| 2011 | 1 023 | 13,39% | 13,00% | 12,02% |
| 2012 | 1 226 | 11,66% | 11,01% | 10,03% |
| 2013 | 1 241 | 12,25% | 12,01% | 11,36% |
| 2014 | 1 329 | 16,33% | 15,80% | 14,37% |
| 2015 | 1 474 | 17,10% | 16,55% | 15,88% |
| 2016 | 1 554 | 12,74% | 12,42% | 11,90% |
| 2017 | 1 658 | 12,73% | 12,55% | 12,12% |
| 2018 | 1 797 | 18,25% | 17,47% | 16,64% |
| 2019 | 1 929 | 20,74% | 20,01% | 19,03% |
| 2020 | 2 024 | 11,36% | 11,22% | 10,97% |
| 2021 | 2 289 | 22,46% | 22,11% | 21,19% |
| 2022 | 2 413 | 21,38% | 20,89% | 19,52% |

### 6.6. Minimalny score

| Rok | N | Score ≥ 2 | Bazowe score ≥ 3 | Score ≥ 4 |
|---:|---:|---:|---:|---:|
| 2011 | 1 023 | 24,24% | 13,00% | 4,20% |
| 2012 | 1 226 | 24,55% | 11,01% | 3,59% |
| 2013 | 1 241 | 26,27% | 12,01% | 4,92% |
| 2014 | 1 329 | 30,47% | 15,80% | 5,34% |
| 2015 | 1 474 | 31,61% | 16,55% | 7,46% |
| 2016 | 1 554 | 28,12% | 12,42% | 4,95% |
| 2017 | 1 658 | 26,90% | 12,55% | 5,73% |
| 2018 | 1 797 | 33,39% | 17,47% | 7,40% |
| 2019 | 1 929 | 39,66% | 20,01% | 7,72% |
| 2020 | 2 024 | 25,20% | 11,22% | 3,95% |
| 2021 | 2 289 | 40,06% | 22,11% | 9,83% |
| 2022 | 2 413 | 36,76% | 20,89% | 8,99% |

## 7. Rozkład według sektorów

Wartości oznaczają udział klasy pozytywnej. Liczebność sektorów we wspólnej próbie wynosi: Extended Candidate `5 610`, Industrials/Manufacturing `8 760`, Retail `1 448`, Technology `4 139`.

### 7.1. Próg ROA

| Sektor | 2 p.p. | Bazowe 3 p.p. | 4 p.p. |
|---|---:|---:|---:|
| Extended Candidate | 15,45% | 14,83% | 14,33% |
| Industrials/Manufacturing | 18,60% | 17,81% | 17,17% |
| Retail | 11,60% | 11,12% | 10,64% |
| Technology | 16,50% | 15,85% | 15,12% |

### 7.2. Próg OCF/assets

| Sektor | 2 p.p. | Bazowe 3 p.p. | 4 p.p. |
|---|---:|---:|---:|
| Extended Candidate | 15,65% | 14,83% | 14,14% |
| Industrials/Manufacturing | 18,63% | 17,81% | 17,21% |
| Retail | 11,88% | 11,12% | 10,91% |
| Technology | 16,33% | 15,85% | 15,05% |

### 7.3. Próg current ratio

| Sektor | 15% | Bazowe 20% | 25% |
|---|---:|---:|---:|
| Extended Candidate | 15,76% | 14,83% | 14,19% |
| Industrials/Manufacturing | 18,72% | 17,81% | 17,16% |
| Retail | 11,60% | 11,12% | 10,64% |
| Technology | 16,79% | 15,85% | 14,86% |

### 7.4. Próg liabilities/assets

| Sektor | 7,5 p.p. | Bazowe 10 p.p. | 12,5 p.p. |
|---|---:|---:|---:|
| Extended Candidate | 15,67% | 14,83% | 14,15% |
| Industrials/Manufacturing | 18,69% | 17,81% | 17,09% |
| Retail | 12,09% | 11,12% | 10,36% |
| Technology | 16,72% | 15,85% | 14,93% |

### 7.5. Próg revenues

| Sektor | 7,5% | Bazowe 10% | 15% |
|---|---:|---:|---:|
| Extended Candidate | 15,19% | 14,83% | 14,01% |
| Industrials/Manufacturing | 18,23% | 17,81% | 17,00% |
| Retail | 11,60% | 11,12% | 10,43% |
| Technology | 16,45% | 15,85% | 14,88% |

### 7.6. Minimalny score

| Sektor | Score ≥ 2 | Bazowe score ≥ 3 | Score ≥ 4 |
|---|---:|---:|---:|
| Extended Candidate | 29,86% | 14,83% | 5,67% |
| Industrials/Manufacturing | 34,38% | 17,81% | 7,49% |
| Retail | 23,96% | 11,12% | 4,56% |
| Technology | 30,78% | 15,85% | 6,40% |

Kolejność sektorów według udziału klasy pozytywnej pozostaje identyczna we wszystkich wariantach. Dla progów składowych maksymalna zmiana sektorowa względem bazy nie przekracza 1 p.p.; zmiana minimalnego score przesuwa udziały o ponad 10–16 p.p.

## 8. Ocena stabilności

### 8.1. Progi pięciu sygnałów

Definicja jest stabilna względem predefiniowanych zmian progów składowych:

- udział klasy pozytywnej pozostaje w wąskim przedziale `15,24–16,97%`;
- agreement wynosi co najmniej `99,11%`;
- Jaccard klasy pozytywnej wynosi co najmniej `0,947`;
- maksymalna zmiana udziału pozytywnych w pojedynczym roku nie przekracza około `1,46` p.p.;
- ranking sektorów nie zmienia się w żadnym wariancie.

Najmniejszą zmianę etykiet powoduje łagodniejszy próg revenues `7,5%`: `89` etykiet, agreement `99,55%`, Jaccard `0,973`.

Wśród progów składowych relatywnie największą zmianę powodują:

- current ratio `15%`: `178` etykiet, Jaccard `0,947`;
- liabilities/assets `7,5 p.p.`: `174` etykiety, Jaccard `0,949`;
- revenues `15%`: `167` etykiet, Jaccard `0,948`.

Nadal są to zmiany małe względem `19 957` obserwacji.

### 8.2. Minimalny score

Minimalny score jest zdecydowanie najbardziej wrażliwym elementem definicji:

- `score >= 2` niemal podwaja udział klasy pozytywnej z `16,08%` do `31,61%`;
- `score >= 4` zmniejsza udział klasy pozytywnej do `6,54%`;
- Jaccard z bazowym `v2` spada odpowiednio do `0,509` i `0,407`;
- zmienia się `3 099` albo `1 904` etykiet;
- maksymalna roczna różnica wobec bazy wynosi około `19,65` p.p. dla score 2 i `12,29` p.p. dla score 4.

Reguła `3 z 5` nie jest więc drobnym parametrem technicznym, lecz główną decyzją konstrukcyjną targetu.

## 9. Wniosek

Predefiniowana analiza OAT nie dostarcza podstaw do zmiany progów pięciu sygnałów wersji bazowej. Niewielkie przesunięcia progów zachowują niemal te same etykiety, wzorce roczne i ranking sektorów.

Najważniejszym źródłem wrażliwości jest minimalny score. Bazowe `score >= 3` zachowuje pozycję wariantu pośredniego między szeroką definicją `score >= 2` i bardzo restrykcyjną `score >= 4`. Te dwa warianty powinny pozostać jawnie raportowanymi analizami odporności, ale nie powinny zastępować bazowego targetu na podstawie późniejszych wyników modeli.

Test `2023–2024` nie został wykorzystany w tej analizie. Był jednak wcześniej podsumowany w diagnostykach pre-PIT, więc nie należy przedstawiać go jako całkowicie nieoglądanego na etapie definiowania targetu.

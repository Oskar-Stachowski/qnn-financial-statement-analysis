# Diagnostyka `target_candidate_v2` — audyt historyczny pre-PIT

Data analizy: 2026-08-17.

> **Status metodologiczny (2026-08-18): audyt historyczny, zastąpiony dla
> bieżącego targetu przez diagnostykę PIT-B.** Tabele zachowują wyniki
> wcześniejszej ekstrakcji z `sec_facts_wide.csv`: 25 020 dostępnych targetów
> i coverage 94,49%. Nie opisują populacji po walidacji accession, okresu,
> reporting entity i semantyki revenues. Finalny audyt resolvera PIT-B na
> train 2011–2020 i validation 2021–2022 raportuje 14 122 dostępne targety
> (52,46%), 4 221 `missing`, 8 453 `ambiguous` i 121 `hard-exclude`; znajduje
> się w `data/reports/target_candidate_v2_pit_b_final_revenue_resolver.md`.
> Poniższa wczesna diagnostyka raportowała także lata 2023–2024, więc nie jest
> częścią późniejszego, wolnego od testu freeze-gate PIT-B.

## 1. Zakres i metoda

Diagnostykę wykonano na ówczesnych danych przetworzonych:

- `data/interim/sec_facts_wide.csv`,
- `data/reports/sec_facts_sanity_warnings.csv`,
- `data/processed/research_universe.csv`.

Zastosowano definicję z [`target_candidate_v2`](./04_3_target_candidate_v2_definicja.md). Jednostką obserwacji jest para `spółka–rok (i, t)` z dokładnie kolejnym rokiem `t+1`.

Bazowa próba kwalifikująca się do targetowania wymaga:

1. istnienia pary `t`–`t+1`;
2. braku `hard_exclude` w obu latach;
3. dostępności podstawowych danych finansowych roku `t`;
4. nie więcej niż 20% braków w skonfigurowanych cechach bazowych.

Pełny `target_candidate_v2` wymaga dodatkowo kompletu danych dla wszystkich pięciu sygnałów oraz dodatniego bazowego `current_ratio_t`.

## 2. Liczebność, pokrycie i klasa pozytywna

| Miara | Wartość |
|---|---:|
| Wszystkie przetworzone obserwacje spółka–rok | `36 664` |
| Bazowe kwalifikujące się pary `t`–`t+1` | `26 479` |
| Obserwacje z kompletnym targetem | `25 020` |
| Obserwacje bez kompletnego targetu | `1 459` |
| Pokrycie targetu | `94,49%` |
| Klasa pozytywna (`target_candidate_v2 = 1`) | `4 066` |
| Udział klasy pozytywnej | `16,25%` |
| Klasa negatywna | `20 954` |
| Udział klasy negatywnej | `83,75%` |

Target jest umiarkowanie niezbalansowany. Liczebność klasy pozytywnej jest wystarczająca do eksperymentów, ale ewaluacja powinna obejmować przede wszystkim PR-AUC, recall, precision, F1 i balanced accuracy, a nie samo accuracy.

## 3. Rozkład `deterioration_score_1y`

| Score | Liczba obserwacji | Udział |
|---:|---:|---:|
| 0 | `10 351` | `41,37%` |
| 1 | `6 704` | `26,79%` |
| 2 | `3 899` | `15,58%` |
| 3 | `2 402` | `9,60%` |
| 4 | `1 238` | `4,95%` |
| 5 | `426` | `1,70%` |
| **Razem** | **`25 020`** | **`100,00%`** |

Klasa pozytywna obejmuje score `3–5`. Spośród pozytywnych etykiet `59,1%` ma wynik dokładnie `3`, dlatego obserwacje na granicy agregacji stanowią większość klasy pozytywnej.

## 4. Częstość pięciu sygnałów

| Kod | Sygnał | Liczba aktywacji | Udział w 25 020 obserwacjach | Udział we wszystkich aktywacjach |
|---|---|---:|---:|---:|
| D1 | spadek ROA o co najmniej 3 p.p. | `7 414` | `29,63%` | `25,75%` |
| D2 | spadek OCF/assets o co najmniej 3 p.p. | `7 452` | `29,78%` | `25,88%` |
| D3 | spadek current ratio o co najmniej 20% | `5 697` | `22,77%` | `19,79%` |
| D4 | wzrost liabilities/assets o co najmniej 10 p.p. | `3 896` | `15,57%` | `13,53%` |
| D5 | spadek revenues o co najmniej 10% | `4 331` | `17,31%` | `15,04%` |

Najczęstsze są D1 i D2. Ich częstość jest zbliżona i wynosi około 30%. Najrzadszy jest D4, ale nadal występuje w 15,6% obserwacji.

## 5. Korelacje między sygnałami

Poniższa macierz przedstawia korelacje Pearsona dla flag binarnych, równoważne współczynnikowi phi.

|  | D1 ROA | D2 OCF/assets | D3 current ratio | D4 liabilities/assets | D5 revenues |
|---|---:|---:|---:|---:|---:|
| **D1 ROA** | 1,000 | 0,340 | 0,209 | 0,292 | 0,289 |
| **D2 OCF/assets** | 0,340 | 1,000 | 0,149 | 0,191 | 0,202 |
| **D3 current ratio** | 0,209 | 0,149 | 1,000 | 0,370 | 0,079 |
| **D4 liabilities/assets** | 0,292 | 0,191 | 0,370 | 1,000 | 0,125 |
| **D5 revenues** | 0,289 | 0,202 | 0,079 | 0,125 | 1,000 |

Najwyższe korelacje występują między:

- D3 i D4: `0,370`,
- D1 i D2: `0,340`.

Wszystkie korelacje są dodatnie, ale żadna nie przekracza `0,40`. Nie ma więc sygnałów będących niemal mechanicznymi duplikatami. Widoczne są jednak dwa logiczne bloki: rentowność–gotówka oraz płynność–zadłużenie.

## 6. Rozkład targetu według roku

Rok oznacza feature year `t`; target opisuje zmianę z `t` do `t+1`.

| Rok `t` | Bazowe pary | Kompletny target | Pokrycie | Pozytywne | Udział pozytywnych |
|---:|---:|---:|---:|---:|---:|
| 2011 | `1 044` | `1 023` | `97,99%` | `133` | `13,00%` |
| 2012 | `1 289` | `1 226` | `95,11%` | `135` | `11,01%` |
| 2013 | `1 333` | `1 241` | `93,10%` | `149` | `12,01%` |
| 2014 | `1 428` | `1 329` | `93,07%` | `210` | `15,80%` |
| 2015 | `1 571` | `1 474` | `93,83%` | `244` | `16,55%` |
| 2016 | `1 646` | `1 554` | `94,41%` | `193` | `12,42%` |
| 2017 | `1 767` | `1 658` | `93,83%` | `208` | `12,55%` |
| 2018 | `1 909` | `1 797` | `94,13%` | `314` | `17,47%` |
| 2019 | `2 045` | `1 929` | `94,33%` | `386` | `20,01%` |
| 2020 | `2 146` | `2 024` | `94,32%` | `227` | `11,22%` |
| 2021 | `2 405` | `2 289` | `95,18%` | `506` | `22,11%` |
| 2022 | `2 548` | `2 413` | `94,70%` | `504` | `20,89%` |
| 2023 | `2 635` | `2 500` | `94,88%` | `483` | `19,32%` |
| 2024 | `2 713` | `2 563` | `94,47%` | `374` | `14,59%` |

Udział klasy pozytywnej zmienia się od `11,01%` do `22,11%`. Oznacza to wyraźny temporal drift, który jest częściowo zgodny z cyklicznym charakterem kondycji finansowej. Podział czasowy powinien zostać zachowany, a metryki raportowane osobno dla validation i test.

## 7. Rozkład według sektora badawczego

| Sektor | Obserwacje | Udział próby | Pozytywne | Udział pozytywnych |
|---|---:|---:|---:|---:|
| Industrials/Manufacturing | `10 922` | `43,65%` | `1 980` | `18,13%` |
| Extended Candidate | `7 030` | `28,10%` | `1 072` | `15,25%` |
| Technology | `5 273` | `21,08%` | `814` | `15,44%` |
| Retail | `1 795` | `7,17%` | `200` | `11,14%` |

Największą część próby stanowi sektor przemysłowo-produkcyjny. Różnica między najwyższym i najniższym udziałem klasy pozytywnej wynosi około 7 p.p.

## 8. Rozkład według głównej grupy SIC

| Główna grupa SIC | Obserwacje | Udział próby | Pozytywne | Udział pozytywnych |
|---|---:|---:|---:|---:|
| Manufacturing | `13 712` | `54,80%` | `2 428` | `17,71%` |
| Services | `5 650` | `22,58%` | `852` | `15,08%` |
| Retail Trade | `1 819` | `7,27%` | `205` | `11,27%` |
| Transportation, Communications, Utilities | `1 406` | `5,62%` | `158` | `11,24%` |
| Mining | `1 186` | `4,74%` | `305` | `25,72%` |
| Wholesale Trade | `901` | `3,60%` | `91` | `10,10%` |
| Construction | `346` | `1,38%` | `27` | `7,80%` |

Mining ma wyraźnie najwyższy udział klasy pozytywnej, natomiast Construction najniższy. Wskazuje to, że wspólne progi targetu działają w populacjach o różnej zmienności ekonomicznej.

### Najliczniejsze dokładne kody SIC

| SIC | Opis | Obserwacje | Pozytywne | Udział pozytywnych |
|---:|---|---:|---:|---:|
| 2834 | Pharmaceutical Preparations | `1 909` | `608` | `31,85%` |
| 7372 | Prepackaged Software | `1 233` | `188` | `15,25%` |
| 3841 | Surgical & Medical Instruments | `872` | `174` | `19,95%` |
| 3674 | Semiconductors & Related Devices | `728` | `128` | `17,58%` |
| 7389 | Business Services, NEC | `665` | `86` | `12,93%` |
| 2836 | Biological Products | `565` | `204` | `36,11%` |
| 1311 | Crude Petroleum & Natural Gas | `564` | `168` | `29,79%` |
| 5812 | Eating Places | `390` | `47` | `12,05%` |
| 7374 | Computer Processing & Data Preparation | `350` | `47` | `13,43%` |
| 3714 | Motor Vehicle Parts & Accessories | `321` | `31` | `9,66%` |
| 7373 | Computer Integrated Systems Design | `307` | `45` | `14,66%` |
| 7370 | Computer Programming/Data Processing | `290` | `49` | `16,90%` |

Dokładne kody SIC tworzą 336 kategorii, z których wiele jest małych. Porównania ich udziałów pozytywnych powinny uwzględniać liczebność; tabela pokazuje największe grupy zamiast niestabilnych wyników dla bardzo rzadkich kodów.

## 9. Diagnostyka dominacji sygnałów

### 9.1. Obecność sygnału w klasie pozytywnej

| Sygnał | Obecny w pozytywnych | Udział 4 066 pozytywnych | Przypadki rozstrzygające | Udział pozytywnych zależnych od sygnału |
|---|---:|---:|---:|---:|
| D1 ROA | `3 638` | `89,47%` | `2 031` | `49,95%` |
| D2 OCF/assets | `3 278` | `80,62%` | `1 742` | `42,84%` |
| D3 current ratio | `2 700` | `66,40%` | `1 228` | `30,20%` |
| D4 liabilities/assets | `2 437` | `59,94%` | `1 002` | `24,64%` |
| D5 revenues | `2 235` | `54,97%` | `1 203` | `29,59%` |

„Przypadek rozstrzygający” oznacza target pozytywny ze score równym `3`, który po usunięciu danego sygnału zmieniłby się na `0`.

### 9.2. Najczęstsze kombinacje w klasie pozytywnej

| Kombinacja sygnałów | Liczba | Udział klasy pozytywnej |
|---|---:|---:|
| ROA + OCF/assets + revenues | `742` | `18,25%` |
| ROA + OCF/assets + current ratio + liabilities/assets | `632` | `15,54%` |
| ROA + OCF/assets + current ratio | `432` | `10,62%` |
| wszystkie pięć sygnałów | `426` | `10,48%` |
| ROA + current ratio + liabilities/assets | `313` | `7,70%` |
| ROA + OCF/assets + liabilities/assets | `286` | `7,03%` |

### 9.3. Wniosek o dominacji

Nie występuje **pełna dominacja pojedynczego sygnału**:

- udziały we wszystkich aktywacjach mieszczą się między `13,53%` i `25,88%`;
- najwyższa korelacja między dowolnymi dwoma sygnałami wynosi tylko `0,370`;
- każdy z pięciu sygnałów występuje w istotnej części klasy pozytywnej.

Jednocześnie D1 (ROA) jest wyraźnie najbardziej wpływowym pojedynczym sygnałem dla binarnej etykiety:

- występuje w `89,47%` pozytywnych obserwacji;
- jest rozstrzygający dla `49,95%` klasy pozytywnej.

Jeszcze silniejsza jest dominacja wspólnego bloku **ROA–OCF/assets**:

- co najmniej jeden z tych sygnałów występuje w `3 977` z `4 066` pozytywnych obserwacji (`97,81%`);
- oba sygnały jednocześnie występują w `2 939` pozytywnych obserwacjach (`72,28%`);
- tylko `89` pozytywnych obserwacji nie zawiera ani D1, ani D2 i wymaga jednoczesnego wystąpienia D3, D4 oraz D5.

Wniosek jest zatem dwuczęściowy: target nie jest kontrolowany przez jeden niemal zduplikowany sygnał, ale jego klasa pozytywna jest w znacznym stopniu zbudowana wokół pogorszenia rentowności lub przepływów operacyjnych. Wynika to zarówno z częstszego występowania D1 i D2, jak i z reguły `3 z 5`.

Przed finalnym zatwierdzeniem targetu warto potraktować jako analizę wrażliwości wariant, w którym ROA i OCF/assets tworzą jeden wspólny wymiar lub w którym raportuje się wyniki osobno dla kombinacji z jednym i z dwoma sygnałami tego bloku. Nie należy wybierać wariantu na podstawie późniejszej jakości modeli.

## 10. Podsumowanie historycznej diagnostyki

1. W ekstrakcji pre-PIT target miał wysokie pokrycie (`94,49%`) i zapewniał `4 066` obserwacji pozytywnych; wartości te nie są bieżącymi statystykami PIT-B.
2. Klasa pozytywna stanowi `16,25%` próby i jest umiarkowanie niezbalansowana.
3. Żaden sygnał nie jest prawie idealnym duplikatem innego; korelacje są niskie lub umiarkowane.
4. Występuje temporal drift oraz wyraźne zróżnicowanie według sektora i SIC.
5. ROA jest najbardziej wpływowym pojedynczym sygnałem, a blok ROA–OCF/assets dominuje w strukturze klasy pozytywnej.
6. `target_candidate_v2` nadaje się do dalszego etapu jako jawnie zdefiniowany target kandydacki, ale analiza wrażliwości na agregację ROA i OCF/assets jest metodologicznie uzasadniona.

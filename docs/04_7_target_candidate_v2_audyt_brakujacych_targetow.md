# Audyt obserwacji z niedostępnym `target_candidate_v2` — historyczny pre-PIT

Data analizy: 2026-08-17.

> **Status metodologiczny (2026-08-18): audyt historyczny, zastąpiony dla
> bieżącej populacji przez audyt PIT-B.** Dokument celowo zachowuje analizę
> wskazanych wtedy 1 459 braków w ekstrakcji pre-PIT i nie powinien być
> interpretowany jako aktualny poziom missingness. Po konserwatywnej walidacji
> PIT-B na train 2011–2020 i validation 2021–2022 populacja obejmuje 14 122
> targety `available`, 4 221 `missing`, 8 453 `ambiguous` i 121
> `hard-exclude`; aktualne wyniki są zapisane w
> `data/reports/target_candidate_v2_pit_b_final_revenue_resolver.md`.
> Sekcja dotycząca 2024–2025 jest zapisem wcześniejszej eksploracji i nie
> należała do późniejszego freeze-gate PIT-B. Oznacza też, że lata 2023–2024
> nie są całkowicie nieoglądanym holdoutem dla diagnostyki targetu.

## 1. Cel i zakres

Audyt porównuje kwalifikujące się obserwacje spółka–rok z dostępnym i niedostępnym [`target_candidate_v2`](./04_3_target_candidate_v2_definicja.md). Zachowano populację z wcześniejszej [diagnostyki v2](./04_4_target_candidate_v2_diagnostyka.md), aby dokładnie odtworzyć wskazane `1 459` brakujących targetów.

| Status | Obserwacje | Udział |
|---|---:|---:|
| target dostępny | `25 020` | 94,49% |
| target niedostępny | `1 459` | 5,51% |
| razem kwalifikujące się pary | `26 479` | 100,00% |

Brakującym targetom nie przypisano klasy `0`. `target_candidate_v2` pozostaje dla nich wartością brakującą.

Jednostką analizy jest feature year `t`. Wymagany target opisuje zmianę z `t` do `t+1` i jest dostępny wyłącznie wtedy, gdy można policzyć komplet pięciu sygnałów D1–D5.

## 2. Ważna uwaga implementacyjna: wykluczenia t+1

Kontrola odtworzonej logiki wykazała, że `hard_exclude_flag_next` po scaleniu ma typ `object`. Zapis:

```python
~hard_exclude_flag_next.fillna(False)
```

nie wykonuje wtedy bezpiecznej negacji logicznej dla wszystkich wierszy. W konsekwencji wcześniejsza populacja `26 479` zawiera `90` obserwacji oznaczonych jako hard-exclude w t+1, mimo że opis metodologiczny zakładał ich usunięcie.

| Miara | Dotychczasowa populacja | Po jawnym rzutowaniu flagi na `bool` |
|---|---:|---:|
| kwalifikujące się pary | `26 479` | `26 389` |
| dostępny target | `25 020` | `24 946` |
| niedostępny target | `1 459` | `1 443` |
| pokrycie targetu | 94,49% | 94,53% |

Spośród `90` niepoprawnie pozostawionych obserwacji `74` mają policzalny target, a `16` należy do analizowanych `1 459` braków. Skala nie zmienia głównych wniosków o brakach, ale błąd należy poprawić przed zamrożeniem finalnego datasetu i następnie przeliczyć wszystkie statystyki targetu.

Dalsze tabele zachowują historyczną populację `26 479`, ponieważ przedmiotem zadania jest dokładnie zbiór `1 459` obserwacji. Analiza feature year 2024 podaje dodatkowo liczebności po ścisłym zastosowaniu wykluczenia.

## 3. Rozkład według roku

| Feature year | Kwalifikujące się | Target dostępny | Target brakujący | Udział brakujących |
|---:|---:|---:|---:|---:|
| 2011 | `1 044` | `1 023` | `21` | 2,01% |
| 2012 | `1 289` | `1 226` | `63` | 4,89% |
| 2013 | `1 333` | `1 241` | `92` | 6,90% |
| 2014 | `1 428` | `1 329` | `99` | 6,93% |
| 2015 | `1 571` | `1 474` | `97` | 6,17% |
| 2016 | `1 646` | `1 554` | `92` | 5,59% |
| 2017 | `1 767` | `1 658` | `109` | 6,17% |
| 2018 | `1 909` | `1 797` | `112` | 5,87% |
| 2019 | `2 045` | `1 929` | `116` | 5,67% |
| 2020 | `2 146` | `2 024` | `122` | 5,69% |
| 2021 | `2 405` | `2 289` | `116` | 4,82% |
| 2022 | `2 548` | `2 413` | `135` | 5,30% |
| 2023 | `2 635` | `2 500` | `135` | 5,12% |
| 2024 | `2 713` | `2 563` | `150` | 5,53% |

Braki występują we wszystkich latach. Najwyższy udział przypada na lata 2013–2014, a nie na najnowszy rok. Wartość dla 2024 (`5,53%`) jest praktycznie równa całej próbie (`5,51%`), więc wśród istniejących par t–t+1 nie widać wyjątkowego załamania kompletności dla 2025.

## 4. Sektor i SIC

### 4.1. Sektory badawcze

| Sektor | Kwalifikujące się | Target brakujący | Udział brakujących | Udział w całej próbie | Udział w 1 459 brakach |
|---|---:|---:|---:|---:|---:|
| Industrials / Manufacturing | `11 695` | `773` | 6,61% | 44,17% | 52,98% |
| Extended Candidate | `7 563` | `533` | 7,05% | 28,56% | 36,53% |
| Technology | `5 389` | `116` | 2,15% | 20,35% | 7,95% |
| Retail | `1 832` | `37` | 2,02% | 6,92% | 2,54% |

Industrials / Manufacturing oraz Extended Candidate tworzą `72,73%` populacji, ale aż `89,51%` brakujących targetów. Technology i Retail są wyraźnie nadreprezentowane w próbie complete-case.

### 4.2. Główne grupy SIC

| Główna grupa SIC | Kwalifikujące się | Target brakujący | Udział brakujących |
|---|---:|---:|---:|
| Manufacturing | `14 524` | `812` | 5,59% |
| Services | `5 942` | `292` | 4,91% |
| Retail Trade | `1 857` | `38` | 2,05% |
| Transportation, Communications, Utilities | `1 453` | `47` | 3,23% |
| Mining | `1 283` | `97` | 7,56% |
| Wholesale Trade | `934` | `33` | 3,53% |
| Construction | `486` | `140` | **28,81%** |

Construction jest wyraźnym odstającym przypadkiem: odpowiada za tylko `1,84%` kwalifikujących się obserwacji, ale za `9,60%` wszystkich braków.

### 4.3. Dokładne kody SIC

| SIC | Opis | Kwalifikujące się | Braki | Udział brakujących | Dominujący brak |
|---:|---|---:|---:|---:|---|
| 2834 | Pharmaceutical Preparations | `2 296` | `387` | 16,86% | D5 revenues (`369`) |
| 1531 | Operative Builders | `129` | `124` | **96,12%** | D3 current ratio (`122`) |
| 2836 | Biological Products | `659` | `94` | 14,26% | D5 revenues (`87`) |
| 7359 | Equipment Rental & Leasing, NEC | `71` | `47` | **66,20%** | D3 current ratio (`47`) |
| 7389 | Business Services, NEC | `710` | `45` | 6,34% | D3 current ratio (`35`) |
| 7372 | Prepackaged Software | `1 273` | `40` | 3,14% | D5 revenues (`24`) |
| 1040 | Gold and Silver Ores | `120` | `32` | 26,67% | D5 revenues (`32`) |
| 3841 | Surgical & Medical Instruments | `901` | `29` | 3,22% | D5 revenues (`27`) |

SIC 2834 sam odpowiada za `26,53%` wszystkich brakujących targetów. Wysokie wskaźniki braków mają ekonomicznie różne źródła: w farmacji, biotechnologii i części wydobycia dominuje brak użytecznej dynamiki przychodów, natomiast w budownictwie i leasingu brak current ratio. To wskazuje na komponent branżowej nieporównywalności, a nie jedynie przypadkowe błędy danych.

## 5. Wielkość spółki

Kwartyle wyznaczono osobno w każdym feature year, aby ograniczyć wpływ inflacji i zmiany składu populacji w czasie.

### 5.1. Kwartyle aktywów

| Kwartyl aktywów | Kwalifikujące się | Braki | Udział brakujących | Udział w 1 459 brakach |
|---|---:|---:|---:|---:|
| Q1 – najmniejsze | `6 615` | `712` | **10,76%** | 48,80% |
| Q2 | `6 620` | `246` | 3,72% | 16,86% |
| Q3 | `6 618` | `222` | 3,35% | 15,22% |
| Q4 – największe | `6 626` | `279` | 4,21% | 19,12% |

### 5.2. Kwartyle przychodów

| Kwartyl przychodów | Kwalifikujące się | Braki | Udział brakujących | Udział w 1 459 brakach |
|---|---:|---:|---:|---:|
| Q1 – najmniejsze | `6 615` | `918` | **13,88%** | 62,92% |
| Q2 | `6 620` | `143` | 2,16% | 9,80% |
| Q3 | `6 618` | `171` | 2,58% | 11,72% |
| Q4 – największe | `6 626` | `227` | 3,43% | 15,56% |

Mediana aktywów wynosi `837,2 mln USD` w grupie z targetem i `103,5 mln USD` w grupie bez targetu. Mediana przychodów wynosi odpowiednio `652,4 mln USD` i tylko `1,33 mln USD`; co najmniej 25% grupy bez targetu ma przychody równe zero. Standaryzowana różnica dla logarytmu aktywów wynosi `-0,542`, a dla dodatnich przychodów `-0,584`, co jest dużą różnicą profilu.

## 6. Wskaźniki finansowe dostępne w t

Tabela pokazuje pokrycie i mediany w obu grupach. SMD jest liczony po winsoryzacji 1–99%; znak oznacza kierunek „brak targetu minus target dostępny”. Wartości bezwzględne około `0,5` lub większe oznaczają dużą różnicę profilu.

| Wskaźnik w t | Pokrycie: target dostępny | Mediana: target dostępny | Pokrycie: target brakujący | Mediana: target brakujący | SMD |
|---|---:|---:|---:|---:|---:|
| current ratio | 100,00% | 1,977 | 68,06% | 3,377 | 0,611 |
| liabilities/assets | 100,00% | 0,531 | 100,00% | 0,457 | 0,104 |
| liabilities/equity | 91,17% | 1,024 | 90,20% | 0,726 | 0,009 |
| ROA | 100,00% | 2,72% | 100,00% | **-19,31%** | **-0,507** |
| ROE | 91,17% | 7,08% | 90,20% | **-23,86%** | -0,405 |
| profit margin | 100,00% | 2,73% | 70,73% | -3,66% | -0,433 |
| asset turnover | 100,00% | 0,749 | 100,00% | 0,137 | **-0,549** |
| sales growth | 88,94% | 6,31% | 62,51% | 2,87% | 0,053 |
| working capital/assets | 100,00% | 0,208 | 68,61% | 0,444 | -0,081 |
| cash/assets | 99,48% | 0,109 | 99,79% | 0,168 | **0,522** |
| OCF/assets | 100,00% | 6,99% | 97,26% | **-13,29%** | **-0,655** |

Obserwacje bez targetu są średnio mniejsze, mniej rentowne, mają znacznie słabsze przepływy operacyjne i niższą rotację aktywów. Jednocześnie część grupy — szczególnie spółki przedprzychodowe — ma relatywnie dużo gotówki i wysoki current ratio, gdy jest on raportowany. Nie jest to więc jednorodna grupa „złych spółek”, lecz mieszanina spółek w trudniejszej kondycji oraz specyficznych modeli biznesowych i prezentacji sprawozdań.

## 7. Liczba braków i bezpośrednie przyczyny braku targetu

### 7.1. Braki w dziesięciu cechach bazowych w t

| Liczba brakujących cech bazowych | Kwalifikujące się | Target brakujący | Udział brakujących targetów w grupie | Udział w 1 459 brakach |
|---:|---:|---:|---:|---:|
| 0 | `20 235` | `306` | 1,51% | 20,97% |
| 1 | `2 985` | `119` | 3,99% | 8,16% |
| 2 | `3 259` | `1 034` | **31,73%** | **70,87%** |

Próg kwalifikacji dopuszcza maksymalnie dwa braki w dziesięciu cechach bazowych. Obserwacje znajdujące się dokładnie na tej granicy odpowiadają za ponad 70% brakujących targetów.

### 7.2. Liczba niedostępnych sygnałów targetu

| Liczba niedostępnych sygnałów D1–D5 | Obserwacje | Udział 1 459 braków |
|---:|---:|---:|
| 1 | `1 380` | **94,59%** |
| 2 | `34` | 2,33% |
| 3 | `21` | 1,44% |
| 4 | `14` | 0,96% |
| 5 | `10` | 0,69% |

Większość przypadków jest prawie kompletna: brakuje dokładnie jednego z pięciu sygnałów. Nie uzasadnia to jednak przypisania klasy `0`, ponieważ brakujący sygnał mógłby zmienić zarówno score, jak i finalną etykietę.

### 7.3. Brak według sygnału

Powody mogą współwystępować, dlatego wartości nie sumują się do `1 459`.

| Niedostępny sygnał | Obserwacje | Udział 1 459 braków |
|---|---:|---:|
| D5 revenues | `858` | **58,81%** |
| D3 current ratio | `548` | **37,56%** |
| D2 OCF/assets | `101` | 6,92% |
| D1 ROA | `81` | 5,55% |
| D4 liabilities/assets | `29` | 1,99% |

Najczęstsze rozłączne kombinacje to:

- tylko D5: `793` obserwacje (`54,35%` wszystkich braków);
- tylko D3: `500` (`34,27%`);
- tylko D2: `49` (`3,36%`);
- tylko D1: `36` (`2,47%`).

### 7.4. Pierwotne dane powodujące brak

| Niedostępny lub nieważny input | t | t+1 |
|---|---:|---:|
| assets | `0` | `25` |
| liabilities | `0` | `14` |
| revenues powyżej minimalnego mianownika | `427` | `766` |
| net income | `0` | `61` |
| operating cash flow | `40` | `67` |
| current assets | `407` | `423` |
| current liabilities powyżej minimalnego mianownika | `458` | `477` |

Dominują dwa mechanizmy:

1. zerowe, bardzo małe lub niedostępne przychody, przez które nie można policzyć dynamiki revenues;
2. brak klasyfikowanych pozycji current assets/current liabilities lub nieważny mianownik current ratio.

Braki w ROA i liabilities/assets prawie zawsze wynikają z danych t+1, ponieważ podstawowe pozycje roku t są już wymagane przez filtr kwalifikacyjny.

Pełna lista `1 459` przypadków wraz z identyfikatorami, wartościami t i t+1 oraz powodami znajduje się w pliku [`target_candidate_v2_missing_target_observations.csv`](../data/reports/target_candidate_v2_missing_target_observations.csv).

## 8. Szczegółowa analiza feature year 2024

### 8.1. Istniejące pary 2024–2025

W dotychczasowej populacji występuje `2 713` par 2024–2025. Target jest dostępny dla `2 563`, a niedostępny dla `150`, co daje pokrycie `94,47%`.

| Input w 2025 | Dostępność dla 2 713 par | Braki |
|---|---:|---:|
| assets | 99,96% | `1` |
| liabilities | 100,00% | `0` |
| revenues powyżej minimalnego mianownika | 96,39% | `98` |
| net income | 99,89% | `3` |
| operating cash flow | 99,89% | `3` |
| current assets | 98,67% | `36` |
| current liabilities powyżej minimalnego mianownika | 98,56% | `39` |

W porównaniu z dostępnością danych 2024 dla feature year 2023 największa różnica dotyczy revenues i wynosi tylko `-0,54 p.p.`. Dla pozostałych pozycji zmiany mieszczą się między `-0,07` i `+0,04 p.p.`. Nie ma więc dowodu na gwałtowne pogorszenie kompletności istniejących rekordów 2025.

Wśród `150` brakujących targetów dla feature year 2024:

- D5 revenues jest niedostępny w `106` przypadkach (`70,67%`);
- D3 current ratio w `45` (`30,00%`);
- D1 i D2 po `4` przypadki;
- D4 w `1` przypadku.

Na poziomie pierwotnych danych `98` przypadków ma nieważne lub brakujące revenues w 2025, `48` w 2024, `36/39` ma brak current assets/current liabilities w 2025, a `35/38` w 2024. Powody współwystępują.

### 8.2. Brak całego rekordu t+1 i prawe cenzurowanie

Przed wymaganiem pary t–t+1 istnieje `2 801` obserwacji roku 2024 spełniających kryteria jakości danych w t:

| Status 2024→2025 | Obserwacje | Udział 2 801 |
|---|---:|---:|
| brak całego rekordu 2025 | `88` | 3,14% |
| rekord 2025 hard-excluded | `7` | 0,25% |
| ścisłe kwalifikujące się pary | `2 706` | 96,61% |
| kompletny target po ścisłym wykluczeniu | `2 557` | **91,29%** |

Po poprawnym zastosowaniu hard-exclude liczba brakujących targetów w ścisłej populacji 2024 wynosi `149`, a pokrycie `94,49%`. Efektywne pokrycie względem wszystkich jakościowo poprawnych obserwacji 2024 jest jednak niższe (`91,29%`), ponieważ dodatkowo dochodzi brak całego rekordu 2025.

Rok 2024 ma najwyższą liczbę bezwzględną obserwacji bez t+1 (`88`) i udział `3,14%`, wobec `1,97%` dla wszystkich lat. Część może wynikać z prawego cenzurowania najnowszych raportów, ale na podstawie szerokiego pliku zagregowanego nie można rozdzielić braku złożenia 10-K, opóźnienia pozyskania danych i braku użytecznych faktów XBRL.

## 9. Ocena ryzyk metodologicznych

### 9.1. Complete-case selection bias — ryzyko wysokie

Brak targetu nie przypomina mechanizmu MCAR:

- najmniejszy kwartyl przychodów zawiera `62,92%` wszystkich braków;
- ROA i OCF/assets są wyraźnie niższe w grupie bez targetu;
- braki koncentrują się w określonych sektorach i SIC;
- `70,87%` braków dotyczy obserwacji mających dokładnie dwa braki w cechach bazowych;
- główne przyczyny są strukturalnie związane z modelem biznesowym i sposobem prezentacji sprawozdania.

Complete-case nie reprezentuje zatem całej populacji kwalifikujących się spółek. Szczególnie słabiej reprezentowane są małe, przedprzychodowe i nierentowne spółki oraz wybrane branże. Może to prowadzić do zbyt optymistycznego obrazu jakości danych i stabilności finansowej.

### 9.2. Survivorship bias — ryzyko umiarkowane i kierunkowo niekorzystne

Zbiór `1 459` sam w sobie składa się z obserwacji posiadających rekord t+1, więc brak targetu w tej grupie nie jest skutkiem całkowitego zniknięcia spółki. Filtr wymagający istnienia t+1 wyklucza jednak osobny zbiór `533` jakościowo poprawnych obserwacji t (`1,97%`), dla których nie ma kolejnego rekordu.

Obserwacje bez t+1 są wyraźnie mniejsze i słabsze niż obserwacje z parą:

- mediana log10 assets: `7,91` wobec `8,90`;
- mediana ROA: `-1,55%` wobec `2,47%`;
- mediana OCF/assets: `2,07%` wobec `6,65%`;
- mediana liabilities/assets: `0,576` wobec `0,529`;
- najmniejszy kwartyl aktywów odpowiada za `50,47%` przypadków bez t+1.

Brak następnego raportu może być powiązany z delistingiem, przejęciem, upadłością lub zakończeniem działalności. Nie można tego potwierdzić wyłącznie na obecnych danych, ale profil obserwacji wskazuje, że survivorship bias może usuwać trudniejsze przypadki i zaniżać częstość pogorszenia.

### 9.3. Informative censoring — ryzyko wysokie

Cenzurowanie jest powiązane z obserwowalną wielkością, rentownością, przepływami pieniężnymi, branżą oraz kompletnością sprawozdania. Dla 2024 dochodzi dodatkowy mechanizm prawego cenzurowania danych 2025. Braki targetu są więc informacyjne względem cech, które prawdopodobnie wiążą się również z kondycją finansową.

Nie można bezpiecznie założyć MAR wyłącznie po uwzględnieniu roku i sektora; część mechanizmu zależy od nieobserwowanej wartości t+1 oraz zdarzeń powodujących brak raportu. Tym bardziej niedopuszczalne byłoby przypisanie brakującym targetom klasy `0`.

## 10. Historyczny wniosek i zalecenia dla pracy

Brakujące targety stanowią **istotne ryzyko metodologiczne**, mimo że ich nominalny udział w kwalifikujących się parach jest niewielki (`5,51%`). Problemem nie jest sama liczba, lecz silna selektywność: braki dotyczą nieproporcjonalnie małych, przedprzychodowych, mniej rentownych i branżowo specyficznych spółek.

Ryzyko nie dyskwalifikuje badania, ale wymaga jawnego ograniczenia estimandu i analiz odporności. Rekomendowane działania:

1. poprawić rzutowanie `next_year_hard_exclude_flag` na `bool` i przeliczyć finalną próbę;
2. zachować brakujące targety jako `NA`, nigdy jako klasę `0`;
3. opisać model jako dotyczący spółek z pełnym, porównywalnym zestawem danych t–t+1, a nie całej populacji emitentów;
4. raportować coverage targetu według roku, sektora, SIC i kwartylu wielkości;
5. w analizie odporności zastosować wagi odwrotności prawdopodobieństwa kompletnego targetu wyznaczone wyłącznie na podstawie danych dostępnych w t albo co najmniej porównać wyniki ważone i nieważone;
6. przeprowadzić bounds/sensitivity analysis dla brakujących etykiet, zamiast imputować jedną klasę;
7. dla testowego feature year 2024 raportować zarówno pokrycie wśród istniejących par (`94,47%`), jak i efektywne pokrycie względem obserwacji jakościowych w t (`91,29%`);
8. rozważyć osobne potraktowanie spółek zeroprzychodowych i branż, w których current ratio jest strukturalnie niedostępny, ponieważ target v2 nie ma dla nich identycznej interpretacji ekonomicznej.

Po wdrożeniu tych zabezpieczeń ryzyko można uznać za kontrolowalne i właściwie ujawnione, ale obecnie nie powinno być pomijane jako technicznie losowe `5,5%` braków.

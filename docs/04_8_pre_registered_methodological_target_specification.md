# Pre-registered methodological target specification

Data rejestracji decyzji: 2026-08-17.

## 0. Datowane uzupełnienie po rejestracji — 2026-08-18

Poniższe sekcje 1–9 zachowują treść decyzji z dnia rejestracji i nie są
przepisywane wstecznie. Po prerejestracji wdrożono oraz zaudytowano target
vintage **PIT-B**:

- anchor targetu stanowi najwcześniejszy oryginalny 10-K za rok `t+1`;
- wartości `t+1` są wartościami current, a wartości `t` wartościami
  comparative z tego samego accession;
- późniejsze 10-K/A i restatements pozostają wyłączone;
- obowiązują walidacje reporting-entity continuity, annual fiscal period,
  semantyki primitives oraz konserwatywny, fail-closed resolver revenues;
- statusy `missing`, `ambiguous` i `hard-exclude` pozostają `NA` i nigdy nie
  są mapowane na klasę `0`.

Finalny audyt revenue resolvera, wykonany wyłącznie na train 2011–2020 i
validation 2021–2022, wydał werdykt `TARGET B READY TO FREEZE`. Jest to wynik
freeze-gate, a nie automatyczny akt zamrożenia. Target nie został jeszcze
formalnie zamrożony, a cały dataset pozostaje niezablokowany do czasu
ukończenia polityki point-in-time dla `X_t` i rozwiązania ryzyka survivorship
bias w research universe. Wyniki audytu znajdują się w
`data/reports/target_candidate_v2_pit_b_final_revenue_resolver.md`.

Dla przejrzystości: wczesne dokumenty pre-PIT raportowały opisowe agregaty dla
lat 2023–2024. Lata te nie były używane w rekonstrukcji ani freeze-gate PIT-B,
analizie revenue resolvera lub wyborze jego reguł, ale nie są całkowicie
nieoglądanym holdoutem dla wcześniejszej diagnostyki targetu. Nadal pozostają
wyłączone z dalszego doboru definicji, preprocessingu, cech i hiperparametrów.

## 1. Status i cel dokumentu

Niniejszy dokument rejestruje, przed rozpoczęciem właściwego modelowania i przed zamrożeniem zbioru danych, planowaną definicję targetu głównego oraz obowiązkowe analizy odporności.

Decyzja wynika z dotychczasowego audytu definicji targetu, diagnostyki rozkładów, predefiniowanej analizy wrażliwości, analizy potencjalnego podwójnego liczenia ROA i OCF/assets oraz audytu brakujących targetów.

Specyfikacja ma zapobiec późniejszemu dobieraniu definicji targetu do wyników modeli. Nie oznacza jeszcze zamrożenia datasetu. Przed jego zamrożeniem należy usunąć i ponownie skontrolować problemy point-in-time, data vintage oraz temporal leakage w pipeline danych.

## 2. Jednostka obserwacji i interpretacja

Jednostką obserwacji jest spółka–rok `(i, t)`. Target opisuje istotne, wielowymiarowe pogorszenie kondycji finansowej między rokiem `t` i dokładnie kolejnym rokiem `t+1`.

Cechy modelu `X_t` mogą wykorzystywać wyłącznie informacje dostępne w ustalonym momencie predykcji. Dane z `t+1` mogą być używane wyłącznie do konstrukcji targetu i jego diagnostyki; nie mogą być częścią zbioru cech modelu.

Target jest proxy pogorszenia kondycji finansowej. Nie jest bezpośrednią etykietą bankructwa, niewypłacalności, oszustwa ani manipulacji sprawozdawczej.

## 3. Pięć predefiniowanych sygnałów

Dla każdego poprawnie obserwowanego przejścia `t -> t+1` definiuje się:

### D1. Pogorszenie ROA

```text
D1_ROA = 1,
jeżeli ROA_t+1 - ROA_t <= -0,03
```

Sygnał oznacza spadek ROA o co najmniej 3 punkty procentowe.

### D2. Pogorszenie OCF/assets

```text
D2_OCF_assets = 1,
jeżeli OCF/assets_t+1 - OCF/assets_t <= -0,03
```

Sygnał oznacza spadek OCF/assets o co najmniej 3 punkty procentowe.

### D3. Pogorszenie current ratio

```text
D3_current_ratio = 1,
jeżeli current_ratio_t+1 / current_ratio_t <= 0,80
```

Sygnał oznacza względny spadek current ratio o co najmniej 20%.

### D4. Wzrost liabilities/assets

```text
D4_liabilities_assets = 1,
jeżeli liabilities/assets_t+1 - liabilities/assets_t >= 0,10
```

Sygnał oznacza wzrost liabilities/assets o co najmniej 10 punktów procentowych.

### D5. Spadek revenues

```text
D5_revenues = 1,
jeżeli revenues_t+1 / revenues_t - 1 <= -0,10
```

Sygnał oznacza względny spadek przychodów o co najmniej 10%.

W przeciwnym razie dany dostępny sygnał przyjmuje wartość `0`. Dokładne reguły kwalifikacji wartości i mianowników pozostają zgodne z definicją [`target_candidate_v2`](./04_3_target_candidate_v2_definicja.md).

## 4. Planowany target główny

```text
deterioration_score_1y =
    D1_ROA
  + D2_OCF_assets
  + D3_current_ratio
  + D4_liabilities_assets
  + D5_revenues
```

Planowany target główny pozostaje zdefiniowany następująco:

```text
target_candidate_v2 = 1, jeżeli deterioration_score_1y >= 3
target_candidate_v2 = 0, jeżeli deterioration_score_1y < 3
```

Definicja `score >= 3` pozostaje podstawową definicją do głównych eksperymentów, tabel i wnioskowania w pracy magisterskiej. Nie może zostać zastąpiona innym progiem na podstawie wyników modeli na validation ani test.

## 5. Obowiązkowe robustness targets

### 5.1. Alternatywne progi score

Na podstawie niezmienionych sygnałów D1–D5 należy utworzyć dwa z góry zadeklarowane targety odpornościowe:

```text
target_robustness_score_ge_2 = 1,
jeżeli deterioration_score_1y >= 2

target_robustness_score_ge_4 = 1,
jeżeli deterioration_score_1y >= 4
```

Wariant `score >= 2` reprezentuje łagodniejszą, a `score >= 4` bardziej restrykcyjną definicję wielowymiarowego pogorszenia. Są to wyłącznie robustness checks, a nie równorzędni kandydaci wybierani według wyników modeli.

### 5.2. Agregacja bloku ROA–OCF/assets

Ze względu na stwierdzoną materialną zależność bazowej klasy pozytywnej od oddzielnego naliczania ROA i OCF/assets obowiązkowy pozostaje wariant:

```text
operating_performance = max(D1_ROA, D2_OCF_assets)

alternative_score =
    operating_performance
  + D3_current_ratio
  + D4_liabilities_assets
  + D5_revenues

target_robustness_operating_performance = 1,
jeżeli alternative_score >= 3
```

Wariant ten sprawdza odporność wyników na potencjalne podwójne liczenie powiązanego bloku wyników operacyjnych. Nie zastępuje targetu głównego.

## 6. Brakujące targety

Brakujących targetów nie wolno oznaczać jako klasę `0`.

Jeżeli nie można wiarygodnie policzyć kompletu sygnałów wymaganych przez daną definicję, odpowiedni score i target pozostają brakujące (`NA`). Dotyczy to targetu głównego oraz wszystkich targetów odpornościowych.

Obserwacje z brakującym targetem:

- nie wchodzą do uczenia nadzorowanego dla tego targetu;
- pozostają objęte osobną diagnostyką braków i selection bias;
- nie mogą być zaliczane do klasy negatywnej w statystykach targetu ani metrykach modeli.

## 7. Zasady wykorzystania danych do decyzji metodologicznych

1. Target główny i robustness targets są ustalone przed właściwym modelowaniem.
2. Wyniki modeli nie mogą służyć do zmiany progów sygnałów, minimalnego score ani wyboru targetu dającego najkorzystniejsze metryki.
3. Test `2023–2024` nie może być używany do wyboru definicji targetu, preprocessingu, cech ani hiperparametrów.
4. Wyniki dla targetów odpornościowych należy raportować jako test stabilności wniosków względem definicji etykiety.
5. Ewentualne odstępstwo od tej specyfikacji wymaga osobnego, datowanego uzasadnienia i musi zostać jawnie opisane jako analiza post hoc.

## 8. Warunek poprzedzający zamrożenie datasetu

Dataset nie zostaje zamrożony na podstawie niniejszego dokumentu.

Przed zamrożeniem należy co najmniej:

1. zdefiniować moment predykcji i regułę `as-of`;
2. zapewnić, że wszystkie `X_t` były dostępne w tym momencie;
3. wdrożyć kontrolę filing date, accession number, 10-K/10-K/A oraz późniejszych restatementów;
4. usunąć dane i flagi z `t+1` z artefaktu cech;
5. zachować point-in-time provenance faktów SEC także po pivotowaniu danych;
6. zapewnić, że imputacja, winsoryzacja, skalowanie i feature selection będą dopasowywane wyłącznie na train, a w walidacji krzyżowej wewnątrz właściwego foldu czasowego;
7. ponownie przeliczyć diagnostykę targetów po naprawie pipeline'u i potwierdzić, że zmiany wynikają z korekty dostępności danych, a nie z dostrajania definicji targetu.

Dopiero po spełnieniu tych warunków można utworzyć i oznaczyć finalny, zamrożony dataset badawczy.

## 9. Zarejestrowana decyzja

Na dzień rejestracji obowiązuje następująca hierarchia:

| Rola | Definicja |
|---|---|
| Planowany target główny | `target_candidate_v2`, bazowy score `>= 3` |
| Robustness check 1 | bazowy score `>= 2` |
| Robustness check 2 | bazowy score `>= 4` |
| Obowiązkowy robustness check bloku ROA–OCF/assets | `operating_performance = max(D1, D2)`, `alternative_score >= 3` |
| Brak targetu | `NA`; nigdy automatycznie `0` |
| Status datasetu | niezablokowany; oczekuje na usunięcie problemów point-in-time i leakage |

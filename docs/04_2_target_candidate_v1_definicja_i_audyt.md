# `target_candidate_v1` — definicja i krótki audyt metodologiczny

> **Status metodologiczny (2026-08-18): dokument historyczny, pre-PIT.**
> Dokument zachowuje pierwszą kandydacką definicję oraz przesłanki przejścia
> do `target_candidate_v2`. Definicja `v1` została zastąpiona przez `v2` i nie
> jest planowanym targetem głównym. Liczebności poniżej pochodzą z ówczesnej
> ekstrakcji `sec_facts_wide.csv`, sprzed wdrożenia polityki PIT-B, walidacji
> semantycznej i rozdzielenia statusów `missing`, `ambiguous` oraz
> `hard-exclude`. Wstępne zestawienia obejmowały również lata 2023–2024, więc
> dokument nie stanowi aktualnego audytu ani dowodu pełnego zaślepienia testu.

## 1. Status dokumentu

`target_candidate_v1` jest zachowaną kandydacką definicją głównego targetu przyszłego, wielowymiarowego pogorszenia kondycji finansowej. Nie jest etykietą bankructwa, niewypłacalności, oszustwa ani manipulacji wynikiem finansowym.

Jednostką obserwacji jest para `spółka–rok (i, t)`. Cechy modelu pochodzą z roku `t`, natomiast target opisuje zmianę między rokiem `t` i dokładnie kolejnym rokiem `t+1`.

## 2. Warunki techniczne wyznaczenia targetu

Target można wyznaczyć tylko wtedy, gdy:

1. istnieją obserwacje tej samej spółki dla dokładnie kolejnych lat `t` i `t+1`;
2. żaden z tych dwóch `company-year` nie ma flagi `hard_exclude`;
3. wszystkie dane potrzebne do pięciu sygnałów są dostępne po technicznym czyszczeniu danych;
4. mianowniki spełniają reguły bezpieczeństwa:
   - `assets > 1 000 USD` w obu latach,
   - `current_liabilities > 1 000 USD` w obu latach,
   - `revenues > 1 000 USD` w obu latach;
5. rok `t+1` nie jest używany do budowy żadnej cechy wejściowej obserwacji z roku `t`.

Jeżeli nie można wyznaczyć choć jednego z pięciu sygnałów, `target_candidate_v1` przyjmuje wartość brakującą (`NA`), a obserwacja nie wchodzi do głównego eksperymentu.

Target jest liczony na wartościach po technicznych kontrolach jakości, ale przed imputacją i winsoryzacją. Wersja `v1` zakłada porównania na pełnej precyzji wartości liczbowych.

## 3. Definicje wielkości wejściowych

Dla każdego roku `y`:

```text
ROA_y                  = net_income_y / assets_y
OCF_to_assets_y        = operating_cash_flow_y / assets_y
current_ratio_y        = current_assets_y / current_liabilities_y
liabilities_to_assets_y = liabilities_y / assets_y
revenue_growth_t1      = revenues_t+1 / revenues_t - 1
```

Zmiana o `0,03` oznacza zmianę o 3 punkty procentowe, a nie zmianę o 3% wartości początkowej.

## 4. Dokładna definicja pięciu sygnałów

### S1. Pogorszenie rentowności

```text
S1 = 1, jeżeli:

(ROA_t >= 0 i ROA_t+1 < 0)
LUB
(ROA_t+1 - ROA_t <= -0,03)
```

W pozostałych przypadkach `S1 = 0`.

### S2. Pogorszenie zdolności generowania gotówki operacyjnej

```text
S2 = 1, jeżeli:

(OCF_to_assets_t >= 0 i OCF_to_assets_t+1 < 0)
LUB
(OCF_to_assets_t+1 - OCF_to_assets_t <= -0,03)
```

W pozostałych przypadkach `S2 = 0`.

### S3. Pogorszenie płynności

```text
S3 = 1, jeżeli:

(current_ratio_t >= 1 i current_ratio_t+1 < 1)
LUB
(current_ratio_t+1 / current_ratio_t <= 0,80)
```

W pozostałych przypadkach `S3 = 0`.

Drugi warunek oznacza spadek wskaźnika płynności bieżącej o co najmniej 20% względem poziomu z roku `t`.

### S4. Wzrost zadłużenia

```text
S4 = 1, jeżeli:

(liabilities_to_assets_t < 0,80 i liabilities_to_assets_t+1 >= 0,80)
LUB
(liabilities_to_assets_t+1 - liabilities_to_assets_t >= 0,10)
```

W pozostałych przypadkach `S4 = 0`.

Zmiana o `0,10` oznacza wzrost relacji zobowiązań do aktywów o 10 punktów procentowych.

### S5. Spadek przychodów

```text
S5 = 1, jeżeli:

revenues_t+1 / revenues_t - 1 <= -0,10
```

W pozostałych przypadkach `S5 = 0`.

Warunek oznacza spadek przychodów o co najmniej 10% między `t` i `t+1`.

## 5. Agregacja sygnałów

```text
deterioration_score_next_year = S1 + S2 + S3 + S4 + S5

target_candidate_v1 = 1,
jeżeli deterioration_score_next_year >= 3

target_candidate_v1 = 0,
jeżeli deterioration_score_next_year <= 2
```

Należy zachować w zbiorze zarówno binarny target, jak i wynik `deterioration_score_next_year` z przedziału `0–5` oraz wszystkie pięć flag składowych.

## 6. Historyczna empiryczna dostępność w danych pre-PIT

Na podstawie ówczesnego `data/interim/sec_facts_wide.csv` i istniejących wtedy reguł jakości:

- bazowa liczba kwalifikujących się par `t`–`t+1`: `26 479`;
- liczba obserwacji z kompletem pięciu sygnałów: `25 022`;
- liczba reprezentowanych spółek: `2 936`;
- pokrycie targetu: `94,5%` kwalifikujących się par;
- liczba obserwacji pozytywnych: `4 201`;
- udział klasy pozytywnej: `16,8%`.

Rozkład klasy pozytywnej w podziale czasowym wynosi około `14,9%` w train, `21,9%` w validation i `17,6%` w test.

## 7. Przypadki graniczne

### 7.1. Minimalne przekroczenie poziomu krytycznego

Każdy z poniższych przypadków daje pełny sygnał równy `1`, mimo bardzo małej zmiany:

| Sygnał | Rok `t` | Rok `t+1` | Wynik | Powód |
|---|---:|---:|---:|---|
| S1: ROA | `0,0001` | `-0,0001` | `1` | minimalne przejście poniżej zera |
| S2: OCF/assets | `0,0001` | `-0,0001` | `1` | minimalne przejście poniżej zera |
| S3: current ratio | `1,0000` | `0,9999` | `1` | minimalne przejście poniżej `1` |
| S4: liabilities/assets | `0,7999` | `0,8000` | `1` | minimalne osiągnięcie poziomu `0,80` |

W każdym przypadku niewielka różnica otrzymuje taką samą wagę jak zmiana bardzo duża.

### 7.2. Obserwacje po dwóch stronach progu zmiany

| Sygnał | Przypadek dający `1` | Bardzo podobny przypadek dający `0` |
|---|---|---|
| S1 | ROA: `0,1000 -> 0,0700` | ROA: `0,1000 -> 0,0701` |
| S2 | OCF/assets: `0,0800 -> 0,0500` | OCF/assets: `0,0800 -> 0,0501` |
| S3 | current ratio: `1,2500 -> 1,0000` | current ratio: `1,2500 -> 1,0001` |
| S4 | liabilities/assets: `0,5000 -> 0,6000` | liabilities/assets: `0,5000 -> 0,5999` |
| S5 | przychody: `100 mln -> 90 mln` | przychody: `100 mln -> 90,001 mln` |

Różnice ekonomiczne między parami mogą być nieistotne, ale etykiety są odmienne.

### 7.3. Słaby poziom bez dalszego pogorszenia

- ROA `-0,10 -> -0,09`: `S1 = 0`, ponieważ sytuacja poprawia się, choć ROA pozostaje ujemne.
- current ratio `0,90 -> 0,82`: `S3 = 0`, ponieważ wskaźnik był już poniżej `1`, nie spadł o 20% i nie przekroczył progu w tym roku.
- liabilities/assets `1,00 -> 1,05`: `S4 = 0`, ponieważ zadłużenie pozostaje bardzo wysokie, ale nie wzrosło o 10 punktów procentowych ani nie przekroczyło progu `0,80` w tym roku.

Są to skutki zamierzonego rozróżnienia między **pogorszeniem** a samym **niskim poziomem kondycji**.

### 7.4. Granica agregacji `3 z 5`

- Trzy minimalne przekroczenia progów dają `target_candidate_v1 = 1`.
- Dwa bardzo silne pogorszenia i trzy sygnały równe `0` dają `target_candidate_v1 = 0`.
- Target nie rozróżnia wyniku `3`, `4` i `5` po binarnej agregacji, dlatego należy zachować również pełny score.

## 8. Potencjalne problemy metodologiczne

1. **Nieciągłość progów.** Minimalne przekroczenie granicy zmienia cały sygnał z `0` na `1`. Powoduje to potencjalny szum etykiety przy obserwacjach blisko progów.

2. **Równa waga sygnałów i brak informacji o skali.** Każdy sygnał ma wagę `1`, niezależnie od wielkości pogorszenia. Spadek ROA o 3,00 p.p. jest traktowany tak samo jak spadek o 30 p.p.

3. **Mieszanie progów zmiany i progów poziomu.** Przejście przez zero, `current ratio = 1` lub `liabilities/assets = 0,80` może wywołać sygnał przy minimalnej zmianie, podczas gdy spółka pozostająca po złej stronie progu nie otrzyma sygnału bez odpowiednio dużego dalszego pogorszenia.

4. **Niepełna niezależność wymiarów.** ROA, OCF/assets, płynność i zadłużenie mogą reagować na te same zdarzenia gospodarcze. Reguła `3 z 5` nie gwarantuje trzech niezależnych źródeł ryzyka.

5. **Wrażliwość na mianowniki i wartości ekstremalne.** Niskie aktywa, zobowiązania krótkoterminowe lub przychody mogą powodować gwałtowne zmiany wskaźników. Próg techniczny `1 000 USD` zabezpiecza jedynie przed dzieleniem przez zero i bardzo małymi wartościami, ale nie zapewnia ekonomicznej materialności dla spółki publicznej.

6. **Wpływ zdarzeń jednorazowych.** Odpis, sprzedaż aktywów, przejęcie, restrukturyzacja, zmiana roku obrotowego lub jednorazowy spadek sprzedaży mogą dać target pozytywny bez trwałego pogorszenia kondycji.

7. **Heterogeniczność sektorowa.** Te same poziomy płynności i zadłużenia mogą mieć odmienne znaczenie w technologii, handlu i przemyśle. Wersja `v1` stosuje wspólne progi dla wszystkich sektorów.

8. **Zmiana częstości targetu w czasie.** Udział klasy pozytywnej różni się między train, validation i test. Może to odzwierciedlać cykl gospodarczy, zmianę składu próby albo zmianę jakości danych i powinno być opisane jako temporal drift.

9. **Complete-case selection bias.** Wymóg kompletu pięciu sygnałów usuwa obserwacje z brakami. Braki mogą częściej występować w określonych sektorach, latach lub wśród spółek o słabszej jakości raportowania.

10. **Target oparty na proxy.** Etykieta mierzy przyjętą operacjonalizację pogorszenia, a nie bezpośrednio obserwowalne zdarzenie ekonomiczne. Wynik modelu nie może być interpretowany jako prawdopodobieństwo bankructwa, fraudu ani niewypłacalności.

11. **Ryzyko leakage i błędnej chronologii.** Dane `t+1` mogą występować wyłącznie w targetach. Należy zachować daty filingów i sprawdzić, czy cechy roku `t` nie pochodzą z późniejszych porównań lub restatementów, które nie były dostępne w momencie predykcji.

12. **Dobór progów po obejrzeniu wyników.** Progów nie należy dostrajać do jakości modeli. `target_candidate_v1` powinien zostać zatwierdzony przed treningiem, a inne progi analizowane wyłącznie jako jawne warianty wrażliwości.

## 9. Minimalny audyt wymagany przed zatwierdzeniem targetu produkcyjnego

Przed uznaniem `target_candidate_v1` za finalny target główny należy:

1. policzyć liczbę obserwacji leżących bardzo blisko każdego progu;
2. porównać rozkład pięciu sygnałów według lat i sektorów;
3. sprawdzić najczęstsze kombinacje sygnałów tworzących klasę pozytywną;
4. ręcznie przejrzeć próbę przypadków granicznych oraz przypadków z ekstremalnymi zmianami;
5. powtórzyć analizę po wyłączeniu skrajnego 1% zmian wskaźników;
6. porównać wariant `score >= 3` z wcześniej zaplanowanymi wariantami wrażliwości, bez używania wyników modeli do wyboru definicji głównej.

# `target_candidate_v2` — definicja zmiany i pomocniczy score stanu

> **Status metodologiczny (2026-08-18): definicja sygnałów pozostaje aktualna;
> wyniki empiryczne są historyczne, pre-PIT.** Progi D1–D5, reguła
> `score >= 3` i zakaz mapowania braków na klasę `0` pozostają bez zmian.
> Liczebności i rozkłady w sekcjach 7–8 pochodzą jednak z wcześniejszej
> ekstrakcji, a nie z targetu PIT-B. Aktualny audyt PIT-B znajduje się w
> `data/reports/target_candidate_v2_pit_b_final_revenue_resolver.md` i obejmuje
> wyłącznie train 2011–2020 oraz validation 2021–2022. Wczesna diagnostyka
> poniżej raportowała również agregaty dla 2023–2024, dlatego lata te nie są
> w pełni nieoglądanym holdoutem dla diagnostyki definicji targetu.

## 1. Cel i status definicji

`target_candidate_v2` mierzy **istotne, wielowymiarowe pogorszenie kondycji finansowej między rokiem `t` i dokładnie kolejnym rokiem `t+1`**.

Target nie opisuje samego niekorzystnego poziomu wskaźnika. W szczególności osiągnięcie lub przekroczenie poziomu `0`, `1,0` albo `0,8` nie daje automatycznie sygnału w głównym score.

Definicja `v2` zastępuje w głównym score warunki przejścia przez poziomy zastosowane w [`target_candidate_v1`](./04_2_target_candidate_v1_definicja_i_audyt.md). Niekorzystny poziom w roku `t+1` jest zachowany jako osobna zmienna diagnostyczna `adverse_state_score_t1`.

`target_candidate_v2` pozostaje proxy pogorszenia kondycji. Nie jest etykietą bankructwa, niewypłacalności, oszustwa ani manipulacji wynikiem finansowym.

## 2. Jednostka obserwacji i wymagania danych

Jednostką obserwacji jest `spółka–rok (i, t)`. Cechy wejściowe modelu pochodzą wyłącznie z roku `t`, natomiast sygnały targetu wykorzystują zmianę między `t` i `t+1`.

Target można wyznaczyć, jeżeli:

1. istnieją obserwacje tej samej spółki dla dokładnie kolejnych lat `t` i `t+1`;
2. żaden z tych dwóch `company-year` nie ma flagi `hard_exclude`;
3. wszystkie wartości potrzebne do pięciu sygnałów są dostępne po technicznym czyszczeniu danych;
4. `assets > 1 000 USD` w obu latach;
5. `current_liabilities > 1 000 USD` w obu latach;
6. `revenues > 1 000 USD` w obu latach;
7. `current_ratio_t > 0` oraz `current_ratio_t+1 >= 0`.

Jeżeli nie można poprawnie policzyć choć jednego z pięciu sygnałów, `deterioration_score_1y` i `target_candidate_v2` przyjmują wartość brakującą (`NA`). Target nie jest imputowany.

## 3. Wielkości wejściowe

Dla każdego roku `y`:

```text
ROA_y                   = net_income_y / assets_y
OCF_to_assets_y         = operating_cash_flow_y / assets_y
current_ratio_y         = current_assets_y / current_liabilities_y
liabilities_to_assets_y = liabilities_y / assets_y
revenue_change_1y       = revenues_t+1 / revenues_t - 1
```

Zmiana o `0,03` lub `0,10` oznacza odpowiednio 3 albo 10 punktów procentowych, a nie 3% lub 10% wartości początkowej wskaźnika.

## 4. Pięć sygnałów pogorszenia

### D1. Spadek ROA o co najmniej 3 p.p.

```text
deterioration_roa_1y = 1,
jeżeli ROA_t+1 - ROA_t <= -0,03
```

W przeciwnym razie `deterioration_roa_1y = 0`.

### D2. Spadek OCF/assets o co najmniej 3 p.p.

```text
deterioration_ocf_to_assets_1y = 1,
jeżeli OCF_to_assets_t+1 - OCF_to_assets_t <= -0,03
```

W przeciwnym razie `deterioration_ocf_to_assets_1y = 0`.

### D3. Spadek current ratio o co najmniej 20%

```text
deterioration_current_ratio_1y = 1,
jeżeli current_ratio_t+1 / current_ratio_t <= 0,80
```

Równoważnie:

```text
(current_ratio_t+1 - current_ratio_t) / current_ratio_t <= -0,20
```

W przeciwnym razie `deterioration_current_ratio_1y = 0`.

### D4. Wzrost liabilities/assets o co najmniej 10 p.p.

```text
deterioration_liabilities_to_assets_1y = 1,
jeżeli liabilities_to_assets_t+1 - liabilities_to_assets_t >= 0,10
```

W przeciwnym razie `deterioration_liabilities_to_assets_1y = 0`.

### D5. Spadek przychodów o co najmniej 10%

```text
deterioration_revenues_1y = 1,
jeżeli revenues_t+1 / revenues_t - 1 <= -0,10
```

W przeciwnym razie `deterioration_revenues_1y = 0`.

## 5. Score i target binarny

```text
deterioration_score_1y =
    deterioration_roa_1y
  + deterioration_ocf_to_assets_1y
  + deterioration_current_ratio_1y
  + deterioration_liabilities_to_assets_1y
  + deterioration_revenues_1y
```

`deterioration_score_1y` przyjmuje wartości całkowite od `0` do `5`.

```text
target_candidate_v2 = 1,
jeżeli deterioration_score_1y >= 3

target_candidate_v2 = 0,
jeżeli deterioration_score_1y <= 2
```

W zbiorze należy zachować pięć flag składowych, pełny score oraz target binarny. Pozwala to audytować każdą etykietę i analizować różnicę między wynikiem `3`, `4` i `5`.

## 6. Pomocniczy `adverse_state_score_t1`

`adverse_state_score_t1` opisuje niekorzystny **poziom** wybranych wskaźników w roku `t+1`. Nie wchodzi do `deterioration_score_1y`, nie jest głównym targetem i nie może być cechą modelu dla obserwacji z roku `t`, ponieważ wykorzystuje dane przyszłe.

### Składowe stanu

```text
adverse_roa_t1 = 1,
jeżeli ROA_t+1 < 0

adverse_ocf_to_assets_t1 = 1,
jeżeli OCF_to_assets_t+1 < 0

adverse_current_ratio_t1 = 1,
jeżeli current_ratio_t+1 < 1,0

adverse_liabilities_to_assets_t1 = 1,
jeżeli liabilities_to_assets_t+1 >= 0,80
```

Następnie:

```text
adverse_state_score_t1 =
    adverse_roa_t1
  + adverse_ocf_to_assets_t1
  + adverse_current_ratio_t1
  + adverse_liabilities_to_assets_t1
```

Score przyjmuje wartości od `0` do `4`. Nie definiuje się obecnie osobnego binarnego targetu na jego podstawie.

Przychody nie wchodzą do `adverse_state_score_t1`, ponieważ ich absolutny poziom zależy od skali spółki i nie istnieje wspólny, ekonomicznie uzasadniony próg niekorzystnego poziomu dla całej próby. Spadek przychodów pozostaje wyłącznie sygnałem zmiany `D5`.

## 7. Interpretacja obu wyników

`deterioration_score_1y` i `adverse_state_score_t1` odpowiadają na różne pytania:

- `deterioration_score_1y`: w ilu wymiarach nastąpiło istotne pogorszenie między `t` i `t+1`;
- `adverse_state_score_t1`: ile wskaźników znajduje się na niekorzystnym poziomie w roku `t+1`.

Możliwe są między innymi następujące sytuacje:

- wysoki `deterioration_score_1y` i niski `adverse_state_score_t1`: spółka istotnie się pogorszyła, ale nadal pozostaje po korzystnej stronie progów poziomu;
- niski `deterioration_score_1y` i wysoki `adverse_state_score_t1`: spółka pozostaje w słabej kondycji, ale między `t` i `t+1` nie nastąpiło kolejne duże pogorszenie;
- wysokie oba wyniki: istotne pogorszenie doprowadziło do niekorzystnego stanu albo pogłębiło już istniejące problemy.

W ówczesnych danych pre-PIT występowało `565` obserwacji z `target_candidate_v2 = 1` i `adverse_state_score_t1 = 0` oraz `378` obserwacji z `target_candidate_v2 = 0` i `adverse_state_score_t1 = 4`. Historycznie potwierdziło to, że score zmiany i score poziomu mierzą odmienne konstrukty.

## 8. Historyczny empiryczny rozkład `target_candidate_v2` pre-PIT

Na podstawie ówcześnie przetworzonych danych, przed wdrożeniem PIT-B:

- bazowa liczba kwalifikujących się par `t`–`t+1`: `26 479`;
- liczba obserwacji z kompletnym `target_candidate_v2`: `25 020`;
- liczba reprezentowanych spółek: `2 936`;
- pokrycie targetu: `94,5%`;
- liczba obserwacji pozytywnych: `4 066`;
- udział klasy pozytywnej: `16,3%`.

| Split | Ważne obserwacje | Pozytywne | Udział klasy pozytywnej |
|---|---:|---:|---:|
| train: 2011–2020 | `15 255` | `2 199` | `14,4%` |
| validation: 2021–2022 | `4 702` | `1 010` | `21,5%` |
| test: 2023–2024 | `5 063` | `857` | `16,9%` |

Rozkład pełnego score:

| `deterioration_score_1y` | Liczba obserwacji | Udział |
|---:|---:|---:|
| 0 | `10 351` | `41,4%` |
| 1 | `6 704` | `26,8%` |
| 2 | `3 899` | `15,6%` |
| 3 | `2 402` | `9,6%` |
| 4 | `1 238` | `4,9%` |
| 5 | `426` | `1,7%` |

## 9. Pozostałe ograniczenia

Usunięcie przejść przez poziomy ogranicza problem pełnego sygnału wywołanego minimalnym przekroczeniem `0`, `1,0` lub `0,8`, ale nie usuwa wszystkich nieciągłości. Przykładowo spadek ROA o dokładnie `3,00` p.p. daje sygnał, a spadek o `2,99` p.p. go nie daje.

Pozostają również:

1. równa waga pięciu sygnałów niezależnie od skali pogorszenia;
2. wrażliwość wskaźników na małe mianowniki i wartości ekstremalne;
3. możliwa korelacja między ROA i OCF/assets oraz między płynnością i zadłużeniem;
4. wpływ zdarzeń jednorazowych, zmian zakresu działalności i restatementów;
5. wspólne progi dla sektorów o różnych strukturach finansowych;
6. zmienność częstości targetu między okresami;
7. complete-case selection bias wynikający z wymagania kompletu pięciu sygnałów.

Progów `v2` nie należy dostrajać do wyników modeli. Ewentualne alternatywne progi powinny być raportowane wyłącznie jako jawne analizy wrażliwości.

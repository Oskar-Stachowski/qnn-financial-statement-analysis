# Frozen target specification — `target_candidate_v2_pit_b` v1.0.0

Data formalnego zamrożenia: **2026-08-18**
Status: **FROZEN — target specification only**

## 1. Decyzja i zakres zamrożenia

`TARGET B` zostaje formalnie zamrożony jako główna definicja targetu pracy
magisterskiej. Zamrożenie obejmuje:

- definicje D1–D5 i ich progi;
- regułę `deterioration_score_1y >= 3`;
- politykę target vintage PIT-B;
- semantic and period validation;
- finalny fail-closed revenue resolver;
- politykę `missing`, `ambiguous` i `hard-exclude`;
- obowiązkowe targety robustness.

Zamrożenie **nie obejmuje** datasetu modelowego, `X_t`, preprocessingu,
research universe, selekcji cech, architektury modeli ani hiperparametrów.
Elementy te pozostają niezablokowane i wymagają osobnej kontroli point-in-time
oraz rozwiązania ryzyka survivorship bias przed budową finalnego `X_t`.

Raport freeze-gate poprzedzający tę decyzję zachowuje pole
`target_frozen = false`, ponieważ dokumentuje stan przed formalnym aktem
zamrożenia. Niniejszy dokument jest późniejszym, jawnym aktem freeze.

## 2. Jednostka obserwacji i interpretacja

Jednostką obserwacji jest spółka–rok `(i, t)`. Target mierzy istotne,
wielowymiarowe pogorszenie kondycji finansowej między `t` i `t+1`. Nie jest
etykietą bankructwa, fraudu, niewypłacalności ani manipulacji sprawozdawczej.

Dane `t+1` mogą być używane wyłącznie do konstrukcji i diagnostyki targetu.
Nie mogą wejść do cech modelu `X_t`.

## 3. Zamrożone sygnały D1–D5

Dla poprawnie zwalidowanych wartości definiuje się:

```text
D1_ROA = 1,
jeżeli ROA_t+1 - ROA_t <= -0,03

D2_OCF_assets = 1,
jeżeli OCF/assets_t+1 - OCF/assets_t <= -0,03

D3_current_ratio = 1,
jeżeli current_ratio_t+1 / current_ratio_t <= 0,80

D4_liabilities_assets = 1,
jeżeli liabilities/assets_t+1 - liabilities/assets_t >= 0,10

D5_revenues = 1,
jeżeli revenues_t+1 / revenues_t - 1 <= -0,10
```

Nie stosuje się w głównym score samych przejść przez poziomy `0`, `1,0` lub
`0,8`. Każdy dostępny sygnał niespełniający odpowiedniego warunku przyjmuje
wartość `0`.

## 4. Zamrożony target główny

```text
deterioration_score_1y =
    D1_ROA
  + D2_OCF_assets
  + D3_current_ratio
  + D4_liabilities_assets
  + D5_revenues

target_candidate_v2 = 1, jeżeli deterioration_score_1y >= 3
target_candidate_v2 = 0, jeżeli deterioration_score_1y < 3
```

Definicja `score >= 3` nie może zostać zastąpiona inną definicją na podstawie
wyników modeli, validation ani testu.

## 5. Zamrożona polityka PIT-B

Dla targetu obowiązuje:

1. anchor stanowi najwcześniejszy oryginalny 10-K za rok `t+1`;
2. wartości `t+1` są wartościami current z tego accession;
3. wartości `t` są wartościami comparative przedstawionymi w tym samym
   accession;
4. current i comparative muszą pochodzić z tego samego accession oraz z
   właściwych annual instant/duration contexts;
5. 10-K/A, późniejsze restatements i fakty pochodzące z późniejszych filingów
   są wyłączone;
6. standardowe lata 52/53-tygodniowe pozostają dopuszczalne;
7. transition lub nierozstrzygnięty fiscal period prowadzi do braku targetu;
8. zmiana accounting predecessor lub reporting entity zgodna z zamrożonym
   rejestrem/regułami powoduje `hard-exclude`;
9. zwykłe reclassifications i discontinued operations nie powodują
   automatycznego wykluczenia.

## 6. Zamrożony resolver revenues

Revenue resolver działa fail-closed. Dopuszcza przychody wyłącznie wtedy, gdy
ten sam standardowy concept oraz obie wartości annual current/comparative są
jednoznacznie potwierdzone na skonsolidowanym issuer-level primary statement of
operations/income wskazanym przez FilingSummary dla anchor accession.

Component, segment, project, collaboration, unbilled, note-only lub inna
niepotwierdzona pozycja nie może zastępować skonsolidowanych annual revenues.
Brak jednoznacznego potwierdzenia daje `ambiguous/NA`, a nie heurystyczny wybór
i nie klasę `0`.

## 7. Zamrożona polityka niedostępnego targetu

Jeżeli któregokolwiek wymaganego sygnału nie można wiarygodnie policzyć:

- `missing` pozostaje `NA`;
- `ambiguous` pozostaje `NA`;
- `hard-exclude` pozostaje `NA`;
- żadnego z tych statusów nie wolno mapować na klasę `0`.

Obserwacje bez dostępnego targetu nie wchodzą do uczenia nadzorowanego dla
tego targetu, ale pozostają przedmiotem raportowania missingness i selection
bias.

## 8. Obowiązkowe robustness checks

Bez zmiany D1–D5 obowiązkowo należy raportować:

```text
target_robustness_score_ge_2 = 1, gdy deterioration_score_1y >= 2
target_robustness_score_ge_4 = 1, gdy deterioration_score_1y >= 4

operating_performance = max(D1_ROA, D2_OCF_assets)
alternative_score = operating_performance + D3 + D4 + D5
target_robustness_operating_performance = 1, gdy alternative_score >= 3
```

Są to analizy odporności, a nie kandydaci wybierani według jakości modeli.
Wartości agreement i Jaccard z historycznych analiz pre-PIT należy przeliczyć
na zamrożonej populacji PIT-B wyłącznie dla train i validation przed ich
raportowaniem jako wyników finalnych.

## 9. Populacja development i coverage w chwili freeze

Freeze-gate obejmował wyłącznie train 2011–2020 i validation 2021–2022:

| Miara | Wartość |
|---|---:|
| Populacja train + validation | `26 917` |
| Target available | `14 122` |
| Coverage targetu | `52,46%` |
| Klasa pozytywna wśród available | `2 167` |
| Udział klasy pozytywnej | `15,34%` |

Coverage około 52,5% jest właściwością konserwatywnej, semantycznie
zwalidowanej definicji PIT-B, a nie błędem polegającym na przypisaniu braków do
klasy negatywnej.

## 10. Obowiązkowe ograniczenia metodologiczne

- **Complete-case selection bias: wysokie ryzyko.** Dostępność targetu zależy
  od roku, sektora, SIC, wielkości spółki i profilu finansowego.
- **Informative censoring: istotne ryzyko.** Brak anchor `t+1`, annual
  primitives albo jednoznacznej prezentacji revenues może być związany z
  kondycją spółki, delistingiem, M&A lub fazą pre-revenue.
- **Survivorship bias: nierozwiązane ryzyko upstream.** Obecny research
  universe może wykorzystywać bieżącą listę spółek/SIC/sektora i musi zostać
  poprawiony przed finalnym `X_t`.
- Estymand głównego eksperymentu dotyczy spółka–lat z dostępnym, porównywalnym
  targetem PIT-B, a nie automatycznie całej populacji emitentów SEC.

Ograniczeń tych nie wolno redukować przez oznaczenie niedostępnych targetów
jako `0` ani przez złagodzenie resolvera po obejrzeniu wyników modeli.

## 11. Test 2023–2024

Feature years 2023–2024 nie zostały użyte do rekonstrukcji PIT-B, finalnego
revenue-resolver audit ani decyzji freeze. Nie wolno ich używać do późniejszej
zmiany targetu, preprocessingu, cech lub hiperparametrów.

Jednocześnie wcześniejsze dokumenty pre-PIT pokazały agregaty dla tych lat.
Nie należy więc przedstawiać testu jako całkowicie nieoglądanego względem
wczesnej diagnostyki targetu. Może on nadal pełnić rolę czasowego testu modeli,
o ile to wcześniejsze ujawnienie zostanie jawnie opisane.

## 12. Reprodukcja i wersjonowanie

Maszynowo czytelny manifest znajduje się w
`configs/target_candidate_v2_pit_b_freeze_manifest.yaml`. Zawiera:

- wersję targetu;
- pełny commit bazowy sprzed aktu freeze;
- commity implementacji, audytu i wyników;
- SHA-256 konfiguracji, kodu, testów i dowodów manual review;
- wersje środowiska użytego przy freeze.

Commit zawierający niniejszy dokument, manifest, konfigurację i testy jest
wersją repozytorium formalnie zamrażającą target. Manifest celowo nie zawiera
własnego hasha ani hasha własnego commita, aby uniknąć samoodniesienia.

## 13. Kontrola zmian po freeze

Po zamrożeniu nie wolno zmieniać D1–D5, progów, `score >= 3`, polityki PIT-B,
revenue resolvera ani polityki niedostępności w ramach wersji `1.0.0`.

Każda konieczna późniejsza korekta wymaga jednocześnie:

1. nowego identyfikatora wersji targetu;
2. datowanego uzasadnienia przed ponownym modelowaniem;
3. nowego manifestu i audytu train/validation;
4. zachowania wersji `1.0.0` jako punktu odniesienia;
5. jawnego oznaczenia zmiany jako odstępstwa lub analizy post hoc.

Wyniki modeli nie mogą być uzasadnieniem zmiany zamrożonej definicji.

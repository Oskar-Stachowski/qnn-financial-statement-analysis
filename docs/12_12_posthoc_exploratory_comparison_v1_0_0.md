# Post-hoc exploratory comparison v1.0.0

Data: **2026-08-25**

Status: **COMPLETE — DEVELOPMENT ONLY**

## Cel i granica

Pakiet zamyka dwie ograniczone luki metodologiczne przy użyciu wyłącznie
istniejących surowych wyników OOF z lat walidacyjnych 2015–2020:

1. sparowane porównanie XGBoost z HistGradientBoosting i Random Forest;
2. seed-matched porównanie QNN `20260818` z istniejącymi kontrolami
   PCA-matched dla tego samego seedu.

Analiza jest jawnie `post-hoc exploratory`, warunkowa względem wcześniejszej
selekcji konfiguracji i bez korekty winner's curse lub wielokrotności. Nie jest
prerejestrowaną analizą confirmatory i nie zmienia głównego rankingu modeli.

Nie wykonano fitu, refitu, nowych predykcji, kalibracji, zmiany progu, tuningu,
nowych seedów, ensemble ani zmiany splitów. Nie otwarto żadnego wiersza,
predykcji, cechy, targetu lub metryki dla lat 2021–2024.

## Metoda

- jednostka losowania: `economic_group_id`;
- 2 000 replikacji bootstrapu ze zwracaniem;
- identyczne losowania klastrów dla wszystkich modeli w każdej replikacji;
- 95% przedział percentylowy, percentyle 2,5 i 97,5, metoda NumPy `linear`;
- seed bootstrapu `20260818`;
- metryki: average precision (AP; historycznie PR-AUC) oraz ROC-AUC;
- kierunek różnicy: model A minus model B.

Wszystkie cztery porównania wykorzystują ten sam zestaw 10 760 obserwacji OOF,
1 986 przypadków dodatnich i 3 340 klastrów ekonomicznych. Wszystkie 2 000
replikacji było niedegenerowanych.

## Seed-matched scope

QNN, PCA-matched MLP i PCA-matched fixed-L2 logistic używają seedu `20260818`,
tych samych sześciu foldów, identycznych zbiorów treningowych i walidacyjnych,
identycznego preprocessingu oraz tych samych fold-fitted czterech komponentów
PCA. MLP ma również ten sam hash środowiska co QNN. Kontrola logistyczna działała
w innym środowisku programowym, co zostało ujawnione, ale jej dane, preprocessing
i reprezentacja PCA są dopasowane.

W projekcie nie istnieje osobny artefakt „fixed-L2 MLP”. Bez nowego treningu nie
można go utworzyć. Dlatego wykonano porównanie z jedyną istniejącą kontrolą
fixed-L2: PCA-matched regresją logistyczną. Różnica jest oznaczona w tabeli
`request_mapping` i w disclosure.

## Wyniki i artefakty

Pakiet znajduje się w `reports/posthoc_exploratory_comparison_v1_0_0/`:

- `summary.md` — zwarte zestawienie liczb i granic twierdzeń;
- `tables/01_*` — XGBoost vs HistGB i RF;
- `tables/02_*` — QNN vs kontrole PCA-matched dla seedu `20260818`;
- `tables/03_*` — istniejące, predefiniowane warianty QNN, opisowo;
- `tables/04_*` — istniejąca stabilność trzech seedów;
- `tables/05_*` — kontrole zgodności kluczy, seedów, membership, preprocessingu
  i PCA;
- `tables/06_*` — obowiązkowe ograniczenia metodologiczne;
- `tables/07_*` — exact-path provenance i SHA-256;
- `tables/08_*` — 8 000 audytowalnych rekordów replikacji bootstrapu;
- `tables/09_*` — kompaktowa tabela do późniejszej integracji przez autora;
- `figures/` — dwa forest plots w PNG i SVG;
- `manifest.json` — granice dostępu, status PASS oraz hashe wyjść.

## Reprodukcja

```bash
bash scripts/run_posthoc_exploratory_comparison_v1_0_0.sh
```

Generator odtwarza pakiet w katalogu tymczasowym i wymaga identycznego zestawu
plików oraz SHA-256. Konfiguracją autorytatywną jest
`configs/posthoc_exploratory_comparison_v1_0_0.yaml`.

## Obowiązkowe zastrzeżenie do późniejszego użycia

Każda tabela lub figura wykorzystana przez autora musi być oznaczona jako
`post-hoc exploratory`, `development-only`, `conditional-on-selection` i
`selection-unadjusted`. Przedziały nie są p-value, nie są skorygowane o proces
selekcji modeli ani wielokrotne porównania i nie uzasadniają formalnego
twierdzenia o przewadze modelu.

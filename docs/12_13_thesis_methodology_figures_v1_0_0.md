# Figury metodologiczne do pracy v1.0.0

## Cel i status

Pakiet `reports/thesis_methodology_figures_v1_0_0/` zawiera trzy grafiki
przeznaczone do metodologicznej i wynikowej części pracy:

1. schemat pipeline'u i zabezpieczeń przed leakage;
2. oś czasu ról okresów badania;
3. waterfall selekcji głównej próby modelowej.

Pakiet ma status `REPORTING_ONLY`. Generator korzysta wyłącznie z zamrożonych
konfiguracji, dokumentacji metodologicznej i dwóch kompaktowych tabel
agregatowych. Nie otwiera chronionych danych wierszowych, nie dopasowuje modeli,
nie tworzy predykcji i nie przelicza wyników predykcyjnych.

## Diagram pipeline'u

Diagram rozdziela warstwę danych point-in-time od modelowania i oceny. Pokazuje
następujące bariery:

- historyczne filing-first membership i exact anchor accession;
- brak fallbacku do późniejszego filingu oraz brak informacji `t+1` w `X_t`;
- jawny `target_available_at` i cutoff walidacyjny;
- SHA-256 membership próby supervised;
- expanding-window CV z rocznym embargo;
- preprocessing dopasowany wyłącznie na fold-train;
- ranking wyłącznie na pooled OOF 2015--2020;
- wersjonowane gates i zakaz tuningu/reselekcji po wynikach chronionych.

Pełne sformułowania i źródła każdego węzła zapisano w
`tables/01_pipeline_stages_and_safeguards.csv`.

## Oś czasu

Oś czasu jawnie rozdziela:

- `2011--2014`: początkową historię treningową dla temporal CV, nie osobny okres
  raportowania wyników;
- `2015--2020`: development OOF użyty do selekcji i rankingu;
- `2021--2022`: design-exposed/spent development, tylko secondary evidence;
- `2023--2024`: temporal holdout z prior-exposure disclosure, nie fully unseen.

Role nie mogą być łączone w jeden pooled estimand. Wyniki okresów chronionych
nie mogą aktywować tuningu ani zmiany metody.

## Waterfall próby

Waterfall przedstawia wyłącznie selection flow próby modelowej train
2011--2020:

`47 938 -> 19 784 -> 19 671`.

Niedostępny target PIT-B usuwa `28 154` obserwacje, a niedopuszczony
`x_t_status` dalsze `113`. Retencja względem puli train wynosi `41,03%`.

Nie jest to ten sam mianownik co pełne filing-first universe 2011--2024, dla
którego target availability wynosi osobno `26 602 / 64 901 = 40,99%`.

## Artefakty

- `figures/01_pipeline_and_leakage_safeguards.*`;
- `figures/02_period_timeline.*`;
- `figures/03_sample_selection_waterfall.*`;
- `tables/01_pipeline_stages_and_safeguards.csv`;
- `tables/02_period_timeline.csv`;
- `tables/03_sample_selection_waterfall.csv`;
- `tables/04_source_provenance.csv`;
- `manifest.json`.

SVG jest preferowany do finalnego składu, a PNG stanowi wersję kompatybilną.

## Odtworzenie

```bash
bash scripts/run_thesis_methodology_figures_v1_0_0.sh
```

Polecenie najpierw generuje pakiet, a następnie odtwarza go w katalogu
tymczasowym i porównuje hashe wszystkich artefaktów.


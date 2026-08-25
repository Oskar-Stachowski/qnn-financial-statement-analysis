# Post-hoc exploratory comparisons v1.0.0

Status: **COMPLETE — DEVELOPMENT ONLY**

Pakiet jest technicznym zestawieniem dowodów, nie tekstem pracy ani analizą confirmatory. Wszystkie CI są warunkowe względem wcześniejszej selekcji konfiguracji, bez korekty selekcji i wielokrotności.

## Sparowane porównania modeli drzewiastych

| Porównanie (A − B) | ΔAP | 95% CI | ΔROC-AUC | 95% CI |
|---|---:|---:|---:|---:|
| XGBoost − HistGradientBoosting | 0.005279 | [-0.004754; 0.014580] | 0.001076 | [-0.001788; 0.004102] |
| XGBoost − Random Forest | 0.006452 | [-0.001956; 0.014736] | 0.001086 | [-0.001649; 0.004147] |

## Seed-matched QNN i kontrole PCA

| Porównanie (A − B) | ΔAP | 95% CI | ΔROC-AUC | 95% CI |
|---|---:|---:|---:|---:|
| QNN − PCA-matched MLP | -0.009429 | [-0.022515; 0.003928] | -0.003145 | [-0.006539; 0.000423] |
| QNN − PCA-matched fixed-L2 logistic | 0.002207 | [-0.013658; 0.017610] | -0.000331 | [-0.004412; 0.003913] |

Kontrola określona w prośbie jako fixed-L2 MLP nie istnieje w artefaktach. Wykorzystano istniejącą PCA-matched regresję logistyczną fixed-L2; nie wykonano nowego fitu.

## Granice

- wyłącznie OOF 2015–2020;
- 2 000 sparowanych losowań klastrów `economic_group_id`;
- AP = average precision;
- brak p-value i brak formalnego twierdzenia o przewadze;
- brak dostępu do danych chronionych i brak zmian głównego rankingu.

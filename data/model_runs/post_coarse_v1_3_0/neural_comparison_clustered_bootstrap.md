# Clustered bootstrap: refined MLP vs QNN

Status: **COMPLETE**.

Jednostka losowania: `economic_group_id`; poprawne replikacje: 2000/2000; seed: `20260818`.

| Model | Block | PR-AUC | 95% CI | ΔPR-AUC vs MLP | 95% CI różnicy |
|---|---:|---:|---:|---:|---:|
| Refined MLP | L+D | 0.396263 | [0.375772, 0.419443] | 0.000000 | [0.000000, 0.000000] |
| QNN | L | 0.372969 | [0.352288, 0.395790] | -0.023294 | [-0.039402, -0.006735] |
| QNN | L+D | 0.373961 | [0.354057, 0.395900] | -0.022302 | [-0.037103, -0.008424] |
| QNN | L+D+R | 0.383948 | [0.364326, 0.407518] | -0.012316 | [-0.026889, 0.003082] |

Przedziały są sparowane, ale opisują rozwojowe OOF warunkowo względem wybranych konfiguracji. Nie są niezależnym testem, nie korygują selekcji modelu, a raportowane prawdopodobieństwo bootstrapowe nie jest wartością p. Wynik z analitycznego symulatora nie stanowi dowodu przewagi kwantowej.

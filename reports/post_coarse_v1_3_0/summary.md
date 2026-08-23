# Wyniki refinementu i eksperymentu QNN

Raport dotyczy wyłącznie wewnętrznej walidacji czasowej OOF 2015–2020. Nie otwiera ani nie wykorzystuje lat chronionych 2021–2024.

## Refinement modeli klasycznych

Pozycje głównego refinementu: **28**. Pozycje dodatkowego refinementu MLP: **8**.

Najlepsza jednoseedowa konfiguracja dodatkowego MLP:

- `model_stage_v1__refinement__pytorch_mlp__epochs_300__001`, blok **L+D**, PR-AUC **0.395256**, ROC-AUC **0.746026**.

## QNN

Status fazy QNN: **COMPLETE**.

Wybrany globalny ansatz Q1: **ROT_CNOT_RING** (konfiguracja `model_stage_v1__qnn_q1__rot_cnot_ring`, blok **L+D+R**, PR-AUC **0.383798**).

## Confirmation i porównanie MLP–QNN

Sloty confirmation modeli klasycznych/MLP: **30**. Sloty QNN: **3**.

- **Refined MLP**: PR-AUC **0.396263**, ROC-AUC **0.746409**, ΔPR-AUC vs MLP **0.000000**.
- **QNN L**: PR-AUC **0.372969**, ROC-AUC **0.732330**, ΔPR-AUC vs MLP **-0.023294**.
- **QNN L+D**: PR-AUC **0.373961**, ROC-AUC **0.738855**, ΔPR-AUC vs MLP **-0.022302**.
- **QNN L+D+R**: PR-AUC **0.383948**, ROC-AUC **0.740584**, ΔPR-AUC vs MLP **-0.012316**.

> Uwaga metodologiczna: dodatkowy refinement MLP jest analizą wtórną, zadeklarowaną po coarse searchu i przed QNN. Nie zmienia głównego, zamrożonego rankingu modeli klasycznych; służy wyłącznie porównaniu klasycznej sieci neuronowej z QNN.

## Niepewność porównania MLP–QNN

Status clustered bootstrap: **COMPLETE**. Poprawne replikacje: **2000**/**2000**, jednostka losowania: `economic_group_id`, seed: `20260818`.

- **Refined MLP**: PR-AUC **0.396263** (95% CI [0.375772, 0.419443]), ΔPR-AUC vs MLP **0.000000** (95% CI [0.000000, 0.000000]).
- **QNN L**: PR-AUC **0.372969** (95% CI [0.352288, 0.395790]), ΔPR-AUC vs MLP **-0.023294** (95% CI [-0.039402, -0.006735]).
- **QNN L+D**: PR-AUC **0.373961** (95% CI [0.354057, 0.395900]), ΔPR-AUC vs MLP **-0.022302** (95% CI [-0.037103, -0.008424]).
- **QNN L+D+R**: PR-AUC **0.383948** (95% CI [0.364326, 0.407518]), ΔPR-AUC vs MLP **-0.012316** (95% CI [-0.026889, 0.003082]).

> Te przedziały są sparowane, ale dotyczą rozwojowego OOF i są warunkowe względem wybranych konfiguracji. Nie są niezależnym testem, nie korygują selekcji modeli, a prawdopodobieństwo bootstrapowe nie jest wartością p.

## Główny ranking rozwojowy

Globalny zwycięzca głównego protokołu: **xgboost**, `model_stage_v1__coarse__xgboost__004`, blok **L+D+R**.

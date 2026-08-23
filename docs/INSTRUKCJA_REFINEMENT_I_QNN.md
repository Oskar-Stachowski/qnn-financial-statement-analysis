# Instrukcja: refinement modeli klasycznych, dodatkowy MLP i eksperyment QNN

> **Status procedury — zakończona 2026-08-23.** Wszystkie opisane poniżej etapy
> refinementu, QNN Q1/Q2, confirmation, inference i raportowania zostały
> wykonane, a wyniki zamrożono w wersji post-coarse `v1.3.0`. Ten dokument jest
> instrukcją odtworzeniową i zapisem kolejności wykonania; nie jest poleceniem do
> ponownego uruchomienia etapów w istniejącym katalogu wynikowym. Aktualny stan
> opisuje [`10_current_experiment_status.md`](10_current_experiment_status.md), a
> integralność zamrożonego wyniku określa
> [`10_1_post_coarse_v1_3_0_results_freeze.md`](10_1_post_coarse_v1_3_0_results_freeze.md).

Przed jakąkolwiek pracą na istniejących wynikach uruchom wyłącznie odczytowy
verifier:

```bash
.venv-classical/bin/python -m src.modeling.verify_post_coarse_results_freeze
```

Oczekiwany werdykt to `POST_COARSE_V1_3_0_RESULTS_INTEGRITY_PASS`. Następnym
dozwolonym etapem są osobno wersjonowane analizy wtórne na OOF 2015–2020:
PCA-matched controls, interpretowalność i robustness. Ta instrukcja nie
autoryzuje dostępu do lat 2021–2024.

## 1. Co robi ta paczka

Paczka uruchamia dalszą część eksperymentu **bez ponownego wykonywania coarse searchu**. Wykorzystuje gotowy i zamrożony katalog:

`data/model_runs/classical_mlp_coarse_v1`

Kolejność jest wymuszona przez pliki kontrolne:

1. główny refinement rodzin zakwalifikowanych przez pierwotną regułę: XGBoost, HistGradientBoosting i Random Forest;
2. dodatkowy refinement PyTorch MLP jako **wtórny komparator klasyczna NN–QNN**;
3. QNN Q1: 3 ansatze × 3 bloki cech;
4. zamrożenie jednego globalnego ansatzu;
5. QNN Q2 osobno dla bloków `L`, `L+D`, `L+D+R`;
6. zamrożenie konfiguracji wybranych do confirmation;
7. confirmation z dodatkowymi seedami `20260819` i `20260820`;
8. sparowany clustered bootstrap dla refined MLP vs QNN;
9. raporty końcowe i osobna tabela refined MLP vs QNN.

Dodatkowy MLP **nie zmienia pierwotnej reguły refinementu ani głównego rankingu modeli klasycznych**. Jest raportowany oddzielnie, ponieważ decyzja o jego rozszerzeniu została podjęta po coarse searchu, ale przed refinementem i QNN.

## 1.1. Ważne: zachowaj lokalne artefakty coarse searchu

Do późniejszego uśrednienia trzech seedów potrzebne są surowe OOF predictions z bazowego seedu `20260818`. Część tych plików może być celowo ignorowana przez Git i dlatego nie musi być widoczna na GitHubie. **Nie usuwaj lokalnego katalogu `data/model_runs/classical_mlp_coarse_v1/candidate_results` ani wskazanych w manifeście plików `canonical_oof_predictions.json`.** Sam zbiorczy `classical_mlp_coarse_search_manifest.json` nie wystarcza do końcowego confirmation. Komenda `plan` sprawdza ich obecność i hashe przed rozpoczęciem dalszych obliczeń.

## 2. Instalacja plików

Rozpakuj ZIP poza repozytorium, wejdź do katalogu paczki i najpierw sprawdź jej integralność:

```bash
python3 scripts/verify_post_coarse_package.py
```

Następnie skopiuj pliki do repozytorium:

```bash
bash apply_to_repo.sh /pełna/ścieżka/do/qnn-financial-statement-analysis
```

Skrypt instalacyjny automatycznie powtarza kontrolę SHA-256 przed kopiowaniem.

Następnie przejdź do repozytorium:

```bash
cd /pełna/ścieżka/do/qnn-financial-statement-analysis
```

## 3. Kontrola i obowiązkowy commit przed obliczeniami

Najpierw uruchom testy statyczne:

```bash
bash scripts/run_post_coarse.sh test
```

Sprawdź zmiany:

```bash
git status --short
```

Dodaj pliki:

```bash
git add \
  configs/model_stage_v1_3_0_neural_comparator_amendment.yaml \
  configs/post_coarse_experiment_v1_0_0.yaml \
  src/modeling/post_coarse_runner.py \
  src/modeling/post_coarse_reporting.py \
  src/modeling/neural_comparison_inference.py \
  scripts/run_post_coarse.sh \
  docs/INSTRUKCJA_REFINEMENT_I_QNN.md \
  docs/UZASADNIENIE_MLP_JAKO_DODATKOWEGO_KOMPARATORA.md \
  tests/test_post_coarse_runner.py
```

Zrób commit **przed pierwszym fitem refinementu lub QNN**:

```bash
git commit -m "Add post-coarse refinement and QNN protocol"
```

Runner odmówi model fittingu, gdy jego pliki metodyczne są nieśledzone albo zmodyfikowane po commicie. Jest to celowe zabezpieczenie przed zmianą reguł po zobaczeniu wyników.

## 4. Wskazanie interpreterów

Skrypt próbuje automatycznie znaleźć typowe katalogi środowisk. Najpierw sprawdź:

```bash
bash scripts/run_post_coarse.sh status
```

Jeżeli przy którymś interpreterze pojawi się `NOT FOUND`, ustaw pełne ścieżki. Przykład:

```bash
export CLASSICAL_PYTHON="$PWD/.venv-classical/bin/python"
export QNN_PYTHON="$PWD/.venv-qnn-mlp/bin/python"
```

Nazwy katalogów mogą być inne. Interpreter `classical` musi odpowiadać lockfile `environments/classical/requirements.lock`, a interpreter `qnn_mlp` — `environments/qnn_mlp/requirements.lock`.

Tryby `test`, `plan`, `inference` i `report` wymagają tylko interpretera `classical`; `smoke` wymaga tylko `qnn_mlp`; tryby wykonujące refinement, QNN lub confirmation wymagają obu.

## 5. Preflight QNN i plan bez obliczeń na danych projektu

Najpierw wykonaj syntetyczny smoke test wszystkich ansatzów i obu rozmiarów PCA:

```bash
bash scripts/run_post_coarse.sh smoke
```

Oczekiwany wynik w konsoli i w pliku `data/model_runs/post_coarse_v1_3_0/qnn_resource_smoke.json`:

```text
"status": "PASS"
```

Następnie wygeneruj plan. Ta komenda nie fituje modeli:

```bash
bash scripts/run_post_coarse.sh plan
```

Sprawdź:

```bash
python -m json.tool data/model_runs/post_coarse_v1_3_0/post_coarse_plan.json | less
```

Plan powinien wykazać m.in.:

- 247 pozycji coarse wykorzystanych ponownie bez refitu;
- 3 główne rodziny refinementu;
- 8 dodatkowych konfiguracji MLP na bloku `L+D`;
- 9 pozycji Q1;
- 12 logicznych pozycji Q2, z trzema pozycjami `t0` odziedziczonymi z Q1;
- 3 sloty QNN confirmation i 36 dodatkowych fold fits.

## 6. Etap A — refinement modeli klasycznych i MLP

Uruchom:

```bash
bash scripts/run_post_coarse.sh refinement
```

Skrypt wykonuje:

- XGBoost na zamrożonym najlepszym bloku `L+D+R`;
- HistGradientBoosting na `L+D+R`;
- Random Forest na `L+D+R`;
- dodatkowy PyTorch MLP na zamrożonym najlepszym bloku MLP `L+D`.

Po zakończeniu sprawdź status:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path("data/model_runs/post_coarse_v1_3_0/refinement_phase_manifest.json")
x = json.loads(p.read_text())
print("status:", x["status"])
print("primary:", x["primary_track"]["counts"])
print("MLP comparator:", x["supplemental_mlp_comparator"]["counts"])
PY
```

Wymagane do przejścia dalej:

```text
status: COMPLETE
```

`COMPLETE` na poziomie fazy oznacza, że wszystkie zaplanowane pozycje mają stan terminalny. Pojedyncza konfiguracja może być technicznie nieważna i jest wtedy jawnie policzona w polu `technically_invalid`; nie jest zastępowana ręcznie.

Wygeneruj raport cząstkowy:

```bash
bash scripts/run_post_coarse.sh report
```

Najważniejsze pliki:

- `reports/post_coarse_v1_3_0/01_primary_refinement_results.csv`;
- `reports/post_coarse_v1_3_0/02_mlp_comparator_refinement_results.csv`;
- `reports/post_coarse_v1_3_0/summary.md`.

## 7. Etap B — QNN Q1 i Q2

Dopiero po poprawnym manifeście refinementu uruchom:

```bash
bash scripts/run_post_coarse.sh qnn
```

Runner najpierw wykonuje Q1. Bezpośrednio po Q1 zapisuje i hashuje:

`data/model_runs/post_coarse_v1_3_0/qnn_selected_ansatz.json`

Dopiero potem może wykonać Q2. Nie ma ręcznego wyboru ansatzu.

Po zakończeniu sprawdź:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path("data/model_runs/post_coarse_v1_3_0/qnn_phase_manifest.json")
x = json.loads(p.read_text())
print("status:", x["status"])
print("ansatz:", x["ansatz_selection"])
print("Q1:", x["q1_counts"])
print("Q2:", x["q2_counts"])
PY
```

Dopuszczalne terminalne statusy fazy:

- `COMPLETE` — wybrano ansatz i wykonano Q2;
- `QNN_TECHNICALLY_INFEASIBLE` — nie było kompletnej technicznie konfiguracji Q1. Taki wynik również jest wynikiem naukowym i nie wolno ręcznie podstawiać innego ansatzu.

Wygeneruj ponownie raport:

```bash
bash scripts/run_post_coarse.sh report
```

Najważniejsze nowe tabele:

- `03_qnn_q1_ansatz_results.csv`;
- `04_qnn_q2_results.csv`.

## 8. Etap C — confirmation i wynik końcowy

Confirmation jest rozdzielone na dwie jawne, wznawialne fazy. Najpierw uruchom
wyłącznie modele klasyczne i dodatkowy komparator MLP:

```bash
bash scripts/run_post_coarse.sh confirmation-classical
```

Przed rozpoczęciem dodatkowych seedów skrypt zapisuje zamrożony wybór do:

`data/model_runs/post_coarse_v1_3_0/post_coarse_confirmation_selection.json`

Po ukończeniu tej fazy zapisuje bramkę
`confirmation_classical_phase_manifest.json` z polem
`qnn_confirmation_started: false`. Na tym etapie można bezpiecznie się zatrzymać.

Po osobnej kontroli bramki uruchom confirmation QNN:

```bash
bash scripts/run_post_coarse.sh confirmation-qnn
```

Druga komenda wznawia zamrożoną selekcję i wykonuje:

- confirmation jednej najlepszej konfiguracji Q2 na każdy z trzech bloków, czyli 36 dodatkowych fold fits QNN.

Trzy niezależne reprezentanty bloków QNN mogą pracować równolegle, ale
seedy `20260819`, `20260820` i foldy wewnątrz każdego kandydata zachowują
zamrożoną kolejność. Wyniki są zapisywane w zamrożonej kolejności bloków.
Confirmation używa osobnego `qnn_confirmation_resource_ledger.json`, aby nie
zmieniać hasha ukończonej fazy QNN.

Tryb `confirmation` nadal wykonuje obie części po kolei, lecz nie daje punktu
kontrolnego przed pierwszym fitem QNN.

Po zakończeniu najpierw wykonaj zamrożoną analizę niepewności:

```bash
bash scripts/run_post_coarse.sh inference
```

Dopiero potem wygeneruj raport końcowy:

```bash
bash scripts/run_post_coarse.sh report
```

Analiza `inference` wykonuje **2 000 sparowanych replikacji clustered bootstrap** po `economic_group_id`, z seedem `20260818`. Te same wylosowane klastry są stosowane do MLP i wszystkich reprezentantów QNN. Raportowany jest 95-procentowy przedział percentylowy dla PR-AUC, ROC-AUC oraz różnic `QNN − MLP`. Przedziały opisują niepewność na rozwojowym OOF warunkowo względem wybranych konfiguracji; nie są niezależnym testem i nie korygują selekcji modeli. Pole z prawdopodobieństwem bootstrapowym nie jest wartością p. Technicznie nieważny blok QNN jest jawnie odnotowany i pomijany; analiza jest wykonywana dla pozostałych kompletnych bloków. Jeżeli nie ma żadnego kompletnego reprezentanta QNN, wynik otrzymuje status `NOT_APPLICABLE_QNN_TECHNICALLY_INFEASIBLE`.

Najważniejsze artefakty:

- `data/model_runs/post_coarse_v1_3_0/final_primary_development_ranking.json` — główny ranking, bez dodatkowego MLP;
- `data/model_runs/post_coarse_v1_3_0/neural_comparison_manifest.json` — osobne refined MLP vs QNN;
- `data/model_runs/post_coarse_v1_3_0/neural_comparison_clustered_bootstrap.json` — pełny manifest niepewności;
- `data/model_runs/post_coarse_v1_3_0/neural_comparison_clustered_bootstrap.csv` — tabela punktów i 95% CI;
- `data/model_runs/post_coarse_v1_3_0/neural_comparison_clustered_bootstrap.md` — krótka interpretacja;
- `reports/post_coarse_v1_3_0/05_primary_confirmation_results.csv`;
- `reports/post_coarse_v1_3_0/06_confirmed_mlp_vs_qnn.csv`;
- `reports/post_coarse_v1_3_0/07_final_primary_family_ranking.csv`;
- `reports/post_coarse_v1_3_0/08_neural_comparison_clustered_bootstrap.csv`;
- `reports/post_coarse_v1_3_0/summary.md`.

## 9. Sprawdzenie kompletności

```bash
bash scripts/run_post_coarse.sh status
```

Po pełnym przebiegu powinny istnieć:

- `refinement_phase_manifest.json`;
- `qnn_phase_manifest.json`;
- `confirmation_phase_manifest.json`;
- `neural_comparison_clustered_bootstrap.json`;
- `run_manifest.json`.

Dodatkowo możesz sprawdzić łańcuch końcowy. Po `inference` plik `run_manifest.json` zawiera również hash manifestu clustered bootstrap:

```bash
python -m json.tool data/model_runs/post_coarse_v1_3_0/run_manifest.json
```

## 10. Wznawianie i błędy

Kompletne foldy są wznawialne: ponowne uruchomienie tej samej fazy wykorzysta już istniejące poprawne artefakty. Nie usuwaj ręcznie pojedynczych plików z katalogów kandydatów.

Jeżeli wykonanie zakończy się terminalnym, niekompletnym foldem, jego ponowne uruchomienie w tym samym katalogu jest celowo blokowane. W takiej sytuacji zachowaj stary katalog do audytu i uruchom nową, jawnie wersjonowaną ścieżkę, np.:

```bash
export POST_COARSE_OUTPUT_DIR="$PWD/data/model_runs/post_coarse_v1_3_0_retry_01"
```

Nie kasuj starego wyniku i nie podmieniaj seedów, hiperparametrów ani ansatzu.

Jeżeli `plan` zgłosi brak albo niezgodny hash artefaktu coarse OOF, zatrzymaj eksperyment. Przywróć dokładny lokalny katalog z backupu. Dopiero gdy odtworzenie nie jest możliwe, wykonaj coarse search ponownie w osobnym katalogu i w dokładnie zamrożonych środowiskach; nie mieszaj artefaktów z dwóch przebiegów.

## 11. Czego nie robić

Nie uruchamiaj starego trybu pełnego `execute`, ponieważ ponownie wykona coarse search. Nie edytuj konfiguracji po zobaczeniu wyników refinementu albo QNN. Nie otwieraj lat 2021–2024 na potrzeby wyboru modelu. Nie włączaj dodatkowego MLP do głównego rankingu — jego rola jest wtórna i porównawcza.

Tryb:

```bash
bash scripts/run_post_coarse.sh all
```

jest dostępny, ale zalecane jest wykonywanie `refinement`, `qnn`,
`confirmation-classical` i `confirmation-qnn` osobno, z kontrolą manifestu po
każdej fazie.


## 12. Co pozostaje po tej paczce

Ta paczka kończy rdzeń eksperymentu: refinement, QNN Q1/Q2, confirmation, porównanie MLP–QNN i rozwojową analizę niepewności. Nie zastępuje późniejszych analiz wtórnych przewidzianych w kontrakcie projektu. Po zamrożeniu końcowych reprezentantów nadal należy osobno wykonać:

- diagnostyczne kontrole PCA-matched: fixed L2 i MLP na dokładnie tej samej reprezentacji PCA co finalny QNN;
- interpretowalność modeli, w tym Integrated Gradients dla MLP i analizę komponentów/sensytywności QNN;
- prerejestrowane testy odporności bez ponownego strojenia;
- kontrolowane otwarcie 2021–2022 dopiero po pełnym freeze gate, a następnie odrębny gate przed 2023–2024.

Te analizy nie mogą zmieniać wyboru ansatzu, rosteru modeli, hiperparametrów ani głównego rankingu zamrożonego w tej fazie.

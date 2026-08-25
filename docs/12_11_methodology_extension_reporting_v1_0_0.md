# Rozszerzenie metodologiczne: stabilność seedów i koszt obliczeniowy v1.0.0

## Cel i status

Pakiet `methodology_extension_v1_0_0` uzupełnia raportowanie wyników development
o dwa elementy wymagane przed pisaniem pracy:

1. opisową ocenę stabilności końcowych modeli względem trzech seedów;
2. porównanie zarejestrowanego kosztu obliczeniowego końcowych reprezentantów
   oraz osobny bilans etapów programu eksperymentalnego.

Pakiet ma status `REPORTING_ONLY`. Generator nie konstruuje i nie dopasowuje
modeli, nie uruchamia benchmarku i nie otwiera danych z chronionych lat
2021–2024. Wszystkie metryki pochodzą z istniejących predykcji OOF dla lat
2015–2020, a czasy z zapisanych manifestów i ledgerów.

## Stabilność seedów

Dla każdego stochastycznego reprezentanta raportowane są osobno wyniki seedów
`20260818`, `20260819` i `20260820` oraz średnia, odchylenie standardowe z próby,
minimum, maksimum i rozstęp. Statystyki dotyczą pooled OOF PR-AUC i ROC-AUC.

Końcowy wynik `SCORE_AVERAGED_ENSEMBLE` jest obliczany po uśrednieniu raw score
dla każdego rekordu OOF. Nie jest on średnią arytmetyczną trzech wartości AP.
Zmienność między seedami jest raportowana oddzielnie od zmienności między
foldami czasowymi.

Trzy seedy pozwalają wyłącznie na opis rozrzutu. SD i zakres nie są przedziałami
ufności i nie stanowią podstawy do wnioskowania inferencyjnego. Dummy prior,
fixed L2 logistic i RBF SVM zachowują pojedynczy deterministyczny run i otrzymują
status `NOT_APPLICABLE_DETERMINISTIC_SINGLE_RUN`.

## Koszt końcowych reprezentantów

Porównanie główne wykorzystuje sumę zapisanych sekund prób workera dla sześciu
foldów czasowych. Dla modeli z trzema seedami pokazane są mediana i zakres
czasów; dla modeli deterministycznych pojedynczy zapisany czas. Dodatkowo
raportowany jest opisowy mnożnik względem mediany XGBoost.

Nie jest to kontrolowany benchmark sprzętowy. Wykonania odbywały się w różnych
środowiskach Pythona i bibliotek oraz w różnych momentach. Wartości są przydatne
do pokazania rzędu wielkości kosztu, lecz nie do precyzyjnego porównania
implementacji lub sprzętu.

## Koszt programu eksperymentalnego

Koszty etapów są oddzielone od kosztu pojedynczego finalnego reprezentanta.
W tabeli występują komponenty coarse search, refinement i confirmation dla
modeli klasycznych/MLP oraz Q1/Q2 i confirmation dla QNN. Wiersze `TOTAL` są
podsumowaniami nieaddytywnymi względem wcześniejszych wierszy i nie powinny być
sumowane ponownie.

Pełnej ścieżki QNN nie należy zestawiać jako ilorazu z pojedynczym fittem
XGBoost, ponieważ liczba kandydatów i szerokość procedury poszukiwania są inne.

## Backend QNN i granice twierdzeń

Finalne QNN wykorzystywało analityczny symulator `lightning.qubit`,
`shots=None`, interfejs PyTorch, różniczkowanie `adjoint` i `float64`. Końcowy
wariant miał 4 kubity, 2 warstwy, ansatz `ROT_CNOT_RING` i 29 parametrów
trenowalnych. Czasy nie są opóźnieniem sprzętu kwantowego, a wyniki z symulatora
nie uzasadniają twierdzenia o przewadze kwantowej.

## Artefakty

- `tables/01_seed_stability_summary.csv` — tabela główna do pracy;
- `tables/02_seed_stability_detailed.csv` — wartości per seed i ensemble;
- `tables/03_compute_cost_final_representatives.csv` — główne porównanie kosztu;
- `tables/04_compute_cost_per_seed.csv` — czasy i metryki per seed;
- `tables/05_compute_cost_program_stages.csv` — bilans etapów badania;
- `tables/06_runtime_environments.csv` — środowiska i szczegóły QNN;
- `tables/07_methodological_disclosures.csv` — gotowe ograniczenia do pracy;
- `tables/08_source_provenance.csv` — hashe źródeł;
- `tables/09_seed_stability_thesis_compact.csv` — zwarta tabela do DOCX;
- `tables/10_compute_cost_thesis_compact.csv` — zwarta tabela kosztu do DOCX;
- `figures/01_seed_stability_pr_auc.*` — dot-range stabilności;
- `figures/02_pr_auc_vs_runtime.*` — AP względem czasu w skali logarytmicznej;
- `manifest.json` — hashe i liczności całego pakietu.

Zgodnie z zasadami wykorzystania AI w projekcie pakiet nie generuje akapitów,
interpretacji ani podpisów przeznaczonych do wklejenia do pracy. Autor tworzy
je samodzielnie na podstawie tabel zwartych, tabel audytowych i rejestru
ograniczeń metodologicznych.

## Uruchomienie

```bash
bash scripts/run_methodology_extension_report_v1_0_0.sh
```

# Audyt gotowości pracy v1.0.5

Data: **2026-08-24**

Werdykt: **BASELINE_AUDIT_FAIL**

Audyt został ukończony. Wynik `FAIL` nie dotyczy integralności modeli: oba
zamrożone pakiety wyników przeszły swoje bezpieczne verifiery. Blokery znajdują
się przede wszystkim w niescalonej i nieaktualnej warstwie pracy magisterskiej.

## Granica audytu

Użyto committed allowlisty v1.0.5 z commitu
`1416e4f941632890f2f945a311c8c15ae1c2a652` i SHA-256
`b6c79a296e88dab37ccd049f97b8e69516247c9e63486b8bf2256c4ef6019359`.
Committed review z commitu `48301abe72da735fe5dfaac078600b99f334c7a8`
ma `ALLOWLIST_REVIEW_PASS` i zero findingów.

Nie otwarto lat cech 2021–2024, ich schematów, próbek, predykcji ani metryk.
Nie wykonano fitu, refitu, inferencji, predykcji, reportingu, notebooka, sieci
ani zewnętrznego storage. Wyniki są wyłącznie development OOF 2015–2020.
Wyjście wcześniejszej, zbyt szerokiej komendy `rg` nie zostało wykorzystane
jako dowód; wnioski oparto na exact-path evidence.

## Macierz ośmiu kontroli

| Kontrola | Ocena | Wniosek |
|---|---|---|
| PIT population, target, X_t, preprocessing, PCA, temporal CV | PASS z naprawą dokumentacji | Implementacja i kontrakty są spójne; tekst pracy jest częściowo przestarzały. |
| Leakage, survivorship, censoring, estimand | PASS z ograniczeniami | Filing-first universe usuwa główny błąd current-snapshot; informative censoring pozostaje jawne. |
| Selekcja, seedy, kalibracja, próg, raportowanie | IMPORTANT gaps | Decyzje są zamrożone, lecz thesis-facing reporting contract nie jest domknięty. |
| Integralność primary i secondary | PASS | Oba verifiery przeszły. |
| XGBoost, MLP, PCA controls, QNN | PASS z ograniczeniami inferencji | Liczby są zgodne; porównania nie są selection-adjusted ani niezależnym testem. |
| Rozdziały, README, dokumentacja | FAIL — BLOCKER | README jest aktualny, dokument pracy nie. |
| Testy i reprodukowalność | Częściowy PASS | Pakiety freeze są zweryfikowane; pełnego suite w Kroku 6 nie uruchamiano. |
| Nieuprawnione twierdzenia | PASS z cleanupem | Aktualne raporty nie twierdzą independent test, fully unseen ani quantum advantage. |

## Co jest technicznie i naukowo w dobrym stanie

Historyczne uniwersum jest filing-first, a nie oparte na bieżącej liście
tickerów. Zawiera 64 901 eligible company-years i odzyskuje 6 267 historycznych
CIK oraz 30 871 company-years względem starego current snapshot; 6 123 z tych
CIK nie ma w bieżącym snapshot. To istotnie ogranicza survivorship bias.

Target używa pierwszego oryginalnego 10-K za `t+1`, dokładnego accession,
sygnałów D1–D5 i reguły `deterioration_score_1y >= 3`. Braki i przypadki
niejednoznaczne pozostają NA. Coverage około 52,46% wymusza warunkowy estimand
i jawne ograniczenie informative censoring; projekt tego nie maskuje. IPW
zostało odrzucone z powodu słabej positivity, skrajnych wag, niskiego ESS i
niewiarygodnego MAR/support.

Preprocessing i PCA są dopasowywane wyłącznie na treningowej części każdego
foldu. CV ma sześć expanding-window foldów, embargo i dokładny cutoff
`target_available_at`. Główną metryką jest pooled OOF PR-AUC 2015–2020, a
bootstrap klastruje po `economic_group_id`.

Verifier primary potwierdził 30 plików, 8 tabel, 36 fold-fitów QNN confirmation
i 2 000 poprawnych replikacji bootstrapu. Verifier secondary potwierdził 16
plików compact, inventory 585 plików oraz 96/96 ukończonych zadań. Żaden z nich
nie dopasowywał modelu ani nie otwierał okresu chronionego.

## Wyniki, które wolno raportować

Głównym zwycięzcą development OOF jest XGBoost `L+D+R`: PR-AUC 0,413089 i
ROC-AUC 0,759870. Refined MLP comparator ma PR-AUC 0,396263. Najlepszy
potwierdzony QNN `L+D+R`, z ansatzem `ROT_CNOT_RING`, ma PR-AUC 0,383948.
Różnica QNN minus MLP wynosi -0,012316, z paired clustered 95% CI
[-0,026889; 0,003082]. Nie daje to podstawy do twierdzenia o przewadze QNN.

MLP PCA-matched osiąga jednoseedowe 0,393227, a fixed-L2 PCA-matched 0,381590,
przy trzyseedowej referencji QNN 0,383948. To porównanie jest opisowe, a nie
seed-matched. Warianty pipeline XGBoost dają zbliżone wyniki; warianty definicji
targetu zmieniają prevalencję, więc ich PR-AUC nie jest bezpośrednio
porównywalne. Strukturalne warianty QNN ani usunięcie splątania nie wspierają
twierdzenia o quantum advantage.

## BLOCKER

1. **Finalny dokument nie jest złożony.** `thesis/Praca Magisterska Oskar
   Stachowski os109908.docx` ma w ekstrakcji 442 słowa: stronę tytułową, spis
   treści i puste nagłówki. Brak zintegrowanych rozdziałów, wstępu, zakończenia,
   bibliografii, wykazów i streszczenia.

2. **Rozdział 5 opisuje nieaktualny stan.** Twierdzi, że refinement, QNN,
   confirmation, kalibracja, robustness i interpretowalność nie zostały
   wykonane, oraz zawiera liczne pola `DO UZUPEŁNIENIA`. Wszystkie te etapy są
   już ukończone i zamrożone. Rozdział musi zostać napisany na podstawie
   istniejących raportów primary i secondary.

3. **Rozdział 1 podaje inną definicję targetu.** Tekst mówi o pogorszeniu co
   najmniej dwóch z trzech wymiarów, podczas gdy zamrożona definicja ma pięć
   sygnałów D1–D5 i próg score >= 3. Należy skorygować tekst, bez zmiany targetu.

4. **Rozdział 4 ma przestarzały status wykonania.** Nadal twierdzi, że pełny
   ranking, kalibratory i progi nie istnieją oraz że runner nie wykonał pełnego
   eksperymentu. Należy opisać faktycznie wykonany, zamrożony stan i zachować
   jego development-only granice.

5. **Rozdział 3 nie jest redakcyjnie ukończony.** Aktualny PDF zawiera zdanie
   „W tej części rozdziału należy jeszcze zdefiniować...” dotyczące VQC. Zawiera
   też jawnie oznaczoną ilustrację wygenerowaną przez GPT Image/ChatGPT. Sekcję
   trzeba dokończyć, a ilustrację rozliczyć w odrębnej bramce autora i użycia AI;
   ten audyt nie przesądza statusu tej bramki.

## IMPORTANT

- **Kontrakt raportowania po kalibracji.** Artefakty kalibratora i progu są
  kompletne i zahashowane, lecz praca sama wskazuje brak zamrożonego zestawu
  Brier/log loss, intercept/slope, confusion matrix, precision, recall,
  specificity i F1. Trzeba zamrozić thesis-facing schema albo jawnie oznaczyć
  niedostępne pola, zanim otworzy się późniejsze bramki.

- **Granica inferencji.** Bootstrap MLP–QNN jest sparowany i klastrowany, ale
  warunkowy względem wybranych konfiguracji; nie koryguje selekcji ani wielu
  porównań. Nie należy przedstawiać jego prawdopodobieństwa jako p-value ani
  formułować definitywnej przewagi.

- **Brak bieżącego globalnego baseline testów.** W Kroku 6 wolno było uruchomić
  tylko named safe verifiers. Historyczne „14 failures / 305 passed” pozostaje
  nieważne. Pełny test run wymaga następnego manifestu dostępu do testów.

- **Terminologia okresów.** Starszy frozen dokument pipeline nadal nazywa
  2021–2022 one-shot external validation. Polityka nadrzędna i README poprawnie
  mówią `design-exposed / spent development`. Finalna praca musi używać wyłącznie
  terminologii nadrzędnej i jawnie wskazać supersession.

## OPTIONAL

- Wyjaśnić, że supplemental MLP był wybierany z połączonej puli coarse plus
  refinement, choć zwycięska tożsamość ma `stage=coarse`.
- Przy każdej tabeli i figurze dodać wersję raportu/manifestu oraz zachować
  oznaczenie single-seed vs three-seed jako porównania opisowego.

## Decyzja

Krok 6 jest ukończony z werdyktem `BASELINE_AUDIT_FAIL`: 5 blockerów,
4 findingi important i 2 optional. Dalsze kroki runbooka nie są autoryzowane,
dopóki wszystkie blockery nie zostaną faktycznie zamknięte i potwierdzone w
successor raporcie. Nie ma potrzeby powtarzać modeli ani otwierać lat 2021–2024;
następna praca dotyczy przede wszystkim tekstu, integracji i kontraktu raportowania.

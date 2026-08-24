# Pozostałe zadania projektu i pracy magisterskiej — kompletny runbook

Stan zweryfikowany: **2026-08-24**

Bazowy stan eksperymentu: commit `ae8ab17`
(`Resolve data access incidents after independent review`).

Ten dokument jest listą pozostałej pracy, kolejnością jej wykonania i zbiorem
gotowych promptów. Nie jest zgodą na otwarcie danych ani na zmianę zamrożonego
eksperymentu. Commit wprowadzający niniejszy runbook stanowi nowy punkt bazowy
planu; jego hash należy zanotować przy rozpoczęciu Kroku 1.

## Zakres i stan zastany

Rekomendowana ścieżka kończy badanie na wynikach **development-only OOF dla lat
walidacyjnych 2015–2020**. Zgodnie z
[`10_current_experiment_status.md`](10_current_experiment_status.md) wykonane i
zamrożone są już między innymi:

- model development, finalna selekcja rodzin, seedy, kalibracja i próg;
- post-coarse oraz confirmation;
- 96/96 zadań secondary-development i ich zamrożony pakiet raportowy;
- niezależny review dwóch incydentów dostępu do danych.

Nie należy ponownie wykonywać tych etapów. Lata cech 2021–2024 pozostają
zamknięte zgodnie z
[`09_1_data_access_policy_v1_1_0.md`](09_1_data_access_policy_v1_1_0.md).
Opcjonalna ścieżka chronionych okresów znajduje się na końcu dokumentu i nie
może uruchomić się automatycznie.

Główny DOCX jest obecnie szkieletem, a osobne rozdziały są wersjami roboczymi.
Dlatego ukończenie repozytorium technicznego nie oznacza jeszcze ukończenia
pracy magisterskiej.

## Źródła nadrzędne

W sprawach eksperymentu i dostępu do danych pierwszeństwo mają:

- [`09_1_data_access_policy_v1_1_0.md`](09_1_data_access_policy_v1_1_0.md) i jej
  konfiguracja maszynowa;
- [`09_5_data_access_incident_v1_1_0_independent_review_v1_0_0.md`](09_5_data_access_incident_v1_1_0_independent_review_v1_0_0.md);
- [`08_3_model_execution_contract_v1_2_0.md`](08_3_model_execution_contract_v1_2_0.md)
  oraz `configs/model_execution_contract_v1_2_0.yaml`;
- [`10_current_experiment_status.md`](10_current_experiment_status.md) i
  obowiązujące successor amendments/freezes;
- historyczne frozen specifications tylko jako dowód chronologii, z
  uwzględnieniem późniejszych supersession declarations.

W sprawach akademickich pierwszeństwo mają zawsze aktualne akty i strony SGH:

- [zasady wykorzystania AI](https://www.sgh.waw.pl/wyciag-z-zasad-wykorzystania-ai-przy-przygotowaniu-prac-pisemnych);
- [wzór pracy i wymagania formalne](https://www.sgh.waw.pl/wzor-pracy-magisterskiej-i-wymagania-formalne);
- [zasady i terminy składania pracy](https://www.sgh.waw.pl/zasady-skladania-pracy-magisterskiej);
- [zasady egzaminu magisterskiego](https://www.sgh.waw.pl/egzamin-magisterski).

Stan z 2026-08-24 dla studentów IV semestru 2025/2026 lato wskazuje wgranie
zaakceptowanej pracy do APD do **2026-09-21** i pozytywną ocenę promotora do
**2026-09-24**. Te daty trzeba ponownie potwierdzić przed składaniem; nie należy
traktować ich jako uniwersalnych dla innego toku lub indywidualnej decyzji.

## Twarda granica wykorzystania AI w SGH

Codex może pomagać w ideacji, wyszukiwaniu i rozumieniu literatury, korekcie
językowej i stylistycznej, formatowaniu bibliografii, programowaniu, analizie
danych, obliczeniach, wykresach/diagramach wykonanych według własnych wytycznych
autora oraz technicznym składzie dokumentu.

Codex ani Work/Chat **nie mogą**:

- tworzyć koncepcji pracy lub jej zasadniczych elementów za autora;
- tworzyć akapitów, rozdziałów ani całości pracy, także pierwszej wersji;
- rozszerzać tekstu autora;
- tworzyć opisów wyników obliczeń, ich interpretacji lub wniosków;
- dostosowywać pytań i hipotez do poznanych wyników;
- tworzyć grafik przypominających fotografie lub ilustracje;
- być cytowane jako źródło informacji.

Autor samodzielnie pisze treść naukową, opisuje wyniki, interpretuje je i
formułuje wnioski. AI może później wskazać niespójność albo wykonać korektę
językową bez dopisywania treści. Każdy brak merytoryczny ma wrócić do autora,
nie zostać uzupełniony przez model.

Praca musi zawierać wyodrębnioną sekcję o sposobie i zakresie użycia AI, a
obiekty stworzone z udziałem AI muszą być oznaczone. Prompty i odpowiedzi trzeba
gromadzić, z wyjątkiem ideacji i operacji na tekście. Rejestru nie wolno
rekonstruować ani upiększać po fakcie. Promotor może dodatkowo ograniczyć użycie
AI. Jeżeli rejestr zawiera dane wrażliwe, należy przechowywać go bezpiecznie poza
publicznym repozytorium, a w repo zapisać wyłącznie niesensytywny manifest.

## Zasady wykonania wszystkich kroków

1. Wykonuj kroki kolejno, po jednym. Jedyny wyjątek to jawny skok do opcjonalnej
   ścieżki po Kroku 7C, opisany w jej punkcie wejścia. Oznaczenie „świeża sesja”
   oznacza nowy kontekst Codex bez dostępu do treści poprzedniego audytu poza
   committed artefaktami jawnie wpisanymi na allowlistę.
2. Każdy krok zaczyna się od sprawdzenia `HEAD` i `git status`. Nie dołączaj do
   commitu zmian autora ani plików spoza zakresu kroku.
3. Każda zmiana kontraktu, kodu, raportu lub dokumentacji ma osobny commit.
   Raport `FAIL`/`NOT_READY` także jest wynikiem i ma zostać zacommitowany.
   Wyjątkiem jest nieoczekiwany dostęp do chronionej treści: wtedy najpierw
   zatrzymaj pracę i uruchom procedurę incydentową.
4. Przy nieczystym worktree nie zakładaj, że zmiany są własne. Nie używaj
   destrukcyjnych poleceń ani szerokiego stagingu.
5. Żaden krok ścieżki podstawowej nie może trenować, refitować ani wykonywać
   nowych predykcji na danych projektu. Dozwolone są testowe fity wyłącznie na
   jawnie syntetycznych danych oraz zamrożone obliczenia raportowe z OOF
   2015–2020 po niezależnym zatwierdzeniu exact allowlisty.
6. Przed audytem lub verifierem, który może otworzyć artefakt analityczny,
   zawsze obowiązuje sekwencja: przygotowanie exact allowlisty, niezależny
   review, wykonanie w kolejnej świeżej sesji. Nie wolno tworzyć lub rozszerzać
   allowlisty i używać jej w tej samej sesji. Audyt wyłącznie dokumentów może
   użyć committed exact-document scope bez osobnego data-access review, jeżeli
   jawnie wyklucza dane i artefakty analityczne.
7. Przed odpowiednią bramą artefakty 2021–2024 wolno sprawdzać wyłącznie przez
   existence check albo opaque byte-level SHA-256. Nie wolno ich deserializować,
   odczytywać schematu, liczby wierszy, wartości, rozkładów ani wyników.
8. Nie wykonuj repo-wide search ani szerokiego odczytu `data/`, `reports/` lub
   `notebooks/`, jeśli dokładne pliki i operacje nie zostały zatwierdzone.
9. Frozen artifacts i historyczne frozen specifications pozostają
   byte-identical. Korekty realizuj przez successor amendment, compatibility
   declaration lub aktualny dokument statusowy.
10. Push, merge, finalny tag/release, otwarcie bramy, wysłanie plików do APD,
    wiadomość zewnętrzna i usuwanie lokalnych artefaktów wymagają osobnej,
    jawnej decyzji autora.
11. Codex może nadać wyłącznie werdykt techniczny. Statusy autora, promotora,
    APD, JSA i dziekanatu muszą pochodzić od właściwej osoby lub systemu.
12. Po każdym kolejnym użyciu AI aktualizuj AI-use manifest i wymagane archiwum
    promptów/odpowiedzi. `AI_COMPLIANCE_READY` zawsze ma jawny cutoff i traci
    ważność po następnym użyciu AI. Po ostatniej operacji Codex autor dopisuje
    jej zapis, uruchamia committed deterministyczny validator bez AI i zamyka
    rejestr własną attestation; dalsze AI ponownie go otwiera.
13. Przed commitowaniem DOCX/PDF/prezentacji sprawdź widoczność repozytorium i
    uzyskaj osobną decyzję autora. Bez zgody na publikację commituj tylko
    niesensytywne manifesty, hashe i raporty QA, a pliki trzymaj w
    autoryzowanym prywatnym storage.

Używane statusy są rozłączne:

- `AUTHOR_SCOPE_APPROVED` i `PROMOTER_SCOPE_APPROVED` — zatwierdzono zakres,
  pytania i hipotezy, ale nie finalny tekst;
- `AUTHOR_DRAFT_COMPLETE` — autor ukończył własny draft;
- `AUTHOR_FINAL_CONTENT_APPROVED` — autor zatwierdził całą finalną treść;
- `AI_COMPLIANCE_READY` / `AI_COMPLIANCE_NOT_READY` — stan kompletności
  rejestru, archiwum i wymaganych oznaczeń użycia AI do jawnego cutoffu;
- `AI_LEDGER_CLOSED_AUTHOR_ATTESTED` — autor zamknął rejestr po ostatniej
  operacji AI i od tego czasu nie użyto AI w przygotowaniu artefaktów;
- `GATED_SPENT_ONLY` / `GATED_FULL_HOLDOUT` — terminalny wariant opcjonalnego
  rozszerzenia zamrożony przed pierwszym dostępem do chronionej treści;
- `GATED_EXTENSION_ABORTED` — udokumentowane przerwanie rozszerzenia; nie jest
  samo w sobie zgodą na użycie żadnego wyniku ani na release;
- `CODEX_TECHNICAL_READY_PASS` — kontrole techniczne przeszły;
- `PROMOTER_CONTENT_APPROVED` — promotor zaakceptował treść;
- `PROMOTER_FINAL_PDF_APPROVED` i `PROMOTER_PRESENTATION_APPROVED` — promotor
  zaakceptował dokładne pliki;
- `APD_PACKAGE_READY` / `APD_PACKAGE_NOT_READY` — wynik kontroli
  formalno-technicznej pakietu;
- `APD_SUBMITTED_CONFIRMED` — autor potwierdził skuteczne złożenie;
- `SIMILARITY_REPORT_GENERATED`, `PROMOTER_SIMILARITY_REPORT_ACCEPTED`,
  `PROMOTER_POSITIVE_GRADE_RECORDED` i `REVIEWER_POSITIVE_REVIEW_RECORDED` —
  statusy właściwego systemu/osoby, z nazwami zweryfikowanymi w Kroku 1;
- `DEFENSE_ELIGIBILITY_CONFIRMED` — dziekanat/system potwierdził wszystkie
  warunki dopuszczenia do egzaminu;
- `RELEASE_VERIFIED` — złożone pliki odpowiadają zahashowanemu release.

---

## Faza A — plan, wymagania i decyzje autora

### Krok 0. Wersjonowanie niniejszego runbooka

Ten krok jest spełniany przez osobny commit wprowadzający ten plik. Jeśli plik
jest już tracked i committed, nie twórz pustego commitu.

```text
Zweryfikuj, że docs/CODEX_REMAINING_WORK_PROMPTS.md jest śledzony przez Git i że
commit wprowadzający plan nie zawiera innych plików. Nie otwieraj danych ani
raportów. Podaj hash commitu planu, bazowy commit eksperymentu ae8ab17, nazwę
bieżącej gałęzi i stan worktree. Nie pushuj i nie merguj.
```

Warunek przejścia: runbook znajduje się w osobnym commicie, a jego hash jest
znany.

### Krok 1. Datowany snapshot aktualnych wymagań SGH

Uruchomić w świeżej sesji. Ten krok wymaga dostępu tylko do oficjalnych stron i
aktów SGH; nie dotyka danych projektu.

```text
Przygotuj wersjonowaną, datowaną macierz aktualnych wymagań SGH dla tej pracy.
Korzystaj wyłącznie z oficjalnych stron sgh.waw.pl, APD SGH i Biblioteki Aktów
Prawnych SGH. Zapisz URL, tytuł dokumentu lub aktu, datę dostępu i zakres
obowiązywania. Nie opieraj się na snippetach ani na samym lokalnym PDF-ie.

Macierz ma objąć:
- strukturę i wymagania merytoryczne pracy;
- aktualny wzór strony tytułowej, język, styl cytowań i formatowanie;
- zasady AI, wymagane disclosure i archiwizację promptów/odpowiedzi;
- APD, samodzielność, kontrolę antyplagiatową/JSA, pliki i metadane;
- obowiązkową prezentację PDF, identyfikację wizualną i egzamin;
- bieżące terminy i dokumenty przekazywane asystentowi roku.

Każdy wymóg przypisz do roli CODEX, AUTOR, PROMOTOR, RECENZENT, DZIEKANAT,
SYSTEM_APD albo SYSTEM_JSA. Oddziel wymagania obowiązkowe od rekomendacji.
Zapisz snapshot w docs/, dodaj test linków i zrób osobny commit. Nie deklaruj
spełnienia czynności osoby ani systemu na podstawie samego planu.
```

Warunek przejścia: wszystkie formalności mają źródło urzędowe i datę dostępu;
autor zna realny termin pozostawiający czas na ocenę promotora.

### Krok 2. Uzgodnienie tematu, pytań i zakresu z wykonanym badaniem

To bramka autora i promotora. Codex przygotowuje wyłącznie arkusz decyzji, nie
tworzy finalnej koncepcji pracy ani tekstu naukowego.

```text
Przygotuj decision sheet porównujący zatwierdzoną kartę tematu, konspekt,
planowane dane i obecny committed stan eksperymentu. Użyj wyłącznie wskazanych
dokumentów źródłowych i aktualnego statusu; nie otwieraj danych analitycznych.

Dla tytułu, celu, pytań, hipotez, populacji, targetu, zakresu cech, PCA, modeli,
metryk i okresów nadaj status RETAINED, NARROWED, NOT_TESTED albo EXPLORATORY.
Uwzględnij target D1–D5 z klasą dodatnią przy score >=3, PCA 4/6, rzeczywisty
backend QNN lightning.qubit, development-only OOF 2015–2020, simulator-only i
brak podstaw do twierdzenia quantum advantage. Nie przepisuj hipotez pod wynik.

Wskaż każdą rozbieżność wymagającą decyzji autora lub promotora. Zapisz arkusz
bez proponowania gotowych akapitów, interpretacji i wniosków. Zrób commit.
```

Autor musi następnie zatwierdzić finalny tytuł, cel, pytania/hipotezy i rolę
porównań statystycznych oraz wybrać dokładnie jeden wariant:

- `BASE_DEVELOPMENT_ONLY` — rekomendowany, bez otwierania 2021–2024;
- `GATED_PROTECTED_PERIOD_EXTENSION` — opcjonalny; przed pierwszym dostępem do
  chronionej treści decision sheet musi dodatkowo zamrozić dokładnie jeden
  terminalny wariant: `GATED_SPENT_ONLY` albo `GATED_FULL_HOLDOUT`.

Przy `GATED_FULL_HOLDOUT` reguła kontynuacji po 2021–2022 zależy wyłącznie od
formalnych PASS/FAIL integralności, nigdy od wielkości performance. Po poznaniu
wyniku 2021–2022 nie wolno przełączyć się na `GATED_SPENT_ONLY` dlatego, że
wynik jest korzystny albo niekorzystny. Decision sheet zapisuje uzasadnienie,
hash wariantu i regułę kontynuacji.

Promotor powinien potwierdzić wariant oraz dopuszczalny zakres AI. Codex nie
może sam zaliczyć tej bramki ani zmienić wariantu na podstawie wyniku.

Warunek przejścia: committed decision sheet ma status `AUTHOR_SCOPE_APPROVED`
i `PROMOTER_SCOPE_APPROVED`. Jawna lista nierozwiązanych decyzji oznacza, że
bramka pozostaje niezaliczona.

#### Interpretacja podziału czasowego danych

Podział okresów należy interpretować przez pryzmat danych czasowych, a nie jako prosty losowy podział train/validation/test.

**Lata 2011–2020 stanowią okres development i model selection.** Funkcję zbioru walidacyjnego pełni w nim PIT-safe temporal cross-validation z walidacyjnymi latami 2015–2020. Wyniki OOF z tych foldów służą do porównywania modeli, selekcji konfiguracji, confirmation oraz pozostałych decyzji dopuszczonych przez zamrożony kontrakt. Nie jest więc wymagane wydzielenie dodatkowego, statycznego validation set tylko po to, aby zachować klasyczny schemat train/validation/test.

**Lata 2021–2022 nie są niezależnym zbiorem walidacyjnym ani finalnym testem.** Pierwotnie były przeznaczone do zewnętrznej walidacji, jednak podczas wcześniejszego projektowania pipeline'u zostały ujawnione ich wybrane charakterystyki, m.in. statystyki targetu, cech, missingness i retencji. Z tego powodu są konserwatywnie klasyfikowane jako `design-exposed / spent development period`. Ich późniejsza ocena może służyć wyłącznie jako dodatkowy dowód czasowej stabilności zamrożonego rozwiązania i nie może uruchamiać ponownej selekcji, tuningu, zmiany cech, preprocessingu, kalibracji ani progu.

Po zamrożeniu metodologii dane z 2021–2022 mogą również wejść do historii używanej przy prerejestrowanym reficie modelu dla późniejszych punktów predykcji. Należy odróżnić taki refit zamrożonego modelu na informacjach dostępnych w danym momencie od ponownego tuningu lub zmiany metodologii.

**Lata 2023–2024 stanowią finalny temporal model-performance holdout.** Mogą zostać użyte dopiero po zamrożeniu całej procedury modelowej i przejściu odpowiednich bram dostępu. Wynik holdoutu nie może wpłynąć na wybór modelu ani metodologię. Ze względu na wcześniejsze ujawnienie wyłącznie agregatów targetu okres ten nie powinien być określany jako `fully unseen`, lecz pozostaje właściwym końcowym testem zachowania modeli na późniejszym okresie.

Dane z roku 2025 mogą być potrzebne wyłącznie jako `t+1` do konstrukcji targetu dla obserwacji z feature year 2024; rok 2025 nie stanowi osobnego feature year ani dodatkowego zbioru testowego.

W uproszczeniu:

`2011–2020: development + temporal validation → freeze → 2021–2022: secondary temporal evaluation / późniejsza historia refitu → 2023–2024: final temporal holdout`.


### Krok 3. Rejestr dotychczasowego wykorzystania AI

```text
Zbuduj audytowalny rejestr faktycznego wykorzystania AI w projekcie i pracy na
podstawie dostępnych dowodów oraz informacji autora. Dla każdej pozycji zapisz
narzędzie, wersję jeśli znana, datę lub okres, cel, obiekt wynikowy, zakres
ingerencji, sposób weryfikacji przez autora oraz lokalizację promptu i odpowiedzi,
jeśli ich gromadzenie było wymagane.

Nie rekonstruuj brakujących promptów i nie przedstawiaj szacunku jako faktu.
Oznacz luki. Potencjalne akapity, opisy wyników, interpretacje albo wnioski
wygenerowane przez AI oznacz jako BLOCKER do samodzielnego napisania od nowa
przez autora na podstawie jego wiedzy — nie parafrazuj ich ponownie przez AI.
Przygotuj tylko faktograficzny szablon sekcji o użyciu AI, który autor sam
uzupełni i zatwierdzi. Nie umieszczaj sekretów ani danych osobowych w repo.

W tym samym kroku utwórz i zacommituj wersjonowany, maszynowo czytelny schema
rejestru oraz deterministyczny offline validator, który nie wywołuje AI ani
sieci. Validator ma co najmniej sprawdzać: wymagane pola i unikalne identyfikatory,
chronologię i jawny cutoff, klasyfikację dozwolonego/niedozwolonego użycia,
istnienie i SHA-256 wymaganych archiwów prompt/odpowiedź, wskazanie obiektu
wynikowego i wymaganej etykiety disclosure, sposób weryfikacji autora, jawne
luki oraz zgodność rekordu zamknięcia z hashem walidowanej wersji rejestru.
Dodaj niesensytywne fixtures syntetyczne: co najmniej jeden przypadek poprawny
i osobne przypadki błędne dla brakującego archiwum, brakującej etykiety,
niezgodnego hasha, wpisu po cutoffie i nierozwiązanego BLOCKER-a. Testy muszą
udowodnić fail-closed behavior i stabilny kod wyjścia. Opisz dokładną komendę,
wersję schema oraz semantykę PASS/FAIL. Nie wpisuj attestation autora
automatycznie i nie projektuj samohashującego się pliku: rekord zamknięcia ma
wiązać hash uprzednio zwalidowanego, niezmiennego snapshotu rejestru.

Zrób osobny commit niesensytywnego rejestru lub jego manifestu, schema,
validatora, fixtures i testów; zapisz hash commitu oraz SHA-256 validatora.
```

Warunek przejścia: `AI_COMPLIANCE_READY` wolno nadać tylko wtedy, gdy wszystkie
wymagane, istniejące prompty/odpowiedzi są zarchiwizowane, a każda niedozwolona
treść została już samodzielnie zastąpiona przez autora i zweryfikowana. Sam plan
naprawy nie wystarcza. Brak obowiązkowego zapisu, którego nie da się odzyskać,
utrzymuje `AI_COMPLIANCE_NOT_READY` i wymaga jawnej konsultacji z promotorem w
sprawie dalszego postępowania; nie wolno go maskować rekonstrukcją. Dodatkowo
syntetyczne testy committed validatora muszą przejść, a bieżący rejestr musi
otrzymać PASS przy zerowej liczbie nierozwiązanych BLOCKER-ów; sam fakt
utworzenia schema lub skryptu nie zalicza bramki.

---

## Faza B — gotowość techniczna i pakiet dowodowy

### Krok 4. Exact allowlista audytu gotowości

Uruchomić w świeżej sesji.

```text
Przygotuj bezpieczną, wersjonowaną exact allowlistę dla read-only audytu
gotowości projektu do pracy magisterskiej. Najpierw odczytaj wyłącznie aktualną
politykę dostępu, deklaracje incydentów, wynik niezależnego review i jego
allowlistę. Nie otwieraj data/, reports/ ani notebooks/ i nie wykonuj
repo-wide search.

Allowlista ma określić dokładne pliki dokumentacji, konfiguracji, kodu i testów;
ewentualne pojedyncze artefakty development-only; dozwolone operacje; bezpieczne
verifiery; zakazane ścieżki i operacje; existence/opaque SHA-256 only dla
potencjalnie chronionych artefaktów; limit wyjścia narzędzi oraz procedurę stopu
przy nieoczekiwanej treści.

Dodaj osobną `exact_content_read_allowlist_for_review`, ograniczoną do plików
niezbędnych do oceny samej allowlisty. Reviewer nie może dziedziczyć szerszego
zakresu wykonawcy.

Nie wykonuj audytu. Dodaj test strukturalny allowlisty, zaktualizuj wyłącznie
status planu i zrób commit. Podaj hash oraz instrukcję dla niezależnego review.
```

Warunek przejścia: allowlista jest committed, test przechodzi i nie odczytano
treści analitycznej.

### Krok 5. Niezależny review allowlisty audytu

Uruchomić w innej świeżej sesji albo przez niezależnego reviewera.

```text
Wykonaj wyłącznie niezależny review committed exact allowlisty audytu
gotowości. Czytaj tylko politykę, kontrolne dokumenty incydentowe i pliki
dozwolone dla review. Nie wykonuj właściwego audytu, nie otwieraj wyników i nie
rozszerzaj allowlisty w tej sesji.

Sprawdź exact-path scope, dozwolone operacje, zakazy, boundary 2021–2024,
ochronę przed schema/row-count disclosure, ograniczenie wyszukiwania oraz stop
policy. Zapisz wersjonowany werdykt ALLOWLIST_REVIEW_PASS albo
ALLOWLIST_REVIEW_FAIL z uzasadnieniem i zrób commit niezależnie od wyniku.
```

Warunek przejścia: tylko `ALLOWLIST_REVIEW_PASS`. Po `FAIL` wróć do Kroku 4 z
nową wersją i ponów niezależny review.

### Krok 6. Read-only audyt gotowości projektu

Uruchomić w kolejnej świeżej sesji i zastosować zatwierdzoną allowlistę bez
zmian.

```text
Przeprowadź końcowy read-only audyt gotowości technicznej i naukowej materiału
projektowego. Stosuj dokładnie reviewed committed allowlistę. Nie rozszerzaj
zakresu, nie wykonuj fitu/refitu/predykcji i nie otwieraj lat 2021–2024.

Zweryfikuj:
1. PIT population, target, X_t, preprocessing, PCA i temporal CV;
2. leakage, survivorship bias, informative censoring i granice estimandu;
3. selekcję modeli, seedy, kalibrację, próg i statistical-reporting contract;
4. integralność wyników primary oraz secondary development-only;
5. poprawność porównań XGBoost, MLP, PCA controls i QNN;
6. status braków w rozdziałach, README i dokumentacji;
7. istniejący stan testów oraz reprodukowalność, bez uruchamiania testów spoza
   allowlisty;
8. brak twierdzeń o niezależnym teście, fully unseen holdoucie lub quantum
   advantage.

Nie traktuj historycznej liczby „14 failures / 305 passed / 146 subtests” jako
ważnego baseline: pochodziła z unieważnionego audytu. Raportuj wyłącznie
obserwacje z tej prawidłowej sesji. Zapisz raport BLOCKER/IMPORTANT/OPTIONAL i
werdykt BASELINE_AUDIT_PASS albo BASELINE_AUDIT_FAIL. Raport oraz boundary test
zacommituj także przy FAIL. Przy incydencie dostępu zatrzymaj pracę i zastosuj
procedurę incydentową zamiast kończyć audyt.
```

Warunek przejścia: wszystkie BLOCKER-y są faktycznie zamknięte i potwierdzone
w successor raporcie. Sam plan naprawy nie zalicza bramki. Nowe blokery wchodzą
przed dalsze kroki.

### Krok 7A. Manifest bezpieczeństwa testów

Uruchomić w świeżej sesji. W tej części nie uruchamiać testów development-only.

```text
Utwórz wersjonowany test-access manifest obejmujący każdy test i fixture, które
mogą wejść do końcowej weryfikacji. Nadaj jedną kategorię:
- synthetic/config-only;
- development-only z dokładną allowlistą wejść;
- protected/gated — niewykonywany przed właściwą bramą.

Inspekcję kodu wykonuj tylko w zatwierdzonym zakresie. Test odczytujący pełny
panel lub okres 2011–2024 nie jest automatycznie bezpieczny tylko dlatego, że
później filtruje lata. Zapisz kanoniczną komendę bezpiecznego suite oraz
egzekwowalny guard, który uniemożliwia przypadkowe uruchomienie kategorii
protected/gated.

Zapisz dokładne moduły, interpreter/owner środowiska, dozwolone wejścia,
oczekiwane operacje i katalog tymczasowy dla outputów. Zaimplementuj guard na
danych syntetycznych, ale nie uruchamiaj jeszcze development-only suite.
Dodaj węższą exact allowlistę dla reviewera. Zacommituj manifest, guard i jego
synthetic/config-only tests.
```

Warunek przejścia: test-access manifest i guard są committed.

### Krok 7B. Niezależny review test-access manifestu

Uruchomić w osobnej świeżej sesji.

```text
Wykonaj read-only, niezależny review committed test-access manifestu i guarda.
Nie uruchamiaj development-only ani protected/gated tests. Sprawdź każdy test i
fixture w dokładnie dozwolonym zakresie kodu, pełną ścieżkę odczytu danych,
interpreter, env, katalogi outputów i zachowanie przy próbie obejścia guarda.
Porównaj pokrycie manifestu z metadanymi tracked inventory `git ls-files` bez
odczytywania treści plików spoza dozwolonego zakresu.

Zapisz TEST_ACCESS_REVIEW_PASS albo FAIL z dokładną listą test IDs i zrób
commit. Nie poprawiaj manifestu i nie wykonuj suite w tej samej sesji.
```

Warunek przejścia: tylko `TEST_ACCESS_REVIEW_PASS`. Każda późniejsza zmiana
zakresu lub wejść wraca do Kroków 7A–7B.

### Krok 7C. Naprawa i wykonanie bezpiecznego suite

Uruchomić w kolejnej świeżej sesji.

```text
Stosując reviewed committed test-access manifest i guard, najpierw odtwórz
ważny baseline, a następnie napraw rzeczywiste problemy bez przepisywania
historii eksperymentu:
- zachowaj historical manifests i frozen artifacts byte-identical;
- użyj versioned supersession/compatibility declarations zamiast fałszywej
  aktualizacji starych hashy;
- usuń zależność od kolejności, globalnego stanu modułów i przecieków env;
- dodaj regresje dla naprawionych przypadków;
- uruchom najpierw testy izolowane, potem kanoniczny bezpieczny suite w
  wymaganych zamrożonych środowiskach;
- sprawdź order independence i wyjaśnij każdy skip.

Kryterium PASS to zero nieoczekiwanych failures. Celowe historyczne różnice
mają być zielonym testem supersession/compatibility, a nie „uzasadnionym
czerwonym” wynikiem. Zapisz dokładne komendy, środowiska, test IDs i wyniki.
Zrób commit również przy FAIL; nie uruchamiaj testów chronionych.

Jeśli naprawa dodała lub zmieniła test, fixture albo wejście, zacommituj zmianę
i wróć do Kroków 7A–7B przed uruchomieniem zmienionego pełnego suite. Nie
rozszerzaj manifestu i nie używaj go w tej samej sesji.
```

Warunek przejścia: kanoniczny bezpieczny suite ma `SAFE_TEST_SUITE_PASS`.
Przy `BASE_DEVELOPMENT_ONLY` przejdź do Kroku 8. Przy
`GATED_PROTECTED_PERIOD_EXTENSION` przejdź teraz do P1A, zanim powstaną package,
tekst, DOCX, prezentacja, audyt finalny lub release.

### Krok 8. Zamrożenie kontraktu primary reporting i jego allowlisty

Uruchomić w świeżej sesji. Ten krok nie otwiera wierszowych predykcji i nie
generuje raportu.

W `BASE_DEVELOPMENT_ONLY` obowiązuje wyłącznie OOF 2015–2020. Po
`SPENT_REPORT_FREEZE_PASS` z P2B albo `HOLDOUT_REPORT_FREEZE_PASS` z P6E krok
wykonuje się w `GATED_SUCCESSOR_MODE`: powstaje jawny successor kontraktu, który
może dodać tylko exact gated/frozen outputs mające odpowiedni PASS i analizy
zamrożone przed ich ujawnieniem. Output z FAIL nigdy nie może wejść do
successor allowlisty. Nie wolno dopisać nowej statystyki po wyniku ani mieszać
development, spent-development i holdout w jeden estimand.

```text
Przygotuj wersjonowany kontrakt primary thesis reporting, osobną exact allowlistę
wykonawczą oraz kod generatora, output schema, verifier i testy działające
wyłącznie na danych syntetycznych. Oprzyj projekt kontraktu na frozen
specifications, aktualnych amendments, manifestach i raporcie gotowości. W trybie
bazowym nie deserializuj realnych predykcji OOF ani artefaktów 2021–2024. W
`GATED_SUCCESSOR_MODE` na tym etapie nadal nie otwieraj wartości protected:
przypnij tylko hashe i schemas outputów P2B/P6E mających odpowiedni freeze PASS.
Nie wykonuj obliczeń wynikowych.

Dodaj węższą `exact_content_read_allowlist_for_review` dla Kroku 9 oraz jawne
operacje niezależnej reprodukcji z Kroku 10B. W allowliście wykonawczej zamroź
także exact read-only ledger-lookup operations potrzebne później w Krokach 11,
13B, 14, 15 i 20; zmiana ścieżki lub operacji wymaga successor review. Reviewer
nie może otrzymać szerszego dostępu tylko dlatego, że wykonawca będzie go
potrzebował później.

Kontrakt ma zamrozić:
1. dokładny roster reprezentantów rodzin i ich tożsamość;
2. źródłowe ścieżki i SHA-256 oraz boundary OOF 2015–2020;
3. pooled OOF average precision, historycznie nazywane PR-AUC, ROC-AUC;
4. AP każdego folda, arithmetic mean, sample SD ddof=1, minimum, porównanie z
   prevalence i seed dispersion;
5. primary 2000-replikacyjny clustered-bootstrap CI finalnego XGBoost z
   economic_group_id, seedem, regułą redraw i percentylami;
6. roczne metryki pełnego rosteru;
7. Brier score, log loss, calibration curve, parametry istniejącej kalibracji
   i metryki zamrożonego max-F1 threshold;
8. composition/retention według roku, sektora, time-t size, x_t_status,
   XBRL availability, available feature count i klasy targetu;
9. wykresy PR, ROC i calibration oraz zasady ich wizualnego QA;
10. provenance i freeze/index istniejących pakietów EDA, PCA, coarse,
    post-coarse i secondary-development, po jawnej klasyfikacji ich granicy
    okresów;
11. dokładne formuły, mianowniki, binning kalibracji, rounding, sortowanie,
    formaty, środowisko, deterministyczność i failure policy;
12. manifest wejść/wyjść, verifier i testy;
13. klasy dopuszczalnych twierdzeń i wymagane etykiety zastrzeżeń, bez
    generowania gotowych zdań do pracy.

Primary clustered CI finalnego XGBoost jest wymaganiem wcześniejszego frozen
contractu. Ewentualne nowe paired CI XGBoost vs inni finaliści lub QNN vs
XGBoost oznacz jawnie jako post-development, post-hoc/exploratory,
selection-unadjusted — nie jako prerejestrowane. Autor zamraża decyzję o ich
wykonaniu przed poznaniem nowych wartości przedziałów, ale nie wolno ukrywać, że
same wyniki modelowe są już znane. QNN vs PCA-matched controls pozostaje
porównaniem wyłącznie opisowym: kontrole są jednoseedowe, a headline QNN
trzyseedowy, więc nie twórz dla nich paired CI ani seed-matched claimu.

Zamroź również decyzję: wygenerować reporting-only agregaty FP/FN, przykłady
przypadków i porównanie kosztu czasu, czy usunąć te zapowiedzi z planu rozdziału
5. Każdą nową analizę oznacz jako reporting-only i odpowiednio exploratory; nie
dobieraj jej na podstawie wartości nowo obliczonego wyniku.

Kalibrację i próg oceniane na tych samych pooled OOF oznacz jako internal/apparent
development operating characteristics, nie niezależną ocenę generalizacji.
„Bez inferencji” rozumiej jako bez model inference/nowych predykcji; kontraktowo
dopuszczone obliczenia statystyczne z zamrożonych OOF są dozwolone.

Zamroź i zahashuj kontrakt, generator, schema, verifier, synthetic fixtures,
testy i allowlistę w jednym spójnym manifeście. Zrób commit przed pierwszym
odczytem row-level OOF. Nie wykonuj generatora na realnych wejściach.

W `BASE_DEVELOPMENT_ONLY` pakiet lub plik zawierający jakąkolwiek treść
2021–2024 pozostaje wyłącznie existence/opaque-hash provenance i nie może
dostarczyć liczby ani twierdzenia do ledgeru. W `GATED_SUCCESSOR_MODE` wyjątek
stanowią tylko exact aggregate reports P2B/P6E z odpowiednim PASS, wpisane do
reviewed successor allowlisty; cała pozostała chroniona treść nadal jest
opaque-only. Brak bezpiecznego, autoryzowanego źródła oznacza OMIT/BLOCKER, nie
zgodę na odczyt
albo automatyczne wycinanie po deserializacji.
```

Warunek przejścia: kontrakt, generator, schema, verifier, synthetic tests i
allowlista są committed i zahashowane, testy syntetyczne są green, a wszystkie
opcje raportowe rozstrzygnięto przed odczytem wyników.

### Krok 9. Niezależny review allowlisty i kontraktu reporting

Uruchomić w innej świeżej sesji albo przez niezależnego reviewera.

```text
Wykonaj niezależny review committed kontraktu primary thesis reporting i jego
exact allowlisty. Nie odczytuj wyników ani predykcji i nie uruchamiaj generatora.
Sprawdź zgodność z frozen reporting/inference contract, kompletność
obowiązkowych raportów, zamrożenie opcjonalnych decyzji, exact paths,
development-only boundary, deterministyczność i stop policy. W trybie bazowym
potwierdź brak 2021–2024. W `GATED_SUCCESSOR_MODE` potwierdź, że jedynym
dodatkiem są exact frozen aggregate reports P2B/P6E z odpowiednim PASS, bez
szerszego dziedziczenia dostępu.

Zapisz REPORTING_ALLOWLIST_REVIEW_PASS albo FAIL w osobnym wersjonowanym
raporcie i zrób commit niezależnie od wyniku. Nie poprawiaj i nie stosuj
allowlisty w tej samej sesji.
```

Warunek przejścia: tylko `REPORTING_ALLOWLIST_REVIEW_PASS`.

### Krok 10A. Wykonanie primary reporting package i evidence ledger

Uruchomić w kolejnej świeżej sesji.

```text
Wykonaj wyłącznie reviewed committed primary reporting contract na exact
allowliście. W `BASE_DEVELOPMENT_ONLY` korzystaj tylko z zamrożonych OOF
development-only 2015–2020 i nie otwieraj lat 2021–2024. W
`GATED_SUCCESSOR_MODE` successor allowlista może dodatkowo otworzyć wyłącznie
exact aggregate reports P2B/P6E z odpowiednim freeze PASS i przetworzyć je
metodami zamrożonymi przed wynikami. Nie trenuj, nie refituj, nie twórz nowych
predykcji, nie zmieniaj rosteru, kalibratora ani progu. Nie otwieraj poza successor
allowlistą row-level protected data, nie licz nowych post-result statystyk i
raportuj development, spent-development i holdout w oddzielnych sekcjach z
osobnymi ograniczeniami.

Wygeneruj wszystkie obowiązkowe tabele, figury, statystyki i jawnie zamrożone
porównania. Zbuduj jeden thesis evidence and claims ledger obejmujący EDA, PCA,
coarse, post-coarse, primary i secondary-development. Dla każdej liczby, tabeli,
figury i klasy twierdzenia zapisz definicję, mianownik, rounding, źródłowy
plik/rekord, SHA-256, zakres populacji, granicę claimu i obowiązkowe etykiety
zastrzeżeń. Nie układaj gotowych zdań. Ledger nie może zawierać narracji pracy,
opisu wyników, interpretacji ani wniosków.

W trybie bazowym do ledgeru włączaj wyłącznie exact-allowlisted treści
development-only. W `GATED_SUCCESSOR_MODE` możesz dodać exact frozen aggregate
reports P2B/P6E mające odpowiedni PASS. Wszystkie inne potencjalnie chronione
pakiety EDA/PCA/reports rejestruj tylko jako opaque-hash provenance, bez odczytu i bez
wartości pochodnych.

Każdy wynik oznacz odpowiednio: development-only, conditional-on-selection,
selection-unadjusted, internal/apparent calibration/threshold, informative
censoring oraz simulator-only. Nie używaj quantum advantage ani independent
test. Rozróżnij average precision od całki trapezowej krzywej PR.

Zweryfikuj pakiet read-only verifierem. Wygeneruj go ponownie w katalogu
tymczasowym i porównaj hashe. Obejrzyj każdą figurę. Potwierdź byte identity
wyłącznie exact-allowlisted wejść i frozen artifacts wymienionych w reviewed
contract. Jeśli brakuje wejścia, zatrzymaj się; nie pobieraj szerokiego backupu
ani nie rozszerzaj allowlisty. Zapisz raport PASS/FAIL i zrób osobny commit także
przy FAIL.
```

Warunek przejścia: execution report jest committed, wszystkie oczekiwane outputy
powstały albo failure jest jawnie zapisany. Samokontrola wykonawcy nie zamraża
jeszcze pakietu.

### Krok 10B. Niezależna weryfikacja i freeze primary package

Uruchomić w innej świeżej sesji. Stosować tę samą reviewed exact allowlistę i
nie zmieniać generatora ani outputów.

```text
Wykonaj niezależną read-only weryfikację primary thesis reporting package.
Sprawdź hashe kodu i wejść, kompletność output schema, boundary OOF 2015–2020,
wszystkie formuły/zastrzeżenia i zgodność evidence ledger z tabelami. W trybie
bazowym potwierdź brak dostępu do 2021–2024. W `GATED_SUCCESSOR_MODE` odtwórz
również tylko exact frozen aggregate reports P2B/P6E z odpowiednim PASS i z
successor allowlisty oraz potwierdź brak dostępu do pozostałej chronionej
treści. Uruchom verifier i odtwórz pakiet w nowym katalogu tymczasowym tym samym
zamrożonym generatorem;
porównaj deterministyczne output hashes. Obejrzyj każdą figurę PNG/SVG oraz
sprawdź ich zgodność liczbową.

Nie poprawiaj pakietu w sesji review. Zapisz PRIMARY_REPORTING_FREEZE_PASS albo
FAIL, manifest freeze i raport niezależny; zrób commit również przy FAIL. Przy
FAIL wróć do nowej wersji kontraktu/generatora i ponów Kroki 8–10B.
```

Warunek przejścia: `PRIMARY_REPORTING_FREEZE_PASS`, determinism check i visual
QA mają PASS, a każda liczba planowana w pracy ma źródło w ledgerze.

### Krok 11. Ujednolicenie dokumentacji technicznej i mapa poprawek pracy

```text
Ujednolić aktywną dokumentację repozytorium z finalnym zamrożonym eksperymentem.
Zakres źródeł obejmuje: aktualną politykę i status, obowiązujące konfiguracje i
amendments, raporty audytów, primary reporting package, secondary-development
freeze i thesis report oraz evidence ledger. Nie ograniczaj się tylko do
primary package. Nie otwieraj danych wierszowych. W trybie bazowym nie otwieraj
żadnej treści 2021–2024. W `GATED_SUCCESSOR_MODE` wolno odczytać tylko exact
frozen aggregate reports wskazane w reviewed successor allowliście; każdy okres
zachowuje własną etykietę.

Najpierw zapisz committed exact-document scope. Pliki raportowe mogą być
odczytane tylko wtedy, gdy zostały już zamrożone i jawnie dopuszczone do
documentation consumption przez reviewed reporting allowlistę. Potrzeba nowego
artefaktu analitycznego wymaga successor allowlisty i osobnego review; nie
rozszerzaj zakresu w tej sesji.

W README i bieżących dokumentach technicznych skoryguj co najmniej:
- target D1–D5 i score >=3 zamiast historycznego „2 z 3”;
- faktyczną PCA 4/6 zamiast planu 4/8/12;
- lightning.qubit oraz historyczny, przerwany przebieg default.qubit;
- zakończony status post-coarse, confirmation, secondary analyses i reporting;
- dodatkowy MLP jako post-coarse comparator amendment;
- common permutation i TreeSHAP amendments;
- „pooled OOF average precision (AP), historycznie raportowane jako PR-AUC”;
- development-only, brak niezależnego post-selection testu, informative
  censoring, simulator-only i brak podstaw do quantum advantage;
- predykcyjną, a nie przyczynową interpretację wyników;
- aktualne commity, manifesty, środowiska i procedurę restore z S3.

Historycznych frozen specifications nie przepisuj. Dla roboczych rozdziałów
utwórz tylko discrepancy matrix: lokalizacja, stary zapis, źródło prawdy, rodzaj
problemu i właściciel AUTOR/CODEX. Oznacz wszystkie placeholdery, w tym brak
definicji wariacyjnego klasyfikatora QNN, stare backendy i sekcje „DO
UZUPEŁNIENIA”. Nie twórz zastępczych akapitów, opisów wyników ani wniosków.

Dodatkowo sklasyfikuj stare skrypty i dokumenty jako ACTIVE, SUPERSEDED albo
LEGACY; przygotuj dependency inventory dla lokalnych dużych artefaktów przed
jakąkolwiek decyzją o usuwaniu. Nie usuwaj niczego. Odnotuj jako OPTIONAL puste
lub niepełne metadane projektu, np. pyproject, LICENSE i CITATION, jeśli nadal
występują. Uruchom bezpieczne kontrole linków i terminologii, po czym zrób
commit.
```

Warunek przejścia: aktywna dokumentacja nie przeczy źródłom prawdy, a każdy
problem tekstu pracy ma właściciela bez niedozwolonej narracji AI.

---

## Faza C — autorska treść, źródła i kontrolowana redakcja

### Krok 12. Pakiet dowodowy dla autora i samodzielne napisanie pracy

Codex przygotowuje wyłącznie materiał nawigacyjny. Następnie zatrzymuje się na
czas samodzielnego pisania przez autora.

```text
Przygotuj bezpieczny pakiet dla AUTORA, używając wyłącznie outline'u napisanego
i zatwierdzonego przez autora. Do tego outline'u zmapuj zaakceptowany scope,
evidence ledger, tabele i figury, glossary, checklistę pytań/hipotez, listę
ograniczeń, discrepancy matrix oraz listę brakujących źródeł i decyzji. Nie
twórz ani nie przebudowuj koncepcji/outline'u, akapitów, opisów wyników,
interpretacji, wniosków ani gotowych odpowiedzi na pytania badawcze. Nie
dopowiadaj wartości.

W trybie bazowym zweryfikuj, że pakiet nie zawiera wyników 2021–2024. W
`GATED_SUCCESSOR_MODE` może zawierać tylko exact frozen aggregate claims z
P2B/P6E mających odpowiedni PASS, z jednoznaczną etykietą spent-development
albo holdout i obowiązkowym disclosure; nie może zawierać row-level protected
content. Zahashuj pakiet,
zapisz test spójności i zrób commit.
```

Po tym kroku **autor samodzielnie** przygotowuje i zatwierdza:

- stronę tytułową według aktualnego wzoru;
- wstęp: uzasadnienie, przedmiot, cel, pytania/hipotezy, struktura, metoda i
  omówienie literatury;
- kompletne rozdziały teoretyczne, metodologiczny i wynikowy;
- własny opis tabel i figur, interpretację oraz dyskusję wyników;
- wnioski odpowiadające kolejno na każde pytanie i hipotezę;
- ograniczenia i zakres generalizacji;
- bibliografię, spisy tabel/rysunków i potrzebne załączniki;
- streszczenie około 900 znaków, słowa kluczowe i sekcję o użyciu AI;
- treść prezentacji: cel, metoda, najważniejsze wnioski i charakterystyka źródeł.

Brakujący Rozdział, Wstęp, Zakończenie lub opis wyniku nie może zostać
uzupełniony przez Work/Chat. Autor powinien przekazywać promotorowi iteracje i
prowadzić response matrix uwag. Status `AUTHOR_DRAFT_COMPLETE` i akceptację
treści może nadać wyłącznie autor.

### Krok 13A. Exact-document scope audytu cytowań

Uruchomić po dostarczeniu pełnego tekstu autora.

```text
Na podstawie tracked file inventory i listy źródeł dostarczonej przez autora
przygotuj exact-document/source-record scope dla audytu cytowań. Nie odczytuj
jeszcze treści rozdziałów ani źródeł. Wpisz każdy author-written DOCX/PDF,
bibliografię, exact URL/DOI/rekord wydawcy, dozwolone operacje oraz jawne
wykluczenie danych i artefaktów analitycznych. Zrób commit scope i zatrzymaj
sesję. Rozszerzenie listy wymaga nowej committed wersji przed odczytem.
```

Warunek przejścia: exact scope jest committed.

### Krok 13B. Audyt cytowań, bibliografii i praw do materiałów

Uruchomić w kolejnej świeżej sesji.

```text
Wykonaj read-only audyt cytowań i bibliografii author-written chapters. Nie
poprawiaj treści naukowej i nie dopisuj zdań. Dla każdego źródła zweryfikuj w
źródle pierwotnym albo oficjalnym rekordzie wydawcy: autora, tytuł, rok, venue,
tom/numer/strony, DOI lub stabilny URL i datę dostępu, jeśli potrzebna.

Sprawdź:
- bijekcję cytowanie–bibliografia;
- źródło dla każdego istotnego twierdzenia teoretycznego i historycznego;
- evidence-ledger source dla każdej liczby empirycznej;
- spójny, wybrany przez autora system cytowań SGH;
- licencję/atrybucję zewnętrznych tabel i grafik;
- brak cytowania AI, snippetów i zmyślonych źródeł.

Codex nie może ustalić, czy autor faktycznie przeczytał źródło. Autor składa w
citation ledger osobne oświadczenie o zapoznaniu się z każdą wykorzystaną
pozycją; brak oświadczenia pozostaje blockerem autora, nie technicznym domysłem.

Committed document scope stosuj tylko do rozdziałów i źródeł. Exact frozen
evidence ledger wolno odczytać wyłącznie przez ledger-lookup operations z
reviewed reporting allowlisty Kroku 9. Nie otwieraj jego wejść ani innych
artefaktów analitycznych.

Zapisz audit matrix z BLOCKER/IMPORTANT/OPTIONAL. Nie generuj brakującego
uzasadnienia ani interpretacji; wskaż je autorowi. Zrób commit raportu także
przy FAIL. Po poprawkach autora ponów audyt do CITATION_AUDIT_PASS.
```

Warunek przejścia: zero osieroconych cytowań/rekordów, zero nieweryfikowalnych
pozycji i wszystkie wymagane prawa/atrybucje są udokumentowane.

### Krok 14. Korekta językowa, claims review i akceptacja promotora

```text
Wykonaj redline wyłącznie author-written text w zakresie korekty językowej i
stylistycznej, spójności terminologii, formatowania cytowań oraz zgodności liczb
z evidence ledger. Nie rozszerzaj tekstu, nie twórz opisów wyników, interpretacji
ani wniosków. Brak treści zgłoś jako komentarz do autora.

Użyj committed exact-document scope z Kroku 13A. Evidence ledger może służyć
wyłącznie jako zamrożone źródło kontroli liczb poprzez exact lookup operations
zatwierdzone w reporting allowliście Kroku 9; nie otwieraj jego wejść, danych ani
nowych artefaktów analitycznych.

Przeprowadź claims review zdanie po zdaniu dla twierdzeń wynikowych, odpowiedzi
na pytania i hipotezy. Flaguj development-only boundary, AP vs PR-AUC,
conditional-on-selection, selection-unadjusted, internal/apparent calibration,
informative censoring, simulator-only, predykcyjne-vs-przyczynowe i quantum
advantage. Każdą zmianę mogącą zmienić sens pozostaw do jawnej decyzji autora.

Zapisz redline i audit report. Nie scalaj zmian merytorycznych bez akceptacji
autora. Po przyjęciu/odrzuceniu zmian zrób commit zatwierdzonej wersji.
```

Następnie autor zatwierdza kompletny tekst i konkretny hash jako
`AUTHOR_FINAL_CONTENT_APPROVED`, przekazuje go promotorowi, rozwiązuje uwagi w
response matrix i uzyskuje `PROMOTER_CONTENT_APPROVED` dla konkretnej
wersji/hasza. Codex nie może nadać żadnego z tych statusów.

---

## Faza D — dokument, prezentacja, APD i release

### Krok 15. Integracja finalnego DOCX i PDF

Uruchomić dopiero dla tekstu z `AUTHOR_FINAL_CONTENT_APPROVED` i
`PROMOTER_CONTENT_APPROVED`. Należy użyć skill `documents` i pełnego
render-and-verify workflow.

```text
Zintegruj wyłącznie author/promoter-approved treść z głównym DOCX. Nie zmieniaj
znaczenia twierdzeń i nie uzupełniaj braków merytorycznych. Użyj aktualnego
oficjalnego wzoru strony tytułowej SGH oraz wymagań potwierdzonych w Kroku 1.

Stosuj wartości potwierdzone w Kroku 1; według snapshotu 2026-08-24 są to co
najmniej: A4, wszystkie marginesy 2,5 cm, Times New Roman 12 pkt, przypisy 10
pkt, interlinia 1,5, justowanie i ciągła paginacja. Sprawdź też spis treści;
numerację i podpisy tabel/rysunków; cross-references; bibliografię; spisy;
załączniki; streszczenie; sekcję AI; kompletność przypisów. Usuń wyłącznie po
akceptacji autora komentarze i Track Changes. Nie ukrywaj nierozwiązanych uwag.

Sprawdź bijekcję AI-use manifest ↔ lokalne oznaczenie przy każdym obiekcie
stworzonym z udziałem AI, w tym wykresie, tabeli, diagramie lub innym wymagającym
ujawnienia elemencie. Zero nieoznaczonych obiektów jest warunkiem PASS.

Wyrenderuj wszystkie strony do PNG/PDF i obejrzyj każdą stronę: przepełnienia,
fonty, sieroty/wdowy, łamanie tabel, czytelność wykresów, puste strony, odwołania
i metadane. Wykonaj privacy scrub: hidden/deleted Track Changes, komentarze i
ich autorzy, custom XML/document properties, osadzone lokalne ścieżki, prywatne
linki, ukryte obiekty oraz stare wersje osadzonych plików. Sprawdź zgodność
wszystkich liczb z evidence ledger wyłącznie przez exact lookup operations z
reviewed reporting allowlisty; nie otwieraj jego wejść. Jeśli pełny render jest
niemożliwy, zwróć FAIL. Zachowaj edytowalny DOCX i finalny PDF oraz zapisz ich
SHA-256 i raport QA.
Same pliki commituj tylko po sprawdzeniu widoczności repo i osobnej zgodzie
autora; w przeciwnym razie commituj wyłącznie manifest/hash/QA.
```

Warunek przejścia: `DOCUMENT_RENDER_QA_PASS`, autor zatwierdził render, a
promotor nadał `PROMOTER_FINAL_PDF_APPROVED` dokładnemu finalnemu PDF.

### Krok 16. Prezentacja do obrony

Treść slajdów, interpretacje i wnioski dostarcza autor. Codex może wykonać skład
i kontrolę wizualną; przy użyciu skill `presentations` nie wolno mu dopisywać
treści naukowej.

```text
Złóż prezentację na podstawie wyłącznie author-written slide outline,
zatwierdzonych claims i figur z evidence ledger. Nie twórz nowych opisów,
interpretacji ani wniosków. Prezentacja ma syntetycznie pokazywać cel, metodę,
najważniejsze wnioski oraz charakterystykę wykorzystanych źródeł z uzasadnieniem
wyboru.

Zastosuj identyfikację wizualną SGH. Pierwszy slajd ma zawierać tytuł, autora,
kierunek i promotora. Nie generuj fotografii, ilustracji ani dekoracyjnych
bitmap przez AI. Używaj author-written text, zatwierdzonych wykresów oraz
technicznych diagramów według wytycznych autora; oznacz każdy obiekt stworzony
z udziałem AI zgodnie z Krokiem 1. Wyrenderuj do PDF. Stosuj parametry z
aktualnego snapshotu; według stanu 2026-08-24 prezentacja ma maksymalnie 25,0
MB. Sprawdź fonty, kontrast, czytelność wszystkich figur i zgodność każdej
liczby z ledgerem przez exact lookup operations z reviewed reporting allowlisty;
nie otwieraj wejść ledgeru. Zrób pełny visual QA, zapisz SHA-256 i raport. Plik
commituj tylko po sprawdzeniu widoczności repo i osobnej zgodzie autora; inaczej
commituj manifest/hash/QA.
```

Według snapshotu 2026-08-24 autor wykonuje próbę prezentacji mieszczącą się w
10 minutach i samodzielnie przygotowuje się do trzech pytań egzaminacyjnych;
aktualny Krok 1 ma pierwszeństwo. Warunek przejścia: autor zatwierdził plik, a
promotor nadał `PROMOTER_PRESENTATION_APPROVED` dokładnemu presentation PDF.

### Krok 17. Formalny pakiet APD — bez uploadu przez Codex

```text
Ponownie sprawdź aktualne oficjalne strony SGH i datę obowiązywania wymagań.
Przygotuj read-only checklistę APD dla dokładnych, zatwierdzonych plików. Nie
loguj się do APD, nie akceptuj oświadczeń i niczego nie wysyłaj za autora.

Sprawdź:
- identyczny tytuł i język w pracy, presentation PDF i metadanych APD;
- streszczenie i słowa kluczowe w języku pracy, identyczne z zatwierdzoną
  wersją przeznaczoną do wpisania w APD;
- finalny thesis PDF, presentation PDF i ich rozmiary zgodne z bieżącymi
  limitami;
- opcjonalne załączniki jako jeden dozwolony typ archiwum;
- decyzję autora o udostępnieniu pracy w czytelni;
- oświadczenie o samodzielności do osobistego zaakceptowania;
- dokumenty do asystenta roku i obowiązek wysłania ich z adresu SGH;
- obowiązek wysłania kompletnego zestawu do asystenta roku w tym samym dniu, w
  którym autor wgrywa pracę do APD, jeżeli aktualny snapshot nadal tak stanowi;
- bufor na analizę antyplagiatową, ocenę promotora i recenzję;
- aktualny termin indywidualny autora.

Instrukcja dla autora ma obejmować także faktyczne przekazanie wgranego rekordu
do zatwierdzenia przez opiekuna/promotora, zgodnie z aktualnym interfejsem APD.

Zapisz checklistę bez danych logowania i wrażliwych zrzutów. Podaj werdykt
APD_PACKAGE_READY albo APD_PACKAGE_NOT_READY oraz hashe sprawdzonych plików.
Zrób commit raportu, nie wykonuj uploadu.
```

Warunek przejścia: `APD_PACKAGE_READY`; nie oznacza jeszcze złożenia, akceptacji
raportu podobieństwa ani pozytywnej oceny promotora.

### Krok 18. Exact allowlista finalnego audytu release/readiness

Uruchomić w świeżej sesji.

```text
Przygotuj dokładną, wersjonowaną allowlistę końcowego read-only audytu projektu,
DOCX/PDF, prezentacji i pakietu APD. Wpisz każdy dozwolony plik i verifier.
Chronione artefakty 2021–2024 pozostaw existence/opaque SHA-256 only. Nie
wykonuj audytu, nie uruchamiaj modeli ani testów spoza safe-test manifest.
Dodaj osobną `exact_content_read_allowlist_for_review`, test strukturalny
allowlisty, zrób commit i podaj instrukcję niezależnego review.

W `GATED_SUCCESSOR_MODE` existence/opaque-only nadal dotyczy row-level inputs,
predictions i wszystkiego poza zatwierdzonym zakresem. Exact aggregate reports
zamrożone przez P2B/P6E i mające odpowiedni PASS mogą być jawnie allowlisted do
kontroli liczb w pracy;
nie wolno odziedziczyć szerszego dostępu z bram wykonawczych.
```

Warunek przejścia: committed exact allowlista i green structural test.

### Krok 19. Niezależny review allowlisty finalnego audytu

Uruchomić w osobnej świeżej sesji albo przez niezależnego reviewera.

```text
Wykonaj tylko niezależny review final-audit allowlisty. Nie wykonuj właściwego
audytu i nie otwieraj wyników. Sprawdź exact scope, bezpieczny test runner,
granice danych, dozwolone render/verifier operations, stop policy i zakaz
model fit/refit/inference. Zapisz FINAL_ALLOWLIST_REVIEW_PASS albo FAIL i zrób
commit także przy FAIL. Nie poprawiaj i nie stosuj allowlisty w tej sesji.
```

Warunek przejścia: tylko `FINAL_ALLOWLIST_REVIEW_PASS`.

### Krok 20. Finalny audyt techniczny i release candidate

Uruchomić w kolejnej świeżej sesji.

```text
Wykonaj finalny read-only audit na reviewed committed allowliście. Sprawdź:
- czysty i jednoznaczny Git state oraz pochodzenie wszystkich artefaktów;
- kanoniczny safe test suite i wszystkie read-only verifiery;
- hashe frozen artifacts, raportów i evidence ledger;
- zgodność liczb w DOCX/PDF i prezentacji ze źródłami;
- kompletność rozdziałów, cytowań, bibliografii, spisów i załączników;
- brak placeholderów, Track Changes, komentarzy, broken links i stale paths;
- aktualne disclosure AI, amendments, incydenty i ograniczenia;
- bijekcję AI-use manifest ↔ oznaczenia przy obiektach oraz zero nieoznaczonych
  obiektów wymagających disclosure;
- brak niezależnego-test/fully-unseen/quantum-advantage claims;
- render QA dokumentu i prezentacji oraz formalną checklistę APD;
- reprodukcję raportów bez treningu i różnicę między reprodukcją z klona a
  odtworzeniem wymagającym dokładnych artefaktów z S3;
- manifest source commit, środowisk, SHA-256 i procedurę restore bez pobierania
  chronionej treści podczas audytu.

Zapisz wersjonowany raport z werdyktem CODEX_TECHNICAL_READY_PASS albo FAIL.
PASS wolno wydać tylko bez blockerów technicznych. Raport zacommituj także przy
FAIL. Przy PASS utwórz immutable release-candidate manifest wiążący source
commit, DOCX, thesis PDF, presentation PDF, evidence ledger, citation audit,
AI-use manifest i test/verifier reports. Nie taguj, nie pushuj i nie deklaruj
akceptacji autora, promotora, APD ani systemu podobieństwa. Rozróżnij
`source_tree_commit` sprzed utworzenia manifestu od późniejszego
`release_manifest_commit`; manifest nie może pozornie hashować własnego commitu.
Jeśli pliki pracy nie są committed z powodów prywatności, wskaż ich
autoryzowany prywatny storage i sprawdzone SHA-256 bez ujawniania treści.

W raporcie zapisz `ai_audit_cutoff_before_this_step`. Sam Krok 20 jest kolejnym
użyciem AI i dlatego po jego zakończeniu wcześniejszy `AI_COMPLIANCE_READY` jest
prowizoryczny do czasu ręcznego domknięcia rejestru przez autora.
```

Warunek przejścia: `CODEX_TECHNICAL_READY_PASS`, clean worktree i jawne
`AUTHOR_FINAL_CONTENT_APPROVED`, `PROMOTER_CONTENT_APPROVED`,
`PROMOTER_FINAL_PDF_APPROVED`, `PROMOTER_PRESENTATION_APPROVED` oraz
`AI_COMPLIANCE_READY` do cutoffu sprzed audytu i `APD_PACKAGE_READY` dla
dokładnie tych hashy. Przed uploadem autor musi jeszcze zamknąć wpis Kroku 20.

### Krok 21. Złożenie, potwierdzenie release i przygotowanie do obrony

Autor osobiście:

1. po otrzymaniu odpowiedzi z Kroku 20 dodaje finalny prompt/odpowiedź do
   archiwum, uruchamia bez-AI validator i nadaje
   `AI_LEDGER_CLOSED_AUTHOR_ATTESTED`; po tym nie używa AI do zmiany pracy ani
   prezentacji przed złożeniem;
2. loguje się do APD i wprowadza metadane;
3. akceptuje oświadczenie o samodzielności;
4. wgrywa zatwierdzony thesis PDF, presentation PDF i ewentualne załączniki;
5. wybiera zgodę lub brak zgody na udostępnienie;
6. w tym samym dniu wysyła wymagane dokumenty z adresu SGH do asystenta roku,
   jeśli aktualna instrukcja z Kroku 1 nadal ustanawia ten termin;
7. przekazuje rekord do zatwierdzenia promotorowi i śledzi status raportu
   podobieństwa, decyzji promotora oraz recenzji;
8. potwierdza `APD_SUBMITTED_CONFIRMED`; dla pozostałych etapów dostarcza stan
   widoczny w APD, lecz źródłem statusu pozostaje właściwy system, promotor,
   recenzent lub dziekanat.

Przed dopuszczeniem do obrony właściwe źródła muszą potwierdzić: realizację
programu studiów, pozytywną ocenę promotora, przesłanie dokumentów asystentowi
roku, pozytywną ocenę recenzenta i brak zaległości finansowych. Dopiero wtedy
zapisuje się `DEFENSE_ELIGIBILITY_CONFIRMED`.

Po takim potwierdzeniu można użyć Codex tylko do technicznego domknięcia:

```text
Na podstawie potwierdzenia autora porównaj lokalne SHA-256 release candidate z
faktycznie złożonymi kopiami plików dostarczonymi przez autora. Nie loguj się do
APD i nie zapisuj danych osobowych ani zrzutów systemu. Jeśli hashe są zgodne,
utwórz finalny release manifest.

Przed tagiem, pushem, mergem albo zdalnym backupem poproś o osobną zgodę autora.
Po zgodzie utwórz jednoznaczny finalny tag wskazujący source commit i hashe
submitted thesis/presentation, zweryfikuj remote backup gałęzi i tagu oraz
dostępność instrukcji odtworzenia dużych artefaktów. Nie usuwaj lokalnych danych
ani modeli. Zapisz RELEASE_VERIFIED albo FAIL. Jest to post-submission use AI:
nie zmieniaj złożonej pracy ani prezentacji i dopisz tę operację do projektu
AI-use manifest.
```

Po tej ostatniej operacji autor ponownie uruchamia bez-AI validator i zamyka
projektowy rejestr. Każde dalsze użycie AI unieważnia jego cutoff i wymaga
ponownego domknięcia; nie ma automatycznej, samohashującej się deklaracji.

Autor przygotowuje własne wystąpienie i odpowiedzi zgodnie z aktualnym zakresem
egzaminu. Codex może uporządkować oficjalną listę zagadnień albo przeprowadzić
quiz na materiale wskazanym przez autora, lecz nie może przygotować gotowych
odpowiedzi jako substytutu wiedzy autora. Każda zmiana złożonego pliku wymaga
nowego successor release, ponownej akceptacji i właściwego ponownego uploadu.

---

## Opcjonalna ścieżka chronionych okresów 2021–2024

**Domyślna decyzja: nie wykonywać.** Ścieżka development-only jest kompletna bez
tych wyników. Otwarcie wymaga jawnej decyzji autora, rekomendowanego potwierdzenia
promotora, osobnego harmonogramu i pełnej sekwencji bram.

Nie można przejść bezpośrednio do 2023–2024. Zamrożony kontrakt wymaga kolejno:

1. `DATA_ACCESS_GATE_2021_2022_REOPEN_V1`;
2. kontrolowanej oceny spent-development 2021–2022;
3. `MODEL_EXECUTION_V1_2_SECOND_INTEGRITY_GATE`;
4. `DATA_ACCESS_GATE_2023_2024_FEATURE_APPLICATION_V1`;
5. `DATA_ACCESS_GATE_2023_2024_LABEL_REVEAL_V1`.

Są to trzy data-access gates i jedna dodatkowa integrity gate. Każda allowlista
i każda brama wymaga osobnego committed artefaktu, niezależnego review oraz
wykonania w świeżym kontekście. `FAIL` zatrzymuje dalszą chronioną część gałęzi.
Każdy podkrok przygotowania tworzy także węższą exact-content allowlistę dla
reviewera; review nie dziedziczy wykonawczego zakresu danych.
PASS bramy wyłącznie odblokowuje użycie wcześniej reviewed post-gate scope;
nie rozszerza allowlisty ani nie autoryzuje żadnej ścieżki, operacji lub outputu
niewpisanych i niezatwierdzonych przed bramą.

Przerwanie tej gałęzi wymaga committed raportu `GATED_EXTENSION_ABORTED`, który
wiąże wybrany terminalny wariant i jego hash, ostatni PASS/FAIL, wszystkie użyte
scope IDs/hashes, dokładny zakres ujawnionej treści, przyczynę i czas stopu oraz
stan ewentualnego incydentu. FAIL blokuje następną chronioną bramę, ale nie musi
blokować ukończenia całej pracy. Dopiero po zamknięciu incydentu, niezależnej
kontroli raportu przerwania i ponownym `AUTHOR_SCOPE_APPROVED` oraz
`PROMOTER_SCOPE_APPROVED` wolno wybrać jedną ścieżkę powrotu:

- `BASE_DEVELOPMENT_ONLY`: zero wartości i claims z okresów chronionych w
  package/ledger/pracy, jawne disclosure faktu i zakresu wcześniejszego dostępu
  oraz ponowienie Kroków 8–21 w trybie bazowym;
- spent-only `GATED_SUCCESSOR_MODE`: wyłącznie przy
  `SPENT_REPORT_FREEZE_PASS`, z exact zamrożonym raportem P2B, disclosure
  przerwania i ponowieniem Kroków 8–21.

`HOLDOUT_REPORT_FREEZE_PASS` jest jedyną drogą użycia wyniku holdoutu. Output z
FAIL pozostaje wykluczony. Po poznaniu performance zmiana terminalnego wariantu
nie może być motywowana wartością wyniku; uzasadnienie pozawynikowe musi być
jawne i zaakceptowane przez autora oraz promotora. Nierozwiązany incydent lub
brak ponownej akceptacji utrzymuje gałąź i release w stanie BLOCKED.

Ta sekwencja nie przywraca historycznych „old second-gate access semantics”.
`model_execution_contract_v1_2_0` został zamrożony po access amendment v1.1.0,
operacjonalizuje jego niekonfliktujące reguły i definiuje nową bramę wyłącznie
integralnościową. Obowiązuje do czasu ewentualnego jawnego successor contract;
nie wolno jej pominąć milcząco.

### P1A. Kontrakt i allowlista reopen 2021–2022

```text
Po jawnej decyzji autora/promotora przygotuj, bez otwierania chronionej treści,
successor execution/reporting contract i committed access manifest dla
DATA_ACCESS_GATE_2021_2022_REOPEN_V1. Manifest ma zawierać trzy rozłączne,
nazwane exact scopes: `spent_gate_verifier_scope` dla P1C,
`spent_post_gate_execution_scope` dla P2A oraz
`spent_post_execution_freeze_scope` dla P2B. Dla każdego zamroź exact paths,
komendy/operacje, wejścia, wyjścia, dozwolone pola i jednoznaczne zakazy.
Manifest i kontrakt muszą wiązać hash decision sheet oraz jego terminalny
wariant `GATED_SPENT_ONLY` albo `GATED_FULL_HOLDOUT`; brak lub niezgodność hasha
ma działać fail-closed.
Zamroź finalny roster, kod, środowiska, preprocessing, seedy, kalibrację, próg,
raportowanie i failure policy. Okres ma wszędzie pozostać nazwany
design-exposed/spent development i nie może aktywować strojenia ani zmian
metodologii.

Istniejący production CLI przyjmuje wyłącznie exact inputs 2011–2020, więc nie
używaj go z obejściem ścieżek. Przed gate zaimplementuj, przetestuj wyłącznie na
danych syntetycznych i zahashuj fail-closed successor runner dla całego rosteru
i wszystkich prerejestrowanych refitów 2021–2024. Runner nie może mieć
arbitrary-input option, fallbacków ani ręcznych override. W dwóch rozłącznych
trybach musi gwarantować sealed-target feature application oraz późniejszą
one-shot evaluation. Już tutaj zamroź też membership/alignment, PIT cutoffs,
logiczny output schema, serializację i reguły kompletności potrzebne w P4–P6;
po wyniku spent nie wolno ich projektować ponownie.

Przed pierwszym otwarciem zamroź także wykonywalny evaluator/report generator:
metryki, bootstrap, calibration/threshold reporting, schemas, rounding,
incident/prior-exposure disclosure, verifier i failure policy. Kod ten nie może
zostać dopisany po poznaniu wyników 2021–2022 ani labeli 2023–2024.

Przed gate nie odczytuj nowych row counts ani schema summaries. Dozwolone są
tylko specyfikacje, manifesty, existence checks, opaque SHA-256 i testy
syntetyczne. Utwórz wymagany committed gate manifest z jawnym statusem `spent`
i zakazem tuningu. Zrób commit kontraktu, runnera/evaluatora, ich hashy, exact
access manifestu, gate manifestu, gate verifiera i testów. Nie wykonuj review,
gate ani oceny w tej sesji.
```

### P1B. Niezależny review allowlisty reopen

```text
W świeżej, niezależnej sesji przejrzyj wyłącznie committed access manifest i
kontrakt DATA_ACCESS_GATE_2021_2022_REOPEN_V1. Nie otwieraj chronionej treści i
nie wykonuj gate verifiera. Osobno sprawdź `spent_gate_verifier_scope`,
`spent_post_gate_execution_scope` i `spent_post_execution_freeze_scope`, w tym
exact paths/operacje/wejścia/wyjścia, opaque-hash boundary, frozen
roster/środowiska/reporting oraz zakaz tuningu. Zapisz osobny PASS/FAIL każdego
scope'u i łączny SPENT_ACCESS_MANIFEST_REVIEW_PASS albo FAIL; zrób commit. Nie
poprawiaj ani nie stosuj żadnego scope'u w tej sesji.
```

### P1C. Wykonanie gate reopen

```text
W kolejnej świeżej sesji wykonaj wyłącznie reviewed gate verifier dla
DATA_ACCESS_GATE_2021_2022_REOPEN_V1 w granicach exact
`spent_gate_verifier_scope` z committed ID i hashem zatwierdzonym w P1B; wpisz
oba do gate report. Sam verifier sprawdza prerequisites i nie otwiera wartości,
schematów ani liczebności chronionych danych; dopiero PASS odblokowuje późniejszy
P2 w jego osobnym reviewed scope. Zapisz formalny PASS/FAIL i commit. FAIL
pozostawia 2021–2024 zamknięte.
```

### P2A. Kontrolowana ocena spent-development 2021–2022

Uruchomić w kolejnej świeżej sesji.

```text
Wyłącznie po niezależnym PASS DATA_ACCESS_GATE_2021_2022_REOPEN_V1 wykonaj
zamrożony kontrakt w granicach exact `spent_post_gate_execution_scope` z
committed ID i hashem zatwierdzonym w P1B; wpisz oba do execution report.
Wykonaj cały finalny roster bez strojenia i bez zmiany tożsamości
reprezentantów. Zastosuj prerejestrowane PIT-safe refits:
- predykcja 2021: train 2011–2019, embargo 2020;
- predykcja 2022: train 2011–2020, embargo 2021.

Każdy refit odtwarza preprocessing od zera, stosuje exact target_available_at,
zamrożone trzy seedy dla modeli stochastycznych, następnie zamrożony kalibrator
i próg. Wygeneruj predykcje i raport dokładnie raz, zahashuj je i zacommituj
dowody. Wynik zawsze opisuj jako secondary evidence from a design-exposed/spent
development period, nigdy jako independent validation. Wynik nie może zmienić
modelu, cech, kalibracji ani progu. Wartość performance nie może wpływać na
decyzję o dalszej bramie; rzeczywisty błąd integralności lub gate FAIL musi ją
zatrzymać.
```

### P2B. Niezależny freeze raportu spent-development

```text
W osobnej świeżej sesji, na reviewed allowliście, uruchom wyłącznie zamrożony w
P1A verifier w granicach exact `spent_post_execution_freeze_scope` z committed
ID i hashem zatwierdzonym w P1B; wpisz oba do freeze report. Sprawdź tożsamość
runnera/evaluatora, hashe predykcji i raportu, kompletność całego rosteru,
wykonanie exact refit schedule oraz obowiązkową etykietę
design-exposed/spent development. Nie poprawiaj outputów. Zapisz
SPENT_REPORT_FREEZE_PASS albo FAIL i commit. FAIL nie pozwala użyć raportu w
pracy ani przejść do P3A.
```

Wyłącznie przy `SPENT_REPORT_FREEZE_PASS` zastosuj terminalny wariant zamrożony
przed dostępem. Dla `GATED_SPENT_ONLY` pozostaw 2023–2024 zamknięte i wróć do
Kroku 8 w `GATED_SUCCESSOR_MODE`; wykonaj successor allowlistę, review,
package/evidence ledger i dalej Kroki 9–21. Dla `GATED_FULL_HOLDOUT` przejdź do
P3A bez nowej decyzji opartej na performance. P2B FAIL wyklucza raport i wymaga
procedury `GATED_EXTENSION_ABORTED` albo dozwolonej, wersjonowanej naprawy oraz
ponownego niezależnego freeze; nie wolno przejść do P3A ani Kroku 8 z tym
outputem.

### P3A. Allowlista drugiej bramy integralności

```text
Wyłącznie dla precommitted `GATED_FULL_HOLDOUT`, nie odczytując wartości
performance 2021–2022, przygotuj exact allowlistę i verifier dla
MODEL_EXECUTION_V1_2_SECOND_INTEGRITY_GATE. Zamroź dozwolone
identity/hash/completeness/schema-presence checks i wszystkie forbidden gate
inputs z obowiązującego kontraktu. Zrób commit i nie wykonuj review ani bramy.
```

### P3B. Niezależny review allowlisty bramy integralności

```text
W osobnej świeżej sesji przejrzyj exact allowlistę drugiej bramy integralności.
Nie uruchamiaj gate verifiera. Potwierdź, że nie może on odczytać PR-AUC, F1,
calibration, CI, progu jakości ani interpretacji 2021–2022 i że performance
magnitude nie może wpłynąć na werdykt. Zapisz INTEGRITY_ALLOWLIST_REVIEW_PASS
albo FAIL i commit. Nie stosuj allowlisty w tej sesji.
```

### P3C. Wykonanie drugiej bramy integralności

```text
W kolejnej świeżej sesji wykonaj MODEL_EXECUTION_V1_2_SECOND_INTEGRITY_GATE na
reviewed allowliście. Sprawdzaj tożsamości, kompletność statusów, hashe kodu,
rosteru, kalibracji/progu oraz existence/hash/schema-presence dozwolone przez
kontrakt dla prediction/report files 2021–2022. Potwierdź brak tuningu i dalsze
zapieczętowanie 2023–2024.

Zapisz MODEL_EXECUTION_V1_2_INTEGRITY_PASS albo FAIL i commit. FAIL utrzymuje
2023–2024 zamknięte i uruchamia właściwą wersjonowaną procedurę
integralności/incydentu.
```

### P4A. Kontrakt i allowlista ślepej aplikacji cech 2023–2024

```text
Wyłącznie po P3C PASS i przy zgodnym hashu precommitted
`GATED_FULL_HOLDOUT` przygotuj dokładny gate artifact i committed access
manifest dla DATA_ACCESS_GATE_2023_2024_FEATURE_APPLICATION_V1. Manifest ma
zawierać trzy rozłączne exact scopes: `feature_gate_verifier_scope` dla P4C,
`feature_post_gate_execution_scope` dla P5A oraz
`feature_post_execution_audit_scope` dla P5B, każdy z exact paths,
komendami/operacjami, wejściami, wyjściami, dozwolonymi polami i zakazami.
Przed gate nie ustalaj actual expected rows, liczebności ani schema summaries z
chronionych danych. Nie zamrażaj nowego evaluation/reporting contractu po wyniku
spent. Zweryfikuj i przypnij bez zmian dokładne hashe algorytmu
membership/alignment, logicznego output schema, PIT cutoffs, seedów,
serializacji, failure policy, runnera, ewaluatora i kontraktu zamrożonych w P1A.
Po wyniku 2021–2022 wolno utworzyć tylko gate-specific access manifest i gate
artifact odwołujące się do tych hashy; żadna nowa decyzja modelowa, metryczna ani
raportowa nie jest dozwolona. Actual membership/count/hash wolno ustalić dopiero
po feature gate. Utwórz wymagany committed feature-application gate manifest.
Zrób commit; nie wykonuj review ani bramy.
```

### P4B. Niezależny review allowlisty feature gate

```text
W osobnej świeżej sesji przejrzyj committed feature-gate contract i access
manifest bez otwierania chronionej treści. Osobno sprawdź
`feature_gate_verifier_scope`, `feature_post_gate_execution_scope` i
`feature_post_execution_audit_scope`, w tym exact paths/operacje/wejścia/wyjścia,
brak actual expected rows/schema diagnostics przed bramą, zapieczętowanie
targetów, PIT-refit schedule, cały roster i zakaz zmian. Zapisz osobny PASS/FAIL
każdego scope'u i łączny FEATURE_ACCESS_MANIFEST_REVIEW_PASS albo FAIL; zrób
commit. Nie poprawiaj ani nie stosuj żadnego scope'u w tej sesji.
```

### P4C. Wykonanie feature-application gate

```text
W kolejnej świeżej sesji wykonaj reviewed gate verifier dla
DATA_ACCESS_GATE_2023_2024_FEATURE_APPLICATION_V1 w granicach exact
`feature_gate_verifier_scope` z committed ID i hashem zatwierdzonym w P4B;
wpisz oba do gate report. Zapisz PASS/FAIL i commit. FAIL pozostawia cechy,
targety i wyniki 2023–2024 zamknięte. PASS odblokowuje wyłącznie osobny reviewed
scope P5A; nie wykonuj jeszcze refitów ani predykcji.
```

### P5A. Ślepe PIT-safe refity i zamrożenie predykcji 2023–2024

Uruchomić w kolejnej świeżej sesji.

```text
Wyłącznie po niezależnym PASS feature-application gate wykonaj ślepą aplikację
całego zamrożonego rosteru przy nadal zapieczętowanych targetach, ściśle w
granicach exact `feature_post_gate_execution_scope` z committed ID i hashem
zatwierdzonym w P4B; wpisz oba do execution evidence. Wymagane prerejestrowane
refity to:
- predykcja 2023: train 2011–2021, embargo 2022;
- predykcja 2024: train 2011–2022, embargo 2023; label 2023 nigdy nie jest
  training data.

To obowiązkowy prerejestrowany refit, a nie ponowne strojenie. Dla każdego roku
odtwórz preprocessing od zera i exact target_available_at. Modele stochastyczne
wykonaj na trzech zamrożonych seedach i uśrednij raw scores; dla dummy prior,
fixed-L2 logistic i probability-disabled RBF SVM zachowaj zamrożone
deterministyczne wyjątki. Następnie zastosuj zamrożony kalibrator i próg. Nie
wolno zmieniać rodzin, hiperparametrów, ansatzu, feature block, preprocessingu,
kalibracji, progu ani reporting contract.

Dopiero teraz sprawdź kompletność według zamrożonego algorytmu/schema, zapisz
actual membership metadata i hashe wszystkich predykcji. Zacommituj execution
evidence i zatrzymaj się przed label reveal. Nie wykonuj niezależnego audytu w
tej samej sesji.
```

### P5B. Niezależny audit feature-application execution

```text
W osobnej świeżej sesji wykonaj wyłącznie exact
`feature_post_execution_audit_scope` z committed ID i hashem zatwierdzonym w
P4B; wpisz oba do audit report. Zweryfikuj tożsamość całego rosteru, PIT cutoffs,
hashe kodu/środowisk, kompletność według zamrożonego schema, actual membership
manifest i wszystkie prediction hashes. Targety i ich statystyki pozostają
zapieczętowane. Nie poprawiaj predykcji. Zapisz
FEATURE_APPLICATION_EXECUTION_PASS albo FAIL i commit. FAIL zabrania przejścia
do label gate.
```

### P6A. Kontrakt i allowlista label-reveal gate

```text
Po P5B PASS przygotuj artefakt i committed access manifest dla
DATA_ACCESS_GATE_2023_2024_LABEL_REVEAL_V1. Manifest ma zawierać trzy rozłączne
exact scopes: `label_gate_verifier_scope` dla P6C,
`label_post_gate_evaluation_scope` dla P6D oraz
`label_post_evaluation_freeze_scope` dla P6E, każdy z exact paths,
komendami/operacjami, wejściami, wyjściami, dozwolonymi polami i zakazami.
Potwierdź, że wszystkie prediction hashes, evaluation/reporting contract oraz
wykonywalny evaluator, generator raportu i verifier zachowały hashe zamrożone
przed pierwszym protected-period result. Utwórz wymagany committed label-reveal
gate manifest i potwierdź, że wynik nie może wywołać zmiany. Nie otwieraj labeli,
nie wykonuj review ani bramy. Zrób commit.
```

### P6B. Niezależny review allowlisty label gate

```text
W osobnej świeżej sesji przejrzyj wyłącznie committed label-gate artifact,
contract, verifier i access manifest. Osobno sprawdź
`label_gate_verifier_scope`, `label_post_gate_evaluation_scope` i
`label_post_evaluation_freeze_scope`, w tym exact paths/operacje/wejścia/wyjścia,
kompletność prediction hashes, zakaz zmian, one-shot policy i incident
disclosure. Zapisz osobny PASS/FAIL każdego scope'u i łączny
LABEL_ACCESS_MANIFEST_REVIEW_PASS albo FAIL; zrób commit. Nie stosuj żadnego
scope'u w tej sesji.
```

### P6C. Wykonanie label-reveal gate

```text
W kolejnej świeżej sesji wykonaj reviewed verifier
DATA_ACCESS_GATE_2023_2024_LABEL_REVEAL_V1 w granicach exact
`label_gate_verifier_scope` z committed ID i hashem zatwierdzonym w P6B; wpisz
oba do gate report. Nie ujawniaj labeli przed formalnym PASS. Zapisz PASS/FAIL i
commit. FAIL utrzymuje labele zamknięte, a PASS odblokowuje wyłącznie osobny
reviewed scope P6D.
```

### P6D. Jednorazowa ocena holdoutu

Uruchomić w kolejnej świeżej sesji.

```text
Wyłącznie po P6C PASS wykonaj jednorazową ocenę dokładnie według zamrożonego
kontraktu i exact `label_post_gate_evaluation_scope` z committed ID i hashem
zatwierdzonym w P6B; wpisz oba do evaluation report. Bez względu na wynik nie
uruchamiaj reselekcji, tuningu, recalibration ani rethresholding. Raport zawsze
ujawnia wcześniejszą ekspozycję agregatów targetu i nie nazywa 2023–2024 fully
unseen. Dodaj manifest, verifier, integralność, incident disclosure i commit.
Niezależny freeze raportu wykonaj w następnej świeżej sesji; nie poprawiaj
wyniku w review.
```

### P6E. Niezależny freeze raportu holdout

```text
W osobnej świeżej sesji uruchom tylko wcześniej zamrożony verifier w granicach
exact `label_post_evaluation_freeze_scope` z committed ID i hashem zatwierdzonym
w P6B; wpisz oba do freeze report. Sprawdź prediction/label/evaluator hashes,
kompletność outputów, one-shot execution, obowiązkowe disclosure i brak zmian
metodologii. Nie poprawiaj raportu ani kodu. Zapisz HOLDOUT_REPORT_FREEZE_PASS
albo FAIL i commit. FAIL nie zezwala na użycie wyniku w pracy jako
zatwierdzonego dowodu.
```

Wyłącznie po `HOLDOUT_REPORT_FREEZE_PASS` z P6E wróć do Kroku 8 w
`GATED_SUCCESSOR_MODE`: utwórz successor reporting contract/allowlistę i ponów
review, package/evidence ledger, dokumentację, samodzielną aktualizację tekstu
przez autora, cytowania, DOCX/PDF, prezentację, APD package, finalny audyt i
release. P6E FAIL wyklucza holdout output i uruchamia procedurę
`GATED_EXTENSION_ABORTED` albo dozwoloną, wersjonowaną naprawę oraz ponowny
niezależny freeze. Stary `CODEX_TECHNICAL_READY_PASS` traci ważność po każdym
dostępie lub dodaniu nowych wyników.

---

## Zadania opcjonalne po złożeniu pracy

Nie blokują ścieżki development-only, chyba że finalny audyt wykaże bezpośrednią
zależność:

- osobny dependency audit i decyzja autora o zachowaniu lub usunięciu lokalnych
  dużych artefaktów; żadnego usuwania bez jawnej zgody i sprawdzonego backupu;
- pełne uporządkowanie ACTIVE/SUPERSEDED/LEGACY oraz archiwizacja starych
  skryptów bez przepisywania historii;
- uzupełnienie standardowego `pyproject.toml`, LICENSE i CITATION/CITATION.cff;
- publikowalny pakiet reprodukcyjny rozdzielający to, co działa z samego klona,
  od tego, co wymaga autoryzowanego restore z S3;
- rozszerzenia badawcze, QPU/noise/shots lub nowa wersja metodologii wyłącznie
  jako nowy projekt, nigdy jako post-hoc poprawa wyników tej pracy.

## Definicja ukończenia

Lista jest zakończona dopiero wtedy, gdy jednocześnie:

- projekt ma `CODEX_TECHNICAL_READY_PASS` dla dokładnego release;
- autor nadał `AUTHOR_FINAL_CONTENT_APPROVED` i samodzielnie odpowiada za całą
  narrację;
- promotor nadał `PROMOTER_FINAL_PDF_APPROVED` i
  `PROMOTER_PRESENTATION_APPROVED` dokładnym plikom;
- rejestr, archiwum i lokalne oznaczenia AI mają
  `AI_LEDGER_CLOSED_AUTHOR_ATTESTED` po ostatnim użyciu AI;
- pakiet ma `APD_PACKAGE_READY`, a autor potwierdził złożenie;
- raport podobieństwa, ocena promotora, recenzja i dopuszczenie do obrony mają
  status potwierdzony przez właściwą osobę/system;
- release i backup odpowiadają hashom złożonych plików;
- autor jest przygotowany do prezentacji i pytań w aktualnym formacie egzaminu.

Żaden pojedynczy status techniczny nie zastępuje akceptacji autora, promotora,
APD, systemu podobieństwa, recenzenta ani dziekanatu.

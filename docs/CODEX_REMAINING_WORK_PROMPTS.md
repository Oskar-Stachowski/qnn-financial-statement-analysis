# Pozostałe zadania Codex — kompletna lista promptów

Status bazowy: niezależna obsługa incydentów została zapisana w commicie
`ae8ab17` (`Resolve data access incidents after independent review`).

## Jak korzystać z listy

1. Wysyłaj prompty kolejno, po jednym.
2. Każdy prompt oznaczony jako „świeża sesja” uruchamiaj w nowej sesji Codex.
3. Nie przechodź dalej, jeśli poprzedni krok zakończył się `FAIL`, pozostawił
   nieczysty worktree albo nie utworzył oczekiwanego commitu.
4. Domyślna i rekomendowana ścieżka pracy magisterskiej kończy eksperyment na
   wynikach development-only z lat walidacyjnych 2015–2020.
5. Opcjonalnej gałęzi holdout 2023–2024 nie wolno uruchamiać automatycznie.
   Wymaga osobnej decyzji autora i najlepiej potwierdzenia promotora.
6. Żaden krok podstawowy nie może otwierać wartości, statystyk, predykcji ani
   wyników dla chronionych lat 2021–2024. Dane z późniejszych filingów mogą być
   traktowane wyłącznie zgodnie z obowiązującą polityką i bramami dostępu.
7. W przypadku nieoczekiwanego dostępu do chronionej treści Codex ma natychmiast
   zatrzymać pracę i zastosować procedurę incydentową. Nie wolno kontynuować
   „mimo wszystko”.

---

## Ścieżka podstawowa — rekomendowana

### Krok 1. Zamrożenie allowlisty audytu gotowości

Uruchomić w świeżej sesji Codex.

```text
Przygotuj bezpieczną, wersjonowaną allowlistę dla końcowego audytu gotowości
projektu do pracy magisterskiej po commicie ae8ab17. Najpierw odczytaj wyłącznie
obowiązującą politykę dostępu, deklaracje incydentów, wynik niezależnego review
i jego allowlistę. Nie otwieraj data/, reports/ ani notebooks/.

Nowa allowlista ma dokładnie określić:
- dozwolone pliki dokumentacji, konfiguracji, kodu i testów;
- dokładne, bezpieczne artefakty wyników development-only, jeśli są niezbędne;
- dozwolone read-only verifiery;
- zakazane katalogi, operacje i wyszukiwania repozytoryjne;
- zasadę existence/opaque SHA-256 only dla potencjalnie chronionych artefaktów;
- procedurę natychmiastowego stopu przy naruszeniu zakresu.

Nie wykonuj jeszcze właściwego audytu. Dodaj test strukturalny allowlisty,
zweryfikuj go, zaktualizuj dokumentację statusową i zrób osobny commit. Podaj
hash commitu oraz dokładną komendę dla kolejnego, niezależnego audytu.
```

Warunek przejścia: allowlista jest committed, test przechodzi, a żadne dane
analityczne nie zostały otwarte.

### Krok 2. Świeży audyt metodologii, wyników i dokumentacji

Uruchomić w kolejnej świeżej sesji Codex.

```text
Przeprowadź końcowy, read-only audyt gotowości projektu do napisania pracy
magisterskiej. Ściśle przestrzegaj najnowszej committed allowlisty audytu.
Nie rozszerzaj jej zakresu i nie wykonuj wyszukiwań od katalogu głównego.

Zweryfikuj:
1. spójność populacji PIT, targetu, X_t, preprocessingu, PCA i temporal CV;
2. leakage, survivorship bias, informative censoring i granice estimandu;
3. selekcję modeli, seedy, calibration/threshold i inference contract;
4. integralność głównych oraz wtórnych wyników development-only;
5. poprawność interpretacji porównań XGBoost, MLP, PCA controls i QNN;
6. zgodność rozdziałów pracy, README i dokumentacji statusowej z wykonanym
   eksperymentem;
7. stan testów i reprodukowalności;
8. brak nieuprawnionych twierdzeń o niezależnym teście lub quantum advantage.

Nie modyfikuj modeli, wyników ani metodologii i nie uruchamiaj fitu. Zapisz
wersjonowany raport audytu z klasyfikacją BLOCKER/IMPORTANT/OPTIONAL, dokładnymi
odwołaniami do plików oraz jednoznacznym werdyktem READY albo NOT_READY.
Dodaj test zapewniający, że raport respektuje boundary development-only.
Jeśli audyt przejdzie, zrób commit. Jeśli nie przejdzie, nie maskuj problemów —
podaj minimalną listę napraw w kolejności zależności.
```

Warunek przejścia: raport audytu wskazuje dokładnie, które z kolejnych kroków
są nadal potrzebne. Jeżeli wykryje nowe blokery, mają pierwszeństwo przed
poniższą listą.

### Krok 3. Primary thesis reporting package — bez trenowania

Uruchomić w świeżej sesji Codex po pozytywnym audycie albo zgodnie z jego listą
napraw.

```text
Zbuduj wersjonowany primary thesis reporting package wyłącznie z zamrożonych
predykcji OOF development-only dla lat walidacyjnych 2015–2020. Najpierw
przestrzegaj committed allowlisty i w razie potrzeby przygotuj jej wąski,
wersjonowany successor obejmujący tylko dokładne artefakty wejściowe.

Bezwzględne ograniczenia:
- bez fitu, refitu, inferencji i zmiany predykcji;
- bez otwierania lat 2021–2024;
- bez zmiany selekcji modeli, hiperparametrów, kalibratora lub progu;
- bez modyfikowania istniejących frozen artifacts.

Pakiet powinien zawierać co najmniej:
1. prerejestrowany 2000-replikacyjny clustered-bootstrap CI dla finalnego
   zwycięzcy XGBoost, z klastrem economic_group_id;
2. roczne AP i ROC-AUC finalnych reprezentantów;
3. Brier score, log loss oraz calibration curve;
4. parametry istniejącej kalibracji;
5. confusion matrix, precision, recall, specificity, F1 i predicted-positive
   share dla zamrożonego progu;
6. finalne wykresy PR, ROC i calibration;
7. jasne rozróżnienie pooled OOF average precision od całki trapezowej PR-AUC;
8. zastrzeżenia development-only, conditional-on-selection i
   selection-unadjusted;
9. manifest wejść i wyjść z SHA-256, read-only verifier i testy.

Zweryfikuj deterministyczność przez ponowne wygenerowanie pakietu w katalogu
tymczasowym i porównanie hashy. Przeprowadź wizualną kontrolę wszystkich
wykresów. Zaktualizuj dokumentację statusową i zrób commit.
```

Warunek przejścia: verifier zwraca `PASS`, wszystkie testy pakietu przechodzą,
a istniejące predykcje i frozen artifacts pozostały byte-identical.

### Krok 4. Naprawa pełnego zestawu testów i wersjonowanych freeze’ów

Uruchomić w świeżej sesji Codex.

```text
Doprowadź repozytorium do wiarygodnego stanu testowego bez przepisywania
historii eksperymentu. Najpierw upewnij się, że uruchamiane testy są synthetic-
only albo odczytują wyłącznie jawnie dozwolone konfiguracje i manifesty. Nie
uruchamiaj testu, który może otworzyć chronione dane.

Zdiagnozowany wcześniej pełny suite miał 14 failures przy 305 passed i 146
passed subtests. Większość failures wynikała z historycznych hashy po
wersjonowanych poprawkach, a trzy z zanieczyszczenia stanu modułów lub kolejności
testów.

Wymagania:
- zachowaj historyczne manifesty i frozen artifacts byte-identical;
- nie aktualizuj starych hashy tak, jakby późniejsze poprawki istniały od
  początku;
- zastosuj wersjonowane supersession/compatibility declarations;
- usuń zależność testów od kolejności i globalnego stanu modułów lub środowiska;
- dodaj regresje dla naprawionych przypadków;
- uruchom izolowane testy, potem pełny bezpieczny suite;
- rozdziel rzeczywiste błędy od celowo historycznych oczekiwań.

Zapisz raport z komendami i wynikami. Jeżeli bezpieczny pełny suite jest green,
zaktualizuj status i zrób commit. Jeśli coś pozostaje czerwone, nie deklaruj
PASS — udokumentuj dokładny blocker.
```

Warunek przejścia: bezpieczny test suite jest green albo pozostałe wyjątki są
formalnie, wersjonowanie i przekonująco uzasadnione.

### Krok 5. Ujednolicenie dokumentacji naukowej i repozytoryjnej

Uruchomić w świeżej sesji Codex. Ten krok nie może przeliczać wyników.

```text
Ujednolić dokumentację projektu i źródła rozdziałów pracy z finalnym,
zamrożonym eksperymentem. Korzystaj tylko z committed wyników audytu i primary
thesis reporting package. Nie otwieraj chronionych danych i nie uruchamiaj
modeli.

Napraw co najmniej:
- definicję targetu: pięć sygnałów D1–D5 i próg >=3, zamiast historycznej
  wersji „2 z 3”;
- faktyczną PCA 4/6 komponentów zamiast nieaktualnego planu 4/8/12 cech;
- backend kwalifikującego eksperymentu QNN: lightning.qubit, wraz z opisem
  pełnego restartu po przerwaniu default.qubit;
- status wykonania post-coarse, confirmation, secondary analyses i reporting;
- rolę dodatkowego MLP jako post-coarse comparator amendment;
- rejestr deviations/amendments, w tym poprawki common permutation i TreeSHAP;
- terminologię „pooled OOF average precision (AP), raportowane jako PR-AUC”;
- ograniczenia: development-only, brak niezależnego post-selection testu,
  informative censoring, simulator-only i brak podstaw do quantum advantage;
- różnicę między interpretacją predykcyjną a przyczynową;
- aktualne commity, manifesty, środowiska i przypisy repozytoryjne;
- wszystkie nieaktualne twierdzenia, placeholdery i sekcje „DO UZUPEŁNIENIA”.

Nie zmieniaj historycznych frozen specifications w miejscu. Stosuj następcze
dokumenty lub jasno oznaczone aktualizacje bieżących rozdziałów. Uruchom kontrole
linków i spójności pojęć. Zrób commit z listą zmienionych dokumentów.
```

Warunek przejścia: README, status projektu i źródła rozdziałów nie przeczą
konfiguracjom ani raportom.

### Krok 6. Pakiet przekazania do Work/Chat

Uruchomić w świeżej sesji Codex. Po tym kroku większość redakcji może odbywać
się w Work/Chat.

```text
Przygotuj jeden bezpieczny, samowystarczalny pakiet kontekstowy Markdown do
pisania pracy w Work/Chat. Oprzyj go wyłącznie na zatwierdzonej dokumentacji i
thesis reporting packages; nie odczytuj danych wierszowych.

Pakiet ma zawierać:
- cel pracy, pytania badawcze i hipotezy zgodne z wykonanym badaniem;
- dokładny zakres populacji, okresów i estimandu;
- skróconą metodologię PIT, targetu, cech, CV, selekcji i modeli;
- zatwierdzone główne oraz wtórne wyniki z mapowaniem do tabel i figur;
- claims matrix: co wolno, czego nie wolno i z jakim zastrzeżeniem twierdzić;
- ograniczenia i threats to validity;
- glossary symboli, nazw modeli i metryk;
- mapę rozdziałów, tabel, figur, konfiguracji i manifestów;
- listę brakujących cytowań lub decyzji redakcyjnych;
- instrukcję, że Work/Chat nie może dopowiadać nowych wyników ani wartości.

Zweryfikuj, że pakiet nie zawiera chronionych wartości ani nowych statystyk dla
lat 2021–2024. Dodaj hash i prostą kontrolę spójności, zaktualizuj status i zrób
commit.
```

Po tym kroku należy przejść do Work/Chat i przygotować finalną narrację
rozdziałów. Nie trzeba pozostawać w Codex podczas zwykłej redakcji tekstu.

### Krok 7. Integracja napisanych rozdziałów i głównego DOCX

Wykonać po zakończeniu zasadniczej redakcji w Work/Chat i umieszczeniu jej w
workspace. Uruchomić w świeżej sesji Codex.

```text
Zintegruj zatwierdzone rozdziały z głównym dokumentem pracy magisterskiej.
Użyj skill documents i wykonaj pełny render-and-verify workflow dla DOCX.

Wymagania:
- nie zmieniaj samodzielnie wyników ani znaczenia twierdzeń naukowych;
- sprawdź zgodność liczb, nazw i zastrzeżeń z committed thesis reporting
  packages oraz pakietem przekazania do Work/Chat;
- scal rozdziały, bibliografię i załączniki;
- zaktualizuj spis treści, podpisy, numerację tabel i figur, odwołania krzyżowe,
  wykazy oraz paginację;
- sprawdź styl uczelni, nagłówki, marginesy, sieroty/wdowy, łamanie tabel,
  czytelność figur i kompletność przypisów;
- wyrenderuj wszystkie strony do PNG/PDF i wykonaj wizualną kontrolę każdej
  strony;
- jeśli wymagane narzędzie renderujące jest niedostępne, nie deklaruj QA PASS —
  zgłoś dokładny brak środowiskowy;
- zachowaj edytowalny DOCX oraz finalny PDF i zrób commit.

Na końcu podaj listę wszystkich automatycznych zmian redakcyjnych i wszystkich
punktów wymagających decyzji autora.
```

Warunek przejścia: kompletny DOCX i PDF są spójne, wyrenderowane i wizualnie
zweryfikowane.

### Krok 8. Końcowy audyt reprodukowalności i gotowości pracy

Uruchomić w ostatniej świeżej sesji Codex.

```text
Wykonaj końcowy read-only audyt release/readiness całego projektu i pracy
magisterskiej. Najpierw zamroź dokładną allowlistę tego audytu. Nie otwieraj
chronionych danych ani nie uruchamiaj nowych modeli.

Sprawdź:
- czysty worktree i jednoznaczne commity źródłowe;
- wszystkie bezpieczne testy i read-only verifiery;
- hashe frozen artifacts i thesis reporting packages;
- zgodność liczb w DOCX/PDF z tabelami źródłowymi;
- kompletność rozdziałów, tabel, figur, bibliografii i załączników;
- brak placeholderów, zerwanych linków, nieaktualnych ścieżek i sprzecznych
  deklaracji;
- poprawne disclosure metodologii, amendments, incydentów, ograniczeń i użycia
  AI;
- brak twierdzeń o niezależnym holdoucie lub quantum advantage;
- możliwość odtworzenia raportów bez refitu modeli;
- instrukcję dostępu/odtworzenia dużych artefaktów z S3 bez ich pobierania.

Zapisz wersjonowany raport końcowy z werdyktem THESIS_READY_PASS albo
THESIS_READY_FAIL. PASS wolno wydać wyłącznie, jeśli nie ma nierozwiązanych
blockerów. Jeżeli jest PASS, zrób finalny commit i podaj krótką checklistę
rzeczy pozostających wyłącznie po stronie autora/promotora.
```

---

## Opcjonalna gałąź — holdout 2023–2024

**Nie wykonywać**, jeżeli praca ma pozostać uczciwie opisana jako
development-only. Holdout nie jest wymagany do ukończenia rekomendowanej
ścieżki.

Gałąź może zostać uruchomiona wyłącznie wtedy, gdy autor świadomie chce
wzmocnić wniosek o generalizacji temporalnej i akceptuje dodatkowy koszt,
ryzyko oraz obowiązek ujawnienia wcześniejszych ekspozycji i incydentów.

### H1. Zamrożenie kompletnego kontraktu holdout

```text
Nie otwierając żadnych wartości dla lat 2021–2024, przygotuj i zamroź kompletny
kontrakt opcjonalnej oceny holdout 2023–2024. Zweryfikuj formalne zamknięcie
incydentów. Zamroź model, środowisko, preprocessing, alignment, expected rows,
prediction schema, calibration, threshold, metryki, bootstrap, reporting,
failure policy i trzy wymagane access gates. Dodaj manifesty SHA-256, testy
syntetyczne i niezależny gate verifier. Nie wykonuj feature application ani
label reveal. Zrób commit.
```

### H2. Ślepa aplikacja cech i zamrożenie predykcji

```text
Po niezależnym PASS bramy DATA_ACCESS_GATE_2023_2024_FEATURE_APPLICATION_V1
wykonaj wyłącznie ślepą aplikację finalnego zamrożonego pipeline’u do cech
holdout. Targety i ich statystyki muszą pozostać zapieczętowane. Nie wolno
stroić, refitować, zmieniać preprocessingu, kalibracji ani progu. Zweryfikuj
alignment i kompletność wyłącznie zgodnie z kontraktem, zapisz predykcje,
zahashuj je i wykonaj niezależny audit execution. Zatrzymaj się przed label
reveal i zrób commit dowodowy.
```

### H3. Jednorazowe ujawnienie labeli i ocena

```text
Po potwierdzeniu hashy wszystkich wymaganych predykcji i niezależnym PASS bramy
DATA_ACCESS_GATE_2023_2024_LABEL_REVEAL_V1 wykonaj jednorazową ocenę holdout
według zamrożonego kontraktu. Nie zmieniaj żadnego elementu modelu ani
raportowania na podstawie wyniku. Wygeneruj pełny raport z disclosure wcześniejszej
ekspozycji agregatów i incydentów; nie nazywaj okresu „fully unseen”. Dodaj
manifest, verifier, testy integralności i commit. Bez względu na wynik nie
uruchamiaj ponownej selekcji ani strojenia.
```

Po wykonaniu H1–H3 trzeba powtórzyć kroki 5–8 ścieżki podstawowej, aby
dokumentacja i praca uwzględniały nową, ograniczoną ocenę temporalną.

---

## Co nie jest obecnie rekomendowane

- nowe strojenie lub ponowny coarse search;
- ponowne wykonanie QNN confirmation lub secondary analyses;
- eksperymenty na QPU, shots albo noise dodane wyłącznie post hoc;
- zmiana targetu po poznaniu wyników;
- przedstawianie wyników OOF jako niezależnego testu;
- pobieranie wszystkich artefaktów z S3, jeśli verifiery mogą działać na
  istniejących lokalnych manifestach i wymaganych małych plikach.

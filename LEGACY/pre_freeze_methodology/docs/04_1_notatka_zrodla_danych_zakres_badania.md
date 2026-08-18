# Notatka do rozdzialu 4.1. Zrodla danych i zakres badania

## Cel notatki

Niniejsza notatka zbiera informacje z repozytorium potrzebne do napisania podrozdzialu **4.1. Zrodla danych i zakres badania** pracy magisterskiej pt. *Zastosowanie hybrydowych kwantowych sieci neuronowych do klasyfikacji ryzyka finansowo-sprawozdawczego spolek publicznych na podstawie danych z systemu SEC EDGAR*.

Notatka ma charakter roboczy. Oddziela:

- fakty wynikajace bezposrednio z kodu, konfiguracji i raportow w repozytorium,
- decyzje metodologiczne, ktore nalezy opisac w pracy,
- ograniczenia zakresu badania,
- elementy, ktore nalezy podeprzec zrodlami bibliograficznymi.

Glowny wniosek: podrozdzial 4.1 mozna napisac na podstawie aktualnego repozytorium w sposob dosc precyzyjny, poniewaz proces pozyskania i selekcji danych jest juz udokumentowany skryptami, konfiguracja i raportami jakosci. W rozdziale 4.1 nalezy jednak unikac opisywania zbioru jako finalnego zbioru modelowego, poniewaz obecny etap repozytorium dotyczy przede wszystkim zrodel, zakresu, parsowania i przygotowania danych wejściowych do dalszych eksperymentow.

## Proponowana funkcja podrozdzialu 4.1

Podrozdzial 4.1 powinien odpowiedziec na pytania:

1. Z jakich zrodel pochodza dane?
2. Dlaczego wybrano dane SEC EDGAR / Company Facts?
3. Jak zdefiniowano populacje badanych spolek?
4. Jaki jest zakres czasowy, formularzowy, walutowy i sektorowy badania?
5. Jakie dane finansowe sa pobierane z XBRL?
6. Jakie ograniczenia wynikaja z przyjetego zrodla i zakresu danych?

Nie trzeba w 4.1 szczegolowo opisywac konstrukcji wskaznikow finansowych, targetu, imputacji, skalowania, selekcji cech ani konfiguracji modeli. Te elementy naleza raczej do 4.2-4.5. W 4.1 wystarczy pokazac, ze dane zrodlowe i probka badawcza sa zdefiniowane w sposob odtwarzalny.

## Glowne zrodla danych

### SEC EDGAR jako zrodlo pierwotne

Podstawowym zrodlem danych jest system **SEC EDGAR** oraz udostepniane przez SEC pliki i interfejsy API. W repozytorium wykorzystywane sa trzy typy zasobow SEC:

1. `company_tickers.json` - mapa tickerow, nazw spolek i numerow CIK.
2. `submissions` API - metadane emitenta, w tym nazwa, typ jednostki, SIC, opis SIC, koniec roku obrotowego, tickery i gieldy.
3. `companyfacts` API - dane XBRL dla poszczegolnych spolek, uzywane do pozyskania pozycji finansowych.

Odpowiadajace skrypty:

- `src/data/01_download_sec_ticker_map.py`,
- `src/data/02_download_sec_company_metadata.py`,
- `src/data/download_sec.py`,
- `src/data/06_parse_companyfacts.py`.

### Dlaczego SEC Company Facts

W pracy mozna uzasadnic wybor SEC Company Facts nastepujaco:

- jest to oficjalne, publicznie dostepne zrodlo danych dla emitentow raportujacych do SEC,
- dane sa standaryzowane w formacie XBRL, co pozwala mapowac pozycje sprawozdawcze na zmienne liczbowe,
- dane obejmuja wieloletnia historie sprawozdan, co umozliwia budowe panelu typu `company-year`,
- dane sa odpowiednie do problemu klasyfikacyjnego opartego na wskaznikach finansowych,
- Company Facts pozwala uniknac recznego parsowania raportow 10-K w formacie tekstowym lub HTML.

Wazne ograniczenie do opisania: standaryzacja XBRL nie oznacza pelnej jednolitosci danych. Spolki moga uzywac roznych tagow dla podobnych pozycji, raportowac dane z rozna szczegolowoscia, miec rozne konce roku obrotowego i rozne profile dzialalnosci. Dlatego repo zawiera osobna konfiguracje mapowania tagow i kontrole jakosci.

## Pipeline danych w repozytorium

### Krok 1: mapa ticker-CIK

Skrypt `src/data/01_download_sec_ticker_map.py` pobiera plik:

```text
https://www.sec.gov/files/company_tickers.json
```

Wyniki:

- `data/raw/sec_company_tickers.json`,
- `data/interim/sec_ticker_cik_map.csv`,
- `data/interim/sec_unique_ciks.csv`.

Zastosowanie w badaniu:

- CIK jest podstawowym identyfikatorem SEC,
- ticker jest traktowany jako pomocniczy identyfikator rynkowy,
- ta tabela tworzy punkt startowy do pobierania metadanych emitentow.

### Krok 2: metadane emitentow z SEC submissions

Skrypt `src/data/02_download_sec_company_metadata.py` pobiera metadane dla unikalnych CIK z endpointu:

```text
https://data.sec.gov/submissions/CIK{cik10}.json
```

Wynik:

- `data/raw/sec_submissions/CIK{cik10}.json`,
- `data/interim/sec_company_metadata.csv`.

Najwazniejsze pola z punktu widzenia 4.1:

- `cik`, `cik10`,
- `name_from_sec`,
- `entity_type`,
- `sic`,
- `sic_description`,
- `fiscal_year_end`,
- `tickers`,
- `exchanges`.

Metadane sa wykorzystywane do klasyfikacji spolek i budowy zakresu badania.

### Krok 3: klasyfikacja wedlug SIC

Skrypt `src/data/03_classify_sec_companies_by_sic.py` przypisuje spolkom uproszczone kategorie badawcze na podstawie:

- kodu SIC,
- opisu SIC,
- typu jednostki,
- nazwy emitenta,
- regul wykluczajacych SPAC, REIT, fundusze, ETF, trusty, financials i utilities.

Wynik:

- `data/interim/sec_company_classified.csv`.

Wazna decyzja metodologiczna: klasyfikacja nie jest gotowym sektorem rynkowym typu GICS/NAICS, lecz autorska klasyfikacja badawcza oparta na SIC i regulach filtracji. W pracy nalezy jasno napisac, ze SIC sluzy do zdefiniowania zakresu proby, a nie do pelnej analizy sektorowej.

### Krok 4: budowa research universe

Skrypt `src/data/04_build_research_universe.py` tworzy probke spolek objetych badaniem.

Wyniki:

- `data/processed/research_universe.csv`,
- `data/processed/research_universe_excluded.csv`,
- `data/processed/research_universe_summary.csv`.

Aktualny research universe:

| Miara | Wartosc |
|---|---:|
| Liczba rekordow wejsciowych po klasyfikacji | 7 993 |
| Liczba spolek w research universe | 3 730 |
| Liczba unikalnych CIK w research universe | 3 730 |
| Liczba unikalnych glownych tickerow | 3 720 |
| Brak glownego tickera | 10 |
| Brak glownej gieldy po normalizacji | 22 |

Struktura wedlug etykiety badawczej:

| Research sector | Liczba spolek |
|---|---:|
| Industrials_Manufacturing | 1 677 |
| Extended_Candidate | 1 091 |
| Technology | 735 |
| Retail | 227 |

Struktura wedlug glownej grupy SIC:

| SIC major group | Liczba spolek |
|---|---:|
| Manufacturing | 1 979 |
| Services | 937 |
| Mining | 238 |
| Retail_Trade | 231 |
| Transportation_Communications_Utilities | 171 |
| Wholesale_Trade | 109 |
| Construction | 65 |

Struktura wedlug glownej gieldy:

| Primary exchange | Liczba spolek |
|---|---:|
| Nasdaq | 1 901 |
| NYSE | 1 147 |
| OTC | 660 |
| Brak / nieustalone | 22 |

Glowne powody wykluczenia z research universe:

| Powod wykluczenia | Liczba |
|---|---:|
| non_operating_entity_type | 1 562 |
| missing_sic | 1 069 |
| financials_insurance_real_estate_excluded | 735 |
| spac_or_blank_check_company | 321 |
| reit_excluded | 201 |
| fund_etf_or_trust_excluded | 196 |
| utilities_excluded | 142 |
| out_of_scope_sector | 37 |

Interpretacja do pracy: badanie nie obejmuje calej populacji emitentow SEC. Obejmuje wyselekcjonowana probe spolek operacyjnych, z naciskiem na sektory niefinansowe i nieuzytecznosci publicznej, dla ktorych klasyczne wskazniki finansowe sa bardziej porownywalne.

### Krok 5: pobranie Company Facts

Skrypt `src/data/download_sec.py` pobiera pliki Company Facts z endpointu:

```text
https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json
```

Wynik:

- `data/raw/companyfacts/CIK{cik10}.json`.

Wedlug raportu `data/reports/xbrl_parse_quality_report.md`:

| Miara | Wartosc |
|---|---:|
| Spolki w research universe | 3 730 |
| Znalezione pliki Company Facts | 3 712 |
| Sparsowane pliki Company Facts | 3 712 |
| Brakujace pliki Company Facts | 18 |
| Bledy parsowania JSON | 0 |

Interpretacja do pracy: niemal wszystkie spolki z research universe maja dostepne dane Company Facts. Brak 18 plikow dotyczy ok. 0,48% research universe i jest ograniczeniem proby, ale nie zmienia zasadniczo jej skali.

### Krok 6: mapowanie XBRL na zmienne finansowe

Mapowanie tagow znajduje sie w:

- `configs/sec_tags.yaml`.

Skrypt parsujacy:

- `src/data/06_parse_companyfacts.py`.

Wyniki:

- `data/interim/sec_facts_long.csv`,
- `data/interim/sec_facts_wide.csv`,
- `data/reports/xbrl_variable_coverage.csv`,
- `data/reports/xbrl_tag_usage.csv`,
- `data/reports/xbrl_missing_by_company.csv`,
- `data/reports/xbrl_parse_quality_report.md`.

Zmienna finansowa jest definiowana przez zestaw tagow XBRL w przestrzeni `us-gaap`. Repo odrzuca dane IFRS na etapie mapowania, poniewaz konfiguracja obejmuje tagi `us-gaap`. Akceptowana jednostka to `USD`, a akceptowany formularz to `10-K`.

Aktualnie skonfigurowano 27 zmiennych finansowych:

- aktywa, zobowiazania, suma zobowiazan i kapitalu,
- aktywa i zobowiazania biezace,
- przychody,
- wynik netto,
- kapital wlasny,
- gotowka,
- naleznosci,
- zapasy,
- koszt przychodow,
- koszty operacyjne,
- rzeczowe aktywa trwale,
- wartosci niematerialne,
- goodwill,
- amortyzacja,
- inwestycje dlugoterminowe,
- dlug dlugoterminowy i krotkoterminowy,
- EBIT / operating income,
- koszty odsetkowe,
- CAPEX,
- zyski zatrzymane,
- przeplywy pieniezne z dzialalnosci operacyjnej, inwestycyjnej i finansowej.

W pracy nie trzeba wypisywac wszystkich tagow XBRL, ale warto podac, ze szczegolowe mapowanie znajduje sie w konfiguracji projektu i ze zmienne sa tworzone z tagow `us-gaap`.

### Krok 7: kontrole jakosci danych

Skrypt `src/data/07_sanity_check_sec_facts.py` wykonuje techniczne kontrole jakosci i generuje:

- `data/reports/sec_facts_sanity_warnings.csv`,
- `data/reports/sec_facts_sanity_summary.csv`.

Kontrole obejmuja m.in.:

- zgodnosc postaci danych liczbowych,
- zgodnosc formularzy i jednostek z konfiguracja,
- duplikaty `company-year-variable`,
- roczne okresy dla zmiennych przeplywowych,
- nadmierne opoznienie daty zlozenia wzgledem konca okresu,
- niespojnosci bilansowe,
- wartosci ujemne tam, gdzie sa nietypowe lub niedopuszczalne,
- skrajne relacje wyniku netto do przychodow lub aktywow,
- braki podstawowych zmiennych w wiekszosci lat dla danej spolki.

Najwazniejsze ostrzezenia z raportu:

| Poziom | Check | Liczba ostrzezen | Liczba spolek |
|---|---|---:|---:|
| high | liabilities_absurdly_above_assets | 258 | 127 |
| high | liabilities_and_equity_negative | 8 | 8 |
| medium | net_loss_abs_large_relative_to_revenues | 3 951 | 1 088 |
| medium | net_loss_abs_large_relative_to_assets | 3 255 | 911 |
| medium | revenues_missing_for_majority_of_years | 327 | 327 |
| medium | net_profit_large_relative_to_revenues | 196 | 157 |
| medium | net_profit_large_relative_to_assets | 150 | 118 |

Do 4.1 wystarczy opisac, ze dane zostaly objete walidacja techniczna i ze ostrzezenia nie sa automatyczna interpretacja ekonomiczna. Szczegolowa polityka wykluczen nalezy raczej do 4.2.

## Zakres czasowy badania

Zakres czasowy jest okreslony w `configs/dataset_config.yaml`:

```yaml
dataset:
  start_year: 2011
  end_year: 2025
target:
  horizon_years: 1
splits:
  train_end_year: 2020
  validation_years:
    - 2021
    - 2022
  test_years:
    - 2023
    - 2024
```

Interpretacja:

- zrodla Company Facts sa parsowane dla lat 2011-2025,
- lata 2011-2024 sa docelowo latami cech / obserwacji `company-year`,
- rok 2025 jest potrzebny jako okres `t+1` do konstrukcji etykiety dla obserwacji z roku 2024,
- podzial modelowy ma charakter czasowy: train do 2020, validation 2021-2022, test 2023-2024.

W 4.1 nalezy napisac glownie o zakresie 2011-2025 jako zakresie zrodlowym oraz wyjasnic, ze ostatni rok jest wykorzystywany ze wzgledu na horyzont predykcyjny. Szczegoly konstrukcji targetu i podzialu train-validation-test powinny znalezc sie w dalszych podrozdzialach.

## Zakres formularzy i jednostek

Zgodnie z konfiguracja i parserem:

- wykorzystywane sa formularze `10-K`,
- akceptowana jednostka dla faktow finansowych to `USD`,
- parser pracuje na rocznych danych sprawozdawczych,
- dla zmiennych przeplywowych wymagany jest okres od 300 do 400 dni,
- dane kwartalne i nie-roczne sa odrzucane.

Uzasadnienie do pracy:

- formularz 10-K jest rocznym raportem spolek publicznych skladanym do SEC,
- roczne dane sa bardziej adekwatne do oceny kondycji finansowej i porownan miedzy spolkami niz dane kwartalne,
- ograniczenie do USD upraszcza porownywalnosc i eliminuje problem przeliczen walutowych,
- ograniczenie do `10-K` i annual facts zmniejsza ryzyko mieszania okresow kwartalnych z rocznymi.

## Zakres populacji i proby badawczej

Badanie obejmuje spolki publiczne obecne w danych SEC, ale po filtrach:

- tylko spolki sklasyfikowane jako jednostki operacyjne,
- tylko spolki z dostepnym i poprawnym SIC,
- wykluczone sa spolki finansowe, ubezpieczeniowe, nieruchomosciowe, banki i utilities,
- wykluczone sa SPAC / blank check companies,
- wykluczone sa REIT,
- wykluczone sa fundusze, ETF i trusty,
- pozostaja sektory: Technology, Retail, Industrials_Manufacturing i Extended_Candidate.

Uzasadnienie metodologiczne:

- instytucje finansowe i utilities maja specyficzne modele bilansowe, regulacyjne i kapitalowe,
- klasyczne wskazniki finansowe, takie jak zadluzenie do aktywow, current ratio, kapital obrotowy do aktywow czy asset turnover, sa trudniej porownywalne miedzy bankami, ubezpieczycielami, utilities i spolkami przemyslowymi/uslugowymi,
- SPAC, fundusze, ETF, trusty i REIT nie sa typowymi spolkami operacyjnymi w sensie analizy wynikow operacyjnych i kondycji finansowej.

Do bibliografii nalezy podeprzec ogolne stwierdzenie, ze sektory finansowe i utilities wymagaja odrebnego traktowania w analizie wskaznikowej i modelowaniu ryzyka finansowego. Same liczby proby wynikaja z repozytorium i nie wymagaja bibliografii zewnetrznej, ale w pracy warto wskazac pliki projektu jako material badawczy / zalacznik.

## Zakres zmiennych finansowych

Zmienne z Company Facts sa najpierw mapowane na szeroki zestaw pozycji sprawozdawczych. W 4.1 warto opisac je grupowo, nie jako pelny katalog techniczny:

1. Pozycje bilansowe:
   - aktywa,
   - zobowiazania,
   - kapital wlasny,
   - aktywa i zobowiazania krotkoterminowe,
   - gotowka,
   - naleznosci,
   - zapasy,
   - rzeczowe aktywa trwale,
   - wartosci niematerialne,
   - goodwill,
   - dlug krotko- i dlugoterminowy.

2. Pozycje rachunku wynikow:
   - przychody,
   - wynik netto,
   - EBIT / wynik operacyjny,
   - koszt przychodow,
   - koszty operacyjne,
   - koszty odsetkowe,
   - amortyzacja.

3. Pozycje przeplywow pienieznych:
   - przeplywy operacyjne,
   - przeplywy inwestycyjne,
   - przeplywy finansowe,
   - CAPEX.

4. Pozycje dodatkowe:
   - zyski zatrzymane,
   - inwestycje dlugoterminowe.

## Pokrycie danych

Wedlug `data/reports/xbrl_variable_coverage.csv` i notatki metodologicznej `docs/04_metodologia_wskazniki_trendy_target.md`, najlepsze pokrycie maja podstawowe pozycje bilansowe i rachunku przeplywow.

Najwyzsze pokrycie `company-year`:

| Zmienna | Pokrycie company-year |
|---|---:|
| assets | 99,7% |
| liabilities_and_equity | 99,6% |
| liabilities | 99,5% |
| operating_cash_flow | 99,1% |
| equity | 99,0% |
| cash | 98,9% |
| net_income | 97,8% |
| financing_cash_flow | 97,8% |
| retained_earnings | 97,6% |
| current_assets | 97,2% |
| current_liabilities | 96,8% |
| investing_cash_flow | 93,3% |
| ebit | 91,0% |
| revenues | 88,0% |

Zmienne o srednim lub niskim pokryciu:

| Zmienna | Pokrycie company-year | Komentarz |
|---|---:|---|
| accounts_receivable | 78,9% | przydatne, ale wymaga kontroli brakow |
| depreciation_amortization | 73,6% | przydatne do wskaznikow dodatkowych |
| cost_of_revenue | 63,6% | zalezne od profilu dzialalnosci i tagowania |
| intangible_assets | 63,1% | nie dotyczy wszystkich spolek |
| inventory | 59,2% | mocno sektorowe |
| interest_expense | 59,0% | zalezne od struktury finansowania |
| goodwill | 58,1% | nie dotyczy wszystkich spolek |
| long_term_debt | 56,2% | nizsze pokrycie |
| short_term_debt | 53,2% | nizsze pokrycie |
| long_term_investments | 6,3% | bardzo niskie pokrycie, raczej poza rdzeniem badania |

Interpretacja do pracy:

- rdzen badania moze opierac sie na dobrze pokrytych pozycjach finansowych,
- zmienne o nizszym pokryciu powinny byc traktowane ostroznie, jako kandydaci do cech dodatkowych albo analiz pomocniczych,
- niskie pokrycie nie zawsze oznacza blad danych; czesto wynika z tego, ze dana pozycja nie wystepuje w bilansie danego typu spolek albo jest raportowana innym tagiem.

## Dane wyjsciowe po parsowaniu XBRL

Wedlug `data/reports/xbrl_parse_quality_report.md`:

| Miara | Wartosc |
|---|---:|
| Wybrane roczne fakty kandydackie | 897 920 |
| Wiersze w formacie dlugim | 799 171 |
| Wiersze w formacie szerokim | 36 664 |
| Liczba raportowanych zmiennych coverage | 27 |
| Liczba wierszy tag usage | 61 |
| Liczba wierszy missing-by-company | 3 730 |

Format dlugi (`sec_facts_long.csv`) zachowuje metadane zrodlowe faktow: `form`, `fp`, `filed`, `accn`, `frame`, `start`, `end`, `fy`, `namespace`, `tag`, `unit`.

Format szeroki (`sec_facts_wide.csv`) jest baza do dalszego przygotowania datasetu modelowego, gdzie jeden wiersz odpowiada obserwacji `company-year`.

## Decyzje metodologiczne do opisania w 4.1

### Jednostka obserwacji

Docelowa jednostka obserwacji to **spolka-rok** (`company-year`). W 4.1 mozna to zaznaczyc, ale szczegoly konstrukcji cech i targetu zostawic do 4.2.

### Oficjalne dane liczbowe, bez danych tekstowych

Zakres badania ogranicza sie do liczbowych danych finansowych z XBRL. Repozytorium nie wykorzystuje:

- pelnego tekstu raportow 10-K,
- not objasniajacych jako tekstu,
- informacji z Management Discussion and Analysis,
- komunikatow prasowych,
- cen akcji,
- kapitalizacji rynkowej,
- danych makroekonomicznych,
- danych o faktycznych bankructwach,
- danych o postepowaniach SEC / AAER jako twardych etykietach fraudu.

To ograniczenie jest wazne, poniewaz temat pracy dotyczy klasyfikacji ryzyka finansowo-sprawozdawczego na podstawie danych liczbowych. W rozdziale 4.1 trzeba jasno napisac, ze badanie nie jest pelna analiza fundamentalna ani pelna detekcja oszustw finansowych.

### Dane roczne zamiast kwartalnych

Parser odrzuca dane kwartalne i nie-roczne. W 4.1 warto uzasadnic to tym, ze:

- raporty roczne sa bardziej kompletne,
- badanie dotyczy kondycji finansowej w horyzoncie rocznym,
- QNN i klasyczne modele beda porownywane na jednolitej strukturze `company-year`,
- mieszanie danych kwartalnych i rocznych mogloby prowadzic do nieporownywalnosci wartosci przeplywowych.

### Wylaczenie sektorow specyficznych

Wylaczenie financials, insurance, real estate, banks i utilities trzeba uzasadnic nie tylko technicznie, ale tez merytorycznie:

- banki i instytucje finansowe maja specyficzna strukture aktywow i pasywow,
- utilities dzialaja w silnie regulowanym modelu kapitalochlonnym,
- REIT i fundusze nie sa typowymi spolkami operacyjnymi,
- dla tych podmiotow klasyczne wskazniki zadluzenia, plynnosci i rentownosci moga miec inna interpretacje.

## Ograniczenia zakresu badania

### Ograniczenia zrodla SEC Company Facts

1. Dane obejmuja tylko emitentow raportujacych do SEC.
2. Zakres jest skoncentrowany na rynku amerykanskim i spolkach skladajacych raporty w EDGAR.
3. Company Facts udostepnia dane XBRL, ale nie gwarantuje idealnie jednolitego tagowania ekonomicznie podobnych pozycji.
4. Czesci spolek brakuje danych Company Facts.
5. Dane moga byc aktualizowane w czasie, dlatego lokalny cache jest istotny dla odtwarzalnosci.
6. Nie wszystkie pozycje sprawozdawcze sa raportowane przez wszystkie spolki.

### Ograniczenia mapowania XBRL

1. Repo uzywa autorskiej konfiguracji tagow `configs/sec_tags.yaml`.
2. Uwzgledniono tagi `us-gaap`, nie IFRS.
3. Dla niektorych zmiennych istnieje kilka dopuszczalnych tagow i poziomy priorytetu.
4. Czasem wartosc jest pochodna:
   - aktywa moga byc uzupelnione z `liabilities_and_equity`,
   - zobowiazania moga byc wyliczone jako `liabilities_and_equity - equity`,
   - koszty operacyjne moga byc wyliczone jako `revenues - ebit`.
5. Takie wartosci pochodne sa uzyteczne, ale nalezy je opisac jako decyzje techniczne, a nie bezposrednio raportowane fakty.

### Ograniczenia proby badawczej

1. Proba nie jest losowa.
2. Proba jest ograniczona do spolek przechodzacych filtry SIC i entity type.
3. Obecnosc spolek OTC moze zwiekszac zroznicowanie jakosci i kompletności danych.
4. Wykluczenie sektorow finansowych i utilities poprawia porownywalnosc wskaznikow, ale ogranicza uogolnialnosc wynikow.
5. Brak twardych etykiet bankructwa/fraudu oznacza, ze dalsza czesc pracy operuje na proxy ryzyka, a nie na obserwacji faktycznego zdarzenia prawnego.

### Ograniczenia zakresu czasowego

1. Lata 2011-2025 zapewniaja dlugi panel, ale starsze lata moga miec gorsze lub mniej jednolite pokrycie XBRL.
2. Ostatni rok zrodlowy jest wykorzystywany do horyzontu `t+1`, nie jako zwykla obserwacja cech.
3. Zbior jest podatny na survivor/availability bias, bo opiera sie na spolkach z dostepnymi danymi w SEC Company Facts i aktualnej mapie ticker-CIK.

### Ograniczenia interpretacyjne

1. Dane finansowe same nie pozwalaja jednoznacznie wykryc manipulacji sprawozdawczej.
2. Wskazniki finansowe sa proxy kondycji i ryzyka, nie dowodem bankructwa lub fraudu.
3. Braki danych moga wynikac zarowno z problemow technicznych, jak i z ekonomicznej nieadekwatnosci danej pozycji dla danej spolki.
4. Porownywanie spolek z roznych branz wymaga ostroznosci, nawet po wykluczeniu sektorow najbardziej specyficznych.

## Future improvements

Do wskazania w 4.1 albo raczej w ograniczeniach pracy / zakonczeniu:

1. Rozszerzenie zrodla o SEC Financial Statement and Notes Data Sets.
2. Dodanie danych rynkowych:
   - kapitalizacja,
   - stopy zwrotu,
   - zmiennosc,
   - delisting / bankruptcy events.
3. Dodanie twardych etykiet zdarzen:
   - bankructwo,
   - restrukturyzacja,
   - AAER / SEC enforcement actions,
   - restatements.
4. Rozszerzenie mapowania XBRL o dodatkowe tagi i taxonomy extensions.
5. Osobne modele dla sektorow lub co najmniej mocniejsze kontrole sektorowe.
6. Osobny pipeline dla instytucji finansowych i utilities zamiast ich wykluczania.
7. Porownanie danych rocznych z kwartalnymi.
8. Dodanie analizy tekstowej raportow 10-K, np. MD&A lub risk factors.
9. Utrwalenie wersji danych przez zapis dat pobrania, hashy plikow i manifestu raw data.
10. Automatyczne testy regresji danych dla mapowania XBRL i kontroli jakosci.

## Co nalezy podeprzec bibliografia lub zrodlami

### Zrodla oficjalne SEC

Do bibliografii / przypisow nalezy dodac oficjalne strony SEC dla:

1. EDGAR APIs:
   - czym sa endpointy `submissions`, `companyfacts`, `companyconcept`, `frames`.
2. Company Facts API:
   - charakterystyka danych XBRL dostepnych per CIK.
3. `company_tickers.json`:
   - mapa tickerow i CIK.
4. Zasady dostepu do EDGAR:
   - User-Agent,
   - fair access,
   - limity tempa pobierania.
5. Formularz 10-K:
   - roczny raport skladany przez spolki publiczne,
   - znaczenie rocznych sprawozdan finansowych.
6. Lista kodow SIC SEC:
   - uzasadnienie uzycia SIC do klasyfikacji sektorowej.

### XBRL / US GAAP

Do podparcia zrodlami:

1. Rola XBRL w raportowaniu finansowym do SEC.
2. Znaczenie taksonomii US GAAP.
3. Ograniczenia tagowania XBRL:
   - wiele tagow dla podobnych pozycji,
   - extension tags,
   - problemy porownywalnosci.

Mozliwe typy zrodel:

- SEC XBRL / Inline XBRL documentation,
- FASB US GAAP Financial Reporting Taxonomy,
- artykuly naukowe o jakosci i porownywalnosci danych XBRL.

### Analiza wskaznikowa i zakres sektorowy

Do bibliografii nalezy dodac zrodla dla twierdzen, ze:

1. Wskazniki finansowe sa klasycznym narzedziem oceny kondycji finansowej.
2. Wskazniki plynnosci, rentownosci, zadluzenia i efektywnosci maja rozna interpretacje sektorowa.
3. Instytucje finansowe, banki, ubezpieczyciele i utilities wymagaja osobnego traktowania w analizie finansowej.
4. Analiza distress / bankructwa czesto wykorzystuje dane sprawozdawcze i wskazniki finansowe.

Mozliwe zrodla:

- klasyczna literatura rachunkowosci finansowej i analizy finansowej,
- Altman i literatura distress prediction,
- prace o porownywalnosci wskaznikow miedzy branzami.

### ML/QNN a zakres danych

W 4.1 wystarczy tylko zasygnalizowac, ze dane maja charakter tabelaryczny i liczbowy. Do bibliografii w rozdzialach 2-3 nalezy podeprzec:

1. Specyfike danych tabularnych w ML.
2. Problem leakage w danych panelowych i czasowych.
3. Potrzebe redukcji wymiaru dla QNN / VQC.
4. Ograniczenia NISQ i symulacji kwantowych.

W 4.1 nie trzeba tego rozwijac, chyba ze w jednym akapicie uzasadniajacym, dlaczego zakres danych ograniczono do policzalnych cech finansowych.

### Przykladowe oficjalne zrodla do sprawdzenia przed bibliografia

Ponizsze adresy wynikaja z dokumentacji i linkow wykorzystywanych w repozytorium. Przed wstawieniem do bibliografii warto sprawdzic aktualny tytul strony i date dostepu.

| Obszar | Zrodlo / adres |
|---|---|
| EDGAR APIs | `https://www.sec.gov/search-filings/edgar-application-programming-interfaces` |
| Zasady dostepu do EDGAR | `https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data` |
| Mapa ticker-CIK | `https://www.sec.gov/files/company_tickers.json` |
| Company Facts API | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json` jako endpoint; opis najlepiej cytowac z dokumentacji EDGAR APIs |
| Submissions API | `https://data.sec.gov/submissions/CIK{cik10}.json` jako endpoint; opis najlepiej cytowac z dokumentacji EDGAR APIs |
| SEC Financial Statement Data Sets | `https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets` |
| SEC Financial Statement and Notes Data Sets | `https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets` |
| Lista kodow SIC SEC | `https://www.sec.gov/search-filings/standard-industrial-classification-sic-code-list` |
| US GAAP Taxonomy | oficjalna strona FASB dotyczaca US GAAP Financial Reporting Taxonomy |
| XBRL / Inline XBRL | dokumentacja SEC lub FASB dotyczaca XBRL i Inline XBRL w raportowaniu finansowym |

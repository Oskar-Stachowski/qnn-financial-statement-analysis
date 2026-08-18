# Frozen historical research universe specification — v1.1.0

Data formalnego zamrożenia: **2026-08-18**
Status: **FROZEN — historical point-in-time research universe only**

## 1. Decyzja i zakres

Historyczny point-in-time research universe zostaje formalnie zamrożony w
wersji `1.1.0`. Jednostką kanonicznego panelu jest registrant–fiscal year
identyfikowany przez CIK i rok cech. Universe określa, które historyczne
spółka-lata należą do populacji badawczej; nie określa dostępności cech ani
targetu.

Zamrożenie obejmuje:

- filing-first membership;
- historyczny SIC i klasyfikację sektorową;
- wybór anchor 10-K;
- politykę registrant-role;
- `economic_statement_scope_id` i wybór representative CIK;
- `economic_group_id`;
- reguły duplicate registrants;
- wykluczenie potwierdzonych nominal/non-operating co-issuerów;
- politykę `eligible`, `excluded` i `ambiguous`;
- wymagane provenance oraz regułę konsumencką dla przyszłego `X_t`.

Zamrożenie nie obejmuje:

- finalnego `X_t`;
- ekstrakcji ani availability cech;
- imputacji, winsoryzacji, skalowania lub innego preprocessingu;
- feature selection;
- modeli, architektur i hiperparametrów;
- procedury trenowania oraz oceny modeli.

## 2. Filing-first membership

Populacja jest budowana z historycznego census oryginalnych filingów SEC, a
nie z bieżącej listy tickerów, giełd ani aktywnych spółek. Kandydatem jest każdy
historyczny registrant składający kwalifikujący się oryginalny `10-K`, którego
historyczny SIC z tego samego accession spełnia zamrożoną politykę sektorową.

Nie są kwalifikującymi formami `10-K/A`, `10-KT` ani `10-KT/A`. Bieżący ticker,
bieżąca giełda i bieżąca aktywność emitenta nie są warunkami membership.
Historyczne lata spółek później delistowanych, przejętych, zlikwidowanych lub
nieaktywnych pozostają w universe. Brak filingu `t+1`, cech, targetu albo
bieżącego tickera nie usuwa obserwacji `t`.

CIK jest podstawowym identyfikatorem registranta. Zmiana tickera nie tworzy
nowej jednostki. Następca z innym CIK pozostaje odrębnym registrantem; powiązań
CIK nie wolno zgadywać na podstawie podobnej nazwy lub tickera.

## 3. Zakres lat i źródła point-in-time

Zamrożony panel obejmuje feature years `2011–2024`:

- development train/validation: `2011–2022`;
- mechaniczne zastosowanie tej samej polityki do test years: `2023–2024`.

Źródłami są:

1. SEC EDGAR quarterly master index — census filingów i accession;
2. SEC Financial Statement Data Sets `SUB` — historyczny submission metadata,
   fiscal year, SIC i accepted timestamp;
3. submission header tego samego accession — osobne bloki `FILER`, fallback
   metadata i historyczny SIC co-registrantów;
4. oficjalna tabela SEC SIC — opis kodu, nie źródło bieżącego membership;
5. primary original 10-K oraz jego XBRL package — dowód statement scope dla
   joint filings.

Informacje bieżące mogą służyć wyłącznie do audytu survivorship bias i nie mogą
zmieniać historycznego membership.

## 4. Anchor 10-K i timestamp membership

Dla CIK–fiscal year anchor stanowi najwcześniejszy oryginalny `10-K`. Kolejność
wyboru jest deterministyczna:

1. najwcześniejszy `accepted_at`;
2. następnie najwcześniejszy `filed`;
3. następnie accession jako stabilny tie-breaker.

`membership_available_at` jest timestampem accepted z FSDS `SUB` albo
historycznego submission header. Jeżeli timestamp rzeczywiście pozostaje
niedostępny, dopuszczalnym fallbackiem jest `filed` z precyzją daty, jawnie
oznaczony w `membership_available_at_precision`. Późniejszy filing nie może
zmienić wcześniejszego anchoru w tej samej wersji universe.

## 5. Historyczny SIC i klasyfikacja sektorowa

SIC musi należeć do tego samego anchor accession i właściwego bloku registranta:

1. `FSDS SUB` jest używany wyłącznie dla zgodnego primary CIK;
2. dla co-registrantów i fallbacku używa się ich własnego bloku `FILER` w
   submission header;
3. SIC primary CIK nie może zostać skopiowany na innego co-registranta;
4. konflikt FSDS–header daje `ambiguous`;
5. brak wiarygodnego historycznego SIC daje `ambiguous`;
6. future/current SIC nie jest fallbackiem.

Zamrożona polityka sektorowa:

- wykluczone: SIC `6000–6799` (financials/insurance/real estate) oraz
  `4900–4999` (utilities);
- Technology: zakresy `3570–3579`, `3660–3669`, `3670–3679`, `3810–3819`,
  `3820–3829`, `7370–7379` albo zamrożone słowa kluczowe opisu SIC;
- Retail: `5200–5999`, po zastosowaniu wcześniejszych wykluczeń i reguły
  Technology;
- Industrials/Manufacturing: `2000–3999`, po zastosowaniu reguły Technology;
- Extended Candidate: zamrożone zakresy healthcare/services, wholesale,
  construction, transportation/communications i energy/mining zapisane w
  `configs/research_universe_pit.yaml`;
- pozostałe prawidłowe SIC są `excluded` jako `out_of_scope_sector`.

## 6. Zamrożone registrant roles

Każdy kanoniczny wiersz otrzymuje jedną z czterech wartości:

```text
single_filer_xbrl_registrant
single_filer_non_xbrl_registrant
joint_primary_registrant
joint_co_registrant
```

Single-filer/non-XBRL jest rzeczywistym pojedynczym registrantem. Brak XBRL
wpływa później na availability `X_t`, ale sam nie zmienia membership.

## 7. Economic statement scope i representative CIK

Dla joint filing membership jest rozstrzygany na poziomie pełnego annual
statement scope, a nie samej obecności CIK na cover page.

CIK jest zachowywany jako odrębna reporting entity tylko wtedy, gdy primary
original 10-K potwierdza jego własny pełny roczny komplet sprawozdań: balance
sheet, statement of operations/income i cash-flow statement. Jeden joint
accession może zatem zawierać kilka eligible reporting entities, jeżeli każda
ma odrębny pełny audited annual statement scope.

Jeżeli kilka CIK współdzieli dokładnie ten sam skonsolidowany statement scope:

- pozostaje maksymalnie jeden eligible representative CIK;
- representative wynika wyłącznie z dowodu statement entity w primary 10-K i
  XBRL provenance;
- target, coverage, cechy i wyniki modeli nie mogą wpływać na wybór;
- pozostałe CIK pozostają w kanonicznym artefakcie jako `excluded` provenance
  oraz w polach linked/co-registrant representative row;
- brak jednoznacznego właściciela statement scope daje `ambiguous`, nie
  arbitralny wybór.

`economic_statement_scope_id` jednoznacznie identyfikuje accession i jego
statement scope. W jednym roku nie może istnieć więcej niż jeden eligible
wiersz dla tego samego identyfikatora. Eligible CIK musi być równy
`representative_cik`.

## 8. Duplicate registrants i nominal co-issuers

Freeze-gate potwierdził i zamroził następujące działania:

- `132` duplicate registrant rows zostały usunięte z eligible i zachowane jako
  `excluded` z reason code `duplicate_registrant_same_statement_scope`;
- `28` wierszy potwierdzonych nominal/non-operating finance co-issuerów zostało
  oznaczonych `excluded` z reason code
  `nominal_nonoperating_finance_coissuer`;
- `6` nierozstrzygniętych obserwacji zostało oznaczonych `ambiguous`.

Nazwa zawierająca „finance” lub „capital” nigdy nie jest samodzielną podstawą
wykluczenia. Wykluczenie nominalnego co-issuera wymaga bezpośredniego dowodu z
primary filingu o braku substantive operations.

## 9. Economic group

`economic_group_id` łączy CIK, które historycznie współwystępowały w joint
filings, w konserwatywne connected components. Identyfikator:

- nie zmienia membership;
- nie zmienia anchoru ani SIC;
- nie nadpisuje głównego temporal splitu;
- nie usuwa odrębnych reporting entities z własnymi statement scopes;
- służy później do dependence/leakage diagnostics, clustered inference i
  opcjonalnego group-aware cross-validation.

## 10. Statusy membership

Dozwolone są wyłącznie trzy statusy:

- `eligible` — historyczny anchor, SIC/sektor i economic-entity scope są zgodne
  z polityką; tylko te wiersze mogą być kandydatami do przyszłego `X_t`;
- `excluded` — powód wykluczenia jest jednoznaczny i zapisany w provenance;
- `ambiguous` — brak wystarczającego dowodu; wiersz nie może wejść do `X_t` i
  nie wolno go arbitralnie przypisać do `eligible` ani innej klasy.

Membership, `x_t_status` i `target_status` pozostają osobnymi polami. Target
`t+1` nie może decydować o obecności obserwacji `t` w universe.

## 11. Wymagane provenance

Kanoniczny artefakt zachowuje co najmniej:

- accession, CIK i feature year;
- filed/accepted timestamp oraz precision;
- historyczny SIC, opis, źródło i conflict details;
- źródłową i rozstrzygniętą registrant role;
- representative CIK;
- wszystkie CIK accession i linked co-registrant CIKs;
- `economic_statement_scope_id` i członków tego scope;
- `economic_group_id`;
- resolution action, evidence oraz membership reason;
- status membership przed i po economic-entity resolution;
- osobne `x_t_status` i `target_status`.

Wiersze wykluczone przez resolver nie są fizycznie kasowane, ponieważ ich
zachowanie jest konieczne do audytu liczebności i wyboru representative CIK.

## 12. Finalne liczebności

Kanoniczny artefakt zawiera `103 099` company-year anchors:

| Membership status | Liczba |
|---|---:|
| `eligible` | **64 901** |
| `excluded` | **36 659** |
| `ambiguous` | **1 539** |

Dodatkowe invariants:

- eligible unique representative CIK: `9 798`;
- eligible distinct statement scope-years: `64 901`;
- eligible distinct economic groups: `9 739`;
- eligible duplicate statement scope-year rows: `0`;
- eligible non-representative rows: `0`;
- joint-filing eligible company-years: `610`.

## 13. Survivorship i historical-classification bias

Względem starego current-snapshot universe wersja zamrożona odzyskuje `6 267`
historycznych CIK i `30 871` company-years. `6 123` odzyskanych CIK nie występuje
w bieżącym ticker snapshot. Potwierdza to, że bieżąca lista spółek nie może być
warunkiem historycznego membership.

SEC-only inactivity/delisting proxy nie jest potwierdzoną datą delistingu i nie
rozróżnia automatycznie M&A, likwidacji oraz braku mapowania tickera. Jest to
ograniczenie diagnostyczne, a nie filtr membership.

## 14. Relacja do zamrożonego targetu

Target `target_candidate_v2_pit_b` pozostaje odrębnie zamrożony w wersji
`1.0.0`. Niniejszy freeze nie zmienia jego definicji, kodu ani artefaktu.
Zweryfikowany SHA-256 targetu wynosi:

```text
473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff
```

## 15. Elementy jawnie niezamrożone

`X_t` nie został zbudowany. Nie są zamrożone ani zatwierdzone: feature
availability, point-in-time feature extraction, preprocessing, imputacja,
winsoryzacja, skalowanie, feature selection, modele i hiperparametry. Żaden z
tych elementów nie może być przedstawiany jako część universe v1.1.0.

## 16. Reprodukcja i kontrola zmian

Maszynowo czytelny manifest znajduje się w
`configs/research_universe_pit_freeze_manifest.yaml`. Hashuje konfigurację,
kod konstrukcji i audytu, testy, evidence oraz finalne raporty. Duży lokalny
kanoniczny CSV jest kontrolowany przez non-versioned reproduction check.

Po freeze zmiana którejkolwiek zamrożonej reguły wymaga:

1. nowej wersji historical universe;
2. datowanego uzasadnienia niezależnego od wyników modeli;
3. ponownego full audit i nowego manifestu;
4. zachowania wersji `1.1.0` jako punktu odniesienia;
5. jawnego opisania wpływu na membership i porównywalność eksperymentów.

Wyniki targetu, cech lub modeli nie mogą uzasadniać post hoc zmiany universe
v1.1.0.

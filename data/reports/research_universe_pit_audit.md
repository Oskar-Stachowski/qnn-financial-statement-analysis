# Audyt historycznego point-in-time research universe

Wygenerowano: `2026-08-18T13:12:25.750545+02:00`.

## Wynik

Nowy universe jest zbudowany filing-first z census oryginalnych 10-K SEC. CIK i historyczny SIC pochodzą z tego samego anchor filing; bieżąca lista tickerów nie jest warunkiem membership. Status membership, `X_t` i targetu są rozdzielone. Zamrożony `target_candidate_v2_pit_b v1.0.0` nie został przeliczony ani zmieniony.

Testowe feature years 2023–2024 zostały objęte wyłącznie mechanicznym zastosowaniem zamrożonej polityki universe; nie użyto ich do podjęcia ani zmiany decyzji metodologicznej.

## Registrant-role / economic-entity resolution

Role źródłowe zostały rozdzielone na cztery jednoznaczne wartości. Wspólny accession nie tworzy kilku eligible obserwacji dla jednego statement scope. Wiersze usunięte z populacji eligible pozostają w kanonicznym pliku jako provenance `excluded` albo `ambiguous`.

Membership przed zastosowaniem resolvera:

| membership_status_pre_entity_resolution | n | share_pct |
| --- | --- | --- |
| eligible | 65067 | 63.11 |
| excluded | 36499 | 35.4 |
| ambiguous | 1533 | 1.49 |

Membership po zastosowaniu resolvera:

| membership_status | n | share_pct |
| --- | --- | --- |
| eligible | 64901 | 62.95 |
| excluded | 36659 | 35.56 |
| ambiguous | 1539 | 1.49 |

Zmiany membership:

| membership_status_pre_entity_resolution | membership_status | registrant_resolution_action | membership_reason | company_years |
| --- | --- | --- | --- | --- |
| eligible | excluded | exclude_duplicate_registrant_row | duplicate_registrant_same_statement_scope | 132 |
| eligible | excluded | exclude_nonoperating_issuer | nominal_nonoperating_finance_coissuer | 28 |
| eligible | ambiguous | mark_ambiguous | statement_scope_owner_not_eligible_under_historical_policy | 4 |
| eligible | ambiguous | mark_ambiguous | statement_scope_owner_is_nonregistrant_parent | 2 |

- Wykluczono 132 potwierdzone duplicate registrant rows.
- Wykluczono 28 nominalnych/non-operating finance co-issuerów na podstawie bezpośredniego dowodu z filingu.
- 6 nierozstrzygniętych obserwacji zmieniono na `ambiguous`.
- Eligible statement scope-year duplicates: 0.
- Eligible wiersze niebędące representative CIK: 0.
- Distinct eligible statement scope-years: 64,901; representative CIKs: 9,798; economic groups: 9,739.

`economic_group_id` wyłącznie identyfikuje powiązane ekonomicznie statement scopes. Nie zmienia membership i nie zastępuje temporal splitu; ma służyć clustered inference, leakage diagnostics i opcjonalnemu group-aware CV.

## Liczebność według roku

| year | anchors | eligible_company_years | eligible_pre_entity_resolution | removed_by_entity_resolution | eligible_companies | excluded | ambiguous | recovered_vs_old | recovered_share_pct | absent_current_ticker | inactive_delisted_unmapped_proxy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2011 | 8486 | 5662 | 5678 | 16 | 5662 | 2745 | 79 | 3994 | 70.54 | 3921 | 615 |
| 2012 | 8024 | 5364 | 5376 | 12 | 5364 | 2570 | 90 | 3623 | 67.54 | 3553 | 476 |
| 2013 | 7942 | 5262 | 5276 | 14 | 5262 | 2586 | 94 | 3444 | 65.45 | 3376 | 522 |
| 2014 | 7873 | 5148 | 5159 | 11 | 5148 | 2618 | 107 | 3202 | 62.2 | 3137 | 578 |
| 2015 | 7515 | 4851 | 4874 | 23 | 4851 | 2575 | 89 | 2817 | 58.07 | 2749 | 525 |
| 2016 | 7247 | 4592 | 4613 | 21 | 4592 | 2559 | 96 | 2461 | 53.59 | 2399 | 445 |
| 2017 | 7032 | 4408 | 4418 | 10 | 4408 | 2524 | 100 | 2166 | 49.14 | 2105 | 367 |
| 2018 | 6879 | 4295 | 4304 | 9 | 4295 | 2485 | 99 | 1939 | 45.15 | 1879 | 380 |
| 2019 | 6730 | 4150 | 4159 | 9 | 4150 | 2484 | 96 | 1667 | 40.17 | 1607 | 298 |
| 2020 | 6998 | 4206 | 4215 | 9 | 4206 | 2687 | 105 | 1519 | 36.12 | 1452 | 240 |
| 2021 | 7683 | 4542 | 4551 | 9 | 4542 | 3021 | 120 | 1510 | 33.25 | 1435 | 343 |
| 2022 | 7333 | 4423 | 4431 | 8 | 4423 | 2776 | 134 | 1240 | 28.04 | 1174 | 450 |
| 2023 | 6820 | 4142 | 4150 | 8 | 4142 | 2520 | 158 | 834 | 20.14 | 777 | 406 |
| 2024 | 6537 | 3856 | 3863 | 7 | 3856 | 2509 | 172 | 455 | 11.8 | 397 | 397 |

## Odzyskane spółki i survivorship bias

- Stary universe: 3,730 CIK.
- Nowy PIT universe: 9,798 kwalifikujących się CIK i 64,901 spółka-lat.
- Odzyskano 6,267 CIK oraz 30,871 spółka-lat nieobecnych w starym universe.
- Z odzyskanych CIK 6,123 nie występuje w current ticker snapshot (komponent survivorship/inactivity/unmapped), a 144 nadal występuje, lecz było pominiętych przez starą bieżącą klasyfikację/filtry.
- Odzyskane obserwacje stanowią 47.57% nowego universe.
- 199 CIK starego snapshotu nie ma kwalifikującego historycznego anchoru w badanym zakresie albo historycznie nie spełnia polityki sektorowej.

Wniosek: survivorship bias starego universe był istotny — current-company snapshot usuwał historycznych registrantów. Nowa definicja usuwa ten warunek z membership, ale nie gwarantuje dostępności X_t ani targetu.

## Spółki później nieaktywne / delistowane

Konserwatywny proxy obejmuje 6,042 spółka-lat i 6,042 unikalnych CIK. Proxy oznacza jednocześnie: brak na current ticker snapshot (`2026-05-20T09:51:01.214500+00:00`) oraz brak późniejszego oryginalnego 10-K do końca indeksu 2025.

To nie jest potwierdzona data delistingu: SEC filing index sam nie rozróżnia delistingu, M&A, likwidacji i braku mapowania tickera. Membership zachowuje te obserwacje; do potwierdzenia zdarzeń potrzebne byłoby osobne historyczne źródło giełdowe/CRSP.

## Sektory

| sector | n | share_pct |
| --- | --- | --- |
| Industrials_Manufacturing | 25903 | 39.91 |
| Extended_Candidate | 22660 | 34.91 |
| Technology | 12066 | 18.59 |
| Retail | 4272 | 6.58 |

Rozkład sektor–rok:

| feature_year | research_sector | company_years |
| --- | --- | --- |
| 2011 | Extended_Candidate | 2290 |
| 2011 | Industrials_Manufacturing | 1940 |
| 2011 | Retail | 389 |
| 2011 | Technology | 1043 |
| 2012 | Extended_Candidate | 2166 |
| 2012 | Industrials_Manufacturing | 1836 |
| 2012 | Retail | 369 |
| 2012 | Technology | 993 |
| 2013 | Extended_Candidate | 2106 |
| 2013 | Industrials_Manufacturing | 1823 |
| 2013 | Retail | 362 |
| 2013 | Technology | 971 |
| 2014 | Extended_Candidate | 1994 |
| 2014 | Industrials_Manufacturing | 1850 |
| 2014 | Retail | 350 |
| 2014 | Technology | 954 |
| 2015 | Extended_Candidate | 1798 |
| 2015 | Industrials_Manufacturing | 1847 |
| 2015 | Retail | 335 |
| 2015 | Technology | 871 |
| 2016 | Extended_Candidate | 1658 |
| 2016 | Industrials_Manufacturing | 1801 |
| 2016 | Retail | 321 |
| 2016 | Technology | 812 |
| 2017 | Extended_Candidate | 1551 |
| 2017 | Industrials_Manufacturing | 1770 |
| 2017 | Retail | 301 |
| 2017 | Technology | 786 |
| 2018 | Extended_Candidate | 1461 |
| 2018 | Industrials_Manufacturing | 1774 |
| 2018 | Retail | 288 |
| 2018 | Technology | 772 |
| 2019 | Extended_Candidate | 1377 |
| 2019 | Industrials_Manufacturing | 1748 |
| 2019 | Retail | 262 |
| 2019 | Technology | 763 |
| 2020 | Extended_Candidate | 1313 |
| 2020 | Industrials_Manufacturing | 1840 |
| 2020 | Retail | 261 |
| 2020 | Technology | 792 |
| 2021 | Extended_Candidate | 1328 |
| 2021 | Industrials_Manufacturing | 2026 |
| 2021 | Retail | 287 |
| 2021 | Technology | 901 |
| 2022 | Extended_Candidate | 1297 |
| 2022 | Industrials_Manufacturing | 2004 |
| 2022 | Retail | 268 |
| 2022 | Technology | 854 |
| 2023 | Extended_Candidate | 1207 |
| 2023 | Industrials_Manufacturing | 1885 |
| 2023 | Retail | 248 |
| 2023 | Technology | 802 |
| 2024 | Extended_Candidate | 1114 |
| 2024 | Industrials_Manufacturing | 1759 |
| 2024 | Retail | 231 |
| 2024 | Technology | 752 |

## SIC (20 najczęstszych)

| historical_sic | historical_sic_description | company_years | unique_ciks |
| --- | --- | --- | --- |
| 2834.0 | PHARMACEUTICAL PREPARATIONS | 6327 | 993 |
| 7372.0 | SERVICES-PREPACKAGED SOFTWARE | 3030 | 599 |
| 1311.0 | CRUDE PETROLEUM & NATURAL GAS | 2604 | 435 |
| 7389.0 | SERVICES-BUSINESS SERVICES, NEC | 2165 | 427 |
| 3841.0 | SURGICAL & MEDICAL INSTRUMENTS & APPARATUS | 1793 | 272 |
| 2836.0 | BIOLOGICAL PRODUCTS, (NO DISGNOSTIC SUBSTANCES) | 1645 | 273 |
| 3674.0 | SEMICONDUCTORS & RELATED DEVICES | 1403 | 207 |
| 1000.0 | METAL MINING | 1181 | 264 |
| 7374.0 | SERVICES-COMPUTER PROCESSING & DATA PREPARATION | 1084 | 240 |
| 5812.0 | RETAIL-EATING PLACES | 814 | 126 |
| 8742.0 | SERVICES-MANAGEMENT CONSULTING SERVICES | 749 | 144 |
| 7370.0 | SERVICES-COMPUTER PROGRAMMING, DATA PROCESSING, ETC. | 702 | 154 |
| 1040.0 | GOLD AND SILVER ORES | 681 | 139 |
| 3714.0 | MOTOR VEHICLE PARTS & ACCESSORIES | 642 | 94 |
| 7373.0 | SERVICES-COMPUTER INTEGRATED SYSTEMS DESIGN | 632 | 110 |
| 2860.0 | INDUSTRIAL ORGANIC CHEMICALS | 619 | 99 |
| 3845.0 | ELECTROMEDICAL & ELECTROTHERAPEUTIC APPARATUS | 594 | 81 |
| 4813.0 | TELEPHONE COMMUNICATIONS (NO RADIOTELEPHONE) | 558 | 91 |
| 7371.0 | SERVICES-COMPUTER PROGRAMMING SERVICES | 538 | 99 |
| 3663.0 | RADIO & TV BROADCASTING & COMMUNICATIONS EQUIPMENT | 515 | 75 |

## Ambiguous i excluded

| membership_status | membership_reason | company_years |
| --- | --- | --- |
| ambiguous | historical_sic_missing_in_registrant_header | 1532 |
| ambiguous | statement_scope_owner_not_eligible_under_historical_policy | 4 |
| ambiguous | statement_scope_owner_is_nonregistrant_parent | 2 |
| ambiguous | historical_sic_conflict | 1 |
| excluded | financials_insurance_real_estate_excluded | 32076 |
| excluded | utilities_excluded | 3778 |
| excluded | out_of_scope_sector | 645 |
| excluded | duplicate_registrant_same_statement_scope | 132 |
| excluded | nominal_nonoperating_finance_coissuer | 28 |


Filingi poza panelem spółka–rok:

| feature_year_resolution_status | observed_fiscal_year | filing_rows |
| --- | --- | --- |
| resolved_out_of_scope | 2000 | 2 |
| resolved_out_of_scope | 2001 | 5 |
| resolved_out_of_scope | 2002 | 5 |
| resolved_out_of_scope | 2003 | 6 |
| resolved_out_of_scope | 2004 | 11 |
| resolved_out_of_scope | 2005 | 12 |
| resolved_out_of_scope | 2006 | 16 |
| resolved_out_of_scope | 2007 | 31 |
| resolved_out_of_scope | 2008 | 59 |
| resolved_out_of_scope | 2009 | 107 |
| resolved_out_of_scope | 2010 | 6685 |
| resolved_out_of_scope | 2025 | 732 |

Łącznie 7,671 filingów pozostaje poza panelem: 7,671 ma jednoznaczny rok poza zakresem 2011–2024, a 0 nie ma wiarygodnego roku i nie jest zgadywane.

## Joint filings i co-registranci

610 kwalifikujących spółka-lat (130 CIK) pochodzi z accession obejmującego więcej niż jednego registranta. Każdy odrębny pełny annual statement scope pozostaje osobną reporting entity, ale dla współdzielonego scope zachowany jest tylko jeden eligible representative CIK. SIC nadal pochodzi z historycznego bloku `FILER` danego CIK.

| registrant_role_resolved | n | share_pct |
| --- | --- | --- |
| single_filer_xbrl_registrant | 60533 | 93.27 |
| single_filer_non_xbrl_registrant | 3758 | 5.79 |
| joint_primary_registrant | 338 | 0.52 |
| joint_co_registrant | 272 | 0.42 |

## Wiele oryginalnych 10-K dla CIK–roku

701 eligible CIK–lat ma więcej niż jeden kandydat oryginalnego 10-K (maksimum 3). Zgodnie z polityką anchor jest najwcześniejszym accepted filing; liczba kandydatów i rank pozostają w provenance. Nie zmieniano wyboru na podstawie danych finansowych ani targetu.

## Historyczna klasyfikacja a stary snapshot

W części wspólnej 4,155 spółka-lat ma historyczny SIC inny niż SIC z bieżącego snapshotu, 7,212 ma inną etykietę sektorową, a w 1,490 zmienia się sam status eligible/excluded.

Bieżący snapshot uznaje za eligible 589 spółka-lat, które historycznie nie były eligible; odwrotnie, 901 historycznych spółka-lat zostałoby utraconych przez zastosowanie bieżącej klasyfikacji.

| current_snapshot_eligible | historical_eligible | current_snapshot_sector | research_sector | company_years |
| --- | --- | --- | --- | --- |
| False | False | Excluded_REIT | Excluded_Financials_Insurance_RealEstate | 2318 |
| False | False | Excluded_Fund_ETF_Trust | Excluded_Financials_Insurance_RealEstate | 1564 |
| True | True | Industrials_Manufacturing | Industrials_Manufacturing | 568 |
| True | True | Industrials_Manufacturing | Extended_Candidate | 449 |
| True | True | Extended_Candidate | Extended_Candidate | 312 |
| False | False | Excluded_SPAC_Blank_Check | Excluded_Financials_Insurance_RealEstate | 270 |
| True | False | Industrials_Manufacturing | Excluded_Financials_Insurance_RealEstate | 259 |
| False | False | Excluded_Financials_Insurance_RealEstate | Excluded_Financials_Insurance_RealEstate | 256 |
| True | True | Extended_Candidate | Technology | 230 |
| True | True | Extended_Candidate | Industrials_Manufacturing | 207 |
| True | True | Technology | Extended_Candidate | 178 |
| False | True | Excluded_Financials_Insurance_RealEstate | Industrials_Manufacturing | 172 |
| True | False | Extended_Candidate | Excluded_Financials_Insurance_RealEstate | 167 |
| False | True | Excluded_Financials_Insurance_RealEstate | Extended_Candidate | 155 |
| True | True | Industrials_Manufacturing | Technology | 136 |
| True | True | Technology | Industrials_Manufacturing | 131 |
| True | True | Technology | Technology | 124 |
| False | True | Excluded_Fund_ETF_Trust | Extended_Candidate | 115 |
| False | True | Excluded_Financials_Insurance_RealEstate | Technology | 107 |
| True | False | Technology | Excluded_Financials_Insurance_RealEstate | 103 |

## Rozdzielenie statusów

`membership_status` wynika z kwalifikującego anchor 10-K, jego historycznego SIC oraz zamkniętej polityki registrant-role/economic-entity. `x_t_status` pozostaje `not_built`. Dostępność targetu jest tylko dołączoną informacją i nie wpływa na membership.

Target status w kwalifikującej populacji development 2011–2022:

| target_status | eligible_company_years |
| --- | --- |
| not_computed | 30500 |
| available | 14061 |
| ambiguous | 8240 |
| missing | 3998 |
| hard_exclude | 104 |

X_t status:

| x_t_status | n | share_pct |
| --- | --- | --- |
| not_built | 64901 | 100.0 |

## Ocena metodologiczna

- Stary universe: istotne ryzyko survivorship bias oraz historical-classification bias zostało potwierdzone empirycznie.
- Nowy universe: membership jest historyczne i filing-first; brak t+1, targetu albo przyszłego filingu nie usuwa obserwacji t.
- Brak historycznego SIC lub konflikt source-of-record skutkuje `ambiguous`, nigdy zgadywaniem sektora.
- Current ticker i exchange służą wyłącznie do audytu; nie są filtrami.
- Zamrożony target ma nadal hash `473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff` zgodny z freeze manifestem.
- Finalny X_t nadal nie istnieje i nie trenowano modeli.

## Źródła

- SEC EDGAR quarterly master index: census filingów i historyczna ścieżka accession.
- SEC Financial Statement Data Sets, `SUB`: CIK, SIC, okres i accepted timestamp obowiązujące dla danego submission.
- SEC submission header tego samego accession: fallback oraz osobne bloki `FILER` dla joint filings.
- Oficjalna tabela kodów SIC SEC: wyłącznie opis statycznego kodu; nie źródło membership ani bieżącego SIC spółki.

## Freeze gate

Audyt nie zamraża universe automatycznie. Weryfikuje jedynie gotowość zaimplementowanej wersji 1.1.0.

**RESEARCH UNIVERSE READY TO FREEZE**

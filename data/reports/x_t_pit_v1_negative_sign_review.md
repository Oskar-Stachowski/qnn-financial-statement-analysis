# X_t v1 — pre-freeze sanity check ujemnych selected primitives

Wygenerowano: 2026-08-19T06:41:04.459677+00:00

## Zakres i wynik

Kontrola objęła wyłącznie development 2011–2022. Sprawdzono 25 primitive-cases w 23 company-years względem exact frozen-universe anchor accession, filing index, primary original 10-K oraz primary financial statement. Test 2023–2024 nie był używany do decyzji.

- faktycznie raportowane i ekonomicznie uzasadnione: 5
- błąd znaku/tagu/kontekstu XBRL: 16
- nierozstrzygalne ekonomicznie: 4
- zachowane bez zmiany: 5
- ustawione fail-closed jako ambiguous/NA: 20

Nie zastosowano odwracania znaku ani podmiany na alternatywny fact/tag. Dla każdego fail-closed primitive para current/comparative została oznaczona ambiguous, a wszystkie zależne cechy przeliczone do stanu niedostępnego.

## Wynik według primitive

| Primitive | Przypadki przed | Selected ujemne po |
|---|---:|---:|
| assets | 3 | 0 |
| liabilities | 12 | 0 |
| current_assets | 3 | 0 |
| current_liabilities | 2 | 0 |
| revenues | 5 | 5 |

## Kontrola przypadek po przypadku

| Company-year | Primitive | Przed | Klasyfikacja | Działanie | Primary statement evidence |
|---|---|---:|---|---|---|
| 0000925535-2011 | current_assets | -62602 | unresolved | ambiguous_na | Total current assets: -62602; Primary balance sheet presents negative cash and negative total current assets; conservative economic classification is unresolved. |
| 0001024520-2011 | revenues | -143061 | reported_economically_valid | retain | Revenue, net: -143061; Primary statement and revenue detail show product revenue offset by 332,000 of sales returns and allowances. |
| 0001067286-2012 | current_assets | -284 | unresolved | ambiguous_na | TOTAL CURRENT ASSETS: -284; Primary balance sheet presents negative cash and negative total current assets; conservative economic classification is unresolved. |
| 0001089319-2014 | current_liabilities | -289411 | xbrl_semantic_or_context_error | ambiguous_na | Total current liabilities: 289411; Primary 10-K presents positive current liabilities; the XBRL-rendered sign is inverted. |
| 0001089319-2014 | liabilities | -303881 | xbrl_semantic_or_context_error | ambiguous_na | TOTAL LIABILITIES: 303881; Primary 10-K presents positive liabilities; the XBRL-rendered sign is inverted. |
| 0001326190-2022 | revenues | -68000 | reported_economically_valid | retain | Revenues: -68000; The filing attributes negligible negative revenue to adjustments of prior-year BARDA cost reimbursements. |
| 0001484674-2012 | current_liabilities | -492652 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 492652; Primary 10-K presents positive current/total liabilities; XBRL fact sign is inverted. |
| 0001499735-2012 | liabilities | -12785 | xbrl_semantic_or_context_error | ambiguous_na | Total current liabilities: 211707; The -12,785 fact corresponds to liabilities assumed in an acquisition disclosure, not consolidated balance-sheet liabilities. |
| 0001514514-2014 | revenues | -128995 | reported_economically_valid | retain | Net Sales: -128995; Gross sales of 74,856 are exceeded by credits and 173,000 of slotting fees, producing reported negative net sales. |
| 0001617351-2018 | liabilities | -10806 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 12185; Liabilities tag is attached to Total Stockholders' Equity (deficit), while primary liabilities are 12,185. |
| 0001617351-2019 | assets | -6889 | xbrl_semantic_or_context_error | ambiguous_na | Total Assets: 2334; Selected value is the stockholders' deficit line tagged LiabilitiesAndStockholdersEquity; primary total assets are 2,334. |
| 0001625285-2018 | assets | -13 | unresolved | ambiguous_na | Total Assets: -13; Primary balance sheet reports negative cash, current assets and total assets; the economic classification of the overdraft cannot be resolved conservatively. |
| 0001625285-2018 | current_assets | -13 | unresolved | ambiguous_na | Total Current Assets: -13; Primary balance sheet presents negative cash and negative total current assets; conservative economic classification is unresolved. |
| 0001629606-2018 | revenues | -65034 | reported_economically_valid | retain | Sales: -65034; The filing explicitly explains 114,574 of dispensary cost reimbursements offsetting delivery and commission income. |
| 0001673504-2019 | assets | -12490 | xbrl_semantic_or_context_error | ambiguous_na | Total Assets: 14142; Selected value is the stockholders' deficit line tagged LiabilitiesAndStockholdersEquity; primary total assets are 14,142. |
| 0001696411-2018 | liabilities | -1600 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 1600; Liabilities tag is attached to stockholders' deficit; primary liabilities are positive 1,600. |
| 0001696411-2019 | liabilities | -2800 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 2800; Liabilities tag is attached to stockholders' deficit; primary liabilities are positive 2,800. |
| 0001696411-2020 | liabilities | -26862 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 35748; Liabilities tag is attached to stockholders' deficit; primary liabilities are positive 35,748. |
| 0001698530-2021 | revenues | -483000 | reported_economically_valid | retain | Total revenue: -483000; The filing documents a 2.792 million AbbVie cumulative catch-up revenue reversal offset by Ipsen revenue. |
| 0001714379-2019 | liabilities | -12167 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 12763; Liabilities tag is attached to stockholders' deficit; primary liabilities are positive 12,763. |
| 0001746278-2020 | liabilities | -14843 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 20225; Liabilities tag is attached to stockholder's deficit; primary liabilities are positive 20,225. |
| 0001753373-2020 | liabilities | -15854 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 27545; Liabilities tag is attached to stockholders' deficit; primary liabilities are positive 27,545. |
| 0001753391-2019 | liabilities | -14796 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 16994; Liabilities tag is attached to stockholders' deficit; primary liabilities are positive 16,994. |
| 0001753391-2020 | liabilities | -12692 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 15144; Liabilities tag is attached to stockholders' deficit; primary liabilities are positive 15,144. |
| 0001765048-2020 | liabilities | -12634 | xbrl_semantic_or_context_error | ambiguous_na | Total Liabilities: 14066; Liabilities tag is attached to stockholders' deficit; primary liabilities are positive 14,066. |

## Invariants i integralność

- 64 901 eligible company-years zachowanych; schema i exact-accession invariants przeszły.
- frozen universe SHA-256: `a449c8145d1f46f954f12b1dfc079bb0b367c4f7f5edf3332a983ad7c1fb8182`.
- frozen target SHA-256: `473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff`.
- raw X_t SHA-256 po przeliczeniu: `0f1b35b9ffbb1fb1c1cdfb7dff12e3efd8fb38f60b33407ff2b2a8fb6b88397f`.
- brak imputacji, winsoryzacji, skalowania, feature selection i treningu modeli.

## Werdykt

**X_T V1 READY TO FREEZE**

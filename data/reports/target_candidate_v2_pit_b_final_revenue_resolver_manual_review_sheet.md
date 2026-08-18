# Direct primary-statement review — PIT-B revenues

Arkusz kontrolny; decyzje manualne pozostają w pliku CSV. Wartości pochodzą z dokładnego SEC-rendered statement wskazanego przez FilingSummary dla anchor accession t+1.

## 00. L3HARRIS TECHNOLOGIES, INC. /DE/ — t=2011

- Kategoria: `historical_concept_conflict`; sektor: `Technology`; SIC: `3812`.
- Anchor: `0001193125-12-369967`; statement: `Consolidated Statement of Income`; file: `R2.htm`.
- Resolver: `Total Revenue` / `us-gaap:SalesRevenueNet`; comparative `5418400000.0`; current `5451300000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/202058/000119312512369967/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue from product sales and services | `us-gaap:SalesRevenueNetAbstract` | `{"2012-06-29":null,"2011-07-01":null,"2010-07-02":null}` |
| Revenue from product sales | `us-gaap:SalesRevenueGoodsNet` | `{"2012-06-29":3364700000.0,"2011-07-01":3691500000.0,"2010-07-02":3502300000.0}` |
| Revenue from services | `us-gaap:SalesRevenueServicesNet` | `{"2012-06-29":2086600000.0,"2011-07-01":1726900000.0,"2010-07-02":1222700000.0}` |
| Total Revenue | `us-gaap:SalesRevenueNet` | `{"2012-06-29":5451300000.0,"2011-07-01":5418400000.0,"2010-07-02":4725000000.0}` |
| Cost of product sales and services | `us-gaap:CostOfGoodsAndServicesSoldAbstract` | `{"2012-06-29":null,"2011-07-01":null,"2010-07-02":null}` |
| Cost of product sales | `us-gaap:CostOfGoodsSold` | `{"2012-06-29":-1945200000.0,"2011-07-01":-2141199999.9999998,"2010-07-02":-2082800000.0000002}` |

## 01. CADENCE DESIGN SYSTEMS INC — t=2011

- Kategoria: `historical_concept_conflict`; sektor: `Technology`; SIC: `7372`.
- Anchor: `0000813672-13-000007`; statement: `Consolidated Income Statements`; file: `R3.htm`.
- Resolver: `Total revenue` / `us-gaap:SalesRevenueNet`; comparative `1149835000.0`; current `1326424000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/813672/000081367213000007/R3.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue: | `us-gaap:RevenuesAbstract` | `{"2012-12-29":null,"2011-12-31":null,"2011-01-01":null}` |
| Total revenue | `us-gaap:SalesRevenueNet` | `{"2012-12-29":1326424000.0,"2011-12-31":1149835000.0,"2011-01-01":935954000.0}` |
| Marketing and sales | `us-gaap:SellingAndMarketingExpense` | `{"2012-12-29":342278000.0,"2011-12-31":323798000.0,"2011-01-01":305558000.0}` |

## 02. Jazz Pharmaceuticals plc — t=2011

- Kategoria: `historical_concept_conflict`; sektor: `Industrials_Manufacturing`; SIC: `2834`.
- Anchor: `0001232524-13-000010`; statement: `Consolidated Statements of Income`; file: `R4.htm`.
- Resolver: `Total revenues` / `us-gaap:Revenues`; comparative `272277000.0`; current `585979000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1232524/000123252413000010/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues: | `us-gaap:RevenuesAbstract` | `{"2012-12-31":null,"2011-12-31":null,"2010-12-31":null}` |
| Product sales, net | `us-gaap:SalesRevenueGoodsNet` | `{"2012-12-31":580527000.0,"2011-12-31":266518000.0,"2010-12-31":170006000.0}` |
| Royalties and contract revenues | `jazz:RoyaltiesAndContractRevenues` | `{"2012-12-31":5452000.0,"2011-12-31":5759000.0,"2010-12-31":3775000.0}` |
| Total revenues | `us-gaap:Revenues` | `{"2012-12-31":585979000.0,"2011-12-31":272277000.0,"2010-12-31":173781000.0}` |
| Cost of product sales (excluding amortization of acquired developed technologies) | `jazz:CostOfProductSalesExcludingAmortizationOfAcquiredDevelopedTechnology` | `{"2012-12-31":78425000.0,"2011-12-31":13942000.0,"2010-12-31":13559000.0}` |

## 03. Alkermes plc. — t=2011

- Kategoria: `historical_concept_conflict`; sektor: `Industrials_Manufacturing`; SIC: `2834`.
- Anchor: `0001047469-13-006422`; statement: `CONSOLIDATED STATEMENTS OF OPERATIONS AND COMPREHENSIVE INCOME (LOSS)`; file: `R4.htm`.
- Resolver: `Total revenues` / `us-gaap:SalesRevenueNet`; comparative `389977000.0`; current `575548000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1520262/000104746913006422/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| REVENUES: | `us-gaap:SalesRevenueNetAbstract` | `{"2013-03-31":null,"2012-03-31":null,"2011-03-31":null}` |
| Manufacturing and royalty revenues | `alks:ManufacturingAndRoyaltyRevenues` | `{"2013-03-31":510900000.0,"2012-03-31":326444000.0,"2011-03-31":156840000.0}` |
| Product sales, net | `us-gaap:SalesRevenueGoodsNet` | `{"2013-03-31":58107000.0,"2012-03-31":41184000.0,"2011-03-31":28920000.0}` |
| Research and development revenue | `us-gaap:ContractsRevenue` | `{"2013-03-31":6541000.0,"2012-03-31":22349000.0,"2011-03-31":880000.0}` |
| Total revenues | `us-gaap:SalesRevenueNet` | `{"2013-03-31":575548000.0,"2012-03-31":389977000.0,"2011-03-31":186640000.0}` |

## 04. VERU INC. — t=2012

- Kategoria: `historical_concept_conflict`; sektor: `Industrials_Manufacturing`; SIC: `2834`.
- Anchor: `0001171843-13-004893`; statement: `Consolidated Statements Of Income`; file: `R4.htm`.
- Resolver: `Net revenues` / `us-gaap:SalesRevenueNet`; comparative `35033897.0`; current `31456778.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/863894/000117184313004893/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net revenues | `us-gaap:SalesRevenueNet` | `{"2013-09-30":31456778.0,"2012-09-30":35033897.0,"2011-09-30":18565102.0}` |
| Cost of sales | `us-gaap:CostOfGoodsSold` | `{"2013-09-30":13952420.0,"2012-09-30":14412884.0,"2011-09-30":8699912.0}` |

## 05. Digimarc CORP — t=2012

- Kategoria: `historical_concept_conflict`; sektor: `Technology`; SIC: `7373`.
- Anchor: `0001193125-14-062441`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Total revenue` / `us-gaap:Revenues`; comparative `44375000.0`; current `34964000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1438231/000119312514062441/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue: | `us-gaap:RevenuesAbstract` | `{"2013-12-31":null,"2012-12-31":null,"2011-12-31":null}` |
| Total revenue | `us-gaap:Revenues` | `{"2013-12-31":34964000.0,"2012-12-31":44375000.0,"2011-12-31":36039000.0}` |
| Cost of revenue: | `us-gaap:CostOfRevenueAbstract` | `{"2013-12-31":null,"2012-12-31":null,"2011-12-31":null}` |
| Total cost of revenue | `us-gaap:CostOfRevenue` | `{"2013-12-31":8205000.0,"2012-12-31":6508000.0,"2011-12-31":6937000.0}` |
| Sales and marketing | `us-gaap:SellingAndMarketingExpense` | `{"2013-12-31":6144000.0,"2012-12-31":3827000.0,"2011-12-31":4336000.0}` |

## 06. KORN FERRY — t=2013

- Kategoria: `historical_concept_conflict`; sektor: `Extended_Candidate`; SIC: `7361`.
- Anchor: `0001193125-14-253292`; statement: `CONSOLIDATED STATEMENTS OF INCOME`; file: `R4.htm`.
- Resolver: `Total revenue` / `us-gaap:Revenues`; comparative `849701000.0`; current `995559000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/56679/000119312514253292/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Fee revenue | `us-gaap:SalesRevenueServicesNet` | `{"2014-04-30":960301000.0,"2013-04-30":812831000.0,"2012-04-30":790505000.0}` |
| Total revenue | `us-gaap:Revenues` | `{"2014-04-30":995559000.0,"2013-04-30":849701000.0,"2012-04-30":826759000.0}` |

## 07. PTC INC. — t=2013

- Kategoria: `historical_concept_conflict`; sektor: `Technology`; SIC: `7372`.
- Anchor: `0000857005-14-000032`; statement: `Consolidated Statements Of Operations`; file: `R4.htm`.
- Resolver: `Total revenue` / `us-gaap:SalesRevenueNet`; comparative `1293541000.0`; current `1356967000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/857005/000085700514000032/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue: | `us-gaap:RevenuesAbstract` | `{"2014-09-30":null,"2013-09-30":null,"2012-09-30":null}` |
| Total revenue | `us-gaap:SalesRevenueNet` | `{"2014-09-30":1356967000.0,"2013-09-30":1293541000.0,"2012-09-30":1255679000.0}` |
| Cost of revenue: | `us-gaap:CostOfRevenueAbstract` | `{"2014-09-30":null,"2013-09-30":null,"2012-09-30":null}` |
| Cost of license revenue | `us-gaap:LicenseCosts` | `{"2014-09-30":31663000.0,"2013-09-30":33004000.0,"2012-09-30":30595000.0}` |
| Cost of service revenue | `us-gaap:CostOfServices` | `{"2014-09-30":256876000.0,"2013-09-30":258954000.0,"2012-09-30":265483000.0}` |
| Cost of support revenue | `us-gaap:MaintenanceCosts` | `{"2014-09-30":85144000.0,"2013-09-30":81081000.0,"2012-09-30":76050000.0}` |
| Total cost of revenue | `us-gaap:CostOfRevenue` | `{"2014-09-30":373683000.0,"2013-09-30":373039000.0,"2012-09-30":372128000.0}` |
| Sales and marketing | `us-gaap:SellingAndMarketingExpense` | `{"2014-09-30":357447000.0,"2013-09-30":360640000.0,"2012-09-30":377796000.0}` |

## 08. YUM BRANDS INC — t=2013

- Kategoria: `historical_concept_conflict`; sektor: `Retail`; SIC: `5812`.
- Anchor: `0001041061-15-000007`; statement: `Consolidated Statements of Income`; file: `R2.htm`.
- Resolver: `Total revenues` / `us-gaap:Revenues`; comparative `13084000000.0`; current `13279000000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1041061/000104106115000007/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues | `us-gaap:RevenuesAbstract` | `{"2014-12-27":null,"2013-12-28":null,"2012-12-29":null}` |
| Company sales | `us-gaap:SalesRevenueGoodsNet` | `{"2014-12-27":11324000000.0,"2013-12-28":11184000000.0,"2012-12-29":11833000000.0}` |
| Total revenues | `us-gaap:Revenues` | `{"2014-12-27":13279000000.0,"2013-12-28":13084000000.0,"2012-12-29":13633000000.0}` |

## 09. NVE CORP /NEW/ — t=2014

- Kategoria: `historical_concept_conflict`; sektor: `Technology`; SIC: `3674`.
- Anchor: `0000724910-16-000052`; statement: `Statements of Income`; file: `R4.htm`.
- Resolver: `Total revenue` / `us-gaap:Revenues`; comparative `30584088.0`; current `27717278.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/724910/000072491016000052/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:RevenuesAbstract` | `{"2016-03-31":null,"2015-03-31":null,"2014-03-31":null}` |
| Product sales | `us-gaap:SalesRevenueGoodsNet` | `{"2016-03-31":24410391.0,"2015-03-31":29894045.0,"2014-03-31":25512028.0}` |
| Total revenue | `us-gaap:Revenues` | `{"2016-03-31":27717278.0,"2015-03-31":30584088.0,"2014-03-31":25934907.0}` |
| Cost of sales | `us-gaap:CostOfRevenue` | `{"2016-03-31":6616852.0,"2015-03-31":6019868.0,"2014-03-31":5720277.0}` |

## 10. Liberty Broadband Corp — t=2014

- Kategoria: `historical_concept_conflict`; sektor: `Extended_Candidate`; SIC: `4841`.
- Anchor: `0001558370-16-003202`; statement: `Condensed Combined Statements of Operations`; file: `R4.htm`.
- Resolver: `Total revenue` / `us-gaap:SalesRevenueNet`; comparative `69045000.0`; current `91182000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1611983/000155837016003202/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue: | `us-gaap:RevenuesAbstract` | `{"2015-12-31":null,"2014-12-31":null,"2013-12-31":null}` |
| Total revenue | `us-gaap:SalesRevenueNet` | `{"2015-12-31":91182000.0,"2014-12-31":69045000.0,"2013-12-31":77363000.0}` |

## 11. SENSIENT TECHNOLOGIES CORP — t=2015

- Kategoria: `historical_concept_conflict`; sektor: `Industrials_Manufacturing`; SIC: `2860`.
- Anchor: `0001140361-17-008738`; statement: `CONSOLIDATED STATEMENTS OF EARNINGS`; file: `R2.htm`.
- Resolver: `Revenue` / `us-gaap:SalesRevenueGoodsNet`; comparative `1375964000.0`; current `1383210000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/310142/000114036117008738/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:SalesRevenueGoodsNet` | `{"2016-12-31":1383210000.0,"2015-12-31":1375964000.0,"2014-12-31":1447821000.0}` |

## 12. MICROSOFT CORP — t=2015

- Kategoria: `historical_concept_conflict`; sektor: `Technology`; SIC: `7372`.
- Anchor: `0001193125-16-662209`; statement: `INCOME STATEMENTS`; file: `R2.htm`.
- Resolver: `Total revenue` / `us-gaap:SalesRevenueNet`; comparative `93580000000.0`; current `85320000000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/789019/000119312516662209/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:SalesRevenueNetAbstract` | `{"2016-06-30":null,"2015-06-30":null,"2014-06-30":null}` |
| Total revenue | `us-gaap:SalesRevenueNet` | `{"2016-06-30":85320000000.0,"2015-06-30":93580000000.0,"2014-06-30":86833000000.0}` |
| Cost of revenue | `us-gaap:CostOfRevenueAbstract` | `{"2016-06-30":null,"2015-06-30":null,"2014-06-30":null}` |
| Total cost of revenue | `us-gaap:CostOfRevenue` | `{"2016-06-30":32780000000.0,"2015-06-30":33038000000.0,"2014-06-30":27078000000.0}` |
| Sales and marketing | `us-gaap:SellingAndMarketingExpense` | `{"2016-06-30":14697000000.0,"2015-06-30":15713000000.0,"2014-06-30":15811000000.0}` |

## 13. MARTIN MIDSTREAM PARTNERS L.P. — t=2015

- Kategoria: `historical_concept_conflict`; sektor: `Extended_Candidate`; SIC: `5171`.
- Anchor: `0001176334-17-000011`; statement: `CONSOLIDATED STATEMENTS OF OPERATIONS`; file: `R4.htm`.
- Resolver: `Total revenues` / `us-gaap:SalesRevenueNet`; comparative `1036844000.0`; current `827391000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1176334/000117633417000011/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues: | `us-gaap:SalesRevenueNetAbstract` | `{"2016-12-31":null,"2015-12-31":null,"2014-12-31":null}` |
| Product sales: | `mmlp:ProductSalesAbstract` | `{"2016-12-31":null,"2015-12-31":null,"2014-12-31":null}` |
| Total product sales | `us-gaap:SalesRevenueGoodsNet` | `{"2016-12-31":574036000.0,"2015-12-31":748018000.0,"2014-12-31":1385123000.0}` |
| Total revenues | `us-gaap:SalesRevenueNet` | `{"2016-12-31":827391000.0,"2015-12-31":1036844000.0,"2014-12-31":1642141000.0}` |

## 14. UNISYS CORP — t=2016

- Kategoria: `historical_concept_conflict`; sektor: `Technology`; SIC: `7373`.
- Anchor: `0000746838-18-000009`; statement: `Consolidated Statements of Income`; file: `R2.htm`.
- Resolver: `Total revenue` / `us-gaap:Revenues`; comparative `2820700000.0`; current `2741800000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/746838/000074683818000009/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:RevenuesAbstract` | `{"2017-12-31":null,"2016-12-31":null,"2015-12-31":null}` |
| Total revenue | `us-gaap:Revenues` | `{"2017-12-31":2741800000.0,"2016-12-31":2820700000.0,"2015-12-31":3015100000.0}` |
| Cost of revenue: | `us-gaap:CostOfRevenueAbstract` | `{"2017-12-31":null,"2016-12-31":null,"2015-12-31":null}` |
| Total cost of revenue | `us-gaap:CostOfRevenue` | `{"2017-12-31":2263500000.0,"2016-12-31":2262100000.0,"2015-12-31":2474200000.0}` |

## 15. SOLESENCE, INC. — t=2016

- Kategoria: `historical_concept_conflict`; sektor: `Industrials_Manufacturing`; SIC: `2844`.
- Anchor: `0001387131-18-001319`; statement: `STATEMENTS OF OPERATIONS`; file: `R4.htm`.
- Resolver: `Total revenue` / `us-gaap:SalesRevenueNet`; comparative `10783000.0`; current `12471000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/883107/000138713118001319/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue: | `us-gaap:RevenuesAbstract` | `{"2017-12-31":null,"2016-12-31":null}` |
| Product revenue | `us-gaap:SalesRevenueGoodsNet` | `{"2017-12-31":12129000.0,"2016-12-31":10720000.0}` |
| Other revenue | `us-gaap:OtherSalesRevenueNet` | `{"2017-12-31":342000.0,"2016-12-31":63000.0}` |
| Total revenue | `us-gaap:SalesRevenueNet` | `{"2017-12-31":12471000.0,"2016-12-31":10783000.0}` |
| Cost of revenue | `us-gaap:CostOfRevenue` | `{"2017-12-31":8621000.0,"2016-12-31":7543000.0}` |

## 16. HACKETT GROUP, INC. — t=2016

- Kategoria: `historical_concept_conflict`; sektor: `Extended_Candidate`; SIC: `8742`.
- Anchor: `0001564590-18-005161`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Total revenue` / `us-gaap:Revenues`; comparative `288561000.0`; current `285862000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1057379/000156459018005161/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue: | `us-gaap:RevenuesAbstract` | `{"2017-12-29":null,"2016-12-30":null,"2016-01-01":null}` |
| Revenue before reimbursements | `us-gaap:SalesRevenueServicesNet` | `{"2017-12-29":263252000.0,"2016-12-30":259907000.0,"2016-01-01":234581000.0}` |
| Total revenue | `us-gaap:Revenues` | `{"2017-12-29":285862000.0,"2016-12-30":288561000.0,"2016-01-01":260940000.0}` |

## 17. CUMBERLAND PHARMACEUTICALS INC — t=2016

- Kategoria: `historical_concept_conflict`; sektor: `Industrials_Manufacturing`; SIC: `2834`.
- Anchor: `0001628280-18-003034`; statement: `Consolidated Statements of Income and Comprehensive Income (Loss)`; file: `R4.htm`.
- Resolver: `Net revenues` / `us-gaap:SalesRevenueNet`; comparative `33025560.0`; current `41150131.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1087294/000162828018003034/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues: | `us-gaap:RevenuesAbstract` | `{"2017-12-31":null,"2016-12-31":null,"2015-12-31":null}` |
| Net product revenue | `us-gaap:SalesRevenueGoodsNet` | `{"2017-12-31":40376563.0,"2016-12-31":32478185.0,"2015-12-31":33013184.0}` |
| Other revenue | `us-gaap:OtherSalesRevenueNet` | `{"2017-12-31":773568.0,"2016-12-31":547375.0,"2015-12-31":505867.0}` |
| Net revenues | `us-gaap:SalesRevenueNet` | `{"2017-12-31":41150131.0,"2016-12-31":33025560.0,"2015-12-31":33519051.0}` |

## 18. ModuLink Inc. — t=2016

- Kategoria: `historical_concept_conflict`; sektor: `Extended_Candidate`; SIC: `7000`.
- Anchor: `0001553350-17-000782`; statement: `STATEMENTS OF OPERATIONS`; file: `R4.htm`.
- Resolver: `Total Revenue` / `us-gaap:Revenues`; comparative `98943.0`; current `60534.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1611046/000155335017000782/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:RevenuesAbstract` | `{"2016-12-31":null,"2015-12-31":null}` |
| Wine Tour Sales | `us-gaap:SalesRevenueNet` | `{"2016-12-31":58124.0,"2015-12-31":55943.0}` |
| Total Revenue | `us-gaap:Revenues` | `{"2016-12-31":60534.0,"2015-12-31":98943.0}` |

## 19. U-Haul Holding Co /NV/ — t=2018

- Kategoria: `historical_concept_conflict`; sektor: `Extended_Candidate`; SIC: `7510`.
- Anchor: `0000004457-20-000053`; statement: `Condensed Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Total revenues` / `us-gaap:Revenues`; comparative `3768707000.0`; current `3978868000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/4457/000000445720000053/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues: | `us-gaap:RevenuesAbstract` | `{"2020-03-31":null,"2019-03-31":null,"2018-03-31":null}` |
| Self-storage revenues | `uhal:SelfStorageRevenues` | `{"2020-03-31":418741000.0,"2019-03-31":367276000.0,"2018-03-31":323903000.0}` |
| Self-moving and self-storage products and service sales | `uhal:SaleRevenuesGoodsGross` | `{"2020-03-31":265091000.0,"2019-03-31":264146000.0,"2018-03-31":261557000.0}` |
| Other revenue | `us-gaap:OtherIncome` | `{"2020-03-31":240359000.0,"2019-03-31":219365000.0,"2018-03-31":184034000.0}` |
| Total revenues | `us-gaap:Revenues` | `{"2020-03-31":3978868000.0,"2019-03-31":3768707000.0,"2018-03-31":3601114000.0}` |
| Cost of sales | `us-gaap:CostOfGoodsAndServicesSold` | `{"2020-03-31":164018000.0,"2019-03-31":162142000.0,"2018-03-31":160489000.0}` |

## 20. Xylem Inc. — t=2018

- Kategoria: `historical_concept_conflict`; sektor: `Industrials_Manufacturing`; SIC: `3561`.
- Anchor: `0001524472-20-000006`; statement: `Consolidated Income Statements`; file: `R2.htm`.
- Resolver: `Revenue` / `us-gaap:Revenues`; comparative `5207000000.0`; current `5249000000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1524472/000152447220000006/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:Revenues` | `{"2019-12-31":5249000000.0,"2018-12-31":5207000000.0,"2017-12-31":4707000000.0}` |
| Cost of revenue | `us-gaap:CostOfRevenue` | `{"2019-12-31":3203000000.0,"2018-12-31":3181000000.0,"2017-12-31":2860000000.0}` |

## 21. Andersons, Inc. — t=2019

- Kategoria: `historical_concept_conflict`; sektor: `Extended_Candidate`; SIC: `5150`.
- Anchor: `0000821026-21-000060`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Revenues` / `us-gaap:Revenues`; comparative `8170191000.0`; current `8208436000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/821026/000082102621000060/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues | `us-gaap:Revenues` | `{"2020-12-31":8208436000.0,"2019-12-31":8170191000.0,"2018-12-31":3045382000.0}` |
| Cost of sales and merchandising revenues | `us-gaap:CostOfGoodsAndServicesSold` | `{"2020-12-31":7803514000.0,"2019-12-31":7652299000.0,"2018-12-31":2743377000.0}` |

## 22. Inogen Inc — t=2019

- Kategoria: `historical_concept_conflict`; sektor: `Industrials_Manufacturing`; SIC: `3842`.
- Anchor: `0001564590-21-008106`; statement: `Consolidated Statements of Comprehensive Income (Loss)`; file: `R4.htm`.
- Resolver: `Total revenue` / `us-gaap:Revenues`; comparative `361943000.0`; current `308487000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1294133/000156459021008106/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:RevenuesAbstract` | `{"2020-12-31":null,"2019-12-31":null,"2018-12-31":null}` |
| Sales revenue | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2020-12-31":280189000.0,"2019-12-31":340546000.0,"2018-12-31":336015000.0}` |
| Rental revenue | `ingn:RentalRevenueNet` | `{"2020-12-31":28298000.0,"2019-12-31":21397000.0,"2018-12-31":22096000.0}` |
| Total revenue | `us-gaap:Revenues` | `{"2020-12-31":308487000.0,"2019-12-31":361943000.0,"2018-12-31":358111000.0}` |
| Cost of revenue | `us-gaap:CostOfRevenueAbstract` | `{"2020-12-31":null,"2019-12-31":null,"2018-12-31":null}` |
| Cost of sales revenue | `us-gaap:CostOfGoodsAndServicesSold` | `{"2020-12-31":156764000.0,"2019-12-31":175974000.0,"2018-12-31":163989000.0}` |
| Cost of rental revenue, including depreciation of $5,695, $6,253 and $7,567, respectively | `ingn:CostOfRental` | `{"2020-12-31":13543000.0,"2019-12-31":14108000.0,"2018-12-31":15542000.0}` |
| Total cost of revenue | `us-gaap:CostOfRevenue` | `{"2020-12-31":170307000.0,"2019-12-31":190082000.0,"2018-12-31":179531000.0}` |
| Gross profit-sales revenue | `ingn:GrossProfitSalesRevenue` | `{"2020-12-31":123425000.0,"2019-12-31":164572000.0,"2018-12-31":172026000.0}` |
| Gross profit-rental revenue | `ingn:GrossProfitRentalRevenue` | `{"2020-12-31":14755000.0,"2019-12-31":7289000.0,"2018-12-31":6554000.0}` |
| Sales and marketing | `us-gaap:SellingAndMarketingExpense` | `{"2020-12-31":97520000.0,"2019-12-31":105550000.0,"2018-12-31":95641000.0}` |

## 23. HERTZ GLOBAL HOLDINGS, INC — t=2019

- Kategoria: `historical_concept_conflict`; sektor: `Extended_Candidate`; SIC: `7510`.
- Anchor: `0001657853-21-000006`; statement: `CONSOLIDATED STATEMENTS OF OPERATIONS`; file: `R4.htm`.
- Resolver: `Total revenues` / `us-gaap:Revenues`; comparative `9779000000.0`; current `5258000000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1657853/000165785321000006/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues: | `us-gaap:RevenuesAbstract` | `{"2020-12-31":null,"2019-12-31":null,"2018-12-31":null}` |
| Total revenues | `us-gaap:Revenues` | `{"2020-12-31":5258000000.0,"2019-12-31":9779000000.0,"2018-12-31":9504000000.0}` |
| Depreciation of revenue earning vehicles and lease charges | `htz:CostOfServicesDepreciationAndLeaseCharges` | `{"2020-12-31":2032000000.0,"2019-12-31":2565000000.0,"2018-12-31":2690000000.0}` |
| Revenues: | `us-gaap:RevenuesAbstract` | `{"2020-12-31":null,"2019-12-31":null,"2018-12-31":null}` |
| Total revenues | `us-gaap:Revenues` | `{"2020-12-31":5258000000.0,"2019-12-31":9779000000.0,"2018-12-31":9504000000.0}` |
| Depreciation of revenue earning vehicles and lease charges | `htz:CostOfServicesDepreciationAndLeaseCharges` | `{"2020-12-31":2032000000.0,"2019-12-31":2565000000.0,"2018-12-31":2690000000.0}` |

## 24. Cardlytics, Inc. — t=2020

- Kategoria: `historical_concept_conflict`; sektor: `Technology`; SIC: `7370`.
- Anchor: `0001666071-22-000022`; statement: `CONSOLIDATED STATEMENTS OF OPERATIONS`; file: `R5.htm`.
- Resolver: `Revenue` / `us-gaap:Revenues`; comparative `186892000.0`; current `267116000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1666071/000166607122000022/R5.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:Revenues` | `{"2021-12-31":267116000.0,"2020-12-31":186892000.0,"2019-12-31":210430000.0}` |
| Sales and marketing expense | `us-gaap:SellingAndMarketingExpense` | `{"2021-12-31":65996000.0,"2020-12-31":45307000.0,"2019-12-31":43828000.0}` |

## 25. HP INC — t=2015

- Kategoria: `largest_revenue_revision_delta_absolute`; sektor: `Technology`; SIC: `3570`.
- Anchor: `0000047217-16-000093`; statement: `Consolidated Statements of Earnings`; file: `R2.htm`.
- Resolver: `Net revenue` / `us-gaap:Revenues`; comparative `51463000000.0`; current `48238000000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/47217/000004721716000093/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net revenue | `us-gaap:RevenuesAbstract` | `{"2016-10-31":null,"2015-10-31":null,"2014-10-31":null}` |
| Net revenue | `us-gaap:Revenues` | `{"2016-10-31":48238000000.0,"2015-10-31":51463000000.0,"2014-10-31":56651000000.0}` |
| Cost of revenue | `us-gaap:CostOfRevenue` | `{"2016-10-31":39240000000.0,"2015-10-31":41524000000.0,"2014-10-31":45431000000.0}` |

## 26. Philip Morris International Inc. — t=2017

- Kategoria: `largest_revenue_revision_delta_absolute`; sektor: `Industrials_Manufacturing`; SIC: `2111`.
- Anchor: `0001413329-19-000007`; statement: `Consolidated Statements of Earnings`; file: `R2.htm`.
- Resolver: `Net revenues (Notes 2 & 21)` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `28748000000.0`; current `29625000000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1413329/000141332919000007/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues including excise taxes | `us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax` | `{"2018-12-31":79823000000.0,"2017-12-31":78098000000.0,"2016-12-31":74953000000.0}` |
| Net revenues (Notes 2 & 21) | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2018-12-31":29625000000.0,"2017-12-31":28748000000.0,"2016-12-31":26685000000.0}` |
| Cost of sales | `us-gaap:CostOfGoodsAndServicesSold` | `{"2018-12-31":10758000000.0,"2017-12-31":10432000000.0,"2016-12-31":9391000000.0}` |

## 27. DuPont de Nemours, Inc. — t=2018

- Kategoria: `largest_revenue_revision_delta_absolute`; sektor: `Industrials_Manufacturing`; SIC: `2821`.
- Anchor: `0001666700-20-000006`; statement: `Consolidated Statements of Income`; file: `R2.htm`.
- Resolver: `Net sales` / `us-gaap:Revenues`; comparative `22594000000.0`; current `21512000000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1666700/000166670020000006/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net sales | `us-gaap:Revenues` | `{"2019-12-31":21512000000.0,"2018-12-31":22594000000.0,"2017-12-31":11672000000.0}` |
| Cost of sales | `us-gaap:CostOfGoodsAndServicesSold` | `{"2019-12-31":14056000000.0,"2018-12-31":15302000000.0,"2017-12-31":9558000000.0}` |

## 28. CHS INC — t=2015

- Kategoria: `largest_revenue_revision_delta_absolute;largest_revenue_revision_delta_scaled`; sektor: `Extended_Candidate`; SIC: `5150`.
- Anchor: `0000823277-16-000065`; statement: `Consolidated Statements of Operations`; file: `R3.htm`.
- Resolver: `Revenues` / `us-gaap:Revenues`; comparative `34582442000.0`; current `30347203000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/823277/000082327716000065/R3.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues | `us-gaap:Revenues` | `{"2016-08-31":30347203000.0,"2015-08-31":34582442000.0,"2014-08-31":42664033000.0}` |

## 29. CHS INC — t=2016

- Kategoria: `largest_revenue_revision_delta_absolute;largest_revenue_revision_delta_scaled`; sektor: `Extended_Candidate`; SIC: `5150`.
- Anchor: `0000823277-17-000053`; statement: `Consolidated Statements of Operations`; file: `R3.htm`.
- Resolver: `Revenues` / `us-gaap:Revenues`; comparative `30347203000.0`; current `31934751000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/823277/000082327717000053/R3.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues | `us-gaap:Revenues` | `{"2017-08-31":31934751000.0,"2016-08-31":30347203000.0,"2015-08-31":34582442000.0}` |

## 30. TTEC Holdings, Inc. — t=2011

- Kategoria: `largest_revenue_revision_delta_scaled`; sektor: `Extended_Candidate`; SIC: `7363`.
- Anchor: `0001104659-13-014418`; statement: `Consolidated Statements of Comprehensive Income`; file: `R4.htm`.
- Resolver: `Revenue` / `us-gaap:SalesRevenueServicesNet`; comparative `1179388000.0`; current `1162981000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1013880/000110465913014418/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:SalesRevenueServicesNet` | `{"2012-12-31":1162981000.0,"2011-12-31":1179388000.0,"2010-12-31":1094906000.0}` |

## 31. Groupon, Inc. — t=2011

- Kategoria: `largest_revenue_revision_delta_scaled`; sektor: `Extended_Candidate`; SIC: `7311`.
- Anchor: `0001490281-13-000008`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Total revenue` / `us-gaap:Revenues`; comparative `1610430000.0`; current `2334472000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1490281/000149028113000008/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue: | `us-gaap:RevenuesAbstract` | `{"2012-12-31":null,"2011-12-31":null,"2010-12-31":null}` |
| Third party and other revenue | `grpn:ThirdPartyAndOtherRevenue` | `{"2012-12-31":1879729000.0,"2011-12-31":1589604000.0,"2010-12-31":312941000.0}` |
| Direct revenue | `us-gaap:SalesRevenueGoodsNet` | `{"2012-12-31":454743000.0,"2011-12-31":20826000.0,"2010-12-31":0.0}` |
| Total revenue | `us-gaap:Revenues` | `{"2012-12-31":2334472000.0,"2011-12-31":1610430000.0,"2010-12-31":312941000.0}` |
| Cost of revenue: | `us-gaap:CostOfRevenueAbstract` | `{"2012-12-31":null,"2011-12-31":null,"2010-12-31":null}` |
| Third party and other revenue | `grpn:CostOfRevenueThirdPartyAndOther` | `{"2012-12-31":297739000.0,"2011-12-31":243789000.0,"2010-12-31":42896000.0}` |
| Direct revenue | `us-gaap:CostOfGoodsSold` | `{"2012-12-31":421201000.0,"2011-12-31":15090000.0,"2010-12-31":0.0}` |
| Total cost of revenue | `us-gaap:CostOfRevenue` | `{"2012-12-31":718940000.0,"2011-12-31":258879000.0,"2010-12-31":42896000.0}` |

## 32. QUANTUM X LABS INC. — t=2021

- Kategoria: `largest_revenue_revision_delta_scaled`; sektor: `Technology`; SIC: `7372`.
- Anchor: `0001493152-23-008765`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Revenues` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `45224000.0`; current `96603000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/797542/000149315223008765/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2022-12-31":96603000.0,"2021-12-31":45224000.0}` |

## 33. Cineverse Corp. — t=2011

- Kategoria: `random_available_D5`; sektor: `Extended_Candidate`; SIC: `7841`.
- Anchor: `0001173204-13-000005`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Revenues` / `us-gaap:Revenues`; comparative `76557000.0`; current `88080000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1173204/000117320413000005/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues | `us-gaap:Revenues` | `{"2013-03-31":88080000.0,"2012-03-31":76557000.0}` |

## 34. Good Times Restaurants Inc. — t=2012

- Kategoria: `random_available_D5`; sektor: `Retail`; SIC: `5812`.
- Anchor: `0000825324-13-000043`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Total net revenues` / `us-gaap:Revenues`; comparative `19706000.0`; current `22892000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/825324/000082532413000043/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| NET REVENUES: | `us-gaap:SalesRevenueNetAbstract` | `{"2013-09-30":null,"2012-09-30":null}` |
| Restaurant sales | `us-gaap:SalesRevenueGoodsNet` | `{"2013-09-30":22523000.0,"2012-09-30":19274000.0}` |
| Total net revenues | `us-gaap:Revenues` | `{"2013-09-30":22892000.0,"2012-09-30":19706000.0}` |

## 35. TUCOWS INC /PA/ — t=2012

- Kategoria: `random_available_D5`; sektor: `Technology`; SIC: `7374`.
- Anchor: `0001437749-14-004497`; statement: `Consolidated Statements of Comprehensive Income`; file: `R4.htm`.
- Resolver: `Net revenues (note 16)` / `us-gaap:SalesRevenueServicesNet`; comparative `114726901.0`; current `129934904.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/909494/000143774914004497/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net revenues (note 16) | `us-gaap:SalesRevenueServicesNet` | `{"2013-12-31":129934904.0,"2012-12-31":114726901.0,"2011-12-31":97064967.0}` |
| Cost of revenues (note 16): | `tcx:CostOfRevenuesNote16Abstract` | `{"2013-12-31":null,"2012-12-31":null,"2011-12-31":null}` |
| Cost of revenues | `us-gaap:CostOfServices` | `{"2013-12-31":92960321.0,"2012-12-31":82837395.0,"2011-12-31":68088387.0}` |
| Total cost of revenues | `us-gaap:CostOfRevenue` | `{"2013-12-31":98508023.0,"2012-12-31":88517733.0,"2011-12-31":73762082.0}` |
| Sales and marketing (*) | `us-gaap:SellingAndMarketingExpense` | `{"2013-12-31":12141036.0,"2012-12-31":8701446.0,"2011-12-31":7442681.0}` |
| Sales and marketing | `tcx:StockbasedCompensationIncludedInSalesAndMarketing` | `{"2013-12-31":129302.0,"2012-12-31":92168.0,"2011-12-31":91244.0}` |

## 36. METTLER TOLEDO INTERNATIONAL INC/ — t=2012

- Kategoria: `random_available_D5`; sektor: `Technology`; SIC: `3826`.
- Anchor: `0001037646-14-000005`; statement: `Consolidated Statements of Operations`; file: `R2.htm`.
- Resolver: `Total Net Sales` / `us-gaap:SalesRevenueNet`; comparative `2341528000.0`; current `2378972000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1037646/000103764614000005/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net sales | `us-gaap:SalesRevenueNetAbstract` | `{"2013-12-31":null,"2012-12-31":null,"2011-12-31":null}` |
| Product Sales | `us-gaap:SalesRevenueGoodsNet` | `{"2013-12-31":1862026000.0,"2012-12-31":1852192000.0,"2011-12-31":1826891000.0}` |
| Service Sales | `us-gaap:SalesRevenueServicesNet` | `{"2013-12-31":516946000.0,"2012-12-31":489336000.0,"2011-12-31":482437000.0}` |
| Total Net Sales | `us-gaap:SalesRevenueNet` | `{"2013-12-31":2378972000.0,"2012-12-31":2341528000.0,"2011-12-31":2309328000.0}` |
| Cost of sales | `us-gaap:CostOfRevenueAbstract` | `{"2013-12-31":null,"2012-12-31":null,"2011-12-31":null}` |
| Products Cost of Sales | `us-gaap:CostOfGoodsSold` | `{"2013-12-31":794915000.0,"2012-12-31":811204000.0,"2011-12-31":798682000.0}` |
| Service Cost of Sales | `us-gaap:CostOfServices` | `{"2013-12-31":302031000.0,"2012-12-31":289269000.0,"2011-12-31":292372000.0}` |

## 37. KRONOS WORLDWIDE INC — t=2012

- Kategoria: `random_available_D5`; sektor: `Industrials_Manufacturing`; SIC: `2810`.
- Anchor: `0001564590-14-000695`; statement: `CONSOLIDATED STATEMENTS OF OPERATIONS`; file: `R4.htm`.
- Resolver: `Net sales` / `us-gaap:SalesRevenueNet`; comparative `1976300000.0`; current `1732400000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1257640/000156459014000695/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net sales | `us-gaap:SalesRevenueNet` | `{"2013-12-31":1732400000.0,"2012-12-31":1976300000.0,"2011-12-31":1943300000.0}` |
| Cost of sales | `us-gaap:CostOfGoodsSold` | `{"2013-12-31":1620200000.0,"2012-12-31":1415900000.0,"2011-12-31":1194900000.0}` |

## 38. APPLIED INDUSTRIAL TECHNOLOGIES INC — t=2014

- Kategoria: `random_available_D5`; sektor: `Extended_Candidate`; SIC: `5080`.
- Anchor: `0000109563-15-000129`; statement: `Statements of Consolidated Income`; file: `R2.htm`.
- Resolver: `Net Sales` / `us-gaap:SalesRevenueNet`; comparative `2459878000.0`; current `2751561000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/109563/000010956315000129/R2.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net Sales | `us-gaap:SalesRevenueNet` | `{"2015-06-30":2751561000.0,"2014-06-30":2459878000.0,"2013-06-30":2462171000.0}` |
| Cost of Sales | `us-gaap:CostOfGoodsAndServicesSold` | `{"2015-06-30":1981747000.0,"2014-06-30":1772952000.0,"2013-06-30":1779209000.0}` |

## 39. OLD DOMINION FREIGHT LINE, INC. — t=2015

- Kategoria: `random_available_D5`; sektor: `Extended_Candidate`; SIC: `4213`.
- Anchor: `0000878927-17-000005`; statement: `Statements Of Operations`; file: `R4.htm`.
- Resolver: `Revenue from operations` / `us-gaap:SalesRevenueServicesNet`; comparative `2972442000.0`; current `2991517000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/878927/000087892717000005/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue from operations | `us-gaap:SalesRevenueServicesNet` | `{"2016-12-31":2991517000.0,"2015-12-31":2972442000.0,"2014-12-31":2787897000.0}` |

## 40. LIGAND PHARMACEUTICALS INC — t=2015

- Kategoria: `random_available_D5`; sektor: `Industrials_Manufacturing`; SIC: `2834`.
- Anchor: `0000886163-17-000021`; statement: `CONSOLIDATED STATEMENTS OF OPERATIONS`; file: `R4.htm`.
- Resolver: `Total revenues` / `us-gaap:Revenues`; comparative `71914000.0`; current `108973000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/886163/000088616317000021/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues: | `us-gaap:RevenuesAbstract` | `{"2016-12-31":null,"2015-12-31":null,"2014-12-31":null}` |
| Material sales | `us-gaap:SalesRevenueGoodsNet` | `{"2016-12-31":22502000.0,"2015-12-31":27662000.0,"2014-12-31":28488000.0}` |
| License fees, milestones and other revenues | `lgnd:CollaborativeResearchAndDevelopmentAndOtherRevenues` | `{"2016-12-31":27048000.0,"2015-12-31":6058000.0,"2014-12-31":6056000.0}` |
| Total revenues | `us-gaap:Revenues` | `{"2016-12-31":108973000.0,"2015-12-31":71914000.0,"2014-12-31":64538000.0}` |
| Cost of sales | `us-gaap:CostOfGoodsSold` | `{"2016-12-31":5571000.0,"2015-12-31":5807000.0,"2014-12-31":9136000.0}` |

## 41. CBAK Energy Technology, Inc. — t=2015

- Kategoria: `random_available_D5`; sektor: `Industrials_Manufacturing`; SIC: `3690`.
- Anchor: `0001062993-17-000203`; statement: `Condensed consolidated statements of operations and comprehensive (loss) income`; file: `R4.htm`.
- Resolver: `Net revenues` / `us-gaap:SalesRevenueNet`; comparative `13904414.0`; current `10369444.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1117171/000106299317000203/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net revenues | `us-gaap:SalesRevenueNet` | `{"2016-09-30":10369444.0,"2015-09-30":13904414.0}` |
| Cost of revenues | `us-gaap:CostOfRevenue` | `{"2016-09-30":-12099632.0,"2015-09-30":-12954553.0}` |
| Sales and marketing expenses | `us-gaap:SellingAndMarketingExpense` | `{"2016-09-30":-995290.0,"2015-09-30":-135468.0}` |

## 42. APPFOLIO INC — t=2015

- Kategoria: `random_available_D5`; sektor: `Technology`; SIC: `7372`.
- Anchor: `0001433195-17-000010`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Revenue` / `us-gaap:SalesRevenueNet`; comparative `74977000.0`; current `105586000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1433195/000143319517000010/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:SalesRevenueNet` | `{"2016-12-31":105586000.0,"2015-12-31":74977000.0,"2014-12-31":47671000.0}` |
| Cost of revenue (exclusive of depreciation and amortization) | `us-gaap:CostOfGoodsAndServicesSold` | `{"2016-12-31":44630000.0,"2015-12-31":33903000.0,"2014-12-31":22555000.0}` |
| Sales and marketing | `us-gaap:SellingAndMarketingExpense` | `{"2016-12-31":28827000.0,"2015-12-31":26076000.0,"2014-12-31":16876000.0}` |

## 43. CBIZ, Inc. — t=2016

- Kategoria: `random_available_D5`; sektor: `Extended_Candidate`; SIC: `7389`.
- Anchor: `0001564590-18-004128`; statement: `Consolidated Statements of Comprehensive Income`; file: `R4.htm`.
- Resolver: `Revenue` / `us-gaap:Revenues`; comparative `799832000.0`; current `855340000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/944148/000156459018004128/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:Revenues` | `{"2017-12-31":855340000.0,"2016-12-31":799832000.0,"2015-12-31":750422000.0}` |

## 44. CVR PARTNERS, LP — t=2016

- Kategoria: `random_available_D5`; sektor: `Industrials_Manufacturing`; SIC: `2870`.
- Anchor: `0001425292-18-000022`; statement: `CONSOLIDATED STATEMENTS OF OPERATIONS`; file: `R4.htm`.
- Resolver: `Net sales` / `us-gaap:SalesRevenueGoodsNet`; comparative `356284000.0`; current `330802000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1425292/000142529218000022/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net sales | `us-gaap:SalesRevenueGoodsNet` | `{"2017-12-31":330802000.0,"2016-12-31":356284000.0,"2015-12-31":289194000.0}` |
| Cost of sales | `us-gaap:CostOfRevenue` | `{"2017-12-31":314390000.0,"2016-12-31":300307000.0,"2015-12-31":199697000.0}` |

## 45. ProPhase Labs, Inc. — t=2018

- Kategoria: `random_available_D5`; sektor: `Industrials_Manufacturing`; SIC: `2834`.
- Anchor: `0001493152-20-004807`; statement: `Consolidated Statements of Operations and Other Comprehensive Income (Loss)`; file: `R4.htm`.
- Resolver: `Net sales` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `13126000.0`; current `9876000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/868278/000149315220004807/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net sales | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2019-12-31":9876000.0,"2018-12-31":13126000.0}` |
| Cost of sales | `us-gaap:CostOfGoodsAndServicesSold` | `{"2019-12-31":7261000.0,"2018-12-31":8345000.0}` |
| Sales and marketing | `us-gaap:SellingAndMarketingExpense` | `{"2019-12-31":1042000.0,"2018-12-31":1107000.0}` |

## 46. GARMIN LTD — t=2019

- Kategoria: `random_available_D5`; sektor: `Technology`; SIC: `3812`.
- Anchor: `0001564590-21-006192`; statement: `Consolidated Statements of Income`; file: `R4.htm`.
- Resolver: `Net sales` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `3757505000.0`; current `4186573000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1121788/000156459021006192/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net sales | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2020-12-26":4186573000.0,"2019-12-28":3757505000.0,"2018-12-29":3347444000.0}` |

## 47. CONMED Corp — t=2020

- Kategoria: `random_available_D5`; sektor: `Industrials_Manufacturing`; SIC: `3845`.
- Anchor: `0000816956-22-000004`; statement: `Consolidated Statements of Comprehensive Income`; file: `R4.htm`.
- Resolver: `Revenues` / `us-gaap:Revenues`; comparative `862459000.0`; current `1010635000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/816956/000081695622000004/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues | `us-gaap:Revenues` | `{"2021-12-31":1010635000.0,"2020-12-31":862459000.0,"2019-12-31":955097000.0}` |
| Cost of sales | `us-gaap:CostOfGoodsAndServicesSold` | `{"2021-12-31":442599000.0,"2020-12-31":402159000.0,"2019-12-31":430382000.0}` |

## 48. AMERICAN EAGLE OUTFITTERS INC — t=2020

- Kategoria: `random_available_D5`; sektor: `Retail`; SIC: `5651`.
- Anchor: `0000950170-22-003587`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Total net revenue` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `3759113000.0`; current `5010785000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/919012/000095017022003587/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Total net revenue | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2022-01-29":5010785000.0,"2021-01-30":3759113000.0,"2020-02-01":4308212000.0}` |
| Cost of sales, including certain buying, occupancy and warehousing expenses | `us-gaap:CostOfGoodsAndServicesSold` | `{"2022-01-29":3018995000.0,"2021-01-30":2610966000.0,"2020-02-01":2785911000.0}` |

## 49. RESOURCES CONNECTION, INC. — t=2020

- Kategoria: `random_available_D5`; sektor: `Extended_Candidate`; SIC: `7389`.
- Anchor: `0001084765-21-000017`; statement: `Consolidated Statements Of Operations`; file: `R4.htm`.
- Resolver: `Revenue` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `703353000.0`; current `629516000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1084765/000108476521000017/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2021-05-29":629516000.0,"2020-05-30":703353000.0,"2019-05-25":728999000.0}` |

## 50. BIODESIX INC — t=2020

- Kategoria: `random_available_D5`; sektor: `Extended_Candidate`; SIC: `8071`.
- Anchor: `0000950170-22-003495`; statement: `Statements of Operations`; file: `R4.htm`.
- Resolver: `Revenues` / `us-gaap:Revenues`; comparative `45557000.0`; current `54506000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1439725/000095017022003495/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues | `us-gaap:Revenues` | `{"2021-12-31":54506000.0,"2020-12-31":45557000.0}` |
| Sales, marketing, general and administrative | `us-gaap:SellingGeneralAndAdministrativeExpense` | `{"2021-12-31":50517000.0,"2020-12-31":34857000.0}` |

## 51. GENCOR INDUSTRIES INC — t=2021

- Kategoria: `random_available_D5`; sektor: `Industrials_Manufacturing`; SIC: `3531`.
- Anchor: `0001193125-22-306498`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Net revenue` / `us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax`; comparative `85278000.0`; current `103479000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/64472/000119312522306498/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net revenue | `us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax` | `{"2022-09-30":103479000.0,"2021-09-30":85278000.0}` |

## 52. HASBRO, INC. — t=2022

- Kategoria: `random_available_D5`; sektor: `Industrials_Manufacturing`; SIC: `3944`.
- Anchor: `0000046080-24-000034`; statement: `Consolidated Statements of Operations`; file: `R5.htm`.
- Resolver: `Net revenues` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `5856700000.0`; current `5003300000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/46080/000004608024000034/R5.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net revenues | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2023-12-31":5003300000.0,"2022-12-25":5856700000.0,"2021-12-26":6420400000.0}` |
| Cost of sales | `us-gaap:CostOfGoodsAndServicesSold` | `{"2023-12-31":1706000000.0,"2022-12-25":1911800000.0,"2021-12-26":1927500000.0}` |

## 53. KULICKE & SOFFA INDUSTRIES INC — t=2014

- Kategoria: `random_available_D5_fill`; sektor: `Technology`; SIC: `3674`.
- Anchor: `0000056978-15-000125`; statement: `CONSOLIDATED STATEMENTS OF OPERATIONS`; file: `R4.htm`.
- Resolver: `Net revenue` / `us-gaap:SalesRevenueNet`; comparative `568569000.0`; current `536471000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/56978/000005697815000125/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net revenue | `us-gaap:SalesRevenueNet` | `{"2015-10-03":536471000.0,"2014-09-27":568569000.0,"2013-09-28":534938000.0}` |
| Cost of sales | `us-gaap:CostOfGoodsAndServicesSold` | `{"2015-10-03":277379000.0,"2014-09-27":295015000.0,"2013-09-28":287993000.0}` |

## 54. NextPlat Corp — t=2016

- Kategoria: `random_available_D5_fill`; sektor: `Extended_Candidate`; SIC: `4813`.
- Anchor: `0001493152-18-004404`; statement: `Consolidated Statements of Operations and Comprehensive Loss`; file: `R4.htm`.
- Resolver: `Net sales` / `us-gaap:SalesRevenueNet`; comparative `4698638.0`; current `6004955.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1058307/000149315218004404/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net sales | `us-gaap:SalesRevenueNet` | `{"2017-12-31":6004955.0,"2016-12-31":4698638.0}` |
| Cost of sales | `us-gaap:CostOfRevenue` | `{"2017-12-31":4854216.0,"2016-12-31":3623516.0}` |

## 55. POWER SOLUTIONS INTERNATIONAL, INC. — t=2018

- Kategoria: `random_available_D5_fill`; sektor: `Industrials_Manufacturing`; SIC: `3510`.
- Anchor: `0001628280-20-006265`; statement: `CONSOLIDATED STATEMENTS OF OPERATIONS`; file: `R4.htm`.
- Resolver: `Net sales` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `496038000.0`; current `546076000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1137091/000162828020006265/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Net sales | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2019-12-31":546076000.0,"2018-12-31":496038000.0}` |
| Cost of sales | `us-gaap:CostOfGoodsAndServicesSold` | `{"2019-12-31":446188000.0,"2018-12-31":437269000.0}` |

## 56. Atomera Inc — t=2020

- Kategoria: `random_available_D5_fill`; sektor: `Technology`; SIC: `3674`.
- Anchor: `0001683168-22-001031`; statement: `Statements of Operations`; file: `R4.htm`.
- Resolver: `Revenue:` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `62000.0`; current `400000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1420520/000168316822001031/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue: | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2021-12-31":400000.0,"2020-12-31":62000.0}` |
| Cost of revenue | `us-gaap:CostOfGoodsAndServicesSold` | `{"2021-12-31":0.0,"2020-12-31":-13000.0}` |

## 57. NextTrip, Inc. — t=2021

- Kategoria: `random_available_D5_fill`; sektor: `Extended_Candidate`; SIC: `4700`.
- Anchor: `0001493152-23-009743`; statement: `Statements of Operations`; file: `R4.htm`.
- Resolver: `REVENUES` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `1651765.0`; current `630428.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/788611/000149315223009743/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| REVENUES | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2022-12-31":630428.0,"2021-12-31":1651765.0}` |
| COST OF REVENUE | `us-gaap:CostOfRevenue` | `{"2022-12-31":349930.0,"2021-12-31":559965.0}` |

## 58. POWERDYNE INTERNATIONAL, INC. — t=2022

- Kategoria: `random_available_D5_fill`; sektor: `Technology`; SIC: `7374`.
- Anchor: `0001493152-24-018248`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Revenues` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `1207168.0`; current `1452950.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1435617/000149315224018248/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenues | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2023-12-31":1452950.0,"2022-12-31":1207168.0}` |
| Cost of revenues | `us-gaap:CostOfGoodsAndServicesSold` | `{"2023-12-31":1022114.0,"2022-12-31":801040.0}` |

## 59. Fulgent Genetics, Inc. — t=2022

- Kategoria: `random_available_D5_fill`; sektor: `Extended_Candidate`; SIC: `8071`.
- Anchor: `0000950170-24-022233`; statement: `Consolidated Statements of Operations`; file: `R4.htm`.
- Resolver: `Revenue` / `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; comparative `618968000.0`; current `289213000.0`.
- [SEC statement](https://www.sec.gov/Archives/edgar/data/1674930/000095017024022233/R4.htm)

| Wiersz statement | Concept | Annual values by end date |
|---|---|---|
| Revenue | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `{"2023-12-31":289213000.0,"2022-12-31":618968000.0,"2021-12-31":992584000.0}` |
| Cost of revenue | `us-gaap:CostOfRevenue` | `{"2023-12-31":184757000.0,"2022-12-31":252067000.0,"2021-12-31":215533000.0}` |

from __future__ import annotations

from datetime import date
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import src.data.target_candidate_v2_pit as pit_module
from src.data.target_candidate_v2_pit import (
    continuity_ambiguity_screen,
    load_config,
    parse_scope,
    resolve_fiscal_year_sequence,
    semantic_vintage_ambiguity_screen,
    select_primitive_pair,
    select_tag_context,
    target_candidate_v2,
)
from src.data.revenue_statement_resolver import (
    evidence_rows,
    is_income_statement_metadata,
    parse_amount,
    parse_date_cell,
)


valid_evidence_payload = importlib.import_module(
    "src.data.15_download_revenue_statement_evidence"
).valid_evidence_payload


CONFIG = load_config()
SCOPE = parse_scope(CONFIG)


def record(tag: str, value: float, start: str, end: str, accession: str = "a1") -> dict:
    return {
        "tag": tag,
        "value": value,
        "accn": accession,
        "form": "10-K",
        "filed": "2022-02-01",
        "start": start,
        "end": end,
        "document_fiscal_year_focus": 2021,
        "document_fiscal_period_focus": "FY",
        "frame": "",
    }


def anchor(accession: str, report_end: str, records: list[dict], focus: int) -> dict:
    return {
        "accn": accession,
        "records": records,
        "report_end": date.fromisoformat(report_end),
        "document_period_end_date": report_end,
        "document_fiscal_year_focus": focus,
        "document_fiscal_period_focus": "FY",
        "filed": "2022-02-01",
        "accepted_at": "2022-02-01T12:00:00Z",
    }


def write_revenue_statement(
    directory: Path,
    *,
    tag: str,
    label: str,
    comparative: float,
    current: float,
    title_suffix: str = "",
    period_colspan: int = 1,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    summary = """<FilingSummary><MyReports><Report><ShortName>CONSOLIDATED STATEMENTS OF OPERATIONS</ShortName><LongName>Statement - CONSOLIDATED STATEMENTS OF OPERATIONS</LongName><Role>http://example.com/role/StatementOfIncome</Role><MenuCategory>Statements</MenuCategory><HtmlFileName>R2.htm</HtmlFileName></Report></MyReports></FilingSummary>"""
    filler = '<td class="fn"></td>' if period_colspan == 2 else ""
    statement = f"""<html><body><table class="report"><tr><th>CONSOLIDATED STATEMENTS OF OPERATIONS (USD $) {title_suffix}</th><th>12 Months Ended</th><th></th></tr><tr><th colspan="{period_colspan}">Dec 31, 2021</th><th colspan="{period_colspan}">Dec 31, 2020</th></tr><tr class="rou"><td class="pl"><a onclick="top.Show.showAR(this, 'defref_us-gaap_{tag}', window);">{label}</a></td><td class="nump">{current}</td>{filler}<td class="nump">{comparative}</td>{filler}</tr></table></body></html>"""
    (directory / "FilingSummary.xml").write_text(summary)
    (directory / "R2.htm").write_text(statement)


class PeriodValidationTests(unittest.TestCase):
    def test_standard_53_week_duration_is_valid(self) -> None:
        selected = select_tag_context(
            anchor(
                "a1",
                "2021-01-02",
                [record("NetIncomeLoss", 10.0, "2019-12-29", "2021-01-02")],
                2020,
            ),
            "NetIncomeLoss",
            date(2021, 1, 2),
            date(2019, 12, 29),
            "duration",
            SCOPE,
            "current_t1",
        )
        self.assertEqual(selected["status"], "selected")
        self.assertEqual(selected["duration_days"], 371)

    def test_duplicate_fiscal_focus_is_resolved_by_annual_sequence(self) -> None:
        anchors = [
            anchor("a1", "2022-01-31", [], 2022),
            anchor("a2", "2023-01-31", [], 2022),
            anchor("a3", "2024-01-31", [], 2023),
        ]
        resolved = resolve_fiscal_year_sequence(anchors, SCOPE)
        self.assertEqual(
            [item["resolved_fiscal_year"] for item in resolved], [2022, 2023, 2024]
        )


class SubmissionMetadataTests(unittest.TestCase):
    def test_historical_shard_supplies_acceptance_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            main = {
                "filings": {
                    "recent": {"accessionNumber": []},
                    "files": [{"name": "CIK0000000001-submissions-001.json"}],
                }
            }
            shard = {
                "accessionNumber": ["0000000001-20-000001"],
                "form": ["10-K"],
                "filingDate": ["2020-03-01"],
                "reportDate": ["2019-12-31"],
                "acceptanceDateTime": ["2020-03-01T21:00:00.000Z"],
                "primaryDocument": ["annual.htm"],
                "isXBRL": [1],
            }
            (directory / "CIK0000000001.json").write_text(json.dumps(main))
            (directory / "CIK0000000001-submissions-001.json").write_text(
                json.dumps(shard)
            )
            with patch.object(pit_module, "SUBMISSIONS_DIR", directory):
                metadata = pit_module.submission_metadata("0000000001")
        self.assertEqual(
            metadata["0000000001-20-000001"]["accepted_at"],
            "2020-03-01T21:00:00.000Z",
        )

    def test_sec_statement_cache_rejects_throttling_payloads(self) -> None:
        self.assertTrue(
            valid_evidence_payload(
                Path("FilingSummary.xml"),
                b"<FilingSummary><MyReports /></FilingSummary>",
            )
        )
        self.assertTrue(
            valid_evidence_payload(
                Path("R2.htm"), b'<html><table class="report"></table></html>'
            )
        )
        self.assertFalse(
            valid_evidence_payload(
                Path("FilingSummary.xml"),
                b"<html>Request Rate Threshold Exceeded</html>",
            )
        )
        self.assertFalse(
            valid_evidence_payload(
                Path("R2.htm"), b"<html>Request Rate Threshold Exceeded</html>"
            )
        )


class SemanticValidationTests(unittest.TestCase):
    def test_dotted_month_abbreviations_in_legacy_sec_reports_are_parsed(self) -> None:
        self.assertEqual(parse_date_cell("Dec. 31, 2014"), date(2014, 12, 31))
        self.assertEqual(parse_date_cell("Sept. 30, 2013"), date(2013, 9, 30))
        self.assertEqual(
            parse_amount("$ 20,247 us-gaap_SalesRevenueNet", 1_000_000.0),
            20_247_000_000.0,
        )

    def test_reversed_consolidated_statement_name_is_recognized(self) -> None:
        self.assertTrue(
            is_income_statement_metadata(
                {
                    "short_name": "Statements of Consolidated Operations",
                    "long_name": "Statement - Statements of Consolidated Operations",
                    "role": "http://example.com/role/StatementsOfConsolidatedOperations",
                }
            )
        )
        # Some issuers combine the income statement and comprehensive-income
        # statement. It is admissible metadata, but a revenue row must still
        # independently pass the strict row/concept/context checks.
        self.assertTrue(
            is_income_statement_metadata(
                {
                    "short_name": "Statements of Consolidated Comprehensive Income",
                    "long_name": "Statement - Statements of Consolidated Comprehensive Income",
                    "role": "http://example.com/role/StatementsOfConsolidatedComprehensiveIncome",
                }
            )
        )

    def test_share_count_scale_does_not_scale_monetary_revenue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="Revenues",
                label="Operating revenue",
                comparative=19_687_000_000,
                current=17_478_000_000,
                title_suffix="shares in Thousands",
            )
            row = evidence_rows(evidence)[0]
        self.assertEqual(row["statement_scale_label"], "units")
        self.assertEqual(row["amounts"]["2021-12-31"], 17_478_000_000)

    def test_period_colspan_maps_amount_and_footnote_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="Revenues",
                label="Revenues",
                comparative=18_376,
                current=18_095,
                title_suffix="In Millions, except Share data in Thousands",
                period_colspan=2,
            )
            row = evidence_rows(evidence)[0]
        self.assertEqual(row["statement_scale_label"], "millions")
        self.assertEqual(row["amounts"]["2021-12-31"], 18_095_000_000)
        self.assertEqual(row["amounts"]["2020-12-31"], 18_376_000_000)

    def test_rowspan_title_and_leading_footnote_column_do_not_shift_years(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / "FilingSummary.xml").write_text(
                "<FilingSummary><MyReports><Report>"
                "<ShortName>Consolidated Statements of Income</ShortName>"
                "<LongName>Statement - Consolidated Statements of Income</LongName>"
                "<Role>http://example.com/role/StatementOfIncome</Role>"
                "<MenuCategory>Statements</MenuCategory><HtmlFileName>R2.htm</HtmlFileName>"
                "</Report></MyReports></FilingSummary>"
            )
            (evidence / "R2.htm").write_text(
                "<html><body><table class='report'>"
                "<tr><th colspan='2' rowspan='2'>Consolidated Statements of Income "
                "- USD ($) $ in Thousands</th><th colspan='3'>12 Months Ended</th></tr>"
                "<tr><th>Dec. 29, 2018</th><th>Dec. 30, 2017</th>"
                "<th>Dec. 31, 2016</th></tr>"
                "<tr><td class='pl'><a onclick=\"top.Show.showAR(this, "
                "'defref_us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax', "
                "window);\">Net sales</a></td><td class='th'><sup>[1]</sup></td>"
                "<td class='nump'>$ 3,347,444</td><td class='nump'>$ 3,121,560</td>"
                "<td class='nump'>$ 3,045,797</td></tr></table></body></html>"
            )
            row = evidence_rows(evidence)[0]
        self.assertEqual(row["amounts"]["2018-12-29"], 3_347_444_000.0)
        self.assertEqual(row["amounts"]["2017-12-30"], 3_121_560_000.0)
        self.assertEqual(row["amounts"]["2016-12-31"], 3_045_797_000.0)

    def test_repeated_dates_across_dimension_columns_are_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / "FilingSummary.xml").write_text(
                "<FilingSummary><MyReports><Report>"
                "<ShortName>Consolidated Statements of Operations</ShortName>"
                "<LongName>Statement - Consolidated Statements of Operations</LongName>"
                "<Role>http://example.com/role/StatementOfIncome</Role>"
                "<MenuCategory>Statements</MenuCategory><HtmlFileName>R2.htm</HtmlFileName>"
                "</Report></MyReports></FilingSummary>"
            )
            (evidence / "R2.htm").write_text(
                "<html><body><table class='report'>"
                "<tr><th>CONSOLIDATED STATEMENTS OF OPERATIONS (USD $)</th></tr>"
                "<tr><th>Dec 31, 2021</th><th>Dec 31, 2021</th>"
                "<th>Dec 31, 2020</th><th>Dec 31, 2020</th></tr>"
                "<tr><td><a onclick=\"top.Show.showAR(this, 'defref_us-gaap_Revenues', window);\">"
                "Revenues</a></td><td>100</td><td>40</td><td>90</td><td>30</td></tr>"
                "</table></body></html>"
            )
            row = evidence_rows(evidence)[0]
        self.assertIsNone(row["amounts"]["2021-12-31"])
        self.assertIsNone(row["amounts"]["2020-12-31"])

    def test_revenue_uses_primary_statement_not_tag_priority(self) -> None:
        records = [
            record(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                100.0,
                "2020-01-01",
                "2020-12-31",
            ),
            record(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                110.0,
                "2021-01-01",
                "2021-12-31",
            ),
            record("SalesRevenueNet", 200.0, "2020-01-01", "2020-12-31"),
            record("SalesRevenueNet", 220.0, "2021-01-01", "2021-12-31"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="SalesRevenueNet",
                label="Total revenues",
                comparative=200.0,
                current=220.0,
            )
            result = select_primitive_pair(
                "revenues",
                CONFIG["primitive_concepts"]["revenues"],
                anchor("a1", "2021-12-31", records, 2021),
                anchor("a0", "2020-12-31", [], 2020),
                anchor("am1", "2019-12-31", [], 2019),
                SCOPE,
                evidence,
            )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["strategy"], "sales_revenue_net")
        self.assertEqual(
            result["semantic_diagnostic"], "primary_statement_revenue_confirmed"
        )

    def test_revenue_without_primary_statement_evidence_is_ambiguous(self) -> None:
        records = [
            record("Revenues", 100.0, "2020-01-01", "2020-12-31"),
            record("Revenues", 110.0, "2021-01-01", "2021-12-31"),
        ]
        result = select_primitive_pair(
            "revenues",
            CONFIG["primitive_concepts"]["revenues"],
            anchor("a1", "2021-12-31", records, 2021),
            anchor("a0", "2020-12-31", [], 2020),
            anchor("am1", "2019-12-31", [], 2019),
            SCOPE,
        )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["reason"], "primary_statement_evidence_unavailable")

    def test_component_revenue_label_is_rejected(self) -> None:
        records = [
            record(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                100.0,
                "2020-01-01",
                "2020-12-31",
            ),
            record(
                "RevenueFromContractWithCustomerExcludingAssessedTax",
                110.0,
                "2021-01-01",
                "2021-12-31",
            ),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="RevenueFromContractWithCustomerExcludingAssessedTax",
                label="Collaboration revenue",
                comparative=100.0,
                current=110.0,
            )
            result = select_primitive_pair(
                "revenues",
                CONFIG["primitive_concepts"]["revenues"],
                anchor("a1", "2021-12-31", records, 2021),
                anchor("a0", "2020-12-31", [], 2020),
                anchor("am1", "2019-12-31", [], 2019),
                SCOPE,
                evidence,
            )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["reason"], "primary_statement_revenue_not_confirmed")

    def test_admissible_total_is_selected_over_prohibited_component_row(self) -> None:
        records = [
            record("SalesRevenueNet", 20.0, "2020-01-01", "2020-12-31"),
            record("SalesRevenueNet", 22.0, "2021-01-01", "2021-12-31"),
            record("Revenues", 100.0, "2020-01-01", "2020-12-31"),
            record("Revenues", 110.0, "2021-01-01", "2021-12-31"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="SalesRevenueNet",
                label="Project revenue",
                comparative=20.0,
                current=22.0,
            )
            statement_path = evidence / "R2.htm"
            statement = statement_path.read_text()
            statement = statement.replace(
                "</table>",
                '<tr><td><a onclick="top.Show.showAR(this, '
                "'defref_us-gaap_Revenues', window);\">Total revenues</a></td>"
                "<td>110</td><td>100</td></tr></table>",
            )
            statement_path.write_text(statement)
            result = select_primitive_pair(
                "revenues",
                CONFIG["primitive_concepts"]["revenues"],
                anchor("a1", "2021-12-31", records, 2021),
                anchor("a0", "2020-12-31", [], 2020),
                anchor("am1", "2019-12-31", [], 2019),
                SCOPE,
                evidence,
            )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["strategy"], "revenues_general")
        self.assertEqual(result["comparative_t"]["value"], 100.0)
        self.assertEqual(result["current_t1"]["value"], 110.0)

    def test_goods_tag_is_rejected_when_services_component_is_present(self) -> None:
        records = [
            record("SalesRevenueGoodsNet", 100.0, "2020-01-01", "2020-12-31"),
            record("SalesRevenueGoodsNet", 110.0, "2021-01-01", "2021-12-31"),
            record("SalesRevenueServicesNet", 20.0, "2020-01-01", "2020-12-31"),
            record("SalesRevenueServicesNet", 22.0, "2021-01-01", "2021-12-31"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="SalesRevenueGoodsNet",
                label="Sales",
                comparative=100.0,
                current=110.0,
            )
            result = select_primitive_pair(
                "revenues",
                CONFIG["primitive_concepts"]["revenues"],
                anchor("a1", "2021-12-31", records, 2021),
                anchor("a0", "2020-12-31", [], 2020),
                anchor("am1", "2019-12-31", [], 2019),
                SCOPE,
                evidence,
            )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(
            result["reason"], "component_revenue_without_absent_complement"
        )

    def test_net_sales_is_rejected_when_financial_services_revenue_is_separate(
        self,
    ) -> None:
        records = [
            record("SalesRevenueNet", 100.0, "2020-01-01", "2020-12-31"),
            record("SalesRevenueNet", 110.0, "2021-01-01", "2021-12-31"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="SalesRevenueNet",
                label="Net sales",
                comparative=100.0,
                current=110.0,
            )
            statement_path = evidence / "R2.htm"
            statement_path.write_text(
                statement_path.read_text().replace(
                    "</table>",
                    '<tr><td><a onclick="top.Show.showAR(this, '
                    "'defref_us-gaap_FinancialServicesRevenue', window);\">"
                    "Financial services revenue</a></td><td>22</td><td>20</td>"
                    "</tr></table>",
                )
            )
            result = select_primitive_pair(
                "revenues",
                CONFIG["primitive_concepts"]["revenues"],
                anchor("a1", "2021-12-31", records, 2021),
                anchor("a0", "2020-12-31", [], 2020),
                anchor("am1", "2019-12-31", [], 2019),
                SCOPE,
                evidence,
            )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(
            result["reason"],
            "component_revenue_without_confirmed_consolidated_total",
        )

    def test_product_sales_is_rejected_when_licensing_revenue_is_separate(self) -> None:
        records = [
            record("SalesRevenueGoodsNet", 100.0, "2020-01-01", "2020-12-31"),
            record("SalesRevenueGoodsNet", 110.0, "2021-01-01", "2021-12-31"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="SalesRevenueGoodsNet",
                label="Revenue",
                comparative=100.0,
                current=110.0,
            )
            statement_path = evidence / "R2.htm"
            statement_path.write_text(
                statement_path.read_text().replace(
                    "</table>",
                    '<tr><td><a onclick="top.Show.showAR(this, '
                    "'defref_us-gaap_LicensesRevenue', window);\">"
                    "Licensing revenue</a></td><td>2</td><td>1</td>"
                    "</tr></table>",
                )
            )
            result = select_primitive_pair(
                "revenues",
                CONFIG["primitive_concepts"]["revenues"],
                anchor("a1", "2021-12-31", records, 2021),
                anchor("a0", "2020-12-31", [], 2020),
                anchor("am1", "2019-12-31", [], 2019),
                SCOPE,
                evidence,
            )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(
            result["reason"],
            "component_revenue_without_confirmed_consolidated_total",
        )

    def test_revenue_row_is_confirmed_when_it_equals_presented_component_sum(
        self,
    ) -> None:
        records = [
            record("Revenues", 100.0, "2020-01-01", "2020-12-31"),
            record("Revenues", 110.0, "2021-01-01", "2021-12-31"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="Revenues",
                label="Revenue",
                comparative=100.0,
                current=110.0,
            )
            statement_path = evidence / "R2.htm"
            statement_path.write_text(
                statement_path.read_text().replace(
                    "</table>",
                    '<tr><td><a onclick="top.Show.showAR(this, '
                    "'defref_us-gaap_SalesRevenueGoodsNet', window);\">"
                    "Product revenue</a></td><td>66</td><td>60</td></tr>"
                    '<tr><td><a onclick="top.Show.showAR(this, '
                    "'defref_us-gaap_SalesRevenueServicesNet', window);\">"
                    "Service revenue</a></td><td>44</td><td>40</td>"
                    "</tr></table>",
                )
            )
            result = select_primitive_pair(
                "revenues",
                CONFIG["primitive_concepts"]["revenues"],
                anchor("a1", "2021-12-31", records, 2021),
                anchor("a0", "2020-12-31", [], 2020),
                anchor("am1", "2019-12-31", [], 2019),
                SCOPE,
                evidence,
            )
        self.assertEqual(result["status"], "selected")

    def test_net_revenue_is_not_blocked_by_disclosed_gross_excise_basis(self) -> None:
        tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
        records = [
            record(tag, 100.0, "2020-01-01", "2020-12-31"),
            record(tag, 110.0, "2021-01-01", "2021-12-31"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag=tag,
                label="Net revenues",
                comparative=100.0,
                current=110.0,
            )
            statement_path = evidence / "R2.htm"
            statement_path.write_text(
                statement_path.read_text().replace(
                    "</table>",
                    '<tr><td><a onclick="top.Show.showAR(this, '
                    "'defref_us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax', "
                    'window);">Revenues including excise taxes</a></td>'
                    "<td>330</td><td>300</td></tr></table>",
                )
            )
            result = select_primitive_pair(
                "revenues",
                CONFIG["primitive_concepts"]["revenues"],
                anchor("a1", "2021-12-31", records, 2021),
                anchor("a0", "2020-12-31", [], 2020),
                anchor("am1", "2019-12-31", [], 2019),
                SCOPE,
                evidence,
            )
        self.assertEqual(result["status"], "selected")

    def test_extension_total_blocks_standard_tag_component(self) -> None:
        records = [
            record("Revenues", 10.0, "2020-01-01", "2020-12-31"),
            record("Revenues", 11.0, "2021-01-01", "2021-12-31"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="Revenues",
                label="Revenue",
                comparative=10.0,
                current=11.0,
            )
            statement_path = evidence / "R2.htm"
            statement = statement_path.read_text()
            statement = statement.replace(
                "</table>",
                '<tr><td><a onclick="top.Show.showAR(this, '
                "'defref_example_TotalRevenue', window);\">Total revenues</a></td>"
                "<td>110</td><td>100</td></tr></table>",
            )
            statement_path.write_text(statement)
            result = select_primitive_pair(
                "revenues",
                CONFIG["primitive_concepts"]["revenues"],
                anchor("a1", "2021-12-31", records, 2021),
                anchor("a0", "2020-12-31", [], 2020),
                anchor("am1", "2019-12-31", [], 2019),
                SCOPE,
                evidence,
            )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["reason"], "multiple_primary_statement_revenue_rows")

    def test_unparsed_total_row_still_blocks_another_revenue_candidate(self) -> None:
        records = [
            record("Revenues", 10.0, "2020-01-01", "2020-12-31"),
            record("Revenues", 11.0, "2021-01-01", "2021-12-31"),
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence = Path(temporary_directory)
            write_revenue_statement(
                evidence,
                tag="Revenues",
                label="Revenue",
                comparative=10.0,
                current=11.0,
            )
            statement_path = evidence / "R2.htm"
            statement = statement_path.read_text()
            statement = statement.replace(
                "</table>",
                '<tr><td><a onclick="top.Show.showAR(this, '
                "'defref_example_TotalRevenue', window);\">Total revenues</a></td>"
                "<td>110</td><td>—</td></tr></table>",
            )
            statement_path.write_text(statement)
            result = select_primitive_pair(
                "revenues",
                CONFIG["primitive_concepts"]["revenues"],
                anchor("a1", "2021-12-31", records, 2021),
                anchor("a0", "2020-12-31", [], 2020),
                anchor("am1", "2019-12-31", [], 2019),
                SCOPE,
                evidence,
            )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["reason"], "multiple_primary_statement_revenue_rows")

    def test_multiple_values_for_same_best_context_are_ambiguous(self) -> None:
        records = [
            record("Assets", 100.0, "", "2020-12-31"),
            record("Assets", 101.0, "", "2020-12-31"),
            record("Assets", 120.0, "", "2021-12-31"),
        ]
        result = select_primitive_pair(
            "assets",
            CONFIG["primitive_concepts"]["assets"],
            anchor("a1", "2021-12-31", records, 2021),
            anchor("a0", "2020-12-31", [], 2020),
            None,
            SCOPE,
        )
        self.assertEqual(result["status"], "ambiguous")

    def test_same_strategy_and_valid_periods_are_selected(self) -> None:
        records = [
            record("Assets", 100.0, "", "2020-12-31"),
            record("Assets", 120.0, "", "2021-12-31"),
        ]
        result = select_primitive_pair(
            "assets",
            CONFIG["primitive_concepts"]["assets"],
            anchor("a1", "2021-12-31", records, 2021),
            anchor("a0", "2020-12-31", [], 2020),
            None,
            SCOPE,
        )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["strategy"], "assets_direct")
        self.assertEqual(result["comparative_t"]["value"], 100.0)
        self.assertEqual(result["current_t1"]["value"], 120.0)

    def test_derived_liabilities_preserve_component_provenance(self) -> None:
        records = [
            record("LiabilitiesAndStockholdersEquity", 100.0, "", "2020-12-31"),
            record(
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                40.0,
                "",
                "2020-12-31",
            ),
            record("LiabilitiesAndStockholdersEquity", 120.0, "", "2021-12-31"),
            record(
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                45.0,
                "",
                "2021-12-31",
            ),
        ]
        result = select_primitive_pair(
            "liabilities",
            CONFIG["primitive_concepts"]["liabilities"],
            anchor("a1", "2021-12-31", records, 2021),
            anchor("a0", "2020-12-31", [], 2020),
            None,
            SCOPE,
        )
        self.assertEqual(result["status"], "selected")
        comparative = result["comparative_t"]
        self.assertEqual(comparative["value"], 60.0)
        self.assertEqual(comparative["source_values"], "100.0;40.0")
        self.assertEqual(comparative["source_accessions"], "a1;a1")

    def test_parent_equity_liabilities_fallback_is_blocked_by_nonzero_nci(self) -> None:
        records = [
            record("LiabilitiesAndStockholdersEquity", 100.0, "", "2020-12-31"),
            record("StockholdersEquity", 40.0, "", "2020-12-31"),
            record("MinorityInterest", 5.0, "", "2020-12-31"),
            record("LiabilitiesAndStockholdersEquity", 120.0, "", "2021-12-31"),
            record("StockholdersEquity", 45.0, "", "2021-12-31"),
            record("MinorityInterest", 6.0, "", "2021-12-31"),
        ]
        result = select_primitive_pair(
            "liabilities",
            CONFIG["primitive_concepts"]["liabilities"],
            anchor("a1", "2021-12-31", records, 2021),
            anchor("a0", "2020-12-31", [], 2020),
            None,
            SCOPE,
        )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["reason"], "no_common_semantic_strategy")


class TargetAndContinuityTests(unittest.TestCase):
    def test_frozen_target_metadata_and_definition(self) -> None:
        frozen = CONFIG["frozen_target"]
        self.assertEqual(frozen["id"], "target_candidate_v2_pit_b")
        self.assertEqual(frozen["version"], "1.0.0")
        self.assertEqual(frozen["status"], "frozen")
        self.assertEqual(
            frozen["freeze_scope"], "target_definition_and_pit_b_extraction"
        )
        self.assertFalse(frozen["dataset_frozen"])
        self.assertFalse(frozen["feature_pipeline_frozen"])
        self.assertFalse(frozen["research_universe_frozen"])
        self.assertEqual(
            frozen["signals"],
            {
                "D1_roa_drop_pp": 0.03,
                "D2_ocf_assets_drop_pp": 0.03,
                "D3_current_ratio_relative_drop": 0.20,
                "D4_liabilities_assets_increase_pp": 0.10,
                "D5_revenues_relative_drop": 0.10,
            },
        )
        self.assertEqual(frozen["target"]["positive_if_score_at_least"], 3)
        self.assertEqual(
            frozen["mandatory_robustness_checks"]["score_thresholds"], [2, 4]
        )
        self.assertEqual(
            frozen["mandatory_robustness_checks"]["operating_performance"],
            {
                "definition": "max(D1_roa, D2_ocf_assets)",
                "alternative_score_positive_if_at_least": 3,
            },
        )
        self.assertEqual(
            frozen["unavailable_target_policy"],
            {
                "missing": "NA",
                "ambiguous": "NA",
                "hard_exclude": "NA",
                "map_unavailable_to_zero": False,
            },
        )

    def test_frozen_scope_excludes_test_from_target_freeze_gate(self) -> None:
        self.assertEqual(SCOPE.feature_year_start, 2011)
        self.assertEqual(SCOPE.feature_year_end, 2022)
        self.assertEqual(SCOPE.validation_years, frozenset({2021, 2022}))
        self.assertEqual(CONFIG["scope"]["test_years"], [2023, 2024])
        self.assertFalse(
            CONFIG["frozen_target"]["development_audit"][
                "feature_years_2023_2024_used_in_pit_b_freeze_gate"
            ]
        )

    def test_target_candidate_v2_thresholds_are_unchanged(self) -> None:
        base = {
            "assets": 100.0,
            "liabilities": 40.0,
            "current_assets": 100.0,
            "current_liabilities": 50.0,
            "revenues": 100.0,
            "net_income": 10.0,
            "operating_cash_flow": 10.0,
        }
        nxt = {
            "assets": 100.0,
            "liabilities": 51.0,
            "current_assets": 80.0,
            "current_liabilities": 50.0,
            "revenues": 89.0,
            "net_income": 6.9,
            "operating_cash_flow": 6.9,
        }
        signals, score, target, _, _ = target_candidate_v2(base, nxt, minimum=0.0)
        self.assertEqual(
            signals,
            {
                "D1_roa": 1,
                "D2_ocf_assets": 1,
                "D3_current_ratio": 1,
                "D4_liabilities_assets": 1,
                "D5_revenues": 1,
            },
        )
        self.assertEqual(score, 5)
        self.assertEqual(target, 1)

    def test_frozen_main_target_requires_three_signals(self) -> None:
        base = {
            "assets": 100.0,
            "liabilities": 40.0,
            "current_assets": 100.0,
            "current_liabilities": 50.0,
            "revenues": 100.0,
            "net_income": 10.0,
            "operating_cash_flow": 10.0,
        }
        two_signal_next = {
            **base,
            "net_income": 6.9,
            "operating_cash_flow": 6.9,
        }
        three_signal_next = {**two_signal_next, "revenues": 89.0}

        _, score_two, target_two, _, _ = target_candidate_v2(
            base, two_signal_next, minimum=0.0
        )
        _, score_three, target_three, _, _ = target_candidate_v2(
            base, three_signal_next, minimum=0.0
        )
        self.assertEqual((score_two, target_two), (2, 0))
        self.assertEqual((score_three, target_three), (3, 1))

    def test_material_multi_primitive_rebasing_is_ambiguous(self) -> None:
        base = {
            "assets": 100.0,
            "liabilities": 50.0,
            "current_assets": 40.0,
            "current_liabilities": 20.0,
            "revenues": 100.0,
            "net_income": 5.0,
            "operating_cash_flow": 8.0,
        }
        revised = {**base, "assets": 300.0, "liabilities": 180.0, "revenues": 400.0}
        ambiguous, components = continuity_ambiguity_screen(
            base, revised, CONFIG, minimum=1.0
        )
        self.assertTrue(ambiguous)
        self.assertEqual(components, ["assets", "liabilities", "revenues"])

    def test_two_material_components_are_now_conservatively_ambiguous(self) -> None:
        base = {"assets": 100.0, "liabilities": 50.0}
        revised = {"assets": 300.0, "liabilities": 180.0}
        ambiguous, components = continuity_ambiguity_screen(
            base, revised, CONFIG, minimum=1.0
        )
        self.assertTrue(ambiguous)
        self.assertEqual(components, ["assets", "liabilities"])

    def test_exact_cross_vintage_sign_inversion_is_ambiguous(self) -> None:
        reasons = semantic_vintage_ambiguity_screen(
            {"net_income": -1_627_628.0, "operating_cash_flow": -137_788.0},
            {"net_income": 1_627_628.0, "operating_cash_flow": -137_788.0},
            CONFIG,
        )
        self.assertEqual(reasons, ["net_income:cross_vintage_exact_sign_inversion"])

    def test_real_signed_revision_is_not_mistaken_for_sign_inversion(self) -> None:
        reasons = semantic_vintage_ambiguity_screen(
            {"net_income": -1_000_000.0},
            {"net_income": 900_000.0},
            CONFIG,
        )
        self.assertEqual(reasons, [])


if __name__ == "__main__":
    unittest.main()

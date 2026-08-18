from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import pandas as pd

from src.data.historical_research_universe import (
    add_comparison_statuses,
    build_historical_anchors,
    classify_historical_sic,
    load_official_sic_description_map,
    load_policy,
    parse_master_index,
    parse_submission_header,
    parse_submission_header_registrants,
)
from src.data.registrant_role_resolution import (
    apply_registrant_role_resolution,
    connected_economic_group_map,
)


POLICY = load_policy()


def master_row(accession: str, cik10: str = "0000001001") -> dict[str, object]:
    return {
        "accession": accession,
        "cik10_master": cik10,
        "company_name_master": "HISTORICAL CO",
        "form_master": "10-K",
        "filed_master": "2022-02-15",
        "archive_filename": f"edgar/data/1001/{accession}.txt",
        "index_year": 2022,
        "index_quarter": 1,
    }


def sub_row(
    accession: str,
    *,
    accepted: str,
    sic: str = "2834",
) -> dict[str, object]:
    return {
        "accession": accession,
        "cik10_sub": "0000001001",
        "name": "HISTORICAL CO",
        "sic": sic,
        "afs": "2",
        "fye": "1231",
        "form": "10-K",
        "period": "20211231",
        "fy": "2021",
        "fp": "FY",
        "filed": "20220215",
        "accepted": accepted,
        "prevrpt": "0",
        "instance": "historical-20211231.htm",
        "nciks": "1",
        "aciks": "",
        "fsds_source_year": 2022,
        "fsds_source_quarter": 1,
    }


class HistoricalResearchUniverseTests(unittest.TestCase):
    def test_official_sic_description_parser(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sic.html"
            path.write_text(
                "<table><tr><th>SIC Code</th><th>Office</th><th>Industry Title</th></tr>"
                "<tr><td>7372</td><td>Technology</td><td>PREPACKAGED SOFTWARE</td>"
                "</tr></table>",
                encoding="utf-8",
            )
            result = load_official_sic_description_map(path)
        self.assertEqual(result, {7372: "PREPACKAGED SOFTWARE"})

    def test_master_index_accepts_only_exact_original_10k(self) -> None:
        text = "\n".join(
            [
                "CIK|Company Name|Form Type|Date Filed|Filename",
                "--------------------------------------------------------------------------------",
                "1001|A CO|10-K|2022-02-01|edgar/data/1001/0000001001-22-000001.txt",
                "1001|A CO|10-K/A|2022-02-02|edgar/data/1001/0000001001-22-000002.txt",
                "1001|A CO|10-KT|2022-02-03|edgar/data/1001/0000001001-22-000003.txt",
            ]
        )
        result = parse_master_index(
            text,
            index_year=2022,
            index_quarter=1,
            qualifying_forms=frozenset({"10-K"}),
        )
        self.assertEqual(result["accession"].tolist(), ["0000001001-22-000001"])

    def test_submission_header_parses_same_accession_metadata(self) -> None:
        text = """<SEC-HEADER>
<ACCESSION-NUMBER>0000001001-22-000001
<ACCEPTANCE-DATETIME>20220215160507
<PERIOD>20211231
<FILING-DATE>20220215
<COMPANY-DATA>
<CONFORMED-NAME>HISTORICAL CO
<ASSIGNED-SIC>2834
<FISCAL-YEAR-END>1231
</SEC-HEADER>"""
        parsed = parse_submission_header(text)
        self.assertEqual(parsed["accession_header"], "0000001001-22-000001")
        self.assertEqual(parsed["accepted_header"], "2022-02-15 16:05:07")
        self.assertEqual(parsed["period_header"], "2021-12-31")
        self.assertEqual(parsed["sic_header"], "2834")

    def test_joint_filing_sic_is_paired_to_each_registrant_cik(self) -> None:
        text = """<SEC-HEADER>
<ACCESSION-NUMBER>0000001001-22-000001
<ACCEPTANCE-DATETIME>20220215160507
<PERIOD>20211231
<FILING-DATE>20220215
<FILER>
<COMPANY-DATA>
<CONFORMED-NAME>PRIMARY CO
<CIK>0000001001
<ASSIGNED-SIC>2834
<FISCAL-YEAR-END>1231
</COMPANY-DATA>
<FILER>
<COMPANY-DATA>
<CONFORMED-NAME>CO REGISTRANT
<CIK>0000001002
<ASSIGNED-SIC>6021
<FISCAL-YEAR-END>1231
</COMPANY-DATA>
</SEC-HEADER>"""
        parsed = parse_submission_header_registrants(text)
        by_cik = {row["cik10_header"]: row for row in parsed}
        self.assertEqual(by_cik["0000001001"]["sic_header"], "2834")
        self.assertEqual(by_cik["0000001002"]["sic_header"], "6021")

    def test_missing_historical_sic_is_ambiguous(self) -> None:
        result = classify_historical_sic("", "", POLICY)
        self.assertEqual(result["membership_status"], "ambiguous")
        self.assertEqual(result["membership_reason"], "missing_or_invalid_historical_sic")

    def test_financials_are_excluded_using_historical_sic(self) -> None:
        result = classify_historical_sic("6021", "National Commercial Banks", POLICY)
        self.assertEqual(result["membership_status"], "excluded")
        self.assertEqual(result["research_sector"], "Excluded_Financials_Insurance_RealEstate")

    def test_earliest_original_10k_is_company_year_anchor(self) -> None:
        accession_early = "0000001001-22-000001"
        accession_late = "0000001001-22-000009"
        master = pd.DataFrame(
            [master_row(accession_late), master_row(accession_early)]
        )
        sub = pd.DataFrame(
            [
                sub_row(accession_late, accepted="20220217120000"),
                sub_row(accession_early, accepted="20220215160507"),
            ]
        )
        anchors, unresolved = build_historical_anchors(
            master, sub, pd.DataFrame(), {2834: "Pharmaceutical Preparations"}, POLICY
        )
        self.assertTrue(unresolved.empty)
        self.assertEqual(len(anchors), 1)
        self.assertEqual(anchors.iloc[0]["accession"], accession_early)
        self.assertEqual(anchors.iloc[0]["anchor_candidate_count"], 2)
        self.assertEqual(anchors.iloc[0]["membership_status"], "eligible")
        self.assertEqual(anchors.iloc[0]["x_t_status"], "not_built")

    def test_conflicting_same_accession_sic_is_not_guessed(self) -> None:
        accession = "0000001001-22-000001"
        headers = pd.DataFrame(
            [
                {
                    "accession": accession,
                    "cik10_header": "0000001001",
                    "sic_header": "6021",
                }
            ]
        )
        anchors, _ = build_historical_anchors(
            pd.DataFrame([master_row(accession)]),
            pd.DataFrame([sub_row(accession, accepted="20220215160507", sic="2834")]),
            headers,
            {},
            POLICY,
        )
        row = anchors.iloc[0]
        self.assertEqual(row["membership_status"], "ambiguous")
        self.assertIn("historical_sic_conflict", row["membership_reason"])
        self.assertEqual(row["historical_sic_source"], "conflict")

    def test_joint_filing_does_not_copy_primary_sic_to_co_registrant(self) -> None:
        accession = "0000001001-22-000001"
        second_master = master_row(accession, cik10="0000001002")
        second_master["company_name_master"] = "CO REGISTRANT"
        headers = pd.DataFrame(
            [
                {
                    "accession": accession,
                    "cik10_header": "0000001001",
                    "sic_header": "2834",
                },
                {
                    "accession": accession,
                    "cik10_header": "0000001002",
                    "sic_header": "6021",
                },
            ]
        )
        anchors, _ = build_historical_anchors(
            pd.DataFrame([master_row(accession), second_master]),
            pd.DataFrame([sub_row(accession, accepted="20220215160507")]),
            headers,
            {
                2834: "Pharmaceutical Preparations",
                6021: "National Commercial Banks",
            },
            POLICY,
        )
        by_cik = anchors.set_index("cik10")
        self.assertEqual(by_cik.loc["0000001001", "historical_sic"], 2834)
        self.assertEqual(by_cik.loc["0000001002", "historical_sic"], 6021)
        self.assertEqual(by_cik.loc["0000001001", "membership_status"], "eligible")
        self.assertEqual(by_cik.loc["0000001002", "membership_status"], "excluded")
        self.assertTrue(by_cik.loc["0000001002", "joint_filing_flag"])

    def test_current_ticker_and_target_do_not_change_membership(self) -> None:
        accession = "0000001001-22-000001"
        anchors, _ = build_historical_anchors(
            pd.DataFrame([master_row(accession)]),
            pd.DataFrame([sub_row(accession, accepted="20220215160507")]),
            pd.DataFrame(),
            {2834: "Pharmaceutical Preparations"},
            POLICY,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_path = root / "old.csv"
            ticker_path = root / "tickers.csv"
            target_path = root / "target.csv"
            pd.DataFrame({"cik10": ["0000009999"]}).to_csv(old_path, index=False)
            pd.DataFrame({"cik10": ["0000009999"]}).to_csv(ticker_path, index=False)
            pd.DataFrame(
                columns=["cik10", "feature_year", "target_status"]
            ).to_csv(target_path, index=False)
            result = add_comparison_statuses(
                anchors, old_path, ticker_path, target_path
            )
        row = result.iloc[0]
        self.assertEqual(row["membership_status"], "eligible")
        self.assertFalse(row["in_current_ticker_snapshot"])
        self.assertEqual(row["target_status"], "not_computed")

    def test_joint_duplicate_is_removed_from_eligible_but_kept_as_provenance(self) -> None:
        accession = "0000001001-22-000001"
        universe = pd.DataFrame(
            {
                "accession": [accession, accession],
                "feature_year": [2021, 2021],
                "cik10": ["0000001001", "0000001002"],
                "registrant_role": [
                    "primary_xbrl_registrant",
                    "co_registrant_or_non_xbrl_registrant",
                ],
                "joint_filing_flag": [True, True],
                "membership_status": ["eligible", "eligible"],
                "membership_reason": ["", ""],
            }
        )
        common = {
            "accession": accession,
            "feature_year": 2021,
            "scope_status": "resolved",
            "scope_reason": "manual_single_statement_scope",
            "statement_entity_ciks": "0000001001",
            "economic_statement_scope_id": f"{accession}:0000001001",
            "manual_evidence": "One audited consolidated annual statement suite.",
        }
        detail = pd.DataFrame(
            [
                {
                    **common,
                    "cik10": "0000001001",
                    "registrant_role_resolved": "joint_primary_registrant",
                    "economic_entity_status": (
                        "separate_reporting_entity_with_own_statements"
                    ),
                    "recommended_membership_action": (
                        "retain_one_economic_entity"
                    ),
                    "economic_entity_reason": "registrant_matches_statement_scope",
                },
                {
                    **common,
                    "cik10": "0000001002",
                    "registrant_role_resolved": "joint_co_registrant",
                    "economic_entity_status": (
                        "co_registrant_sharing_same_consolidated_statements"
                    ),
                    "recommended_membership_action": (
                        "exclude_duplicate_registrant_row"
                    ),
                    "economic_entity_reason": "no_distinct_statement_scope",
                },
            ]
        )
        filing_registrants = pd.DataFrame(
            {
                "accession": [accession, accession],
                "cik10": ["0000001001", "0000001002"],
            }
        )
        result, diagnostics = apply_registrant_role_resolution(
            universe,
            detail,
            filing_registrants,
            expected_action_counts={
                "retain_one_economic_entity": 1,
                "exclude_duplicate_registrant_row": 1,
            },
        )
        by_cik = result.set_index("cik10")
        self.assertEqual(by_cik.loc["0000001001", "membership_status"], "eligible")
        self.assertEqual(by_cik.loc["0000001002", "membership_status"], "excluded")
        self.assertEqual(
            by_cik.loc["0000001002", "membership_reason"],
            "duplicate_registrant_same_statement_scope",
        )
        self.assertEqual(
            by_cik.loc["0000001002", "representative_cik"], "0000001001"
        )
        self.assertEqual(
            by_cik.loc["0000001001", "linked_co_registrant_ciks"],
            "0000001002",
        )
        self.assertEqual(diagnostics["eligible_statement_scope_year_duplicates"], 0)

    def test_connected_group_does_not_change_membership(self) -> None:
        filing_registrants = pd.DataFrame(
            {
                "accession": ["a", "a", "b", "b"],
                "cik10": ["0000000001", "0000000002", "0000000002", "0000000003"],
            }
        )
        groups, _ = connected_economic_group_map(filing_registrants)
        self.assertEqual(groups["0000000001"], groups["0000000003"])


if __name__ == "__main__":
    unittest.main()

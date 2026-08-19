from __future__ import annotations

from datetime import date
import math
from pathlib import Path
import tempfile
import unittest

from src.data.research_universe_target_application import verify_frozen_inputs
from src.data.x_t_pit import (
    PRIMITIVES,
    apply_negative_sign_review,
    exact_anchor,
    feature_names,
    feature_result,
    load_config,
    load_negative_sign_review,
    load_universe,
    output_columns,
    prediction_timestamp,
    process_eligible_row,
    scope_xbrl_instance_records,
)


class PointInTimeXtV1PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config()

    def test_frozen_dependencies_remain_exact(self) -> None:
        hashes = verify_frozen_inputs(self.config)
        self.assertEqual(
            hashes["universe_artifact_sha256"],
            "a449c8145d1f46f954f12b1dfc079bb0b367c4f7f5edf3332a983ad7c1fb8182",
        )
        self.assertEqual(
            hashes["target_artifact_sha256"],
            "473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff",
        )

    def test_only_pre_registered_L_D_R_blocks_exist(self) -> None:
        self.assertEqual(set(self.config["blocks"]), {"L", "D", "R"})
        self.assertEqual(
            self.config["pre_registered_model_comparisons"],
            [["L"], ["L", "D"], ["L", "D", "R"]],
        )
        self.assertFalse(self.config["block_selection_may_use_test_set"])
        self.assertFalse(self.config["extension_block"]["implemented"])

    def test_raw_policy_has_no_preprocessing_or_models(self) -> None:
        self.assertTrue(self.config["x_t"]["raw_only"])
        self.assertFalse(any(self.config["x_t"]["preprocessing"].values()))
        self.assertFalse(self.config["x_t"]["models_trained"])
        self.assertFalse(
            self.config["x_t"]["test_used_for_policy_or_resolver_decisions"]
        )
        self.assertFalse(self.config["point_in_time"]["amendments_allowed"])
        self.assertFalse(self.config["point_in_time"]["later_filings_allowed"])
        self.assertFalse(
            self.config["point_in_time"]["later_filing_feature_fallback_allowed"]
        )

    def test_negative_sign_review_is_complete_and_development_only(self) -> None:
        decisions = load_negative_sign_review(self.config)
        self.assertEqual(len(decisions), 25)
        self.assertEqual(
            sum(item["action"] == "retain" for item in decisions.values()), 5
        )
        self.assertEqual(
            sum(item["action"] == "ambiguous_na" for item in decisions.values()),
            20,
        )
        self.assertEqual(
            sum(
                item["outcome"] == "xbrl_semantic_or_context_error"
                for item in decisions.values()
            ),
            16,
        )
        self.assertEqual(
            sum(item["outcome"] == "unresolved" for item in decisions.values()),
            4,
        )
        self.assertTrue(
            all(2011 <= int(key[0].rsplit("-", 1)[1]) <= 2022 for key in decisions)
        )

    def test_negative_sign_review_fails_closed_without_sign_correction(self) -> None:
        selection = {
            "value": -100.0,
            "status": "selected",
            "reason": "source_selected",
            "tag": "Assets",
            "accn": "0000000001-20-000001",
        }
        decision = {
            "selected_value_before": -100.0,
            "action": "ambiguous_na",
            "reason": "unresolved_test_case",
        }
        reviewed = apply_negative_sign_review(selection, decision)
        self.assertEqual(reviewed["status"], "ambiguous")
        self.assertIsNone(reviewed["value"])
        self.assertEqual(reviewed["tag"], "Assets")
        self.assertEqual(reviewed["accn"], selection["accn"])
        self.assertEqual(
            reviewed["reason"],
            "manual_primary_statement_sign_review:unresolved_test_case",
        )

    def test_output_schema_contains_no_target_or_t_plus_1_provenance(self) -> None:
        columns = output_columns(self.config)
        self.assertFalse(any("target" in column.lower() for column in columns))
        self.assertFalse(any("current_t1" in column.lower() for column in columns))
        self.assertFalse(any("anchor_t1" in column.lower() for column in columns))
        self.assertNotIn("economic_group_id", feature_names(self.config))
        self.assertNotIn("historical_sic", feature_names(self.config))
        self.assertNotIn("research_sector", feature_names(self.config))

    def test_accepted_timestamp_is_normalized_to_eastern_time(self) -> None:
        timestamp, precision, lower = prediction_timestamp(
            {"accepted_at": "2022-07-21 11:04:00", "filed": "2022-07-21"}
        )
        self.assertEqual(timestamp, "2022-07-21T11:04:00-04:00")
        self.assertEqual(precision, "accepted_timestamp_et")
        self.assertFalse(lower)

    def test_aware_accepted_timestamp_is_converted_to_eastern_time(self) -> None:
        timestamp, precision, lower = prediction_timestamp(
            {"accepted_at": "2022-07-21T15:04:00Z", "filed": "2022-07-21"}
        )
        self.assertEqual(timestamp, "2022-07-21T11:04:00-04:00")
        self.assertEqual(precision, "accepted_timestamp_et")
        self.assertFalse(lower)

    def test_missing_accepted_timestamp_uses_next_day_midnight_et(self) -> None:
        timestamp, precision, lower = prediction_timestamp(
            {"accepted_at": "", "filed": "2020-12-31"}
        )
        self.assertEqual(timestamp, "2021-01-01T00:00:00-05:00")
        self.assertEqual(precision, "filed_date_next_day_midnight_et")
        self.assertTrue(lower)

    def test_positive_near_zero_denominator_is_not_excluded(self) -> None:
        selected = {"status": "selected", "reason": "ok"}
        result = feature_result(
            block="L",
            selections=[selected, selected],
            source_primitives=["net_income", "assets"],
            source_roles="current_t",
            prediction_at="2020-01-01T00:00:00-05:00",
            precision="accepted_timestamp_et",
            formula=lambda: 5.0 / 500.0,
            denominator_values=[("assets", 500.0)],
            denominator_condition=lambda value: value > 0,
            near_zero=1000.0,
        )
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["near_zero_denominator_flag"])
        self.assertTrue(math.isclose(result["value"], 0.01))

    def test_nonpositive_denominator_is_not_computable(self) -> None:
        selected = {"status": "selected", "reason": "ok"}
        result = feature_result(
            block="L",
            selections=[selected, selected],
            source_primitives=["net_income", "assets"],
            source_roles="current_t",
            prediction_at="2020-01-01T00:00:00-05:00",
            precision="accepted_timestamp_et",
            formula=lambda: 1.0,
            denominator_values=[("assets", 0.0)],
            denominator_condition=lambda value: value > 0,
        )
        self.assertEqual(result["status"], "not_computable")
        self.assertIn("nonpositive_denominator", result["reason"])

    def test_exact_anchor_uses_only_frozen_accession_records(self) -> None:
        source = {
            "accession": "0000000001-20-000001",
            "period_end": "2019-12-31",
            "form": "10-K",
            "filed": "2020-02-01",
            "accepted_at": "2020-02-01 12:00:00",
            "feature_year": 2019,
            "document_fiscal_year_focus": 2019,
            "document_fiscal_period_focus": "FY",
            "xbrl_instance": "example.xml",
        }
        record = {
            "tag": "Assets",
            "value": 100.0,
            "accn": source["accession"],
            "form": "10-K",
            "filed": "2020-02-01",
            "start": "",
            "end": "2019-12-31",
            "document_fiscal_year_focus": 2019,
            "document_fiscal_period_focus": "FY",
            "frame": "CY2019Q4I",
        }
        scope = type(
            "Scope",
            (),
            {
                "annual_period_min_days": 300,
                "annual_period_max_days": 400,
                "period_start_tolerance_days": 14,
            },
        )()
        anchor, status, _ = exact_anchor(
            source, {source["accession"]: [record]}, scope
        )
        self.assertEqual(status, "available")
        self.assertEqual(anchor["accn"], source["accession"])
        self.assertEqual({item["accn"] for item in anchor["records"]}, {source["accession"]})

    def test_standard_52_week_period_end_is_allowed_within_tolerance(self) -> None:
        source = {
            "accession": "0000000001-20-000001",
            "period_end": "2019-12-31",
            "form": "10-K",
            "filed": "2020-02-01",
            "accepted_at": "2020-02-01 12:00:00",
            "feature_year": 2019,
            "document_fiscal_year_focus": 2019,
            "document_fiscal_period_focus": "FY",
            "xbrl_instance": "example.xml",
        }
        record = {
            "tag": "Assets",
            "value": 100.0,
            "accn": source["accession"],
            "form": "10-K",
            "filed": "2020-02-01",
            "start": "2018-12-30",
            "end": "2019-12-29",
            "document_fiscal_year_focus": 2019,
            "document_fiscal_period_focus": "FY",
            "frame": "CY2019Q4I",
        }
        scope = type(
            "Scope",
            (),
            {
                "annual_period_min_days": 300,
                "annual_period_max_days": 400,
                "period_start_tolerance_days": 14,
            },
        )()
        anchor, status, _ = exact_anchor(
            source, {source["accession"]: [record]}, scope
        )
        self.assertEqual(status, "available")
        self.assertEqual(anchor["report_end"].isoformat(), "2019-12-29")
        self.assertEqual(anchor["frozen_universe_period_end_delta_days"], 2)

    def test_non_original_10_k_anchor_is_rejected(self) -> None:
        source = {
            "accession": "0000000001-20-000001",
            "period_end": "2019-12-31",
            "form": "10-K/A",
        }
        anchor, status, reason = exact_anchor(
            source,
            {},
            type(
                "Scope",
                (),
                {
                    "annual_period_min_days": 300,
                    "annual_period_max_days": 400,
                    "period_start_tolerance_days": 14,
                },
            )(),
        )
        self.assertIsNone(anchor)
        self.assertEqual(status, "hard_exclude")
        self.assertEqual(reason, "frozen_anchor_form_not_original_10_k")

    def test_non_xbrl_row_is_retained_with_explicit_status(self) -> None:
        source = {
            "research_universe_company_year_id": "u1",
            "cik10": "1",
            "feature_year": 2011,
            "membership_status": "eligible",
            "accession": "0000000001-12-000001",
            "form": "10-K",
            "filed": "2012-03-01",
            "accepted_at": "2012-03-01 10:00:00",
            "period_end": "2011-12-31",
            "xbrl_submission_available": "False",
            "statement_scope_xbrl_available": False,
            "statement_scope_xbrl_status": "not_available_non_xbrl",
            "statement_scope_xbrl_reason": "frozen_universe_anchor_has_no_xbrl_submission",
            "representative_cik": "1",
        }
        result = process_eligible_row(
            source,
            config=self.config,
            semantic_config={"primitive_concepts": {}},
            scope=type(
                "Scope",
                (),
                {
                    "annual_period_min_days": 300,
                    "annual_period_max_days": 400,
                    "period_start_tolerance_days": 14,
                },
            )(),
            accession_records={},
            period_ends={("0000000001", 2011): date(2011, 12, 31)},
            companyfacts_relative_path="",
            evidence_root=type("P", (), {})(),
        )
        self.assertEqual(result["x_t_status"], "not_available_non_xbrl")
        for primitive in PRIMITIVES:
            self.assertEqual(
                result[f"current_t_{primitive}_status"], "not_available_non_xbrl"
            )
        for feature in feature_names(self.config):
            self.assertEqual(
                result[f"{feature}_status"], "not_available_non_xbrl"
            )

    def test_joint_scope_xbrl_availability_uses_entity_identifier(self) -> None:
        eligible, _ = load_universe(self.config)
        development = eligible.loc[eligible["feature_year"].between(2011, 2022)]
        joint_co_xbrl = development.loc[
            development["registrant_role_resolved"].eq("joint_co_registrant")
            & development["xbrl_submission_available"].map(
                lambda value: str(value).lower() in {"true", "1", "yes"}
            )
        ]
        self.assertEqual(len(joint_co_xbrl), 230)
        self.assertEqual(
            joint_co_xbrl["statement_scope_xbrl_status"].eq("available").sum(),
            4,
        )
        self.assertEqual(
            joint_co_xbrl["statement_scope_xbrl_status"]
            .eq("not_available_non_xbrl")
            .sum(),
            226,
        )

    def test_joint_scope_instance_parser_excludes_dimensional_contexts(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<xbrl xmlns="http://www.xbrl.org/2003/instance"
      xmlns:xbrli="http://www.xbrl.org/2003/instance"
      xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
      xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
      xmlns:us-gaap="http://fasb.org/us-gaap/2022"
      xmlns:test="http://example.test">
  <context id="issuer">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000000001</identifier></entity>
    <period><instant>2021-12-31</instant></period>
  </context>
  <context id="segment">
    <entity><identifier scheme="http://www.sec.gov/CIK">0000000001</identifier>
      <segment><xbrldi:explicitMember dimension="test:Axis">test:Member</xbrldi:explicitMember></segment>
    </entity>
    <period><instant>2021-12-31</instant></period>
  </context>
  <unit id="USD"><measure>iso4217:USD</measure></unit>
  <us-gaap:Assets contextRef="issuer" unitRef="USD">100</us-gaap:Assets>
  <us-gaap:Assets contextRef="segment" unitRef="USD">40</us-gaap:Assets>
</xbrl>"""
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]) as directory:
            root = Path(directory)
            (root / "instance.xml").write_text(xml, encoding="utf-8")
            source = {
                "cik10": "0000000001",
                "representative_cik": "0000000001",
                "accession": "0000000001-22-000001",
                "form": "10-K",
                "filed": "2022-03-01",
                "feature_year": 2021,
                "document_fiscal_year_focus": 2021,
                "document_fiscal_period_focus": "FY",
                "joint_filing_flag": True,
                "statement_scope_xbrl_status": "available",
                "statement_scope_xbrl_entity_ciks": "0000000001",
                "statement_scope_xbrl_context_files": "instance.xml",
                "statement_scope_xbrl_evidence_path": str(root.relative_to(Path(__file__).resolve().parents[1])),
            }
            records = scope_xbrl_instance_records(
                source,
                {
                    "primitive_concepts": {
                        "assets": {
                            "strategies": [{"priority": 1, "concepts": ["Assets"]}]
                        }
                    }
                },
                type("Scope", (), {"allowed_forms": ("10-K",)})(),
            )
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tag"], "Assets")
        self.assertEqual(records[0]["value"], 100.0)
        self.assertEqual(records[0]["context_id"], "issuer")


if __name__ == "__main__":
    unittest.main()

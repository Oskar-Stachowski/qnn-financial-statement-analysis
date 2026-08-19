from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import tempfile
import unittest

from src.data.primitive_resolver_v1_1 import (
    select_primitive_pair,
    select_primitive_single_period,
)
from src.data.target_candidate_v2_pit import load_config, parse_scope
from src.data.x_t_pit import feature_result
from src.data.x_t_pit_v1_1 import (
    materialize_frozen_target_train_projection,
    materialize_train_projection,
    materialize_target_application_train_projection,
    restricted_companyfacts_root,
)


CONFIG = load_config()
SCOPE = parse_scope(CONFIG)


def fact(tag: str, value: float, start: str, end: str) -> dict:
    return {
        "tag": tag,
        "value": value,
        "accn": "synthetic-accession",
        "form": "10-K",
        "filed": "2020-02-01",
        "start": start,
        "end": end,
        "document_fiscal_year_focus": 2019,
        "document_fiscal_period_focus": "FY",
        "frame": "",
    }


def anchor(records: list[dict], report_end: str = "2019-12-31") -> dict:
    return {
        "accn": "synthetic-accession",
        "records": records,
        "report_end": date.fromisoformat(report_end),
        "document_period_end_date": report_end,
        "document_fiscal_year_focus": 2019,
        "document_fiscal_period_focus": "FY",
        "filed": "2020-02-01",
        "accepted_at": "2020-02-01T12:00:00Z",
    }


class FailClosedPriorityBarrierTests(unittest.TestCase):
    def test_ambiguous_highest_priority_cannot_fall_back_and_features_fail_closed(self) -> None:
        policy = CONFIG["primitive_concepts"]["net_income"]
        current_anchor = anchor(
            [
                # Highest priority is present at the expected end but has no
                # admissible annual duration, hence it is ambiguous.
                fact("NetIncomeLoss", 10.0, "2019-10-01", "2019-12-31"),
                # The lower-priority concept is otherwise fully admissible.
                fact("ProfitLoss", 9.0, "2019-01-01", "2019-12-31"),
            ]
        )
        selected = select_primitive_single_period(
            "net_income",
            policy,
            current_anchor,
            anchor([], "2018-12-31"),
            SCOPE,
        )

        self.assertEqual(selected["status"], "ambiguous")
        self.assertIsNone(selected["value"])
        self.assertEqual(selected["reason"], "higher_priority_context_ambiguous")
        self.assertEqual(selected["candidate_strategies"], "net_income_loss")
        self.assertNotEqual(selected.get("strategy"), "profit_loss")

        assets = {"status": "selected", "reason": "synthetic", "value": 100.0}
        revenues = {
            "status": "selected",
            "reason": "synthetic",
            "value": 200.0,
        }
        for sources, formula in (
            ([selected, assets], lambda: 9.0 / 100.0),
            ([selected, revenues], lambda: 9.0 / 200.0),
        ):
            derived = feature_result(
                block="synthetic",
                selections=sources,
                source_primitives=["net_income", "denominator"],
                source_roles="current_t",
                prediction_at="2020-02-01T12:00:00Z",
                precision="accepted_timestamp",
                formula=formula,
            )
            self.assertEqual(derived["status"], "ambiguous")
            self.assertIsNone(derived["value"])

    def test_cross_tag_pair_is_blocked_by_higher_priority_role_ambiguity(self) -> None:
        policy = {
            "period_type": "instant",
            "strategies": [
                {
                    "name": "direct",
                    "priority": 1,
                    "concepts": ["Direct"],
                    "equivalence_group": "same_construct",
                },
                {
                    "name": "fallback",
                    "priority": 2,
                    "concepts": ["Fallback"],
                    "equivalence_group": "same_construct",
                },
            ],
        }
        pair_anchor = anchor(
            [
                # Direct is selected for t-1 and ambiguous for t.
                fact("Direct", 90.0, "", "2018-12-31"),
                fact("Direct", 100.0, "2019-01-01", "2019-12-31"),
                # Fallback supplies the current instant, which v1 accepted as
                # a controlled cross-tag pair.
                fact("Fallback", 100.0, "", "2019-12-31"),
            ]
        )
        result = select_primitive_pair(
            "synthetic",
            policy,
            pair_anchor,
            anchor([], "2018-12-31"),
            anchor([], "2017-12-31"),
            SCOPE,
        )
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["value"])
        self.assertEqual(result["reason"], "higher_priority_context_ambiguous")


class ProtectedPeriodRoutingTests(unittest.TestCase):
    def test_mixed_raw_artifact_materializes_only_train_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "mixed.csv"
            destination = directory / "train.csv"
            source.write_bytes(
                b"research_universe_company_year_id,cik10,feature_year,payload\n"
                b"allowed-2020,0000000001,2020,train-value\n"
                b"sealed-2021,0000000001,2021,DO_NOT_OPEN_2021\n"
                b"sealed-2024,0000000001,2024,DO_NOT_OPEN_2024\n"
            )
            count = materialize_train_projection(source, destination)
            projected = destination.read_bytes()
        self.assertEqual(count, 1)
        self.assertIn(b"train-value", projected)
        self.assertNotIn(b"DO_NOT_OPEN", projected)

    def test_companyfacts_decoder_only_decodes_allowed_accessions(self) -> None:
        payload = {
            "facts": {
                "us-gaap": {
                    "NetIncomeLoss": {
                        "label": "Net income",
                        "units": {
                            "USD": [
                                {
                                    "val": 10,
                                    "accn": "allowed-accession",
                                    "form": "10-K",
                                    "filed": "2020-02-01",
                                    "start": "2019-01-01",
                                    "end": "2019-12-31",
                                    "fy": 2019,
                                    "fp": "FY",
                                },
                                {
                                    "val": "DO_NOT_DECODE_PROTECTED_VALUE",
                                    "accn": "sealed-accession",
                                    "form": "10-K",
                                    "filed": "2024-02-01",
                                    "start": "2023-01-01",
                                    "end": "2023-12-31",
                                    "fy": 2023,
                                    "fp": "FY",
                                },
                            ]
                        },
                    }
                }
            }
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "companyfacts.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            root = restricted_companyfacts_root(
                path,
                allowed_accessions={"allowed-accession"},
                required_tags={"NetIncomeLoss"},
            )
        facts = root["us-gaap"]["NetIncomeLoss"]["units"]["USD"]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["accn"], "allowed-accession")
        self.assertEqual(facts[0]["val"], 10)

    def test_mixed_target_application_materializes_only_train_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "mixed_target.csv"
            destination = directory / "train_target.csv"
            source.write_bytes(
                b"research_universe_company_year_id,universe_anchor_accession,cik10,feature_year,payload\n"
                b"allowed-2020,a0,0000000001,2020,train-label\n"
                b"sealed-2021,a1,0000000001,2021,DO_NOT_OPEN_TARGET_2021\n"
                b"sealed-2024,a4,0000000001,2024,DO_NOT_OPEN_TARGET_2024\n"
            )
            count = materialize_target_application_train_projection(
                source, destination
            )
            projected = destination.read_bytes()
        self.assertEqual(count, 1)
        self.assertIn(b"train-label", projected)
        self.assertNotIn(b"DO_NOT_OPEN", projected)

    def test_frozen_target_router_handles_quoted_early_metadata(self) -> None:
        header = (
            b"cik10,company_name,primary_ticker,research_sector,sic,sic_int,"
            b"sic_description,sic_major_group,feature_year,payload\n"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "mixed_target.csv"
            destination = directory / "train_target.csv"
            source.write_bytes(
                header
                + b'0000000001,"Allowed, Inc.",A,sector,1,1,desc,1,2020,train-value\n'
                + b'0000000001,"Sealed, Inc.",A,sector,1,1,desc,1,2022,DO_NOT_OPEN_2022\n'
            )
            count = materialize_frozen_target_train_projection(
                source, destination
            )
            projected = destination.read_bytes()
        self.assertEqual(count, 1)
        self.assertIn(b"train-value", projected)
        self.assertNotIn(b"DO_NOT_OPEN", projected)


if __name__ == "__main__":
    unittest.main()

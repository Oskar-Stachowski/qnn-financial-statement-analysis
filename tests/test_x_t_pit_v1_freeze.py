from __future__ import annotations

import csv
import hashlib
import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "configs/x_t_pit_v1_freeze_manifest.yaml"
POLICY_PATH = ROOT / "configs/x_t_pit_v1.yaml"
UNIVERSE_MANIFEST_PATH = ROOT / "configs/research_universe_pit_freeze_manifest.yaml"
TARGET_MANIFEST_PATH = ROOT / "configs/target_candidate_v2_pit_b_freeze_manifest.yaml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_data_rows(path: Path) -> int:
    with path.open("rb") as stream:
        return max(sum(1 for _ in stream) - 1, 0)


class FrozenRawPointInTimeXtV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))

    def test_manifest_identifies_frozen_raw_x_t_and_boundary(self) -> None:
        frozen = self.manifest["raw_point_in_time_x_t"]
        self.assertEqual(frozen["id"], "x_t_pit")
        self.assertEqual(frozen["version"], "1.0.0")
        self.assertEqual(frozen["status"], "frozen")
        self.assertEqual(
            frozen["freeze_scope"], "raw_point_in_time_feature_construction"
        )
        self.assertTrue(frozen["raw_artifact_frozen"])
        for item in (
            "supervised_sample_policy_frozen",
            "imputation_frozen",
            "missing_indicators_frozen",
            "winsorization_frozen",
            "scaling_frozen",
            "feature_selection_frozen",
            "models_frozen",
            "hyperparameters_frozen",
        ):
            self.assertFalse(frozen[item])

    def test_frozen_policy_semantics_and_feature_blocks(self) -> None:
        x_t = self.policy["x_t"]
        pit = self.policy["point_in_time"]
        statuses = self.policy["status_policy"]
        self.assertEqual(x_t["version"], "1.0.0")
        self.assertEqual(x_t["status"], "frozen")
        self.assertTrue(x_t["raw_only"])
        self.assertFalse(any(x_t["preprocessing"].values()))
        self.assertFalse(x_t["models_trained"])
        self.assertFalse(x_t["test_used_for_policy_or_resolver_decisions"])

        self.assertEqual(pit["anchor"], "exact_frozen_universe_accession")
        self.assertTrue(pit["original_10_k_only"])
        self.assertFalse(pit["amendments_allowed"])
        self.assertFalse(pit["later_filings_allowed"])
        self.assertFalse(pit["later_restatements_allowed"])
        self.assertFalse(pit["later_filing_feature_fallback_allowed"])
        self.assertTrue(pit["current_and_comparative_same_accession"])
        self.assertEqual(
            pit["accepted_at_policy"]["missing_fallback"],
            "next_calendar_day_midnight_et_after_filed_date",
        )
        self.assertEqual(
            pit["reviewed_negative_current_primitive_policy"][
                "xbrl_error_or_unresolved"
            ],
            "ambiguous_na",
        )
        self.assertFalse(
            pit["reviewed_negative_current_primitive_policy"][
                "heuristic_sign_correction_allowed"
            ]
        )

        self.assertEqual(
            self.policy["blocks"]["L"]["features"],
            [
                "log_assets_t",
                "roa_t",
                "ocf_to_assets_t",
                "current_ratio_t",
                "liabilities_to_assets_t",
                "working_capital_to_assets_t",
                "accruals_to_assets_t",
            ],
        )
        self.assertEqual(
            self.policy["blocks"]["D"]["features"],
            [
                "asset_growth_1y",
                "delta_roa_1y",
                "delta_ocf_to_assets_1y",
                "current_ratio_change_1y",
                "delta_liabilities_to_assets_1y",
            ],
        )
        self.assertEqual(
            self.policy["blocks"]["R"]["features"],
            [
                "log1p_revenues_t",
                "profit_margin_t",
                "ocf_margin_t",
                "asset_turnover_t",
                "revenue_growth_1y",
            ],
        )
        self.assertEqual(
            self.policy["pre_registered_model_comparisons"],
            [["L"], ["L", "D"], ["L", "D", "R"]],
        )
        self.assertFalse(self.policy["block_selection_may_use_test_set"])
        self.assertFalse(statuses["missing_feature_drops_row"])
        self.assertFalse(statuses["missing_target_drops_raw_x_t_row"])
        self.assertFalse(statuses["missing_mapped_to_zero"])

    def test_versioned_component_hashes_match_manifest(self) -> None:
        for component_group in self.manifest["versioned_components"].values():
            for component in component_group:
                path = ROOT / component["path"]
                with self.subTest(path=component["path"]):
                    self.assertTrue(path.is_file())
                    self.assertEqual(sha256(path), component["sha256"])

    def test_raw_artifact_is_byte_identical_and_has_frozen_schema(self) -> None:
        artifact = self.manifest["non_versioned_reproduction_check"]
        path = ROOT / artifact["path"]
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_size, artifact["bytes"])
        self.assertEqual(csv_data_rows(path), artifact["data_rows"])
        self.assertEqual(sha256(path), artifact["sha256"])
        self.assertEqual(
            artifact["sha256"],
            "0f1b35b9ffbb1fb1c1cdfb7dff12e3efd8fb38f60b33407ff2b2a8fb6b88397f",
        )
        with path.open("r", encoding="utf-8", newline="") as stream:
            header = next(csv.reader(stream))
        self.assertEqual(len(header), artifact["columns"])
        self.assertFalse(any("target" in column.lower() for column in header))
        self.assertFalse(any("current_t1" in column.lower() for column in header))
        self.assertFalse(any("anchor_t1" in column.lower() for column in header))

    def test_build_and_final_audits_match_freeze(self) -> None:
        build = json.loads(
            (ROOT / "data/reports/x_t_pit_v1_build_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        audit = json.loads(
            (ROOT / "data/reports/x_t_pit_v1_audit.json").read_text(
                encoding="utf-8"
            )
        )
        sign_review = yaml.safe_load(
            (ROOT / "configs/x_t_pit_v1_negative_sign_review.yaml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(build["status"], "frozen")
        self.assertEqual(build["raw_artifact_rows"], 64_901)
        self.assertEqual(build["raw_artifact_columns"], 1_072)
        self.assertEqual(
            build["raw_artifact_sha256"],
            self.manifest["non_versioned_reproduction_check"]["sha256"],
        )
        self.assertFalse(build["preprocessing_applied"])
        self.assertFalse(build["models_trained"])
        self.assertFalse(build["test_used_for_policy_or_resolver_decisions"])

        self.assertEqual(audit["verdict"], "X_T V1 READY TO FREEZE")
        self.assertEqual(audit["blocking_issues"], [])
        self.assertEqual(audit["raw_rows_all_years"], 64_901)
        self.assertEqual(audit["development_rows"], 56_903)
        self.assertFalse(audit["test_years_used_for_decisions"])
        for primitive in (
            "assets",
            "liabilities",
            "current_assets",
            "current_liabilities",
        ):
            self.assertEqual(
                audit["primitive_sign_summary"][primitive]["negative"], 0
            )
        self.assertEqual(
            audit["primitive_sign_summary"]["revenues"]["negative"], 5
        )
        cases = sign_review["cases"]
        self.assertEqual(len(cases), 25)
        self.assertEqual(sum(item["action"] == "retain" for item in cases), 5)
        self.assertEqual(
            sum(item["action"] == "ambiguous_na" for item in cases), 20
        )

    def test_frozen_target_and_universe_remain_byte_identical(self) -> None:
        upstream = self.manifest["upstream_frozen_invariants"]
        universe_manifest = yaml.safe_load(
            UNIVERSE_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        target_manifest = yaml.safe_load(
            TARGET_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        universe = upstream["research_universe"]
        target = upstream["target"]

        self.assertEqual(
            universe_manifest["historical_research_universe"]["version"], "1.1.0"
        )
        self.assertEqual(target_manifest["target"]["version"], "1.0.0")
        self.assertEqual(
            sha256(ROOT / universe["path"]), universe["sha256"]
        )
        self.assertEqual(sha256(ROOT / target["path"]), target["sha256"])
        self.assertEqual(
            universe["sha256"],
            "a449c8145d1f46f954f12b1dfc079bb0b367c4f7f5edf3332a983ad7c1fb8182",
        )
        self.assertEqual(
            target["sha256"],
            "473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff",
        )


if __name__ == "__main__":
    unittest.main()

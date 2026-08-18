from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "configs/research_universe_pit_freeze_manifest.yaml"
POLICY_PATH = ROOT / "configs/research_universe_pit.yaml"
TARGET_FREEZE_MANIFEST_PATH = (
    ROOT / "configs/target_candidate_v2_pit_b_freeze_manifest.yaml"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def csv_data_rows(path: Path) -> int:
    with path.open("rb") as stream:
        return max(sum(1 for _ in stream) - 1, 0)


class FrozenHistoricalResearchUniverseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))

    def test_manifest_identifies_frozen_universe_and_freeze_boundary(self) -> None:
        universe = self.manifest["historical_research_universe"]
        self.assertEqual(universe["id"], "research_universe_pit")
        self.assertEqual(universe["version"], "1.1.0")
        self.assertEqual(universe["status"], "frozen")
        self.assertEqual(
            universe["freeze_scope"],
            "historical_filing_first_membership_and_economic_entity_resolution",
        )
        self.assertEqual(universe["unit"], "cik_fiscal_year")
        self.assertFalse(universe["x_t_frozen"])
        self.assertFalse(universe["feature_availability_frozen"])
        self.assertFalse(universe["preprocessing_frozen"])
        self.assertFalse(universe["models_frozen"])
        self.assertFalse(universe["hyperparameters_frozen"])

    def test_frozen_policy_semantics_are_unchanged(self) -> None:
        historical = self.policy["historical_universe"]
        forms = self.policy["forms"]
        classification = self.policy["classification"]
        entity = self.policy["entity_history"]
        status = self.policy["status_policy"]

        self.assertEqual(historical["version"], "1.1.0")
        self.assertEqual(historical["status"], "frozen")
        self.assertEqual(historical["anchor"], "earliest_original_10k")
        self.assertEqual(historical["membership_timestamp"], "anchor_accepted_at")
        self.assertFalse(historical["current_ticker_required"])
        self.assertFalse(historical["current_exchange_required"])

        self.assertEqual(forms["qualifying_original"], ["10-K"])
        self.assertEqual(forms["non_qualifying"], ["10-K/A", "10-KT", "10-KT/A"])

        self.assertEqual(classification["missing_sic_status"], "ambiguous")
        self.assertEqual(classification["conflicting_sic_status"], "ambiguous")
        self.assertFalse(classification["use_future_sic_as_fallback"])
        self.assertFalse(classification["use_current_entity_metadata"])
        self.assertFalse(classification["use_company_name_as_exclusion_rule"])

        self.assertEqual(entity["primary_identifier"], "cik")
        self.assertTrue(entity["retain_pre_delisting_pre_acquisition_years"])
        self.assertFalse(entity["infer_cik_links_from_names_or_tickers"])
        self.assertEqual(
            entity["joint_filing_policy"],
            "one_eligible_row_per_economic_statement_scope_fail_closed",
        )
        self.assertEqual(
            entity["registrant_role_values"],
            [
                "single_filer_xbrl_registrant",
                "single_filer_non_xbrl_registrant",
                "joint_primary_registrant",
                "joint_co_registrant",
            ],
        )
        self.assertFalse(entity["economic_group_policy"]["changes_membership"])
        self.assertFalse(
            entity["economic_group_policy"]["overrides_temporal_split"]
        )

        self.assertEqual(status["membership"], ["eligible", "excluded", "ambiguous"])
        self.assertEqual(status["x_t_before_feature_pipeline"], "not_built")
        self.assertFalse(status["missing_t1_removes_membership"])

    def test_frozen_final_counts_and_entity_resolution_counts(self) -> None:
        final = self.manifest["final_membership"]
        self.assertEqual(final["company_year_anchors_all_statuses"], 103_099)
        self.assertEqual(final["eligible"], 64_901)
        self.assertEqual(final["excluded"], 36_659)
        self.assertEqual(final["ambiguous"], 1_539)
        self.assertEqual(final["eligible_distinct_statement_scope_years"], 64_901)
        self.assertEqual(final["eligible_duplicate_statement_scope_year_rows"], 0)
        self.assertEqual(final["eligible_nonrepresentative_rows"], 0)

        resolution = self.manifest["entity_resolution"]
        self.assertEqual(resolution["duplicate_registrant_rows_excluded"], 132)
        self.assertEqual(resolution["nominal_nonoperating_coissuers_excluded"], 28)
        self.assertEqual(resolution["unresolved_rows_changed_to_ambiguous"], 6)
        self.assertFalse(
            resolution["representative_selection_uses_target_features_or_models"]
        )

    def test_versioned_component_hashes_match_manifest(self) -> None:
        for component_group in self.manifest["versioned_components"].values():
            for component in component_group:
                path = ROOT / component["path"]
                with self.subTest(path=component["path"]):
                    self.assertTrue(path.is_file())
                    self.assertEqual(sha256(path), component["sha256"])

    def test_generated_artifact_hashes_sizes_and_rows_match_manifest(self) -> None:
        for artifact in self.manifest["non_versioned_reproduction_checks"]:
            path = ROOT / artifact["path"]
            with self.subTest(path=artifact["path"]):
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_size, artifact["bytes"])
                self.assertEqual(csv_data_rows(path), artifact["data_rows"])
                self.assertEqual(sha256(path), artifact["sha256"])

    def test_canonical_artifact_obeys_membership_and_scope_invariants(self) -> None:
        path = ROOT / "data/processed/research_universe_pit.csv"
        columns = [
            "cik10",
            "feature_year",
            "membership_status",
            "membership_reason",
            "x_t_status",
            "registrant_role_resolved",
            "economic_statement_scope_id",
            "economic_group_id",
            "representative_cik",
            "entity_resolution_membership_changed",
        ]
        frame = pd.read_csv(
            path,
            usecols=columns,
            dtype={"cik10": "string", "representative_cik": "string"},
            low_memory=False,
        )
        final = self.manifest["final_membership"]
        counts = frame["membership_status"].value_counts().to_dict()

        self.assertEqual(len(frame), final["company_year_anchors_all_statuses"])
        self.assertEqual(counts.get("eligible", 0), final["eligible"])
        self.assertEqual(counts.get("excluded", 0), final["excluded"])
        self.assertEqual(counts.get("ambiguous", 0), final["ambiguous"])

        eligible = frame.loc[frame["membership_status"].eq("eligible")].copy()
        scope_year_duplicates = eligible.duplicated(
            ["economic_statement_scope_id", "feature_year"], keep=False
        )
        self.assertFalse(scope_year_duplicates.any())
        self.assertFalse(eligible["economic_statement_scope_id"].isna().any())
        self.assertFalse(eligible["economic_group_id"].isna().any())
        self.assertTrue(eligible["cik10"].eq(eligible["representative_cik"]).all())
        self.assertTrue(eligible["x_t_status"].eq("not_built").all())
        self.assertEqual(
            eligible["economic_statement_scope_id"].nunique(),
            final["eligible_distinct_statement_scope_years"],
        )
        self.assertEqual(
            eligible["economic_group_id"].nunique(),
            final["eligible_distinct_economic_groups"],
        )
        self.assertEqual(
            set(eligible["registrant_role_resolved"].dropna().unique()),
            {
                "single_filer_xbrl_registrant",
                "single_filer_non_xbrl_registrant",
                "joint_primary_registrant",
                "joint_co_registrant",
            },
        )

        self.assertEqual(
            frame["membership_reason"]
            .eq("duplicate_registrant_same_statement_scope")
            .sum(),
            132,
        )
        self.assertEqual(
            frame["membership_reason"]
            .eq("nominal_nonoperating_finance_coissuer")
            .sum(),
            28,
        )
        changed_to_ambiguous = frame[
            frame["entity_resolution_membership_changed"].fillna(False).astype(bool)
            & frame["membership_status"].eq("ambiguous")
        ]
        self.assertEqual(len(changed_to_ambiguous), 6)

    def test_final_audit_is_ready_and_matches_frozen_counts(self) -> None:
        audit_path = ROOT / "data/reports/research_universe_pit_audit.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        overall = audit["overall"]

        self.assertEqual(
            audit["freeze_gate_verdict"], "RESEARCH UNIVERSE READY TO FREEZE"
        )
        self.assertEqual(overall["eligible_company_years"], 64_901)
        self.assertEqual(overall["excluded_company_years"], 36_659)
        self.assertEqual(overall["ambiguous_company_years"], 1_539)
        self.assertEqual(overall["eligible_statement_scope_year_duplicate_rows"], 0)
        self.assertEqual(overall["eligible_nonrepresentative_rows"], 0)
        self.assertEqual(overall["eligible_missing_statement_scope_rows"], 0)
        self.assertEqual(overall["eligible_missing_economic_group_rows"], 0)
        self.assertTrue(audit["registrant_role_entity_resolution"]["freeze_gate_ready"])
        self.assertFalse(
            audit["methodological_assessment"][
                "new_universe_membership_depends_on_target_t1"
            ]
        )
        self.assertFalse(
            audit["methodological_assessment"][
                "new_universe_membership_depends_on_x_t_availability"
            ]
        )

    def test_frozen_target_artifact_remains_byte_identical(self) -> None:
        target = self.manifest["target_invariant"]
        target_freeze_manifest = yaml.safe_load(
            TARGET_FREEZE_MANIFEST_PATH.read_text(encoding="utf-8")
        )
        target_freeze_artifact = next(
            artifact
            for artifact in target_freeze_manifest["non_versioned_reproduction_checks"]
            if artifact["path"] == target["path"]
        )
        target_path = ROOT / target["path"]

        self.assertEqual(target["id"], "target_candidate_v2_pit_b")
        self.assertEqual(target["version"], "1.0.0")
        self.assertEqual(target["status"], "frozen_unchanged")
        self.assertFalse(target["changed_by_universe_freeze"])
        self.assertEqual(target["sha256"], target_freeze_artifact["sha256"])
        self.assertEqual(sha256(target_path), target["sha256"])


if __name__ == "__main__":
    unittest.main()

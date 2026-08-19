from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
X_MANIFEST = ROOT / "configs/x_t_pit_v1_1_0_train_freeze_manifest.yaml"
TARGET_MANIFEST = (
    ROOT / "configs/target_candidate_v2_pit_b_v1_1_0_train_freeze_manifest.yaml"
)
PIPELINE_CONFIG = ROOT / "configs/supervised_ml_pipeline_v1_2_0.yaml"
PIPELINE_MANIFEST = ROOT / "configs/supervised_ml_pipeline_v1_2_0_freeze_manifest.yaml"
AUDIT_PATH = ROOT / "data/reports/resolver_x_t_v1_1_0_impact_audit.json"
CAUSAL_CONTROL_PATH = (
    ROOT / "data/reports/resolver_x_t_v1_1_0_causal_control.json"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def membership_sha256(values: pd.Series) -> str:
    payload = "".join(f"{item}\n" for item in sorted(values.astype(str)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResolverXtV11FreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.x_manifest = yaml.safe_load(X_MANIFEST.read_text(encoding="utf-8"))
        cls.target_manifest = yaml.safe_load(
            TARGET_MANIFEST.read_text(encoding="utf-8")
        )
        cls.pipeline = yaml.safe_load(PIPELINE_CONFIG.read_text(encoding="utf-8"))
        cls.pipeline_manifest = yaml.safe_load(
            PIPELINE_MANIFEST.read_text(encoding="utf-8")
        )
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        cls.causal_control = json.loads(
            CAUSAL_CONTROL_PATH.read_text(encoding="utf-8")
        )

    def test_historical_v1_artifacts_are_unchanged(self) -> None:
        self.assertEqual(
            sha256(ROOT / "data/processed/x_t_pit_v1_raw.csv"),
            "0f1b35b9ffbb1fb1c1cdfb7dff12e3efd8fb38f60b33407ff2b2a8fb6b88397f",
        )
        self.assertEqual(
            sha256(ROOT / "data/interim/target_candidate_v2_pit_b.csv"),
            "473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff",
        )
        self.assertTrue(self.x_manifest["historical_v1"]["retained_immutable"])
        self.assertTrue(self.target_manifest["historical_v1"]["retained_immutable"])

    def test_versioned_component_hashes_are_exact(self) -> None:
        for manifest in (
            self.x_manifest,
            self.target_manifest,
            self.pipeline_manifest,
        ):
            for item in manifest.get("versioned_components", []):
                with self.subTest(path=item["path"]):
                    self.assertEqual(sha256(ROOT / item["path"]), item["sha256"])
        for item in self.x_manifest["audit_evidence"]:
            with self.subTest(path=item["path"]):
                self.assertEqual(sha256(ROOT / item["path"]), item["sha256"])

    def test_new_artifacts_are_train_only_and_content_addressed(self) -> None:
        artifacts = [
            (
                self.x_manifest["artifact"],
                "research_universe_company_year_id",
            ),
            (self.target_manifest["artifacts"]["target_train"], "cik10"),
            (
                self.target_manifest["artifacts"]["target_application_train"],
                "research_universe_company_year_id",
            ),
        ]
        for artifact, id_column in artifacts:
            path = ROOT / artifact["path"]
            self.assertEqual(sha256(path), artifact["sha256"])
            seen: set[str] = set()
            rows = 0
            for chunk in pd.read_csv(
                path,
                usecols=[id_column, "feature_year"],
                dtype=str,
                chunksize=5_000,
            ):
                years = pd.to_numeric(chunk["feature_year"], errors="raise")
                self.assertTrue(years.between(2011, 2020).all())
                ids = (
                    chunk[id_column].astype(str)
                    if id_column != "cik10"
                    else chunk["cik10"].astype(str).str.zfill(10)
                    + "-"
                    + chunk["feature_year"].astype(str)
                )
                self.assertFalse(ids.duplicated().any())
                self.assertFalse(any(item in seen for item in ids))
                seen.update(ids)
                rows += len(chunk)
            self.assertEqual(rows, artifact["rows"])

    def test_exact_fail_closed_delta_and_dependent_features(self) -> None:
        raw = self.audit["raw_x_t"]
        self.assertEqual(raw["rows_compared"], 47_938)
        self.assertEqual(raw["changed_company_years"], 112)
        self.assertEqual(raw["pair_changed_company_years"], 0)
        self.assertEqual(
            raw["primitives"]["net_income"]["status_transitions"],
            {"selected->ambiguous": 109},
        )
        self.assertEqual(
            raw["primitives"]["liabilities"]["status_transitions"],
            {"selected->ambiguous": 3},
        )
        self.assertEqual(raw["feature_value_na_cells_delta"], 278)
        self.assertEqual(raw["features"]["roa_t"]["changed_company_years"], 109)
        self.assertEqual(
            raw["features"]["accruals_to_assets_t"]["changed_company_years"],
            109,
        )
        self.assertEqual(
            raw["features"]["profit_margin_t"]["changed_company_years"], 66
        )
        self.assertEqual(
            raw["features"]["liabilities_to_assets_t"]["changed_company_years"],
            3,
        )

    def test_target_is_versioned_but_labels_and_statuses_do_not_change(self) -> None:
        target = self.audit["target"]
        self.assertTrue(target["frozen_target_affected"])
        self.assertFalse(target["target_definition_changed"])
        self.assertFalse(target["target_labels_changed"])
        self.assertEqual(target["target_train_changed_company_years"], 87)
        self.assertEqual(target["target_train_status_changes"], 0)
        self.assertEqual(target["target_application_changed_company_years"], 108)
        self.assertEqual(target["target_application_status_changes"], 0)
        self.assertEqual(target["target_application_label_changes"], 0)
        self.assertEqual(
            target["cross_tag_pair_audit"]["selected_cross_tag_pairs_checked"], 1
        )
        self.assertEqual(
            target["cross_tag_pair_audit"]["newly_blocked_pairs"], 0
        )

    def test_supervised_membership_class_balance_and_folds_are_unchanged(self) -> None:
        sample = self.audit["supervised_sample"]
        self.assertEqual(sample["old_n"], 19_671)
        self.assertEqual(sample["new_n"], 19_671)
        self.assertEqual(sample["feature_changed_company_years"], 25)
        self.assertEqual(sample["feature_changed_cells"], 75)
        self.assertEqual(sample["feature_value_na_cells_delta"], 74)
        self.assertEqual(sample["changed_membership_n"], 0)
        self.assertEqual(sample["entered_n"], 0)
        self.assertEqual(sample["exited_n"], 0)
        expected_hash = "864af3d9aac6ea239d993ea48cd819c2185f3249957d8b81f6d8d4c3c9f3d680"
        self.assertEqual(sample["old_membership_sha256"], expected_hash)
        self.assertEqual(sample["new_membership_sha256"], expected_hash)
        self.assertEqual(sample["old_class_balance"], sample["new_class_balance"])
        self.assertEqual(sample["missingness"]["roa_t"]["na_delta"], 25)
        self.assertEqual(
            sample["missingness"]["accruals_to_assets_t"]["na_delta"], 25
        )
        self.assertEqual(sample["missingness"]["profit_margin_t"]["na_delta"], 24)
        self.assertFalse(self.audit["temporal_folds"]["any_membership_changed"])
        self.assertEqual(self.audit["temporal_folds"]["changed_folds"], {})

    def test_same_source_v1_control_excludes_cache_drift_as_the_cause(self) -> None:
        control = self.causal_control
        self.assertEqual(control["scope"], "train_2011_2020_only")
        self.assertEqual(control["changed_company_years_checked"], 112)
        self.assertEqual(control["primitive_cells_checked"], 112)
        self.assertEqual(control["exact_frozen_selection_matches"], 112)
        self.assertEqual(control["mismatch_n"], 0)
        self.assertTrue(control["causal_isolation_passed"])
        self.assertFalse(control["protected_feature_years_opened"])
        self.assertFalse(control["models_trained"])

    def test_access_boundary_and_no_training_are_explicit(self) -> None:
        self.assertFalse(self.audit["inputs"].get("protected_feature_years_opened", False))
        self.assertFalse(self.audit["models_trained"])
        self.assertFalse(
            self.pipeline["supervised_ml_pipeline"]["predictive_models_trained"]
        )
        self.assertEqual(
            self.pipeline["authoritative_scope"]["protected_feature_years"],
            [2021, 2022, 2023, 2024],
        )
        self.assertFalse(
            self.pipeline["authoritative_scope"]["protected_values_opened"]
        )


if __name__ == "__main__":
    unittest.main()

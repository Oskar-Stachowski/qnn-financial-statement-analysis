from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import yaml

from src.modeling.model_stage_preregistration import canonical_sha256, materialized_registry


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "configs/model_stage_v1_freeze_manifest.yaml"
CONFIG_PATH = ROOT / "configs/model_stage_v1.yaml"
CANDIDATES_PATH = ROOT / "configs/model_stage_candidates_v1.json"
NOTEBOOK_PATH = ROOT / "notebooks/05_model_stage_preregistration.ipynb"
REPORT_PATH = ROOT / "data/reports/model_stage_preregistration_freeze_gate_execution.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ModelStageV1FreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = yaml.safe_load(MANIFEST_PATH.read_text())
        cls.config = yaml.safe_load(CONFIG_PATH.read_text())
        cls.candidates = json.loads(CANDIDATES_PATH.read_text())
        cls.notebook = json.loads(NOTEBOOK_PATH.read_text())
        cls.report = json.loads(REPORT_PATH.read_text())

    def test_frozen_identity_and_access_declaration(self) -> None:
        stage = self.manifest["model_stage"]
        self.assertEqual(stage["id"], "model_stage_preregistration")
        self.assertEqual(stage["version"], "1.0.0")
        self.assertEqual(stage["status"], "frozen")
        self.assertEqual(stage["technical_gate_verdict"], "MODEL STAGE READY TO FREEZE")
        self.assertFalse(stage["search_started"])
        self.assertFalse(stage["project_data_model_fit_performed"])
        self.assertFalse(stage["external_validation_opened_analytically"])
        self.assertFalse(stage["test_opened_or_used"])
        access = self.manifest["access_and_change_control"]
        self.assertEqual(access["external_validation_status_at_freeze"], "unopened_analytically")
        self.assertEqual(access["test_status_at_freeze"], "unopened_unused")
        self.assertEqual(access["project_data_training_status_at_freeze"], "not_started")
        self.assertFalse(access["freeze_authorizes_search_or_training"])

    def test_authoritative_artifact_hashes(self) -> None:
        sources = self.manifest["authoritative_sources"]
        for key in ("notebook", "machine_policy", "candidate_registry", "frozen_specification"):
            item = sources[key]
            self.assertEqual(file_sha256(ROOT / item["path"]), item["sha256"], key)
        report = self.manifest["technical_freeze_gate"]["report"]
        self.assertEqual(file_sha256(ROOT / report["path"]), report["sha256"])

    def test_upstream_frozen_inputs_are_byte_identical(self) -> None:
        upstream = self.manifest["upstream_frozen_inputs"]
        manifest_pairs = [
            (upstream["target"]["manifest"], upstream["target"]["manifest_sha256"]),
            (
                upstream["historical_research_universe"]["manifest"],
                upstream["historical_research_universe"]["manifest_sha256"],
            ),
            (upstream["raw_x_t"]["manifest"], upstream["raw_x_t"]["manifest_sha256"]),
            (
                upstream["supervised_ml_pipeline"]["configuration"],
                upstream["supervised_ml_pipeline"]["configuration_sha256"],
            ),
            (
                upstream["supervised_ml_pipeline"]["manifest"],
                upstream["supervised_ml_pipeline"]["manifest_sha256"],
            ),
            (
                upstream["supervised_ml_pipeline"]["specification"],
                upstream["supervised_ml_pipeline"]["specification_sha256"],
            ),
        ]
        for relative, expected in manifest_pairs:
            self.assertEqual(file_sha256(ROOT / relative), expected, relative)

    def test_protected_implementation_contracts_are_byte_identical(self) -> None:
        for item in self.manifest["protected_implementation_and_audit_components"]:
            self.assertEqual(file_sha256(ROOT / item["path"]), item["sha256"], item["path"])

    def test_every_materialized_id_and_candidate_list_is_frozen(self) -> None:
        self.assertEqual(self.candidates, materialized_registry())
        lists = {
            **{f"coarse.{name}": values for name, values in self.candidates["coarse"].items()},
            **{
                f"refinement.{name}": values
                for name, values in self.candidates["refinement"].items()
            },
            "qnn.stage_q1": self.candidates["qnn"]["stage_q1"],
            "qnn.stage_q2": self.candidates["qnn"]["stage_q2"],
        }
        expected = self.manifest["candidate_lists"]
        self.assertEqual(set(lists), set(expected))
        identifiers: list[str] = []
        for name, values in lists.items():
            self.assertEqual(len(values), expected[name]["count"], name)
            self.assertEqual(canonical_sha256(values), expected[name]["sha256"], name)
            identifiers.extend(value["configuration_id"] for value in values)
        registry = self.manifest["authoritative_sources"]["candidate_registry"]
        self.assertEqual(len(identifiers), registry["configuration_id_count"])
        self.assertEqual(len(identifiers), len(set(identifiers)))
        self.assertTrue(registry["configuration_ids_unique"])

    def test_machine_policy_locks_core_model_decisions(self) -> None:
        stage = self.config["model_stage"]
        self.assertEqual(stage["version"], "1.0.0")
        self.assertEqual(stage["status"], "frozen")
        self.assertEqual(
            stage["authoritative_notebook_sha256"],
            "67c4daa32a00cb0db08fbd35b950f422a277b63e22e669a449487c9a80626afc",
        )
        self.assertEqual(
            self.config["model_roster"]["included"],
            [
                "dummy_prior",
                "fixed_l2_logistic",
                "elastic_net_logistic",
                "rbf_svm",
                "random_forest",
                "hist_gradient_boosting",
                "xgboost",
                "pytorch_mlp",
                "qnn_if_technically_feasible",
            ],
        )
        self.assertEqual(self.config["frozen_pipeline_reference"]["feature_blocks"], ["L", "L+D", "L+D+R"])
        self.assertEqual(
            self.config["frozen_pipeline_reference"]["primary_metric"],
            "pooled_oof_pr_auc_2015_2020",
        )
        elastic = self.config["elastic_net_logistic_constructor"]
        self.assertEqual((elastic["penalty"], elastic["solver"]), ("elasticnet", "saga"))
        self.assertEqual(elastic["n_jobs"], 1)
        weights = self.config["class_imbalance"]
        self.assertEqual(weights["w_negative"], 1.0)
        self.assertEqual(weights["w_positive"], "sqrt(N_negative/N_positive)")

    def test_seed_score_calibration_qnn_and_test_gate_are_locked(self) -> None:
        seeds = self.config["seed_aggregation"]
        self.assertEqual(seeds["coarse_and_refinement_training_seed"], 20260818)
        self.assertEqual(seeds["confirmation_seeds"], [20260819, 20260820])
        self.assertIn("arithmetic_mean", seeds["oof_rule"])
        self.assertFalse(seeds["probability_averaging_allowed"])
        raw = self.config["raw_score_interface"]
        self.assertEqual(raw["hist_gradient_boosting"], "decision_function")
        self.assertEqual(raw["xgboost"], "native_output_margin_true")
        self.assertEqual(raw["pytorch_mlp"], "direct_scalar_logit")
        calibration = self.config["calibration_and_threshold"]
        self.assertFalse(calibration["threshold_is_independent_generalization_estimate"])
        qnn = self.config["qnn"]
        self.assertTrue(qnn["stage_q1"]["may_select_final_ansatz"])
        self.assertTrue(qnn["stage_q1"]["stage_q2_may_change_ansatz"] is False)
        self.assertEqual(qnn["resource_policy"]["maximum_total_fit_attempts"], 240)
        self.assertFalse(qnn["resource_policy"]["post_hoc_simplification_allowed"])
        gate = self.config["validation_and_test"]["second_freeze_gate"]
        self.assertTrue(gate["test_may_open_only_after_committed_test_ready_manifest"])
        self.assertFalse(self.config["model_roster"]["roster_may_change_after_validation"])

    def test_notebook_and_gate_remain_clean_and_data_blind(self) -> None:
        self.assertEqual(file_sha256(NOTEBOOK_PATH), self.config["model_stage"]["authoritative_notebook_sha256"])
        code = "\n".join(
            "".join(cell["source"])
            for cell in self.notebook["cells"]
            if cell["cell_type"] == "code"
        )
        for cell in self.notebook["cells"]:
            if cell["cell_type"] == "code":
                self.assertIsNone(cell["execution_count"])
                self.assertEqual(cell["outputs"], [])
        for forbidden in (
            "read_csv(",
            "read_parquet(",
            "data/processed/",
            "data/interim/",
            "target_candidate_v2_pit_b.csv",
            "x_t_pit_v1_raw.csv",
        ):
            self.assertNotIn(forbidden, code)
        checks = self.report["checks"]
        self.assertEqual(self.report["verdict"], "MODEL STAGE READY TO FREEZE")
        self.assertEqual(checks["forbidden_project_data_loader_hits"], [])
        self.assertFalse(checks["external_validation_values_loaded"])
        self.assertFalse(checks["test_values_loaded"])
        self.assertFalse(checks["project_data_model_fit_performed"])
        self.assertTrue(checks["classical_synthetic_smoke_passed"])
        self.assertTrue(checks["qnn_mlp_synthetic_smoke_passed"])

    def test_all_declared_decision_domains_are_frozen(self) -> None:
        domains = self.manifest["frozen_decision_domains"]
        self.assertGreaterEqual(len(domains), 19)
        self.assertTrue(all(domains.values()))
        refinement = self.config["candidate_materialization"]["conditional_refinement"]
        self.assertEqual(refinement["eligible_data"], "OOF_2015_2020_only")
        self.assertFalse(refinement["validation_or_test_may_activate"])
        interpretation = self.config["interpretability"]
        self.assertFalse(interpretation["may_change_model_or_feature_selection"])
        robustness = self.config["robustness_and_sensitivity"]
        self.assertFalse(robustness["retune_hyperparameters"])
        self.assertFalse(robustness["may_change_primary_selection"])


if __name__ == "__main__":
    unittest.main()

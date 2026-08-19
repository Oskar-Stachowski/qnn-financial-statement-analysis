from __future__ import annotations

import contextlib
import hashlib
import io
import json
import unittest
from pathlib import Path

from src.modeling.model_stage_preregistration_scientific_patch import (
    canonical_sha256,
    materialized_registry,
    pca_input_columns,
)


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/05_model_stage_preregistration.ipynb"
CANDIDATES = ROOT / "configs/model_stage_candidates_v1_scientific_patch.json"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ModelStagePreregistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.notebook = json.loads(NOTEBOOK.read_text())
        cls.candidates = json.loads(CANDIDATES.read_text())
        namespace: dict[str, object] = {"__name__": "__main__"}
        with contextlib.redirect_stdout(io.StringIO()):
            for position, cell in enumerate(cls.notebook["cells"]):
                if cell["cell_type"] == "code":
                    exec(compile("".join(cell["source"]), f"cell_{position}", "exec"), namespace)
        cls.namespace = namespace

    def test_notebook_is_clean_and_does_not_load_model_data(self) -> None:
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

    def test_upstream_frozen_hashes_are_unchanged(self) -> None:
        expected = {
            "configs/target_candidate_v2_pit_b_freeze_manifest.yaml": "52fd67d360e486e45615330a869f8b7d5810eb08d957432b4c2da7cc146b66bb",
            "configs/research_universe_pit_freeze_manifest.yaml": "60310dbc9379371c05316b28de273832d0eaf02f20fc1ee7bb28697a26fb71b7",
            "configs/x_t_pit_v1_freeze_manifest.yaml": "9b59e812bfb1b34a2f72c78ce4fc0ba484249d0a1d48cdea8f94506a403a9023",
            "configs/supervised_ml_pipeline_v1.yaml": "0e817dac719d1651ec7518141e71c627dc208f4bed5ccfebed6c5b9d88652765",
            "configs/supervised_ml_pipeline_v1_freeze_manifest.yaml": "f1000d9e66a83160ff4ae0c5759c09c96491e18c4b579f6a397e0e98afc6eef1",
        }
        self.assertEqual(
            {relative: file_sha256(ROOT / relative) for relative in expected},
            expected,
        )

    def test_materialized_candidate_lists_and_hashes(self) -> None:
        self.assertEqual(self.candidates, materialized_registry())
        lists = {
            **{f"coarse.{key}": value for key, value in self.candidates["coarse"].items()},
            **{f"refinement.{key}": value for key, value in self.candidates["refinement"].items()},
            "qnn.stage_q1": self.candidates["qnn"]["stage_q1"],
            "qnn.stage_q2": self.candidates["qnn"]["stage_q2"],
        }
        self.assertEqual(set(lists), set(self.candidates["list_hashes"]))
        for name, candidates in lists.items():
            self.assertEqual(canonical_sha256(candidates), self.candidates["list_hashes"][name])
        identifiers = [item["configuration_id"] for values in lists.values() for item in values]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_pca_contract_includes_ordered_indicators(self) -> None:
        for block in ("L", "L+D", "L+D+R"):
            frozen = self.candidates["pca_feature_order"][block]
            self.assertEqual(tuple(frozen["columns"]), pca_input_columns(block))
            self.assertTrue(frozen["includes_missing_indicators"])
        contract = self.namespace["PCA_QNN_CONTRACT"]
        self.assertEqual(contract["pca"]["svd_solver"], "full")
        self.assertFalse(contract["pca"]["whiten"])
        self.assertEqual(contract["clipping"], [-3.0, 3.0])

    def test_elastic_net_and_pytorch_mlp_are_fully_locked(self) -> None:
        elastic = self.namespace["ELASTIC_NET_CONSTRUCTOR"]
        self.assertEqual(elastic["penalty"], "elasticnet")
        self.assertEqual(elastic["solver"], "saga")
        self.assertEqual(elastic["n_jobs"], 1)
        mlp = self.namespace["PYTORCH_MLP_CONTRACT"]
        self.assertEqual(mlp["optimizer"]["betas"], [0.9, 0.999])
        self.assertEqual(mlp["optimizer"]["eps"], 1e-8)
        self.assertEqual(mlp["loss"]["reduction"], "mean")
        self.assertTrue(mlp["determinism"]["torch_use_deterministic_algorithms"])
        for stage, expected_epochs in (("coarse", 200), ("refinement", 300)):
            for candidate in self.candidates[stage]["pytorch_mlp"]:
                self.assertEqual(candidate["parameters"]["epochs"], expected_epochs)
                self.assertIn(f"__epochs_{expected_epochs}__", candidate["configuration_id"])

    def test_mlp_identity_patch_does_not_change_sampled_search_points(self) -> None:
        historical = json.loads(
            (ROOT / "configs/model_stage_candidates_v1.json").read_text()
        )
        for stage in ("coarse", "refinement"):
            old = historical[stage]["pytorch_mlp"]
            patched = self.candidates[stage]["pytorch_mlp"]
            self.assertEqual(len(old), len(patched))
            self.assertEqual(
                [candidate["parameters"] for candidate in old],
                [
                    {
                        key: value
                        for key, value in candidate["parameters"].items()
                        if key != "epochs"
                    }
                    for candidate in patched
                ],
            )

    def test_seed_score_calibration_and_roster_policies(self) -> None:
        seeds = self.namespace["SEED_AGGREGATION"]
        self.assertEqual(seeds["coarse_and_refinement_seed"], 20260818)
        self.assertEqual(seeds["confirmation_seeds"], [20260819, 20260820])
        self.assertIn("arithmetic mean", seeds["oof_observation_raw_score"])
        scores = self.namespace["RAW_SCORE_INTERFACE"]
        self.assertIn("decision_function", scores["hist_gradient_boosting"])
        self.assertIn("output_margin=True", scores["xgboost"])
        self.assertIn("logit(clip", scores["random_forest"])
        selection = self.namespace["SELECTION_POLICY"]
        self.assertFalse(selection["threshold"]["independent_generalization_estimate"])
        roster = self.namespace["FAMILY_REPRESENTATIVE_ROSTER"]
        self.assertTrue(roster["one_representative_per_family"])
        self.assertFalse(roster["validation_may_remove_or_replace_test_roster_members"])

    def test_qnn_reproducibility_and_resource_caps(self) -> None:
        packages = self.namespace["QNN_ARCHITECTURE_PACKAGES"]
        self.assertEqual(
            {name: value["trainable_parameters_q4_depth2_including_head"] for name, value in packages.items()},
            {"ROT_CNOT_RING": 29, "RY_RZ_CZ_BRICKWORK": 21, "RY_CRX_RING": 21},
        )
        stage = self.namespace["QNN_STAGE_Q1"]
        self.assertIn("architecture_packages", stage["interpretation"])
        self.assertIn("fewer_trainable_parameters", stage["tie_break"])
        self.assertFalse(stage["stage_q2_may_change_ansatz"])
        self.assertEqual(sum(self.namespace["QNN_BUDGET"].values()), 240)
        self.assertEqual(self.namespace["DIAGNOSTIC_BUDGET"]["total"], 12)

    def test_gate_verdict_and_test_lock(self) -> None:
        self.assertEqual(self.namespace["TECHNICAL_FREEZE_GATE_VERDICT"], "MODEL STAGE READY TO FREEZE")
        policy = self.namespace["VALIDATION_AND_TEST_POLICY"]
        self.assertTrue(policy["second_freeze_gate"]["test_may_open_only_after_committed_test_ready_manifest"])
        self.assertFalse(policy["external_validation"]["may_remove_models_from_test_roster"])


if __name__ == "__main__":
    unittest.main()

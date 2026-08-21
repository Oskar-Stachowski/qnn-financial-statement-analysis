"""Static integrity tests for the post-coarse refinement/QNN package.

These tests do not load project data and do not fit any model.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs/post_coarse_experiment_v1_0_0.yaml"
AMENDMENT_PATH = ROOT / "configs/model_stage_v1_3_0_neural_comparator_amendment.yaml"
CONTRACT_PATH = ROOT / "configs/model_execution_contract_v1_2_0_scientific_patch.yaml"
REGISTRY_PATH = ROOT / "configs/model_stage_candidates_v1_scientific_patch.json"
INFERENCE_PATH = ROOT / "src/modeling/neural_comparison_inference.py"
COARSE_MANIFEST_PATH = (
    ROOT
    / "data/model_runs/classical_mlp_coarse_v1/classical_mlp_coarse_search_manifest.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PostCoarseStaticIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))[
            "post_coarse_execution"
        ]
        cls.amendment = yaml.safe_load(AMENDMENT_PATH.read_text(encoding="utf-8"))[
            "methodology_amendment"
        ]
        cls.contract = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))

    def test_amendment_hash_matches_controller_config(self) -> None:
        self.assertEqual(
            sha256(AMENDMENT_PATH),
            self.config["authority"]["methodology_amendment"]["sha256"],
        )

    def test_base_authority_hashes_match_target_repository(self) -> None:
        self.assertEqual(
            sha256(CONTRACT_PATH),
            self.config["authority"]["base_execution_contract"]["sha256"],
        )
        self.assertEqual(
            sha256(REGISTRY_PATH),
            self.config["authority"]["candidate_registry"]["sha256"],
        )
        self.assertEqual(
            sha256(COARSE_MANIFEST_PATH),
            self.config["coarse_source"]["manifest_sha256"],
        )

    def test_primary_refinement_rule_is_unchanged_and_capped_at_three(self) -> None:
        policy = yaml.safe_load((ROOT / "configs/model_stage_v1.yaml").read_text(encoding="utf-8"))["candidate_materialization"]["conditional_refinement"]
        self.assertEqual(policy["maximum_families"], 3)
        self.assertEqual(
            self.config["primary_refinement"][
                "expected_qualified_families_ordered"
            ],
            ["xgboost", "hist_gradient_boosting", "random_forest"],
        )
        self.assertFalse(
            self.amendment["primary_track"][
                "supplemental_mlp_may_change_primary_global_winner"
            ]
        )

    def test_supplemental_mlp_uses_only_existing_frozen_candidates(self) -> None:
        configured_ids = self.config["supplemental_mlp_comparator"][
            "refinement_configuration_ids"
        ]
        registry_ids = [
            row["configuration_id"]
            for row in self.registry["refinement"]["pytorch_mlp"]
        ]
        self.assertEqual(configured_ids, registry_ids)
        self.assertEqual(len(configured_ids), 8)
        self.assertTrue(
            all("epochs_300" in configuration_id for configuration_id in configured_ids)
        )

    def test_qnn_scope_matches_frozen_registry(self) -> None:
        self.assertEqual(len(self.registry["qnn"]["stage_q1"]), 3)
        self.assertEqual(len(self.registry["qnn"]["stage_q2"]), 4)
        self.assertEqual(self.config["qnn"]["q1_logical_positions"], 9)
        self.assertEqual(self.config["qnn"]["confirmation_additional_fold_fits"], 36)


    def test_clustered_bootstrap_policy_is_frozen(self) -> None:
        policy = self.config["inference"]
        amendment_policy = self.amendment["neural_comparison_inference"]
        self.assertEqual(policy["resampling_unit"], "economic_group_id")
        self.assertTrue(policy["paired_cluster_draws_across_models"])
        self.assertEqual(policy["replicates"], 2000)
        self.assertEqual(policy["seed"], 20260818)
        self.assertEqual(policy["minimum_valid_replicates"], 1900)
        self.assertFalse(policy["selection_adjusted"])
        self.assertFalse(policy["bootstrap_probability_is_p_value"])
        self.assertEqual(amendment_policy["replicates"], 2000)
        self.assertEqual(amendment_policy["random_seed"], 20260818)
        self.assertFalse(amendment_policy["selection_adjusted_inference"])
        self.assertFalse(amendment_policy["formal_quantum_superiority_claim_allowed"])
        self.assertTrue(INFERENCE_PATH.is_file())
        self.assertIn(
            "src/modeling/neural_comparison_inference.py",
            self.config["git_gate"]["authority_files"],
        )

    def test_protected_years_remain_closed(self) -> None:
        boundary = self.amendment["data_and_claim_boundaries"]
        self.assertEqual(boundary["protected_feature_years"], [2021, 2022, 2023, 2024])
        self.assertTrue(boundary["protected_data_must_not_be_deserialized"])
        self.assertTrue(
            self.config["execution_gates"][
                "protected_feature_years_must_remain_closed"
            ]
        )


if __name__ == "__main__":
    unittest.main()

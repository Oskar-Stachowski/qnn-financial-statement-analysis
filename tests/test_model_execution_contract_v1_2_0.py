from __future__ import annotations

import copy
import math
import random
from pathlib import Path
import unittest

import yaml

from src.modeling.model_execution_contract import (
    align_and_average_raw_scores,
    calibration_plan,
    candidate_complexity_units,
    candidate_fold_aggregate_status,
    canonical_candidate_index,
    canonical_sha256,
    fold_retry_action,
    file_sha256,
    is_boundary_candidate,
    load_contract,
    load_registry,
    max_f1_threshold,
    merge_coarse_refinement_results,
    qnn_execution_identity,
    rank_candidates,
    second_integrity_gate_verdict,
    select_confirmation_candidates,
    select_qnn_ansatz,
    select_qnn_confirmation_candidates,
    select_refinement_families,
    software_spec_payload,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[1]


def parameters_for(family: str, *, boundary: bool = False) -> dict:
    values = {
        "dummy_prior": {"strategy": "prior", "imbalance": "none"},
        "fixed_l2_logistic": {"C": 1.0, "imbalance": "none"},
        "elastic_net_logistic": {
            "C": 0.001 if boundary else 0.1,
            "l1_ratio": 0.5,
            "imbalance": "none",
        },
        "rbf_svm": {"C": 1.0, "gamma": "scale", "imbalance": "none"},
        "random_forest": {
            "criterion": "gini",
            "max_depth": 12,
            "min_samples_leaf": 5,
            "max_features": "sqrt",
            "max_samples": 0.7,
            "imbalance": "none",
        },
        "hist_gradient_boosting": {
            "learning_rate": 0.06,
            "max_iter": 150,
            "max_leaf_nodes": 15,
            "min_samples_leaf": 50,
            "l2_regularization": 0.1,
            "max_features": 0.7,
            "imbalance": "none",
        },
        "xgboost": {
            "n_estimators": 500,
            "max_depth": 3,
            "learning_rate": 0.05,
            "subsample": 0.7,
            "colsample_bytree": 0.7,
            "min_child_weight": 5,
            "reg_alpha": 0.01,
            "reg_lambda": 5.0,
            "gamma": 0.0,
            "imbalance": "none",
        },
        "pytorch_mlp": {
            "hidden_layer_sizes": [32],
            "activation": "relu",
            "weight_decay": 0.0001,
            "learning_rate": 0.001,
            "batch_size": 64,
            "epochs": 200,
            "imbalance": "none",
        },
    }
    return copy.deepcopy(values[family])


def result_row(
    family: str,
    configuration_id: str,
    metric: float,
    *,
    block: str = "L",
    stage: str = "coarse",
    boundary: bool = False,
    seed: int = 20260818,
    status: str = "COMPLETE",
) -> dict:
    return {
        "stage": stage,
        "family": family,
        "feature_block": "BLOCK_AGNOSTIC" if family == "dummy_prior" else block,
        "configuration_id": configuration_id,
        "parameters": parameters_for(family, boundary=boundary),
        "training_seed": seed,
        "status": status,
        "pooled_oof_pr_auc": metric if status == "COMPLETE" else None,
    }


class ModelExecutionContractV120Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_contract()
        cls.registry = load_registry()
        cls.manifest = yaml.safe_load(
            (
                ROOT
                / "configs/model_execution_contract_v1_2_0_freeze_manifest.yaml"
            ).read_text(encoding="utf-8")
        )

    def test_identity_authority_and_access_boundary(self) -> None:
        identity = self.contract["execution_contract"]
        self.assertEqual(identity["version"], "1.2.0")
        self.assertEqual(identity["status"], "frozen_pre_runner_execution_contract")
        self.assertFalse(identity["production_runner_implemented"])
        self.assertFalse(identity["model_training_performed"])
        self.assertFalse(identity["protected_feature_years_opened"])
        self.assertEqual(
            self.contract["data_boundary"]["protected_feature_years"],
            [2021, 2022, 2023, 2024],
        )
        validation = validate_contract(self.contract, self.registry)
        self.assertTrue(validation["authority_hashes_match"])
        self.assertTrue(validation["candidate_index_count_matches"])
        self.assertTrue(validation["candidate_index_hash_matches"])
        self.assertTrue(validation["software_spec_hashes_match"])

    def test_freeze_manifest_hashes_components_and_preserves_historical_v1(self) -> None:
        superseded_by_pre_fit_patch = {
            "src/modeling/model_execution_contract.py",
            "tests/test_model_execution_contract_v1_2_0.py",
        }
        for section in ("authoritative_sources", "frozen_upstream"):
            for name, item in self.manifest[section].items():
                with self.subTest(section=section, name=name):
                    if item["path"] in superseded_by_pre_fit_patch:
                        self.assertTrue((ROOT / item["path"]).is_file())
                    else:
                        self.assertEqual(
                            file_sha256(ROOT / item["path"]), item["sha256"]
                        )
        historical = {
            "configs/model_stage_v1.yaml": "e9951acd7d81a15a6e60a49cc88bc3021bb20be9dd0afcad952b98cecbe62b25",
            "configs/model_stage_v1_freeze_manifest.yaml": "f7525bc4943d233a71a2bacdc17a90c2e6ca13361ad523a0a4ee8ba33579e189",
            "notebooks/05_model_stage_preregistration.ipynb": "67c4daa32a00cb0db08fbd35b950f422a277b63e22e669a449487c9a80626afc",
        }
        self.assertEqual(
            {path: file_sha256(ROOT / path) for path in historical}, historical
        )

    def test_every_candidate_has_one_canonical_order_position(self) -> None:
        index = canonical_candidate_index(self.contract, self.registry)
        self.assertEqual(len(index), 320)
        self.assertEqual([item["ordinal"] for item in index], list(range(1, 321)))
        self.assertEqual(
            canonical_sha256(index),
            "67184eac4f62909e0717bfb2e8775de275cbf3842fc9cf4dfd316e42a3b20726",
        )
        registry_ids = {
            item["configuration_id"]
            for stage in ("coarse", "refinement")
            for values in self.registry[stage].values()
            for item in values
        } | {
            item["configuration_id"]
            for stage in ("stage_q1", "stage_q2")
            for item in self.registry["qnn"][stage]
        }
        self.assertEqual(
            {item["configuration_id"] for item in index}, registry_ids
        )

    def test_ranking_is_input_order_invariant_and_uses_full_tie_key(self) -> None:
        rows = [
            result_row("elastic_net_logistic", "z", 0.70000049, block="L+D"),
            result_row("elastic_net_logistic", "b", 0.70000041, block="L"),
            result_row("elastic_net_logistic", "a", 0.70000041, block="L"),
        ]
        expected = ["a", "b", "z"]
        self.assertEqual(
            [row["configuration_id"] for row in rank_candidates(rows, self.contract)],
            expected,
        )
        random.Random(7).shuffle(rows)
        self.assertEqual(
            [row["configuration_id"] for row in rank_candidates(rows, self.contract)],
            expected,
        )

    def test_boundary_uses_full_preregistered_domain_not_sampled_list(self) -> None:
        self.assertTrue(
            is_boundary_candidate(
                "elastic_net_logistic",
                {"C": 0.001, "l1_ratio": 0.5, "imbalance": "none"},
                self.contract,
            )
        )
        self.assertFalse(
            is_boundary_candidate(
                "elastic_net_logistic",
                {"C": 0.1, "l1_ratio": 0.5, "imbalance": "none"},
                self.contract,
            )
        )
        self.assertFalse(
            is_boundary_candidate(
                "rbf_svm",
                {"C": 1.0, "gamma": "scale", "imbalance": "none"},
                self.contract,
            )
        )
        self.assertTrue(
            is_boundary_candidate(
                "random_forest",
                {**parameters_for("random_forest"), "max_depth": None},
                self.contract,
            )
        )

    def test_refinement_activation_is_deterministic_inclusive_and_capped_at_three(self) -> None:
        rows = [result_row("fixed_l2_logistic", "global", 0.8000)]
        family_metrics = {
            "elastic_net_logistic": 0.7990,
            "rbf_svm": 0.7980,
            "hist_gradient_boosting": 0.7970,
            "xgboost": 0.7960,
        }
        for family, metric in family_metrics.items():
            rows.append(
                result_row(
                    family,
                    f"{family}-leader",
                    metric,
                    boundary=family == "elastic_net_logistic",
                )
            )
            rows.append(result_row(family, f"{family}-runner", metric - 0.002))
        selected = select_refinement_families(rows, self.contract)
        self.assertEqual(
            [item["family"] for item in selected],
            ["elastic_net_logistic", "rbf_svm", "hist_gradient_boosting"],
        )
        random.Random(11).shuffle(rows)
        self.assertEqual(select_refinement_families(rows, self.contract), selected)

    def test_merge_and_confirmation_selection_are_closed(self) -> None:
        coarse = [
            result_row("elastic_net_logistic", "coarse-a", 0.70),
            result_row("elastic_net_logistic", "coarse-b", 0.71),
            result_row("elastic_net_logistic", "coarse-c", 0.69),
        ]
        refinement = [
            result_row(
                "elastic_net_logistic",
                "refine-a",
                0.72,
                stage="refinement",
            )
        ]
        activations = [{"family": "elastic_net_logistic", "feature_block": "L"}]
        merged = merge_coarse_refinement_results(
            coarse, refinement, activations, self.contract
        )
        selected = select_confirmation_candidates(merged, self.contract)
        elastic_l = [
            item
            for item in selected
            if item["family"] == "elastic_net_logistic"
            and item["feature_block"] == "L"
        ]
        self.assertEqual(
            [item["configuration_id"] for item in elastic_l],
            ["refine-a", "coarse-b"],
        )
        with self.assertRaises(ValueError):
            merge_coarse_refinement_results(
                coarse,
                [
                    result_row(
                        "elastic_net_logistic",
                        "wrong-block",
                        0.9,
                        block="L+D",
                        stage="refinement",
                    )
                ],
                activations,
                self.contract,
            )
        confirmation = self.contract["confirmation"]
        self.assertEqual(confirmation["classical_mlp_confirmation_slots"], 30)
        self.assertEqual(confirmation["classical_mlp_additional_fold_fits"], 360)
        self.assertEqual(confirmation["qnn_confirmation_slots"], 3)
        self.assertEqual(confirmation["qnn_additional_fold_fits"], 36)

    def test_complexity_units_are_static_and_qnn_counts_match_preregistration(self) -> None:
        self.assertEqual(
            candidate_complexity_units(
                "pytorch_mlp",
                parameters_for("pytorch_mlp"),
                "L",
                "coarse",
                contract=self.contract,
            ),
            14 * 32 + 32 + 32 + 1,
        )
        qnn = {"qubits_pca": 4, "layers": 2}
        self.assertEqual(
            candidate_complexity_units(
                "qnn", qnn, "L", "qnn_q1", selected_ansatz_id="ROT_CNOT_RING", contract=self.contract
            ),
            29,
        )
        self.assertEqual(
            candidate_complexity_units(
                "qnn", qnn, "L", "qnn_q1", selected_ansatz_id="RY_CRX_RING", contract=self.contract
            ),
            21,
        )

    def test_seed_alignment_uses_canonical_key_and_raw_score_mean(self) -> None:
        def row(year: int, identifier: str, score: float) -> dict:
            return {
                "validation_feature_year": year,
                "research_universe_company_year_id": identifier,
                "fold_id": f"fold_{year}",
                "target_label": int(identifier.endswith("p")),
                "economic_group_id": f"g-{identifier}",
                "prediction_timestamp": f"{year}-06-01T00:00:00Z",
                "raw_score": score,
            }

        predictions = {
            20260818: [row(2016, "b", 0.3), row(2015, "ap", 0.1)],
            20260819: [row(2015, "ap", 0.2), row(2016, "b", 0.4)],
            20260820: [row(2016, "b", 0.5), row(2015, "ap", 0.3)],
        }
        averaged = align_and_average_raw_scores(
            predictions, [20260818, 20260819, 20260820], self.contract
        )
        self.assertEqual(
            [
                (item["validation_feature_year"], item["research_universe_company_year_id"])
                for item in averaged
            ],
            [(2015, "ap"), (2016, "b")],
        )
        self.assertAlmostEqual(averaged[0]["averaged_raw_score"], 0.2)
        self.assertAlmostEqual(averaged[1]["averaged_raw_score"], 0.4)
        broken = copy.deepcopy(predictions)
        broken[20260820] = broken[20260820][:-1]
        with self.assertRaises(ValueError):
            align_and_average_raw_scores(
                broken, [20260818, 20260819, 20260820], self.contract
            )

    def test_failure_state_machine_has_no_manual_fallback(self) -> None:
        self.assertEqual(
            fold_retry_action(
                "pytorch_mlp",
                "INFRASTRUCTURE_FAILURE",
                checkpoint_valid=True,
                contract=self.contract,
            ),
            "RESUME_CHECKPOINT",
        )
        self.assertEqual(
            fold_retry_action(
                "pytorch_mlp",
                "INFRASTRUCTURE_FAILURE",
                checkpoint_valid=True,
                resume_attempts_used=1,
                contract=self.contract,
            ),
            "FRESH_RETRY",
        )
        self.assertEqual(
            fold_retry_action("xgboost", "NAN_OR_INF_RAW_SCORE", contract=self.contract),
            "NUMERICAL_INVALID",
        )
        self.assertEqual(
            fold_retry_action("elastic_net_logistic", "CONVERGENCE_WARNING", contract=self.contract),
            "CONVERGENCE_INVALID",
        )
        self.assertEqual(
            fold_retry_action("qnn", "TIMEOUT", contract=self.contract),
            "TIMEOUT_INVALID",
        )
        complete = {f"fold_{year}": "COMPLETE" for year in range(2015, 2021)}
        self.assertEqual(
            candidate_fold_aggregate_status(complete, self.contract), "COMPLETE"
        )
        complete["fold_2018"] = "TIMEOUT_INVALID"
        self.assertEqual(
            candidate_fold_aggregate_status(complete, self.contract),
            "FAMILY_CANDIDATE_TECHNICALLY_INVALID",
        )
        self.assertEqual(
            candidate_fold_aggregate_status(
                complete, self.contract, family="qnn"
            ),
            "QNN_CANDIDATE_TECHNICALLY_INVALID",
        )

    def test_qnn_q1_and_q2_selection_have_no_manual_tie(self) -> None:
        q1_rows = []
        for ansatz in ("ROT_CNOT_RING", "RY_RZ_CZ_BRICKWORK", "RY_CRX_RING"):
            q1_rows.append(
                {
                    "stage": "qnn_q1",
                    "family": "qnn",
                    "feature_block": "L",
                    "configuration_id": f"q1-{ansatz}",
                    "parameters": {
                        "ansatz": ansatz,
                        "qubits_pca": 4,
                        "layers": 2,
                        "imbalance": "sqrt",
                    },
                    "training_seed": 20260818,
                    "status": "COMPLETE",
                    "pooled_oof_pr_auc": 0.7,
                }
            )
        selected_ansatz = select_qnn_ansatz(q1_rows, self.contract)
        self.assertEqual(
            selected_ansatz["selected_ansatz_id"], "RY_RZ_CZ_BRICKWORK"
        )
        q2_rows = []
        for block in ("L", "L+D", "L+D+R"):
            for configuration_id, imbalance, layers in (
                ("q2-a", "sqrt", 1),
                ("q2-b", "none", 3),
            ):
                q2_rows.append(
                    {
                        "stage": "qnn_q2",
                        "family": "qnn",
                        "feature_block": block,
                        "configuration_id": configuration_id,
                        "selected_ansatz_id": "RY_RZ_CZ_BRICKWORK",
                        "parameters": {
                            "qubits_pca": 4,
                            "layers": layers,
                            "imbalance": imbalance,
                        },
                        "training_seed": 20260818,
                        "status": "COMPLETE",
                        "pooled_oof_pr_auc": 0.7,
                    }
                )
        selected_q2 = select_qnn_confirmation_candidates(q2_rows, self.contract)
        self.assertEqual(len(selected_q2), 3)
        self.assertTrue(
            all(item["configuration_id"] == "q2-b" for item in selected_q2)
        )

    def test_qnn_executable_identity_is_complete_and_hash_sensitive(self) -> None:
        identity = qnn_execution_identity(
            "RY_RZ_CZ_BRICKWORK",
            "model_stage_v1__qnn_q2__t2",
            "L+D",
            "fold_2018",
            20260818,
            "a" * 64,
            self.contract,
            self.registry,
        )
        for field in self.contract["qnn_executable_identity"]["candidate_identity_fields"]:
            self.assertIn(field, identity)
        changed = qnn_execution_identity(
            "RY_RZ_CZ_BRICKWORK",
            "model_stage_v1__qnn_q2__t2",
            "L+D",
            "fold_2018",
            20260819,
            "a" * 64,
            self.contract,
            self.registry,
        )
        self.assertNotEqual(
            identity["executable_identity_sha256"],
            changed["executable_identity_sha256"],
        )

    def test_environment_spec_hashes_are_frozen(self) -> None:
        self.assertEqual(
            canonical_sha256(software_spec_payload("classical", self.contract)),
            "11fa28a6ee9599eeb0d8bc0ed459f75dfedaf506b8191649f114d98f4cf82a6c",
        )
        self.assertEqual(
            canonical_sha256(software_spec_payload("qnn_mlp", self.contract)),
            "7ff0365d25d1ff2d5dc6bdcdfd926f454b2b080d11284e420c56ee2d1a2c44a3",
        )

    def test_calibration_and_exact_max_f1_degenerate_rules(self) -> None:
        constant = calibration_plan([0, 1, 1, 0], [0.5, 0.5, 0.5, 0.5])
        self.assertEqual(constant["status"], "CONSTANT_SCORE_INTERCEPT_ONLY")
        self.assertEqual(constant["coefficient"], 0.0)
        self.assertAlmostEqual(constant["intercept"], 0.0)
        self.assertEqual(
            calibration_plan([1, 1], [0.1, 0.2])["status"],
            "CALIBRATION_TECHNICALLY_INVALID",
        )
        threshold = max_f1_threshold(
            [1, 0, 0, 1], [0.4, 0.3, 0.2, 0.1]
        )
        self.assertEqual(threshold["status"], "THRESHOLD_SELECTED")
        self.assertEqual(threshold["threshold"], 0.4)
        self.assertEqual(
            max_f1_threshold([1, 1], [0.2, 0.8])["status"],
            "THRESHOLD_NOT_CREATED_CALIBRATION_INVALID",
        )

    def test_interpretability_and_robustness_cannot_rerank(self) -> None:
        interpretation = self.contract["interpretability_execution_scope"]
        robustness = self.contract["robustness_execution_scope"]
        self.assertFalse(interpretation["may_change_primary_ranking_or_roster"])
        self.assertFalse(
            robustness["may_change_primary_ranking_roster_calibration_or_threshold"]
        )
        self.assertEqual(len(robustness["global_winner_mandatory_pipeline_runs"]), 5)
        self.assertEqual(len(robustness["global_winner_mandatory_label_runs"]), 3)
        self.assertEqual(len(robustness["qnn_structural_runs_if_qnn_feasible"]), 4)

    def test_second_gate_is_integrity_only_and_cannot_consume_performance(self) -> None:
        gate = self.contract["second_freeze_gate"]
        evidence = {
            "checks": {item: True for item in gate["pass_requires_all"]},
            "performance_metric_fields_consumed": False,
            "manual_override_or_waiver": False,
        }
        self.assertEqual(
            second_integrity_gate_verdict(evidence, self.contract),
            "MODEL_EXECUTION_V1_2_INTEGRITY_PASS",
        )
        evidence["2021_2022_PR_AUC_value"] = 0.99
        self.assertEqual(
            second_integrity_gate_verdict(evidence, self.contract),
            "MODEL_EXECUTION_V1_2_INTEGRITY_FAIL",
        )
        self.assertFalse(gate["performance_magnitude_may_change_verdict"])

    def test_reference_module_has_no_project_data_or_runner_implementation(self) -> None:
        source = (
            ROOT / "src/modeling/model_execution_contract.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "read_csv(",
            "read_parquet(",
            "data/processed/",
            "data/interim/",
            ".fit(",
            "torch.optim",
            "xgboost.train",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

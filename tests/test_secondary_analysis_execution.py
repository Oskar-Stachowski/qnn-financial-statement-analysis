"""Synthetic/static tests for secondary-development execution v1.1.0."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np

from src.modeling.secondary_analysis_execution import (
    CLASSICAL_PYTHON,
    DEFAULT_CONFIG,
    QNN_PYTHON,
    ROOT,
    RUNNER_CONFIG,
    SecondarySubprocessFoldExecutor,
    execute_classical_robustness,
    execute_pca_controls,
    execute_qnn_robustness,
    frozen_schedule,
    load_execution_config,
    package_status,
    synthetic_smoke,
    verify_static_authority,
)
from src.modeling.secondary_analysis_execution_worker import grouped_permutation
from src.modeling.model_execution_contract import load_contract
from src.modeling.production_runner import FoldTask
from src.modeling.secondary_analysis_schemas import canonical_sha256


class SecondaryAnalysisExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_execution_config(DEFAULT_CONFIG)

    def test_frozen_schedule_is_exactly_96_unique_tasks(self) -> None:
        schedule, tasks = frozen_schedule(self.config)
        identities = [task["task_identity_sha256"] for task in tasks]
        self.assertEqual(len(tasks), 96)
        self.assertEqual(len(set(identities)), 96)
        self.assertEqual(schedule["counts"]["pca_matched_control_fold_fits"], 12)
        self.assertEqual(schedule["counts"]["global_winner_robustness_fold_fits"], 48)
        self.assertEqual(schedule["counts"]["qnn_structural_robustness_fold_fits"], 24)

    def test_static_authority_and_status_do_not_read_project_data(self) -> None:
        verified = verify_static_authority(self.config)
        status = package_status(DEFAULT_CONFIG)
        self.assertGreaterEqual(len(verified), 7)
        self.assertEqual(status["status"], "PASS")
        self.assertFalse(status["project_data_read"])
        self.assertFalse(status["project_model_fit_performed"])
        self.assertFalse(status["protected_feature_years_opened"])

    def test_all_frozen_execution_routes_are_present(self) -> None:
        section = self.config["secondary_development_execution"]
        self.assertEqual(len(section["preprocessing_variants"]), 5)
        self.assertEqual(len(section["label_variants"]), 3)
        self.assertEqual(len(section["qnn_structural_variants"]), 4)
        self.assertEqual(
            section["qnn_structural_variants"]
            ["replace_entangling_gates_with_identity"]["executable_ansatz_id"],
            "ROT_IDENTITY",
        )
        self.assertFalse(section["data_boundary"]["raw_directory_may_be_read"])
        self.assertEqual(section["data_boundary"]["protected_feature_years"], [2021, 2022, 2023, 2024])

    def test_synthetic_preprocessing_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = synthetic_smoke(DEFAULT_CONFIG, Path(directory))
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(len(report["checks"]), 7)
        self.assertFalse(report["project_data_read"])
        self.assertFalse(report["project_model_fit_performed"])

    def test_grouped_permutation_is_deterministic_on_generated_arrays(self) -> None:
        rng = np.random.default_rng(20260818)
        x_train = rng.normal(size=(80, 4))
        x_validation = rng.normal(size=(24, 4))
        y_train = (x_train[:, 0] - 0.5 * x_train[:, 2] > 0).astype(np.int64)
        y_validation = (x_validation[:, 0] - 0.5 * x_validation[:, 2] > 0).astype(np.int64)
        arrays = {
            "x_train_base": x_train,
            "x_validation_base": x_validation,
            "y_train": y_train,
            "y_validation": y_validation,
            "sample_weight": np.ones(len(y_train), dtype=np.float64),
            "cluster_codes": np.arange(len(y_validation), dtype=np.int64),
        }
        task = {
            "family": "fixed_l2_logistic",
            "parameters": {"C": 1.0, "imbalance": "none"},
            "source_stage": "coarse",
            "seeds": [20260818],
            "feature_groups": [[0, 2], [1, 3]],
            "feature_names": ["feature_a", "feature_b"],
            "repetitions": 4,
            "permutation_seed": 20260818,
        }
        first = grouped_permutation(task, arrays)
        second = grouped_permutation(task, arrays)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "COMPLETE")
        self.assertEqual(len(first["feature_results"]), 2)

    def test_grouped_permutation_fails_closed_on_repeated_cluster(self) -> None:
        arrays = {
            "x_train_base": np.arange(32, dtype=float).reshape(8, 4),
            "x_validation_base": np.arange(16, dtype=float).reshape(4, 4),
            "y_train": np.asarray([0, 1] * 4),
            "y_validation": np.asarray([0, 1, 0, 1]),
            "sample_weight": np.ones(8),
            "cluster_codes": np.asarray([0, 0, 1, 2]),
        }
        task = {
            "family": "fixed_l2_logistic",
            "parameters": {"C": 1.0, "imbalance": "none"},
            "source_stage": "coarse", "seeds": [20260818],
            "feature_groups": [[0, 2], [1, 3]],
            "feature_names": ["a", "b"], "repetitions": 2,
            "permutation_seed": 20260818,
        }
        with self.assertRaises(ValueError):
            grouped_permutation(task, arrays)

    def test_all_84_fold_fit_tasks_and_exact_resume_on_synthetic_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = (
                execute_pca_controls(DEFAULT_CONFIG, output, synthetic=True),
                execute_classical_robustness(DEFAULT_CONFIG, output, synthetic=True),
                execute_qnn_robustness(DEFAULT_CONFIG, output, synthetic=True),
            )
            second = (
                execute_pca_controls(DEFAULT_CONFIG, output, synthetic=True),
                execute_classical_robustness(DEFAULT_CONFIG, output, synthetic=True),
                execute_qnn_robustness(DEFAULT_CONFIG, output, synthetic=True),
            )
        self.assertEqual([item["complete_tasks"] for item in first], [12, 48, 24])
        self.assertEqual(first, second)

    def test_identity_entangler_qnn_route_in_pinned_worker(self) -> None:
        executor = SecondarySubprocessFoldExecutor(
            root=ROOT,
            classical_python=CLASSICAL_PYTHON,
            qnn_python=QNN_PYTHON,
            runner_config_path=RUNNER_CONFIG,
        )
        parameters = {
            "qubits_pca": 4,
            "layers": 1,
            "epochs": 1,
            "batch_size": 4,
            "learning_rate": 0.01,
            "weight_decay": 0.0001,
            "imbalance": "none",
        }
        checkpoint_identity = {
            "family": "qnn",
            "configuration_id": "synthetic_identity_entangler_smoke",
            "parameters_sha256": canonical_sha256(parameters),
            "feature_block": "L+D+R",
            "fold_id": "fold_2015",
            "training_seed": 20260818,
            "train_membership_sha256": canonical_sha256(["train"]),
            "validation_membership_sha256": canonical_sha256(["validation"]),
            "preprocessing_sha256": canonical_sha256({"synthetic": True}),
            "pca_sha256_if_applicable": canonical_sha256({"synthetic_pca": 4}),
            "software_environment_sha256": executor.environment_hashes["qnn_mlp"],
            "device_identity": load_contract(executor.contract_path)[
                "qnn_executable_identity"
            ]["device_identity"],
        }
        task = FoldTask(
            stage="secondary::synthetic_qnn_identity_smoke",
            family="qnn",
            feature_block="L+D+R",
            configuration_id="synthetic_identity_entangler_smoke",
            parameters=parameters,
            training_seed=20260818,
            fold_id="fold_2015",
            validation_feature_year=2015,
            selected_ansatz_id="ROT_IDENTITY",
            train_membership_sha256=checkpoint_identity["train_membership_sha256"],
            validation_membership_sha256=checkpoint_identity[
                "validation_membership_sha256"
            ],
            preprocessing_sha256=checkpoint_identity["preprocessing_sha256"],
            pca_sha256_if_applicable=checkpoint_identity[
                "pca_sha256_if_applicable"
            ],
            software_environment_role="qnn_mlp",
            checkpoint_identity=checkpoint_identity,
        )
        rng = np.random.default_rng(20260818)
        with tempfile.TemporaryDirectory() as directory:
            execution = executor.execute(
                task,
                x_train=rng.normal(size=(8, 4)),
                y_train=np.asarray([0, 1] * 4, dtype=np.int64),
                x_validation=rng.normal(size=(3, 4)),
                sample_weight=np.ones(8, dtype=np.float64),
                checkpoint_path=Path(directory) / "checkpoint.pt",
                timeout_seconds=300,
            )
        self.assertEqual(execution.status, "COMPLETE")
        self.assertEqual(np.asarray(execution.raw_scores).shape, (3,))
        self.assertTrue(np.isfinite(execution.raw_scores).all())


if __name__ == "__main__":
    unittest.main()

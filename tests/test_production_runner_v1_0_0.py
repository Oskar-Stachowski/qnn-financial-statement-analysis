from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import numpy as np
import yaml

from src.modeling.model_execution_contract import (
    align_and_average_raw_scores,
    canonical_candidate_index,
    canonical_sha256,
    file_sha256,
    max_f1_threshold,
)
from src.modeling.production_runner import (
    FoldExecution,
    ProductionExperimentRunner,
    ProtectedDataAccessError,
    RunnerIntegrityError,
    SubprocessFoldExecutor,
    SyntheticFoldExecutor,
    synthetic_dataset,
    synthetic_expectations,
)
from src.modeling.verify_environment_locks import verify as verify_environment_locks


ROOT = Path(__file__).resolve().parents[1]


class ProductionRunnerPolicyTests(unittest.TestCase):
    def make_runner(self, output: Path, **kwargs) -> ProductionExperimentRunner:
        return ProductionExperimentRunner(
            output_dir=output,
            executor=SyntheticFoldExecutor(),
            **kwargs,
        )

    def test_preflight_binds_exact_contract_registry_and_candidate_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runner = self.make_runner(Path(directory))
            index = canonical_candidate_index(runner.contract, runner.registry)
            self.assertEqual(len(index), 320)
            self.assertEqual(
                canonical_sha256(index),
                "263635db04d87466b182f3a853910e2cc6ca11a284deeb57969b5cbea43faf21",
            )

    def test_protected_year_is_rejected_before_execution(self) -> None:
        sample = synthetic_dataset(4)
        sample.loc[0, "feature_year"] = 2021
        with tempfile.TemporaryDirectory() as directory:
            runner = self.make_runner(Path(directory))
            with self.assertRaises(ProtectedDataAccessError):
                runner._canonicalize_sample(sample)

    def test_nonfrozen_data_path_fails_before_pandas_read(self) -> None:
        config = yaml.safe_load(
            (ROOT / "configs/production_experiment_runner_v1_0_0.yaml").read_text()
        )
        config["data"]["frozen_train_inputs"]["raw_x_t_train"][
            "path"
        ] = "data/processed/protected_2021_2024.csv"
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "mutated_runner.yaml"
            config_path.write_text(yaml.safe_dump(config, sort_keys=False))
            with mock.patch("pandas.read_csv") as read_csv:
                with self.assertRaises(RunnerIntegrityError):
                    self.make_runner(Path(directory) / "out", runner_config_path=config_path)
                read_csv.assert_not_called()

    def test_changed_candidate_registry_or_hash_is_hard_failure(self) -> None:
        registry = json.loads(
            (ROOT / "configs/model_stage_candidates_v1.json").read_text()
        )
        registry["coarse"]["fixed_l2_logistic"][0]["configuration_id"] += "_MUTATED"
        config = yaml.safe_load(
            (ROOT / "configs/production_experiment_runner_v1_0_0.yaml").read_text()
        )
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            registry_path = directory_path / "registry.json"
            registry_path.write_text(json.dumps(registry, sort_keys=True))
            config["authority"]["candidate_registry"] = {
                "path": str(registry_path),
                "sha256": file_sha256(registry_path),
            }
            config_path = directory_path / "runner.yaml"
            config_path.write_text(yaml.safe_dump(config, sort_keys=False))
            with self.assertRaises(RunnerIntegrityError):
                self.make_runner(
                    directory_path / "out", runner_config_path=config_path
                )

    def test_changed_sample_or_fold_membership_is_hard_failure(self) -> None:
        sample = synthetic_dataset(4)
        expectations = synthetic_expectations(sample)
        changed = sample.iloc[1:].copy()
        with tempfile.TemporaryDirectory() as directory:
            runner = self.make_runner(Path(directory))
            with self.assertRaises(RunnerIntegrityError):
                runner.verify_sample_and_folds(changed, expectations)

    def test_dry_run_never_calls_executor(self) -> None:
        class ForbiddenExecutor(SyntheticFoldExecutor):
            def execute(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise AssertionError("dry-run attempted model fit")

        sample = synthetic_dataset(4)
        with tempfile.TemporaryDirectory() as directory:
            runner = ProductionExperimentRunner(
                output_dir=Path(directory), executor=ForbiddenExecutor()
            )
            report = runner.run(
                sample,
                expectations=synthetic_expectations(sample),
                dry_run=True,
            )
            self.assertFalse(report["model_fit_performed"])
            self.assertEqual(report["candidate_positions"], 320)

    def test_oof_alignment_and_fsum_seed_aggregation_are_order_invariant(self) -> None:
        sample_rows = [
            {
                "validation_feature_year": year,
                "research_universe_company_year_id": identity,
                "fold_id": f"fold_{year}",
                "target_label": label,
                "economic_group_id": f"G-{identity}",
                "prediction_timestamp": f"{year}-04-30T12:00:00+00:00",
                "raw_score": score,
            }
            for year, identity, label, score in (
                (2016, "B", 0, 0.2),
                (2015, "A", 1, 0.7),
            )
        ]
        predictions = {
            20260818: sample_rows,
            20260819: [{**row, "raw_score": row["raw_score"] + 0.1} for row in reversed(sample_rows)],
            20260820: [{**row, "raw_score": row["raw_score"] - 0.1} for row in sample_rows],
        }
        first = align_and_average_raw_scores(
            predictions, [20260818, 20260819, 20260820]
        )
        second = align_and_average_raw_scores(
            {seed: list(reversed(rows)) for seed, rows in predictions.items()},
            [20260818, 20260819, 20260820],
        )
        self.assertEqual(first, second)
        self.assertEqual(
            [row["research_universe_company_year_id"] for row in first], ["A", "B"]
        )

    def test_checkpoint_resume_then_fresh_retry_order_is_frozen(self) -> None:
        class ScriptedExecutor(SubprocessFoldExecutor):
            def __init__(self) -> None:
                self.calls: list[bool] = []

            def _one_attempt(self, task, **kwargs):  # type: ignore[no-untyped-def]
                resume = bool(kwargs["resume"])
                self.calls.append(resume)
                checkpoint_path = kwargs["checkpoint_path"]
                if len(self.calls) == 1:
                    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
                    checkpoint_path.write_bytes(b"synthetic checkpoint")
                status = (
                    "INFRASTRUCTURE_FAILURE"
                    if len(self.calls) < 3
                    else "COMPLETE"
                )
                audit = {"attempt": len(self.calls), "resume": resume, "outcome": status}
                return (
                    FoldExecution(
                        status=status,
                        raw_scores=np.array([0.0]) if status == "COMPLETE" else None,
                        failure_code=(
                            "WORKER_PROCESS_LOST_BY_OS_SIGNAL"
                            if status != "COMPLETE"
                            else None
                        ),
                        software_environment_sha256="synthetic",
                        device_identity="cpu",
                        attempts=[audit],
                    ),
                    audit,
                )

        from src.modeling.production_runner import FoldTask

        task = FoldTask(
            stage="coarse",
            family="pytorch_mlp",
            feature_block="L",
            configuration_id="synthetic",
            parameters={},
            training_seed=20260818,
            fold_id="fold_2015",
            validation_feature_year=2015,
            selected_ansatz_id=None,
            train_membership_sha256="a",
            validation_membership_sha256="b",
            preprocessing_sha256="c",
            pca_sha256_if_applicable=None,
            software_environment_role="qnn_mlp",
            checkpoint_identity={},
        )
        with tempfile.TemporaryDirectory() as directory:
            executor = ScriptedExecutor()
            result = executor.execute(
                task,
                x_train=np.zeros((2, 1)),
                y_train=np.array([0, 1]),
                x_validation=np.zeros((1, 1)),
                sample_weight=np.ones(2),
                checkpoint_path=Path(directory) / "checkpoint.pt",
                timeout_seconds=1,
            )
            self.assertEqual(result.status, "COMPLETE")
            self.assertEqual(executor.calls, [False, True, False])

    def test_numeric_worker_has_no_project_data_loader(self) -> None:
        source = (ROOT / "src/modeling/production_worker.py").read_text()
        for forbidden in (
            "read_csv(",
            "read_parquet(",
            "data/processed/",
            "data/interim/",
            "2021",
            "2022",
            "2023",
            "2024",
        ):
            self.assertNotIn(forbidden, source)


class SyntheticEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_a = tempfile.TemporaryDirectory()
        cls.temp_b = tempfile.TemporaryDirectory()
        cls.sample = synthetic_dataset(4)
        cls.expectations = synthetic_expectations(cls.sample)
        runner_a = ProductionExperimentRunner(
            output_dir=Path(cls.temp_a.name), executor=SyntheticFoldExecutor()
        )
        runner_b = ProductionExperimentRunner(
            output_dir=Path(cls.temp_b.name), executor=SyntheticFoldExecutor()
        )
        cls.ranking_a = runner_a.run(cls.sample, expectations=cls.expectations)
        cls.ranking_b = runner_b.run(cls.sample, expectations=cls.expectations)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_a.cleanup()
        cls.temp_b.cleanup()

    def test_full_flow_and_required_artifacts_complete(self) -> None:
        root = Path(self.temp_a.name)
        required = (
            "refinement_activation.json",
            "confirmation_selection.json",
            "qnn_selected_ansatz.json",
            "canonical_candidate_result_table.json",
            "final_family_roster.json",
            "qnn_feasibility_and_executable_identity.json",
            "secondary_analysis_execution_plan.json",
            "final_ranking_manifest.json",
            "run_manifest.json",
        )
        self.assertTrue(all((root / path).is_file() for path in required))
        run = json.loads((root / "run_manifest.json").read_text())
        self.assertEqual(run["status"], "COMPLETE")
        self.assertTrue(run["model_fit_performed"])
        self.assertFalse(run["project_data_model_fit_performed"])
        self.assertFalse(run["protected_feature_years_opened"])
        self.assertTrue(self.ranking_a["family_ranking"])

    def test_refinement_confirmation_and_result_manifests_are_accounted(self) -> None:
        root = Path(self.temp_a.name)
        activation = json.loads((root / "refinement_activation.json").read_text())
        self.assertLessEqual(len(activation["activations"]), 3)
        confirmation = json.loads((root / "confirmation_selection.json").read_text())
        self.assertEqual(len(confirmation["classical_mlp"]), 30)
        self.assertEqual(len(confirmation["qnn"]), 3)
        manifests = list(root.glob("candidate_results/**/result_manifest.json"))
        self.assertGreaterEqual(len(manifests), 1986)
        for path in manifests[:25]:
            manifest = json.loads(path.read_text())
            self.assertEqual(manifest["status"], "COMPLETE")
            self.assertTrue("task_identity_sha256" in manifest or "identity" in manifest)

    def test_two_fresh_runs_have_identical_ranking_and_artifact_hashes(self) -> None:
        self.assertEqual(self.ranking_a, self.ranking_b)
        for relative in (
            "refinement_activation.json",
            "confirmation_selection.json",
            "qnn_selected_ansatz.json",
            "canonical_candidate_result_table.json",
            "final_family_roster.json",
            "final_ranking_manifest.json",
        ):
            left = hashlib.sha256((Path(self.temp_a.name) / relative).read_bytes()).hexdigest()
            right = hashlib.sha256((Path(self.temp_b.name) / relative).read_bytes()).hexdigest()
            self.assertEqual(left, right, relative)

    def test_calibration_and_threshold_use_frozen_exact_algorithm(self) -> None:
        root = Path(self.temp_a.name)
        representative = next(
            row
            for row in self.ranking_a["family_ranking"]
            if row.get("oof_prediction_artifact")
        )
        prediction = json.loads(
            (root / representative["oof_prediction_artifact"]).read_text()
        )
        calibration_entry = next(
            row
            for row in self.ranking_a["calibration_and_threshold"]
            if row["identity"]["family"] == representative["family"]
            and row["identity"]["configuration_id"]
            == representative["configuration_id"]
            and row["identity"]["feature_block"] == representative["feature_block"]
        )
        calibration = json.loads(
            (root / calibration_entry["calibration_artifact"]).read_text()
        )
        threshold = json.loads(
            (root / calibration_entry["threshold_artifact"]).read_text()
        )
        coefficient = float.fromhex(calibration["coef_float64_hex"])
        intercept = float.fromhex(calibration["intercept_float64_hex"])
        scores = np.asarray([row["raw_score"] for row in prediction["rows"]])
        labels = [int(row["target_label"]) for row in prediction["rows"]]
        probabilities = 1.0 / (1.0 + np.exp(-(coefficient * scores + intercept)))
        expected = max_f1_threshold(labels, probabilities.tolist())
        self.assertEqual(
            threshold["threshold_float64_hex"], expected["threshold_float64_hex"]
        )
        self.assertEqual(
            threshold["achieved_f1_numerator"], expected["achieved_f1_numerator"]
        )
        self.assertEqual(
            threshold["achieved_f1_denominator"], expected["achieved_f1_denominator"]
        )


class EnvironmentLockTests(unittest.TestCase):
    def lock_versions(self, path: Path) -> dict[str, str]:
        versions: dict[str, str] = {}
        for line in path.read_text().splitlines():
            match = re.match(r"^([A-Za-z0-9_.-]+)==([^ \\\n]+)", line)
            if match:
                versions[match.group(1).lower()] = match.group(2)
        return versions

    def test_lockfiles_are_hash_complete_and_match_fresh_smoke_reports(self) -> None:
        cases = {
            "classical": ROOT / "environments/classical/requirements.lock",
            "qnn_mlp": ROOT / "environments/qnn_mlp/requirements.lock",
        }
        report_paths = {
            "classical": ROOT / "data/reports/classical_environment_smoke_v1_0_0.json",
            "qnn_mlp": ROOT / "data/reports/qnn_mlp_environment_smoke_v1_0_0.json",
        }
        for role, lock in cases.items():
            text = lock.read_text()
            self.assertNotIn("not pinned", text.lower())
            self.assertIn("--hash=sha256:", text)
            versions = self.lock_versions(lock)
            report = json.loads(report_paths[role].read_text())
            self.assertEqual(report["status"], "READY")
            self.assertEqual(report["import_errors"], {})
            self.assertEqual(report["lock_verification"]["status"], "EXACT_MATCH")
            self.assertEqual(
                report["lock_verification"][
                    "installed_distribution_count_excluding_pip"
                ],
                len(versions),
            )
            self.assertEqual(
                report["lock_verification"]["locked_distribution_count"],
                len(versions),
            )
            for package, version in report["expected_packages"].items():
                self.assertEqual(
                    versions[package.lower()], version, f"{role}/{package}"
                )
            self.assertEqual(report["host"]["ram_bytes"], 8589934592)
        verification = verify_environment_locks(
            ROOT / "configs/model_environments_v1_0_0.yaml"
        )
        self.assertEqual(verification["status"], "PASS")
        for role in cases:
            self.assertTrue(
                verification["checks"][role]["exact_installed_distribution_match"]
            )

    def test_qnn_resource_smoke_covers_all_ansatz_qubit_pairs(self) -> None:
        report = json.loads(
            (ROOT / "data/reports/qnn_resource_smoke_v1_0_0.json").read_text()
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(
            {(row["ansatz"], row["qubits"]) for row in report["cases"]},
            {
                (ansatz, qubits)
                for ansatz in (
                    "ROT_CNOT_RING",
                    "RY_RZ_CZ_BRICKWORK",
                    "RY_CRX_RING",
                )
                for qubits in (4, 6)
            },
        )
        for case in report["cases"]:
            self.assertTrue(case["outputs_finite"])
            self.assertTrue(case["gradients_finite"])
            self.assertEqual(case["deterministic_replay_max_abs_difference"], 0.0)
            self.assertEqual(case["checkpoint_round_trip_max_abs_difference"], 0.0)

    def test_production_workers_complete_synthetic_classical_mlp_and_qnn_tasks(self) -> None:
        report = json.loads(
            (
                ROOT
                / "data/reports/production_worker_synthetic_smoke_v1_0_0.json"
            ).read_text()
        )
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(
            {row["family"] for row in report["results"]},
            {"dummy_prior", "pytorch_mlp", "qnn"},
        )
        for row in report["results"]:
            self.assertEqual(row["status"], "COMPLETE")
            self.assertEqual(row["raw_score_count"], 2)
            self.assertIsNotNone(row["raw_score_sha256"])


if __name__ == "__main__":
    unittest.main()

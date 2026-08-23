"""Integrity tests for split and bounded-parallel post-coarse confirmation."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.modeling.post_coarse_runner import (
    CandidateExecutionResult,
    PostCoarseIntegrityError,
    _confirm_qnn_candidates_parallel,
    _configure_confirmation_qnn_ledger,
    load_post_coarse_config,
    require_historical_classical_confirmation_reuse,
    require_historical_qnn_reuse,
    run_confirmation_qnn_phase,
)
from src.modeling.production_runner import (
    CandidateFoldExecutionResult,
    ProductionExperimentRunner,
    SyntheticFoldExecutor,
    synthetic_dataset,
    synthetic_expectations,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    ROOT / "configs/post_coarse_experiment_v1_0_4_confirmation_fold_parallel.yaml"
)
SOURCE_QNN_MANIFEST = (
    ROOT / "data/model_runs/post_coarse_v1_3_0/qnn_phase_manifest.json"
)
SOURCE_CLASSICAL_CONFIRMATION_MANIFEST = (
    ROOT
    / "data/model_runs/post_coarse_v1_3_0/confirmation_classical_phase_manifest.json"
)
SOURCE_CONFIRMATION_SELECTION = (
    ROOT / "data/model_runs/post_coarse_v1_3_0/post_coarse_confirmation_selection.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConfirmationScheduleIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_post_coarse_config(CONFIG_PATH)
        cls.section = cls.config["post_coarse_execution"]

    def test_schedule_amendment_changes_execution_only(self) -> None:
        self.assertEqual(self.section["version"], "1.0.4")
        schedule = self.section["confirmation_schedule_amendment"]
        self.assertTrue(schedule["classical_and_qnn_confirmation_split"])
        self.assertTrue(
            schedule["classical_confirmation_must_complete_before_qnn_confirmation"]
        )
        self.assertEqual(schedule["strategy"], "global_bounded_qnn_confirmation_fold_queue")
        self.assertEqual(
            schedule["maximum_parallel_qnn_confirmation_folds"], 4
        )
        self.assertEqual(schedule["maximum_parallel_qnn_confirmation_candidates"], 1)
        self.assertTrue(schedule["fold_start_order_changed"])
        self.assertFalse(schedule["performance_results_used_to_change_schedule"])
        for key in (
            "model_definition_changed",
            "candidate_registry_changed",
            "confirmation_selection_rule_changed",
            "feature_blocks_changed",
            "hyperparameters_changed",
            "seeds_changed",
            "fold_order_within_candidate_changed",
            "simulator_backend_changed",
            "task_identity_changed",
            "protected_feature_years_opened",
        ):
            self.assertFalse(schedule[key])

    def test_historical_classical_gate_is_exact_and_deeply_valid(self) -> None:
        reuse = self.section["historical_classical_confirmation_reuse"]
        self.assertEqual(
            reuse["source_manifest"]["sha256"],
            sha256(SOURCE_CLASSICAL_CONFIRMATION_MANIFEST),
        )
        self.assertEqual(
            reuse["selection_artifact"]["sha256"],
            sha256(SOURCE_CONFIRMATION_SELECTION),
        )
        manifest = require_historical_classical_confirmation_reuse(
            config=self.config, root=ROOT
        )
        self.assertEqual(manifest["status"], "COMPLETE")
        self.assertFalse(manifest["qnn_confirmation_started"])
        self.assertEqual(len(manifest["primary_confirmed_result_references"]), 30)
        self.assertEqual(
            len(manifest["classical_extra_seed_candidate_result_references"]),
            60,
        )

    def test_confirmation_qnn_wrapper_accepts_historical_classical_gate(self) -> None:
        expected = {"status": "SENTINEL_NO_MODEL_FIT"}
        with patch(
            "src.modeling.post_coarse_runner.run_confirmation_phase",
            return_value=expected,
        ) as run_phase:
            actual = run_confirmation_qnn_phase(
                config=self.config,
                authority=object(),
                output_dir=SOURCE_CLASSICAL_CONFIRMATION_MANIFEST.parent,
            )

        self.assertEqual(actual, expected)
        run_phase.assert_called_once()
        self.assertFalse(run_phase.call_args.kwargs["stop_before_qnn_confirmation"])

    def test_historical_qnn_source_is_exact_and_deeply_valid(self) -> None:
        source = self.section["historical_qnn_reuse"]["source_manifest"]
        self.assertEqual(source["sha256"], sha256(SOURCE_QNN_MANIFEST))
        manifest = require_historical_qnn_reuse(config=self.config, root=ROOT)
        self.assertEqual(manifest["status"], "COMPLETE")
        self.assertEqual(len(manifest["q1_result_references"]), 9)
        self.assertEqual(len(manifest["q2_result_references"]), 12)
        self.assertFalse(manifest["protected_feature_years_opened"])

    def test_new_authority_files_are_declared(self) -> None:
        files = set(self.section["git_gate"]["authority_files"])
        self.assertIn(
            "configs/post_coarse_experiment_v1_0_4_confirmation_fold_parallel.yaml",
            files,
        )
        self.assertIn("tests/test_post_coarse_confirmation_schedule.py", files)
        self.assertIn("src/modeling/post_coarse_runner.py", files)
        self.assertIn("scripts/run_post_coarse.sh", files)

    def test_confirmation_ledger_forks_without_mutating_qnn_source(self) -> None:
        source_sha = sha256(SOURCE_QNN_MANIFEST)
        source_manifest = json.loads(SOURCE_QNN_MANIFEST.read_text(encoding="utf-8"))
        source_ledger_path = ROOT / source_manifest["qnn_resource_ledger"]["path"]
        source_ledger_sha = sha256(source_ledger_path)

        class FakeRunner:
            configured_path: Path | None = None

            def _configure_qnn_ledger(self, ledger_path: Path | None = None) -> None:
                self.configured_path = ledger_path

        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            confirmation_path = output_dir / "qnn_confirmation_resource_ledger.json"
            config = {
                "post_coarse_execution": {
                    "confirmation_schedule_amendment": {
                        "qnn_confirmation_resource_ledger": str(confirmation_path),
                    }
                }
            }
            runner = FakeRunner()
            actual = _configure_confirmation_qnn_ledger(
                runner=runner,
                config=config,
                source_qnn_manifest=source_manifest,
                output_dir=output_dir,
            )
            self.assertEqual(actual, confirmation_path.resolve())
            self.assertEqual(runner.configured_path, confirmation_path.resolve())
            self.assertEqual(
                json.loads(confirmation_path.read_text(encoding="utf-8")),
                json.loads(source_ledger_path.read_text(encoding="utf-8")),
            )

        self.assertEqual(sha256(SOURCE_QNN_MANIFEST), source_sha)
        self.assertEqual(sha256(source_ledger_path), source_ledger_sha)

    def test_fold_restart_reuses_complete_artifact_and_assembles_canonically(self) -> None:
        class CountingExecutor(SyntheticFoldExecutor):
            def __init__(self) -> None:
                self.task_ids: list[str] = []

            def execute(self, task, **kwargs):  # type: ignore[no-untyped-def]
                self.task_ids.append(task.identity_sha256)
                return super().execute(task, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            executor = CountingExecutor()
            runner = ProductionExperimentRunner(
                output_dir=Path(temporary), executor=executor
            )
            sample = runner._canonicalize_sample(synthetic_dataset(4))
            folds = runner.verify_sample_and_folds(
                sample, synthetic_expectations(sample)
            )
            candidate = runner._candidate_parameters(
                "coarse",
                "fixed_l2_logistic",
                "model_stage_v1__coarse__fixed_l2_logistic__001",
            )
            required_folds = list(
                runner.contract["execution_failure_state_machine"]["required_folds"]
            )
            first = runner._execute_candidate_fold(
                stage="coarse",
                family="fixed_l2_logistic",
                feature_block="L",
                candidate=candidate,
                training_seed=20260819,
                folds=folds,
                fold_id=str(required_folds[0]),
            )
            result = runner._execute_candidate(
                stage="coarse",
                family="fixed_l2_logistic",
                feature_block="L",
                candidate=candidate,
                training_seed=20260819,
                folds=folds,
            )

        self.assertEqual(first.status, "COMPLETE")
        self.assertEqual(result.row["status"], "COMPLETE")
        self.assertEqual(list(result.row["fold_statuses"]), required_folds)
        self.assertEqual(len(executor.task_ids), len(required_folds))

    def test_parallel_qnn_confirmation_is_bounded_and_ordered(self) -> None:
        class FakeExecutor:
            def request_shutdown(self) -> None:
                raise AssertionError("shutdown should not be requested")

        class FakeRunner:
            contract = {
                "execution_failure_state_machine": {
                    "required_folds": ["fold_1", "fold_2", "fold_3"]
                }
            }

            def __init__(self) -> None:
                self.executor = FakeExecutor()
                self.lock = threading.Lock()
                self.active = 0
                self.maximum_active = 0
                self.assembled: list[tuple[str, int, list[str]]] = []

            @staticmethod
            def _candidate_parameters(
                stage: str, family: str, configuration_id: str
            ) -> dict[str, object]:
                return {
                    "configuration_id": configuration_id,
                    "qubits_pca": 4,
                }

            @staticmethod
            def _prepare_fold(**kwargs: object) -> None:
                return None

            def _execute_candidate_fold(self, **kwargs: object):
                with self.lock:
                    self.active += 1
                    self.maximum_active = max(self.maximum_active, self.active)
                fold_id = str(kwargs["fold_id"])
                time.sleep(0.01 * (4 - int(fold_id[-1])))
                with self.lock:
                    self.active -= 1
                return CandidateFoldExecutionResult(
                    fold_id=fold_id,
                    status="COMPLETE",
                    manifest={"task_identity": {"fold_id": fold_id}},
                    predictions=[],
                )

            def _assemble_candidate_execution(self, **kwargs: object):
                candidate = kwargs["candidate"]
                fold_results = kwargs["fold_results"]
                configuration_id = str(candidate["configuration_id"])
                seed = int(kwargs["training_seed"])
                fold_ids = [result.fold_id for result in fold_results]
                self.assembled.append((configuration_id, seed, fold_ids))
                return CandidateExecutionResult(
                    row={
                        "configuration_id": configuration_id,
                        "training_seed": seed,
                    },
                    predictions=[],
                )

            @staticmethod
            def _aggregate_confirmed(base, extras):  # type: ignore[no-untyped-def]
                return base

        jobs = []
        for index, block in enumerate(("L", "L+D", "L+D+R"), 1):
            result = CandidateExecutionResult(
                row={
                    "stage": "qnn_q2",
                    "family": "qnn",
                    "feature_block": block,
                    "configuration_id": f"qnn-{index}",
                    "selected_ansatz_id": "ROT_CNOT_RING",
                },
                predictions=[],
            )
            jobs.append(
                (
                    result,
                    {
                        "selected_ansatz_id": "ROT_CNOT_RING",
                        "confirmation_seeds": [20260819, 20260820],
                    },
                )
            )

        runner = FakeRunner()
        results = _confirm_qnn_candidates_parallel(
            runner=runner,
            folds={
                "fold_1": (None, None, None, None),
                "fold_2": (None, None, None, None),
                "fold_3": (None, None, None, None),
            },
            jobs=jobs,
            confirmation_seeds=[20260819, 20260820],
            maximum_workers=4,
        )

        self.assertEqual(runner.maximum_active, 4)
        self.assertEqual(
            [result.row["configuration_id"] for result, _ in results],
            ["qnn-1", "qnn-2", "qnn-3"],
        )
        self.assertEqual(len(runner.assembled), 6)
        self.assertEqual(
            [(configuration, seed) for configuration, seed, _ in runner.assembled],
            [
                (configuration, seed)
                for configuration in ("qnn-1", "qnn-2", "qnn-3")
                for seed in (20260819, 20260820)
            ],
        )
        self.assertTrue(
            all(
                folds == ["fold_1", "fold_2", "fold_3"]
                for _, _, folds in runner.assembled
            )
        )

    def test_fold_parallel_qnn_matches_sequential_synthetic_results(self) -> None:
        selection = {
            "selected_ansatz_id": "ROT_CNOT_RING",
            "confirmation_seeds": [20260819, 20260820],
        }

        def execute(temporary: str, *, parallel: bool):
            runner = ProductionExperimentRunner(
                output_dir=Path(temporary), executor=SyntheticFoldExecutor()
            )
            sample = runner._canonicalize_sample(synthetic_dataset(4))
            folds = runner.verify_sample_and_folds(
                sample, synthetic_expectations(sample)
            )
            candidate = runner._candidate_parameters(
                "qnn_q2", "qnn", "model_stage_v1__qnn_q2__t0"
            )
            base = runner._execute_candidate(
                stage="qnn_q2",
                family="qnn",
                feature_block="L",
                candidate=candidate,
                training_seed=20260818,
                folds=folds,
                selected_ansatz_id="ROT_CNOT_RING",
            )
            if parallel:
                aggregate, extras = _confirm_qnn_candidates_parallel(
                    runner=runner,
                    folds=folds,
                    jobs=[(base, selection)],
                    confirmation_seeds=[20260819, 20260820],
                    maximum_workers=4,
                )[0]
            else:
                extras = [
                    runner._execute_candidate(
                        stage="qnn_q2",
                        family="qnn",
                        feature_block="L",
                        candidate=candidate,
                        training_seed=seed,
                        folds=folds,
                        selected_ansatz_id="ROT_CNOT_RING",
                    )
                    for seed in (20260819, 20260820)
                ]
                aggregate = runner._aggregate_confirmed(base, extras)
            return aggregate, extras

        with tempfile.TemporaryDirectory() as sequential_dir:
            sequential = execute(sequential_dir, parallel=False)
        with tempfile.TemporaryDirectory() as parallel_dir:
            parallel = execute(parallel_dir, parallel=True)

        self.assertEqual(parallel[0].row, sequential[0].row)
        self.assertEqual(parallel[0].predictions, sequential[0].predictions)
        self.assertEqual(
            [result.row for result in parallel[1]],
            [result.row for result in sequential[1]],
        )
        self.assertEqual(
            [result.predictions for result in parallel[1]],
            [result.predictions for result in sequential[1]],
        )

    def test_parallel_qnn_confirmation_rejects_more_than_four_workers(self) -> None:
        with self.assertRaises(PostCoarseIntegrityError):
            _confirm_qnn_candidates_parallel(
                runner=object(),
                folds={},
                jobs=[(object(), {})],
                confirmation_seeds=[20260819, 20260820],
                maximum_workers=5,
            )


if __name__ == "__main__":
    unittest.main()

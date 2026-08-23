"""Static and synthetic tests for v1.1.4 parallel/checkpoint execution."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from src.modeling import secondary_analysis_execution as base
from src.modeling.production_runner import QNNResourceLedger
from src.modeling.secondary_analysis_execution_v1_1_3 import (
    DEFAULT_CONFIG as V113_CONFIG,
    load_execution_config as load_v113_config,
)
from src.modeling.secondary_analysis_execution_v1_1_4 import (
    DEFAULT_CONFIG,
    _isolated_activation,
    _group_in_frozen_order,
    checkpoint_fold_directory,
    load_execution_config,
    ordered_parallel_map,
    synthetic_model_fit_phases_isolated,
    synthetic_pca_controls_isolated,
    synthetic_smoke_isolated,
    verify_amendment_authority,
)


ROOT = Path(__file__).resolve().parents[1]


class SecondaryExecutionParallelCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_execution_config(DEFAULT_CONFIG)
        cls.schedule, cls.tasks = base.frozen_schedule(cls.config)

    def test_scientific_identity_is_unchanged(self) -> None:
        amendment = self.config["secondary_development_execution"][
            "parallel_checkpoint_amendment"
        ]
        for field in (
            "target_values_changed",
            "sample_membership_changed",
            "fold_policy_changed",
            "task_roster_changed",
            "task_identity_changed",
            "model_parameters_changed",
            "interpretation_method_changed",
            "robustness_method_changed",
            "methodology_changed",
        ):
            self.assertFalse(amendment[field])
        inherited_schedule, inherited_tasks = base.frozen_schedule(
            load_v113_config(V113_CONFIG)
        )
        self.assertEqual(len(self.tasks), 96)
        self.assertEqual(self.schedule["counts"], inherited_schedule["counts"])
        self.assertEqual(
            [task["task_identity_sha256"] for task in self.tasks],
            [task["task_identity_sha256"] for task in inherited_tasks],
        )

    def test_parallel_limits_are_exactly_inherited(self) -> None:
        section = self.config["secondary_development_execution"]
        expected = {
            "maximum_parallel_classical_folds": 4,
            "maximum_parallel_mlp_folds": 2,
            "maximum_parallel_qnn_folds": 4,
        }
        for key, value in expected.items():
            self.assertEqual(section["parallel_execution"][key], value)
            self.assertEqual(section["resources"][key], value)
        self.assertFalse(
            section["parallel_checkpoint_amendment"][
                "parallel_across_analysis_variants"
            ]
        )

    def test_ordered_parallel_map_is_bounded_and_ordered(self) -> None:
        lock = threading.Lock()
        active = 0
        maximum_active = 0

        def work(value: int) -> int:
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.01)
            with lock:
                active -= 1
            return value * value

        result = ordered_parallel_map(list(range(12)), work, maximum_workers=3)
        self.assertEqual(result, [value * value for value in range(12)])
        self.assertGreaterEqual(maximum_active, 2)
        self.assertLessEqual(maximum_active, 3)

    def test_analysis_variants_remain_ordered_and_separate(self) -> None:
        tasks = [
            {"task_identity": {"analysis_id": name, "fold_id": f"fold_{index}"}}
            for index, name in enumerate(["a", "a", "b", "b", "a"])
        ]
        groups = _group_in_frozen_order(
            tasks, lambda task: task["task_identity"]["analysis_id"]
        )
        self.assertEqual(
            [[task["task_identity"]["analysis_id"] for task in group] for group in groups],
            [["a", "a", "a"], ["b", "b"]],
        )

    def test_checkpoint_routes_use_exact_frozen_origins(self) -> None:
        mlp = self.schedule["representatives"]["pytorch_mlp"]
        qnn = self.schedule["representatives"]["qnn"]
        mlp_base = checkpoint_fold_directory(
            mlp, 20260818, "fold_2015", self.config
        )
        qnn_base = checkpoint_fold_directory(
            qnn, 20260818, "fold_2015", self.config
        )
        qnn_confirmation = checkpoint_fold_directory(
            qnn, 20260819, "fold_2015", self.config
        )
        self.assertIn("data/model_runs/classical_mlp_coarse_v1/candidate_results/coarse/pytorch_mlp", str(mlp_base))
        self.assertIn("qnn_q1/qnn/model_stage_v1__qnn_q1__rot_cnot_ring", str(qnn_base))
        self.assertIn("qnn_q2/qnn/model_stage_v1__qnn_q2__t0", str(qnn_confirmation))
        self.assertTrue(str(mlp_base).endswith("seed_20260818/fold_2015"))
        self.assertTrue(str(qnn_base).endswith("seed_20260818/fold_2015"))
        self.assertTrue(str(qnn_confirmation).endswith("seed_20260819/fold_2015"))

    def test_qnn_resource_ledger_remains_exact_under_threads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = QNNResourceLedger(
                Path(directory) / "ledger.json",
                maximum_attempts=20,
                maximum_runtime_seconds=100.0,
            )

            def attempt(value: int) -> int:
                attempt_id = ledger.begin_attempt("TEST")
                self.assertIsNotNone(attempt_id)
                time.sleep(0.005)
                ledger.finish_attempt(
                    int(attempt_id), runtime_seconds=0.25, outcome="COMPLETE"
                )
                return value

            values = ordered_parallel_map(
                list(range(12)), attempt, maximum_workers=4
            )
            self.assertEqual(values, list(range(12)))
            self.assertEqual(ledger.payload["started_attempts"], 12)
            self.assertEqual(ledger.payload["completed_attempts"], 12)
            self.assertEqual(ledger.payload["interrupted_attempts"], 0)
            self.assertEqual(ledger.payload["total_runtime_seconds"], 3.0)
            self.assertFalse(ledger.limit_reached)

    def test_static_authority_and_checkpoint_cardinality(self) -> None:
        authority = verify_amendment_authority(self.config)
        policy = self.config["secondary_development_execution"][
            "interpretation_checkpoint_sources"
        ]
        self.assertEqual(len(authority), 8)
        self.assertEqual(policy["expected_checkpoint_count"], 36)
        self.assertEqual(policy["confirmation_seeds"], [20260819, 20260820])

    def test_synthetic_smoke_remains_project_data_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = synthetic_smoke_isolated(DEFAULT_CONFIG, Path(directory))
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["project_data_read"])
        self.assertFalse(result["project_model_fit_performed"])
        self.assertFalse(result["protected_feature_years_opened"])

    def test_all_parallel_pca_routes_and_exact_resume_are_data_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = synthetic_pca_controls_isolated(DEFAULT_CONFIG, output)
            result_paths = sorted((output / "task_results").glob("*.json"))
            first_hashes = {
                path.name: base.file_sha256(path) for path in result_paths
            }
            second = synthetic_pca_controls_isolated(DEFAULT_CONFIG, output)
            second_hashes = {
                path.name: base.file_sha256(path) for path in result_paths
            }
        self.assertEqual(first["status"], "COMPLETE")
        self.assertEqual(first["planned_tasks"], 12)
        self.assertEqual(first["complete_tasks"], 12)
        self.assertEqual(second["status"], "COMPLETE")
        self.assertEqual(first_hashes, second_hashes)
        self.assertEqual(len(first_hashes), 12)

    def test_all_84_parallel_fold_fit_routes_are_data_free(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            phases = synthetic_model_fit_phases_isolated(DEFAULT_CONFIG, output)
            results = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((output / "task_results").glob("*.json"))
            ]
        self.assertEqual(phases["pca"]["complete_tasks"], 12)
        self.assertEqual(phases["classical"]["complete_tasks"], 48)
        self.assertEqual(phases["qnn"]["complete_tasks"], 24)
        self.assertEqual(len(results), 84)
        self.assertTrue(all(result["status"] == "COMPLETE" for result in results))
        self.assertTrue(all(not result["protected_feature_years_opened"] for result in results))

    def test_interpretability_orchestration_is_ordered_and_bounded(self) -> None:
        lock = threading.Lock()
        active: dict[str, int] = {}
        maximum: dict[str, int] = {}

        def fake_fold(**kwargs: object) -> dict[str, object]:
            plan_task = kwargs["plan_task"]
            family = str(plan_task["task_identity"]["family"])
            fold_id = str(kwargs["fold_id"])
            with lock:
                active[family] = active.get(family, 0) + 1
                maximum[family] = max(maximum.get(family, 0), active[family])
            time.sleep(0.01)
            with lock:
                active[family] -= 1
            return {"status": "COMPLETE", "fold_id": fold_id}

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with _isolated_activation():
                with patch.object(base, "_run_interpretation_fold", side_effect=fake_fold):
                    result = base.execute_interpretability(
                        DEFAULT_CONFIG, output, synthetic=True
                    )
            task_results = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((output / "task_results").glob("*.json"))
            ]
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["complete_tasks"], 12)
        self.assertEqual(len(task_results), 12)
        expected_folds = [f"fold_{year}" for year in range(2015, 2021)]
        for task_result in task_results:
            self.assertEqual(
                [fold["fold_id"] for fold in task_result["fold_results"]],
                expected_folds,
            )
        self.assertLessEqual(maximum["pytorch_mlp"], 2)
        self.assertLessEqual(maximum["qnn"], 4)
        for family in maximum:
            if family not in {"pytorch_mlp", "qnn"}:
                self.assertLessEqual(maximum[family], 4)

    def test_launcher_is_single_import_and_committed_gated(self) -> None:
        source = (ROOT / "scripts/run_secondary_analyses_v1_1_4.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -c", source)
        self.assertIn(
            "verify_secondary_analysis_execution_v1_1_4(require_committed=True)",
            source,
        )
        self.assertNotIn(
            "python -m src.modeling.secondary_analysis_execution_v1_1_4", source
        )


if __name__ == "__main__":
    unittest.main()

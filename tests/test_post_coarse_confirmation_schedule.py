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
    require_historical_qnn_reuse,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    ROOT / "configs/post_coarse_experiment_v1_0_3_confirmation_parallel.yaml"
)
SOURCE_QNN_MANIFEST = (
    ROOT / "data/model_runs/post_coarse_v1_3_0/qnn_phase_manifest.json"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ConfirmationScheduleIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_post_coarse_config(CONFIG_PATH)
        cls.section = cls.config["post_coarse_execution"]

    def test_schedule_amendment_changes_execution_only(self) -> None:
        self.assertEqual(self.section["version"], "1.0.3")
        schedule = self.section["confirmation_schedule_amendment"]
        self.assertTrue(schedule["classical_and_qnn_confirmation_split"])
        self.assertTrue(
            schedule["classical_confirmation_must_complete_before_qnn_confirmation"]
        )
        self.assertEqual(
            schedule["maximum_parallel_qnn_confirmation_candidates"], 3
        )
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
            "configs/post_coarse_experiment_v1_0_3_confirmation_parallel.yaml",
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

    def test_parallel_qnn_confirmation_is_bounded_and_ordered(self) -> None:
        class FakeExecutor:
            def request_shutdown(self) -> None:
                raise AssertionError("shutdown should not be requested")

        class FakeRunner:
            contract = {"execution_failure_state_machine": {"required_folds": []}}
            executor = FakeExecutor()

            @staticmethod
            def _candidate_parameters(
                stage: str, family: str, configuration_id: str
            ) -> dict[str, object]:
                return {
                    "configuration_id": configuration_id,
                    "qubits_pca": 4,
                }

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
                    },
                )
            )

        lock = threading.Lock()
        active = 0
        maximum_active = 0

        def fake_confirm(**kwargs: object):
            nonlocal active, maximum_active
            base = kwargs["base"]
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.02 * (4 - int(base.row["configuration_id"][-1])))
            with lock:
                active -= 1
            return base, []

        with patch(
            "src.modeling.post_coarse_runner._confirm_candidate",
            side_effect=fake_confirm,
        ) as mocked:
            results = _confirm_qnn_candidates_parallel(
                runner=FakeRunner(),
                folds={},
                jobs=jobs,
                confirmation_seeds=[20260819, 20260820],
                maximum_workers=3,
            )

        self.assertEqual(maximum_active, 3)
        self.assertEqual(
            [result.row["configuration_id"] for result, _ in results],
            ["qnn-1", "qnn-2", "qnn-3"],
        )
        self.assertEqual(mocked.call_count, 3)
        for call in mocked.call_args_list:
            self.assertEqual(call.kwargs["confirmation_seeds"], [20260819, 20260820])
            self.assertEqual(call.kwargs["selected_ansatz_id"], "ROT_CNOT_RING")

    def test_parallel_qnn_confirmation_rejects_more_than_three_workers(self) -> None:
        with self.assertRaises(PostCoarseIntegrityError):
            _confirm_qnn_candidates_parallel(
                runner=object(),
                folds={},
                jobs=[(object(), {})],
                confirmation_seeds=[20260819, 20260820],
                maximum_workers=4,
            )


if __name__ == "__main__":
    unittest.main()

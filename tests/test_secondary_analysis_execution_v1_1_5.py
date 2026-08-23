"""Static and synthetic tests for v1.1.5 permutation remediation."""

from __future__ import annotations

from pathlib import Path
import unittest

import numpy as np

from src.modeling import secondary_analysis_execution as base
from src.modeling import secondary_analysis_execution_worker as v110_worker
from src.modeling.secondary_analysis_execution_v1_1_4 import (
    DEFAULT_CONFIG as V114_CONFIG,
    load_execution_config as load_v114_config,
)
from src.modeling.secondary_analysis_execution_v1_1_5 import (
    DEFAULT_CONFIG,
    WORKER_MODULE,
    load_execution_config,
    verify_amendment_authority,
)
from src.modeling.secondary_analysis_execution_worker_v1_1_5 import (
    POLICY_ID,
    canonical_economic_group_indices,
    grouped_permutation,
)


ROOT = Path(__file__).resolve().parents[1]


def _arrays(*, repeated: bool = True, conflicting: bool = False) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(20260818)
    x_train = rng.normal(size=(80, 4))
    x_validation = rng.normal(size=(24, 4))
    y_train = (x_train[:, 0] - 0.5 * x_train[:, 2] > 0).astype(np.int64)
    y_validation = (x_validation[:, 0] - 0.5 * x_validation[:, 2] > 0).astype(np.int64)
    clusters = np.arange(len(y_validation), dtype=np.int64)
    if repeated:
        clusters[1] = clusters[0]
        y_validation[1] = 1 - y_validation[0] if conflicting else y_validation[0]
    return {
        "x_train_base": x_train,
        "x_validation_base": x_validation,
        "y_train": y_train,
        "y_validation": y_validation,
        "sample_weight": np.ones(len(y_train), dtype=np.float64),
        "cluster_codes": clusters,
    }


def _task() -> dict[str, object]:
    return {
        "family": "fixed_l2_logistic",
        "parameters": {"C": 1.0, "imbalance": "none"},
        "source_stage": "coarse",
        "seeds": [20260818],
        "feature_groups": [[0, 2], [1, 3]],
        "feature_names": ["feature_a", "feature_b"],
        "repetitions": 4,
        "permutation_seed": 20260818,
        "economic_group_duplicate_policy": POLICY_ID,
    }


class SecondaryExecutionEconomicGroupPermutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_execution_config(DEFAULT_CONFIG)
        cls.schedule, cls.tasks = base.frozen_schedule(cls.config)

    def test_only_interpretation_method_is_amended(self) -> None:
        amendment = self.config["secondary_development_execution"][
            "economic_group_permutation_amendment"
        ]
        self.assertTrue(amendment["interpretation_method_changed"])
        self.assertTrue(amendment["methodology_changed"])
        for field in (
            "target_values_changed",
            "sample_membership_changed",
            "fold_policy_changed",
            "task_roster_changed",
            "task_identity_changed",
            "model_parameters_changed",
            "robustness_method_changed",
        ):
            self.assertFalse(amendment[field])

    def test_roster_and_task_identities_remain_exact(self) -> None:
        inherited_schedule, inherited_tasks = base.frozen_schedule(
            load_v114_config(V114_CONFIG)
        )
        self.assertEqual(len(self.tasks), 96)
        self.assertEqual(self.schedule["counts"], inherited_schedule["counts"])
        self.assertEqual(
            [task["task_identity_sha256"] for task in self.tasks],
            [task["task_identity_sha256"] for task in inherited_tasks],
        )

    def test_canonical_indices_use_first_frozen_occurrence(self) -> None:
        indices = canonical_economic_group_indices(
            np.asarray([7, 3, 7, 9, 3]), np.asarray([1, 0, 1, 1, 0])
        )
        np.testing.assert_array_equal(indices, np.asarray([0, 1, 3]))

    def test_conflicting_within_group_label_fails_closed(self) -> None:
        arrays = _arrays(conflicting=True)
        with self.assertRaisesRegex(ValueError, "Target label differs"):
            canonical_economic_group_indices(
                arrays["cluster_codes"], arrays["y_validation"]
            )

    def test_repeated_groups_complete_deterministically(self) -> None:
        arrays = _arrays()
        first = grouped_permutation(_task(), arrays)
        second = grouped_permutation(_task(), arrays)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "COMPLETE")
        self.assertEqual(first["validation_rows_original"], 24)
        self.assertEqual(first["validation_rows"], 23)
        self.assertEqual(first["validation_economic_groups"], 23)
        self.assertEqual(first["duplicate_rows_dropped"], 1)
        self.assertEqual(first["economic_group_duplicate_policy"], POLICY_ID)

    def test_unique_group_numerics_match_inherited_worker(self) -> None:
        arrays = _arrays(repeated=False)
        amended = grouped_permutation(_task(), arrays)
        inherited = v110_worker.grouped_permutation(_task(), arrays)
        self.assertEqual(amended["baseline_pr_auc"], inherited["baseline_pr_auc"])
        self.assertEqual(amended["feature_results"], inherited["feature_results"])

    def test_unknown_duplicate_policy_fails_closed(self) -> None:
        task = _task()
        task["economic_group_duplicate_policy"] = "unknown"
        with self.assertRaisesRegex(ValueError, "Unknown economic-group"):
            grouped_permutation(task, _arrays())

    def test_static_authority_and_frozen_duplicate_audit(self) -> None:
        authority = verify_amendment_authority(self.config)
        amendment = self.config["secondary_development_execution"][
            "economic_group_permutation_amendment"
        ]
        self.assertEqual(len(authority), 6)
        self.assertEqual(amendment["observed_total_excess_rows"], 5)
        self.assertEqual(
            amendment["observed_excess_rows_by_fold"],
            {
                "fold_2015": 2,
                "fold_2016": 2,
                "fold_2017": 0,
                "fold_2018": 0,
                "fold_2019": 1,
                "fold_2020": 0,
            },
        )

    def test_controller_routes_only_to_amended_worker(self) -> None:
        source = (
            ROOT / "src/modeling/secondary_analysis_execution_v1_1_5.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            WORKER_MODULE, "src.modeling.secondary_analysis_execution_worker_v1_1_5"
        )
        self.assertIn('"-m", WORKER_MODULE', source)

    def test_launcher_is_single_import_and_committed_gated(self) -> None:
        source = (ROOT / "scripts/run_secondary_analyses_v1_1_5.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -c", source)
        self.assertIn(
            "verify_secondary_analysis_execution_v1_1_5(require_committed=True)",
            source,
        )
        self.assertNotIn(
            "python -m src.modeling.secondary_analysis_execution_v1_1_5", source
        )


if __name__ == "__main__":
    unittest.main()

"""Static and numeric tests for v1.1.6 TreeSHAP repair."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import numpy as np

from src.modeling import secondary_analysis_execution as base
from src.modeling import secondary_analysis_execution_v1_1_5 as v115
from src.modeling.secondary_analysis_execution_v1_1_5 import (
    DEFAULT_CONFIG as V115_CONFIG,
    load_execution_config as load_v115_config,
)
from src.modeling.secondary_analysis_execution_v1_1_6 import (
    DEFAULT_CONFIG,
    TREE_SHAP_TASK_SHA256,
    WORKER_MODULE,
    _hardlink_file,
    _isolated_activation,
    load_execution_config,
    verify_amendment_authority,
)
from src.modeling.secondary_analysis_execution_worker_v1_1_6 import (
    TREE_SHAP_POLICY_ID,
    detailed_tree_shap,
)


ROOT = Path(__file__).resolve().parents[1]


def _arrays() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(20260818)
    x_train = rng.normal(size=(96, 4))
    x_validation = rng.normal(size=(32, 4))
    y_train = (x_train[:, 0] - 0.5 * x_train[:, 2] > 0).astype(np.int64)
    y_validation = (
        x_validation[:, 0] - 0.5 * x_validation[:, 2] > 0
    ).astype(np.int64)
    return {
        "x_train_base": x_train,
        "x_validation_base": x_validation,
        "y_train": y_train,
        "y_validation": y_validation,
        "sample_weight": np.ones(len(y_train), dtype=np.float64),
        "cluster_codes": np.arange(len(y_validation), dtype=np.int64),
    }


def _task() -> dict[str, object]:
    return {
        "action": "detailed_tree_shap",
        "family": "xgboost",
        "parameters": {
            "n_estimators": 12,
            "max_depth": 2,
            "learning_rate": 0.05,
            "min_child_weight": 1,
            "gamma": 0.0,
            "subsample": 1.0,
            "colsample_bytree": 1.0,
            "reg_alpha": 0.0,
            "reg_lambda": 1.0,
            "imbalance": "none",
        },
        "source_stage": "coarse",
        "seeds": [20260818, 20260819, 20260820],
        "model_feature_names": ["a", "b", "c", "d"],
        "background_rows_max": 512,
        "oof_rows_max": 500,
    }


def _run_pinned_worker() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        arrays_path = root / "arrays.npz"
        result_path = root / "result.json"
        task_path = root / "task.json"
        np.savez(arrays_path, **_arrays())
        task = _task()
        payload = {
            "worker_mode": "interpretation",
            "interpretation_task": task,
            "interpretation_task_sha256": base.canonical_sha256(task),
            "arrays_path": str(arrays_path),
            "result_path": str(result_path),
        }
        task_path.write_text(json.dumps(payload), encoding="utf-8")
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONPATH": str(ROOT),
                "MPLCONFIGDIR": str(root / "matplotlib"),
                "XDG_CACHE_HOME": str(root / "cache"),
            }
        )
        completed = subprocess.run(
            [
                str(ROOT / ".venv-classical/bin/python"),
                "-m",
                WORKER_MODULE,
                "--task",
                str(task_path),
            ],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if completed.returncode != 0 or not result_path.is_file():
            raise AssertionError(completed.stderr or completed.stdout)
        return json.loads(result_path.read_text(encoding="utf-8"))


class SecondaryExecutionTreeShapCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_execution_config(DEFAULT_CONFIG)
        cls.schedule, cls.tasks = base.frozen_schedule(cls.config)

    def test_amendment_is_operational_only(self) -> None:
        amendment = self.config["secondary_development_execution"][
            "treeshap_compatibility_amendment"
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

    def test_roster_and_task_identities_remain_exact(self) -> None:
        inherited_schedule, inherited_tasks = base.frozen_schedule(
            load_v115_config(V115_CONFIG)
        )
        self.assertEqual(len(self.tasks), 96)
        self.assertEqual(self.schedule["counts"], inherited_schedule["counts"])
        self.assertEqual(
            [task["task_identity_sha256"] for task in self.tasks],
            [task["task_identity_sha256"] for task in inherited_tasks],
        )

    def test_failed_source_task_is_exact_frozen_treeshap_task(self) -> None:
        task = next(
            item
            for item in self.tasks
            if item["task_identity_sha256"] == TREE_SHAP_TASK_SHA256
        )
        identity = task["task_identity"]
        self.assertEqual(identity["family"], "xgboost")
        self.assertEqual(identity["representative_role"], "tree_boosting")
        self.assertEqual(
            identity["analysis_id"],
            "interventional_TreeSHAP_seed_20260818_models",
        )

    def test_tree_shap_numeric_compatibility_is_complete(self) -> None:
        result = _run_pinned_worker()
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["tree_shap_policy"], TREE_SHAP_POLICY_ID)
        self.assertEqual(result["feature_perturbation"], "interventional")
        self.assertEqual(result["model_output"], "raw")
        self.assertEqual(result["background_rows"], 96)
        self.assertEqual(result["evaluation_rows"], 32)
        self.assertFalse(result["background_subsampled"])
        self.assertEqual(len(result["mean_abs_shap_by_seed"]), 3)
        self.assertEqual(len(result["mean_abs_shap"]), 4)
        self.assertTrue(np.isfinite(result["mean_abs_shap"]).all())

    def test_tree_shap_preserves_booster_and_raw_scores(self) -> None:
        result = _run_pinned_worker()
        for audit in result["seed_audits"]:
            self.assertTrue(audit["booster_unchanged"])
            self.assertTrue(audit["raw_scores_unchanged"])
            self.assertLessEqual(audit["additivity_max_abs"], 1e-4)
            self.assertEqual(len(audit["booster_sha256"]), 64)
            self.assertEqual(len(audit["raw_score_sha256"]), 64)

    def test_wrong_tree_shap_limits_fail_closed(self) -> None:
        task = _task()
        task["background_rows_max"] = 100
        with self.assertRaisesRegex(ValueError, "background limit changed"):
            detailed_tree_shap(task, _arrays())

    def test_hardlink_carry_forward_is_exact_and_storage_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.bin"
            source.write_bytes(b"exact carry-forward\n")
            target_root = root / "target"
            target = target_root / "artifact/source.bin"
            entry = _hardlink_file(source, target, target_root)
            self.assertEqual(source.read_bytes(), target.read_bytes())
            self.assertEqual(source.stat().st_ino, target.stat().st_ino)
            self.assertEqual(entry["path"], "artifact/source.bin")
            self.assertEqual(entry["bytes"], len(b"exact carry-forward\n"))

    def test_static_authority_and_carry_policy(self) -> None:
        authority = verify_amendment_authority(self.config)
        carry = self.config["secondary_development_execution"]["carry_forward"]
        self.assertEqual(len(authority), 6)
        self.assertEqual(carry["required_complete_pca_tasks"], 12)
        self.assertEqual(carry["required_complete_interpretation_tasks"], 11)
        self.assertEqual(carry["required_failed_interpretation_tasks"], 1)
        self.assertEqual(
            carry["excluded_failed_task_identity_sha256"], TREE_SHAP_TASK_SHA256
        )

    def test_activation_routes_to_v116_worker_and_restores_prior(self) -> None:
        prior = v115.WORKER_MODULE
        with _isolated_activation():
            self.assertEqual(v115.WORKER_MODULE, WORKER_MODULE)
        self.assertEqual(v115.WORKER_MODULE, prior)

    def test_launcher_is_single_import_and_committed_gated(self) -> None:
        source = (ROOT / "scripts/run_secondary_analyses_v1_1_6.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -c", source)
        self.assertIn(
            "verify_secondary_analysis_execution_v1_1_6(require_committed=True)",
            source,
        )
        self.assertIn("repair-treeshap", source)
        self.assertNotIn(
            "python -m src.modeling.secondary_analysis_execution_v1_1_6", source
        )


if __name__ == "__main__":
    unittest.main()

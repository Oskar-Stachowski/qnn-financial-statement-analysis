"""Tests for the v1.1.7 report-integrity amendment."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.modeling import secondary_analysis_execution as base
from src.modeling.secondary_analysis_execution_v1_1_6 import (
    DEFAULT_CONFIG as V116_CONFIG,
    load_execution_config as load_v116_config,
)
from src.modeling.secondary_analysis_execution_v1_1_7 import (
    DEFAULT_CONFIG,
    _atomic_json_sha256,
    _legacy_pre_amendment_report,
    _write_report_artifacts,
    load_execution_config,
    verify_amendment_authority,
)


ROOT = Path(__file__).resolve().parents[1]


class SecondaryExecutionReportIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_execution_config(DEFAULT_CONFIG)
        cls.schedule, cls.tasks = base.frozen_schedule(cls.config)

    def test_amendment_is_report_only(self) -> None:
        amendment = self.config["secondary_development_execution"][
            "report_integrity_amendment"
        ]
        for field in (
            "source_output_mutated",
            "source_results_copied",
            "source_results_changed",
            "target_values_changed",
            "sample_membership_changed",
            "fold_policy_changed",
            "task_roster_changed",
            "task_identity_changed",
            "model_parameters_changed",
            "interpretation_method_changed",
            "robustness_method_changed",
            "methodology_changed",
            "project_data_read",
            "project_model_fit_performed",
            "protected_feature_years_opened",
        ):
            self.assertFalse(amendment[field])

    def test_roster_and_task_identities_remain_exact(self) -> None:
        inherited_schedule, inherited_tasks = base.frozen_schedule(
            load_v116_config(V116_CONFIG)
        )
        self.assertEqual(len(self.tasks), 96)
        self.assertEqual(self.schedule["counts"], inherited_schedule["counts"])
        self.assertEqual(
            [task["task_identity_sha256"] for task in self.tasks],
            [task["task_identity_sha256"] for task in inherited_tasks],
        )

    def test_source_defect_is_exactly_pinned(self) -> None:
        source = self.config["secondary_development_execution"]["report_source"]
        self.assertEqual(source["expected_tasks"], 96)
        self.assertEqual(source["expected_complete_tasks"], 96)
        self.assertEqual(len(source["phase_manifest_sha256"]), 4)
        self.assertNotEqual(
            source["report_actual_sha256"],
            source["report_recorded_stale_sha256"],
        )

    def test_legacy_report_reconstruction_removes_amendment_metadata(self) -> None:
        report = {
            "schema_version": 1,
            "id": "secondary_development_results_v1_1_6",
            "status": "COMPLETE",
            "terminal_tasks": 96,
            "parallel_checkpoint_amendment": "1.1.4",
            "economic_group_permutation_amendment": "1.1.5",
            "treeshap_compatibility_amendment": "1.1.6",
        }
        expected = {
            "schema_version": 1,
            "id": "secondary_development_results_v1_1_0",
            "status": "COMPLETE",
            "terminal_tasks": 96,
        }
        self.assertEqual(
            _legacy_pre_amendment_report(report),
            expected,
        )
        self.assertEqual(
            _atomic_json_sha256(_legacy_pre_amendment_report(report)),
            _atomic_json_sha256(expected),
        )

    def test_final_report_is_written_before_manifest_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            report = {
                "schema_version": 1,
                "id": "secondary_development_results_v1_1_7",
                "status": "COMPLETE",
            }
            manifest = {
                "schema_version": 1,
                "id": "secondary_development_execution_v1_1_7",
                "status": "COMPLETE",
            }
            final = _write_report_artifacts(output, report, manifest)
            self.assertEqual(
                final["secondary_report_sha256"],
                base.file_sha256(output / "secondary_development_report.json"),
            )
            written = json.loads(
                (output / "run_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(written, final)

    def test_static_authority_is_complete(self) -> None:
        authority = verify_amendment_authority(self.config)
        self.assertEqual(len(authority), 6)

    def test_controller_contains_no_model_execution_route(self) -> None:
        source = (
            ROOT / "src/modeling/secondary_analysis_execution_v1_1_7.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "execute_pca_controls(",
            "execute_interpretability(",
            "execute_classical_robustness(",
            "execute_qnn_robustness(",
        ):
            self.assertNotIn(forbidden, source)

    def test_launcher_is_single_import_and_committed_gated(self) -> None:
        source = (ROOT / "scripts/run_secondary_analyses_v1_1_7.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("python -c", source)
        self.assertIn(
            "verify_secondary_analysis_execution_v1_1_7(require_committed=True)",
            source,
        )
        self.assertIn("verify-report", source)


if __name__ == "__main__":
    unittest.main()

"""Config-only boundary checks for completed readiness audit v1.0.5."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "configs/thesis_readiness_audit_v1_0_5_result.yaml"
REPORT_PATH = ROOT / "docs/14_thesis_readiness_audit_v1_0_5.md"
STATUS_PATH = ROOT / "docs/10_current_experiment_status.md"
EXPECTED_ALLOWLIST_SHA256 = (
    "b6c79a296e88dab37ccd049f97b8e69516247c9e63486b8bf2256c4ef6019359"
)
EXPECTED_REVIEW_SHA256 = (
    "7767eb335fe9f42adbb40c01259dbab3034bec1a793b0fa92bd2d8d6758d4152"
)


class ThesisReadinessAuditBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = yaml.safe_load(RESULT_PATH.read_text(encoding="utf-8"))
        cls.control = cls.payload["thesis_readiness_audit_result"]

    def test_completed_audit_has_fail_verdict(self) -> None:
        self.assertEqual(self.control["status"], "AUDIT_COMPLETE")
        self.assertEqual(self.control["readiness_verdict"], "BASELINE_AUDIT_FAIL")
        decision = self.payload["decision"]
        self.assertFalse(decision["baseline_audit_pass_asserted"])
        self.assertTrue(decision["baseline_audit_fail_asserted"])
        self.assertTrue(decision["step_6_completed"])
        self.assertFalse(decision["subsequent_runbook_steps_authorized"])

    def test_authorization_is_pinned_to_committed_pass(self) -> None:
        allowlist = self.payload["authorization"]["allowlist"]
        self.assertEqual(allowlist["sha256"], EXPECTED_ALLOWLIST_SHA256)
        self.assertTrue(allowlist["sha256_verified_before_audit"])
        self.assertFalse(allowlist["modified_during_audit"])
        review = self.payload["authorization"]["review"]
        self.assertEqual(review["sha256"], EXPECTED_REVIEW_SHA256)
        self.assertEqual(review["verdict"], "ALLOWLIST_REVIEW_PASS")
        self.assertEqual(review["unresolved_review_findings"], 0)

    def test_all_eight_readiness_checks_are_evaluated(self) -> None:
        checks = self.payload["readiness_checks"]
        self.assertEqual(len(checks), 8)
        for name, result in checks.items():
            self.assertIsInstance(result, dict, name)
            self.assertNotIn(result["status"], {"NOT_EVALUATED", "PARTIAL_NO_VERDICT"})
            self.assertTrue(result["summary"], name)

    def test_fail_is_supported_by_nonempty_blockers(self) -> None:
        findings = self.payload["findings"]
        blockers = findings["blocker"]
        self.assertEqual(len(blockers), self.payload["decision"]["blocker_count"])
        self.assertEqual(
            {item["id"] for item in blockers},
            {
                "BLOCKER-001",
                "BLOCKER-002",
                "BLOCKER-003",
                "BLOCKER-004",
                "BLOCKER-005",
            },
        )
        self.assertEqual(len(findings["important"]), 4)
        self.assertEqual(len(findings["optional"]), 2)

    def test_protected_boundary_and_no_fit_are_explicit(self) -> None:
        scope = self.payload["scope_and_exposure"]
        self.assertEqual(scope["protected_feature_years"], [2021, 2022, 2023, 2024])
        for key in (
            "protected_period_content_read",
            "protected_schema_row_count_distribution_sample_or_value_read",
            "unlisted_data_reports_or_notebooks_content_read",
            "model_fit_refit_inference_prediction_or_reporting_performed",
            "network_or_external_storage_accessed",
            "unexpected_protected_or_analytical_content_exposure_incident",
            "incident_declaration_required",
            "predecessor_broad_search_output_used_as_audit_evidence",
        ):
            self.assertFalse(scope[key], key)

    def test_safe_verifiers_pass_without_protected_access(self) -> None:
        verifiers = self.payload["safe_verifiers"]
        self.assertEqual(verifiers["allowlist_structure"]["status"], "PASS")
        self.assertEqual(verifiers["allowlist_structure"]["tests_run"], 15)
        for key in (
            "post_coarse_v1_3_0_results_integrity",
            "secondary_development_v1_1_7_results_integrity",
        ):
            verifier = verifiers[key]
            self.assertEqual(verifier["status"], "PASS")
            self.assertFalse(verifier["protected_feature_years_opened"])

    def test_unsupported_claim_review_is_fail_closed(self) -> None:
        claims = self.payload["unsupported_claims_review"]
        self.assertFalse(claims["independent_test_claim_found_in_current_results"])
        self.assertFalse(claims["fully_unseen_holdout_claim_found_in_current_results"])
        self.assertFalse(claims["quantum_advantage_claim_found_in_current_results"])
        self.assertTrue(claims["generic_or_stale_thesis_language_requires_editorial_alignment"])

    def test_report_and_status_match_machine_verdict(self) -> None:
        report = REPORT_PATH.read_text(encoding="utf-8")
        status = STATUS_PATH.read_text(encoding="utf-8")
        self.assertIn("Werdykt: **BASELINE_AUDIT_FAIL**", report)
        self.assertIn("5 blockerów", report)
        self.assertNotIn("Werdykt: **BASELINE_AUDIT_PASS**", report)
        self.assertIn("BASELINE_AUDIT_FAIL", status)


if __name__ == "__main__":
    unittest.main()

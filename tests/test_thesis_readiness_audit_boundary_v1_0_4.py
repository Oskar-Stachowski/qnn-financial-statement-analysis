"""Config-only boundary checks for the aborted readiness audit v1.0.4."""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "configs/thesis_readiness_audit_v1_0_4_result.yaml"
REPORT_PATH = ROOT / "docs/14_thesis_readiness_audit_v1_0_4.md"
EXPECTED_ALLOWLIST_SHA256 = (
    "183b29d5438e538ebc715c8b795b0822f42d44c40fefb84fe30a7b4ac654f1c5"
)


class ThesisReadinessAuditBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = yaml.safe_load(RESULT_PATH.read_text(encoding="utf-8"))
        cls.control = cls.payload["thesis_readiness_audit_result"]

    def test_abort_is_fail_closed_without_readiness_verdict(self) -> None:
        self.assertEqual(
            self.control["status"], "AUDIT_ABORTED_NO_READINESS_VERDICT"
        )
        self.assertIsNone(self.control["readiness_verdict"])
        decision = self.payload["decision"]
        self.assertFalse(decision["baseline_audit_pass_asserted"])
        self.assertFalse(decision["baseline_audit_fail_asserted"])
        self.assertFalse(decision["step_6_completed"])
        self.assertFalse(decision["subsequent_runbook_steps_authorized"])

    def test_reviewed_allowlist_is_pinned(self) -> None:
        allowlist = self.payload["authorization"]["allowlist"]
        self.assertEqual(allowlist["sha256"], EXPECTED_ALLOWLIST_SHA256)
        self.assertTrue(allowlist["sha256_verified_before_audit_content_access"])
        self.assertFalse(allowlist["modified_during_audit"])
        review = self.payload["authorization"]["review"]
        self.assertEqual(review["verdict"], "ALLOWLIST_REVIEW_PASS")
        self.assertEqual(review["unresolved_review_findings"], 0)

    def test_nonconformance_is_non_analytical(self) -> None:
        event = self.payload["process_nonconformance"]
        self.assertEqual(event["classification"], "non_analytical_process_nonconformance")
        self.assertFalse(event["protected_or_analytical_content_exposed"])
        self.assertTrue(event["current_operation_stopped"])
        self.assertFalse(event["scope_expansion_performed_after_detection"])

    def test_protected_boundary_remained_closed(self) -> None:
        exposure = self.payload["scope_and_exposure"]
        self.assertFalse(exposure["protected_period_content_read"])
        self.assertFalse(
            exposure["protected_schema_row_count_distribution_sample_or_value_read"]
        )
        self.assertFalse(exposure["unexpected_protected_or_analytical_content_exposure_incident"])
        self.assertFalse(exposure["incident_declaration_required"])

    def test_partial_checks_do_not_become_findings(self) -> None:
        self.assertEqual(len(self.payload["readiness_checks"]), 8)
        findings = self.payload["findings"]
        self.assertEqual(findings["blocker"], [])
        self.assertEqual(findings["important"], [])
        self.assertEqual(findings["optional"], [])
        self.assertTrue(
            findings["finding_lists_withheld_because_fatal_process_route_forbids_readiness_verdict"]
        )

    def test_report_never_claims_baseline_verdict(self) -> None:
        report = REPORT_PATH.read_text(encoding="utf-8")
        self.assertIn("AUDIT_ABORTED_NO_READINESS_VERDICT", report)
        self.assertIn("Krok 6", report)
        self.assertNotIn("Werdykt: **BASELINE_AUDIT_PASS**", report)
        self.assertNotIn("Werdykt: **BASELINE_AUDIT_FAIL**", report)


if __name__ == "__main__":
    unittest.main()

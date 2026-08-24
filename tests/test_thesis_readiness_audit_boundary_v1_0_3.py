"""Config-only boundary checks for the aborted readiness audit v1.0.3.

This file is an audit output. The v1.0.3 allowlist did not pre-authorize its
execution as a safe verifier, so the aborting audit session must not run it.
"""

from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
RESULT_PATH = ROOT / "configs/thesis_readiness_audit_v1_0_3_result.yaml"
REPORT_PATH = ROOT / "docs/14_thesis_readiness_audit_v1_0_3.md"
EXPECTED_ALLOWLIST_SHA256 = (
    "d05e8e647c2d6b4207b4272255fb2d2d50b89d9892145478332589b4ac09238f"
)
EXPECTED_SUBJECT_COMMIT = "2a08d0935e7bb49c33b1df0a0da9470d6d0748ae"


def load_result() -> dict:
    with RESULT_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise AssertionError("Audit result must be a YAML mapping")
    return payload


class ThesisReadinessAuditBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_result()
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
        self.assertTrue(decision["retry_requires_new_fresh_context"])

    def test_reviewed_allowlist_identity_is_pinned(self) -> None:
        allowlist = self.payload["authorization"]["allowlist"]
        self.assertEqual(allowlist["sha256"], EXPECTED_ALLOWLIST_SHA256)
        self.assertEqual(allowlist["subject_git_commit"], EXPECTED_SUBJECT_COMMIT)
        self.assertTrue(allowlist["sha256_verified_before_audit_content_access"])
        self.assertFalse(allowlist["modified_in_this_session"])
        review = self.payload["authorization"]["review"]
        self.assertEqual(review["verdict"], "ALLOWLIST_REVIEW_PASS")
        self.assertTrue(review["allowlist_gate_authorizes_step_6"])
        self.assertEqual(review["unresolved_review_findings"], 0)

    def test_nonconformance_route_matches_output_cap_trigger(self) -> None:
        event = self.payload["process_nonconformance"]
        self.assertEqual(
            event["classification"], "non_analytical_process_nonconformance"
        )
        self.assertEqual(event["trigger"], "output_cap_exceeded_without_content_exposure")
        self.assertGreater(
            event["requested_allowlist_lines_in_command"],
            event["configured_maximum_rendered_lines_per_command"],
        )
        self.assertTrue(event["current_operation_stopped"])
        self.assertFalse(event["scope_expansion_performed"])

    def test_no_analytical_or_protected_exposure_is_claimed(self) -> None:
        exposure = self.payload["scope_and_exposure"]
        for key, value in exposure.items():
            self.assertFalse(value, key)

    def test_all_substantive_checks_remain_not_evaluated(self) -> None:
        checks = self.payload["readiness_checks"]
        self.assertEqual(len(checks), 8)
        self.assertEqual(set(checks.values()), {"NOT_EVALUATED"})
        findings = self.payload["findings"]
        self.assertEqual(findings["blocker"], [])
        self.assertEqual(findings["important"], [])
        self.assertEqual(findings["optional"], [])
        self.assertTrue(findings["finding_lists_are_empty_because_audit_was_not_performed"])

    def test_report_states_abort_and_never_claims_baseline_verdict(self) -> None:
        report = REPORT_PATH.read_text(encoding="utf-8")
        self.assertIn("AUDIT_ABORTED_NO_READINESS_VERDICT", report)
        self.assertIn("Krok 6 pozostaje nieukończony", report)
        self.assertIn("NOT_EVALUATED", report)
        self.assertNotIn("Werdykt: **BASELINE_AUDIT_PASS**", report)
        self.assertNotIn("Werdykt: **BASELINE_AUDIT_FAIL**", report)


if __name__ == "__main__":
    unittest.main()

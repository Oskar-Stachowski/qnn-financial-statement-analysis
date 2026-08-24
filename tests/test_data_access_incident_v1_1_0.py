from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "configs/data_access_policy_v1_1_0.yaml"
PRIOR_INCIDENT_PATH = ROOT / "configs/data_access_incident_v1_0_0.yaml"
INCIDENT_PATH = ROOT / "configs/data_access_incident_v1_1_0.yaml"
ALLOWLIST_PATH = ROOT / "configs/data_access_incident_v1_1_0_review_allowlist.yaml"
INCIDENT_DOC_PATH = ROOT / "docs/09_3_data_access_incident_v1_1_0.md"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise AssertionError(f"Expected mapping in {path}")
    return payload


class DataAccessIncidentV110Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = load_yaml(POLICY_PATH)
        cls.prior = load_yaml(PRIOR_INCIDENT_PATH)
        cls.incident = load_yaml(INCIDENT_PATH)
        cls.allowlist = load_yaml(ALLOWLIST_PATH)

    def test_successor_is_open_contained_and_does_not_self_close(self) -> None:
        incident = self.incident["data_access_incident"]
        resolution = self.incident["resolution_state"]
        review = self.incident["independent_review_control"]
        self.assertEqual(incident["version"], "1.1.0")
        self.assertEqual(
            incident["status"],
            "open_contained_requires_fresh_independent_review",
        )
        self.assertTrue(resolution["containment_complete"])
        self.assertFalse(resolution["independent_review_complete"])
        self.assertFalse(resolution["incident_resolved"])
        self.assertFalse(resolution["thesis_readiness_audit_may_resume"])
        self.assertFalse(review["current_exposed_context_may_self_close_incident"])

    def test_policy_stop_rule_is_carried_forward(self) -> None:
        expected = self.policy["forward_access_lock"]["accidental_access_policy"]
        actual = self.incident["data_access_incident"]["controlling_policy"][
            "accidental_access_policy"
        ]
        self.assertEqual(actual, expected)
        self.assertEqual(
            expected,
            "stop_record_scope_do_not_continue_and_issue_new_versioned_incident_declaration",
        )

    def test_prior_incident_is_preserved_and_not_resolved(self) -> None:
        prior = self.prior["data_access_incident"]
        successor = self.incident["data_access_incident"]
        self.assertEqual(prior["version"], "1.0.0")
        self.assertEqual(successor["prior_declaration"]["version"], "1.0.0")
        self.assertTrue(successor["prior_declaration"]["remains_historical_and_unresolved"])
        self.assertFalse(
            self.incident["change_control"]["this_declaration_resolves_prior_incident_v1_0_0"]
        )

    def test_review_allowlist_uses_only_exact_non_analytical_files(self) -> None:
        control = self.allowlist["incident_review_allowlist"]
        review = self.allowlist["review_requirements"]
        self.assertTrue(review["fresh_context_or_independent_reviewer"])
        self.assertFalse(review["current_exposed_context_may_act_as_reviewer"])

        exact_paths = self.allowlist["exact_content_read_allowlist"]
        self.assertTrue(exact_paths)
        forbidden = tuple(f"{root}/" for root in self.allowlist["explicitly_forbidden_content_roots"])
        for relative in exact_paths:
            self.assertFalse(relative.startswith(forbidden), relative)
            self.assertTrue((ROOT / relative).is_file(), relative)

        self.assertIn("repository_wide_text_search", self.allowlist["explicitly_forbidden_operations"])
        self.assertIn("data", self.allowlist["explicitly_forbidden_content_roots"])
        self.assertIn("reports", self.allowlist["explicitly_forbidden_content_roots"])

    def test_declaration_does_not_authorize_access_or_training(self) -> None:
        change = self.incident["change_control"]
        self.assertFalse(change["this_declaration_changes_methodology"])
        self.assertFalse(change["this_declaration_authorizes_protected_data_access"])
        self.assertFalse(change["this_declaration_authorizes_model_training"])

        text = INCIDENT_DOC_PATH.read_text(encoding="utf-8")
        self.assertIn("OPEN — CONTAINED — FRESH INDEPENDENT REVIEW REQUIRED", text)
        self.assertIn("No protected values are reproduced here", text)
        self.assertIn("must not resume", text)


if __name__ == "__main__":
    unittest.main()

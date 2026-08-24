"""Structural, synthetic/config-only checks for the readiness-audit allowlist."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / "configs/thesis_readiness_audit_v1_0_0_allowlist.yaml"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FORBIDDEN_PATH_TOKENS = ("*", "?", "[", "]")


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise AssertionError(f"Expected mapping in {path}")
    return payload


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assert_exact_relative_path(test: unittest.TestCase, relative: str) -> None:
    test.assertIsInstance(relative, str)
    test.assertTrue(relative)
    test.assertFalse(relative.startswith("/"), relative)
    test.assertFalse(any(token in relative for token in FORBIDDEN_PATH_TOKENS), relative)
    pure = PurePosixPath(relative)
    test.assertNotIn("..", pure.parts, relative)
    test.assertNotIn(".", pure.parts, relative)


class ThesisReadinessAuditAllowlistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_yaml(ALLOWLIST_PATH)
        cls.control = cls.payload["thesis_readiness_audit_allowlist"]
        cls.boundary = cls.payload["protected_period_boundary"]
        cls.scope = cls.payload["audit_scope"]

    def test_preparation_does_not_self_authorize_review_or_audit(self) -> None:
        self.assertEqual(self.payload["schema_version"], 1)
        self.assertEqual(self.control["version"], "1.0.0")
        self.assertEqual(
            self.control["status"], "PREPARED_AWAITING_INDEPENDENT_REVIEW"
        )
        result = self.control["preparation_result"]
        self.assertFalse(result["analytical_content_read"])
        self.assertFalse(result["readiness_audit_performed"])
        self.assertFalse(result["allowlist_review_performed"])
        self.assertFalse(result["protected_period_access_authorized"])
        self.assertFalse(result["model_fit_refit_or_prediction_performed"])
        entry = self.payload["entry_conditions_for_audit"]
        self.assertEqual(entry["required_allowlist_review_verdict"], "ALLOWLIST_REVIEW_PASS")
        self.assertTrue(entry["audit_requires_new_fresh_context_after_review"])
        self.assertFalse(entry["this_preparation_context_may_execute_audit"])

    def test_authority_files_are_exact_and_hash_pinned(self) -> None:
        pins = self.payload["authority_pins"]
        self.assertGreaterEqual(len(pins), 5)
        seen: set[str] = set()
        for item in pins:
            relative = item["path"]
            assert_exact_relative_path(self, relative)
            self.assertNotIn(relative, seen)
            seen.add(relative)
            expected = item["sha256"]
            self.assertRegex(expected, SHA256_RE)
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(sha256(path), expected, relative)

    def test_every_content_path_is_exact_unique_and_present(self) -> None:
        content = self.scope["exact_content_read_allowlist"]
        all_paths: list[str] = []
        for category, paths in content.items():
            self.assertIsInstance(category, str)
            self.assertIsInstance(paths, list)
            self.assertTrue(paths, category)
            for relative in paths:
                assert_exact_relative_path(self, relative)
                self.assertTrue((ROOT / relative).is_file(), relative)
                all_paths.append(relative)
        self.assertEqual(len(all_paths), len(set(all_paths)))
        self.assertFalse(any(path.startswith("notebooks/") for path in all_paths))
        self.assertFalse(any(path.startswith("data/") for path in all_paths))
        self.assertFalse(any(path.startswith("reports/") for path in all_paths))

    def test_development_exceptions_are_exact_bounded_and_disjoint(self) -> None:
        groups = self.scope["exact_development_only_content_allowlist"]
        allowed_prefixes = (
            "data/model_runs/post_coarse_v1_3_0/",
            "data/model_runs/secondary_development_v1_1_6/",
            "data/model_runs/secondary_development_v1_1_7/",
            "reports/post_coarse_v1_3_0/",
            "reports/secondary_development_v1_1_7/",
            "reports/secondary_development_thesis_v1_0_0/",
        )
        paths: list[str] = []
        for group in groups.values():
            self.assertEqual(group["declared_year_boundary"], list(range(2015, 2021)))
            for relative in group["paths"]:
                assert_exact_relative_path(self, relative)
                self.assertTrue(relative.startswith(allowed_prefixes), relative)
                self.assertTrue((ROOT / relative).is_file(), relative)
                paths.append(relative)
        self.assertEqual(len(paths), len(set(paths)))
        opaque = {
            item["path"]
            for item in self.boundary["exact_existence_or_opaque_sha256_only"]
        }
        self.assertTrue(set(paths).isdisjoint(opaque))

    def test_protected_paths_are_opaque_only_and_default_deny(self) -> None:
        self.assertEqual(self.boundary["protected_feature_years"], [2021, 2022, 2023, 2024])
        self.assertIn("data", self.boundary["default_deny_content_roots"])
        self.assertIn("reports", self.boundary["default_deny_content_roots"])
        self.assertIn("notebooks", self.boundary["default_deny_content_roots"])
        self.assertTrue(self.boundary["notebooks_have_no_exceptions"])
        self.assertTrue(self.boundary["path_not_exactly_allowed_is_denied"])
        self.assertFalse(
            self.boundary["protected_schema_row_count_distribution_or_sample_access_allowed"]
        )
        opaque = self.boundary["exact_existence_or_opaque_sha256_only"]
        self.assertEqual(len(opaque), 2)
        for item in opaque:
            assert_exact_relative_path(self, item["path"])
            self.assertEqual(
                item["permitted_operations"],
                ["file_exists", "opaque_byte_level_sha256"],
            )

    def test_review_scope_is_narrow_non_analytical_and_existing(self) -> None:
        review = self.scope["exact_content_read_allowlist_for_review"]
        self.assertEqual(len(review), len(set(review)))
        executor_paths = {
            path
            for paths in self.scope["exact_content_read_allowlist"].values()
            for path in paths
        }
        self.assertTrue(set(review).issubset(executor_paths))
        self.assertLess(len(review), len(executor_paths))
        forbidden = ("data/", "reports/", "notebooks/", "thesis/")
        for relative in review:
            assert_exact_relative_path(self, relative)
            self.assertFalse(relative.startswith(forbidden), relative)
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_cryptographic_inventory_is_fail_closed(self) -> None:
        inventories = self.scope["cryptographically_pinned_exact_inventories"]
        self.assertEqual(len(inventories), 1)
        inventory = inventories[0]
        assert_exact_relative_path(self, inventory["inventory_path"])
        self.assertRegex(inventory["inventory_sha256"], SHA256_RE)
        self.assertRegex(inventory["files_sha256"], SHA256_RE)
        self.assertEqual(inventory["exact_file_count"], 585)
        self.assertEqual(
            inventory["exact_allowed_roots"],
            [
                "data/model_runs/secondary_development_v1_1_6",
                "data/model_runs/secondary_development_v1_1_7",
            ],
        )
        self.assertTrue(inventory["content_access_requires_inventory_sha256_match_first"])
        self.assertEqual(
            inventory["inventory_mismatch_action"],
            "stop_without_parsing_analytical_files",
        )
        # This is an opaque byte-level check; the test deliberately does not parse the inventory.
        self.assertEqual(
            sha256(ROOT / inventory["inventory_path"]), inventory["inventory_sha256"]
        )

    def test_safe_verifiers_are_exact_non_writing_and_context_limited(self) -> None:
        verifiers = self.payload["safe_verifiers"]
        by_id = {item["id"]: item for item in verifiers}
        self.assertEqual(len(by_id), len(verifiers))
        self.assertEqual(
            set(by_id),
            {
                "thesis_readiness_allowlist_structure",
                "post_coarse_v1_3_0_freeze",
                "secondary_development_v1_1_7_freeze",
            },
        )
        for item in verifiers:
            command = item["command"]
            self.assertIsInstance(command, list)
            self.assertTrue(command)
            self.assertFalse(item["writes_project_files"])
            self.assertFalse(any(token in {";", "&&", "||", "|"} for token in command))
        self.assertEqual(
            by_id["post_coarse_v1_3_0_freeze"]["allowed_contexts"],
            ["audit_executor_after_review_pass"],
        )
        secondary = by_id["secondary_development_v1_1_7_freeze"]
        self.assertEqual(secondary["allowed_contexts"], ["audit_executor_after_review_pass"])
        self.assertIn(
            "inventory_sha256_matches_before_analytical_file_parsing",
            secondary["required_preconditions"],
        )

    def test_forbidden_operations_limits_outputs_and_stop_fail_closed(self) -> None:
        forbidden = set(self.payload["explicitly_forbidden_operations"])
        required_forbidden = {
            "repository_wide_text_search",
            "deserialize_unlisted_analytical_artifact",
            "inspect_protected_schema_row_count_distribution_sample_or_value",
            "execute_training_fit_refit_inference_prediction_reporting_or_production_pipeline",
            "expand_allowlist_during_review_or_audit",
        }
        self.assertTrue(required_forbidden.issubset(forbidden))
        limits = self.payload["output_limits"]
        self.assertLessEqual(limits["max_tool_output_bytes_per_command"], 32768)
        self.assertLessEqual(limits["max_rendered_lines_per_command"], 240)
        self.assertEqual(limits["protected_content_rendered_rows"], 0)
        self.assertFalse(limits["rerun_with_broader_scope_after_cap_allowed"])
        stop = self.payload["stop_policy"]
        self.assertEqual(
            stop["on_allowlist_violation"],
            "invalidate_audit_and_issue_new_versioned_incident_declaration",
        )
        self.assertFalse(stop["incident_record_may_include_values"])
        self.assertFalse(stop["readiness_verdict_after_stop_allowed"])

    def test_audit_writes_only_new_exact_outputs(self) -> None:
        review_outputs = self.scope["exact_write_allowlist_for_review"]
        self.assertEqual(
            review_outputs,
            [
                "configs/thesis_readiness_audit_allowlist_review_v1_0_0.yaml",
                "docs/13_thesis_readiness_audit_allowlist_review_v1_0_0.md",
            ],
        )
        outputs = self.scope["exact_write_allowlist_for_audit"]
        self.assertEqual(
            outputs,
            [
                "configs/thesis_readiness_audit_v1_0_0_result.yaml",
                "docs/14_thesis_readiness_audit_v1_0_0.md",
                "tests/test_thesis_readiness_audit_boundary_v1_0_0.py",
            ],
        )
        for relative in [*review_outputs, *outputs]:
            assert_exact_relative_path(self, relative)
        self.assertFalse(self.scope["existing_input_files_may_be_modified"])
        self.assertFalse(self.scope["frozen_artifacts_may_be_modified"])


if __name__ == "__main__":
    unittest.main()

"""Structural, synthetic/config-only checks for readiness-audit allowlist v1.0.3."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST_PATH = ROOT / "configs/thesis_readiness_audit_v1_0_3_allowlist.yaml"
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
        self.assertEqual(self.control["version"], "1.0.3")
        self.assertEqual(
            self.control["status"], "PREPARED_AWAITING_ALLOWLIST_REVIEW"
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

    def test_successor_pins_failed_review_and_preserves_ancestors(self) -> None:
        basis = self.payload["remediation_basis"]
        predecessor = basis["predecessor_allowlist"]
        self.assertEqual(
            predecessor["path"],
            "configs/thesis_readiness_audit_v1_0_2_allowlist.yaml",
        )
        self.assertEqual(predecessor["version"], "1.0.2")
        self.assertEqual(
            predecessor["git_commit"],
            "9993afc0edaf93e2384ade93ab307199b9aa669a",
        )
        self.assertTrue(predecessor["remains_byte_identical"])
        self.assertTrue(predecessor["audit_use_prohibited_by_review"])
        self.assertEqual(
            sha256(ROOT / predecessor["path"]), predecessor["sha256"]
        )
        review = basis["failed_independent_review"]
        self.assertEqual(review["verdict"], "ALLOWLIST_REVIEW_FAIL")
        self.assertEqual(
            review["git_commit"],
            "d9840d3cd5189aa2b2350929ae8646e216de64f5",
        )
        self.assertFalse(review["substantive_review_completed"])
        self.assertTrue(review["process_nonconformance_only"])
        self.assertEqual(sha256(ROOT / review["yaml_path"]), review["yaml_sha256"])
        self.assertEqual(
            sha256(ROOT / review["markdown_path"]), review["markdown_sha256"]
        )
        ancestor = basis["immutable_v1_0_0_ancestor"]
        self.assertEqual(
            ancestor["allowlist_path"],
            "configs/thesis_readiness_audit_v1_0_0_allowlist.yaml",
        )
        self.assertEqual(
            ancestor["structural_test_path"],
            "tests/test_thesis_readiness_audit_allowlist_v1_0_0.py",
        )
        self.assertTrue(ancestor["remains_byte_identical"])
        self.assertTrue(ancestor["audit_use_prohibited_by_review"])
        self.assertEqual(
            sha256(ROOT / ancestor["allowlist_path"]),
            ancestor["allowlist_sha256"],
        )
        self.assertEqual(
            sha256(ROOT / ancestor["structural_test_path"]),
            ancestor["structural_test_sha256"],
        )
        self.assertEqual(
            set(basis["preserved_prior_remediations"]),
            {"ALLOWLIST-REVIEW-001", "ALLOWLIST-REVIEW-002"},
        )
        self.assertEqual(
            set(basis["remediated_findings"]),
            {"ALLOWLIST-REVIEW-003", "ALLOWLIST-REVIEW-004"},
        )
        self.assertFalse(basis["predecessor_review_established_allowlist_defect"])
        self.assertTrue(basis["successor_required_only_by_prior_runbook_route"])

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
        self.assertIn(
            "configs/thesis_readiness_audit_allowlist_review_v1_0_0.yaml", review
        )
        self.assertIn(
            "docs/13_thesis_readiness_audit_allowlist_review_v1_0_0.md", review
        )
        self.assertIn(
            "configs/thesis_readiness_audit_allowlist_review_v1_0_1.yaml",
            review,
        )
        self.assertIn(
            "docs/13_thesis_readiness_audit_allowlist_review_v1_0_1.md",
            review,
        )
        self.assertIn(
            "configs/thesis_readiness_audit_allowlist_review_v1_0_2.yaml",
            review,
        )
        self.assertIn(
            "docs/13_thesis_readiness_audit_allowlist_review_v1_0_2.md",
            review,
        )
        self.assertIn(
            "configs/thesis_readiness_audit_v1_0_3_allowlist.yaml",
            review,
        )
        self.assertIn(
            "tests/test_thesis_readiness_audit_allowlist_v1_0_3.py",
            review,
        )
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
        structural = by_id["thesis_readiness_allowlist_structure"]
        self.assertEqual(
            structural["command"],
            [
                "python",
                "-m",
                "unittest",
                "tests/test_thesis_readiness_audit_allowlist_v1_0_3.py",
            ],
        )
        self.assertEqual(
            structural["exact_inputs"],
            [
                "configs/thesis_readiness_audit_v1_0_3_allowlist.yaml",
                "tests/test_thesis_readiness_audit_allowlist_v1_0_3.py",
            ],
        )
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
            "modify_existing_input_configuration_code_test_document_or_artifact_outside_exact_plan_status_exception",
        }
        self.assertTrue(required_forbidden.issubset(forbidden))
        limits = self.payload["output_limits"]
        self.assertLessEqual(limits["max_tool_output_bytes_per_command"], 32768)
        self.assertEqual(limits["max_rendered_lines_per_command"], 240)
        self.assertNotIn("max_review_subject_lines_rendered_per_command", limits)
        self.assertEqual(limits["max_exact_files_per_review_content_read_command"], 1)
        self.assertEqual(limits["protected_content_rendered_rows"], 0)
        self.assertFalse(limits["rerun_with_broader_scope_after_cap_allowed"])
        stop = self.payload["stop_policy"]
        self.assertFalse(stop["incident_record_may_include_values"])
        self.assertFalse(
            stop["nonconformance_record_may_include_protected_or_analytical_values"]
        )
        self.assertFalse(stop["readiness_verdict_after_fatal_stop_allowed"])
        self.assertTrue(
            stop[
                "readiness_verdict_after_retryable_command_stop_and_compliant_retry_allowed"
            ]
        )

    def test_same_session_review_and_retryable_output_policy_are_explicit(self) -> None:
        policy = self.payload["allowlist_review_execution_policy"]
        self.assertEqual(
            set(policy["accepted_review_modes"]),
            {"same_session_technical_review", "independent_review"},
        )
        self.assertTrue(policy["same_session_iteration_allowed"])
        self.assertTrue(policy["review_requires_subject_committed_before_review"])
        self.assertTrue(policy["review_requires_separate_commit_after_subject_commit"])
        self.assertFalse(policy["review_may_modify_committed_subject"])
        self.assertFalse(policy["review_may_execute_readiness_audit"])
        self.assertFalse(policy["independent_reviewer_required"])
        retry = policy["non_exposure_tool_output_nonconformance"]
        self.assertFalse(retry["invalidates_allowlist_subject"])
        self.assertFalse(retry["requires_new_allowlist_version"])
        self.assertFalse(retry["invalidates_review_if_corrected_before_substantive_verdict"])
        self.assertTrue(retry["stop_current_command_only"])
        self.assertTrue(retry["retry_same_exact_path_with_smaller_output_allowed"])
        self.assertFalse(retry["scope_expansion_allowed"])

    def test_review_subject_uses_simple_200_line_guidance_under_240_cap(self) -> None:
        guidance = self.payload["review_subject_read_guidance"]
        subject = "configs/thesis_readiness_audit_v1_0_3_allowlist.yaml"
        self.assertEqual(guidance["exact_path"], subject)
        self.assertEqual(guidance["applies_to_contexts"], ["allowlist_review"])
        self.assertFalse(guidance["line_count_probe_required"])
        self.assertFalse(guidance["full_file_render_in_one_command_allowed"])
        self.assertEqual(guidance["maximum_rendered_lines_per_command"], 240)
        self.assertEqual(guidance["recommended_chunk_lines"], 200)
        self.assertEqual(
            guidance["recommended_command_template"],
            ["sed", "-n", "{start},{end}p", subject],
        )
        self.assertTrue(guidance["complete_subject_read_required_before_substantive_verdict"])
        self.assertIn(subject, self.scope["exact_content_read_allowlist_for_review"])
        generic = self.payload["operation_constraints"][
            "read_exact_review_allowlisted_file"
        ]
        self.assertEqual(generic["allowed_contexts"], ["allowlist_review"])
        self.assertEqual(generic["maximum_rendered_lines_per_command"], 240)
        self.assertTrue(generic["retry_with_smaller_output_after_non_exposure_limit_error"])
        route_id = self.payload["stop_policy"]["mandatory_trigger_routes"][
            "allowlist_review"
        ]["output_cap_exceeded_without_content_exposure"]
        self.assertEqual(route_id, "retryable_review_output_nonconformance")
        route = self.payload["stop_policy"]["route_definitions"][route_id]
        self.assertFalse(route["invalidates_allowlist_subject"])
        self.assertFalse(route["invalidates_review_after_compliant_retry"])
        self.assertFalse(route["new_allowlist_version_required"])
        self.assertTrue(route["retry_same_exact_path_with_smaller_output_allowed"])

    def test_review_commit_is_exactly_limited_to_three_outputs(self) -> None:
        review_outputs = self.scope["exact_write_allowlist_for_review"]
        self.assertEqual(len(review_outputs), 3)
        self.assertEqual(
            review_outputs,
            [
                "configs/thesis_readiness_audit_allowlist_review_v1_0_3.yaml",
                "docs/13_thesis_readiness_audit_allowlist_review_v1_0_3.md",
                "docs/10_current_experiment_status.md",
            ],
        )
        operations = set(self.payload["allowed_operations"]["allowlist_review"])
        self.assertIn("write_exact_review_output_file", operations)
        self.assertIn("git_diff_exact_review_output_files", operations)
        self.assertIn("commit_exact_review_output_files", operations)
        constraint = self.payload["operation_constraints"][
            "commit_exact_review_output_files"
        ]
        self.assertEqual(constraint["allowed_contexts"], ["allowlist_review"])
        self.assertEqual(
            constraint["exact_paths_reference"],
            "audit_scope.exact_write_allowlist_for_review",
        )
        self.assertEqual(constraint["exact_path_count"], 3)
        self.assertFalse(constraint["broad_staging_allowed"])
        self.assertFalse(constraint["additional_paths_may_be_staged_or_committed"])

    def test_every_mandatory_stop_route_is_permitted_and_exact(self) -> None:
        stop = self.payload["stop_policy"]
        routes = stop["route_definitions"]
        triggers = stop["mandatory_trigger_routes"]
        allowed = self.payload["allowed_operations"]
        required_triggers = {
            "unexpected_protected_or_analytical_content",
            "unlisted_path_required_without_content_exposure",
            "hash_or_inventory_mismatch_without_content_exposure",
            "schema_or_row_count_disclosure_risk_before_exposure",
            "allowlist_violation_without_content_exposure",
            "allowlist_violation_with_content_exposure",
            "ambiguous_period_boundary_without_content_exposure",
            "output_cap_exceeded_without_content_exposure",
        }
        self.assertEqual(
            set(triggers),
            {"allowlist_review", "audit_executor_after_review_pass"},
        )
        for context, mapping in triggers.items():
            self.assertEqual(set(mapping), required_triggers)
            for route_id in mapping.values():
                self.assertIn(route_id, routes)
                route = routes[route_id]
                self.assertIn(context, route["allowed_contexts"])
                self.assertTrue(set(route["mandatory_operations"]).issubset(allowed[context]))
                if route_id == "retryable_review_output_nonconformance":
                    self.assertNotIn("exact_output_route_reference", route)
                    self.assertEqual(route["mandatory_operations"], ["stop_current_operation"])
                    self.assertFalse(route["invalidates_review_after_compliant_retry"])
                    self.assertFalse(route["new_allowlist_version_required"])
                    continue
                prefix, key = route["exact_output_route_reference"].split(".", 1)
                self.assertEqual(prefix, "audit_scope")
                outputs = self.payload[prefix][key]
                self.assertTrue(outputs)
                self.assertEqual(len(outputs), len(set(outputs)))
                for relative in outputs:
                    assert_exact_relative_path(self, relative)
                commit_operations = [
                    operation
                    for operation in route["mandatory_operations"]
                    if operation.startswith("commit_exact_")
                ]
                self.assertEqual(len(commit_operations), 1)
                constraint = self.payload["operation_constraints"][
                    commit_operations[0]
                ]
                self.assertEqual(
                    constraint["exact_paths_reference"],
                    route["exact_output_route_reference"],
                )
                self.assertEqual(constraint["exact_path_count"], len(outputs))
                self.assertFalse(constraint["broad_staging_allowed"])
                self.assertFalse(
                    constraint["additional_paths_may_be_staged_or_committed"]
                )
        classifications = stop["classifications"]
        self.assertFalse(
            classifications["non_analytical_process_nonconformance"][
                "new_data_access_incident_declaration_required"
            ]
        )
        exposure = classifications[
            "unexpected_protected_or_analytical_content_exposure"
        ]
        self.assertTrue(exposure["new_data_access_incident_declaration_required"])
        self.assertFalse(exposure["scope_expansion_allowed"])
        incident = self.scope["exact_write_allowlist_for_unexpected_content_incident"]
        self.assertEqual(len(incident), 2)
        incident_route = routes["unexpected_content_exposure_incident"]
        self.assertFalse(incident_route["review_or_audit_verdict_output_may_be_written"])
        self.assertFalse(incident_route["protected_content_may_be_reopened_to_complete_record"])

    def test_audit_writes_only_new_exact_outputs(self) -> None:
        review_outputs = self.scope["exact_write_allowlist_for_review"]
        self.assertEqual(
            review_outputs,
            [
                "configs/thesis_readiness_audit_allowlist_review_v1_0_3.yaml",
                "docs/13_thesis_readiness_audit_allowlist_review_v1_0_3.md",
                "docs/10_current_experiment_status.md",
            ],
        )
        outputs = self.scope["exact_write_allowlist_for_audit"]
        self.assertEqual(
            outputs,
            [
                "configs/thesis_readiness_audit_v1_0_3_result.yaml",
                "docs/14_thesis_readiness_audit_v1_0_3.md",
                "tests/test_thesis_readiness_audit_boundary_v1_0_3.py",
            ],
        )
        incident_outputs = self.scope[
            "exact_write_allowlist_for_unexpected_content_incident"
        ]
        self.assertEqual(
            incident_outputs,
            [
                "configs/thesis_readiness_audit_access_incident_v1_0_3.yaml",
                "docs/13_1_thesis_readiness_audit_access_incident_v1_0_3.md",
            ],
        )
        for relative in [*review_outputs, *incident_outputs, *outputs]:
            assert_exact_relative_path(self, relative)
        self.assertFalse(self.scope["existing_input_files_may_be_modified"])
        self.assertEqual(
            self.scope["review_plan_status_existing_file_exception"],
            "docs/10_current_experiment_status.md",
        )
        self.assertFalse(self.scope["frozen_artifacts_may_be_modified"])


if __name__ == "__main__":
    unittest.main()

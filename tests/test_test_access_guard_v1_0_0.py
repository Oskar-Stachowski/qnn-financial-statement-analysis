"""Synthetic/config-only regressions for the v1.0.0 test-access guard."""

from __future__ import annotations

import copy
import unittest

import yaml

from src.testing.test_access_guard import (
    DEFAULT_MANIFEST,
    ROOT,
    TestAccessGuardError,
    _require_review_pass,
    selected_tests,
    tracked_test_paths,
    validate_manifest,
)


def load_manifest() -> dict[str, object]:
    payload = yaml.safe_load(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


class TestAccessGuardV100Tests(unittest.TestCase):
    def test_manifest_exactly_covers_tracked_test_inventory(self) -> None:
        manifest = load_manifest()
        counts = validate_manifest(manifest)
        declared = sorted(item["path"] for item in manifest["test_modules"])
        self.assertTrue(set(declared).issubset(tracked_test_paths()))
        self.assertEqual(sum(counts.values()), len(declared))

    def test_every_runnable_profile_excludes_protected_gated_modules(self) -> None:
        manifest = load_manifest()
        for profile_id in manifest["profiles"]:
            selected = selected_tests(manifest, profile_id, "manifest")
            self.assertTrue(selected)
            self.assertTrue(all(item["enabled"] is True for item in selected))
            self.assertTrue(
                all(item["category"] != "protected/gated" for item in selected)
            )

    def test_synthetic_profile_contains_no_development_inputs(self) -> None:
        selected = selected_tests(
            load_manifest(), "synthetic-config-only", "manifest"
        )
        self.assertTrue(
            all(item["category"] == "synthetic/config-only" for item in selected)
        )

    def test_reverse_order_is_exact_reverse_without_scope_change(self) -> None:
        manifest = load_manifest()
        forward = selected_tests(manifest, "canonical-safe", "manifest")
        reverse = selected_tests(manifest, "canonical-safe", "reverse")
        self.assertEqual(
            [item["id"] for item in reverse],
            [item["id"] for item in reversed(forward)],
        )

    def test_guard_rejects_protected_module_injected_into_profile(self) -> None:
        manifest = copy.deepcopy(load_manifest())
        manifest["profiles"]["canonical-safe"]["test_ids"].append(
            "x_t_pit_v1_freeze"
        )
        with self.assertRaisesRegex(TestAccessGuardError, "Protected test in profile"):
            validate_manifest(manifest)

    def test_guard_exposes_no_arbitrary_target_selection(self) -> None:
        with self.assertRaisesRegex(TestAccessGuardError, "Unknown profile"):
            selected_tests(
                load_manifest(), "tests/test_x_t_pit_v1_freeze.py", "manifest"
            )

    def test_canonical_profile_refuses_unreviewed_manifest(self) -> None:
        manifest = copy.deepcopy(load_manifest())
        manifest["review"]["result_path"] = (
            "configs/test_access_review_intentionally_missing.yaml"
        )
        with self.assertRaisesRegex(TestAccessGuardError, "Missing regular file"):
            _require_review_pass(DEFAULT_MANIFEST, manifest, root=ROOT)

    def test_procedural_exception_is_explicit_and_not_independent(self) -> None:
        manifest = load_manifest()
        exception = manifest["procedural_exception"]
        self.assertIs(exception["authorized_by_user"], True)
        self.assertEqual(
            exception["review_kind"], "same_session_technical_review"
        )
        self.assertIs(exception["independent_review_claimed"], False)
        self.assertIs(exception["step_6_blockers_waived"], False)
        self.assertIs(
            manifest["test_access_manifest"]["execution_authorized"], False
        )
        self.assertEqual(
            manifest["test_access_manifest"]["incident"]["path"],
            "configs/data_access_incident_v1_2_0.yaml",
        )

    def test_review_scope_has_no_data_or_report_content_paths(self) -> None:
        allowlist_path = ROOT / "configs/test_access_review_allowlist_v1_0_0.yaml"
        allowlist = yaml.safe_load(allowlist_path.read_text(encoding="utf-8"))
        paths = allowlist["exact_content_paths"]
        self.assertEqual(paths, list(dict.fromkeys(paths)))
        self.assertFalse(
            any(path.startswith(("data/", "reports/")) for path in paths)
        )
        self.assertEqual(allowlist["tracked_fixture_paths"], [])


if __name__ == "__main__":
    unittest.main()

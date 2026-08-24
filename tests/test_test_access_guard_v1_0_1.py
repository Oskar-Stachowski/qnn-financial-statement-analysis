"""Successor regressions for the explicitly authorized v1.0.1 guard scope."""

from __future__ import annotations

import copy
from pathlib import Path
import unittest

import yaml

from src.testing.test_access_guard import (
    ROOT,
    TestAccessGuardError,
    _require_review_pass,
    selected_tests,
    validate_manifest,
)


MANIFEST_PATH = ROOT / "configs/test_access_manifest_v1_0_1.yaml"
SUCCESSOR_MANIFEST_PATH = ROOT / "configs/test_access_manifest_v1_0_2.yaml"
ABORTED_MANIFEST_PATH = ROOT / "configs/test_access_manifest_v1_0_0.yaml"


def load(path: Path) -> dict[str, object]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


class TestAccessGuardV101Tests(unittest.TestCase):
    def test_successor_is_valid_and_explicitly_authorized(self) -> None:
        manifest = load(MANIFEST_PATH)
        counts = validate_manifest(manifest)
        self.assertEqual(manifest["test_access_manifest"]["version"], "1.0.1")
        self.assertIs(manifest["test_access_manifest"]["execution_authorized"], True)
        self.assertEqual(sum(counts.values()), len(manifest["test_modules"]))

    def test_override_does_not_resolve_incident_or_open_protected_tests(self) -> None:
        override = load(MANIFEST_PATH)["same_session_override"]
        self.assertIs(override["authorized_by_user"], True)
        self.assertIs(override["incident_resolved"], False)
        self.assertIs(override["protected_tests_remain_blocked"], True)
        for profile_id in ("synthetic-config-only", "canonical-safe"):
            selected = selected_tests(load(MANIFEST_PATH), profile_id, "manifest")
            self.assertTrue(all(item["category"] != "protected/gated" for item in selected))

    def test_aborted_v100_remains_fail_closed(self) -> None:
        manifest = load(ABORTED_MANIFEST_PATH)
        validate_manifest(manifest)
        self.assertIs(manifest["test_access_manifest"]["execution_authorized"], False)

    def test_canonical_profile_requires_committed_review_result(self) -> None:
        manifest = copy.deepcopy(load(MANIFEST_PATH))
        manifest["review"]["result_path"] = (
            "configs/test_access_review_v1_0_1_intentionally_missing.yaml"
        )
        with self.assertRaisesRegex(TestAccessGuardError, "Missing regular file"):
            _require_review_pass(MANIFEST_PATH, manifest, root=ROOT)

    def test_v102_repair_successor_is_valid(self) -> None:
        manifest = load(SUCCESSOR_MANIFEST_PATH)
        validate_manifest(manifest)
        self.assertEqual(manifest["test_access_manifest"]["version"], "1.0.2")
        self.assertIs(manifest["test_access_manifest"]["execution_authorized"], True)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "configs/target_candidate_v2_pit_b_freeze_manifest.yaml"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FrozenTargetManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_identifies_the_frozen_target(self) -> None:
        target = self.manifest["target"]
        self.assertEqual(target["id"], "target_candidate_v2_pit_b")
        self.assertEqual(target["version"], "1.0.0")
        self.assertEqual(target["status"], "frozen")
        self.assertEqual(
            target["freeze_scope"], "target_definition_and_pit_b_extraction"
        )
        self.assertFalse(target["dataset_frozen"])
        self.assertFalse(target["feature_pipeline_frozen"])
        self.assertFalse(target["research_universe_frozen"])

    def test_versioned_component_hashes_match_the_manifest(self) -> None:
        for component_group in self.manifest["versioned_components"].values():
            for component in component_group:
                path = ROOT / component["path"]
                with self.subTest(path=component["path"]):
                    self.assertTrue(path.is_file())
                    self.assertEqual(sha256(path), component["sha256"])

    def test_development_scope_excludes_test_years(self) -> None:
        scope = self.manifest["development_scope"]
        self.assertEqual(scope["train_feature_years"], [2011, 2020])
        self.assertEqual(scope["validation_feature_years"], [2021, 2022])
        self.assertEqual(scope["test_feature_years"], [2023, 2024])
        self.assertFalse(scope["test_used_in_pit_b_freeze_gate"])


if __name__ == "__main__":
    unittest.main()

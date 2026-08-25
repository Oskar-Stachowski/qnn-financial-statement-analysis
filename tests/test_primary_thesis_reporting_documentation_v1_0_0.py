from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PrimaryThesisReportingDocumentationTests(unittest.TestCase):
    def test_active_status_no_longer_calls_protected_period_closed(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        status = (ROOT / "docs/10_current_experiment_status.md").read_text(
            encoding="utf-8"
        )
        stale = "Feature years 2021–2024 remain closed"
        self.assertNotIn(stale, readme)
        self.assertNotIn(stale, status)
        self.assertIn("PRIMARY_REPORTING_FREEZE_PASS", readme)
        self.assertIn("PRIMARY_REPORTING_FREEZE_PASS", status)
        self.assertIn("Status date: 2026-08-25", status)

    def test_active_readme_records_current_and_historical_qnn_backends(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        normalized = " ".join(readme.split())
        self.assertIn("`lightning.qubit`", readme)
        self.assertIn("earlier `default.qubit` execution was interrupted", normalized)
        self.assertIn("partial outputs were ineligible and not", normalized)

    def test_new_document_links_resolve(self) -> None:
        paths = (
            ROOT / "README.md",
            ROOT / "docs/12_10_primary_thesis_reporting_v1_0_0.md",
            ROOT / "docs/15_author_work_handoff_v1_0_0.md",
        )
        pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for document in paths:
            for target in pattern.findall(document.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                resolved = (document.parent / target).resolve()
                self.assertTrue(resolved.exists(), f"Broken link in {document}: {target}")

    def test_frozen_package_and_handoff_boundaries_agree(self) -> None:
        freeze = json.loads(
            (ROOT / "configs/primary_thesis_reporting_freeze_v1_0_0_result.json").read_text()
        )
        handoff = (ROOT / "docs/15_author_work_handoff_v1_0_0.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(freeze["verdict"], "PRIMARY_REPORTING_FREEZE_PASS")
        self.assertTrue(freeze["development_spent_holdout_estimands_separate"])
        self.assertFalse(freeze["failed_v1_0_0_output_included"])
        self.assertIn("Do not pool development, spent-development and holdout", handoff)
        self.assertIn("Do not use the failed v1.0.0", handoff)


if __name__ == "__main__":
    unittest.main()

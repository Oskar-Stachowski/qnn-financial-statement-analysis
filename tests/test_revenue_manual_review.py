from __future__ import annotations

import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

import src.data.revenue_manual_review as review_module
from src.data.revenue_manual_review import (
    review_key_digest,
    validate_completed_review,
)


prepare_audit_module = importlib.import_module(
    "src.data.16_prepare_final_revenue_resolver_audit"
)
evidence_module = importlib.import_module(
    "src.data.17_prepare_revenue_manual_review_evidence"
)


def review_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    template = pd.DataFrame(
        {
            "cik10": ["0000000001", "0000000002"],
            "feature_year": [2019, 2020],
            "anchor_t1_accn": ["a1", "a2"],
            "local_statement_path": ["data/a/R1.htm", "data/b/R2.htm"],
            "manual_review_outcome": ["pending", "pending"],
            "manual_statement_is_primary_consolidated": [pd.NA, pd.NA],
            "manual_row_is_total_revenue": [pd.NA, pd.NA],
            "manual_current_value_matches": [pd.NA, pd.NA],
            "manual_comparative_value_matches": [pd.NA, pd.NA],
            "manual_provenance_matches": [pd.NA, pd.NA],
            "manual_selection_error": [pd.NA, pd.NA],
            "manual_notes": ["", ""],
        }
    )
    completed = template.copy()
    completed["manual_review_outcome"] = ["pass", "pass"]
    for column in review_module.REQUIRED_CHECK_COLUMNS:
        completed[column] = True
    completed["manual_selection_error"] = False
    completed["manual_notes"] = ["Checked row 1", "Checked row 2"]
    return template, completed


class ManualReviewValidationTests(unittest.TestCase):
    def validate_fixture(
        self, completed: pd.DataFrame, template: pd.DataFrame
    ) -> pd.DataFrame:
        digest = review_key_digest(template, label="test template")
        with (
            patch.object(review_module, "EXPECTED_REVIEW_COUNT", len(template)),
            patch.object(review_module, "EXPECTED_REVIEW_KEY_SHA256", digest),
        ):
            return validate_completed_review(completed, template=template)

    def test_accepts_explicit_completed_decisions(self) -> None:
        template, completed = review_frames()
        validated = self.validate_fixture(completed, template)
        self.assertEqual(validated["manual_review_outcome"].tolist(), ["pass", "pass"])
        self.assertTrue(validated["manual_provenance_matches"].all())

    def test_rejects_pending_or_blanket_missing_decisions(self) -> None:
        template, _ = review_frames()
        with self.assertRaisesRegex(RuntimeError, "invalid review outcomes"):
            self.validate_fixture(template.copy(), template)

    def test_rejects_inconsistent_pass(self) -> None:
        template, completed = review_frames()
        completed.loc[0, "manual_current_value_matches"] = False
        with self.assertRaisesRegex(RuntimeError, "inconsistent"):
            self.validate_fixture(completed, template)

    def test_rejects_changed_immutable_provenance(self) -> None:
        template, completed = review_frames()
        completed.loc[0, "anchor_t1_accn"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "immutable"):
            self.validate_fixture(completed, template)

    def test_rejects_changed_key_manifest(self) -> None:
        template, completed = review_frames()
        digest = review_key_digest(template, label="test template")
        completed.loc[0, "feature_year"] = 2018
        with (
            patch.object(review_module, "EXPECTED_REVIEW_COUNT", len(template)),
            patch.object(review_module, "EXPECTED_REVIEW_KEY_SHA256", digest),
            self.assertRaisesRegex(RuntimeError, "key manifest changed"),
        ):
            validate_completed_review(completed, template=template)


class AuditPipelineGuardTests(unittest.TestCase):
    def test_manual_sample_inputs_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_root = Path(temporary_directory)
            with (
                patch.object(
                    prepare_audit_module, "ROWS_PATH", missing_root / "rows.csv"
                ),
                patch.object(
                    prepare_audit_module,
                    "REVISIONS_PATH",
                    missing_root / "revisions.csv",
                ),
                patch.object(
                    prepare_audit_module,
                    "OLD_CONFLICTS_PATH",
                    missing_root / "conflicts.csv",
                ),
                self.assertRaisesRegex(FileNotFoundError, "Required audit inputs"),
            ):
                prepare_audit_module.require_manual_sample_inputs()

    def test_statement_path_must_be_relative_and_inside_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            evidence_root = base / "data" / "raw" / "evidence"
            statement = evidence_root / "0000000001" / "a1" / "R1.htm"
            statement.parent.mkdir(parents=True)
            statement.write_text("statement", encoding="utf-8")
            relative = statement.relative_to(base)
            with (
                patch.object(evidence_module, "BASE_DIR", base),
                patch.object(evidence_module, "EVIDENCE_ROOT", evidence_root),
            ):
                self.assertEqual(
                    evidence_module.resolve_statement_path(relative),
                    statement.resolve(),
                )
                with self.assertRaisesRegex(RuntimeError, "must be relative"):
                    evidence_module.resolve_statement_path(statement.resolve())


if __name__ == "__main__":
    unittest.main()

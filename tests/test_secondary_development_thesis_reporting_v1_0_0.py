"""Tests for secondary-development thesis reporting v1.0.0."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.modeling.secondary_development_thesis_reporting_v1_0_0 import (
    DEFAULT_CONFIG,
    _metric_summary,
    generate_report,
    verify_reporting_package,
)


ROOT = Path(__file__).resolve().parents[1]


class SecondaryDevelopmentThesisReportingTests(unittest.TestCase):
    def test_package_and_sources_are_read_only(self) -> None:
        result = verify_reporting_package(DEFAULT_CONFIG)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["project_model_fit_performed"])
        self.assertFalse(result["protected_feature_years_opened"])
        source = (
            ROOT
            / "src/modeling/secondary_development_thesis_reporting_v1_0_0.py"
        ).read_text(encoding="utf-8")
        for forbidden in (".fit(", "2021.csv", "2022.csv", "2023.csv", "2024.csv"):
            self.assertNotIn(forbidden, source)

    def test_metric_summary_is_exact_on_generated_rows(self) -> None:
        rows = []
        for year in range(2015, 2021):
            rows.extend(
                [
                    {
                        "identity": f"negative-{year}",
                        "fold_id": f"fold_{year}",
                        "year": year,
                        "label": 0,
                        "score": 0.1,
                    },
                    {
                        "identity": f"positive-{year}",
                        "fold_id": f"fold_{year}",
                        "year": year,
                        "label": 1,
                        "score": 0.9,
                    },
                ]
            )
        result = _metric_summary(rows)
        self.assertEqual(result["n"], 12)
        self.assertEqual(result["positive_n"], 6)
        self.assertEqual(result["pooled_oof_pr_auc"], 1.0)
        self.assertEqual(result["pooled_oof_roc_auc"], 1.0)

    def test_full_report_generation_from_frozen_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as directory:
            output = Path(directory) / "secondary-report"
            result = generate_report(DEFAULT_CONFIG, output)
            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["tables"], 10)
            self.assertEqual(result["figure_files"], 12)
            self.assertEqual(result["task_results"], 96)
            self.assertEqual(result["prediction_artifacts_read"], 84)
            self.assertFalse(result["project_model_fit_performed"])
            self.assertFalse(result["protected_feature_years_opened"])
            manifest = json.loads(
                (output / "analysis_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "COMPLETE")
            self.assertEqual(len(manifest["generated_tables"]), 10)
            self.assertEqual(len(manifest["generated_figures"]), 12)
            self.assertEqual(len(manifest["generated_files"]), 23)


if __name__ == "__main__":
    unittest.main()

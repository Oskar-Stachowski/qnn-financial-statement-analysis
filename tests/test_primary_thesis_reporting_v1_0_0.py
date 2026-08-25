from __future__ import annotations

import csv
import io
import json
import unittest

from src.modeling import primary_thesis_reporting_v1_0_0 as reporting


def _metric_row(year: int, index: int) -> dict:
    value = 0.2 + index / 1000
    return {
        "identity": {
            "family": f"family_{index}",
            "feature_block": "L+D+R",
            "configuration_id": f"configuration_{index}",
        },
        "year": year,
        "n": 100,
        "positive_n": 20,
        "metrics": {
            "pr_auc": value,
            "roc_auc": value + 0.3,
            "brier_score": 0.1,
            "f1_frozen_threshold": 0.4,
            "precision_frozen_threshold": 0.35,
            "recall_frozen_threshold": 0.5,
        },
        "cluster_bootstrap": {
            "replicates": 2000,
            "valid_replicates": 2000,
            "intervals": {
                "pr_auc": {"lower": value - 0.01, "upper": value + 0.01},
                "roc_auc": {"lower": value + 0.29, "upper": value + 0.31},
                "f1_frozen_threshold": {"lower": 0.39, "upper": 0.41},
            },
        },
    }


def _report(years: tuple[int, int], label: str) -> dict:
    return {
        "period_label": label,
        "fully_unseen_claimed": False,
        "selection_or_tuning_performed": False,
        "prior_exposure_disclosure": f"Synthetic disclosure for {label}.",
        "metric_rows": [
            _metric_row(year, index)
            for year in years
            for index in range(9)
        ],
    }


def _source() -> dict:
    development = [
        {
            "rank": str(index + 1),
            "family": f"family_{index}",
            "stage": "coarse",
            "feature_block": "L+D+R",
            "configuration_id": f"configuration_{index}",
            "training_seed": "AVERAGED",
            "status": "COMPLETE",
            "pooled_oof_pr_auc": str(0.4 - index / 100),
            "pooled_oof_roc_auc": str(0.7 - index / 100),
            "parameters": "{}",
        }
        for index in range(9)
    ]
    items = {
        "development_ranking": {"path": "development.csv", "sha256": "a" * 64},
        "spent_report": {"path": "spent.json", "sha256": "b" * 64},
        "holdout_report": {"path": "holdout.json", "sha256": "c" * 64},
    }
    return {
        "development": development,
        "spent": _report((2021, 2022), "spent"),
        "holdout": _report((2023, 2024), "holdout"),
        "source_items": items,
        "provenance_items": [
            {"package": "synthetic", "path": "manifest.json", "sha256": "d" * 64}
        ],
    }


class PrimaryThesisReportingTests(unittest.TestCase):
    def test_package_is_deterministic_and_keeps_estimands_separate(self) -> None:
        first = reporting.build_artifacts(_source())
        second = reporting.build_artifacts(_source())
        self.assertEqual(first, second)

        manifest = json.loads(first["manifest.json"])
        self.assertEqual(manifest["development_rows"], 9)
        self.assertEqual(manifest["protected_metric_rows"], 36)
        self.assertEqual(manifest["figures"], 0)

        rows = list(
            csv.DictReader(
                io.StringIO(first["tables/02_protected_period_metrics.csv"].decode())
            )
        )
        self.assertEqual(len(rows), 36)
        self.assertEqual(
            {row["period_role"] for row in rows},
            {"spent_development", "holdout"},
        )
        self.assertEqual(
            {int(row["year"]) for row in rows if row["period_role"] == "holdout"},
            {2023, 2024},
        )

    def test_unavailable_outputs_are_explicitly_omitted(self) -> None:
        artifacts = reporting.build_artifacts(_source())
        rows = list(
            csv.DictReader(
                io.StringIO(first := artifacts["tables/04_reporting_availability.csv"].decode())
            )
        )
        self.assertTrue(first)
        omitted = {row["requested_output"] for row in rows if row["status"].startswith("OMIT")}
        self.assertIn("log loss", omitted)
        self.assertIn("calibration intercept slope and calibration curve", omitted)
        self.assertIn("new paired comparisons FP FN cases and runtime costs", omitted)

    def test_fully_unseen_claim_fails_closed(self) -> None:
        source = _source()
        source["holdout"]["fully_unseen_claimed"] = True
        with self.assertRaises(reporting.ReportingError):
            reporting.build_artifacts(source)

    def test_cli_exposes_no_arbitrary_paths(self) -> None:
        parser = reporting.build_parser()
        self.assertEqual(parser.parse_args(["generate"]).action, "generate")
        with self.assertRaises(SystemExit):
            parser.parse_args(["generate", "--output", "/tmp/escape"])


if __name__ == "__main__":
    unittest.main()

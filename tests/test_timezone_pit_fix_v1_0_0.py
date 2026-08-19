from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
FIX = importlib.import_module("src.data.37_fix_target_timezone_pit_train")
CONFIG_PATH = ROOT / "configs/timezone_pit_fix_v1_0_0.yaml"


class TimezonePitFixUnitTests(unittest.TestCase):
    def test_exact_accession_instant_overrides_conflicting_target_serialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source = directory / "source.csv"
            output = directory / "output.csv"
            with source.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    [
                        "research_universe_company_year_id",
                        "feature_year",
                        "anchor_t1_accn",
                        "anchor_t1_accepted_at",
                        "target_candidate_v2_pit_b",
                    ]
                )
                writer.writerow(
                    ["0000000001-2013", "2013", "a1", "2015-04-30T17:01:07Z", "1"]
                )
            result = FIX.rewrite_target_artifact(
                source, output, {"a1": "2015-04-30T21:01:00Z"}
            )
            with output.open("r", encoding="utf-8", newline="") as stream:
                row = list(csv.DictReader(stream))[0]
        self.assertEqual(row["anchor_t1_accepted_at"], "2015-04-30T21:01:00Z")
        self.assertEqual(row["target_candidate_v2_pit_b"], "1")
        self.assertEqual(result["non_timestamp_cells_changed"], 0)


class TimezonePitFixArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        cls.report = json.loads(
            (ROOT / cls.config["outputs"]["audit_report"]).read_text(encoding="utf-8")
        )

    def test_artifact_hashes_and_scientific_values_are_unchanged(self) -> None:
        results = self.config["results"]
        self.assertEqual(
            FIX.sha256(ROOT / self.config["outputs"]["target_train"]),
            results["target_train"]["sha256"],
        )
        self.assertEqual(
            FIX.sha256(ROOT / self.config["outputs"]["target_application_train"]),
            results["target_application_train"]["sha256"],
        )
        self.assertEqual(
            FIX.sha256(ROOT / self.config["inputs"]["raw_x_t_train"]),
            results["raw_x_t_train"]["sha256_after"],
        )
        self.assertTrue(self.report["target_labels_unchanged"])
        self.assertTrue(self.report["target_statuses_unchanged"])
        self.assertTrue(self.report["x_t_artifact_unchanged"])
        self.assertEqual(self.report["positive_n"], 3623)
        self.assertEqual(self.report["negative_n"], 16048)

    def test_exact_three_company_year_membership_changes(self) -> None:
        actual = [
            (item["fold"], item["change"], item["research_universe_company_year_id"])
            for item in self.report["changed_memberships"]
        ]
        self.assertEqual(
            actual,
            [
                ("fold_2015", "removed", "0000880460-2013"),
                ("fold_2015", "removed", "0001472601-2013"),
                ("fold_2019", "removed", "0001586495-2016"),
            ],
        )

    def test_all_six_fold_hashes_and_pit_invariants_are_exact(self) -> None:
        expected = {
            item["id"]: item for item in self.config["results"]["folds"]
        }
        self.assertEqual(len(self.report["folds"]), 6)
        for fold in self.report["folds"]:
            frozen = expected[fold["id"]]
            with self.subTest(fold=fold["id"]):
                self.assertEqual(
                    fold["pit_safe_train_n_after"], frozen["pit_safe_train_n"]
                )
                self.assertEqual(
                    fold["train_membership_sha256_after"],
                    frozen["train_membership_sha256"],
                )
                self.assertEqual(fold["prediction_before_target_violations"], 0)
                self.assertEqual(fold["target_after_cutoff_violations"], 0)
        self.assertTrue(self.report["all_six_folds_pass_label_availability"])
        self.assertEqual(
            self.report["supervised_prediction_before_target_violations"], 0
        )

    def test_target_labels_are_byte_identical_as_fields(self) -> None:
        usecols = [
            "research_universe_company_year_id",
            "target_status",
            "target_candidate_v2_pit_b",
        ]
        old = pd.read_csv(
            ROOT / self.config["inputs"]["target_application_train"],
            usecols=usecols,
            dtype=str,
            low_memory=False,
        ).sort_values(usecols[0]).reset_index(drop=True)
        new = pd.read_csv(
            ROOT / self.config["outputs"]["target_application_train"],
            usecols=usecols,
            dtype=str,
            low_memory=False,
        ).sort_values(usecols[0]).reset_index(drop=True)
        pd.testing.assert_frame_equal(old, new)


if __name__ == "__main__":
    unittest.main()

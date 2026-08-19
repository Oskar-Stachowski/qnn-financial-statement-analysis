from __future__ import annotations

import unittest

import pandas as pd

from src.modeling.temporal_cv import (
    MAIN_EXPANDING_WINDOW_FOLDS,
    PointInTimeFoldAudit,
    TemporalFold,
    fold_timeline,
    iter_point_in_time_folds,
    iter_temporal_folds,
    purge_overlapping_training_groups,
    validate_expanding_folds,
)


class TemporalCrossValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = pd.DataFrame(
            {
                "row_id": range(20),
                "feature_year": [year for year in range(2011, 2021) for _ in range(2)],
                "economic_group_id": [
                    group for year in range(2011, 2021) for group in ("persistent", f"g{year}")
                ],
                "prediction_timestamp": [
                    f"{year + 1}-04-01T00:00:00Z"
                    for year in range(2011, 2021)
                    for _ in range(2)
                ],
                "target_available_at": [
                    f"{year + 2}-03-01T00:00:00Z"
                    for year in range(2011, 2021)
                    for _ in range(2)
                ],
            }
        )

    def test_main_fold_definitions_are_exact(self) -> None:
        self.assertEqual(len(MAIN_EXPANDING_WINDOW_FOLDS), 6)
        self.assertEqual(
            [fold.validation_years for fold in MAIN_EXPANDING_WINDOW_FOLDS],
            [(2015,), (2016,), (2017,), (2018,), (2019,), (2020,)],
        )
        self.assertEqual(MAIN_EXPANDING_WINDOW_FOLDS[0].train_years, (2011, 2012, 2013))
        self.assertEqual(
            MAIN_EXPANDING_WINDOW_FOLDS[-1].train_years,
            (2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018),
        )

    def test_every_fold_is_strictly_temporal_and_expanding(self) -> None:
        partitions = list(iter_temporal_folds(self.frame))
        previous_train_rows = 0
        for fold, train, validation in partitions:
            self.assertLess(train["feature_year"].max(), validation["feature_year"].min())
            self.assertTrue(set(train.index).isdisjoint(validation.index))
            self.assertGreater(len(train), previous_train_rows)
            self.assertEqual(validation["feature_year"].unique().tolist(), list(fold.validation_years))
            previous_train_rows = len(train)

    def test_invalid_folds_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            TemporalFold("leaky", 2011, 2015, 2015, 2015)
        nonexpanding = (
            TemporalFold("a", 2011, 2014, 2015, 2015),
            TemporalFold("b", 2012, 2015, 2016, 2016),
        )
        with self.assertRaises(ValueError):
            validate_expanding_folds(nonexpanding)

    def test_rows_outside_cv_pool_fail_closed(self) -> None:
        outside = pd.concat(
            [
                self.frame,
                pd.DataFrame(
                    {
                        "row_id": [21],
                        "feature_year": [2021],
                        "economic_group_id": ["external_validation"],
                    }
                ),
            ],
            ignore_index=True,
        )
        with self.assertRaises(ValueError):
            list(iter_temporal_folds(outside))

    def test_group_purge_removes_train_overlap_and_preserves_validation(self) -> None:
        _, train, validation = next(iter_temporal_folds(self.frame))
        validation_before = validation.copy(deep=True)
        purged, overlapping = purge_overlapping_training_groups(train, validation)
        self.assertEqual(overlapping, ("persistent",))
        self.assertNotIn("persistent", set(purged["economic_group_id"]))
        self.assertTrue(
            set(purged["economic_group_id"]).isdisjoint(validation["economic_group_id"])
        )
        pd.testing.assert_frame_equal(validation, validation_before)

    def test_point_in_time_cutoff_excludes_late_training_labels(self) -> None:
        late_index = self.frame.index[
            self.frame["feature_year"].eq(2013)
            & self.frame["economic_group_id"].eq("g2013")
        ][0]
        self.frame.loc[late_index, "target_available_at"] = "2017-01-01T00:00:00Z"
        fold, train, validation, audit = next(iter_point_in_time_folds(self.frame))
        self.assertIsInstance(audit, PointInTimeFoldAudit)
        self.assertEqual(fold.name, "fold_2015")
        self.assertEqual(audit.label_unavailable_rows_excluded, 1)
        self.assertNotIn(late_index, train.index)
        self.assertEqual(validation["feature_year"].unique().tolist(), [2015])

    def test_prediction_must_strictly_precede_own_target_availability(self) -> None:
        invalid_index = self.frame.index[
            self.frame["feature_year"].eq(2013)
        ][0]
        self.frame.loc[invalid_index, "target_available_at"] = (
            self.frame.loc[invalid_index, "prediction_timestamp"]
        )
        with self.assertRaisesRegex(AssertionError, "strictly precede"):
            list(iter_point_in_time_folds(self.frame))

    def test_cutoff_comparison_uses_instants_not_rendered_offsets(self) -> None:
        late_index = self.frame.index[
            self.frame["feature_year"].eq(2013)
            & self.frame["economic_group_id"].eq("g2013")
        ][0]
        self.frame.loc[late_index, "target_available_at"] = "2016-04-01T00:30:00-04:00"
        first_fold = next(iter_point_in_time_folds(self.frame))
        _, train, _, audit = first_fold
        self.assertNotIn(late_index, train.index)
        self.assertEqual(audit.label_unavailable_rows_excluded, 1)

    def test_missing_group_id_fails_closed(self) -> None:
        _, train, validation = next(iter_temporal_folds(self.frame))
        train.loc[train.index[0], "economic_group_id"] = None
        with self.assertRaises(ValueError):
            purge_overlapping_training_groups(train, validation)

    def test_timeline_marks_train_and_validation(self) -> None:
        timeline = fold_timeline()
        self.assertEqual(timeline.loc["fold_2015", "2011"], "TR")
        self.assertEqual(timeline.loc["fold_2015", "2015"], "VA")
        self.assertEqual(timeline.loc["fold_2015", "2014"], "EM")
        self.assertEqual(timeline.loc["fold_2015", "2016"], "·")
        self.assertEqual(timeline.loc["fold_2020", "2020"], "VA")


if __name__ == "__main__":
    unittest.main()

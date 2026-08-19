from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from src.modeling.preprocessing import (
    FEATURE_BLOCKS,
    FROZEN_BLOCK_COMPARISONS,
    FinancialPreprocessor,
    NotFittedError,
    PreprocessingPolicy,
    features_for_blocks,
)


class FinancialPreprocessorTests(unittest.TestCase):
    def test_frozen_block_combinations_and_order(self) -> None:
        self.assertEqual(FROZEN_BLOCK_COMPARISONS, (("L",), ("L", "D"), ("L", "D", "R")))
        self.assertEqual(features_for_blocks(("L",)), FEATURE_BLOCKS["L"])
        self.assertEqual(
            features_for_blocks(("L", "D", "R")),
            FEATURE_BLOCKS["L"] + FEATURE_BLOCKS["D"] + FEATURE_BLOCKS["R"],
        )
        with self.assertRaises(ValueError):
            features_for_blocks(("R",))

    def test_fit_uses_training_values_only(self) -> None:
        train = pd.DataFrame({"x": [1.0, 2.0, np.nan, 100.0]})
        validation = pd.DataFrame({"x": [np.nan, 1_000_000.0]})
        transformer = FinancialPreprocessor(
            ["x"], policy=PreprocessingPolicy(lower_quantile=0.0, upper_quantile=0.75)
        ).fit(train)
        state_before = transformer.fitted_state()
        transformed = transformer.transform(validation)
        state_after = transformer.fitted_state()

        self.assertEqual(transformer.medians_["x"], 2.0)
        self.assertEqual(transformer.upper_bounds_["x"], 51.0)
        self.assertEqual(transformed.loc[0, "x__missing"], 1)
        self.assertEqual(transformed.loc[1, "x__missing"], 0)
        self.assertEqual(state_before, state_after)

    def test_winsorization_imputation_scaling_and_indicators(self) -> None:
        train = pd.DataFrame(
            {
                "x": [0.0, 1.0, 2.0, 100.0, np.nan],
                "y": [5.0, 5.0, 5.0, 5.0, 5.0],
            },
            index=[10, 11, 12, 13, 14],
        )
        original = train.copy(deep=True)
        transformer = FinancialPreprocessor(
            ["x", "y"],
            policy=PreprocessingPolicy(lower_quantile=0.0, upper_quantile=0.75),
        ).fit(train)
        stages = transformer.transform_stages(train)

        pd.testing.assert_frame_equal(train, original)
        self.assertEqual(stages["winsorized"].loc[13, "x"], 26.5)
        self.assertEqual(stages["imputed"].loc[14, "x"], 1.5)
        self.assertEqual(stages["indicators"].loc[14, "x__missing"], 1)
        self.assertEqual(stages["indicators"].loc[10, "x__missing"], 0)
        self.assertTrue(np.isclose(stages["scaled"]["x"].mean(), 0.0))
        self.assertTrue(np.isclose(stages["scaled"]["x"].std(ddof=0), 1.0))
        self.assertTrue(stages["scaled"]["y"].eq(0.0).all())
        self.assertIn("y", transformer.constant_features_)
        self.assertEqual(list(stages["transformed"].index), list(train.index))
        self.assertEqual(
            tuple(stages["transformed"].columns),
            ("x", "y", "x__missing", "y__missing"),
        )

    def test_same_rows_are_preserved_for_every_frozen_block_comparison(self) -> None:
        all_features = features_for_blocks(("L", "D", "R"))
        frame = pd.DataFrame(
            {feature: [1.0, np.nan, 3.0] for feature in all_features},
            index=[101, 102, 103],
        )
        for blocks in FROZEN_BLOCK_COMPARISONS:
            transformer = FinancialPreprocessor.for_blocks(blocks)
            transformed = transformer.fit_transform(frame)
            self.assertEqual(list(transformed.index), [101, 102, 103])
            self.assertEqual(len(transformed), len(frame))

    def test_schema_errors_and_not_fitted_error_are_explicit(self) -> None:
        transformer = FinancialPreprocessor(["x"])
        with self.assertRaises(NotFittedError):
            transformer.transform(pd.DataFrame({"x": [1.0]}))
        with self.assertRaises(KeyError):
            transformer.fit(pd.DataFrame({"y": [1.0]}))
        with self.assertRaises(ValueError):
            transformer.fit(pd.DataFrame({"x": [np.nan, np.nan]}))
        with self.assertRaises(ValueError):
            transformer.fit(pd.DataFrame({"x": [1.0, np.inf]}))

    def test_validation_only_missingness_has_a_fixed_indicator_column(self) -> None:
        train = pd.DataFrame({"x": [1.0, 2.0, 3.0]})
        validation = pd.DataFrame({"x": [np.nan]})
        transformer = FinancialPreprocessor(["x"]).fit(train)
        transformed = transformer.transform(validation)
        self.assertEqual(transformer.missing_count_["x"], 0)
        self.assertEqual(transformed.loc[0, "x__missing"], 1)
        self.assertIn("x__missing", transformer.get_feature_names_out())

    def test_indicators_can_be_disabled_without_changing_row_count(self) -> None:
        frame = pd.DataFrame({"x": [1.0, np.nan, 3.0]})
        transformer = FinancialPreprocessor(
            ["x"], policy=PreprocessingPolicy(add_missing_indicators=False)
        )
        transformed = transformer.fit_transform(frame)
        self.assertEqual(tuple(transformed.columns), ("x",))
        self.assertEqual(len(transformed), len(frame))


if __name__ == "__main__":
    unittest.main()

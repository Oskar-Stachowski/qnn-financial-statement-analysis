from __future__ import annotations

import unittest

from src.data.sec_timestamps import normalize_sec_acceptance_timestamp


class SecAcceptanceTimestampTests(unittest.TestCase):
    def test_naive_winter_and_summer_values_use_new_york_dst(self) -> None:
        self.assertEqual(
            normalize_sec_acceptance_timestamp("2020-03-01 21:00:00"),
            "2020-03-02T02:00:00Z",
        )
        self.assertEqual(
            normalize_sec_acceptance_timestamp("2022-07-21 11:04:00"),
            "2022-07-21T15:04:00Z",
        )

    def test_compact_sec_value_uses_same_source_semantics(self) -> None:
        self.assertEqual(
            normalize_sec_acceptance_timestamp("20220721110400"),
            "2022-07-21T15:04:00Z",
        )

    def test_explicit_offsets_preserve_the_represented_instant(self) -> None:
        expected = "2022-07-21T15:04:00Z"
        self.assertEqual(
            normalize_sec_acceptance_timestamp("2022-07-21T15:04:00Z"), expected
        )
        self.assertEqual(
            normalize_sec_acceptance_timestamp("2022-07-21T11:04:00-04:00"),
            expected,
        )

    def test_missing_is_preserved_and_invalid_input_fails_closed(self) -> None:
        self.assertEqual(normalize_sec_acceptance_timestamp(""), "")
        with self.assertRaises(ValueError):
            normalize_sec_acceptance_timestamp("not-a-timestamp")

    def test_ambiguous_dst_local_time_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            normalize_sec_acceptance_timestamp("2021-11-07 01:30:00")


if __name__ == "__main__":
    unittest.main()

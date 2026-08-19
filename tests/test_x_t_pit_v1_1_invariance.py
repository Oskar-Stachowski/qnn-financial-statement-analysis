from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from src.data.x_t_pit_v1_1 import (
    load_patch_config,
    materialize_fail_closed_correction,
    resolved_v1_1_config,
)


ROOT = Path(__file__).resolve().parents[1]
TRAIN_PROJECTION = ROOT / "data/interim/x_t_pit_v1_0_0_train_access_projection.csv"
TRAIN_SOURCE_CANDIDATE = (
    ROOT / "data/interim/x_t_pit_v1_1_0_train_source_rebuild_candidate.csv"
)
FROZEN_MIXED_SOURCE_BUILD = ROOT / "data/processed/x_t_pit_v1_1_0_train.csv"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def membership_sha256(path: Path) -> tuple[int, str]:
    identifiers: list[str] = []
    for frame in pd.read_csv(
        path,
        usecols=["research_universe_company_year_id", "feature_year"],
        dtype=str,
        chunksize=5_000,
    ):
        years = pd.to_numeric(frame["feature_year"], errors="raise")
        if not years.between(2011, 2020).all():
            raise AssertionError("Counterfactual input is not physically train-only")
        identifiers.extend(frame["research_universe_company_year_id"].astype(str))
    if len(identifiers) != len(set(identifiers)):
        raise AssertionError("Counterfactual membership contains duplicates")
    payload = "".join(f"{value}\n" for value in sorted(identifiers)).encode("utf-8")
    return len(identifiers), hashlib.sha256(payload).hexdigest()


class XtPitV11MixedPeriodInvarianceTests(unittest.TestCase):
    def test_frozen_mixed_source_build_equals_train_only_replay(self) -> None:
        """Replay only train artifacts; never reopen the mixed-period raw sources."""

        config = resolved_v1_1_config(load_patch_config())
        self.assertEqual(
            membership_sha256(TRAIN_PROJECTION),
            membership_sha256(TRAIN_SOURCE_CANDIDATE),
            "Physically separated train inputs are not membership-aligned",
        )
        with tempfile.TemporaryDirectory(prefix="x_t_train_only_invariance_") as directory:
            replay = Path(directory) / "x_t_pit_v1_1_0_train_replay.csv"
            materialize_fail_closed_correction(
                TRAIN_PROJECTION,
                TRAIN_SOURCE_CANDIDATE,
                replay,
                config,
            )
            self.assertEqual(
                file_sha256(replay),
                file_sha256(FROZEN_MIXED_SOURCE_BUILD),
                "Values, statuses or provenance differ in the train-only replay",
            )
            self.assertEqual(
                membership_sha256(replay),
                membership_sha256(FROZEN_MIXED_SOURCE_BUILD),
                "Train membership differs in the counterfactual replay",
            )


if __name__ == "__main__":
    unittest.main()

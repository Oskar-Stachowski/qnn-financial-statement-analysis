from pathlib import Path
import unittest

from src.modeling.verify_post_coarse_results_freeze import (
    verify_post_coarse_results_freeze,
)


ROOT = Path(__file__).resolve().parents[1]


class PostCoarseResultsFreezeTest(unittest.TestCase):
    def test_compact_result_freeze_is_complete_and_hash_exact(self) -> None:
        result = verify_post_coarse_results_freeze(
            ROOT / "configs/post_coarse_v1_3_0_results_freeze_manifest.yaml"
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["qnn_confirmation_fold_fits"], 36)
        self.assertEqual(result["bootstrap_valid_replicates"], 2_000)
        self.assertEqual(result["report_tables"], 8)
        self.assertIs(result["protected_feature_years_opened"], False)


if __name__ == "__main__":
    unittest.main()

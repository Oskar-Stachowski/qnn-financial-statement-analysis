from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import pandas as pd

from src.data.research_universe_target_application import (
    BASE_DIR,
    assemble_application_artifact,
    load_application_config,
    load_eligible_universe,
    verify_frozen_inputs,
)


def load_input_preparation_module():
    path = BASE_DIR / "src/data/25_prepare_research_universe_target_inputs.py"
    spec = importlib.util.spec_from_file_location("target_input_preparation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ResearchUniverseTargetApplicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_application_config()

    def test_application_uses_exact_frozen_component_versions(self) -> None:
        application = self.config["application"]
        self.assertEqual(application["universe_version"], "1.1.0")
        self.assertEqual(application["target_version"], "1.0.0")
        self.assertTrue(application["eligible_membership_only"])
        self.assertTrue(application["preserve_unavailable_target_rows"])
        self.assertFalse(application["map_unavailable_to_zero"])
        self.assertFalse(application["models_used"])
        self.assertFalse(application["x_t_built"])

    def test_frozen_input_hashes_remain_valid(self) -> None:
        hashes = verify_frozen_inputs(self.config)
        self.assertEqual(
            hashes["universe_artifact_sha256"],
            "a449c8145d1f46f954f12b1dfc079bb0b367c4f7f5edf3332a983ad7c1fb8182",
        )
        self.assertEqual(
            hashes["target_artifact_sha256"],
            "473aa403dfd15822a15ce985f7698efe4a4e3a66bcf30b7634f0ca646805e0ff",
        )

    def test_exactly_64901_eligible_rows_are_loaded(self) -> None:
        eligible = load_eligible_universe(self.config)
        self.assertEqual(len(eligible), 64_901)
        self.assertTrue(eligible["membership_status"].eq("eligible").all())
        self.assertFalse(eligible.duplicated(["cik10", "feature_year"]).any())

    def test_companyfacts_projection_keeps_only_frozen_required_tags(self) -> None:
        module = load_input_preparation_module()
        payload = {
            "cik": 1,
            "entityName": "Example",
            "facts": {
                "us-gaap": {
                    "Assets": {"units": {"USD": []}},
                    "InventoryNet": {"units": {"USD": []}},
                },
                "dei": {"EntityRegistrantName": {}},
            },
        }
        projected = module.projected_companyfacts(payload, {"Assets"})
        self.assertEqual(set(projected["facts"]), {"us-gaap"})
        self.assertEqual(set(projected["facts"]["us-gaap"]), {"Assets"})

    def test_universe_anchor_mismatch_is_not_computable_and_never_zero(self) -> None:
        eligible = load_eligible_universe(self.config).head(1).copy()
        row = eligible.iloc[0]
        frozen = pd.DataFrame(
            [
                {
                    "cik10": row["cik10"],
                    "feature_year": int(row["feature_year"]),
                    "anchor_t_accn": "0000000000-00-000000",
                    "target_status": "available",
                    "D1_roa": 0,
                    "D2_ocf_assets": 0,
                    "D3_current_ratio": 0,
                    "D4_liabilities_assets": 0,
                    "D5_revenues": 0,
                    "deterioration_score_1y": 0,
                    "target_candidate_v2": 0,
                }
            ]
        )
        result = assemble_application_artifact(
            eligible, frozen, pd.DataFrame(columns=frozen.columns), self.config
        )
        self.assertEqual(result.loc[0, "target_status"], "not_computable")
        self.assertEqual(
            result.loc[0, "target_application_reason"],
            "universe_anchor_target_anchor_mismatch",
        )
        self.assertTrue(pd.isna(result.loc[0, "target_candidate_v2_pit_b"]))
        self.assertTrue(pd.isna(result.loc[0, "deterioration_score_1y"]))


if __name__ == "__main__":
    unittest.main()

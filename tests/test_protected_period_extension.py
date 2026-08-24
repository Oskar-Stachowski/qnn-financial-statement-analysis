from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
import yaml

from src.modeling import protected_period_extension as protected


ROOT = Path(__file__).resolve().parents[1]


class ProtectedPeriodExtensionTests(unittest.TestCase):
    def test_cli_has_only_named_actions_and_no_arbitrary_paths(self) -> None:
        parser = protected.build_parser()
        for action in protected.ACTIONS:
            parsed = parser.parse_args([action])
            self.assertEqual(parsed.action, action)
        with self.assertRaises(SystemExit):
            parser.parse_args(["run-spent", "--input", "/tmp/escape.csv"])

    def test_byte_router_never_materializes_later_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "mixed.csv"
            output = root / "spent.csv"
            source.write_bytes(
                b"id,cik10,feature_year,payload\n"
                b"a,0000000001,2020,TRAIN\n"
                b"b,0000000001,2021,SPENT\n"
                b"c,0000000001,2022,SPENT_2\n"
                b"d,0000000001,2023,SEALED_2023\n"
                b"e,0000000001,2024,SEALED_2024\n"
            )
            count = protected.route_csv_through_year(
                source,
                output,
                year_field_index=2,
                expected_year_field=b"feature_year",
                maximum_feature_year=2022,
            )
            payload = output.read_bytes()
        self.assertEqual(count, 3)
        self.assertIn(b"SPENT_2", payload)
        self.assertNotIn(b"SEALED", payload)

    def test_metric_and_cluster_bootstrap_are_deterministic(self) -> None:
        frame = pd.DataFrame(
            {
                "economic_group_id": ["a", "a", "b", "b", "c", "c", "d", "d"],
                "target_label": [0, 1, 0, 1, 0, 1, 0, 1],
                "calibrated_probability": [0.1, 0.8, 0.2, 0.7, 0.3, 0.9, 0.4, 0.6],
                "predicted_label": [0, 1, 0, 1, 0, 1, 0, 1],
            }
        )
        first = protected._cluster_bootstrap(frame, replicates=100, seed=20260818)
        second = protected._cluster_bootstrap(frame, replicates=100, seed=20260818)
        self.assertEqual(first, second)
        self.assertGreaterEqual(first["valid_replicates"], 95)

    def test_contract_freezes_full_holdout_roster_and_schedule(self) -> None:
        contract = yaml.safe_load(
            (ROOT / "configs/protected_period_execution_contract_v1_0_0.yaml").read_text()
        )
        self.assertEqual(contract["terminal_variant"], "GATED_FULL_HOLDOUT")
        self.assertEqual(contract["roster"]["representatives"], 9)
        self.assertFalse(
            contract["refit_schedule"]["prediction_2024"]["label_2023_may_enter_training"]
        )
        self.assertFalse(contract["sealed_modes"]["feature_application"]["target_columns_read_allowed"])

    def test_terminal_one_shot_state_cannot_be_reopened(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "one_shot_state.json"
            authority = {"contract_sha256": "a" * 64}
            state = protected._execution_state(
                state_path,
                "synthetic_one_shot",
                authority,
            )
            protected._finish_execution_state(
                state_path,
                state,
                "FAILED",
                "b" * 64,
            )
            with self.assertRaises(protected.ProtectedExtensionError):
                protected._execution_state(
                    state_path,
                    "synthetic_one_shot",
                    authority,
                )

    def test_access_scopes_are_named_disjoint_and_fail_closed(self) -> None:
        manifest = yaml.safe_load(
            (ROOT / "configs/protected_period_access_manifest_v1_0_0.yaml").read_text()
        )
        scopes = manifest["scopes"]
        self.assertEqual(
            set(scopes),
            {
                "spent_gate_verifier_scope",
                "spent_post_gate_execution_scope",
                "spent_post_execution_freeze_scope",
            },
        )
        ids = [item["id"] for item in scopes.values()]
        self.assertEqual(len(ids), len(set(ids)))
        for item in scopes.values():
            self.assertEqual(
                protected.scope_sha256(item), item["definition_sha256"]
            )
        self.assertIn(
            "deserialize_feature_year_2023_or_2024",
            scopes["spent_post_gate_execution_scope"]["definition"]["forbidden"],
        )


if __name__ == "__main__":
    unittest.main()

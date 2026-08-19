"""Produce a compact, versioned audit of a full synthetic production run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from src.modeling.model_execution_contract import canonical_candidate_index, file_sha256
from src.modeling.production_runner import (
    ProductionExperimentRunner,
    SyntheticFoldExecutor,
    atomic_write_json,
    synthetic_dataset,
    synthetic_expectations,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sample = synthetic_dataset(4)
    expectations = synthetic_expectations(sample)
    with tempfile.TemporaryDirectory(prefix="production_runner_synthetic_audit_") as directory:
        artifact_root = Path(directory)
        runner = ProductionExperimentRunner(
            output_dir=artifact_root, executor=SyntheticFoldExecutor()
        )
        ranking = runner.run(sample, expectations=expectations)
        refinement = json.loads(
            (artifact_root / "refinement_activation.json").read_text()
        )
        confirmation = json.loads(
            (artifact_root / "confirmation_selection.json").read_text()
        )
        key_artifacts = [
            "refinement_activation.json",
            "confirmation_selection.json",
            "qnn_selected_ansatz.json",
            "canonical_candidate_result_table.json",
            "final_family_roster.json",
            "qnn_feasibility_and_executable_identity.json",
            "secondary_analysis_execution_plan.json",
            "final_ranking_manifest.json",
            "run_manifest.json",
        ]
        report = {
            "schema_version": 1,
            "id": "synthetic_production_e2e_v1_0_0",
            "status": "PASS",
            "synthetic_only": True,
            "project_data_opened": False,
            "project_model_training_performed": False,
            "protected_feature_years_opened": False,
            "sample": {
                "rows": len(sample),
                "feature_years": [2011, 2020],
                "membership_sha256": expectations.membership_sha256,
            },
            "folds": list(expectations.folds),
            "canonical_candidate_positions": len(
                canonical_candidate_index(runner.contract, runner.registry)
            ),
            "refinement_families_activated": len(refinement["activations"]),
            "classical_mlp_confirmation_slots": len(
                confirmation["classical_mlp"]
            ),
            "qnn_confirmation_slots": len(confirmation["qnn"]),
            "per_fold_result_manifests": len(
                list(artifact_root.glob("candidate_results/**/result_manifest.json"))
            ),
            "family_representatives": len(ranking["family_ranking"]),
            "calibration_threshold_pairs": len(
                ranking["calibration_and_threshold"]
            ),
            "key_artifact_sha256": {
                path: file_sha256(artifact_root / path) for path in key_artifacts
            },
        }
    atomic_write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

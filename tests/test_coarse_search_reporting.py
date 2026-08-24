from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

BUNDLE_ROOT = Path(__file__).resolve().parents[1]
if str(BUNDLE_ROOT) not in sys.path:
    sys.path.insert(0, str(BUNDLE_ROOT))

from src.modeling.coarse_search_reporting import (
    AmbiguousCoarseSearchSource,
    CoarseSearchArtifactNotFound,
    CoarseSearchIntegrityError,
    build_coarse_search_report,
    select_canonical_manifest,
)


FAMILIES = (
    "dummy_prior",
    "fixed_l2_logistic",
    "elastic_net_logistic",
    "rbf_svm",
    "hist_gradient_boosting",
    "xgboost",
    "random_forest",
    "pytorch_mlp",
)
BLOCKS = ("L", "L+D", "L+D+R")
YEARS = (2015, 2016, 2017, 2018, 2019, 2020)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "configs").mkdir(parents=True)
    (root / "src/modeling").mkdir(parents=True)
    contract = root / "configs/model_execution_contract_fixture.yaml"
    registry = root / "configs/model_stage_candidates_fixture.json"
    contract.write_text("schema_version: 1\n", encoding="utf-8")
    registry.write_text('{"schema_version": 1}\n', encoding="utf-8")
    (root / "configs/production_experiment_runner_v1_0_0.yaml").write_text(
        "schema_version: 1\n"
        "authority:\n"
        "  execution_contract:\n"
        "    path: configs/model_execution_contract_fixture.yaml\n"
        f"    sha256: {_sha256(contract)}\n"
        "  candidate_registry:\n"
        "    path: configs/model_stage_candidates_fixture.json\n"
        f"    sha256: {_sha256(registry)}\n",
        encoding="utf-8",
    )
    (root / "src/modeling/production_runner.py").write_text(
        '"""fixture marker only"""\n', encoding="utf-8"
    )
    return root


def _report(family: str, block: str, ordinal: int, quality_offset: float = 0.0) -> dict:
    base_quality = {
        "dummy_prior": 0.17,
        "fixed_l2_logistic": 0.35,
        "elastic_net_logistic": 0.37,
        "rbf_svm": 0.39,
        "hist_gradient_boosting": 0.43,
        "xgboost": 0.46,
        "random_forest": 0.41,
        "pytorch_mlp": 0.44,
    }[family]
    block_bonus = {"BLOCK_AGNOSTIC": 0.0, "L": 0.0, "L+D": 0.008, "L+D+R": 0.014}[block]
    pr_auc = base_quality + block_bonus + quality_offset
    roc_auc = min(0.99, pr_auc + 0.32)
    per_fold = []
    fold_values = []
    for position, year in enumerate(YEARS):
        fold_pr = max(0.01, min(0.99, pr_auc + (position - 2.5) * 0.008))
        fold_values.append(fold_pr)
        per_fold.append(
            {
                "fold_id": f"fold_{year}",
                "validation_feature_year": year,
                "n": 1000 + position * 10,
                "positive_n": 180 - position * 5,
                "pr_auc": fold_pr,
                "roc_auc": min(0.99, fold_pr + 0.30),
                "runtime_seconds": 1.0 + ordinal + position / 10,
                "status": "COMPLETE",
            }
        )
    parameters = {"imbalance": "none", "fixture_parameter": ordinal}
    return {
        "family": family,
        "configuration_id": f"fixture__{family}__{ordinal:03d}",
        "feature_block": block,
        "parameters": parameters,
        "training_seed": 20260818,
        "status": "COMPLETE",
        "failure_code": None,
        "convergence_status": "CONVERGED_NO_WARNINGS",
        "pooled_oof_n": sum(item["n"] for item in per_fold),
        "pooled_oof_positive_n": sum(item["positive_n"] for item in per_fold),
        "pooled_oof_pr_auc": pr_auc,
        "pooled_oof_roc_auc": roc_auc,
        "fold_pr_auc_mean": sum(fold_values) / len(fold_values),
        "fold_pr_auc_sample_sd": 0.02,
        "per_fold": per_fold,
        "runtime_seconds": 5.0 + ordinal * 3.0,
        "oof_key_count": sum(item["n"] for item in per_fold),
        "oof_unique_key_count": sum(item["n"] for item in per_fold),
        "oof_nonfinite_score_count": 0,
        "canonical_oof_predictions": None,
        "canonical_oof_predictions_sha256": None,
        "candidate_manifest": f"candidate_results/{family}/{ordinal}/candidate_manifest.json",
        "candidate_manifest_sha256": "0" * 64,
    }


def _manifest_payload(quality_offset: float = 0.0) -> dict:
    reports = []
    ordinal = 1
    reports.append(_report("dummy_prior", "BLOCK_AGNOSTIC", ordinal, quality_offset))
    ordinal += 1
    for family in FAMILIES[1:]:
        for block in BLOCKS:
            reports.append(_report(family, block, ordinal, quality_offset))
            ordinal += 1
    dummy = next(item for item in reports if item["family"] == "dummy_prior")
    fixed = max(
        (item for item in reports if item["family"] == "fixed_l2_logistic"),
        key=lambda item: item["pooled_oof_pr_auc"],
    )
    for item in reports:
        item["delta_pr_auc_vs_dummy"] = (
            item["pooled_oof_pr_auc"] - dummy["pooled_oof_pr_auc"]
        )
        item["delta_pr_auc_vs_fixed_l2"] = (
            item["pooled_oof_pr_auc"] - fixed["pooled_oof_pr_auc"]
        )
    return {
        "schema_version": 1,
        "status": "COMPLETE",
        "mode": "classical_mlp_coarse_search",
        "source_kind": "frozen_project_train",
        "executed_families": list(FAMILIES),
        "executed_candidate_positions": len(reports),
        "complete_candidate_positions": len(reports),
        "technically_invalid_candidate_positions": 0,
        "training_seed": 20260818,
        "runtime_seconds": 1234.5,
        "candidate_results": reports,
        "refinement_qualified_families": [
            {"family": "xgboost", "feature_block": "L+D+R"},
            {"family": "pytorch_mlp", "feature_block": "L+D+R"},
        ],
        "model_selection_performed": False,
        "refinement_performed": False,
        "qnn_performed": False,
        "calibration_or_threshold_performed": False,
        "robustness_or_interpretability_performed": False,
        "external_validation_or_test_opened": False,
        "protected_feature_years_opened": False,
    }


def _write_run(root: Path, run_id: str, payload: dict) -> Path:
    payload = dict(payload)
    payload["runner_config_sha256"] = _sha256(
        root / "configs/production_experiment_runner_v1_0_0.yaml"
    )
    payload["contract_sha256"] = _sha256(
        root / "configs/model_execution_contract_fixture.yaml"
    )
    payload["candidate_registry_sha256"] = _sha256(
        root / "configs/model_stage_candidates_fixture.json"
    )
    run_dir = root / "data/model_runs" / run_id
    run_dir.mkdir(parents=True)
    manifest = run_dir / "classical_mlp_coarse_search_manifest.json"
    manifest.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "COMPLETE",
                "mode": "classical_mlp_coarse_search",
                "classical_mlp_coarse_search_manifest_sha256": _sha256(manifest),
                "model_fit_performed": True,
                "protected_feature_years_opened": False,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


class CoarseSearchReportingTests(unittest.TestCase):
    def test_build_report_generates_requested_outputs(self) -> None:
        # The compact fixture intentionally contains one candidate per
        # family/block, not the full frozen coarse registry.
        import src.modeling.coarse_search_reporting as reporting

        fixture_expected_positions = 1 + (len(FAMILIES) - 1) * len(BLOCKS)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        with mock.patch.object(
            reporting,
            "_expected_coarse_positions_from_frozen_registry",
            return_value=fixture_expected_positions,
        ):
            root = _make_root(Path(temporary.name))
            _write_run(root, "coarse_fixture", _manifest_payload())
            report = build_coarse_search_report(
                project_root=root,
                output_dir=root / "reports/coarse_search_thesis",
                verify_oof_hashes=False,
            )

        self.assertIs(report.source.run_manifest_verified, True)
        self.assertEqual(len(report.tables["best_by_family"]), len(FAMILIES))
        self.assertEqual(len(report.tables["top20"]), 20)
        self.assertEqual(
            set(report.tables["feature_blocks_overall"]["feature_block"]),
            set(BLOCKS),
        )
        self.assertEqual(set(report.tables["yearly_pr_auc"]["year"]), set(YEARS))
        self.assertTrue(
            report.tables["thesis_family_summary"]["Status"]
            .isin(
                {
                    "baseline",
                    "kandydat do refinementu",
                    "prowizoryczny lider rodziny",
                }
            )
            .all()
        )
        self.assertTrue(all(path.is_file() for path in report.figures.values()))
        self.assertTrue(report.analysis_manifest_path.is_file())
        analysis_manifest = json.loads(
            report.analysis_manifest_path.read_text(encoding="utf-8")
        )
        self.assertIs(analysis_manifest["model_fit_performed"], False)
        self.assertIs(analysis_manifest["protected_feature_years_opened"], False)
        self.assertIn("prowizoryczny lider", report.summary_markdown)
        self.assertIn("wynik nie jest finalny", report.summary_markdown)

    def test_smoke_mode_is_rejected_as_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _make_root(Path(directory))
            payload = _manifest_payload()
            payload["mode"] = "real_data_execution_smoke_not_model_selection"
            _write_run(root, "smoke", payload)
            with self.assertRaises(CoarseSearchArtifactNotFound):
                select_canonical_manifest(root)

    def test_distinct_verified_runs_are_not_selected_arbitrarily(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _make_root(Path(directory))
            _write_run(root, "run_a", _manifest_payload(quality_offset=0.0))
            _write_run(root, "run_b", _manifest_payload(quality_offset=0.001))
            with self.assertRaises(AmbiguousCoarseSearchSource):
                select_canonical_manifest(root)

    def test_duplicate_candidate_identity_fails_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _make_root(Path(directory))
            payload = _manifest_payload()
            payload["candidate_results"].append(dict(payload["candidate_results"][0]))
            payload["executed_candidate_positions"] += 1
            _write_run(root, "duplicates", payload)
            with self.assertRaisesRegex(
                CoarseSearchIntegrityError, "DUPLICATE_CANDIDATE_IDENTITY"
            ):
                build_coarse_search_report(
                    project_root=root,
                    output_dir=root / "reports/coarse_search_thesis",
                    verify_oof_hashes=False,
                )

    def test_reporting_code_contains_no_training_invocation(self) -> None:
        module_path = BUNDLE_ROOT / "src/modeling/coarse_search_reporting.py"
        module_text = module_path.read_text(encoding="utf-8")
        self.assertNotIn(".fit(", module_text)
        self.assertNotIn("run_classical_mlp_coarse_search(", module_text)
        self.assertNotIn("ProductionExperimentRunner(", module_text)

        notebook_path = (
            BUNDLE_ROOT / "notebooks/08_coarse_search_results_for_thesis.ipynb"
        )
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        code = "\n".join(
            "".join(cell.get("source", []))
            for cell in notebook.get("cells", [])
            if cell.get("cell_type") == "code"
        )
        self.assertNotIn(".fit(", code)
        self.assertNotIn("run_classical_mlp_coarse_search(", code)
        self.assertNotIn("ProductionExperimentRunner(", code)


if __name__ == "__main__":
    unittest.main()

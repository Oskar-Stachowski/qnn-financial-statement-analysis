from __future__ import annotations

import ast
import csv
import json
import math
from pathlib import Path

import pytest

from src.modeling.methodology_extension_reporting_v1_0_0 import (
    ROOT,
    generate_report,
)


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("methodology_extension") / "report"
    manifest = generate_report(output)
    assert manifest["status"] == "PASS"
    return output


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_reporting_module_has_no_model_fit_calls() -> None:
    source_path = ROOT / "src/modeling/methodology_extension_reporting_v1_0_0.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden = {"fit", "fit_transform", "train", "backward", "optimizer_step"}
    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert forbidden.isdisjoint(called)


def test_seed_stability_tables_cover_full_roster(generated: Path) -> None:
    summary = _rows(generated / "tables/01_seed_stability_summary.csv")
    detailed = _rows(generated / "tables/02_seed_stability_detailed.csv")
    assert len(summary) == 10
    assert len(detailed) == 31  # 7 stochastic rows x (3 seeds + ensemble) + 3 deterministic
    assert sum(row["stability_status"] == "DESCRIPTIVE_ONLY_N3" for row in summary) == 7
    assert sum(
        row["stability_status"] == "NOT_APPLICABLE_DETERMINISTIC_SINGLE_RUN"
        for row in summary
    ) == 3


def test_known_seed_and_ensemble_metrics_are_reproduced(generated: Path) -> None:
    detailed = _rows(generated / "tables/02_seed_stability_detailed.csv")
    xgb_seed = next(
        row
        for row in detailed
        if row["family"] == "xgboost" and row["training_seed"] == "20260818"
    )
    qnn_ensemble = next(
        row
        for row in detailed
        if row["family"] == "qnn" and row["record_type"] == "SCORE_AVERAGED_ENSEMBLE"
    )
    assert math.isclose(float(xgb_seed["pooled_oof_pr_auc"]), 0.41167748793642267, abs_tol=1e-12)
    assert math.isclose(float(qnn_ensemble["pooled_oof_pr_auc"]), 0.38394764812793286, abs_tol=1e-12)


def test_runtime_scope_and_qnn_ledger_are_reproduced(generated: Path) -> None:
    cost = _rows(generated / "tables/03_compute_cost_final_representatives.csv")
    stages = _rows(generated / "tables/05_compute_cost_program_stages.csv")
    qnn = next(row for row in cost if row["family"] == "qnn")
    assert 6200.0 < float(qnn["worker_runtime_seconds_median"]) < 6600.0
    qnn_total = next(
        row for row in stages if row["stage"] == "TOTAL_RECORDED_Q1_Q2_CONFIRMATION_PROGRAM"
    )
    assert math.isclose(float(qnn_total["worker_runtime_seconds"]), 165157.69857417035, abs_tol=1e-9)
    refinement = next(row for row in stages if row["stage"] == "POST_COARSE_REFINEMENT_SEED_20260818")
    confirmation = next(
        row for row in stages if row["stage"] == "CONFIRMATION_EXTRA_SEEDS_20260819_20260820"
    )
    assert int(refinement["candidate_configurations"]) == 36
    assert int(confirmation["candidate_configurations"]) == 60


def test_manifest_and_protected_boundary(generated: Path) -> None:
    manifest = json.loads((generated / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["project_model_fit_performed"] is False
    assert manifest["protected_feature_years_opened"] is False
    assert manifest["development_feature_years"] == list(range(2015, 2021))
    assert all("2021" not in row["metric_source"] for row in _rows(generated / "tables/02_seed_stability_detailed.csv"))


def test_figures_exist_in_png_and_svg(generated: Path) -> None:
    for stem in ("01_seed_stability_pr_auc", "02_pr_auc_vs_runtime"):
        assert (generated / "figures" / f"{stem}.png").stat().st_size > 10_000
        assert (generated / "figures" / f"{stem}.svg").stat().st_size > 5_000


def test_thesis_ready_outputs_exist(generated: Path) -> None:
    assert len(_rows(generated / "tables/09_seed_stability_thesis_compact.csv")) == 10
    assert len(_rows(generated / "tables/10_compute_cost_thesis_compact.csv")) == 10
    assert not (generated / "thesis_ready_text.md").exists()

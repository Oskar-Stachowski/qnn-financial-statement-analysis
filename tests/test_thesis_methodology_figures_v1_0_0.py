from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from src.modeling.thesis_methodology_figures_v1_0_0 import verify


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/thesis_methodology_figures_v1_0_0.yaml"
REPORT = ROOT / "reports/thesis_methodology_figures_v1_0_0"


def _rows(name: str) -> list[dict[str, str]]:
    with (REPORT / "tables" / name).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_config_is_reporting_only_and_safe() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    report = config["report"]
    assert report["status"] == "REPORTING_ONLY"
    assert report["protected_row_level_content_read"] is False
    assert report["model_fit_performed"] is False
    assert report["prediction_generation_performed"] is False


def test_manifest_declares_three_reproducible_figures() -> None:
    manifest = json.loads((REPORT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert manifest["figures"] == 3
    assert manifest["figure_formats"] == ["png", "svg"]
    assert manifest["protected_row_level_content_read"] is False
    assert manifest["model_fit_performed"] is False
    assert manifest["prediction_generation_performed"] is False
    paths = {item["path"] for item in manifest["output_files_excluding_manifest"]}
    for stem in (
        "01_pipeline_and_leakage_safeguards",
        "02_period_timeline",
        "03_sample_selection_waterfall",
    ):
        assert f"figures/{stem}.png" in paths
        assert f"figures/{stem}.svg" in paths


def test_waterfall_closes_on_frozen_supervised_sample() -> None:
    rows = _rows("03_sample_selection_waterfall.csv")
    assert [int(row["n_after_stage"]) for row in rows] == [47938, 19784, 19671, 19671]
    assert [int(row["delta_n"]) for row in rows] == [47938, -28154, -113, 19671]
    assert abs(float(rows[-1]["retention_vs_train_pct"]) - 41.03425257624431) < 1e-12


def test_timeline_keeps_period_roles_separate() -> None:
    rows = _rows("02_period_timeline.csv")
    assert [row["period_role"] for row in rows] == [
        "training_history",
        "development",
        "spent_development",
        "holdout",
    ]
    assert [(row["start_year"], row["end_year"]) for row in rows] == [
        ("2011", "2014"),
        ("2015", "2020"),
        ("2021", "2022"),
        ("2023", "2024"),
    ]
    assert "fully unseen" in rows[-1]["prohibited_claim"]


def test_pipeline_table_contains_core_leakage_barriers() -> None:
    rows = _rows("01_pipeline_stages_and_safeguards.csv")
    assert len(rows) == 8
    safeguards = " ".join(row["safeguard"] for row in rows)
    assert "target_available_at" in safeguards
    assert "fold-train" in safeguards
    assert "SHA-256" in safeguards
    assert "no-tune/no-reselection" in safeguards


def test_provenance_contains_no_row_level_data_path() -> None:
    rows = _rows("04_source_provenance.csv")
    paths = [row["source_path"] for row in rows]
    assert not any(path.startswith("data/processed/") for path in paths)
    assert not any("holdout_report" in path or "spent_report" in path for path in paths)
    assert all(row["protected_row_level_content"] == "False" for row in rows)


def test_committed_package_reproduces_bit_for_bit() -> None:
    manifest = verify(REPORT, CONFIG)
    assert manifest["status"] == "PASS"

"""Verify the secondary-development thesis report v1.0.0."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
from typing import Any

from src.modeling.secondary_analysis_schemas import ROOT, canonical_sha256, file_sha256
from src.modeling.secondary_development_thesis_reporting_v1_0_0 import (
    DEFAULT_CONFIG,
    DEFAULT_OUTPUT,
    verify_reporting_package,
)


EXPECTED_TABLE_ROWS = {
    "tables/01_execution_completeness.csv": 4,
    "tables/02_pca_matched_controls.csv": 3,
    "tables/03_xgboost_robustness.csv": 9,
    "tables/04_qnn_structural_robustness.csv": 5,
    "tables/05_variant_fold_metrics.csv": 84,
    "tables/06_common_permutation_importance.csv": 136,
    "tables/07_common_permutation_top5_by_family.csv": 40,
    "tables/08_detailed_feature_importance.csv": 102,
    "tables/09_qnn_encoded_sensitivity.csv": 4,
    "tables/10_qnn_pca_loadings.csv": 136,
}


class SecondaryThesisReportVerificationError(RuntimeError):
    """Raised when the generated thesis report changed or is incomplete."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SecondaryThesisReportVerificationError(message)


def _load_json(path: Path) -> dict[str, Any]:
    _require(path.is_file() and not path.is_symlink(), f"Missing JSON: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(payload, dict), f"Expected JSON object: {path}")
    return payload


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise SecondaryThesisReportVerificationError(
            result.stderr.strip() or "Generated-report Git gate failed."
        )
    return result.stdout.strip()


def verify_secondary_development_thesis_report_v1_0_0(
    report_dir: Path = DEFAULT_OUTPUT,
    *,
    require_committed_package: bool = True,
    require_committed_output: bool = False,
) -> dict[str, Any]:
    package = verify_reporting_package(
        DEFAULT_CONFIG, require_committed=require_committed_package
    )
    report_dir = report_dir.resolve()
    _require(report_dir == DEFAULT_OUTPUT.resolve(), "Only canonical report output is valid.")
    _require(report_dir.is_dir() and not report_dir.is_symlink(), "Report root missing.")
    manifest_path = report_dir / "analysis_manifest.json"
    manifest = _load_json(manifest_path)
    _require(
        manifest.get("id") == "secondary_development_thesis_report_v1_0_0"
        and manifest.get("status") == "COMPLETE",
        "Unexpected report identity/status.",
    )
    _require(
        manifest.get("task_results") == 96
        and manifest.get("prediction_artifacts_read") == 84,
        "Report source counts changed.",
    )
    for field in (
        "primary_selection_changed",
        "project_model_fit_performed",
        "protected_feature_years_opened",
    ):
        _require(manifest.get(field) is False, f"Unsafe report flag: {field}")
    _require(manifest.get("descriptive_deltas_only") is True, "Deltas are not descriptive.")

    entries = manifest.get("generated_files") or []
    _require(isinstance(entries, list) and len(entries) == 23, "Generated file count changed.")
    entry_paths = [str(entry["path"]) for entry in entries]
    _require(len(entry_paths) == len(set(entry_paths)), "Duplicate generated file entry.")
    for entry in entries:
        path = (report_dir / str(entry["path"])).resolve()
        _require(path.is_relative_to(report_dir), f"Generated path escaped report: {path}")
        _require(path.is_file() and not path.is_symlink(), f"Missing generated file: {path}")
        _require(path.stat().st_size == int(entry["bytes"]), f"Size mismatch: {path}")
        _require(file_sha256(path) == entry["sha256"], f"SHA-256 mismatch: {path}")
    _require(
        canonical_sha256(entries) == manifest["generated_files_sha256"],
        "Generated inventory hash changed.",
    )
    actual_files = sorted(
        str(path.relative_to(report_dir))
        for path in report_dir.rglob("*")
        if path.is_file()
    )
    _require(
        actual_files == sorted([*entry_paths, "analysis_manifest.json"]),
        "Report has missing or extra files.",
    )

    table_paths = list(manifest.get("generated_tables") or [])
    figure_paths = list(manifest.get("generated_figures") or [])
    _require(table_paths == list(EXPECTED_TABLE_ROWS), "Table inventory changed.")
    _require(len(figure_paths) == 12, "Figure inventory changed.")
    _require(
        sum(path.endswith(".png") for path in figure_paths) == 6
        and sum(path.endswith(".svg") for path in figure_paths) == 6,
        "Figure format inventory changed.",
    )
    for relative, expected_rows in EXPECTED_TABLE_ROWS.items():
        with (report_dir / relative).open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        _require(len(rows) == expected_rows, f"CSV row count changed: {relative}")
    summary = (report_dir / "summary.md").read_text(encoding="utf-8")
    for required_text in (
        "96/96",
        "development-only",
        "nie wspierają twierdzenia o przewadze kwantowej",
        "Lata 2021–2024 pozostają zamknięte",
    ):
        _require(required_text in summary, f"Summary boundary missing: {required_text}")

    output_git_index_sha256 = "NOT_REQUIRED_FOR_READ_ONLY_VERIFY"
    if require_committed_output:
        relative_paths = [
            str((report_dir / relative).relative_to(ROOT)) for relative in actual_files
        ]
        for relative in relative_paths:
            _git("ls-files", "--error-unmatch", "--", relative)
        dirty = _git("status", "--porcelain", "--", *relative_paths)
        _require(not dirty, "Generated report is uncommitted or modified:\n" + dirty)
        rows = _git("ls-files", "-s", "--", *relative_paths).splitlines()
        _require(len(rows) == len(relative_paths), "Generated Git cardinality mismatch.")
        output_git_index_sha256 = canonical_sha256(sorted(rows))
    return {
        "schema_version": 1,
        "status": "PASS",
        "verdict": "SECONDARY_DEVELOPMENT_THESIS_REPORT_V1_0_0_PASS",
        "verified_files": len(actual_files),
        "verified_tables": len(table_paths),
        "verified_figure_files": len(figure_paths),
        "output_git_index_sha256": output_git_index_sha256,
        "reporting_package_git_index_sha256": package[
            "package_git_index_sha256"
        ],
        "primary_selection_changed": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--package-only", action="store_true")
    parser.add_argument("--require-committed-output", action="store_true")
    args = parser.parse_args()
    if args.package_only:
        result = verify_reporting_package(DEFAULT_CONFIG, require_committed=True)
    else:
        result = verify_secondary_development_thesis_report_v1_0_0(
            args.report_dir,
            require_committed_package=True,
            require_committed_output=args.require_committed_output,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""Build the byte-level inventory for the secondary v1.1.7 result freeze."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.modeling.production_runner import atomic_write_json
from src.modeling.secondary_analysis_schemas import ROOT, canonical_sha256, file_sha256


EXECUTION_ROOT = ROOT / "data/model_runs/secondary_development_v1_1_6"
REPORT_ROOT = ROOT / "data/model_runs/secondary_development_v1_1_7"
DEFAULT_OUTPUT = (
    ROOT / "reports/secondary_development_v1_1_7/artifact_inventory.json"
)
ROOTS = (
    ("secondary_development_execution_v1_1_6", EXECUTION_ROOT),
    ("secondary_development_report_v1_1_7", REPORT_ROOT),
)


class SecondaryDevelopmentInventoryError(RuntimeError):
    """Raised when a result-inventory source is unsafe or incomplete."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SecondaryDevelopmentInventoryError(message)


def collect_inventory() -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    roots: list[dict[str, Any]] = []
    for root_id, root in ROOTS:
        _require(root.is_dir() and not root.is_symlink(), f"Missing inventory root: {root}")
        root_files = sorted(path for path in root.rglob("*") if path.is_file())
        _require(root_files, f"Inventory root is empty: {root}")
        root_rows: list[dict[str, Any]] = []
        for path in root_files:
            _require(not path.is_symlink(), f"Symlink is forbidden in result inventory: {path}")
            row = {
                "path": str(path.relative_to(ROOT)),
                "bytes": int(path.stat().st_size),
                "sha256": file_sha256(path),
            }
            files.append(row)
            root_rows.append(row)
        roots.append(
            {
                "id": root_id,
                "path": str(root.relative_to(ROOT)),
                "file_count": len(root_rows),
                "logical_bytes": sum(int(row["bytes"]) for row in root_rows),
                "files_sha256": canonical_sha256(root_rows),
            }
        )
    _require(len({str(row["path"]) for row in files}) == len(files), "Duplicate inventory path.")
    return {
        "schema_version": 1,
        "id": "secondary_development_results_v1_1_7_artifact_inventory",
        "status": "COMPLETE",
        "roots": roots,
        "file_count": len(files),
        "logical_bytes": sum(int(row["bytes"]) for row in files),
        "files_sha256": canonical_sha256(files),
        "files": files,
        "project_data_deserialized": False,
        "project_model_fit_performed": False,
        "protected_feature_years_opened": False,
    }


def write_inventory(output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    output_path = output_path.resolve()
    _require(output_path == DEFAULT_OUTPUT.resolve(), "Only canonical inventory output may be written.")
    inventory = collect_inventory()
    atomic_write_json(output_path, inventory)
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    inventory = write_inventory(args.output)
    print(
        json.dumps(
            {
                key: inventory[key]
                for key in (
                    "status",
                    "file_count",
                    "logical_bytes",
                    "files_sha256",
                    "protected_feature_years_opened",
                )
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

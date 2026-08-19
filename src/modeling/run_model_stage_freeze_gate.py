"""Run the model-stage technical freeze gate without project-data access.

The command writes the JSON report to stdout.  It executes notebook code in a
fresh namespace, runs synthetic-only smoke scripts in pinned interpreters, and
runs repository policy tests.  It deliberately has no project data loader.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_json_command(command: list[str], root: Path, environment: dict[str, str]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    completed = subprocess.run(
        command,
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    parsed: dict[str, Any] | None = None
    if completed.returncode == 0:
        parsed = json.loads(completed.stdout)
    audit = {
        "command": command,
        "returncode": completed.returncode,
        "stderr": completed.stderr.strip(),
    }
    return parsed, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--classical-python", required=True)
    parser.add_argument("--qnn-python", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    notebook_path = root / "notebooks/05_model_stage_preregistration.ipynb"
    candidates_path = root / "configs/model_stage_candidates_v1.json"
    notebook = json.loads(notebook_path.read_text())
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    clean_outputs = all(cell.get("execution_count") is None and cell.get("outputs", []) == [] for cell in code_cells)
    code_text = "\n".join("".join(cell["source"]) for cell in code_cells)
    forbidden_tokens = (
        "read_csv(", "read_parquet(", "data/processed/", "data/interim/",
        "target_candidate_v2_pit_b.csv", "x_t_pit_v1_raw.csv",
    )
    forbidden_hits = [token for token in forbidden_tokens if token in code_text]
    assertion_count = sum(
        isinstance(node, ast.Assert)
        for cell in code_cells
        for node in ast.walk(ast.parse("".join(cell["source"])))
    )

    namespace: dict[str, Any] = {"__name__": "__main__"}
    notebook_stdout = io.StringIO()
    notebook_error: str | None = None
    try:
        with contextlib.redirect_stdout(notebook_stdout):
            for position, cell in enumerate(notebook["cells"]):
                if cell["cell_type"] == "code":
                    exec(compile("".join(cell["source"]), f"notebook_cell_{position}", "exec"), namespace)
    except Exception as error:  # pragma: no cover - report path
        notebook_error = f"{type(error).__name__}: {error}"

    environment = os.environ.copy()
    environment.update({
        "PYTHONPATH": str(root),
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "MPLCONFIGDIR": "/private/tmp/model_stage_mplconfig",
        "XDG_CACHE_HOME": "/private/tmp/model_stage_xdg_cache",
    })
    Path(environment["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)
    Path(environment["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)
    smoke_script = str(root / "src/modeling/model_stage_smoke.py")
    classical_result, classical_audit = run_json_command(
        [args.classical_python, smoke_script, "classical"], root, environment
    )
    qnn_result, qnn_audit = run_json_command(
        [args.qnn_python, smoke_script, "qnn"], root, environment
    )

    tests = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    candidate_registry = json.loads(candidates_path.read_text())
    checks = {
        "notebook_json_loaded": True,
        "notebook_outputs_clean": clean_outputs,
        "notebook_code_cells": len(code_cells),
        "notebook_assertions_executed": assertion_count,
        "notebook_execution_error": notebook_error,
        "notebook_declared_verdict": namespace.get("TECHNICAL_FREEZE_GATE_VERDICT"),
        "forbidden_project_data_loader_hits": forbidden_hits,
        "classical_synthetic_smoke_passed": classical_result is not None and classical_result.get("status") == "passed",
        "qnn_mlp_synthetic_smoke_passed": qnn_result is not None and qnn_result.get("status") == "passed",
        "repository_tests_passed": tests.returncode == 0,
        "external_validation_values_loaded": False,
        "test_values_loaded": False,
        "project_data_model_fit_performed": False,
    }
    ready = (
        clean_outputs
        and not forbidden_hits
        and notebook_error is None
        and namespace.get("TECHNICAL_FREEZE_GATE_VERDICT") == "MODEL STAGE READY TO FREEZE"
        and checks["classical_synthetic_smoke_passed"]
        and checks["qnn_mlp_synthetic_smoke_passed"]
        and checks["repository_tests_passed"]
    )
    files = [
        "notebooks/05_model_stage_preregistration.ipynb",
        "configs/model_stage_candidates_v1.json",
        "src/modeling/model_stage_preregistration.py",
        "src/modeling/model_stage_smoke.py",
        "src/modeling/run_model_stage_freeze_gate.py",
        "tests/test_model_stage_preregistration.py",
        "configs/target_candidate_v2_pit_b_freeze_manifest.yaml",
        "configs/research_universe_pit_freeze_manifest.yaml",
        "configs/x_t_pit_v1_freeze_manifest.yaml",
        "configs/supervised_ml_pipeline_v1.yaml",
        "configs/supervised_ml_pipeline_v1_freeze_manifest.yaml",
    ]
    report = {
        "report_schema_version": 1,
        "id": "model_stage_preregistration_technical_freeze_gate",
        "executed_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "scope": "specification_candidate_materialization_and_synthetic_smoke_only",
        "checks": checks,
        "notebook_stdout": notebook_stdout.getvalue().strip().splitlines(),
        "classical_smoke": classical_result,
        "classical_smoke_audit": classical_audit,
        "qnn_mlp_smoke": qnn_result,
        "qnn_mlp_smoke_audit": qnn_audit,
        "repository_tests": {
            "command": [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
            "returncode": tests.returncode,
            "stdout": tests.stdout.strip(),
            "stderr": tests.stderr.strip(),
        },
        "candidate_list_hashes": candidate_registry["list_hashes"],
        "pca_feature_order": candidate_registry["pca_feature_order"],
        "file_sha256": {relative: sha256(root / relative) for relative in files},
        "verdict": "MODEL STAGE READY TO FREEZE" if ready else "MODEL STAGE NOT READY TO FREEZE",
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()


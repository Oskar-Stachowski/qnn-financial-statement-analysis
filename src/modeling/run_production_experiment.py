"""CLI entry point for the contract-bound production experiment controller."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.modeling.production_runner import (
    ProductionExperimentRunner,
    SubprocessFoldExecutor,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("dry-run", "execute"))
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--classical-python", required=True, type=Path)
    parser.add_argument("--qnn-python", required=True, type=Path)
    args = parser.parse_args()

    executor = SubprocessFoldExecutor(
        root=Path(__file__).resolve().parents[2],
        classical_python=args.classical_python,
        qnn_python=args.qnn_python,
    )
    runner = ProductionExperimentRunner(output_dir=args.output_dir, executor=executor)
    sample, expectations = runner.load_frozen_project_sample()
    result = runner.run(sample, expectations=expectations, dry_run=args.mode == "dry-run")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

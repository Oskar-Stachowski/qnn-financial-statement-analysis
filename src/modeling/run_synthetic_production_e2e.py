"""Run the complete production orchestration against generated data only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.modeling.production_runner import (
    ProductionExperimentRunner,
    SyntheticFoldExecutor,
    synthetic_dataset,
    synthetic_expectations,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--rows-per-year", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    sample = synthetic_dataset(args.rows_per_year)
    runner = ProductionExperimentRunner(
        output_dir=args.output_dir,
        executor=SyntheticFoldExecutor(),
    )
    result = runner.run(
        sample,
        expectations=synthetic_expectations(sample),
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

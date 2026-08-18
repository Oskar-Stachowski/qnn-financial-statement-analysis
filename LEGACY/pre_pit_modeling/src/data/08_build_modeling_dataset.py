"""
Run the Commit 08 modeling dataset builder.

The reusable dataset-building logic lives in src/data/modeling_dataset.py.
This runner exists so the numbered SEC data pipeline can still be executed with:

    python src/data/08_build_modeling_dataset.py
"""

from __future__ import annotations

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.data.modeling_dataset import BASE_DIR, build_modeling_dataset


def main() -> None:
    result = build_modeling_dataset()
    print("Commit 08 modeling dataset built.")
    print(f"Source rows:        {result['source_rows']:,}")
    print(f"Feature-year rows:  {result['feature_year_rows']:,}")
    print(f"Modeling rows:      {result['modeling_rows']:,}")
    print(f"Excluded rows:      {result['excluded_rows']:,}")
    print(f"Feature years:      {result['feature_year_min']}-{result['feature_year_max']}")
    print(f"Source year max:    {result['source_year_max']}")
    for path in result["output_paths"]:
        print(f"Saved:              {path.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()

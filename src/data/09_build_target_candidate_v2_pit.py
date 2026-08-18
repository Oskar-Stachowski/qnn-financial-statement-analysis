"""Build and audit the point-in-time variant-B target candidate.

This stage does not train models and does not freeze the target.
"""

from __future__ import annotations

from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.data.target_candidate_v2_pit import BASE_DIR, build_target_candidate_v2_pit


def main() -> None:
    audit = build_target_candidate_v2_pit()
    overall = next(row for row in audit["coverage"] if row["split"] == "all")
    balance = next(row for row in audit["class_balance"] if row["split"] == "all")
    print("Point-in-time target_candidate_v2 variant B built (not frozen).")
    print(f"Candidate rows:       {audit['candidate_rows']:,}")
    print(f"Available targets:    {overall['available_target_n']:,}")
    print(f"Coverage:             {overall['target_coverage_all']:.2%}")
    print(f"Hard-exclude:         {overall['hard_exclude_n']:,}")
    print(f"Ambiguous:            {overall['ambiguous_n']:,}")
    print(f"Positive class:       {balance['positive_n']:,} ({balance['positive_rate']:.2%})")
    for path in audit["output_paths"]:
        print(f"Saved:                {path}")
    print(f"Saved:                data/reports/target_candidate_v2_pit_b_audit.json")
    print(f"Saved:                data/reports/target_candidate_v2_pit_b_audit.md")


if __name__ == "__main__":
    main()

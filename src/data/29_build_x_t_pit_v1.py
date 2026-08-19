"""Build the candidate raw point-in-time X_t v1 artifact."""

from __future__ import annotations

from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.data.x_t_pit import BASE_DIR, build_raw_x_t


def main() -> None:
    manifest = build_raw_x_t()
    print("Raw PIT X_t v1 built.")
    print(f"Rows:       {manifest['raw_artifact_rows']:,}")
    print(f"Columns:    {manifest['raw_artifact_columns']:,}")
    print(f"SHA-256:    {manifest['raw_artifact_sha256']}")
    print(f"Artifact:   {manifest['raw_artifact']}")
    print(f"Repository: {BASE_DIR}")


if __name__ == "__main__":
    main()

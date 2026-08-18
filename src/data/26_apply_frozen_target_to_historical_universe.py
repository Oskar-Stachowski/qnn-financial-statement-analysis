"""Apply frozen PIT-B v1.0.0 to eligible frozen-universe v1.1.0 rows.

By default this writes a working artifact used to identify missing primary
statement evidence. Set ``TARGET_APPLICATION_FINAL=1`` only after the evidence
download stage; the frozen input artifacts are never overwritten.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.data.research_universe_target_application import build_application_artifact


def main() -> None:
    final = os.environ.get("TARGET_APPLICATION_FINAL", "").strip() == "1"
    result = build_application_artifact(final=final)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

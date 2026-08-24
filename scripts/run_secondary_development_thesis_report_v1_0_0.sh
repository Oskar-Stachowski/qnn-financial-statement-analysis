#!/usr/bin/env bash
set -euo pipefail

QNN_REPORT_PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QNN_REPORT_MODE="${1:-}"
export MPLCONFIGDIR="/tmp/qnn_matplotlib_secondary_thesis_v1_0_0"
export XDG_CACHE_HOME="/tmp/qnn_cache_secondary_thesis_v1_0_0"
mkdir -p "$MPLCONFIGDIR"
mkdir -p "$XDG_CACHE_HOME"
cd "$QNN_REPORT_PROJECT_ROOT"

case "$QNN_REPORT_MODE" in
  verify-package)
    python -m src.modeling.verify_secondary_development_thesis_report_v1_0_0 \
      --package-only
    ;;
  generate)
    python -m src.modeling.secondary_development_thesis_reporting_v1_0_0 \
      --require-committed
    ;;
  verify-output)
    python -m src.modeling.verify_secondary_development_thesis_report_v1_0_0
    ;;
  verify-output-committed)
    python -m src.modeling.verify_secondary_development_thesis_report_v1_0_0 \
      --require-committed-output
    ;;
  *)
    printf 'Usage: %s {verify-package|generate|verify-output|verify-output-committed}\n' "$0" >&2
    exit 2
    ;;
esac

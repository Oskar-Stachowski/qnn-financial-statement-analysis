#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-status}"
shift || true

case "$MODE" in
  status|plan|smoke|preflight|pca-controls|interpretability|robustness-classical|robustness-qnn|report|all)
    exec python -m src.modeling.secondary_analysis_execution "$MODE" "$@"
    ;;
  verify)
    exec python -m src.modeling.verify_secondary_analysis_execution_package "$@"
    ;;
  *)
    echo "Nieznany tryb: $MODE" >&2
    echo "Dostępne: status, plan, smoke, verify, preflight, pca-controls, interpretability, robustness-classical, robustness-qnn, report, all" >&2
    exit 2
    ;;
esac

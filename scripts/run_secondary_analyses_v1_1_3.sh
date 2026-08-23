#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${1:-status}"
shift || true

case "$MODE" in
  verify)
    exec python -c 'import json; from src.modeling.verify_secondary_analysis_execution_v1_1_3 import verify_secondary_analysis_execution_v1_1_3; print(json.dumps(verify_secondary_analysis_execution_v1_1_3(require_committed=True), indent=2, sort_keys=True))' "$@"
    ;;
  status|plan|smoke|preflight|pca-controls|interpretability|robustness-classical|robustness-qnn|report|all)
    exec python -c 'from src.modeling.verify_secondary_analysis_execution_v1_1_3 import verify_secondary_analysis_execution_v1_1_3; verify_secondary_analysis_execution_v1_1_3(require_committed=True); from src.modeling.secondary_analysis_execution_v1_1_3 import main; main()' "$MODE" "$@"
    ;;
  *)
    echo "Nieznany tryb: $MODE" >&2
    echo "Dostępne: status, plan, smoke, verify, preflight, pca-controls, interpretability, robustness-classical, robustness-qnn, report, all" >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
set -euo pipefail

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-status}"
CONFIG="${SECONDARY_ANALYSIS_CONFIG:-$ROOT/configs/secondary_development_analyses_v1_0_0.yaml}"
OUTPUT_DIR="${SECONDARY_ANALYSIS_OUTPUT_DIR:-$ROOT/data/model_runs/secondary_development_v1_0_0}"
CLASSICAL_PYTHON="${CLASSICAL_PYTHON:-$ROOT/.venv-classical/bin/python}"

if [[ ! -x "$CLASSICAL_PYTHON" ]]; then
  echo "Nie znaleziono interpretera classical: $CLASSICAL_PYTHON" >&2
  exit 2
fi

case "$MODE" in
  status)
    "$CLASSICAL_PYTHON" -m src.modeling.secondary_analysis_runner status \
      --config "$CONFIG"
    ;;
  plan)
    "$CLASSICAL_PYTHON" -m src.modeling.secondary_analysis_runner plan \
      --config "$CONFIG" \
      --output-dir "$OUTPUT_DIR"
    ;;
  smoke)
    mkdir -p "$OUTPUT_DIR"
    "$CLASSICAL_PYTHON" -m src.modeling.secondary_analysis_smoke \
      --config "$CONFIG" \
      --output "$OUTPUT_DIR/secondary_analysis_synthetic_smoke.json"
    ;;
  verify)
    "$CLASSICAL_PYTHON" -m src.modeling.verify_secondary_analysis_package
    ;;
  execute|pca-controls|interpretability|robustness|all)
    echo "Tryb project-data execution nie jest dostępny w pre-execution package v1.0.0." >&2
    echo "Wymaga osobnej, jawnie wersjonowanej implementacji i commita po tym freeze." >&2
    exit 3
    ;;
  *)
    echo "Usage: bash scripts/run_secondary_analyses.sh {status|plan|smoke|verify}" >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
set -euo pipefail

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-plan}"
COARSE_DIR="${COARSE_DIR:-$ROOT/data/model_runs/classical_mlp_coarse_v1}"
OUTPUT_DIR="${POST_COARSE_OUTPUT_DIR:-$ROOT/data/model_runs/post_coarse_v1_3_0}"
REPORT_DIR="${POST_COARSE_REPORT_DIR:-$ROOT/reports/post_coarse_v1_3_0}"
CONFIG="${POST_COARSE_CONFIG:-$ROOT/configs/post_coarse_experiment_v1_0_2_parallel.yaml}"
CONTRACT="${POST_COARSE_CONTRACT:-$ROOT/configs/model_execution_contract_v1_2_1_lightning_scientific_patch.yaml}"

find_python() {
  local explicit="$1"
  shift
  if [[ -n "$explicit" ]]; then
    if [[ ! -x "$explicit" ]]; then
      echo "Interpreter is not executable: $explicit" >&2
      return 1
    fi
    printf '%s\n' "$explicit"
    return 0
  fi
  local candidate
  for candidate in "$@"; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

CLASSICAL_PYTHON="$(find_python "${CLASSICAL_PYTHON:-}" \
  "$ROOT/.venv-classical/bin/python" \
  "$ROOT/.venv_classical/bin/python" \
  "$ROOT/venv-classical/bin/python" \
  "$ROOT/environments/classical/.venv/bin/python" \
  || true)"

QNN_PYTHON="$(find_python "${QNN_PYTHON:-}" \
  "$ROOT/.venv-qnn-mlp/bin/python" \
  "$ROOT/.venv-qnn_mlp/bin/python" \
  "$ROOT/.venv-qnn/bin/python" \
  "$ROOT/.venv_qnn_mlp/bin/python" \
  "$ROOT/venv-qnn-mlp/bin/python" \
  "$ROOT/environments/qnn_mlp/.venv/bin/python" \
  || true)"

require_classical() {
  if [[ -z "$CLASSICAL_PYTHON" ]]; then
    echo "Nie znaleziono interpretera classical." >&2
    echo "Ustaw np.: export CLASSICAL_PYTHON=\"$ROOT/.venv-classical/bin/python\"" >&2
    exit 2
  fi
}

require_qnn() {
  if [[ -z "$QNN_PYTHON" ]]; then
    echo "Nie znaleziono interpretera qnn_mlp." >&2
    echo "Ustaw np.: export QNN_PYTHON=\"$ROOT/.venv-qnn-mlp/bin/python\"" >&2
    exit 2
  fi
}

require_interpreters() {
  require_classical
  require_qnn
}

mkdir -p "$OUTPUT_DIR" "$REPORT_DIR"

case "$MODE" in
  test)
    require_classical
    "$CLASSICAL_PYTHON" -m unittest tests.test_post_coarse_runner
    ;;
  smoke)
    require_qnn
    echo "[1/1] Synthetic QNN resource smoke..."
    "$QNN_PYTHON" -m src.modeling.qnn_resource_smoke \
      --contract "$CONTRACT" \
      --output "$OUTPUT_DIR/qnn_resource_smoke.json"
    ;;
  plan)
    require_classical
    "$CLASSICAL_PYTHON" -m src.modeling.post_coarse_runner plan \
      --config "$CONFIG" \
      --coarse-dir "$COARSE_DIR" \
      --output-dir "$OUTPUT_DIR"
    ;;
  refinement|qnn|confirmation|all)
    require_interpreters
    "$CLASSICAL_PYTHON" -m src.modeling.post_coarse_runner "$MODE" \
      --config "$CONFIG" \
      --coarse-dir "$COARSE_DIR" \
      --output-dir "$OUTPUT_DIR" \
      --classical-python "$CLASSICAL_PYTHON" \
      --qnn-python "$QNN_PYTHON"
    ;;
  inference)
    require_classical
    "$CLASSICAL_PYTHON" -m src.modeling.neural_comparison_inference \
      --config "$CONFIG" \
      --coarse-dir "$COARSE_DIR" \
      --output-dir "$OUTPUT_DIR" \
      --replicates 2000 \
      --seed 20260818
    ;;
  report)
    require_classical
    "$CLASSICAL_PYTHON" -m src.modeling.post_coarse_reporting \
      --output-dir "$OUTPUT_DIR" \
      --report-dir "$REPORT_DIR"
    ;;
  status)
    echo "Repo:       $ROOT"
    echo "Coarse:     $COARSE_DIR"
    echo "Output:     $OUTPUT_DIR"
    echo "Report:     $REPORT_DIR"
    echo "Classical:  ${CLASSICAL_PYTHON:-NOT FOUND}"
    echo "QNN/MLP:    ${QNN_PYTHON:-NOT FOUND}"
    for manifest in \
      post_coarse_plan.json \
      refinement_phase_manifest.json \
      qnn_phase_manifest.json \
      confirmation_phase_manifest.json \
      neural_comparison_clustered_bootstrap.json \
      run_manifest.json; do
      if [[ -f "$OUTPUT_DIR/$manifest" ]]; then
        echo "FOUND:      $manifest"
      else
        echo "MISSING:    $manifest"
      fi
    done
    ;;
  *)
    echo "Usage: bash scripts/run_post_coarse.sh {status|test|smoke|plan|refinement|qnn|confirmation|inference|all|report}" >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
set -euo pipefail

.venv-qnn-mlp/bin/python -m src.modeling.posthoc_exploratory_comparison_v1_0_0 generate
.venv-qnn-mlp/bin/python -m src.modeling.posthoc_exploratory_comparison_v1_0_0 verify

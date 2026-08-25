#!/usr/bin/env bash
set -euo pipefail

.venv-qnn-mlp/bin/python -m src.modeling.thesis_methodology_figures_v1_0_0 generate
.venv-qnn-mlp/bin/python -m src.modeling.thesis_methodology_figures_v1_0_0 verify

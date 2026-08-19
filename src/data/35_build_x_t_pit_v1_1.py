"""CLI entry point for the train-only X_t resolver correction v1.1.0."""

from __future__ import annotations

from src.data.x_t_pit_v1_1 import build_raw_x_t_train


if __name__ == "__main__":
    result = build_raw_x_t_train()
    print(result)

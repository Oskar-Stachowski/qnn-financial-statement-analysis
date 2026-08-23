# Secondary development execution v1.1.3 — robustness signal source

## Status

Status: **FROZEN EXECUTABLE AMENDMENT**

The committed v1.1.2 preflight successfully reached the train-only join and
then stopped before model fitting because the narrower interim target file does
not contain every row created by the historical target-application pipeline.
The mismatch was an input-source coverage issue, not a mismatch in the
supervised sample or a protected-period access.

The already frozen production target-application projection contains
`deterioration_score_1y` and D1–D5 for every one of the 19,671 supervised rows.
It is already the target input used by the production sample loader and is
pinned by SHA-256 in the production runner configuration.

Version 1.1.3 therefore reads the robustness signals from:

```text
data/processed/research_universe_pit_v1_1_0_target_pit_b_v1_2_0_train.csv
```

with SHA-256
`0f5d3bdefe13ed6ea6a1c6cdc94ae2c663f59175a7363dd8bffa26717069dd1b`.
It joins directly on the existing `research_universe_company_year_id` and no
longer deserializes the narrower interim target file for execution.

## Invariants

Before a task can run, the adapter verifies:

- the exact source SHA-256;
- unique company-year identity;
- feature years contained in 2011–2020;
- one-to-one year alignment with the frozen supervised sample;
- `available` target status for every supervised row;
- complete numeric score and D1–D5 values;
- binary D1–D5 signals;
- exact frozen sample and temporal-fold memberships.

The amendment changes no target value, sample member, fold, task identity,
preprocessing rule, hyperparameter, QNN structure, resource cap, failure rule,
or scientific methodology. The roster remains exactly 96 tasks.

## Commands

Use v1.1.3 for subsequent work:

```bash
bash scripts/run_secondary_analyses_v1_1_3.sh verify
bash scripts/run_secondary_analyses_v1_1_3.sh preflight
```

The v1.1.3 module is inert on import. The launcher invokes `main()` once, and
only that execution path activates the versioned adapter. Its synthetic smoke
helper restores inherited controller globals before returning, so test imports
cannot contaminate another frozen version in the same interpreter.

After preflight passes:

```bash
bash scripts/run_secondary_analyses_v1_1_3.sh pca-controls
bash scripts/run_secondary_analyses_v1_1_3.sh interpretability
bash scripts/run_secondary_analyses_v1_1_3.sh robustness-classical
bash scripts/run_secondary_analyses_v1_1_3.sh robustness-qnn
bash scripts/run_secondary_analyses_v1_1_3.sh report
```

The new default output root is
`data/model_runs/secondary_development_v1_1_3`. Earlier incomplete preflight
directories have different immutable identities and are not reused.

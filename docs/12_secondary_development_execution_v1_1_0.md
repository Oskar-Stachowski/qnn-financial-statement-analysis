# Secondary development execution v1.1.0

## Status

Status: **FROZEN EXECUTABLE PACKAGE**

This package implements the 96-task schedule frozen in v1.0.0. It is a
secondary development analysis only: results cannot change the primary
ranking, roster, hyperparameters, calibration, threshold, or selected QNN
ansatz. Feature years 2021–2024 remain sealed.

The v1.0.0 package is not edited. Version 1.1.0 references it and its freeze
manifest by exact SHA-256.

## Safety gates

Before the first project-data read, every real-data mode:

1. verifies the v1.0.0 and post-coarse result freezes;
2. verifies all pinned authority files and the exact train-only target file;
3. requires every v1.1.0 package file to be tracked, committed, and clean;
4. establishes an immutable output identity in a new empty directory;
5. accepts only feature years 2011–2020 and rejects 2021–2024;
6. reads no file under `data/raw` and never restores raw data automatically.

Workers receive numeric NPZ arrays only. They do not load project CSV files.
After a terminal task result is atomically durable, reproducible temporary
numeric arrays are deleted; checkpoints and audit JSON remain available for
resume and verification.

## Commands

Non-project-data controls:

```bash
bash scripts/run_secondary_analyses_v1_1.sh status
bash scripts/run_secondary_analyses_v1_1.sh plan --output-dir /tmp/secondary-plan
bash scripts/run_secondary_analyses_v1_1.sh smoke --output-dir /tmp/secondary-smoke
bash scripts/run_secondary_analyses_v1_1.sh verify
```

The plan and smoke commands should use a fresh temporary output directory. They
do not read project data or fit project models.

Real-data preflight, which reads only the exact train projections and fits no
model:

```bash
bash scripts/run_secondary_analyses_v1_1.sh preflight
```

Execution order:

```bash
bash scripts/run_secondary_analyses_v1_1.sh pca-controls
bash scripts/run_secondary_analyses_v1_1.sh interpretability
bash scripts/run_secondary_analyses_v1_1.sh robustness-classical
bash scripts/run_secondary_analyses_v1_1.sh robustness-qnn
bash scripts/run_secondary_analyses_v1_1.sh report
```

The convenience mode `all` runs those stages in the same order. Re-running a
stage reuses only exact terminal task identities; an identity mismatch fails
closed.

## Frozen roster

| Stage | Tasks |
|---|---:|
| PCA-matched fixed-L2 and MLP controls | 12 |
| Common grouped permutation methods | 8 |
| Detailed interpretation methods | 4 |
| Global XGBoost robustness fold fits | 48 |
| QNN structural robustness fold fits | 24 |
| **Total** | **96** |

PCA controls use the final QNN block, rows, fold-train preprocessing, PCA,
component scaler, clipping, and angle encoding. Their model hyperparameters
come from the frozen fixed-L2 and MLP representatives.

Classical robustness implements five pipeline variants and three alternative
targets on all six folds. QNN robustness implements identity entanglers, both
nonselected Q1 ansatzes, and the 4/6-qubit PCA swap without retuning.

## Interpretation implementation

Common permutation importance uses the original financial feature together
with its own missing indicator, 20 deterministic repetitions, and seed-averaged
raw OOF scores. The permutation unit is `economic_group_id`; the worker fails
closed if a validation fold does not have a unique row per economic group,
rather than silently inventing an ambiguous unequal-cluster permutation.

Detailed methods are:

- standardized coefficients, odds ratios, and sign stability for the frozen
  linear representative;
- interventional TreeSHAP with at most 512 canonical train-background and 500
  validation rows per fold for XGBoost;
- Integrated Gradients on the MLP logit, with the fold-train feature mean as
  baseline, 64 steps, and at most 200 rows per fold;
- QNN PCA loadings, explained variance, and encoded-input logit sensitivity on
  at most 100 rows per fold.

Exact MLP and QNN checkpoints are reused after checking their task identities.
Classical estimators are refitted with the exact frozen seed identity because
their fitted objects were not persisted.

## Output and failure behavior

The default root is `data/model_runs/secondary_development_v1_1_0`. Each frozen
task has one canonical task-result JSON. Model tasks additionally retain OOF
predictions and neural checkpoints. Phase manifests account for every planned
task as `COMPLETE`, `TECHNICALLY_INVALID`, `METHOD_FAILED`, or
`RESOURCE_LIMIT_REACHED`.

A failed method remains a reported result. It cannot be replaced, retuned, or
used to rerank the primary experiment. The final `report` mode succeeds only
after all 96 task identities are terminally accounted for and always declares
that the primary ranking is unchanged and protected years were not opened.

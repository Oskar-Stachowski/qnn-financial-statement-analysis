# Secondary development execution v1.1.4 — parallel folds and checkpoint sources

## Status

Status: **FROZEN EXECUTABLE AMENDMENT**

Version 1.1.4 is an operational-only amendment over v1.1.3. It preserves the
exact 96-task roster, task identities, data boundary, sample, folds, seeds,
model parameters, interpretation methods, robustness methods, and terminal
failure policy.

It addresses two execution issues discovered after the successful v1.1.3
`pca-controls` phase:

1. the inherited resource configuration allowed parallel folds but the
   controller executed every fold sequentially;
2. interpretation looked for every neural checkpoint below the post-coarse
   projection, although the immutable seed-`20260818` checkpoints remain in
   their original frozen execution directories.

No result from v1.1.3 is modified. Version 1.1.4 uses a new output root:

```text
data/model_runs/secondary_development_v1_1_4
```

## Exact checkpoint resolution

For both MLP and QNN interpretation, confirmation seeds `20260819` and
`20260820` continue to resolve below
`data/model_runs/post_coarse_v1_3_0/candidate_results`.

The base seed resolves as follows:

| Family | Seed `20260818` frozen source |
|---|---|
| PyTorch MLP | `data/model_runs/classical_mlp_coarse_v1/candidate_results/coarse/pytorch_mlp/model_stage_v1__coarse__pytorch_mlp__epochs_200__003/L_D_R/` |
| QNN | `data/model_runs/post_coarse_v1_3_0/candidate_results/qnn_q1/qnn/model_stage_v1__qnn_q1__rot_cnot_ring/L_D_R/` |

For the QNN base seed, the resolver also verifies the frozen Q2 `t0` reuse
marker linking the final representative back to the selected Q1
`ROT_CNOT_RING` source.

Real preflight verifies all 36 checkpoint manifests and files, computes their
individual SHA-256 values, and records one canonical inventory SHA-256. Workers
retain the existing checkpoint-internal task-identity validation.

## Ordered parallel execution

Only independent folds within one logical task or one ordered robustness
variant may overlap. Analysis variants remain sequential. Results are always
collected and written in the original frozen order.

| Worker family | Maximum concurrent folds |
|---|---:|
| Classical | 4 |
| PyTorch MLP | 2 |
| QNN | 4 |

Every worker remains single-threaded. The existing `QNNResourceLedger` is
shared by controller threads and already protects its attempt and cumulative
runtime state with a re-entrant lock. Each fold has a separate task directory,
checkpoint, numeric-worker input, prediction artifact, and result identity.

The expected wall-time reduction is approximately 2.5–3×:

- `interpretability`: from roughly 6–9 hours to 2–3 hours;
- `robustness-qnn`: from roughly 5–7 hours to 2–3 hours.

Changing permutation counts, row limits, seeds, model architecture, device,
precision, or scientific method is forbidden.

## Validation

The package tests cover:

- exact equality of all 96 inherited task identities and counts;
- bounded ordered parallel mapping;
- preservation of analysis-variant order;
- thread-safe concurrent QNN resource-ledger updates;
- all 84 parallel fold-fit routes on generated data;
- all 12 interpretation tasks and six folds with a numeric-free mock worker;
- exact `pca-controls` resume;
- synthetic smoke with no project-data access;
- the single-import committed-clean launcher.

A separate read-only diagnostic verified that the 36 real checkpoint sources
exist and that the pinned worker can load all three MLP and all three QNN seed
models for a representative fold. This diagnostic did not calculate project
predictions or access protected years.

## Commands

After the v1.1.4 package is committed:

```bash
bash scripts/run_secondary_analyses_v1_1_4.sh verify
bash scripts/run_secondary_analyses_v1_1_4.sh preflight
bash scripts/run_secondary_analyses_v1_1_4.sh pca-controls
bash scripts/run_secondary_analyses_v1_1_4.sh interpretability
bash scripts/run_secondary_analyses_v1_1_4.sh robustness-classical
bash scripts/run_secondary_analyses_v1_1_4.sh robustness-qnn
bash scripts/run_secondary_analyses_v1_1_4.sh report
```

The v1.1.4 `pca-controls` rerun is intentional and inexpensive. It establishes
the phase prerequisite under the new output identity instead of copying or
mutating v1.1.3 artifacts.

# Secondary development execution v1.1.5

## Purpose

Version 1.1.5 repairs the common grouped-permutation failure observed during
the real v1.1.4 `interpretability` phase. It inherits the exact 96-task roster,
model representatives, checkpoints, seeds, repetitions, fold definitions,
parallel limits, robustness methods, and protected-data boundary from v1.1.4.

The amendment changes only the handling of multiple validation rows belonging
to one `economic_group_id` during common permutation importance.

## Observed failure

The v1.1.4 worker required exactly one validation row per economic group. The
frozen development sample contains five excess rows:

| Fold | Excess rows |
|---|---:|
| `fold_2015` | 2 |
| `fold_2016` | 2 |
| `fold_2017` | 0 |
| `fold_2018` | 0 |
| `fold_2019` | 1 |
| `fold_2020` | 0 |

Labels agree within every repeated group. Four repeated pairs have slightly
different observed predictors, so averaging features or pretending that rows
are independent groups would change the intended unit of permutation.

## Remediation

For common grouped permutation only, each economic group is represented by its
first observed row in the already frozen canonical validation order. The
worker:

1. verifies that every row has an economic-group identity;
2. fails closed if labels differ within a group;
3. selects the first canonical row per group;
4. permutes the original financial feature and its missing indicator between
   these unique group representatives;
5. records original rows, unique groups, removed excess rows, and the policy ID
   in every fold result.

No feature aggregation, synthetic rows, retuning, model substitution, sample
membership change, fold change, or primary reranking is permitted. The common
permutation methodology is explicitly amended; task identities remain stable
because the logical frozen tasks and their order are unchanged. Execution
identity and result authority are separated by the new v1.1.5 config and output
root.

## Output isolation and recovery

v1.1.5 writes to:

```text
data/model_runs/secondary_development_v1_1_5
```

The interrupted v1.1.4 artifacts remain untouched for audit purposes. Because
the output identity changed, v1.1.5 starts with its own preflight and phase
manifests. PCA controls take roughly one minute to reproduce; interpretation
and subsequent phases then resume under the corrected policy.

## Commands

Run sequentially:

```bash
bash scripts/run_secondary_analyses_v1_1_5.sh verify
bash scripts/run_secondary_analyses_v1_1_5.sh preflight
bash scripts/run_secondary_analyses_v1_1_5.sh pca-controls
bash scripts/run_secondary_analyses_v1_1_5.sh interpretability
bash scripts/run_secondary_analyses_v1_1_5.sh robustness-classical
bash scripts/run_secondary_analyses_v1_1_5.sh robustness-qnn
bash scripts/run_secondary_analyses_v1_1_5.sh report
```

Do not continue to use the v1.1.4 launcher for the interrupted secondary run.
Protected feature years 2021–2024 remain closed throughout this package.

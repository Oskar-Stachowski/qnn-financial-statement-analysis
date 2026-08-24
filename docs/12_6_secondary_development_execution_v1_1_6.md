# Secondary development execution v1.1.6

## Purpose

Version 1.1.6 repairs the sole failed v1.1.5 interpretation task: detailed
interventional TreeSHAP for the frozen XGBoost representative. It preserves all
12 completed PCA tasks and 11 completed interpretation tasks, and recomputes
only the six failed TreeSHAP folds.

The new output root is:

```text
data/model_runs/secondary_development_v1_1_6
```

The v1.1.5 output remains unchanged as audit evidence.

## Failure and compatibility repair

The pinned environment contains XGBoost 3.4.1 and SHAP 0.52.0. XGBoost reports
`enable_categorical=True` as estimator metadata even though the fitted booster
contains only numeric features (`feature_types is None`). SHAP rejects
interventional TreeSHAP from that metadata before examining the numeric
booster.

The v1.1.6 worker:

1. requires an XGBoost numeric booster with no categorical feature types;
2. records the fitted booster bytes and raw validation scores;
3. changes only the post-fit estimator metadata to
   `enable_categorical=False`;
4. fails closed unless booster bytes and raw scores remain exactly unchanged;
5. runs TreeSHAP with `feature_perturbation="interventional"` and
   `model_output="raw"`;
6. verifies finite attributions and raw-logit additivity within `1e-4`.

SHAP's default independent masker silently reduces a 512-row background to
100 rows. The amended worker constructs `Independent` explicitly with
`max_samples=len(background)`, ensuring that all 512 canonical first-N rows are
used, as intended by the frozen execution specification.

The real fold-2015 diagnostic completed with 512 background rows, 500
evaluation rows, 34 features and three seeds. Booster bytes and raw scores were
exactly unchanged; the maximum additivity error was below `4e-6`.

## Exact carry-forward

The `repair-treeshap` command validates the committed v1.1.5 package, source
execution identity, preflight, phase manifests and every carried task status.
It then carries forward:

- 12/12 completed PCA task results;
- 11/12 completed interpretation task results;
- their artifacts using verified same-filesystem hard links.

Hard links avoid duplicating approximately 30 MB of artifacts. New result JSON
files record source hashes and carry-forward provenance. The failed v1.1.5
TreeSHAP task is explicitly excluded and cannot be imported. Its six folds are
regenerated in v1.1.6 with the corrected worker.

## Commands

After the package is committed, run:

```bash
bash scripts/run_secondary_analyses_v1_1_6.sh verify
bash scripts/run_secondary_analyses_v1_1_6.sh repair-treeshap
```

The repair command includes v1.1.6 preflight and is resumable. Expected runtime
is approximately 1–2 minutes. After successful repair continue with:

```bash
bash scripts/run_secondary_analyses_v1_1_6.sh robustness-classical
bash scripts/run_secondary_analyses_v1_1_6.sh robustness-qnn
bash scripts/run_secondary_analyses_v1_1_6.sh report
```

The amendment does not change any model, fitted booster, raw score, task
identity, sample member, fold, target, common-permutation result, robustness
method or primary ranking. Protected feature years 2021–2024 remain closed.

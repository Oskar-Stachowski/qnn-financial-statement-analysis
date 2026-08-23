# Current experiment status

Status date: 2026-08-23

## Current state

The complete post-coarse development sequence is finished and frozen. It includes:

- conditional refinement of XGBoost, HistGradientBoosting, and Random Forest;
- the supplemental PyTorch MLP refinement track;
- QNN Q1 ansatz selection and Q2 block-specific selection;
- classical/MLP confirmation and QNN confirmation;
- final family ranking, seed aggregation, calibration, and threshold fitting;
- a 2,000-replicate paired clustered bootstrap over `economic_group_id`;
- the compact eight-table post-coarse report.

The authoritative frozen boundary is
[`docs/10_1_post_coarse_v1_3_0_results_freeze.md`](10_1_post_coarse_v1_3_0_results_freeze.md),
with machine-readable identities in
`configs/post_coarse_v1_3_0_results_freeze_manifest.yaml`. The containing freeze
commit is `34c195822ba9bd0b9f91303f15ed827e4906dddd`.

The read-only verifier:

```bash
.venv-classical/bin/python -m src.modeling.verify_post_coarse_results_freeze
```

returns `POST_COARSE_V1_3_0_RESULTS_INTEGRITY_PASS`. It verifies 30 frozen
files, all 36 QNN confirmation fold fits, 2,000 valid bootstrap replicates, and
the eight report tables. Feature years 2021–2024 were not opened by the
post-coarse execution or by this status update.

## Canonical result locations

- Post-coarse run root: `data/model_runs/post_coarse_v1_3_0/`.
- Final primary development ranking:
  `data/model_runs/post_coarse_v1_3_0/final_primary_development_ranking.json`.
- Neural comparison manifest:
  `data/model_runs/post_coarse_v1_3_0/neural_comparison_manifest.json`.
- Clustered-bootstrap result:
  `data/model_runs/post_coarse_v1_3_0/neural_comparison_clustered_bootstrap.json`.
- Compact report: `reports/post_coarse_v1_3_0/`.
- Human-readable report summary:
  [`reports/post_coarse_v1_3_0/summary.md`](../reports/post_coarse_v1_3_0/summary.md).
- Coarse-search run retained as an immutable upstream dependency:
  `data/model_runs/classical_mlp_coarse_v1/`.

Large fitted objects, row-level OOF predictions, fold checkpoints, and worker
arrays remain intentionally outside Git. They must not be rewritten or mixed
with artifacts from another execution.

## Frozen development outcome

The final primary development leader is:

| Field | Value |
|---|---|
| Family | XGBoost |
| Configuration | `model_stage_v1__coarse__xgboost__004` |
| Feature block | `L+D+R` |
| Seed treatment | average of `20260818`, `20260819`, and `20260820` |
| Pooled OOF PR-AUC | `0.41308893399384633` |
| Pooled OOF ROC-AUC | `0.7598701797010347` |

The globally selected QNN ansatz is `ROT_CNOT_RING`. The confirmed neural
comparison is:

| Representative | Block | Pooled OOF PR-AUC | Pooled OOF ROC-AUC | PR-AUC difference vs MLP |
|---|---:|---:|---:|---:|
| Refined MLP comparator | `L+D` | `0.396263` | `0.746409` | reference |
| QNN | `L` | `0.372969` | `0.732330` | `-0.023294` |
| QNN | `L+D` | `0.373961` | `0.738855` | `-0.022302` |
| QNN | `L+D+R` | `0.383948` | `0.740584` | `-0.012316` |

These are development-only OOF results for validation years 2015–2020. The
bootstrap is conditional on the selected configurations, is not
selection-adjusted, and is not an independent test. Results from an analytic
simulator do not support a claim of quantum advantage.

## Backup and local-storage state

Two separate byte-preserving snapshots exist in the same Amazon S3 bucket:

1. `data/raw` snapshot:
   `qnn-financial-statement-analysis/raw-sec-snapshots/20260823T153845Z_git-34c19582`;
2. `data/model_runs` plus `data/processed` snapshot:
   `qnn-financial-statement-analysis/project-artifact-snapshots/20260823T165347Z_git-34c19582`.

Both snapshots passed checksum-enabled S3 downloads, streamed Zstandard
decompression, TAR enumeration, and per-file SHA-256 comparison against their
source manifests. The artifact snapshot validated 18,463 files and
13,397,282,957 logical bytes with zero mismatch. Its terminal record is
`RESTORE_VALIDATION_COMPLETE.json`.

The large `data/raw` payload was removed locally only after successful restore
validation. The local `data/model_runs` and `data/processed` sources are still
retained because the pending secondary analyses depend on them. The operational
record and restore instructions are in
[`docs/INSTRUKCJA_BACKUP_AMAZON_S3.md`](INSTRUKCJA_BACKUP_AMAZON_S3.md).

## Next permitted work

The next scientific stage is restricted to preregistered secondary development
analyses on OOF 2015–2020:

1. PCA-matched fixed-L2 and PyTorch MLP controls using exactly the final QNN
   representation and rows;
2. common grouped permutation importance and the frozen family-specific
   interpretability methods;
3. mandatory pipeline, label-definition, and QNN structural robustness runs
   with frozen configurations and no retuning.

Their executable controller, configuration, output schemas, synthetic tests,
resource policy, and failure states are versioned and frozen as
`secondary_development_execution_v1_1_0`, documented in
[`docs/12_secondary_development_execution_v1_1_0.md`](12_secondary_development_execution_v1_1_0.md).
Secondary results cannot change the primary ranking, model roster, ansatz,
feature blocks, hyperparameters, preprocessing, calibration method, or threshold
rule.

The schedule and interfaces have now been frozen in the synthetic-only
pre-execution package `secondary_development_analyses_v1_0_0`, documented in
[`docs/11_secondary_development_analyses_v1_0_0.md`](11_secondary_development_analyses_v1_0_0.md).
It deterministically accounts for 96 tasks and exposes `status`, `plan`,
`smoke`, and `verify`. It intentionally cannot read project rows or fit project
models. The v1.1.0 executable package preserves its roster, authority hashes,
access boundary, resource caps, and failure policy. Package tests covered all 84
fold-fit routes and exact resume on generated data plus the new identity-entangler
path in the pinned QNN environment; no project-data execution was performed.

The first v1.1.0 project-input preflight stopped before model fitting because
the additional target projection uses `(cik10, feature_year)` instead of the
equivalent combined sample key. The frozen v1.1.0 files remain unchanged. The
minimal v1.1.1 input-key amendment constructs the canonical `CIK10-YYYY` key,
preserves all 96 tasks, and is documented in
[`docs/12_1_secondary_development_execution_v1_1_1.md`](12_1_secondary_development_execution_v1_1_1.md).
No project model fit was performed and protected years remained closed.

The direct v1.1.1 `python -m` launcher subsequently stopped during package
self-verification because Python loaded the amendment twice (`__main__` and its
canonical module name). It stopped before creating an output identity and before
opening project data. The frozen v1.1.2 launcher imports v1.1.1 exactly once and
is documented in
[`docs/12_2_secondary_development_launcher_v1_1_2.md`](12_2_secondary_development_launcher_v1_1_2.md).

The next operational command, after the v1.1.2 launcher commit, is:

```bash
bash scripts/run_secondary_analyses_v1_1_2.sh preflight
```

If it passes, use the same v1.1.2 script to execute `pca-controls`, `interpretability`,
`robustness-classical`, `robustness-qnn`, and `report` in that order.

Do not rerun `refinement`, `qnn`, `confirmation-classical`,
`confirmation-qnn`, `inference`, `report`, or the legacy full `execute` mode in
the frozen output directories. The existing results are terminal evidence, not
scratch space.

## Protected-period boundary

Feature years 2021–2024 remain closed under
[`docs/09_1_data_access_policy_v1_1_0.md`](09_1_data_access_policy_v1_1_0.md).

- 2021–2022 are a design-exposed, spent development period and may later be
  reopened only through `DATA_ACCESS_GATE_2021_2022_REOPEN_V1`. Any result must
  be labelled secondary spent-period evidence and cannot activate tuning.
- 2023–2024 remain a temporal model-performance holdout with documented prior
  aggregate-target exposure. Blind feature application requires
  `DATA_ACCESS_GATE_2023_2024_FEATURE_APPLICATION_V1`; labels require the later
  `DATA_ACCESS_GATE_2023_2024_LABEL_REVEAL_V1`.
- The contained access incident in
  [`docs/09_2_data_access_incident_v1_0_0.md`](09_2_data_access_incident_v1_0_0.md)
  still requires an independent review and explicit resolution before a
  protected-period gate is relied upon.

Before a gate, protected-period artifacts may be checked only for existence or
by opaque byte-level hashing. Their values, schemas, row counts, distributions,
predictions, and performance must not be inspected.

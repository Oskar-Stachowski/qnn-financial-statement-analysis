# Current experiment status

Status date: 2026-08-24

## Thesis-completion runbook status

Step 4 of `docs/CODEX_REMAINING_WORK_PROMPTS.md` has prepared, but not approved,
the successor exact read-only thesis-readiness audit allowlist v1.0.1. It
remediates `ALLOWLIST-REVIEW-001` and `ALLOWLIST-REVIEW-002` from the committed
v1.0.0 review, whose verdict was `ALLOWLIST_REVIEW_FAIL`. The v1.0.0 allowlist
and its structural test remain byte-identical and v1.0.0 must not be used for
the readiness audit. Version 1.0.1 has status
`PREPARED_AWAITING_INDEPENDENT_REVIEW`; its preparation did not execute the
audit, open analytical content, run a model, or authorize access to feature
years 2021–2024.

The next action for this package is Step 5: a fresh independent review limited
to `exact_content_read_allowlist_for_review` in
`configs/thesis_readiness_audit_v1_0_1_allowlist.yaml`. The readiness audit must
not start unless a separate committed review records `ALLOWLIST_REVIEW_PASS`,
and it must then run in another fresh context against the unchanged committed
v1.0.1 allowlist. This plan-status update does not assert completion of the
author, promoter, or AI-compliance gates from earlier runbook steps.

## Current state

The complete post-coarse development sequence is finished and frozen. It includes:

- conditional refinement of XGBoost, HistGradientBoosting, and Random Forest;
- the supplemental PyTorch MLP refinement track;
- QNN Q1 ansatz selection and Q2 block-specific selection;
- classical/MLP confirmation and QNN confirmation;
- final family ranking, seed aggregation, calibration, and threshold fitting;
- a 2,000-replicate paired clustered bootstrap over `economic_group_id`;
- the compact eight-table post-coarse report.

The full preregistered secondary-development sequence is also finished and
formally frozen through report version 1.1.7. All 96 tasks are `COMPLETE`:
12 PCA-matched controls, 12 interpretability tasks, 48 classical robustness
fits, and 24 QNN structural-robustness fits. The result freeze verifies all 585
files (51,253,022 logical bytes) below the v1.1.6 execution and v1.1.7 report
roots against a committed byte-level inventory.

The derivative secondary thesis report v1.0.0 is also complete. Its read-only
generator consumed 96 task results and 84 OOF prediction artifacts, performed
no fit, opened no protected feature year, and emitted ten CSV tables plus six
figures in both PNG and SVG. The 24-file output bundle passed the independent
verifier and a manual visual-layout review.

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
- Secondary execution evidence:
  `data/model_runs/secondary_development_v1_1_6/`.
- Corrected secondary compact report:
  `data/model_runs/secondary_development_v1_1_7/`.
- Secondary result-freeze inventory:
  `reports/secondary_development_v1_1_7/artifact_inventory.json`.
- Secondary thesis report:
  `reports/secondary_development_thesis_v1_0_0/`.
- Human-readable secondary report summary:
  [`reports/secondary_development_thesis_v1_0_0/summary.md`](../reports/secondary_development_thesis_v1_0_0/summary.md).
- Machine-readable secondary report manifest:
  `reports/secondary_development_thesis_v1_0_0/analysis_manifest.json`.

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

## Secondary reporting outcome

The PCA-matched controls achieved pooled OOF PR-AUC `0.393227` for the MLP
control and `0.381590` for fixed-L2 logistic regression, compared descriptively
with the three-seed QNN reference `0.383948`. Structural QNN variants ranged
from `0.372854` to `0.377730` PR-AUC, below that frozen reference. These are
single-seed versus three-seed descriptive comparisons, not selection-adjusted
tests.

Across the common permutation analysis, revenue scale, asset scale,
profitability, liquidity, accruals, and operating-cash-flow measures recur as
important signals. For QNN, the first encoded PCA component has the greatest
mean sensitivity, but it must be interpreted jointly with its PCA loadings and
not as a direct economic-feature attribution. Label-robustness variants alter
the label definition and class prevalence, so their PR-AUC levels are not
directly comparable with the primary target.

## Backup and local-storage state

Three separate byte-preserving snapshots exist in the same Amazon S3 bucket:

1. `data/raw` snapshot:
   `qnn-financial-statement-analysis/raw-sec-snapshots/20260823T153845Z_git-34c19582`;
2. `data/model_runs` plus `data/processed` snapshot:
   `qnn-financial-statement-analysis/project-artifact-snapshots/20260823T165347Z_git-34c19582`;
3. secondary v1.1.6/v1.1.7 result snapshot:
   `qnn-financial-statement-analysis/secondary-result-snapshots/20260824T070936Z_git-e3a75230`.

All three snapshots passed checksum-enabled S3 downloads, streamed Zstandard
decompression, TAR enumeration, and per-file SHA-256 comparison against their
source manifests. The artifact snapshot validated 18,463 files and
13,397,282,957 logical bytes with zero mismatch. Its terminal record is
`RESTORE_VALIDATION_COMPLETE.json`.

The large `data/raw` payload was removed locally only after successful restore
validation. The local `data/model_runs` and `data/processed` sources are still
retained. A separate incremental snapshot of the newly frozen v1.1.6/v1.1.7
outputs was completed and restore-validated on 2026-08-24. It covers all 585
files and 51,253,022 logical bytes with zero checksum mismatch. Local deletion
remains unauthorized pending a separate dependency audit. The operational
record and restore instructions are in
[`docs/INSTRUKCJA_BACKUP_AMAZON_S3.md`](INSTRUKCJA_BACKUP_AMAZON_S3.md).

## Next permitted work

The preregistered secondary-development analyses on OOF 2015–2020 and their
derivative thesis report are complete. The next permitted work is editorial:
integrate the frozen tables, figures, interpretation, and limitations into the
thesis chapters without rerunning models or changing the scientific boundary.
The incremental byte-preserving backup of the v1.1.6/v1.1.7 source outputs is
complete.

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

The committed v1.1.2 preflight reached the permitted train-only join and then
stopped before model fitting: the interim target source does not cover every
row of the frozen supervised sample. Version 1.1.3 instead reuses the exact
production target-application train file that is already pinned by the
production runner and contains the required score and D1–D5 signals for all
19,671 supervised rows. It changes no sample member, target value, fold, task,
or method. The amendment is documented in
[`docs/12_3_secondary_development_execution_v1_1_3.md`](12_3_secondary_development_execution_v1_1_3.md).

The v1.1.3 package was committed as `725fb4e`. Its committed-clean verifier
returned `SECONDARY_DEVELOPMENT_EXECUTION_V1_1_3_SIGNAL_SOURCE_INTEGRITY_PASS`.
The real preflight then passed for the exact 19,671-row sample, feature years
2011–2020, and folds `fold_2015` through `fold_2020`. It planned all 96 tasks,
did not deserialize the interim target, did not fit a model, and did not open a
protected feature year.

The v1.1.3 `pca-controls` phase then completed in approximately 59 seconds:
all 12 planned fold fits were `COMPLETE` on their first attempt, comprising six
fixed-L2 logistic controls and six PyTorch MLP controls. All 21,520 prediction
rows and six MLP checkpoints passed independent identity, hash, finite-float64,
and fold-membership validation. The phase cannot change primary selection and
did not open a protected year.

Before interpretation, a read-only path audit found that seed-`20260818` MLP
and QNN checkpoints remain in their immutable origin directories rather than
the post-coarse projection used for confirmation seeds. It also confirmed that
the inherited 4/2/4 parallel-fold limits were not used by the sequential
controller loops. Version 1.1.4 corrects both operational issues without
changing any task identity, method, seed, sample, fold, parameter, or result
policy. It is documented in
[`docs/12_4_secondary_development_execution_v1_1_4.md`](12_4_secondary_development_execution_v1_1_4.md).

The v1.1.4 package was committed as `a681d4c`. Its committed-clean verifier
returned
`SECONDARY_DEVELOPMENT_EXECUTION_V1_1_4_PARALLEL_CHECKPOINT_INTEGRITY_PASS`.
The real preflight then passed in approximately 25 seconds for the exact
19,671-row 2011–2020 sample and six folds. It verified all 36 MLP/QNN
checkpoint sources with canonical inventory SHA-256
`af02eb87c67851919470bb46cb8a911e51c2f63c62196c5916d65cc40d6f8ea3`.
It performed no model fit, started no QNN resource-ledger attempt, and opened no
protected year.

The v1.1.4 `pca-controls` phase subsequently completed all 12 tasks. During
`interpretability`, the common grouped-permutation worker correctly exposed an
unmet data assumption: validation folds 2015, 2016, and 2019 contain,
respectively, 2, 2, and 1 rows in excess of one row per `economic_group_id`.
The first two logical interpretation tasks became `METHOD_FAILED`; the third
was interrupted after the same deterministic condition appeared. No protected
feature year was opened. The partial v1.1.4 output is retained as audit
evidence and must not be resumed.

Version 1.1.5 provides the explicit methodological remediation. Common
permutation now uses the first observed row per economic group in frozen
canonical validation order, requires label agreement within every repeated
group, performs no feature aggregation, and records the original-row and
unique-group counts. The 96-task roster, task identities, model parameters,
folds, robustness methods, checkpoint resolution, and parallel limits remain
unchanged. The amendment is documented in
[`docs/12_5_secondary_development_execution_v1_1_5.md`](12_5_secondary_development_execution_v1_1_5.md).

The v1.1.5 preflight and all 12 PCA controls passed. Common permutation then
completed for all eight families, including all 24 corrected family/fold cases
containing repeated economic groups. Eleven of twelve logical interpretation
tasks and 66 of 72 interpretation folds completed. The sole failure was
detailed interventional TreeSHAP for XGBoost on all six folds. XGBoost 3.4.1
exposes categorical-enable estimator metadata for the numeric booster, which
SHAP 0.52.0 rejects. The v1.1.5 phase manifest is terminal but is not a
scientifically complete interpretation result.

Version 1.1.6 normalizes only that post-fit estimator metadata, proves that the
booster bytes and raw scores remain exact, and supplies all 512 canonical
background rows to an explicit independent SHAP masker. It carries forward 12
complete PCA tasks and 11 complete interpretation tasks by verified hard link,
then recomputes only the six failed TreeSHAP folds. It is documented in
[`docs/12_6_secondary_development_execution_v1_1_6.md`](12_6_secondary_development_execution_v1_1_6.md).

All v1.1.6 phases subsequently completed: 12/12 PCA controls, 12/12
interpretability tasks, 48/48 classical robustness fits, and 24/24 QNN
robustness fits. The compact report accounted for all 96 tasks as `COMPLETE`,
but exposed a report-only integrity defect: amendment metadata was added after
the report SHA-256 had already been recorded in `run_manifest.json`. Version
1.1.7 preserves the complete v1.1.6 execution as immutable source evidence and
writes a corrected report under
`data/model_runs/secondary_development_v1_1_7`. It is documented in
[`docs/12_7_secondary_development_execution_v1_1_7.md`](12_7_secondary_development_execution_v1_1_7.md).

The formal result boundary is documented in
[`docs/12_8_secondary_development_results_freeze_v1_1_7.md`](12_8_secondary_development_results_freeze_v1_1_7.md)
and controlled by
`configs/secondary_development_v1_1_7_results_freeze_manifest.yaml`. Its
read-only verifier returns
`SECONDARY_DEVELOPMENT_V1_1_7_RESULTS_INTEGRITY_PASS` for all 96 task results,
84 OOF prediction artifacts, 30 checkpoints, 24 successful initial QNN
attempts, and the exact 585-file inventory. The freeze itself performed no
model fit and opened no protected-period data.

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
- The historical access incidents in
  [`docs/09_2_data_access_incident_v1_0_0.md`](09_2_data_access_incident_v1_0_0.md)
  and
  [`docs/09_3_data_access_incident_v1_1_0.md`](09_3_data_access_incident_v1_1_0.md)
  remain preserved. The fresh independent
  [`review v1.0.0`](09_5_data_access_incident_v1_1_0_independent_review_v1_0_0.md)
  returned `REVIEW_PASS`; both containment records are now `RESOLVED —
  CONTAINED — INDEPENDENT REVIEW COMPLETE`. This resolution grants no
  protected-period access. The affected thesis-readiness audit remains invalid
  and must not resume until a separate committed exact allowlist is reviewed
  and applied in a fresh context or by an independent reviewer.

Before a gate, protected-period artifacts may be checked only for existence or
by opaque byte-level hashing. Their values, schemas, row counts, distributions,
predictions, and performance must not be inspected.

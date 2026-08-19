# Data access policy v1.1.0 — corrective frozen declaration

Status: **FROZEN ACCESS DECLARATION**
Effective date: **2026-08-19**

## 1. Purpose and authority

This document is the authoritative project-wide declaration of analytical data
access from its effective date. It corrects access-status statements in the
historical supervised-pipeline and model-stage v1.0.0 artifacts. Those files
remain immutable evidence of the sequence of the project; they are not rewritten
in place.

The correction is limited to access status and access gates. It does not change
the target, research universe, raw `X_t`, supervised-sample definition,
preprocessing, temporal CV, model roster or hyperparameters, and it does not
authorize model training.

If an older specification, configuration, notebook or manifest conflicts with
this document about whether a period was analytically opened, this policy and
[`configs/data_access_policy_v1_1_0.yaml`](../configs/data_access_policy_v1_1_0.yaml)
prevail.

## 2. Corrected status of 2021–2022

Feature years **2021–2022 are a design-exposed / spent development period**.
Before this correction, their class distribution, target statistics,
missingness, feature statistics, sample-retention diagnostics and transformed
feature diagnostics were inspected while the supervised sample and
preprocessing policy were being designed.

Consequently:

- `external_validation_opened_analytically = true`;
- `independent_one_shot_external_validation = false`;
- 2021–2022 must not be described as independent one-shot external validation;
- the period may later be used only as explicitly labelled secondary evidence
  from a spent development period;
- reopening it may not activate tuning, refinement, feature/preprocessing
  changes, calibration changes or threshold changes.

No model performance for 2021–2022 had been inspected when this correction was
issued. That narrower fact does not restore independence of the complete
research pipeline.

## 3. Corrected status of 2023–2024

Feature years **2023–2024 remain a temporal model-performance holdout with a
documented limitation**. Before this correction, only aggregate target
statistics had been disclosed. Row-level target analysis, feature-level
analysis, model predictions and model performance had not been exposed.

The period therefore must not be called a fully unseen holdout with respect to
target-definition history. It may remain the temporal holdout for locked-model
evaluation, provided every result discloses the earlier aggregate-target
exposure and no test result changes the methodology.

## 4. Immediate forward lock for 2021–2024

From the effective date, no values, feature values, targets, labels,
missingness, coverage, distributions, other statistics, predictions or model
performance for 2021–2024 may be opened again before the applicable access gate.

Before a gate, the only permitted operations are:

- reading specifications, configurations and manifests;
- verifying file existence without deserializing analytical content;
- opaque byte-level SHA-256 verification;
- tests using synthetic data only.

Row counts and schema summaries for 2021–2024 are not permitted as new
pre-gate diagnostics. Accidental access stops the workflow and requires a new,
versioned incident declaration; the analysis must not continue silently.

## 5. Access gates

### 5.1. `DATA_ACCESS_GATE_2021_2022_REOPEN_V1`

The spent period may be reopened only after the corrected data pipeline,
production model-execution code, search/selection rules, seed aggregation,
calibration, threshold, reporting contract, environment locks and final
CV-selected family representatives have been frozen and hashed. The committed
gate manifest must retain the word `spent` and forbid all tuning after opening.

### 5.2. `DATA_ACCESS_GATE_2023_2024_FEATURE_APPLICATION_V1`

This gate permits blind application of the final locked pipeline to holdout
features. Test targets remain sealed. Predictions must be produced without test
labels, checked for completeness under the frozen schema, and hashed before the
label gate.

### 5.3. `DATA_ACCESS_GATE_2023_2024_LABEL_REVEAL_V1`

This gate permits one-time evaluation only after all required predictions and
the evaluation contract are frozen. Test results cannot activate a new model,
hyperparameter, ansatz, feature block, preprocessing choice, calibration method
or threshold.

## 6. Supersession without historical rewriting

The following artifacts remain byte-identical, but their access-status claims
are superseded by this policy:

- `configs/supervised_ml_pipeline_v1.yaml`;
- `configs/supervised_ml_pipeline_v1_freeze_manifest.yaml`;
- `docs/07_1_supervised_ml_pipeline_v1_frozen_specification.md`;
- `configs/model_stage_v1.yaml`;
- `configs/model_stage_v1_freeze_manifest.yaml`;
- `docs/08_1_model_stage_v1_frozen_specification.md`;
- the external-validation access declaration in
  `notebooks/05_model_stage_preregistration.ipynb`.

The exact historical hashes and superseded fields are recorded in the
machine-readable policy. Statements that a particular historical gate process
did not itself load value-bearing data remain local execution facts; they no
longer establish project-wide unopened status.

The layer-specific successors are:

- [`configs/supervised_ml_pipeline_v1_1_0_access_amendment.yaml`](../configs/supervised_ml_pipeline_v1_1_0_access_amendment.yaml);
- [`configs/model_stage_v1_1_0_access_amendment.yaml`](../configs/model_stage_v1_1_0_access_amendment.yaml);
- [`docs/07_2_supervised_ml_pipeline_v1_1_0_access_amendment.md`](./07_2_supervised_ml_pipeline_v1_1_0_access_amendment.md);
- [`docs/08_2_model_stage_v1_1_0_access_amendment.md`](./08_2_model_stage_v1_1_0_access_amendment.md).

## 7. Change control

Any later change to period status, permitted access, gate prerequisites or
post-opening rules requires a new explicit version. Results from 2021–2024 may
not be used to rewrite this declaration retrospectively.

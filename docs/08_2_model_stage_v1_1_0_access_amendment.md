# Model stage v1.0.0 — access declaration amendment v1.1.0

Status: **FROZEN ACCESS-STATUS AMENDMENT**
Effective date: **2026-08-19**

This amendment does not authorize training and does not change the historical
model roster, candidate lists, seeds, QNN design, calibration or robustness
decisions. It supersedes only the access-status and access-gate statements in
model-stage v1.0.0.

## Corrected declaration

- 2021–2022 is a `design_exposed_spent_development_period`.
- `external_validation_opened_analytically = true`.
- `independent_one_shot_external_validation = false`.
- No 2021–2022 result may activate search, refinement, calibration, threshold or
  any other methodology change.
- 2023–2024 is a temporal model-performance holdout with prior aggregate-target
  exposure, not a fully unseen target-design holdout.
- Feature-level analysis, predictions and model performance for 2023–2024 had
  not been exposed at the date of this amendment.

No values, features, targets or statistics from 2021–2024 may be reopened before
the corresponding gate in
[`data_access_policy_v1.1.0`](./09_1_data_access_policy_v1_1_0.md). The old
one-shot-validation and second-gate access semantics are superseded.

Historical v1.0.0 files remain byte-identical. Their non-access methodological
content remains historical and is not changed by this amendment.

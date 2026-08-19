# Supervised ML pipeline v1.0.0 — access declaration amendment v1.1.0

Status: **FROZEN ACCESS-STATUS AMENDMENT**
Effective date: **2026-08-19**

This amendment does not rewrite or replace the target, universe, `X_t`, sample,
preprocessing, feature blocks, temporal CV, inference or robustness decisions
of supervised ML pipeline v1.0.0. It supersedes only that version's claims about
analytical access to 2021–2024.

## Corrected declaration

- 2021–2022 is a `design_exposed_spent_development_period`.
- `external_validation_opened_analytically = true`.
- `independent_one_shot_external_validation = false`.
- Class distribution, target statistics, missingness, feature statistics,
  sample diagnostics and preprocessing diagnostics from 2021–2022 were already
  used during design.
- No model performance from 2021–2022 had been exposed at the date of this
  amendment; this does not restore independence of the full pipeline.
- 2023–2024 remains a temporal model-performance holdout, but earlier aggregate
  target statistics must be disclosed. Feature-level analysis and model
  performance had not been exposed.

No values, features, targets or statistics from 2021–2024 may be reopened before
the applicable gate defined by
[`data_access_policy_v1.1.0`](./09_1_data_access_policy_v1_1_0.md).

The historical pipeline configuration, manifest and frozen specification remain
byte-identical and are superseded only for access-status and access-gate fields.

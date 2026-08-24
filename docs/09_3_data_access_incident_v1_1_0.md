# Data access incident v1.1.0

## Status

`OPEN — CONTAINED — FRESH INDEPENDENT REVIEW REQUIRED`

On 2026-08-24, a read-only whole-project thesis-readiness audit was stopped
after a text search rendered protected-period row content from a data report.
The search was intended to locate documentation about selection bias and
informative censoring, but its path scope included `data/reports` without an
exact content allowlist.

No protected values are reproduced here. The conservatively recorded scope is
machine-readable in
[`configs/data_access_incident_v1_1_0.yaml`](../configs/data_access_incident_v1_1_0.yaml).

This is an additional event and a successor to
[`data_access_incident_v1_0_0`](09_2_data_access_incident_v1_0_0.md). The
historical v1.0.0 declaration remains unchanged and unresolved; this document
does not merge, waive or retrospectively close it.

## Containment performed

- The offending search and the complete thesis-readiness audit were stopped.
- All parallel audit work was stopped.
- No model fit, inference, production run or protected-period evaluation was
  performed.
- No frozen result artifact or methodology was modified.
- No decision was made using the rendered protected content.
- Feature years 2021–2024 remain closed under the existing access policy.
- Preparation of this declaration was limited to exact policy, incident,
  status and test files; no `data/` or `reports/` content was reopened.

The affected audit cannot issue a formal readiness verdict. Findings gathered
before the event remain provisional and cannot substitute for a fresh review.

## Conservative scope

The output rendered row-level identity and financial-primitive or resolver
information for protected feature years. Exact values and an exact record count
are intentionally not reproduced or reconstructed. Model predictions, model
performance, hyperparameter results, calibration results and threshold results
were not observed or used through this event.

## Required resolution

Before the thesis-readiness audit or any protected-period gate is relied upon:

1. review and commit this declaration and its machine-readable counterpart;
2. conduct the review in a fresh context or through an independent reviewer;
3. use only the exact files and operations in
   [`configs/data_access_incident_v1_1_0_review_allowlist.yaml`](../configs/data_access_incident_v1_1_0_review_allowlist.yaml);
4. do not read content under `data/`, `reports/` or `notebooks/` during that
   review;
5. do not reuse protected content exposed in either incident;
6. record the independent outcome in a separate versioned review artifact;
7. create and commit a separate exact allowlist before repeating the broader
   thesis-readiness audit.

The review template is
[`docs/09_4_data_access_incident_v1_1_0_independent_review_template.md`](09_4_data_access_incident_v1_1_0_independent_review_template.md).

## Current resolution state

- containment: **complete**;
- successor declaration: **created**;
- independent review: **not completed**;
- incident resolution: **open**;
- thesis-readiness audit: **must not resume**;
- protected-period access: **not authorized**.

This declaration changes no methodology, grants no data-access permission and
does not authorize model training.

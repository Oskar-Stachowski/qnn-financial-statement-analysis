# Data access incident v1.2.0

## Status

`OPEN — CONTAINED — FRESH INDEPENDENT REVIEW REQUIRED`

On 2026-08-24, the Step 7A synthetic/config-only baseline was stopped after
`tests/test_research_universe_target_application.py` had been misclassified as
synthetic. Two tests in that module call `load_eligible_universe`, which reads
the full historical-universe CSV before any period restriction. The file can
contain protected feature years 2021–2024.

No protected values are reproduced here. Exact protected rows and counts were
not reopened or reconstructed. The conservative machine-readable scope is in
`configs/data_access_incident_v1_2_0.yaml`.

## Containment

- The guarded suite was stopped; development-only tests and Steps 7B–7C were
  not started after detection.
- The offending module was removed from both runnable profiles and reclassified
  as `protected/gated`.
- It was not rerun, and no data or report content was inspected to refine the
  incident scope.
- No project model fit, new prediction, protected evaluation, network action,
  methodology change, or frozen-artifact modification occurred.
- The baseline result is invalid and cannot become a Step 7 verdict.

The process deserialized universe metadata and performed membership filtering,
an all-eligible row-count assertion, duplicate checks and a one-row selection
after the full read. Model results, predictions, target values and financial
feature values were not observed or used through this event.

## Required resolution

This exposed session cannot review or close the incident. A fresh context or
independent reviewer must use only
`configs/data_access_incident_v1_2_0_review_allowlist.yaml`, record a separate
versioned outcome, and leave all `data/` and `reports/` content unopened.

The user's same-session exception for the technical sequence 7A–7C does not
override the frozen accidental-access policy or its independent incident
review requirement. Step 7 must restart from a clean committed baseline only
after that review.

This declaration changes no methodology and grants no access or training
permission.


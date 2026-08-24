# Data access incident v1.1.0 — independent review template

Status: **TEMPLATE — REVIEW NOT EXECUTED**

This file is a checklist, not evidence that the incident has been reviewed or
resolved. A fresh context or independent reviewer must create a new versioned
review artifact rather than changing this template in place.

## Mandatory boundary

The reviewer must follow
[`configs/data_access_incident_v1_1_0_review_allowlist.yaml`](../configs/data_access_incident_v1_1_0_review_allowlist.yaml).
No content under `data/`, `reports/` or `notebooks/` may be opened. The review
does not authorize training, inference, reporting, feature inspection, schema
inspection, row counting or protected-period evaluation.

## Checklist for the new review artifact

- Record reviewer/context identity and date.
- Confirm that only exact allowlisted files were read.
- Confirm that policy v1.1.0 requires stop, scope recording and a new version.
- Confirm that incident v1.1.0 conservatively records the known mechanism and
  scope without reproducing protected values.
- Confirm that both v1.0.0 and v1.1.0 remain historically preserved.
- Confirm that no methodology, frozen results or access permissions changed.
- Confirm that the current context did not self-review or self-close the event.
- Record the isolated test result for
  `tests/test_data_access_incident_v1_1_0.py`.
- State either `REVIEW_PASS` or `REVIEW_FAIL` with reasons.
- If `REVIEW_PASS`, state separately whether the incident can be marked
  resolved and whether a new thesis-audit allowlist is adequate. Do not infer
  authorization for protected-period access.

Any unexpected content or allowlist violation requires an immediate stop and a
new versioned incident declaration.

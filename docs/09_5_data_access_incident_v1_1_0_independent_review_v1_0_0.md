# Data access incidents v1.0.0 and v1.1.0 — independent review v1.0.0

Status: **REVIEW_PASS**
Review date: **2026-08-24**

## Reviewer and independence

The reviewer was the Codex `/root` context started specifically for this
independent review. This context did not cause either access event, did not
receive the rendered protected content from either event, and did not continue
an earlier exposed audit context. It therefore acted as the fresh independent
reviewer required by the incident declarations.

The review followed
`configs/data_access_incident_v1_1_0_review_allowlist.yaml` version 1.0.0. Only
the ten exact files named in `exact_content_read_allowlist` were read. No
content under `data/`, `reports/`, `notebooks/`, `artifacts/` or `outputs/` was
opened. No repository-wide search, analytical artifact deserialization,
schema or row-count inspection, training, inference, reporting or production
pipeline was executed.

## Declaration verification

- The byte-level SHA-256 of `configs/data_access_policy_v1_1_0.yaml` is
  `7ce08bca9921ff72db6b3ec6dfd1dc28c7e751e1ca1ad3b6706180809b66cd9b`,
  matching the v1.1.0 incident declaration.
- The byte-level SHA-256 of `configs/data_access_incident_v1_0_0.yaml` is
  `d84a72f5344379c0f923329410f122f6f49b9003b617c34547ba6e03da227f57`,
  matching the v1.1.0 incident declaration.
- Policy v1.1.0 requires accidental access to stop, its scope to be recorded,
  and a new versioned incident declaration to be issued. Incident v1.1.0
  carries that rule forward exactly.
- Incident v1.0.0 conservatively records the first event, stops the affected
  gate, and leaves the protected period closed without reproducing protected
  values.
- Incident v1.1.0 records a distinct additional event, conservatively records
  its known mechanism and scope, stops the affected readiness audit, and does
  not reproduce protected values.
- Both declarations distinguish containment from resolution and state that no
  protected content affected methodology, model selection, preprocessing,
  sample design or a formal readiness verdict.
- Neither declaration changes methodology, modifies frozen results, grants
  protected-data access or authorizes model training.
- The review did not edit either historical declaration. Version 1.0.0 remains
  preserved, and version 1.1.0 is preserved as the successor record rather
  than being rewritten to self-close the events.

## Isolated test

The only executed test command was:

```text
python -m unittest tests/test_data_access_incident_v1_1_0.py
```

Result: **PASS** — 5 tests ran successfully in 0.015 seconds.

The test confirmed the open-contained pre-review state, the policy stop rule,
historical preservation of v1.0.0, the exact non-analytical review boundary,
and the absence of access or training authorization.

## Outcome and current status

The independent review outcome is **REVIEW_PASS**. The declarations are
internally consistent with policy v1.1.0, containment is complete, the review
boundary was respected, and the required fresh independent review is complete.

As of this review, both incident v1.0.0 and successor incident v1.1.0 may be
marked **RESOLVED — CONTAINED — INDEPENDENT REVIEW COMPLETE**. Their embedded
pre-review status fields remain unchanged as historical evidence; this
versioned review artifact is the subsequent resolution record.

This resolution does not authorize access to feature years 2021–2024 and does
not validate or resume the stopped thesis-readiness audit. No separate
thesis-audit allowlist was presented within this review boundary, so its
adequacy was not established. The audit must remain stopped until a new,
committed, exact allowlist is reviewed and applied in a fresh context or by an
independent reviewer.

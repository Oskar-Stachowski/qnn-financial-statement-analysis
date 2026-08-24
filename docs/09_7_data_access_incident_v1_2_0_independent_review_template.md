# Data access incident v1.2.0 — independent review template

Use a fresh context or independent reviewer. Follow only
`configs/data_access_incident_v1_2_0_review_allowlist.yaml`.

Record in a new versioned artifact:

1. reviewer identity and why the context is independent of the access event;
2. exact committed incident and allowlist identities and SHA-256 values;
3. confirmation that no `data/`, `reports/`, notebook or output content was
   opened;
4. confirmation that the test is `protected/gated`, disabled, and absent from
   every runnable profile;
5. confirmation that the incident scope is conservative and does not reproduce
   protected values;
6. `REVIEW_PASS` or `REVIEW_FAIL`, with exact blockers;
7. whether Step 7 may restart from Step 7A.

Do not run any test or suite during this review. Do not import the offending
module because its test class loads the full universe when executed.

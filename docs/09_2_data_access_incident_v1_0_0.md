# Data access incident v1.0.0

## Status

`OPEN — CONTAINED — INDEPENDENT REVIEW REQUIRED`

The final integrity-only freeze gate attempted on 2026-08-19 is invalid and did
not create a formal freeze. During an initial repository-wide text search for
prior Ultra-audit findings, the search scope incorrectly included data reports.
Rendered matches included protected-period row content.

No protected values are reproduced here. The conservatively recorded scope is
machine-readable in `configs/data_access_incident_v1_0_0.yaml`.

## Containment

The search was stopped after detection. No project-data model fit, production
execution, post-incident dry-run, synthetic smoke, QNN smoke or methodological
decision was performed. The 2021–2024 period remains closed. Historical frozen
artifacts and frozen methodology were not modified.

This handling follows data access policy v1.1.0:
`stop_record_scope_do_not_continue_and_issue_new_versioned_incident_declaration`.

## Required resolution

Before the integrity gate is repeated:

1. review and commit this incident declaration;
2. use a fresh context or an independent reviewer;
3. restrict content reads to an explicit allowlist of configurations, code and
   documentation;
4. verify any potentially protected artifact only by existence and opaque
   SHA-256;
5. do not reuse any protected values revealed during the invalidated process.

This declaration changes no methodology, grants no data-access permission and
does not authorize model training.

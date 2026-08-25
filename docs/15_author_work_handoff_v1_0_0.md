# Author Work handoff v1.0.0

This file is a navigation and checklist artifact only. It does not provide
thesis prose, interpretations or conclusions.

## Evidence entry points

| Need | Exact project artifact |
|---|---|
| Development family ranking | `reports/primary_thesis_reporting_v1_0_0/tables/01_development_family_ranking.csv` |
| 2021–2024 frozen metrics | `reports/primary_thesis_reporting_v1_0_0/tables/02_protected_period_metrics.csv` |
| Period labels and disclosures | `reports/primary_thesis_reporting_v1_0_0/tables/03_period_boundaries.csv` |
| Unavailable/omitted outputs | `reports/primary_thesis_reporting_v1_0_0/tables/04_reporting_availability.csv` |
| Number-level provenance | `reports/primary_thesis_reporting_v1_0_0/evidence_ledger.csv` |
| Secondary tables and figures | `reports/secondary_development_thesis_v1_0_0/` |
| Seed stability, complete and compact tables | `reports/methodology_extension_v1_0_0/tables/01_seed_stability_summary.csv`; `tables/09_seed_stability_thesis_compact.csv` |
| Computational cost, final representatives and program stages | `reports/methodology_extension_v1_0_0/tables/03_compute_cost_final_representatives.csv`; `tables/05_compute_cost_program_stages.csv`; `tables/10_compute_cost_thesis_compact.csv` |
| Seed-stability and cost figures | `reports/methodology_extension_v1_0_0/figures/` |
| Methodological limitations for author review | `reports/methodology_extension_v1_0_0/tables/07_methodological_disclosures.csv` |

## Legacy planning source

The original topic card has been archived byte-for-byte as
`docs/legacy/01 Karta Tematu QNN LEGACY.docx`. It is a superseded planning
source, not a current methodology or thesis-completeness contract. Future
current-state audits must exclude it from blocker and discrepancy counts; it
may be read only as historical provenance. The closure assessment and current
authority list are recorded in `docs/legacy/README.md`.

The former path `docs/01 Karta Tematu QNN.docx` contains only a legacy pointer
so the exact-path structural tests for historical audit allowlists remain
valid. The pointer is not an active topic card.

Historical audit allowlists v1.0.0--v1.0.5 still contain the former path as
part of their frozen process history and must not be edited in place. A future
successor audit must use a new allowlist that excludes the legacy archive.

## Mandatory boundary labels

- Development: `development-only`, `conditional-on-selection`,
  `selection-unadjusted`, no independent post-selection test.
- 2021–2022: `secondary evidence`, `design-exposed/spent development`, not
  independent validation.
- 2023–2024: temporal holdout with prior aggregate exposure and the failed
  pre-metric v1.0.0 label-exposure disclosure; not fully unseen.
- QNN: analytic simulator only; no quantum-advantage claim.
- All model results: predictive association, not a causal claim.

## Historical audit findings for author review

The following items come from the 2026-08-24 readiness result. Chapter files
were not opened or modified while preparing this handoff, so their present
closure status is intentionally not inferred.

| Historical finding | Owner | Current project-side status |
|---|---|---|
| Assemble the final thesis master package and verify front/back matter, references, tables and figures | AUTHOR / Work | NOT RECHECKED |
| Replace stale Chapter 5 execution status and placeholders with author-written analysis | AUTHOR / Work | NOT RECHECKED |
| Align the target definition to the frozen D1–D5 rule and `score >= 3` | AUTHOR / Work | A newer Chapter 1 commit exists; content NOT RECHECKED |
| Update Chapter 4 from planned to actually executed methodology | AUTHOR / Work | NOT RECHECKED |
| Complete the VQC section and resolve the illustration/AI disclosure | AUTHOR / Work | NOT RECHECKED |

## Explicit non-tasks for Work

- Do not rerun, refit, reselect, recalibrate or rethreshold models.
- Do not pool development, spent-development and holdout into one estimand.
- Do not derive further omitted statistics from row-level predictions. The
  reporting-only seed-stability and runtime extension is already closed under
  `configs/methodology_extension_reporting_v1_0_0.yaml`; use its frozen outputs
  rather than recomputing or expanding the analysis.
- Do not use the failed v1.0.0 partial holdout output as evidence.
- Do not describe AP as a trapezoidal PR-curve integral; use average precision,
  historically labelled PR-AUC in project artifacts.

No successor thesis-readiness audit was run as part of this handoff.

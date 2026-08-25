# Primary thesis reporting v1.0.0 — GATED_SUCCESSOR_MODE

## Purpose

This reporting-only package provides a deterministic evidence and navigation
layer for the author. It keeps three estimands separate:

1. development-only pooled OOF evidence for 2015–2020;
2. secondary design-exposed/spent-development evidence for 2021–2022;
3. the 2023–2024 temporal holdout with mandatory prior-exposure disclosure.

The package is not thesis prose. It contains no interpretation, conclusion,
answer to a research question, independent-test claim, fully-unseen claim or
quantum-advantage claim.

## Procedural boundary

The protected-period reports were already complete and frozen before this
reporting contract. Their aggregate values had also been observed after P6E
before the reporting contract was committed. Consequently, this contract is
not described as preregistered or blinded. It uses the conservative successor
rule: copy and normalize only fields already present in exact frozen aggregate
reports and omit every new post-result analysis.

The access review is an author-authorized `same_session_technical_review`, not
the independent review requested by the original runbook. This limitation is
recorded in
`configs/primary_thesis_reporting_access_review_v1_0_0_result.json`.

## Exact value sources

The generator may deserialize only:

- `reports/post_coarse_v1_3_0/07_final_primary_family_ranking.csv`;
- `reports/protected_period_extension_v1/spent_report_v1_0_0.json`, after
  `SPENT_REPORT_FREEZE_PASS`;
- `reports/protected_period_extension_v1/holdout_report_v1_0_1.json`, after
  `HOLDOUT_REPORT_FREEZE_PASS`;
- the two corresponding freeze-result JSON files.

EDA, PCA, coarse, post-coarse and secondary-report packages enter only as
opaque path/SHA-256 provenance. The generator does not read row-level OOF or
protected predictions, targets, features or membership records.

## Canonical outputs

The output root is `reports/primary_thesis_reporting_v1_0_0/`. It contains:

- a nine-row frozen development family ranking;
- 36 protected-period model/year rows, kept in separate spent-development and
  holdout roles;
- a period-boundary and mandatory-label table;
- an explicit availability/omission table;
- an opaque upstream-package provenance table;
- a 639-record number-level evidence ledger in CSV and JSON;
- a deterministic file manifest and navigation README.

No canonical figure is generated. Log loss, calibration intercept/slope and
curve, protected composition/retention, new paired comparisons, FP/FN cases
and runtime-cost comparisons are explicitly omitted rather than reconstructed
from row-level data.

## Reproduction and verification

```bash
.venv-classical/bin/python -m src.modeling.primary_thesis_reporting_v1_0_0 verify-package
.venv-classical/bin/python -m src.modeling.primary_thesis_reporting_v1_0_0 verify-output
.venv-classical/bin/python -m src.modeling.primary_thesis_reporting_v1_0_0 freeze
```

The freeze action regenerates the package in a temporary directory and compares
the exact file set and bytes. The committed result is
`PRIMARY_REPORTING_FREEZE_PASS` with deterministic reproduction, zero new
statistics and zero row-level protected-content reads.

## Author handoff

The author should use the evidence ledger for exact number lookup and the
period-boundary table for mandatory labels. Author-written interpretation and
chapter integration remain outside this package and are handled separately in
Work mode.

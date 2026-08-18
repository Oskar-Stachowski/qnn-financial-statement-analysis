# QNN Financial Statement Analysis

Master's thesis research project on Quantum Neural Networks for financial statement analysis.

## Project scope

This repository supports research on the use of Quantum Neural Networks and classical machine learning models for analyzing financial statement data.

The project may include:

- financial statement preprocessing,
- financial ratio engineering,
- fraud or bankruptcy proxy construction,
- classical machine learning baselines,
- Quantum Neural Network experiments,
- model comparison and evaluation,
- reproducible notebooks and reports.

## Repository structure

```text
data/          datasets used in the empirical part of the thesis
docs/          research notes, methodological assumptions, and project documentation
notebooks/     exploratory notebooks for data analysis and QNN/ML experiments
references/    bibliography, literature notes, and source summaries
reports/       generated experiment reports, tables, plots, and model evaluation results
src/           reusable Python modules for preprocessing, feature engineering, modelling, and evaluation
thesis/        thesis drafts, chapter materials, and final written outputs
```

## Status

Early-stage master's thesis research repository.

## Current data pipeline

The reproducible SEC preprocessing flow is organized as numbered steps in
`src/data/`.

The active pipeline currently covers:

- the original current-snapshot SEC acquisition, preliminary universe,
  Company Facts parsing, and quality checks in steps `01`-`07`;
- point-in-time target B construction and audit in steps `09`-`19`;
- filing-first historical point-in-time research-universe construction,
  registrant-role/economic-entity resolution, and audit in steps `20`-`24`;
- the frozen `target_candidate_v2_pit_b` v1.0.0 specification in
  `docs/04_9_target_candidate_v2_pit_b_frozen_specification.md`;
- the frozen historical research-universe v1.1.0 specification and manifest in
  `docs/05_1_historical_research_universe_pit_frozen_specification.md` and
  `configs/research_universe_pit_freeze_manifest.yaml`.

The historical research universe now uses original SEC 10-K filings and the
historical SIC attached to the same accession. Membership, `X_t` availability,
and target availability are separate statuses. Universe policy v1.1.0 retains
at most one eligible representative per consolidated annual statement scope,
preserves linked co-registrants as provenance, and assigns related scopes an
`economic_group_id` without changing the temporal split. It has passed its
implementation audit and is formally frozen as historical-universe version
v1.1.0. The final point-in-time feature
dataset `X_t` has not been built or frozen yet, and no model training should be
performed until its temporal/data-vintage controls are implemented and audited.

The earlier pre-PIT modeling-dataset implementation and superseded audit
helpers are retained under `LEGACY/` for historical reference. They are not
part of the active pipeline and must not be used to train final models.

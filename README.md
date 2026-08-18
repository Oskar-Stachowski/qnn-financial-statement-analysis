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

- SEC acquisition, universe construction, Company Facts parsing, and quality
  checks in steps `01`-`07`;
- point-in-time target B construction and audit in steps `09`-`19`;
- the frozen `target_candidate_v2_pit_b` v1.0.0 specification in
  `docs/04_9_target_candidate_v2_pit_b_frozen_specification.md`.

The final point-in-time feature dataset `X_t` has not been frozen yet. The
research universe and feature pipeline must be corrected for temporal and
survivorship bias before model training.

The earlier pre-PIT modeling-dataset implementation and superseded audit
helpers are retained under `LEGACY/` for historical reference. They are not
part of the active pipeline and must not be used to train final models.

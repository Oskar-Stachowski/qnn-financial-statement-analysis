# Legacy planning documents

## Status

`01 Karta Tematu QNN LEGACY.docx` is a historical planning document from before
the final empirical scope was frozen. It was moved here on 2026-08-25 without
changing its bytes.

- original path: `docs/01 Karta Tematu QNN.docx`
- archived path: `docs/legacy/01 Karta Tematu QNN LEGACY.docx`
- SHA-256: `92f96cc26225699b2490922d7e5802e4b846395db7ceab0e666613743d25e210`
- authority status: `LEGACY_SUPERSEDED_PLANNING_SOURCE`

The former path `docs/01 Karta Tematu QNN.docx` now contains only a short
legacy pointer. It is retained so the structural tests for historical audit
allowlists v1.0.0--v1.0.5 continue to find their exact path. The pointer is not
a current scope document and redirects readers to this archive and the current
authorities below.

Future current-state thesis audits must not treat discrepancies between the
archived document and the executed experiment as open blockers. The archived
file may be used only to document the historical development of the research
idea. Historical audit allowlists v1.0.0--v1.0.5 retain the former path as
frozen process records; the allowlists themselves must not be edited in place
or reused as current-state audit scope.

## Current authorities

Use the following sources for the current research scope and results:

- `README.md`;
- `docs/10_current_experiment_status.md`;
- `docs/04_9_target_candidate_v2_pit_b_frozen_specification.md`;
- `docs/07_1_supervised_ml_pipeline_v1_frozen_specification.md` and its
  versioned amendments;
- `docs/08_1_model_stage_v1_frozen_specification.md` and the later execution
  and `lightning.qubit` amendments;
- `docs/12_10_primary_thesis_reporting_v1_0_0.md`;
- `docs/15_author_work_handoff_v1_0_0.md`.

## Closure review of the legacy plan

The legacy plan contains no unperformed item that requires reopening the
frozen model pipeline.

Items retained in the executed study include the SEC EDGAR data source,
classical baselines, MLP, QNN, PCA-based dimensionality reduction, temporal
evaluation, multiple seeds, robustness analyses, interpretability and an
explicit no-quantum-advantage boundary.

The following ideas were optional, later narrowed, or deliberately rejected
and are not current thesis requirements:

- Beneish M-Score or Altman Z-Score as predictors or alternative labels;
- exhaustive 4/8/12/20-feature experiments, RFE and mutual-information search;
- QSVC or quantum-kernel experiments;
- learning curves and reduced-sample experiments;
- new model families, new targets or additional hyperparameter searches.

Two useful reporting items remain worth carrying into thesis writing, without
new fitting or a change to the frozen ranking:

1. summarize performance dispersion across the existing confirmation seeds;
2. report computational-resource evidence conservatively, with explicit
   disclosure that classical and QNN runtimes were measured in different
   environments and are not a controlled hardware benchmark.

Existing aggregate Brier score, F1, precision and recall may be reported for
the frozen operating thresholds. New case-level error analysis, recalibration
or threshold changes after observing protected-period results are not required
by the legacy plan and must not be inferred from it.

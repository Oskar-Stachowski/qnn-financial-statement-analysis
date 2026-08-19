# Production runner and reproducible environments v1.0.0

## Scope

This implementation operationalizes model execution contract v1.2.0 without
changing data access policy v1.1.0, raw X_t v1.1.0, supervised pipeline v1.2.0,
or either model-stage v1.2.0 artifact. Historical frozen v1 files remain intact.

No project-data model was fitted. No 2021--2024 values, labels, features,
statistics, predictions, or performance were opened.

## Execution architecture

`ProductionExperimentRunner` is the fail-closed controller. It verifies all
upstream SHA-256 values before data deserialization, accepts only the two exact
2011--2020 train projections, reconstructs and verifies the frozen sample and
all six PIT-safe fold memberships, fits preprocessing and QNN PCA on fold-train
rows only, and owns every selection/calibration/artifact decision.

Estimator workers are numeric-only subprocesses. They receive an NPZ with one
already-partitioned matrix and a JSON task identity. Worker code contains no CSV,
Parquet, project path, validation, or test loader. Classical tasks execute in the
classical lock; MLP/QNN tasks execute in the Python 3.12 lock.

The controller implements, in order:

1. frozen sample and PIT/label-availability folds;
2. train-only preprocessing and QNN train-only PCA/component scaling;
3. canonical coarse and QNN Q1 execution;
4. deterministic conditional refinement and QNN Q2;
5. frozen confirmation seeds;
6. canonical OOF alignment and `math.fsum` raw-score averaging;
7. pooled OOF PR-AUC and deterministic ranking;
8. one-dimensional Platt calibration and exact max-F1 threshold;
9. candidate/fold/seed, ranking, roster, feasibility and secondary-scope
   manifests.

The worker retry order is initial attempt, at most one identity-verified
checkpoint resume, then at most one fresh infrastructure retry. Timeout is
cumulative over all attempts. Nonfinite inputs/parameters/scores, warnings,
timeouts, checkpoint mismatch, deterministic exceptions and exhausted
infrastructure have separate terminal statuses. Partial-fold metrics and manual
candidate substitution are impossible.

## Access and predictor guards

The only financial predictor allowlist is the frozen 17-feature L+D+R order.
Each evaluated block is an exact prefix composition with one unscaled missingness
indicator per included feature. `economic_group_id`, target, year, timestamp and
identity fields cannot enter the numeric predictor matrix. The canonical
prediction key is `(validation_feature_year,
research_universe_company_year_id)`.

The production CLI has no arbitrary input-path option. Any changed upstream
file/path/hash, sample membership, fold membership, candidate registry, expanded
candidate ordering or PCA feature ordering causes a hard failure before fitting.

## Dry run and synthetic E2E

The production dry run verified both train-input hashes, the 19,671-member
sample fingerprint, all six frozen fold fingerprints and the 320-position
candidate plan. It performed zero fits.

The complete synthetic E2E used 40 generated observations from 2011--2020. It
executed the full orchestration and emitted 2,160 per-fold result manifests,
three deterministic refinement activations, 30 classical/MLP and three QNN
confirmation slots, nine representatives, calibrators and thresholds. Two fresh
runs produced byte-identical key manifests in policy tests.

## Environments

`environments/classical/requirements.lock` contains 17 exact direct/transitive
pins with artifact hashes under CPython 3.13.13. The required scientific stack
is numpy 2.4.4, scipy 1.17.1, pandas 3.0.3, scikit-learn 1.8.0, xgboost 3.4.1,
shap 0.52.0, joblib 1.5.3 and threadpoolctl 3.6.0.

`environments/qnn_mlp/requirements.lock` contains 46 exact direct/transitive
pins with artifact hashes under CPython 3.12.2. The required model stack is
torch 2.13.0, PennyLane 0.45.1, pennylane-lightning 0.45.0 and Captum 0.9.0,
with the frozen common scientific packages.

Both locks passed fresh `pip --require-hashes` installation and import smoke on
macOS 15.5 / Darwin 24.5.0, arm64, 8 logical CPUs and 8 GiB RAM. All specified
thread limits were 1. Before any project input is deserialized, the production
controller also requires an exact installed-distribution match against every
direct and transitive lock entry (with only the venv bootstrap `pip` excluded).
QNN execution uses deterministic torch algorithms and analytic
`default.qubit`; CUDA and MPS were not used.

## QNN resource smoke

All six ansatz/qubit combinations (three preregistered ansatzes × 4/6 qubits)
passed forward/backward, finite-output and finite-gradient checks, exact
deterministic replay and exact checkpoint round-trip. The report records wall
time, peak-RSS upper bounds, checkpoint size and parameter/optimizer-state byte
estimates for every case.

IBM Quantum and AWS Braket plugins were not installed. A non-executable adapter
interface is reserved in the runner config; activating it requires a new explicit
preregistration version.

## Commands after freeze authorization

Dry run:

```text
python -m src.modeling.run_production_experiment dry-run \
  --output-dir <new-empty-artifact-directory> \
  --classical-python <classical-venv>/bin/python \
  --qnn-python <qnn-venv>/bin/python
```

The `execute` mode is implemented but was deliberately not invoked on project
data. Production artifacts must be written to a new empty directory and frozen
before any applicable later-period gate.

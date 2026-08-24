# QNN Financial Statement Analysis

A point-in-time, leakage-controlled research pipeline for classifying one-year multidimensional financial deterioration from SEC EDGAR filings and comparing classical machine learning, a PyTorch multilayer perceptron, and analytic quantum neural networks.

> Master's thesis research project by **Oskar Stachowski**.
>
> Repository state reflected in this README: **24 August 2026**.

## Research objective

The project investigates whether a resource-constrained Quantum Neural Network (QNN) can provide competitive performance or complementary modelling value relative to classical machine-learning methods and a matched classical neural network when all models use the same point-in-time financial information.

The outcome is **not** a bankruptcy, fraud, insolvency, or accounting-manipulation label. It is a frozen proxy for material, multidimensional deterioration in a company's financial condition between fiscal years `t` and `t+1`.

## Current project status

| Component | Current state |
|---|---|
| Historical point-in-time research universe | **Frozen**, version `1.1.0` |
| Point-in-time deterioration target | **Frozen**, `target_candidate_v2_pit_b` version `1.0.0` |
| Train-only point-in-time feature projection | **Frozen**, `x_t_pit_v1_1_0_train.csv` |
| Supervised ML pipeline | **Frozen**, with versioned access and resolver amendments |
| Model-stage preregistration and candidate registry | **Frozen**, with a scientific-correctness patch |
| Production execution contract | **Frozen**, version `1.2.1` Lightning with scientific patch |
| Classical and PyTorch MLP coarse search | **Complete** |
| Conditional classical refinement and supplemental MLP refinement | **Complete** |
| QNN Stage Q1 and Stage Q2 | **Complete**; selected ansatz `ROT_CNOT_RING` |
| Classical/MLP and QNN confirmation | **Complete** |
| Final development ranking, calibration, thresholds, bootstrap, and compact report | **Complete and frozen**, post-coarse `v1.3.0` |
| PCA-matched controls, robustness, and interpretability | **Complete and frozen**, 96/96 tasks through report `v1.1.7` |
| Thesis-ready secondary tables, figures, and interpretation | **Complete and frozen**, report `v1.0.0` |
| Large raw-data, model-artifact, and secondary-result backups | **Complete and restore-validated** in Amazon S3 |
| Evaluation using feature years 2021–2024 | **Closed under the frozen access policy** |

The authoritative progress record is [`docs/10_current_experiment_status.md`](docs/10_current_experiment_status.md).

## Latest development result

The complete post-coarse sequence comprises conditional refinement, QNN Q1/Q2, classical/MLP and QNN confirmation, seed aggregation, calibration and threshold fitting, a 2,000-replicate paired clustered bootstrap, and compact reporting. The frozen bundle passes the read-only integrity verifier with verdict `POST_COARSE_V1_3_0_RESULTS_INTEGRITY_PASS`.

The final primary development ranking is led by:

| Field | Value |
|---|---|
| Model family | XGBoost |
| Configuration | `model_stage_v1__coarse__xgboost__004` |
| Feature block | `L+D+R` |
| Seed treatment | averaged seeds `20260818`, `20260819`, and `20260820` |
| Pooled OOF PR-AUC | **0.413089** |
| Pooled OOF ROC-AUC | **0.759870** |

The separate neural comparison is:

| Representative | Block | Pooled OOF PR-AUC | 95% clustered-bootstrap CI | Difference vs MLP |
|---|---:|---:|---:|---:|
| Refined MLP comparator | `L+D` | **0.396263** | [0.375772, 0.419443] | reference |
| QNN | `L` | 0.372969 | [0.352288, 0.395790] | -0.023294 |
| QNN | `L+D` | 0.373961 | [0.354057, 0.395900] | -0.022302 |
| QNN | `L+D+R` | **0.383948** | [0.364326, 0.407518] | -0.012316 |

These remain **development-only OOF results for 2015–2020**. The bootstrap is conditional on the selected configurations and is not an independent test or a selection-adjusted inferential claim. The analytic-simulator experiment does not establish quantum advantage. Full results and interpretation are in [`reports/post_coarse_v1_3_0/`](reports/post_coarse_v1_3_0/), and the exact frozen boundary is documented in [`docs/10_1_post_coarse_v1_3_0_results_freeze.md`](docs/10_1_post_coarse_v1_3_0_results_freeze.md).

The preregistered secondary sequence is likewise complete: 12 PCA-matched
controls, 12 interpretability tasks, 48 classical robustness fits, and 24 QNN
structural-robustness fits. Its formal result freeze verifies 96/96 complete
task results and an exact 585-file inventory. See
[`docs/12_8_secondary_development_results_freeze_v1_1_7.md`](docs/12_8_secondary_development_results_freeze_v1_1_7.md).

The read-only thesis-reporting package converted that frozen evidence into ten
CSV tables, six figures in PNG and SVG, and a concise interpretation. The
24-file bundle passes its independent output verifier and is available in
[`reports/secondary_development_thesis_v1_0_0/`](reports/secondary_development_thesis_v1_0_0/).
The secondary variants are descriptive development evidence: they do not
change the frozen primary ranking and do not establish quantum advantage.

## Data and point-in-time design

### Sources

The active pipeline uses official SEC EDGAR resources, including:

- quarterly master indexes for the historical filing census;
- SEC Financial Statement Data Sets, especially `SUB` metadata;
- same-accession submission headers;
- original annual `10-K` filings and their XBRL packages;
- SEC Company Facts and filing-level statement evidence where required.

The historical universe is **filing-first**. Membership is reconstructed from historical original filings rather than from a current ticker snapshot, which reduces survivorship and historical-classification bias. Current ticker availability, current exchange membership, and present-day issuer activity are not conditions for historical membership.

### Historical research universe

The frozen universe covers feature years **2011–2024** and contains:

| Membership status | Company-year anchors |
|---|---:|
| Eligible | **64,901** |
| Excluded | 36,659 |
| Ambiguous | 1,539 |
| **Total** | **103,099** |

It contains **9,798** eligible representative CIKs and **9,739** eligible economic groups. Membership status, feature availability, and target availability are intentionally separate concepts. The exact policy is documented in [`docs/05_1_historical_research_universe_pit_frozen_specification.md`](docs/05_1_historical_research_universe_pit_frozen_specification.md).

### Frozen target

For an eligible company-year `(i, t)`, the target represents deterioration between `t` and `t+1`. A positive label requires at least three of five validated signals:

| Signal | Frozen rule |
|---|---|
| ROA deterioration | `ROA_(t+1) - ROA_t <= -0.03` |
| Operating cash-flow deterioration | `OCF/assets_(t+1) - OCF/assets_t <= -0.03` |
| Liquidity deterioration | `current_ratio_(t+1) / current_ratio_t <= 0.80` |
| Leverage deterioration | `liabilities/assets_(t+1) - liabilities/assets_t >= 0.10` |
| Revenue deterioration | `revenues_(t+1) / revenues_t - 1 <= -0.10` |

The target is positive when `deterioration_score_1y >= 3`. Values for `t` and `t+1` are reconstructed point-in-time from the same earliest original `10-K` anchor for `t+1`. Later amendments and restatements are excluded. Missing, ambiguous, or hard-excluded signals remain unavailable and are never silently mapped to the negative class.

See [`docs/04_9_target_candidate_v2_pit_b_frozen_specification.md`](docs/04_9_target_candidate_v2_pit_b_frozen_specification.md) for the authoritative definition.

## Features and preprocessing

The frozen predictor set contains **17 financial features** divided into three blocks:

- `L` — seven level features;
- `D` — five one-year change features;
- `R` — five revenue and profitability features.

The only primary comparisons are `L`, `L+D`, and `L+D+R`. Identity fields, timestamps, feature year, target fields, and `economic_group_id` are forbidden predictors.

<details>
<summary>Show the exact frozen feature list</summary>

### L — levels

`log_assets_t`, `roa_t`, `ocf_to_assets_t`, `current_ratio_t`, `liabilities_to_assets_t`, `working_capital_to_assets_t`, `accruals_to_assets_t`

### D — one-year changes

`asset_growth_1y`, `delta_roa_1y`, `delta_ocf_to_assets_1y`, `current_ratio_change_1y`, `delta_liabilities_to_assets_1y`

### R — revenue and profitability

`log1p_revenues_t`, `profit_margin_t`, `ocf_margin_t`, `asset_turnover_t`, `revenue_growth_1y`

</details>

For every temporal fold and feature block, preprocessing is fitted from zero on fold-training rows only:

1. per-feature p1/p99 winsorization;
2. per-feature median imputation;
3. population-standard-deviation scaling;
4. one unscaled binary missingness indicator per financial feature.

Validation rows never influence winsorization caps, medians, means, scales, PCA, or model fitting. The frozen implementation is in [`src/modeling/preprocessing.py`](src/modeling/preprocessing.py), and its methodology is described in [`docs/07_1_supervised_ml_pipeline_v1_frozen_specification.md`](docs/07_1_supervised_ml_pipeline_v1_frozen_specification.md).

## Models

The preregistered benchmark contains:

- dummy-prior and fixed-L2 logistic baselines;
- elastic-net logistic regression;
- RBF SVM;
- Random Forest;
- HistGradientBoosting;
- XGBoost;
- deterministic float64 PyTorch MLP;
- analytic PennyLane QNN, conditional on the frozen technical-feasibility rules.

The QNN stage uses fold-training-only PCA, four or six components/qubits, deterministic float64 execution, analytic `default.qubit`, and adjoint differentiation. The preregistered architecture packages are `ROT_CNOT_RING`, `RY_RZ_CZ_BRICKWORK`, and `RY_CRX_RING`. PCA-matched logistic and MLP controls are diagnostic comparisons and do not enter the primary classical-model ranking.

The complete model-stage specification is in [`docs/08_1_model_stage_v1_frozen_specification.md`](docs/08_1_model_stage_v1_frozen_specification.md).

## Evaluation protocol

The primary model-selection pool covers feature years **2011–2020**. It contains **19,671** supervised company-years. Six expanding-window validation folds generate canonical out-of-fold predictions for years 2015–2020:

| Fold | Training feature years | Embargo year | Validation year |
|---|---|---:|---:|
| `fold_2015` | 2011–2013 | 2014 | 2015 |
| `fold_2016` | 2011–2014 | 2015 | 2016 |
| `fold_2017` | 2011–2015 | 2016 | 2017 |
| `fold_2018` | 2011–2016 | 2017 | 2018 |
| `fold_2019` | 2011–2017 | 2018 | 2019 |
| `fold_2020` | 2011–2018 | 2019 | 2020 |

A training row must additionally satisfy the frozen label-availability cutoff relative to the earliest prediction timestamp in the validation fold.

The primary ranking metric is **pooled out-of-fold PR-AUC** over validation years 2015–2020. ROC-AUC and fold-level metrics are secondary. Dependence-aware uncertainty is preregistered through a clustered bootstrap over `economic_group_id`. The project also preregisters complete-case, no-indicator, no-winsorization, purged-group, sparse-row, and label-definition robustness analyses.

## Protected-period access policy

The authoritative policy is [`docs/09_1_data_access_policy_v1_1_0.md`](docs/09_1_data_access_policy_v1_1_0.md).

Feature years **2021–2022 are a design-exposed, spent development period**. Their target, missingness, retention, and feature diagnostics were inspected during pipeline design, so they must not be described as independent one-shot external validation. They may later provide explicitly labelled secondary evidence, but they cannot activate tuning or methodology changes.

Feature years **2023–2024 remain a temporal model-performance holdout with documented prior aggregate-target exposure**. Row-level features, labels, predictions, and model performance remain protected. Blind feature application and later label reveal require separate committed access gates. No result from 2021–2024 may alter the frozen model family, hyperparameters, ansatz, feature block, preprocessing, calibration, or threshold.

## Reproducible environments

Model execution deliberately uses two isolated, hash-locked environments:

| Environment | Python | Role |
|---|---:|---|
| `classical` | 3.13.13 | Controller, preprocessing, classical estimators, calibration, reporting |
| `qnn_mlp` | 3.12.2 | PyTorch MLP and analytic PennyLane QNN workers |

The following commands use POSIX path conventions. Replace the interpreter paths with exact local installations of the required Python versions.

```bash
git clone https://github.com/Oskar-Stachowski/qnn-financial-statement-analysis.git
cd qnn-financial-statement-analysis

/path/to/python3.13.13 -m venv .venv-classical
.venv-classical/bin/python -m pip install \
  --require-hashes \
  -r environments/classical/requirements.lock

/path/to/python3.12.2 -m venv .venv-qnn
.venv-qnn/bin/python -m pip install \
  --require-hashes \
  -r environments/qnn_mlp/requirements.lock
```

The root `requirements.txt` supports lightweight reporting/notebook work. It is **not** the authoritative environment for contract-bound model execution. Exact environment instructions are in [`environments/README.md`](environments/README.md).

IBM Quantum and AWS Braket plugins are intentionally not installed. Their adapter boundary is reserved but non-executable; activation requires a new explicit preregistration version.

## Running the experiment controller

Start with a contract and input-integrity dry run. The output location must be a new empty directory.

```bash
.venv-classical/bin/python -m src.modeling.run_production_experiment dry-run \
  --output-dir <new-empty-output-directory> \
  --classical-python .venv-classical/bin/python \
  --qnn-python .venv-qnn/bin/python
```

The CLI also implements `real-data-smoke`, `coarse-search`, and full `execute` modes. These modes are bound to exact input paths, SHA-256 identities, candidate registries, fold memberships, environment locks, and access rules. Full execution is not a generic training command and must not be used to bypass the frozen experiment sequence or the protected-period gates.

The controller is implemented in [`src/modeling/production_runner.py`](src/modeling/production_runner.py), with its CLI in [`src/modeling/run_production_experiment.py`](src/modeling/run_production_experiment.py).

## Tests and integrity controls

The repository uses Python `unittest` modules under [`tests/`](tests/). The test suite covers, among other areas:

- historical-universe and target invariants;
- point-in-time and timezone semantics;
- train-only preprocessing;
- frozen sample and fold identities;
- access-policy supersession;
- candidate-registry and execution-contract locks;
- production-runner behaviour and reporting integrity.

Run targeted modules in the environment that owns their dependencies, for example:

```bash
.venv-classical/bin/python -m unittest tests.test_preprocessing
.venv-classical/bin/python -m unittest tests.test_data_access_policy_v1_1_0
.venv-classical/bin/python -m unittest tests.test_model_execution_contract_v1_2_0
```

## Repository structure

```text
configs/       versioned policies, candidate registries, execution contracts, and freeze manifests
data/          raw, interim, processed, report, and local model-run locations
docs/          methodological specifications, access declarations, audits, and status records
environments/  exact Python versions and hash-locked dependency files
notebooks/     pipeline design, EDA, PCA diagnostics, preregistration, and result analysis
prompts/       retained project prompts and workflow instructions
references/    literature and supporting research materials
reports/       compact thesis-ready tables, figures, summaries, and integrity outputs
src/data/      numbered SEC acquisition, PIT reconstruction, target, universe, and feature pipeline
src/modeling/  preprocessing, model contracts, workers, production runner, and reporting
tests/         scientific, integrity, freeze-lock, and execution tests
thesis/        thesis drafts and chapter materials
LEGACY/        superseded pre-PIT and pre-freeze implementations retained for provenance
```

`LEGACY/` is historical evidence only. Its pre-PIT modelling pipeline must not be used to train or report final models.

## Data and artifact availability

Large SEC downloads, generated row-level datasets, fitted objects, checkpoints, and complete model-run directories are intentionally excluded from ordinary Git tracking. Their canonical paths are under `data/`, while compact reports, manifests, schemas, counts, provenance, and SHA-256 references are versioned where appropriate.

The full `data/raw` payload, the large `data/model_runs` plus `data/processed` artifacts, and the completed secondary v1.1.6/v1.1.7 outputs have separate byte-preserving Amazon S3 snapshots. All three snapshots passed checksum-enabled downloads, streamed decompression, TAR enumeration, and per-file SHA-256 validation. Large `data/raw` payloads were removed locally only after that restore validation. The secondary outputs remain local; their backup does not itself authorize deletion. Operational details are recorded in [`docs/INSTRUKCJA_BACKUP_AMAZON_S3.md`](docs/INSTRUKCJA_BACKUP_AMAZON_S3.md).

Consequently, cloning the repository provides the code, specifications, tests, and compact evidence package, but not every large input or execution artifact. Reproduction requires restoring or rebuilding the exact frozen SEC-derived inputs and passing all manifest and hash checks. The controller fails closed when an expected path, file identity, sample membership, fold membership, candidate identity, or environment identity differs from the frozen contract.

## Key documentation

| Topic | Authoritative or current file |
|---|---|
| Current experiment status | [`docs/10_current_experiment_status.md`](docs/10_current_experiment_status.md) |
| Data-access policy | [`docs/09_1_data_access_policy_v1_1_0.md`](docs/09_1_data_access_policy_v1_1_0.md) |
| Frozen target | [`docs/04_9_target_candidate_v2_pit_b_frozen_specification.md`](docs/04_9_target_candidate_v2_pit_b_frozen_specification.md) |
| Historical research universe | [`docs/05_1_historical_research_universe_pit_frozen_specification.md`](docs/05_1_historical_research_universe_pit_frozen_specification.md) |
| Raw point-in-time features | [`docs/06_2_raw_point_in_time_x_t_v1_frozen_specification.md`](docs/06_2_raw_point_in_time_x_t_v1_frozen_specification.md) |
| Supervised ML pipeline | [`docs/07_1_supervised_ml_pipeline_v1_frozen_specification.md`](docs/07_1_supervised_ml_pipeline_v1_frozen_specification.md) |
| Model-stage preregistration | [`docs/08_1_model_stage_v1_frozen_specification.md`](docs/08_1_model_stage_v1_frozen_specification.md) |
| Production runner and environments | [`docs/08_4_production_runner_and_environments_v1_0_0.md`](docs/08_4_production_runner_and_environments_v1_0_0.md) |
| Post-coarse frozen result boundary | [`docs/10_1_post_coarse_v1_3_0_results_freeze.md`](docs/10_1_post_coarse_v1_3_0_results_freeze.md) |
| Post-coarse result summary | [`reports/post_coarse_v1_3_0/summary.md`](reports/post_coarse_v1_3_0/summary.md) |
| Secondary-development result freeze | [`docs/12_8_secondary_development_results_freeze_v1_1_7.md`](docs/12_8_secondary_development_results_freeze_v1_1_7.md) |
| Secondary thesis-reporting contract | [`docs/12_9_secondary_development_thesis_reporting_v1_0_0.md`](docs/12_9_secondary_development_thesis_reporting_v1_0_0.md) |
| Secondary thesis-report summary | [`reports/secondary_development_thesis_v1_0_0/summary.md`](reports/secondary_development_thesis_v1_0_0/summary.md) |
| S3 backup and restore record | [`docs/INSTRUKCJA_BACKUP_AMAZON_S3.md`](docs/INSTRUKCJA_BACKUP_AMAZON_S3.md) |
| Coarse-search summary | [`reports/coarse_search_thesis/summary.md`](reports/coarse_search_thesis/summary.md) |
| Coarse-search family table | [`reports/coarse_search_thesis/tables/07_thesis_family_summary.csv`](reports/coarse_search_thesis/tables/07_thesis_family_summary.csv) |

## Next stages

The next scientific work is thesis integration: incorporate the already frozen
primary and secondary tables, figures, limitations, and narrative into the
final chapters. It must not rerun models, reinterpret label variants as direct
comparisons, or alter the frozen primary decisions. The incremental
byte-preserving backup of v1.1.6/v1.1.7 is complete and restore-validated.

Feature years 2021–2024 remain closed. Reopening 2021–2022 requires the committed spent-development access gate and cannot activate tuning. The 2023–2024 holdout requires separate blind-feature-application and label-reveal gates.

## Citation and disclaimer

Until a final thesis or publication citation is available, cite the repository together with the exact Git commit used for the analysis.

This repository is an academic research project. Its outputs are not investment advice, credit advice, audit evidence, or a production risk-scoring system.

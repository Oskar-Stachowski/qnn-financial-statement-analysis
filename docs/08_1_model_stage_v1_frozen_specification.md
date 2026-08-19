# Model-stage preregistration v1.0.0 — frozen specification

## Status and authority

- ID: `model_stage_preregistration`
- Version: `1.0.0`
- Status: **FROZEN**
- Freeze date: 2026-08-19
- Technical gate: **MODEL STAGE READY TO FREEZE**
- Authoritative preregistration: `notebooks/05_model_stage_preregistration.ipynb`
- Authoritative notebook SHA-256: `67c4daa32a00cb0db08fbd35b950f422a277b63e22e669a449487c9a80626afc`
- Machine-readable policy: `configs/model_stage_v1.yaml`
- Machine-readable policy SHA-256: `e9951acd7d81a15a6e60a49cc88bc3021bb20be9dd0afcad952b98cecbe62b25`
- Materialized candidate registry: `configs/model_stage_candidates_v1.json`
- Candidate registry SHA-256: `857ed6361a55c4ff1183a56614a4058e132db7a8b49bb5742b187900cd9d7f58`

The notebook is the authoritative human-readable preregistration. The YAML is its execution-oriented policy registry. The JSON is the authoritative enumeration of all 142 unique materialized `configuration_id` values, their exact hyperparameters, the preregistered coarse/refinement/QNN lists, and the SHA-256 of every list. Together with the freeze manifest, these artifacts define model-stage v1.0.0.

No search or project-data model fit is authorized by the act of freezing this specification.

## Immutable upstream inputs

This freeze does not alter any upstream frozen artifact:

| Layer | Version | Frozen manifest SHA-256 |
|---|---:|---|
| `target_candidate_v2_pit_b` | 1.0.0 | `52fd67d360e486e45615330a869f8b7d5810eb08d957432b4c2da7cc146b66bb` |
| historical research universe | 1.1.0 | `60310dbc9379371c05316b28de273832d0eaf02f20fc1ee7bb28697a26fb71b7` |
| raw point-in-time `X_t` | 1.0.0 | `9b59e812bfb1b34a2f72c78ce4fc0ba484249d0a1d48cdea8f94506a403a9023` |
| supervised ML pipeline | 1.0.0 | `f1000d9e66a83160ff4ae0c5759c09c96491e18c4b579f6a397e0e98afc6eef1` |

The supervised sample, preprocessing C, three feature blocks, six PIT-safe expanding-window folds, pooled OOF PR-AUC ranking, clustered inference and validation/test access boundaries remain exactly as frozen in supervised ML pipeline v1.0.0.

## Frozen model benchmark

The benchmark roster is:

1. dummy-prior baseline;
2. fixed L2 logistic regression;
3. elastic-net logistic regression with `penalty="elasticnet"`, `solver="saga"` and the complete constructor frozen in the notebook and YAML;
4. RBF SVM;
5. random forest;
6. histogram gradient boosting;
7. XGBoost;
8. PyTorch MLP;
9. QNN, conditional only on satisfying the frozen technical-feasibility policy.

LDA and a single decision tree were not declared in the earlier methodology and are explicitly omitted. Their benchmark roles are covered by the logistic and tree-ensemble families. LightGBM was an earlier alternative to XGBoost; v1.0.0 instantiates that alternative as XGBoost. No model may be added, removed or substituted after inspecting validation or test results.

Every family is evaluated on the frozen feature blocks `L`, `L+D` and `L+D+R` as specified in the preregistration. The dummy is block-agnostic. QNN-specific PCA is a fold-train-only transformation after frozen preprocessing C; it does not redefine a feature block.

## Candidate materialization and search control

The complete candidate registry was generated before training with coarse sampling seed `20260818` and refinement sampling seed `20260821`. It contains 142 unique configuration IDs. All search spaces, exact sampled candidates and list hashes are immutable.

| Candidate list | N | SHA-256 |
|---|---:|---|
| `coarse.dummy_prior` | 1 | `0bd658ab876c744c9d31ab24fd68d2bba1375adc02d88f306ba0ad5183cb832b` |
| `coarse.fixed_l2_logistic` | 2 | `0eb110e1552138bcd87d5d35777c826d73d75b4d7ec643a048e5f827e78668b1` |
| `coarse.elastic_net_logistic` | 12 | `a0cde4769aa6afd413b828b019c7c83f9ac90a171def2f842d740d36c50cd216` |
| `coarse.rbf_svm` | 12 | `9e2f34d2edea9cf7b14e5cb5abd01e96176a438906e2287b094e434e327e46bd` |
| `coarse.random_forest` | 12 | `cc113d8091c867c6723301c165d0f2f0d8b0dd7b3ae9fcf4cdd0157da489b7f1` |
| `coarse.hist_gradient_boosting` | 16 | `9f78bbc7b6e8f15a279effea7d0b1afb69d3080b22a0129a93396d2e4b694b96` |
| `coarse.xgboost` | 16 | `712feb5fe5b28235330de10faa9a0d43c67ec03072f8efa000719dd2f7f7ff6b` |
| `coarse.pytorch_mlp` | 12 | `7316d4dab28573ea7984901da560738221a90406b41391855271e04b9639d85c` |
| `refinement.elastic_net_logistic` | 8 | `cb66a6ff5969436d7d81b4c698bb7174972d0eb251c26cf3bf63c26d1548d2f4` |
| `refinement.rbf_svm` | 8 | `8697c976326c5242bfd7f7444dee16b26822ac7147864ff07d6c233db3ec2a46` |
| `refinement.random_forest` | 8 | `d15e7b62877096dbf26fcb1b19bea9d9f6c840b84b0e1424a0a881caa4517cb4` |
| `refinement.hist_gradient_boosting` | 10 | `e4a0e89d1629f6564878e12ae0733d42e6dc26943d770ebaab6007a0cd63506d` |
| `refinement.xgboost` | 10 | `fac91cf8796ccb23fbf14b5664153a1ae05f6b01280e84d38577b5e45122712e` |
| `refinement.pytorch_mlp` | 8 | `4a4373cdbcdb6e73a9040aaabf99814a991c44d3662c7a8cd646801f554d73e1` |
| `qnn.stage_q1` | 3 | `2393bf866e591e4c42ac69d1377c617d77de2aef94153e08cff5e93ff701fc28` |
| `qnn.stage_q2` | 4 | `6083b919b7ae8d57dd0119ab66b5aab5a5a1379fb74e30c416e4c1792cfe64f4` |

Conditional classical refinement is allowed only from OOF 2015–2020 and only under the frozen objective trigger: the best-block coarse result must be boundary-affected or have a close runner-up; the coarse leader distance threshold is 0.01, runner-up gap threshold is 0.003, and at most three families may refine. Validation 2021–2022 and test 2023–2024 can never activate refinement.

The ranking search cap is 2166 fold fits, including at most 180 conditional-refinement fits. The QNN cap is 240 fold-fit attempts. PCA-matched controls have a separate diagnostic budget of 12 fold fits and never enter primary ranking or QNN selection.

## Weighting, seeds and score contract

Within each training fold only:

\[
w_{negative}=1, \qquad w_{positive}=\sqrt{N_{negative}/N_{positive}}.
\]

The exact family API is frozen: classical estimators use `sample_weight`; XGBoost keeps `scale_pos_weight=1`; PyTorch MLP and QNN use `BCEWithLogitsLoss(pos_weight=...)`; dummy has no weighting. Validation rows are never weighted for fitting.

Coarse/refinement use seed `20260818`; stochastic top candidates are confirmed with `20260819` and `20260820`. For each OOF row, the final raw score is the arithmetic mean of aligned raw scores from all three seeds. Pooled OOF PR-AUC is calculated once on those averaged scores and enters ranking. Deterministic exceptions are dummy prior, fixed L2 logistic and probability-disabled RBF SVM.

Raw-score interfaces are frozen per family: `decision_function` for logistic, SVM and HistGB; native output margin for XGBoost; clipped-probability logit for random forest; direct logits for PyTorch MLP and QNN; and an explicit clipped train-prior logit for dummy.

## Ranking, calibration and threshold

The primary ranking rule is the maximum pooled OOF PR-AUC for validation years 2015–2020. Equal scores are defined after rounding to six decimals. The tie-break order is smaller feature block, simpler frozen family order, no class weighting, fewer parameters, then lexicographic configuration ID. Fold PR-AUC, mean, sample SD, minimum, prevalence comparison and seed dispersion are mandatory stability reporting, but instability cannot alter ranking unless a fit is technically invalid.

Each frozen family representative receives one unweighted one-dimensional logistic Platt calibrator fit to its final seed-averaged pooled OOF raw scores. The max-F1 threshold is chosen on the same calibrated pooled OOF predictions, with the higher threshold winning a tie. This threshold is an operating point and explicitly is not an independent estimate of generalization. Calibration and threshold do not alter primary ranking.

## PyTorch MLP contract

MLP is a deterministic `torch.nn.Sequential` model in float64 with one scalar logit, `BCEWithLogitsLoss(reduction="mean")`, Xavier-uniform weights, zero biases, Adam with betas `(0.9, 0.999)` and epsilon `1e-8`, and no dropout, batch normalization or early stopping. Batch shuffle order, deterministic algorithms, single-thread execution, atomic checkpoint contents, five-epoch cadence and one-resume limit are frozen exactly in the notebook and YAML. The former `alpha` and `max_iter` concepts are represented as `weight_decay` and `epochs`.

## QNN stages, representation and resources

Stage Q1 compares three architecture packages at identical non-architecture settings: `ROT_CNOT_RING`, `RY_RZ_CZ_BRICKWORK` and `RY_CRX_RING`. It may select the ansatz. Stage Q2 searches the four preregistered full configurations while holding the Stage-Q1 ansatz fixed. Q1 is interpreted as a comparison of complete architecture packages, not a causal estimate of the entangling gate effect. Exact gate order/direction, trainable parameter counts, initialization, linear head, minibatch order and tie-break rules are frozen.

The QNN input is frozen preprocessing-C output in the order: all block financial columns, then corresponding missing indicators. PCA includes the indicators, uses `svd_solver="full"`, `whiten=False`, and 4 or 6 components. A fold-train-only `StandardScaler` is applied to PCA components, followed by clipping to `[-3,3]` and `angle=(pi/3)*clipped_component`. Feature-order hashes are:

- `L`: `e44756941715e636fe21f13bd82585d580e9b24c7f1e2beb26e33ebaea525509`
- `L+D`: `8077c1bb7208155340ae32c6e0ce8833226e9cfca56690c966a49fd095b9bc4e`
- `L+D+R`: `bb15196f3ab32eabe3492df6f5d9701da7a9b340eea3f9e84d126623f27429b7`

PCA-matched fixed logistic and PyTorch MLP controls use exactly the QNN representation and rows, remain diagnostic, and cannot affect primary ranking or QNN selection.

QNN uses analytic `default.qubit`, adjoint differentiation and float64. A fold fit has a 120-minute cumulative wall-time cap; total caps are 240 CPU hours and 240 attempts. Checkpoints occur every five epochs. At most one resume and one documented fresh infrastructure retry are allowed. Retries cannot change methodology. Exceeding a cap or another frozen infeasibility condition yields `QNN_TECHNICALLY_INFEASIBLE`; it cannot trigger post-hoc simplification of ansatz, qubits, layers or epochs.

## External roster, interpretation and robustness

Before external validation opens, exactly one CV-frozen representative per family is locked with its feature block, configuration ID/hyperparameters, seed ensemble or deterministic exception, score interface, Platt calibrator and max-F1 threshold. The global CV winner is primary; the other representatives are preregistered secondary comparisons. Validation cannot remove or replace any later test-roster member. A technical failure after lock remains a reported failed roster entry.

Interpretability is frozen as grouped OOF permutation importance common to all families; standardized coefficients/odds ratios for linear models; interventional TreeSHAP for tree/boosting; Integrated Gradients on logits for MLP; and conservative PCA loading, original-feature permutation, encoded-input sensitivity, fold/seed stability and structural ablation for QNN. QNN attributions cannot be described as a complete quantum-model explanation. Interpretation cannot select or change the model.

Mandatory robustness/sensitivity analyses retain frozen hyperparameters and cannot change primary selection: preprocessing B without indicators, complete-case, no-winsorization, purged group CV, sparse-row exclusion at at least 11 of 17 available features, preregistered label sensitivities and QNN structural sensitivities.

## Validation, PIT-safe refits and second test gate

External validation 2021–2022 is one-shot and no-tune. The preregistered PIT-safe refits are:

- prediction 2021: train years 2011–2019, embargo 2020;
- prediction 2022: train years 2011–2020, embargo 2021;
- prediction 2023: train years 2011–2021, embargo 2022;
- prediction 2024: train years 2011–2022, embargo 2023; 2023 test labels are never training data.

Every refit applies the exact `target_available_at` cutoff and refits preprocessing from zero. Stochastic representatives use three seeds, average raw scores, then apply their frozen calibrator and threshold.

After the one-shot validation, changing any family, hyperparameter, ansatz, feature block, preprocessing, calibration or threshold requires an explicitly new methodology version; validation becomes spent and test stays closed. Model-stage v1 can access test 2023–2024 only after a committed second-gate manifest with verdict `MODEL PIPELINE v1 TEST-READY UNCHANGED`. Otherwise the verdict is `MODEL PIPELINE v1 NOT TEST-READY` and test remains closed.

## Freeze-time access declaration

The technical gate and this formal freeze establish that:

- validation 2021–2022 was not opened analytically;
- test 2023–2024 was not opened or used;
- no model was trained on project data;
- only imports, version checks, notebook assertions and synthetic smoke tests were executed.

Any change to this specification, the authoritative notebook, the machine config, the candidate registry, configuration IDs/list hashes, or protected implementation contracts requires a new explicit model-stage version and a new development-only audit.

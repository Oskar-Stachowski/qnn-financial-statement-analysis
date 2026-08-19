# Model execution contract v1.2.0

Status: frozen pre-runner execution contract. Scope: model-development and internal temporal CV for feature years 2011–2020 only. No project model was trained, no production runner was implemented, and no value or statistic from 2021–2024 was opened.

The authoritative machine-readable specification is `configs/model_execution_contract_v1_2_0.yaml`. It operationalizes the nonconflicting model-stage v1 decisions after data-access amendment v1.1.0, raw X_t v1.1.0, supervised pipeline v1.2.0, and the model-stage resolver amendment v1.2.0. Historical v1 files remain immutable.

## Candidate order and ranking

The contract enumerates a canonical 320-position execution index derived from all 142 frozen registry IDs. The order is stage, frozen family order, feature-block order, and authoritative registry-array order. Coarse candidates are expanded over all applicable blocks; dummy is block-agnostic; refinement candidates bind to the selected family leader's block; Q1 and Q2 are expanded over all three blocks. The complete index has SHA-256 `263635db04d87466b182f3a853910e2cc6ca11a284deeb57969b5cbea43faf21`.

Primary comparisons use raw float64 pooled OOF PR-AUC. A tie is equality after six-decimal `ROUND_HALF_EVEN` quantization. The remaining key is smaller block, frozen family simplicity, no imbalance weighting, lower frozen static complexity units, coarse before refinement, and UTF-8 configuration ID. Invalid rows remain auditable but rank after complete rows.

## Boundary and conditional refinement

Boundary refers to endpoints of the full preregistered coarse hyperparameter domains, never to endpoints observed in the sampled candidate list. Only the numeric/ordinal parameters explicitly listed in the contract are ordered. Categorical values, `gamma="scale"`, `max_features="sqrt"`, activation, hidden-layer shape, criterion, and imbalance mode are not boundary values.

The global coarse leader is the highest-ranked complete non-QNN coarse candidate. Each refinement-eligible family receives one family leader and its best block. The runner-up is the next complete coarse candidate in that same family and block. A family activates exactly when distance to the global leader is at most 0.010 and either the family leader is boundary-affected or the runner-up gap is at most 0.003. Distances use unrounded metrics, are clamped below at zero, and comparisons are inclusive. At most three families activate, ordered by distance, leader rank, then frozen refinement-family order.

## Merge, confirmation, and seed aggregation

Coarse and activated refinement results enter one table with a unique family/block/configuration/seed key. Refinement outside the frozen activated block is an integrity error. For elastic net, random forest, HistGB, XGBoost, and MLP, exactly the top two complete merged candidates per family and block are selected for seeds 20260819 and 20260820. This is 30 confirmation slots and 360 additional fold fits. Dummy, fixed L2 logistic, and probability-disabled RBF SVM are deterministic exceptions.

QNN confirms exactly one Q2 candidate per block, three slots and 36 additional fold fits. There is no promotion of a third candidate after a confirmation failure. Unconfirmed stochastic rows remain in the table but cannot enter final ranking.

Predictions align on `(validation_feature_year, research_universe_company_year_id)`, sorted by integer year and UTF-8 ID. Fold, target, economic group, and prediction timestamp must match across seeds. Raw scores are averaged with `math.fsum` in seed order 20260818, 20260819, 20260820. Pooled OOF PR-AUC is then computed once on averaged raw scores. Probabilities are never averaged.

## Failures, retries, and checkpoints

A candidate metric exists only when every one of the six frozen folds is complete. Missing folds, nonfinite inputs/parameters/scores, convergence warnings, numerical runtime warnings, timeouts, unexpected warnings, and deterministic library exceptions are terminal technical invalidations. Partial metrics are forbidden.

Only enumerated infrastructure codes may retry. MLP and QNN may resume once from an identity-matching atomic checkpoint, followed by at most one fresh infrastructure retry. Other families may use at most one fresh infrastructure retry. Seeds, configuration, method, membership, preprocessing, environment, device, and cumulative timeout cannot change. A failed confirmed candidate cannot be replaced by an unselected candidate.

## QNN identity

Q1 ranks nine ansatz/block candidates and freezes one global `selected_ansatz_id`. Its exact key is rounded PR-AUC, smaller block, trainable parameter count, fixed before trainable entangler, ansatz ID, and configuration ID. Q2 consists of reused t0 plus new t1–t3 for each block; its ansatz cannot change. Every execution identity contains ansatz, Q1/Q2 configuration, block, qubits/PCA, layers, epochs, optimizer settings, seed, fold, software/environment hash, and analytic `default.qubit` device identity.

## Calibration and threshold

Every noninvalid family representative exposes exactly one frozen raw-score interface. Stochastic OOF scores are seed-averaged before calibration. Platt uses canonical OOF order, an unweighted one-dimensional logistic fit, and the frozen constructor. Constant bitwise-identical scores use a deterministic zero-slope, prevalence-intercept map. Degenerate labels, nonfinite input, convergence, or solver failure invalidate calibration; no alternative calibrator, reselection, or family replacement is allowed.

The max-F1 candidates are every unique finite calibrated probability plus `nextafter(max_probability, +infinity)` for predict-none. Prediction is positive for probability greater than or equal to threshold. F1 candidates are compared by exact integer cross-multiplication; exact ties select the numerically higher threshold. Calibrator and threshold are frozen as hashed artifacts before the 2021–2022 reopen gate.

## Interpretability and robustness

Common grouped OOF permutation is mandatory for every complete non-dummy family representative and conditional only on QNN technical feasibility. Detailed representatives are selected algorithmically: best fixed/elastic linear, best RF/HistGB/XGBoost tree/boosting, MLP, and feasible QNN. Sampling uses canonical first-N rows, not result-dependent samples.

The global winner receives five pipeline and three label robustness runs with fixed configuration and seed 20260818. A feasible QNN additionally receives four structurally enumerated runs and both PCA-matched controls. QNN pipeline/label robustness is additionally required only if QNN is the global winner. None of these results can alter primary ranking, roster, calibration, or threshold.

## Integrity-only second gate

The second gate can verify hashes, schemas, execution completeness, frozen identities, accounted terminal failures, access declarations, and the continued seal on 2023–2024. It cannot consume 2021–2022 PR-AUC, F1, calibration, confidence intervals, performance acceptance thresholds, or qualitative interpretations. Performance reports enter only as opaque hashes and schema-presence evidence. Therefore performance magnitude can never affect the gate verdict.

The only verdicts are `MODEL_EXECUTION_V1_2_INTEGRITY_PASS` and `MODEL_EXECUTION_V1_2_INTEGRITY_FAIL`. A pass is only a prerequisite for the separate 2023–2024 feature-application gate; it does not itself reveal holdout features or labels.

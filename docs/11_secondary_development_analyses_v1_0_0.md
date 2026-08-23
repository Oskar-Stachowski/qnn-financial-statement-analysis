# Secondary development analyses v1.0.0 — pre-execution freeze

## Status and purpose

Status: **FROZEN PRE-EXECUTION PACKAGE**

This package freezes the schedule, identities, output interfaces, resource
limits, and failure states for the secondary development analyses that follow
the completed post-coarse v1.3.0 result freeze. It does not execute models on
project data and does not authorize access to feature years 2021–2024.

The package has three executable, non-project-data modes:

```bash
bash scripts/run_secondary_analyses.sh status
bash scripts/run_secondary_analyses.sh plan
bash scripts/run_secondary_analyses.sh smoke
```

After the freeze manifest is present, verify it with:

```bash
bash scripts/run_secondary_analyses.sh verify
```

Modes `execute`, `pca-controls`, `interpretability`, `robustness`, and `all`
fail closed in v1.0.0. Adding project-data execution requires a new explicit
version, tests, authority hashes, and commit. This prevents the planning freeze
from silently turning into an unreviewed analytical implementation.

## Frozen scientific boundary

The only permitted analytical population remains development OOF 2015–2020,
with feature years bounded to 2011–2020. The package may not:

- change the primary ranking or family roster;
- replace the global XGBoost winner;
- change the selected QNN ansatz `ROT_CNOT_RING`;
- change feature blocks, hyperparameters, preprocessing, target definition,
  calibration, or threshold rules;
- use result magnitude to activate, remove, or replace a task;
- make a quantum-advantage claim;
- inspect feature years 2021–2024.

The post-coarse freeze manifest, final family ranking, QNN phase manifest,
execution contract, candidate registry, environments, preprocessing, temporal
CV, and access policy are all pinned by SHA-256 in
`configs/secondary_development_analyses_v1_0_0.yaml`.

## Deterministic task roster

The plan contains exactly 96 unique task identities:

| Stage | Planned units |
|---|---:|
| PCA-matched fixed-L2 and MLP controls | 12 fold fits |
| Common grouped permutation importance | 8 family methods |
| Detailed family-specific interpretation | 4 methods |
| Global-winner pipeline and label robustness | 48 fold fits |
| QNN structural robustness | 24 fold fits |
| **Total** | **96 tasks** |

PCA-matched controls use exactly the final ranked QNN representative's feature
block, rows, fold-train preprocessing, PCA dimension, component scaler,
clipping, and angle encoding. Fixed-L2 and MLP hyperparameters come from their
own frozen final family representatives. The two controls use seed `20260818`
and never enter the primary ranking.

The global winner receives five pipeline variants and three label variants on
all six folds, for 48 fold fits. The technically feasible QNN receives four
structural variants on all six folds, for 24 fold fits. QNN is not the frozen
global winner, so it does not receive the additional pipeline or label runs.

## Interpretability

Common grouped permutation importance covers every complete non-dummy family
representative and the feasible QNN. It uses seed `20260818`, 20 repetitions,
canonical OOF 2015–2020 rows, `economic_group_id`, and the frozen original
financial-feature groups with their own missing indicators.

Detailed representatives and methods are fixed algorithmically:

- best complete fixed-L2/elastic-net linear representative: standardized
  coefficients, odds ratios, and fold/seed sign stability;
- best RF/HistGB/XGBoost representative: interventional TreeSHAP;
- final MLP representative: Integrated Gradients on logits;
- final feasible QNN: PCA loadings, explained variance, encoded-input
  sensitivity, and fold/seed stability.

Sampling is canonical first-N, never result-dependent. The maxima are 512 tree
background rows, 500 tree OOF rows per fold, 200 MLP rows per fold with 64 IG
steps, and 100 QNN rows per fold.

## Robustness definitions

The global XGBoost winner uses frozen hyperparameters and seed `20260818` for:

1. preprocessing B without missing indicators;
2. block-specific complete case;
3. no winsorization;
4. purged economic-group CV;
5. sparse rows with at least 11 of 17 raw features;
6. deterioration score at least 2;
7. deterioration score at least 4;
8. `max(D1,D2) + D3 + D4 + D5 >= 3`.

The QNN structural variants are: identity in place of entanglers, each of the
two nonselected Q1 ansatzes at fixed final settings, and the preregistered 4/6
qubit PCA swap. None may retune or trigger reselection.

## Resource and failure policy

Every worker is single-threaded. Parallel limits are four classical folds, two
MLP folds, and four QNN folds. Hard caps are 12 PCA-control fits, 48 global
winner robustness fits, and 24 QNN structural fits. QNN structural cumulative
wall time is capped at 172,800 seconds. Automatic restoration of `data/raw` is
forbidden.

Every planned task must reach one of: `COMPLETE`, `TECHNICALLY_INVALID`,
`METHOD_FAILED`, or `RESOURCE_LIMIT_REACHED`. Failures remain results; no task
may be substituted and no family may be reranked. Authority mismatch,
protected-period detection, missing required development inputs, and output
identity conflicts stop the run fail-closed.

## Output contract

The package freezes required fields for the plan, synthetic smoke, per-task
results, phase manifests, and final run manifest. Every task identity is
canonical-JSON hashed. Phase completion requires every planned task to be
terminally accounted for. All outputs must declare
`protected_feature_years_opened: false` and that the primary selection remains
unchanged.

## Transition to project execution

The next implementation version must provide the actual project executor while
preserving this task roster and all authority identities. Before its first
project-data read it must:

1. pass this package verifier and the post-coarse v1.3.0 verifier;
2. be committed with a clean Git authority gate;
3. use a new empty output directory;
4. refuse any row outside feature years 2011–2020;
5. use only the frozen processed development inputs;
6. fail rather than automatically restore or inspect `data/raw`;
7. retain 2021–2024 as sealed.

# Current experiment status

Status date: 2026-08-20

## Last completed stage

The preregistered classical/MLP coarse search on the six PIT-safe temporal CV folds for 2015–2020 is complete. The run executed 247 candidate positions and 1,482 fold fits with training seed `20260818`. Of these, 238 candidate positions completed successfully. Nine RBF SVM positions were excluded fail-closed after convergence warnings; their fold attempts and terminal statuses remain recorded in the manifests.

No conditional refinement, QNN execution, final calibration or thresholding, robustness, interpretability, or external validation/test execution has been performed as part of this stage.

## Git anchors and result locations

- Coarse-search execution code commit: `39a0a841e51ddfeb5402aeadf9e6a2864b637ac9`.
- Commit recording the coarse-search manifests in Git: `409c1789ba673885779cae01e9b2cfa36c2401a0`.
- Local run root: `data/model_runs/classical_mlp_coarse_v1/`.
- Canonical OOF prediction root: `data/model_runs/classical_mlp_coarse_v1/candidate_results/coarse/`.
- Canonical aggregate manifest: `data/model_runs/classical_mlp_coarse_v1/classical_mlp_coarse_search_manifest.json`.
- Canonical aggregate manifest SHA-256: `5f8029810811d443dbb363cd8dc341fd147d563d7d65d0a824c8c1929e7bfc43`.
- Per-family result manifests: `data/model_runs/classical_mlp_coarse_v1/coarse_results/<family>/result_manifest.json`.
- Refinement qualification manifest: `data/model_runs/classical_mlp_coarse_v1/refinement_eligibility.json`.
- Refinement qualification manifest SHA-256: `236517a5a9297c3fb0db603b0fe9983cf7769a8ecda3684a07ca41bc1566cad0`.
- Runtime and environment record: `data/model_runs/classical_mlp_coarse_v1/runtime_metadata.json`.
- Runtime and environment record SHA-256: `38a0237d0847dfaac702627740e93f1a1aa92b79d9c7a3b2aaad418f371a5788`.

The aggregate, per-family, refinement, run, and runtime manifests are tracked by Git in commit `409c1789...`. Row-level OOF predictions, fitted objects, and checkpoints remain in the local run directory and are intentionally not tracked because of their size. Their paths and SHA-256 integrity references are recorded in the tracked manifests. The coarse-search outputs and existing candidate IDs must not be rewritten.

## Current artifact versions

| Artifact | Current version or identity |
|---|---|
| Timezone/PIT interpretation | `timezone_pit_fix_v1_0_0`, SEC acceptance timestamps canonicalized to UTC |
| Frozen X_t train projection | `x_t_pit_v1_1_0_train.csv`, SHA-256 `872cb551a0855d658c52276e5e7594efb05da167718709ab76b386ebfa917d65` |
| Frozen target-application train overlay | `research_universe_pit_v1_1_0_target_pit_b_v1_2_0_train.csv`, SHA-256 `0f5d3bdefe13ed6ea6a1c6cdc94ae2c663f59175a7363dd8bffa26717069dd1b` |
| Model-stage candidate registry | `model_stage_candidates_v1`, scientific-correctness patch `1.0.1`, SHA-256 `f8135f6037012c13656e2a37187a47dfd3373b109b70c49f65095a27c58940ac` |
| Expanded coarse candidate index | SHA-256 `8351b6400246db5a5e973ac7da34d36e0db5bb2af3637c3ef2273006d04c33aa` |
| Model execution contract | base `1.2.0` plus scientific-correctness overlay `1.0.0`, SHA-256 `59490dc080176a4f5655539db78edeb035e9ce02a2b6a68d95fad5c428081f59` |
| Production experiment runner | `1.0.0`, timezone/PIT-fixed, config SHA-256 `0ee0f55f86050bcbe249de5127a21c04c1bfd390cf4e97cd8ce378df5035afed` |
| Frozen supervised sample membership | SHA-256 `864af3d9aac6ea239d993ea48cd819c2185f3249957d8b81f6d8d4c3c9f3d680` |

## Coarse-search result

The frozen pooled OOF PR-AUC ranking identifies the following global coarse leader:

- family: XGBoost;
- configuration: `model_stage_v1__coarse__xgboost__004`;
- feature block: `L+D+R`;
- pooled OOF PR-AUC: `0.41167748793642267`;
- secondary pooled OOF ROC-AUC: `0.7594860513220995`.

Reference results are:

- Dummy prior pooled OOF PR-AUC: `0.1722831509228104`;
- best fixed-L2 logistic pooled OOF PR-AUC: `0.38165485192849713`;
- XGBoost leader improvement over Dummy: `0.23939433701361226`;
- XGBoost leader improvement over fixed L2: `0.03002263600792554`.

All complete candidates have 10,760 canonical OOF keys and 1,986 positive observations. OOF keys are unique within each complete candidate, scores are finite, and only validation years 2015–2020 occur in the coarse run.

## Families qualified for conditional refinement

The frozen qualification rule selected exactly these families; refinement has not yet been executed:

1. XGBoost — leader `model_stage_v1__coarse__xgboost__004`, block `L+D+R`;
2. HistGradientBoosting — leader `model_stage_v1__coarse__hist_gradient_boosting__007`, block `L+D+R`;
3. Random Forest — leader `model_stage_v1__coarse__random_forest__003`, block `L+D+R`.

## Next steps

1. Execute only the preregistered conditional-refinement candidate IDs for the three qualified families.
2. Rank the common pool of coarse candidates and activated refinement candidates according to the frozen execution contract.
3. Perform the preregistered seed-confirmation stage when required by that contract, without changing candidate identities or search spaces.
4. Execute the separately preregistered QNN stages under the frozen resource ledger when that stage is authorized.
5. Defer final calibration/thresholding, interpretability, robustness, and thesis reporting analyses to their preregistered stages.
6. Keep external validation 2021–2022 and test 2023–2024 closed until their explicitly authorized stages.

## Access status

Feature years 2021–2024 remain closed. The coarse search did not open external validation or test data, and no subsequent step is authorized by this status document to access those periods.

# Secondary development thesis reporting v1.0.0

## Purpose and boundary

This reporting-only package converts the formally frozen secondary-development
v1.1.6/v1.1.7 results into thesis-ready CSV tables, PNG/SVG figures, and a
concise Polish interpretation. It reads only completed development artifacts
for OOF years 2015--2020.

The package cannot fit a model, change the 96-task roster, rerank a family,
alter the frozen primary decisions, or open feature years 2021--2024. Before
generation it requires both the post-coarse v1.3.0 and secondary v1.1.7 result
freezes to pass.

## Output plan

The canonical output is:

```text
reports/secondary_development_thesis_v1_0_0
```

It contains ten tables:

1. phase completeness;
2. PCA-matched controls;
3. XGBoost robustness;
4. QNN structural robustness;
5. all 84 fold-level secondary fit metrics;
6. common grouped permutation importance;
7. top-five permutation features for each of eight families;
8. detailed Elastic Net, TreeSHAP and Integrated Gradients results;
9. QNN encoded-component sensitivity;
10. QNN PCA loadings.

Six figures are emitted as both PNG and SVG. The report manifest pins every
generated file by size and SHA-256.

## Comparison rule

The secondary fit variants use seed `20260818`, while the frozen XGBoost and
QNN headline references average three seeds. Any reported delta is therefore
explicitly descriptive and not a direct seed-matched comparison. Target
robustness variants additionally change the label and positive prevalence, so
their PR-AUC levels are not directly comparable to the primary target.

No secondary result may activate tuning or reselection. Analytic-simulator QNN
results do not support a quantum-advantage claim.

## Commands

Commit the reporting package before opening result artifacts in generation:

```bash
bash scripts/run_secondary_development_thesis_report_v1_0_0.sh verify-package
bash scripts/run_secondary_development_thesis_report_v1_0_0.sh generate
bash scripts/run_secondary_development_thesis_report_v1_0_0.sh verify-output
```

After committing the generated report, use:

```bash
bash scripts/run_secondary_development_thesis_report_v1_0_0.sh verify-output-committed
```

Generation refuses an existing output directory. This prevents a reporting
rerun from silently overwriting an already reviewed result bundle.

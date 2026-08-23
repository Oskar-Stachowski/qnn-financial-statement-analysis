# Secondary development execution v1.1.1 — input-key amendment

## Status

Status: **FROZEN EXECUTABLE AMENDMENT**

Version 1.1.1 corrects one fail-closed interface mismatch discovered by the
first real-data preflight of v1.1.0. The additional train-only robustness-target
projection stores its identity as `(cik10, feature_year)`, while the frozen model
sample uses `research_universe_company_year_id` in the equivalent `CIK10-YYYY`
form.

No model was fitted during the failed preflight. The failure occurred while
validating requested CSV columns, before target values were merged or any
execution stage began. Feature years 2021–2024 remained closed.

The v1.1.0 package and freeze remain byte-identical. This amendment inherits
their full 96-task roster, workers, output schemas, resume rules, resource caps,
and failure policy by exact SHA-256.

## Exact correction

The source columns are now:

```text
cik10, feature_year
```

The adapter validates a 1–10 digit CIK, pads it to ten ASCII digits, validates
that the year is within 2011–2020, and constructs:

```text
{CIK10 zero-padded}-{feature_year}
```

For example, `880460` and `2013` become `0000880460-2013`. The constructed key
must be unique and must align one-to-one with the already frozen supervised
sample. Any mismatch, duplicate, missing component, non-train year, or status
other than `available` fails closed.

The amendment does not change target values, sample membership, folds,
preprocessing, hyperparameters, QNN structure, task identities, or scientific
methodology.

## Commands

Use v1.1.1 for all further work:

```bash
bash scripts/run_secondary_analyses_v1_1_1.sh verify
bash scripts/run_secondary_analyses_v1_1_1.sh preflight
```

After a successful preflight, the frozen execution order is:

```bash
bash scripts/run_secondary_analyses_v1_1_1.sh pca-controls
bash scripts/run_secondary_analyses_v1_1_1.sh interpretability
bash scripts/run_secondary_analyses_v1_1_1.sh robustness-classical
bash scripts/run_secondary_analyses_v1_1_1.sh robustness-qnn
bash scripts/run_secondary_analyses_v1_1_1.sh report
```

The default output root is
`data/model_runs/secondary_development_v1_1_1`. The incomplete v1.1.0 preflight
directory has a different immutable execution identity and must not be reused or
mixed with v1.1.1 outputs.

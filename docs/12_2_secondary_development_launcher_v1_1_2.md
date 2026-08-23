# Secondary development execution launcher v1.1.2

## Status and scope

Status: **FROZEN OPERATIONAL LAUNCHER AMENDMENT**

The v1.1.1 input-key amendment is scientifically and structurally unchanged.
Its first command invoked the Python module with `python -m`, which loads it as
`__main__`. During its self-verification the same file was imported under its
canonical module name, creating a second module instance and rebinding the
historical v1.1.0 loader. The command stopped inside package verification,
before output identity creation and before any project-data file was opened.

Version 1.1.2 changes only the launcher. It imports the v1.1.1 module exactly
once under its canonical name using `python -c`, verifies the launcher package
as committed and clean, then calls the unchanged v1.1.1 `main()` function.

No configuration, join logic, target value, sample membership, task identity,
fold, model, or methodology changes in v1.1.2. The 96-task roster and v1.1.1
output root remain unchanged.

## Command

Use this script for all subsequent operations:

```bash
bash scripts/run_secondary_analyses_v1_1_2.sh verify
bash scripts/run_secondary_analyses_v1_1_2.sh preflight
```

After preflight passes:

```bash
bash scripts/run_secondary_analyses_v1_1_2.sh pca-controls
bash scripts/run_secondary_analyses_v1_1_2.sh interpretability
bash scripts/run_secondary_analyses_v1_1_2.sh robustness-classical
bash scripts/run_secondary_analyses_v1_1_2.sh robustness-qnn
bash scripts/run_secondary_analyses_v1_1_2.sh report
```

The launcher verifier hashes its script, verifier, tests, documentation, and
freeze manifest. Real modes additionally require these files and the inherited
v1.1.1/v1.1.0 packages to be committed and unmodified before any project-data
read.

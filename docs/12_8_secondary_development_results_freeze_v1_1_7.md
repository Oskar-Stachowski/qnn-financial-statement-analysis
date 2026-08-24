# Secondary development v1.1.7 results freeze

## Status and scope

This package formally freezes the completed preregistered secondary-development
execution and corrected compact report. The scientific scope remains
development OOF 2015--2020. Feature years 2021--2024 were not opened, and this
freeze does not authorize access to them.

The authoritative machine-readable manifest is:

```text
configs/secondary_development_v1_1_7_results_freeze_manifest.yaml
```

## Frozen bundle

The freeze covers:

- all 96 complete task-result JSON files from execution v1.1.6;
- all four complete phase manifests;
- 84 OOF prediction artifacts and 30 neural checkpoints;
- preprocessing, PCA and worker evidence retained under the v1.1.6 output;
- the QNN resource ledger and TreeSHAP repair/carry-forward manifests;
- the corrected v1.1.7 report and run manifest;
- a deterministic inventory of every file, byte size and SHA-256 below both
  output roots.

Large outputs remain outside Git. Their exact inventory is committed as
`reports/secondary_development_v1_1_7/artifact_inventory.json`. The verifier
requires the current local file set to match that inventory exactly, including
the absence of extra or missing files.

## Frozen scientific boundary

- Secondary results cannot change the frozen primary family ranking, QNN
  ansatz, feature blocks, hyperparameters, preprocessing, calibration, or
  threshold.
- Analytic-simulator results do not establish quantum advantage.
- No secondary result is an independent protected-period evaluation.
- The v1.1.6 output remains immutable source evidence; v1.1.7 changes only the
  compact report hash reference.

## Verification

Run the read-only committed verifier:

```bash
python -m src.modeling.verify_secondary_development_results_freeze_v1_1_7 --require-committed
```

The only accepted verdict is
`SECONDARY_DEVELOPMENT_V1_1_7_RESULTS_INTEGRITY_PASS`.

The verifier hashes opaque model files and reads only completed development
artifacts bounded to 2011--2020. It never fits a model or opens protected-period
data.

## Next boundary

The next permitted tasks are derivative reporting from these frozen results and
an incremental byte-preserving backup. Reopening 2021--2022 additionally
requires resolution of the documented access incident and a committed
`DATA_ACCESS_GATE_2021_2022_REOPEN_V1`. The 2023--2024 feature and label gates
remain separate and closed.

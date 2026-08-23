# Post-coarse v1.3.0 development-results freeze

## Status and scope

The refinement, QNN Q1/Q2, classical confirmation, QNN confirmation, final
development ranking, calibration and threshold fitting, paired clustered
bootstrap, and compact reporting stages are complete. This freeze records their
exact compact artifacts before any secondary robustness execution or reopening
of protected feature years.

The frozen result scope is development-only OOF 2015--2020. Feature years
2021--2024 were not opened. This freeze does not authorize access to those
periods and does not replace any gate required by data access policy v1.1.0.

## Frozen bundle

The machine-readable authority is
`configs/post_coarse_v1_3_0_results_freeze_manifest.yaml`. It records byte sizes
and SHA-256 identities for:

- compact top-level post-coarse manifests, selection artifacts, ledgers,
  calibration/ranking summaries, and clustered-bootstrap outputs;
- the complete compact report under `reports/post_coarse_v1_3_0/`;
- the deterministic verifier, its test, and this specification.

Large fitted objects, per-row OOF predictions, fold checkpoints, numeric worker
arrays, and stderr/stdout evidence remain local under the ignored model-run
directory. They are not copied into Git. Their identities remain reachable from
the frozen compact manifests and must be retained in an external byte-preserving
backup.

## Frozen outcome invariants

- 30 primary classical/MLP confirmation slots are complete.
- Three QNN block representatives are complete.
- All 36 QNN confirmation fold fits completed on their initial attempt.
- The final primary development ranking contains nine family representatives
  and nine calibration/threshold records.
- The neural comparison contains the refined MLP and three QNN blocks, with four
  calibration/threshold records.
- The paired clustered bootstrap contains 2,000 valid of 2,000 requested
  replicates, with no degenerate replicate.
- The compact report contains eight CSV tables and a Markdown summary.

These results cannot change the frozen model roster, ansatz, feature blocks,
hyperparameters, preprocessing, calibration method, or threshold rule.

## Verification

Run the read-only verifier in the classical environment:

```bash
.venv-classical/bin/python -m src.modeling.verify_post_coarse_results_freeze
```

The only accepted verdict is `POST_COARSE_V1_3_0_RESULTS_INTEGRITY_PASS`.

## Next execution boundary

The next permitted work remains restricted to the preregistered secondary
development analyses: PCA-matched controls, interpretability, and robustness.
Their executable controller, output schemas, synthetic tests, resource policy,
and failure states must be versioned and frozen before execution. Protected
period access remains subject to the separate gates in
`configs/data_access_policy_v1_1_0.yaml`.

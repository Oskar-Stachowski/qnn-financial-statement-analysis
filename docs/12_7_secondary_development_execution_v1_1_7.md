# Secondary development execution v1.1.7

## Purpose

Version 1.1.7 is a report-only integrity amendment over the completed v1.1.6
secondary execution. All 96 v1.1.6 task results and all four phase manifests
are complete and unchanged. No estimator is fitted, no source result is copied
or modified, no project input data is read, and protected feature years
2021–2024 remain closed.

The corrected report output root is:

```text
data/model_runs/secondary_development_v1_1_7
```

The complete v1.1.6 execution root remains unchanged as source evidence.

## Defect and repair

The inherited report writer first serialized the base report and recorded its
SHA-256 in `run_manifest.json`. Amendment wrappers then added the v1.1.4,
v1.1.5 and v1.1.6 metadata fields to the report and serialized it again, but
did not refresh the recorded hash. Consequently, the completed v1.1.6 report
contained 96/96 successful tasks while its run manifest referenced the exact
pre-amendment report bytes.

Version 1.1.7 validates the exact known mismatch, all 96 task-result identities
and hashes, the four complete phase manifests, the committed v1.1.6 package,
execution identity and preflight. It then:

1. builds the final report including all amendment metadata;
2. serializes that final report atomically;
3. records the SHA-256 returned by that exact serialization;
4. serializes the run manifest atomically;
5. re-reads both files and fails closed unless the recorded and actual report
   hashes are identical.

## Commands

```bash
bash scripts/run_secondary_analyses_v1_1_7.sh verify
bash scripts/run_secondary_analyses_v1_1_7.sh report
bash scripts/run_secondary_analyses_v1_1_7.sh verify-report
```

The `report` command performs no model fit and does not open project input
data. It reads only the already completed v1.1.6 result and manifest JSON files.

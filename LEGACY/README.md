# Legacy archive

This directory preserves superseded source code, notebooks, instructions, and
methodological notes that predate the frozen `target_candidate_v2_pit_b`
v1.0.0 workflow.

The files are retained for provenance and historical comparison only. They are
not part of the active pipeline and must not be used to construct the final
modeling dataset or train final models without an explicit methodological
review.

## Contents

- `pre_pit_modeling/` — the earlier modeling-dataset builder, notebook,
  configuration, and Commit 08 instruction based on a superseded target;
- `pre_freeze_methodology/` — working notes written before the final PIT-B
  target and survivorship-bias decisions;
- `intermediate_pit_b_audit/` — one-off audit helpers superseded by the active
  steps `15`-`19` and the frozen audit evidence.

`LEGACY/` is deliberately visible to Git. Ignoring the entire directory would
leave these files stored only on one workstation and would conflict with the
purpose of preserving them.

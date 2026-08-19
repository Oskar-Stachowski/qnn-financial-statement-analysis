# Target PIT-B — resolver correction v1.1.0 (train-only)

Status: frozen for feature years 2011–2020. Data access policy v1.1.0 remains controlling; no values from feature years 2021–2024 were opened and no model was trained.

The target definition and all target labels remain unchanged. The correction affects only A-current primitive provenance used by continuity/vintage diagnostics: 87 company-years in the original target-train projection and 108 company-years in the historical-universe target application. Target status changes: 0. Label changes: 0.

The pair resolver was audited separately. The train target contains one selected `controlled_cross_tag_equivalence` liabilities pair; resolver v1.1.0 leaves it selected. Thus the analogous cross-tag code defect has no observed target-pair incidence in the train period.

Historical target v1.0.0 files and manifests remain immutable. For first model training, the authoritative train references are the v1.1.0 artifacts listed in `configs/target_candidate_v2_pit_b_v1_1_0_train_freeze_manifest.yaml`. Application to later periods is deferred to the appropriate access gates.

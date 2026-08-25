# Primary thesis reporting v1.0.0 — GATED_SUCCESSOR_MODE

This package is a deterministic navigation and evidence bundle, not thesis prose.

- `tables/01_development_family_ranking.csv`: frozen development-only family ranking.
- `tables/02_protected_period_metrics.csv`: separate spent-development and holdout rows.
- `tables/03_period_boundaries.csv`: claim boundaries and mandatory labels.
- `tables/04_reporting_availability.csv`: available and deliberately omitted outputs.
- `tables/05_package_provenance.csv`: opaque provenance for upstream packages.
- `evidence_ledger.csv` / `evidence_ledger.json`: number-level source mapping.

Never pool development, spent-development and holdout into one estimand. The bundle
does not support an independent-test, fully-unseen-holdout or quantum-advantage claim.

# Resolver / raw X_t v1.1.0 — train-only impact audit

Data access policy: v1.1.0. Zakres analityczny: wyłącznie feature years 2011–2020. Nie trenowano modeli.

- Raw rows compared: 47,938
- Changed raw company-years: 112
- Changed current primitives: {"liabilities": 3, "net_income": 109}
- Changed derived features: {"accruals_to_assets_t": 109, "liabilities_to_assets_t": 3, "profit_margin_t": 66, "roa_t": 109}
- Pair-resolver changed company-years: 0
- Frozen target A-provenance changed company-years: 87
- Target status/label changes: 0
- Supervised sample: 19,671 -> 19,671; entered=0; exited=0
- Supervised company-years with changed feature data: 25; changed feature observations=75; new feature-value NA cells=+74
- Frozen temporal-fold membership changed: no
- Feature-value NA cell delta (raw train): +278

Detailed hashes, transition counts, missingness, class balance and fold memberships are in the JSON audit.

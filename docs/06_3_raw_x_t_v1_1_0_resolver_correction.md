# Raw point-in-time X_t v1.1.0 — fail-closed resolver correction

Status: frozen for train/internal CV, feature years 2011–2020 only. No preprocessing and no model training were performed.

Resolver v1.1.0 enforces a priority barrier: if an admissible higher-priority strategy is ambiguous, a lower-priority selected strategy cannot rescue coverage. The same barrier is present in the controlled cross-tag pair branch.

Against frozen v1, 112 train company-years change: 109 `net_income` and 3 `liabilities` primitives move from selected to ambiguous/NA. Dependent changes are `roa_t` 109, `accruals_to_assets_t` 109, `profit_margin_t` 66, and `liabilities_to_assets_t` 3. There are 278 additional raw feature-value NA cells. No pair primitive changes in train.

The full contemporary source rebuild exposed unrelated cache drift. It is quarantined as an interim candidate and is not the frozen output. The published v1.1.0 artifact starts from the content-addressed v1 train projection and admits only coverage-reducing `selected -> ambiguous` transitions whose new reason is `higher_priority_context_ambiguous`.

A same-source causal control replayed the frozen v1 resolver for all 112 admitted primitive cells. It reproduced the exact frozen status, strategy, tag, accession, and value in 112/112 cases, with zero mismatches. Therefore the admitted deltas are attributable to the v1.1 priority barrier rather than to the unrelated cache drift.

Historical v1 remains immutable and is superseded only for first model training and later versioned applications. Validation/test application remains closed under data access policy v1.1.0.

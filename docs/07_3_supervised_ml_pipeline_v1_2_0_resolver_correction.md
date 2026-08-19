# Supervised ML pipeline v1.2.0 — resolver correction

Pipeline v1.2.0 is the authoritative corrective train/internal-CV overlay for the first model training. It inherits the frozen v1 sample rule, feature blocks, preprocessing, temporal CV, metrics, inference, and robustness policies. It also inherits data access policy v1.1.0.

The train sample remains exactly 19,671 observations. No row enters or exits; membership SHA-256 remains `864af3d9aac6ea239d993ea48cd819c2185f3249957d8b81f6d8d4c3c9f3d680`. Class balance remains 3,623 positive and 16,048 negative observations (18.4179757% positive).

Feature data change in 25 supervised company-years (75 feature observations). The feature-value missingness increase is 74 cells: `roa_t` +25 NA, `accruals_to_assets_t` +25 NA, and `profit_margin_t` +24 NA. The remaining changed feature observation already had an NA value and changes status only, from `missing` to `ambiguous`. Sample membership does not change. All six PIT-safe expanding-window train/validation memberships and their counts/hashes are unchanged. Preprocessing has not been fitted; it will still be fitted from zero inside each fold as preregistered.

The spent 2021–2022 period and the 2023–2024 holdout remain sealed. This correction neither authorizes the production runner nor starts model training.

# Secondary development — raport wyników do pracy magisterskiej

Raport jest wyłącznie opisową analizą zamrożonych wyników OOF 2015–2020. Nie uruchamia modeli, nie otwiera lat 2021–2024 i nie zmienia rankingu głównego.

## Kompletność

Wszystkie **96/96** prerejestrowanych zadań zakończyły się statusem `COMPLETE`: 12 PCA-matched controls, 12 zadań interpretowalności, 48 klasycznych fitów robustness i 24 fitów strukturalnych QNN.

## PCA-matched controls

- **MLP — PCA QNN**: PR-AUC **0.393227**, ROC-AUC **0.742075**.
- **Logistic fixed L2 — PCA QNN**: PR-AUC **0.381590**, ROC-AUC **0.739261**.

Zamrożona trzyseedowa referencja QNN L+D+R ma PR-AUC **0.383948**. Kontrole są jednoseedowe; różnice są opisowe i nie stanowią bezpośredniego testu seed-matched.

## Robustness XGBoost

Najwyższy opisowy PR-AUC uzyskał wariant **Target: score ≥2** (0.571492), a najniższy **Target: score ≥4** (0.259942).

Warianty definicji targetu zmieniają etykietę i częstość klasy dodatniej, dlatego ich PR-AUC nie jest bezpośrednio porównywalne z bazowym targetem. Żaden wariant nie aktywuje reselekcji.

## Robustness strukturalna QNN

- **RY_CRX_RING**: PR-AUC **0.377730**, ROC-AUC **0.742117**.
- **RY_RZ_CZ_BRICKWORK**: PR-AUC **0.376835**, ROC-AUC **0.741482**.
- **Brak splątania (identity)**: PR-AUC **0.373548**, ROC-AUC **0.741361**.
- **PCA 6 qubitów**: PR-AUC **0.372854**, ROC-AUC **0.738192**.

Wyniki pochodzą z symulatora analitycznego i nie wspierają twierdzenia o przewadze kwantowej.

## Interpretowalność

Najwyżej sklasyfikowane cechy wspólnej permutation importance:

- XGBoost: log1p_revenues_t, log_assets_t, roa_t, current_ratio_t, working_capital_to_assets_t.
- QNN: roa_t, accruals_to_assets_t, log1p_revenues_t, log_assets_t, ocf_to_assets_t.

Najważniejsze cechy według metod szczegółowych:

- Elastic Net: log_assets_t, log1p_revenues_t, current_ratio_t, asset_turnover_t, current_ratio_change_1y.
- XGBoost TreeSHAP: log1p_revenues_t, log_assets_t, roa_t, ocf_to_assets_t, revenue_growth_1y.
- MLP Integrated Gradients: log1p_revenues_t, log_assets_t, accruals_to_assets_t, current_ratio_t, asset_turnover_t.

Najwyższą średnią czułość QNN ma **pca_angle_1** (1.247809). Czułość komponentu nie jest bezpośrednią atrybucją ekonomiczną cechy; interpretację należy łączyć z tabelą loadings PCA.

## Granice wnioskowania

- Wyniki są development-only i nie są niezależnym testem temporalnym.
- Delt jednoseedowych wariantów względem trzyseedowych referencji nie należy interpretować jako testów istotności.
- Secondary results nie zmieniają modelu głównego, ansatzu, parametrów, preprocessingu, kalibracji ani progów.
- Lata 2021–2024 pozostają zamknięte.

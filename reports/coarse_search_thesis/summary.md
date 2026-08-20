# Podsumowanie wyników rozwojowych OOF

W coarse searchu najwyższy pooled OOF PR-AUC uzyskał **XGBoost** w wariancie **L+D+R** (configuration_id: `model_stage_v1__coarse__xgboost__004`): **0.411677**. Jest to prowizoryczny lider klasycznej/MLP części coarse searchu; wynik nie jest finalny.

Bezwzględna przewaga PR-AUC nad Dummy wynosi **0.239394**, a nad najlepszym fixed L2 logistic **0.030023**. Różnice te nie są automatycznie dowodem istotności statystycznej.

Dla prowizorycznego lidera roczny PR-AUC w latach 2015–2020 mieści się od **0.329695** do **0.527709** (rozstęp **0.198014**). Jest to opis zmienności między latami; bez osobnej analizy niepewności nie należy nadawać mu interpretacji testu stabilności.

Pareto frontier jakość–runtime obejmuje **9** konfiguracji. Prowizoryczny lider znajduje się na tej granicy. Nie wyznaczono arbitralnego jednego „najlepszego kompromisu”.

Do dalszego refinementu zgodnie z zapisanym manifestem kwalifikują się: **XGBoost, HistGradientBoosting, Random Forest**.

Wyników nie należy traktować jako finalnych: refinement, confirmation seeds i QNN należą do kolejnych etapów, a finalny holdout 2021–2024 nie jest używany w tej analizie.

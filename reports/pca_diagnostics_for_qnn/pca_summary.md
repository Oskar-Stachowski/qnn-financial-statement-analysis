### Podsumowanie diagnostycznej analizy PCA — train 2011–2020

1. **Narastanie wariancji.** Minimalna liczba komponentów potrzebna do przekroczenia progów opisowych wynosi: 80%: 7 komponentów; 90%: 9 komponentów; 95%: 11 komponentów. Progi nie stanowią automatycznej reguły wyboru wymiaru.

2. **PCA-4.** Wariant czterowymiarowy zachowuje **66.94%** wariancji i traci **33.06%**. Redukuje wejście z 17 do 4 wymiarów, czyli usuwa 13 wymiarów (76.47%).

3. **PCA-6.** Wariant sześciowymiarowy zachowuje **78.18%** wariancji i traci **21.82%**. Redukuje wejście z 17 do 6 wymiarów, czyli usuwa 11 wymiarów (64.71%).

4. **Błąd rekonstrukcji.** MSE rekonstrukcji wynosi **0.330622** dla PCA-4 oraz **0.218153** dla PCA-6. Dodanie PC5 i PC6 zmniejsza MSE o **0.112470**. Jest to diagnostyka kompresji, a nie jakości klasyfikacji.

5. **Struktura PC1–PC6.** Największe bezwzględne loadings tworzą następujące zestawy:
   - **PC1:** `roa_t` (+0.924), `accruals_to_assets_t` (+0.861), `ocf_to_assets_t` (+0.857)
   - **PC2:** `asset_growth_1y` (+0.724), `delta_liabilities_to_assets_1y` (-0.694), `current_ratio_change_1y` (+0.671)
   - **PC3:** `ocf_margin_t` (+0.688), `profit_margin_t` (+0.622), `asset_turnover_t` (+0.470)
   - **PC4:** `log_assets_t` (+0.555), `log1p_revenues_t` (+0.464), `current_ratio_t` (-0.386)
   - **PC5:** `asset_turnover_t` (+0.500), `revenue_growth_1y` (-0.426), `current_ratio_t` (-0.336)
   - **PC6:** `revenue_growth_1y` (+0.702), `current_ratio_t` (-0.448), `current_ratio_change_1y` (-0.379)

6. **Dodatkowa informacja PC5–PC6.** PC5 i PC6 zachowują łącznie dodatkowe **11.25%** wariancji. Pominięta przez PCA-4 struktura odpowiada wzorcom cech wymienionym dla PC5 i PC6; nie oznacza to automatycznej użyteczności predykcyjnej.

7. **Kompromis.** PCA-4 zapewnia silniejszą kompresję i wejście odpowiadające 4 kubitom, natomiast PCA-6 zachowuje większą część wariancji kosztem dwóch dodatkowych wymiarów i 6 kubitów. Ostateczne porównanie musi zostać wykonane w leakage-safe walidacji modeli.

8. **Ograniczenia interpretacyjne.** PCA maksymalizuje wariancję wejścia, a nie rozdzielność `target=0/1`; znak komponentu jest arbitralny; loadings nie dowodzą zależności przyczynowych ani przydatności predykcyjnej; analiza dotyczy warunkowej, zamrożonej próby supervised 2011–2020. Aktualny zamrożony kontrakt QNN kieruje do PCA także wskaźniki braków, więc 17-cechowe wyniki diagnostyczne nie są numeryczną kopią produkcyjnej reprezentacji.

9. **Granica wykorzystania.** Obiekty preprocessingu i PCA dopasowane w tym notebooku nie są zapisywane. W finalnym eksperymencie imputer, scaler, PCA i model muszą być fitowane wyłącznie na części treningowej każdego folda, a walidacja może być jedynie transformowana.

# Stabilność seedów i koszt obliczeniowy — raport rozszerzony v1.0.0

Raport powstał wyłącznie z zamrożonych artefaktów development OOF 2015–2020. Nie przeprowadzono treningu, nie uruchomiono benchmarku i nie otwarto lat chronionych 2021–2024.

To techniczny arkusz dowodowy, nie tekst pracy. Autor samodzielnie tworzy opis, interpretację i wnioski.

## Najważniejsze wyniki

- QNN: średnia AP między seedami 0.380254, SD 0.004010, zakres 0.375901–0.383798; ensemble AP 0.383948.
- Mediana worker-runtime końcowego QNN dla sześciu foldów: 1.745 h; XGBoost: 7.922 s. Opisowy mnożnik: 793.1×.
- Pełna zarejestrowana ścieżka QNN Q1/Q2/confirmation: 45.877 h. Nie jest to wartość porównywalna z czasem pojedynczego fitu XGBoost.

## Granice interpretacji

- Statystyki z trzech seedów są opisowe i nie są przedziałami ufności.
- SD między seedami i SD między foldami czasowymi opisują różne źródła zmienności.
- Ensemble AP policzono po uśrednieniu raw score; nie jest średnią AP z seedów.
- Czasy pochodzą z historycznych wykonań w różnych środowiskach i nie są kontrolowanym benchmarkiem sprzętowym.
- QNN działał na analitycznym symulatorze lightning.qubit, nie na sprzęcie kwantowym.

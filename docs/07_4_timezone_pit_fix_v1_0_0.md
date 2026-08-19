# SEC Acceptance Time / PIT fix v1.0.0

Zakres poprawki jest ograniczony do reprezentacji czasu i temporalnych
membershipów train 2011–2020. Definicja targetu, etykiety, `X_t`, cechy,
preprocessing, roster modeli i przestrzenie hiperparametrów pozostają bez zmian.

## Semantyka

- Naive SEC Acceptance Time jest interpretowany jako `America/New_York` z
  regułami IANA DST.
- Jawny offset zachowuje reprezentowany instant.
- Konflikt między źródłami dla tego samego accession jest rozstrzygany przez
  zamrożony instant anchora `X_t`, aby cecha i target używały jednego zegara.
- Wszystkie wartości są serializowane i porównywane w canonical UTC (`Z`).
- Niejednoznaczny albo nieistniejący lokalny czas kończy operację fail-closed.

## Wynik train-only

- Supervised sample pozostaje `n=19 671`, positives `3 623`, negatives `16 048`.
- Target labels i statusy: bez zmian.
- Hash `X_t`: bez zmian.
- `fold_2015`: train `6 470 -> 6 468`; usunięto
  `0000880460-2013` i `0001472601-2013`.
- `fold_2019`: train `14 784 -> 14 783`; usunięto
  `0001586495-2016`.
- Pozostałe cztery foldy: membership bez zmian.
- We wszystkich sześciu foldach liczba naruszeń obu inwariantów PIT wynosi zero.

Nie otwierano feature years 2021–2024 i nie trenowano modeli.

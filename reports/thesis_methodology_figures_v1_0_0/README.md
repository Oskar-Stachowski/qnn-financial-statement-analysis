# Figury metodologiczne do pracy — v1.0.0

Status: **COMPLETE — REPORTING ONLY**

Pakiet zawiera trzy wersjonowane grafiki w formatach PNG i SVG:

1. pipeline badawczy i zabezpieczenia przed leakage;
2. oś czasu ról development / spent development / temporal holdout;
3. waterfall selekcji głównej próby modelowej.

Grafiki powstały z zamrożonych konfiguracji i kompaktowych tabel agregatowych.
Nie otwarto danych wierszowych okresów chronionych, nie dopasowano modeli i nie
przeliczono wyników predykcyjnych.

## Zalecane użycie

- SVG: finalny skład DOCX/PDF, jeśli edytor zachowuje grafikę wektorową.
- PNG: wersja kompatybilna, 200 dpi.
- Tabele CSV: audyt liczb, etykiet i źródeł użytych na wykresach.

Waterfall dotyczy próby modelowej train 2011–2020: `47 938 → 19 784 → 19 671`.
Nie należy utożsamiać jego mianownika z pełnym filing-first universe 2011–2024,
dla którego target availability wynosi `26 602 / 64 901 = 40,99%`.

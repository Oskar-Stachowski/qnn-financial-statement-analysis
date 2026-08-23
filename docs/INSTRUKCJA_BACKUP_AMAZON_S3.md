# Backup i kontrolowane przenoszenie dużych danych do Amazon S3

Stan i decyzja: 2026-08-23.

## Stan końcowy

Dokument obejmuje dwie zakończone operacje w tym samym bucketcie S3:

| Snapshot | Zakres | Stan lokalny | Walidacja odtworzenia |
|---|---|---|---|
| `raw-sec-snapshots/20260823T153845Z_git-34c19582` | całe pierwotne `data/raw` | duże payloady usunięte po walidacji; pozostawiono dwa pliki śledzone przez Git | `PASS`, 170 482 pliki |
| `project-artifact-snapshots/20260823T165347Z_git-34c19582` | całe `data/model_runs` i `data/processed` | źródła zachowane lokalnie | `PASS`, 18 463 pliki |

Oba snapshoty przeszły checksum-enabled download, strumieniową dekompresję,
pełne wyliczenie elementów TAR i porównanie SHA-256 każdego pliku z manifestem.
Nie włączono wersjonowania ani własnej konfiguracji KMS/SSE. Pole `AES256`
zwracane przez S3 oznacza automatyczne bazowe SSE-S3 stosowane przez usługę, a
nie opcję ustawioną w poleceniach projektu.

## Część A — przeniesienie `data/raw`

## Krótkie potwierdzenie

Tak — możemy zarchiwizować cały aktualny folder `data/raw` i nie obejmować migracją żadnego innego folderu projektu.

Aktualny stan `data/raw`:

- 170 482 pliki,
- 31 574 786 147 bajtów danych logicznych, czyli około 29,41 GiB,
- brak dowiązań symbolicznych, plików specjalnych i pustych katalogów,
- brak aktywnego procesu zapisującego do `data/raw` w chwili audytu,
- bieżące etapy modelowania korzystają z artefaktów w `data/processed`, a nie z `data/raw`.

Pełny snapshot S3 ma objąć wszystkie pliki z `data/raw`, w tym dane SEC. Po potwierdzonym odtworzeniu usuniemy lokalnie pięć dużych katalogów i `.DS_Store`. Pozostawimy jedynie dwa pliki śledzone przez Git:

- `data/raw/.gitignore`,
- `data/raw/sec_company_tickers.json`.

Te dwa pliki również znajdą się w snapshotcie S3. Pozostawienie ich lokalnie utrzymuje czysty working tree i kosztuje około 1 MB. Usunięcie samego katalogu `data/raw` dałoby znikomy dodatkowy odzysk miejsca, a oznaczyłoby pliki repozytorium jako usunięte. Bezpieczny wariant odzyska praktycznie całe około 29,4 GiB.

## Dlaczego nie używać bezpośrednio `aws s3 mv`

`aws s3 mv` realizuje operację jako kopiowanie obiektu, a następnie usunięcie źródła. Przerwanie wieloplikowej operacji może zostawić zbiór podzielony między dysk lokalny i S3. Dlatego przeniesienie wykonujemy jako kontrolowaną sekwencję:

1. `COPY` — nieusuwający upload całego `data/raw`.
2. `VERIFY` — weryfikacja obiektów i manifestów.
3. `RESTORE TEST` — pełne odtworzenie lub równoważna pełna walidacja strumieniowa i kontrola SHA-256.
4. `DELETE LOCAL` — dopiero wtedy usunięcie dużych lokalnych danych.

Dokumentacja AWS: [zachowanie `aws s3 mv`](https://docs.aws.amazon.com/cli/latest/reference/s3/mv.html) i [kontrola integralności obiektów](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html).

## Zakres migracji

Do S3 trafi dokładnie obecna zawartość:

| Składnik | Liczba plików | Bajty logiczne | Przybliżony rozmiar |
|---|---:|---:|---:|
| `companyfacts` | 3 712 | 14 896 900 286 | 13,874 GiB |
| `sec_filings` | 112 083 | 7 109 395 015 | 6,621 GiB |
| `sec_historical_universe` | 25 512 | 4 849 417 972 | 4,516 GiB |
| `research_universe_target_application` | 20 309 | 3 215 932 921 | 2,995 GiB |
| `sec_submissions` | 8 863 | 1 502 083 497 | 1,399 GiB |
| trzy pliki w katalogu głównym `data/raw` | 3 | 1 056 456 | około 1 MB |
| **Razem** | **170 482** | **31 574 786 147** | **29,406 GiB** |

Poza zakresem pozostają między innymi:

- `data/processed`,
- `artifacts`,
- `reports`,
- `results`,
- `configs`, `src`, `scripts`, `tests` i `docs`,
- środowiska Pythona, cache oraz repozytorium `.git`.

## Założenia bezpieczeństwa

- Podczas tworzenia manifestu i archiwów żaden proces nie może zapisywać do `data/raw`.
- Nie analizujemy ani nie deserializujemy zawartości danych. Używamy wyłącznie kopiowania bajtów, liczników oraz SHA-256.
- Bucket ma mieć włączone Block Public Access.
- Nie włączamy S3 Versioning. Stan bucketu powinien być `Unversioned` albo `Suspended`.
- Nie konfigurujemy KMS, SSE-C ani jawnej opcji `--sse` w poleceniach uploadu. Amazon S3 automatycznie stosuje bazowe SSE-S3 do nowych obiektów i nie pozwala go wyłączyć; nie wymaga to klucza ani konfiguracji po naszej stronie.
- Rola użyta do uploadu nie powinna mieć prawa usuwania obiektów z docelowego prefiksu.
- Do zakończenia testu odtworzenia obiekty pozostają w klasie `STANDARD`; nie ustawiamy reguły `Expiration`.
- Usunięcie lokalne następuje tylko po pełnym teście odtworzenia z wynikiem zero błędów.

## 1. Zmienne robocze — wykonano

Punkt został wykonany 2026-08-23. Nazwa bucketu jest poprawna składniowo i ma 53 znaki. Utworzono osobny identyfikator snapshotu oraz pusty katalog kontrolny.

Stan zmiennych zapisano w `/tmp/qnn_raw_s3_migration.env`, ponieważ zmienne eksportowane przez osobny proces powłoki nie przechodzą automatycznie do kolejnych poleceń. Przed rozpoczęciem następnego punktu należy wczytać ten plik:

```bash
source /tmp/qnn_raw_s3_migration.env
```

Przygotowane wartości:

```text
QNN_S3_BUCKET=qnn-fs-analysis-raw-data-498283326935-eu-central-1-an
QNN_RAW_SNAPSHOT_ID=20260823T153845Z_git-34c19582
QNN_S3_PREFIX=s3://qnn-fs-analysis-raw-data-498283326935-eu-central-1-an/qnn-financial-statement-analysis/raw-sec-snapshots/20260823T153845Z_git-34c19582
QNN_CONTROL_DIR=/tmp/qnn_raw_s3_control.fM2ba7
```

Poniższy blok dokumentuje sposób odtworzenia punktu 1 po restarcie komputera lub usunięciu plików z `/tmp`:

```bash
set -euo pipefail

export QNN_PROJECT_ROOT="/Users/oskarstachowski/qnn-financial-statement-analysis"
export QNN_RAW_DIR="$QNN_PROJECT_ROOT/data/raw"
export QNN_AWS_REGION="eu-central-1"
export QNN_S3_BUCKET="qnn-fs-analysis-raw-data-498283326935-eu-central-1-an"

cd "$QNN_PROJECT_ROOT"
export QNN_RAW_SNAPSHOT_ID="$(date -u +%Y%m%dT%H%M%SZ)_git-$(git rev-parse --short=8 HEAD)"
export QNN_S3_PREFIX="s3://$QNN_S3_BUCKET/qnn-financial-statement-analysis/raw-sec-snapshots/$QNN_RAW_SNAPSHOT_ID"
export QNN_CONTROL_DIR="$(mktemp -d /tmp/qnn_raw_s3_control.XXXXXX)"
export QNN_STATE_FILE="/tmp/qnn_raw_s3_migration.env"

printf 'Snapshot: %s\nPrefix: %s\nControl: %s\n' \
  "$QNN_RAW_SNAPSHOT_ID" "$QNN_S3_PREFIX" "$QNN_CONTROL_DIR"

printf '%s\n' \
  "export QNN_PROJECT_ROOT=\"$QNN_PROJECT_ROOT\"" \
  "export QNN_RAW_DIR=\"$QNN_RAW_DIR\"" \
  "export QNN_AWS_REGION=\"$QNN_AWS_REGION\"" \
  "export QNN_S3_BUCKET=\"$QNN_S3_BUCKET\"" \
  "export QNN_RAW_SNAPSHOT_ID=\"$QNN_RAW_SNAPSHOT_ID\"" \
  "export QNN_S3_PREFIX=\"$QNN_S3_PREFIX\"" \
  "export QNN_CONTROL_DIR=\"$QNN_CONTROL_DIR\"" \
  > "$QNN_STATE_FILE"
```

Nie używaj bucketu o przypadkowej nazwie ani prefiksu współdzielonego z innym snapshotem.

## 2. Kontrole przed uploadem — wykonano

Punkt został wykonany 2026-08-23 z wynikiem `PASS`. Raport zapisano w `$QNN_CONTROL_DIR/PREUPLOAD_CHECKS.txt`.

Potwierdzony stan:

- AWS account `498283326935`, principal `arn:aws:iam::498283326935:user/oskar-stachowski`,
- bucket jest dostępny i znajduje się w `eu-central-1`,
- wszystkie cztery ustawienia Block Public Access mają wartość `true`,
- bucket jest `Unversioned`, zgodnie z decyzją o niewłączaniu wersjonowania,
- Object Ownership ma wartość `BucketOwnerEnforced`,
- wymagane narzędzia są dostępne; AWS CLI ma wersję `2.34.29`,
- nie wykryto procesu zapisującego ani otwartych plików w `data/raw`,
- zakres nadal wynosi dokładnie 170 482 pliki i 31 574 786 147 bajtów,
- brak symlinków, plików specjalnych i pustych katalogów,
- `git status --short -- data/raw` jest pusty,
- `data/raw` zawiera tylko osiem oczekiwanych pozycji najwyższego poziomu.

Poniższe polecenia pozostają zapisem wykonanych kontroli i służą do ich ponowienia bezpośrednio przed uploadem.

### Narzędzia i tożsamość AWS

```bash
command -v aws
command -v tar
command -v zstd
command -v shasum

aws --version
aws sts get-caller-identity
aws s3api head-bucket --bucket "$QNN_S3_BUCKET"
```

### Ochrona bucketu

Sprawdź konfigurację:

```bash
aws s3api get-public-access-block \
  --bucket "$QNN_S3_BUCKET"

aws s3api get-bucket-versioning \
  --bucket "$QNN_S3_BUCKET"

aws s3api get-bucket-ownership-controls \
  --bucket "$QNN_S3_BUCKET"
```

Wymagany wynik operacyjny:

- wszystkie cztery ustawienia Block Public Access mają wartość `true`,
- odpowiedź wersjonowania nie zawiera `Enabled`; akceptujemy brak `Status` albo `Suspended`,
- ownership ma preferowane ustawienie `BucketOwnerEnforced`.

Nie zmieniamy konfiguracji wersjonowania ani szyfrowania bucketu. Polecenia transferu nie przekażą żadnej opcji KMS/SSE. Bazowego SSE-S3 narzuconego automatycznie przez usługę Amazon S3 nie można wyłączyć.

### Brak aktywnego zapisu

```bash
ps -axo pid,ppid,state,etime,%cpu,%mem,time,command | \
  rg -i '[p]ython|[b]ash scripts|[a]ws s3|[c]url|[w]get|data/raw'

lsof +D "$QNN_RAW_DIR"
```

Jeśli pojawi się downloader, proces modyfikujący dane albo otwarty deskryptor do zapisu, nie zaczynaj snapshotu. Samo odczytywanie przez polecenia kontrolne jest dopuszczalne.

### Kontrola dokładnego zakresu

```bash
find "$QNN_RAW_DIR" -mindepth 1 -maxdepth 1 -print | LC_ALL=C sort

find "$QNN_RAW_DIR" -type l -print
find "$QNN_RAW_DIR" ! -type d ! -type f -print
find "$QNN_RAW_DIR" -type d -empty -print

git status --short -- data/raw
git ls-files data/raw
```

Lista najwyższego poziomu ma zawierać dokładnie:

```text
data/raw/.DS_Store
data/raw/.gitignore
data/raw/companyfacts
data/raw/research_universe_target_application
data/raw/sec_company_tickers.json
data/raw/sec_filings
data/raw/sec_historical_universe
data/raw/sec_submissions
```

Kontrole dowiązań, plików specjalnych i pustych katalogów mają nie zwrócić nic. Jeśli stan zmienił się od audytu, ponownie policz zakres i nie używaj starych wartości oczekiwanych.

## 3. Manifest źródła — wykonano

Punkt został wykonany 2026-08-23 z wynikiem `PASS`. Hashowanie trwało 220 sekund. Raport zapisano w `$QNN_CONTROL_DIR/MANIFEST_VALIDATION.txt`.

Potwierdzony wynik:

- 170 482 rekordy SHA-256 dla 170 482 unikalnych ścieżek,
- zero nieprawidłowych rekordów SHA-256,
- zbiór ścieżek manifestu jest dokładnie zgodny z `PAYLOAD_FILES.txt`,
- 31 574 786 147 bajtów danych źródłowych,
- commit `34c195822ba9bd0b9f91303f15ed827e4906dddd`,
- `git status --short -- data/raw` pozostał pusty,
- manifest SHA-256 ma 25 534 369 bajtów, a lista plików 14 282 557 bajtów.

Poniższe polecenia pozostają zapisem wykonanej procedury i umożliwiają jej bezpieczne powtórzenie.

Manifest zapisujemy poza `data/raw`, żeby pozostał dostępny po lokalnym czyszczeniu.

```bash
cd "$QNN_PROJECT_ROOT"

find data/raw -type f -exec shasum -a 256 {} + \
  > "$QNN_CONTROL_DIR/PAYLOAD_SHA256SUMS"

find data/raw -type f -print | LC_ALL=C sort \
  > "$QNN_CONTROL_DIR/PAYLOAD_FILES.txt"

QNN_RAW_FILE_COUNT="$(find data/raw -type f | wc -l | tr -d ' ')"
QNN_RAW_LOGICAL_BYTES="$(find data/raw -type f -exec stat -f '%z' {} + | awk '{s += $1} END {print s+0}')"

printf 'files=%s\nbytes=%s\n' \
  "$QNN_RAW_FILE_COUNT" "$QNN_RAW_LOGICAL_BYTES" \
  > "$QNN_CONTROL_DIR/PAYLOAD_TOTALS.txt"

git rev-parse HEAD > "$QNN_CONTROL_DIR/GIT_COMMIT.txt"
date -u +'%Y-%m-%dT%H:%M:%SZ' > "$QNN_CONTROL_DIR/CREATED_AT_UTC.txt"

cat "$QNN_CONTROL_DIR/PAYLOAD_TOTALS.txt"
find "$QNN_CONTROL_DIR" -maxdepth 1 -type f \
  ! -name CONTROL_SHA256SUMS \
  -exec shasum -a 256 {} + \
  > "$QNN_CONTROL_DIR/CONTROL_SHA256SUMS"
```

Przed dalszym krokiem wynik musi wynosić:

```text
files=170482
bytes=31574786147
```

Jeśli wynik jest inny, zatrzymaj procedurę. Oznacza to zmianę źródła względem audytu.

## 4. Upload bez lokalnego pliku tymczasowego — wykonano

Punkt został wykonany 2026-08-23 z wynikiem `PASS`. Sześć archiwów i katalog kontrolny przesłano do `$QNN_S3_PREFIX`. Raport zapisano w `$QNN_CONTROL_DIR/UPLOAD_SUMMARY.txt`.

Podsumowanie transferu:

| Archiwum | Rozmiar obiektu S3 | Czas |
|---|---:|---:|
| `companyfacts.tar.zst` | 624 169 644 B | 262 s |
| `sec_filings.tar.zst` | 297 270 116 B | 137 s |
| `sec_historical_universe.tar.zst` | 608 704 294 B | 257 s |
| `research_universe_target_application.tar.zst` | 208 009 293 B | 83 s |
| `sec_submissions.tar.zst` | 168 134 851 B | 71 s |
| `raw_root_files.tar.zst` | 208 893 B | 2 s |
| **Razem** | **1 906 497 091 B** | **812 s** |

Transfer 31 574 786 147 bajtów danych źródłowych trwał 13 min 32 s. Osiągnięto łączny współczynnik kompresji około 16,56×. Wszystkie sześć wywołań zakończyło się kodem zero, a `head-object` zwrócił rozmiar i checksumę SHA-256 dla każdego obiektu.

Przed właściwym transferem wystąpiło jedno bezpieczne zatrzymanie: pusty `KeyCount` został zwrócony przez AWS CLI jako `None` zamiast `0`. Warunek poprawiono i uruchomiono ponownie; w pierwszej próbie nie wysłano żadnych danych.

Poniższe polecenia pozostają zapisem wykonanej procedury i umożliwiają jej odtworzenie dla nowego, pustego prefiksu.

Pięć dużych katalogów kompresujemy osobno. Dzięki temu błąd wymaga ponowienia tylko jednego fragmentu, a na niemal pełnym dysku nie powstaje druga lokalna kopia.

```bash
set -euo pipefail
cd "$QNN_PROJECT_ROOT"

for QNN_RAW_PART in \
  companyfacts \
  sec_filings \
  sec_historical_universe \
  research_universe_target_application \
  sec_submissions
do
  printf 'Uploading %s\n' "$QNN_RAW_PART"
  COPYFILE_DISABLE=1 tar -C "$QNN_PROJECT_ROOT" -cf - "data/raw/$QNN_RAW_PART" | \
    zstd -T0 -3 | \
    aws s3 cp - "$QNN_S3_PREFIX/archives/$QNN_RAW_PART.tar.zst" \
      --region "$QNN_AWS_REGION" \
      --checksum-algorithm SHA256 \
      --only-show-errors
done
```

Trzy pliki z katalogu głównego pakujemy razem:

```bash
COPYFILE_DISABLE=1 tar -C "$QNN_PROJECT_ROOT" -cf - \
  data/raw/.DS_Store \
  data/raw/.gitignore \
  data/raw/sec_company_tickers.json | \
  zstd -T0 -3 | \
  aws s3 cp - "$QNN_S3_PREFIX/archives/raw_root_files.tar.zst" \
    --region "$QNN_AWS_REGION" \
    --checksum-algorithm SHA256 \
    --only-show-errors
```

Nie dodawaj do tych poleceń `--sse`, `--sse-kms-key-id` ani opcji szyfrowania po stronie klienta. S3 zastosuje automatyczne SSE-S3 bez konfiguracji w poleceniu.

Następnie wyślij manifesty kontrolne:

```bash
aws s3 cp "$QNN_CONTROL_DIR/" "$QNN_S3_PREFIX/control/" \
  --recursive \
  --region "$QNN_AWS_REGION" \
  --checksum-algorithm SHA256 \
  --only-show-errors
```

## 5. Weryfikacja uploadu — wykonano

Punkt został wykonany 2026-08-23 z wynikiem `PASS`. Raporty zapisano w `$QNN_CONTROL_DIR/S3_VERIFICATION_POINT5.txt` oraz `$QNN_CONTROL_DIR/S3_ARCHIVE_HEADS_RECHECK.tsv`.

Niezależna walidacja potwierdziła:

- dokładnie sześć oczekiwanych kluczy archiwów i brak dodatkowych kluczy w `archives/`,
- łączny rozmiar archiwów równy 1 906 497 091 bajtów,
- zgodność rozmiaru oraz checksumy SHA-256 każdego archiwum z metadanymi zapisanymi bezpośrednio po uploadzie,
- typ checksumy `COMPOSITE` dla pięciu archiwów multipart i `FULL_OBJECT` dla `raw_root_files.tar.zst`,
- klasę składowania `STANDARD`,
- brak `VersionId`, zgodnie ze stanem `Unversioned`,
- zero aktywnych uploadów multipart dla prefiksu snapshotu,
- dokładnie 16 zdalnych obiektów kontrolnych o łącznym rozmiarze 39 824 965 bajtów, zgodnych z lokalnym zbiorem kontrolnym istniejącym przed rozpoczęciem punktu 5.

Pierwsza wersja walidatora zatrzymała się bezpiecznie przed oceną wyniku, ponieważ łączone zapytanie AWS CLI zwróciło `None` dla pola licznika. Zapytania o liczbę i rozmiar rozdzielono; nie wykonano żadnej modyfikacji S3.

Pełny test pobrania, dekompresji i porównania 170 482 plików nie jest częścią punktu 5 i nadal pozostaje wymagany w punkcie 6.

Poniższe polecenia pozostają skróconym zapisem wykonanej kontroli.

Najpierw sprawdź listę i metadane wszystkich sześciu archiwów:

```bash
aws s3 ls "$QNN_S3_PREFIX/archives/" \
  --recursive \
  --summarize \
  --human-readable

for QNN_ARCHIVE_NAME in \
  companyfacts.tar.zst \
  sec_filings.tar.zst \
  sec_historical_universe.tar.zst \
  research_universe_target_application.tar.zst \
  sec_submissions.tar.zst \
  raw_root_files.tar.zst
do
  aws s3api head-object \
    --bucket "$QNN_S3_BUCKET" \
    --key "qnn-financial-statement-analysis/raw-sec-snapshots/$QNN_RAW_SNAPSHOT_ID/archives/$QNN_ARCHIVE_NAME" \
    >> "$QNN_CONTROL_DIR/S3_ARCHIVE_HEADS.jsonl"
done
```

Samo istnienie obiektów nie wystarcza do usunięcia danych lokalnych. Wymagany jest pełny test odtworzenia.

## 6. Pełny test odtworzenia strumieniowego — wykonano

Ze względu na brak 40 GiB wolnego miejsca pełne odtworzenie na filesystem zastąpiono pełną walidacją strumieniową. Punkt został wykonany 2026-08-23 z wynikiem `PASS`. Raport zapisano w `$QNN_CONTROL_DIR/STREAMING_RESTORE_REPORT.txt`, a log przebiegu w `$QNN_CONTROL_DIR/STREAMING_RESTORE_STATUS.log`.

Zastosowany potok dla każdego archiwum:

```text
S3 GET z checksum-mode ENABLED → zstd -d → parser tar → SHA-256 każdego pliku → odrzucenie bajtów
```

Zdalny `PAYLOAD_SHA256SUMS` został najpierw pobrany z kontrolą integralności i porównany bajt po bajcie z lokalnym manifestem. Następnie każde archiwum przeszło przez potok z `set -o pipefail`, bez zapisywania odtworzonych danych na dysku.

Wynik:

| Archiwum | Pliki | Bajty zweryfikowane | Czas |
|---|---:|---:|---:|
| `companyfacts.tar.zst` | 3 712 | 14 896 900 286 | 39 s |
| `sec_filings.tar.zst` | 112 083 | 7 109 395 015 | 21 s |
| `sec_historical_universe.tar.zst` | 25 512 | 4 849 417 972 | 31 s |
| `research_universe_target_application.tar.zst` | 20 309 | 3 215 932 921 | 12 s |
| `sec_submissions.tar.zst` | 8 863 | 1 502 083 497 | 13 s |
| `raw_root_files.tar.zst` | 3 | 1 056 456 | 1 s |
| **Razem** | **170 482** | **31 574 786 147** | **122 s wraz z kontrolą manifestu** |

Warunki zaliczenia spełnione:

- sześć pobrań zakończyło się kodem zero z `--checksum-mode ENABLED`,
- sześć strumieni zstd i tar zakończyło się kodem zero,
- potwierdzono dokładnie 170 482 oczekiwane i unikalne ścieżki,
- potwierdzono dokładnie 31 574 786 147 bajtów,
- SHA-256 każdego pliku jest zgodne z manifestem,
- brak plików brakujących, dodatkowych, zduplikowanych i innych niż regularne,
- nie zapisano żadnego trwałego payloadu lokalnego; tymczasową kopię manifestu usunięto.

Test nie materializował plików na filesystemie, ale jest akceptowany jako pełny test integralności odtworzenia, ponieważ audyt źródła wykazał brak symlinków, plików specjalnych i pustych katalogów. Standardowa materializacja pozostaje możliwa w przyszłości zgodnie z sekcją 8.

Po zaliczeniu testu raporty kontrolne dosłano do S3. Marker `COMPLETE.json` przesłano jako ostatni obiekt, pobrano ponownie z `--checksum-mode ENABLED` i porównano bajt po bajcie z lokalnym markerem. Checksum SHA-256 markera to `qWCaG2NAmIM0J/Ix6jIjtedNXlJtpiR/MxjUbn+Tkro=`. Snapshot zawiera łącznie 28 obiektów. Warunek przejścia do punktu 7 jest spełniony.

## 7. Lokalne zwolnienie miejsca — wykonano

Punkt wykonano 2026-08-23 z wynikiem `PASS`, po ponownym sprawdzeniu zdalnego markera, braku aktywnych uploadów multipart, braku otwartych plików oraz czystego stanu Git.

Rezultat:

- usunięto wyłącznie `companyfacts`, `sec_filings`, `sec_historical_universe`, `research_universe_target_application`, `sec_submissions` i `.DS_Store` wewnątrz `data/raw`,
- rozmiar alokowany `data/raw` spadł z 31 194 960 KiB do 1 028 KiB,
- według `du` odzyskano 31 193 932 KiB, czyli około 29,75 GiB,
- wolne miejsce raportowane przez filesystem wzrosło z 6 119 064 KiB do 37 421 448 KiB, czyli o około 29,85 GiB,
- wykorzystanie dysku spadło z 97% do 81%,
- pozostały dokładnie dwa pliki: `.gitignore` i `sec_company_tickers.json`, łącznie 1 050 308 bajtów logicznych,
- `git status --short -- data/raw` pozostał pusty.

Poniższe polecenia są historycznym zapisem wykonanego kroku destrukcyjnego. Nie uruchamiaj ich ponownie bez nowego pełnego cyklu kontroli, jeśli dane zostaną wcześniej odtworzone.

Kontrola bezpośrednio przed usunięciem:

```bash
aws s3 ls "$QNN_S3_PREFIX/COMPLETE.json"

ps -axo pid,ppid,state,etime,%cpu,%mem,time,command | \
  rg -i '[p]ython|[b]ash scripts|[a]ws s3|[c]url|[w]get|data/raw'

git status --short -- data/raw
du -sh \
  "$QNN_PROJECT_ROOT/data/raw/companyfacts" \
  "$QNN_PROJECT_ROOT/data/raw/sec_filings" \
  "$QNN_PROJECT_ROOT/data/raw/sec_historical_universe" \
  "$QNN_PROJECT_ROOT/data/raw/research_universe_target_application" \
  "$QNN_PROJECT_ROOT/data/raw/sec_submissions"
```

Usuń wyłącznie jawnie wskazane duże składniki wewnątrz `data/raw`:

```bash
rm -rf -- \
  /Users/oskarstachowski/qnn-financial-statement-analysis/data/raw/companyfacts \
  /Users/oskarstachowski/qnn-financial-statement-analysis/data/raw/sec_filings \
  /Users/oskarstachowski/qnn-financial-statement-analysis/data/raw/sec_historical_universe \
  /Users/oskarstachowski/qnn-financial-statement-analysis/data/raw/research_universe_target_application \
  /Users/oskarstachowski/qnn-financial-statement-analysis/data/raw/sec_submissions

rm -f -- \
  /Users/oskarstachowski/qnn-financial-statement-analysis/data/raw/.DS_Store
```

Nie usuwaj katalogu projektu, nie usuwaj całego `data` i nie używaj globu. Pozostaw lokalnie śledzone przez Git pliki `.gitignore` i `sec_company_tickers.json`.

Kontrola po usunięciu:

```bash
git status --short -- data/raw
du -sh data/raw
df -h .
```

Oczekiwany rezultat:

- `git status` nie pokazuje zmian w `data/raw`,
- `data/raw` zajmuje około 1 MB,
- wolne miejsce wzrasta o około 29,4 GiB.

## 8. Odtworzenie do repozytorium, gdy będzie potrzebne

Najpierw sprawdź marker kompletności, następnie odtwórz sześć archiwów. Polecenie jest analogiczne do testu, ale katalogiem docelowym jest projekt:

```bash
aws s3 ls "$QNN_S3_PREFIX/COMPLETE.json"

for QNN_ARCHIVE_NAME in \
  companyfacts.tar.zst \
  sec_filings.tar.zst \
  sec_historical_universe.tar.zst \
  research_universe_target_application.tar.zst \
  sec_submissions.tar.zst \
  raw_root_files.tar.zst
do
  aws s3 cp "$QNN_S3_PREFIX/archives/$QNN_ARCHIVE_NAME" - \
    --region "$QNN_AWS_REGION" \
    --checksum-mode ENABLED \
    --only-show-errors | \
    zstd -d | \
    tar -C "$QNN_PROJECT_ROOT" -xf -
done

cd "$QNN_PROJECT_ROOT"
shasum -a 256 -c "$QNN_CONTROL_DIR/PAYLOAD_SHA256SUMS"
```

Jeśli lokalny katalog kontrolny już nie istnieje, najpierw pobierz manifest z S3:

```bash
mkdir -p "$QNN_CONTROL_DIR"
aws s3 cp "$QNN_S3_PREFIX/control/" "$QNN_CONTROL_DIR/" \
  --recursive \
  --region "$QNN_AWS_REGION" \
  --checksum-mode ENABLED \
  --only-show-errors
```

## 9. Retencja po zakończeniu projektu

Po pełnym sprawdzeniu snapshotu można rozważyć regułę Lifecycle przenoszącą archiwa do tańszej klasy składowania. Nie należy ustawiać automatycznego usunięcia. Klasy archiwalne wydłużają i komplikują odtworzenie, dlatego zmianę klasy wykonujemy dopiero po zakończeniu aktywnych prac i udokumentowaniu procedury restore.

Dokumentacja AWS: [ograniczenia przejść Lifecycle](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-transition-general-considerations.html).

## Kryterium końcowe

Migracja zakończyła się wynikiem `PASS`; wszystkie kryteria zostały spełnione:

1. S3 zawiera sześć archiwów, manifesty i marker `COMPLETE.json`.
2. Pełna walidacja strumieniowa potwierdziła dokładnie 170 482 pliki i 31 574 786 147 bajtów.
3. Wszystkie sumy SHA-256 są zgodne.
4. Lokalne duże katalogi zostały usunięte dopiero po zaliczeniu restore testu.
5. `git status --short -- data/raw` pozostaje pusty.

W ten sposób przenosimy cały ciężki zasób `data/raw` — i tylko ten zasób — bez naruszania artefaktów potrzebnych do dalszych etapów modelowania.

## Część B — backup `data/model_runs` i `data/processed`

### B.1. Zakres i lokalizacja

Po zakończeniu post-coarse wykonano osobny snapshot wszystkich pozostałych
dużych artefaktów projektu. Nie jest to migracja z usunięciem źródła. Lokalne
katalogi pozostają potrzebne do analiz wtórnych i nie zostały zmodyfikowane.

Docelowy prefiks:

```text
s3://qnn-fs-analysis-raw-data-498283326935-eu-central-1-an/qnn-financial-statement-analysis/project-artifact-snapshots/20260823T165347Z_git-34c19582
```

Zakres:

| Archiwum | Źródło | Pliki | Bajty logiczne | Rozmiar obiektu S3 |
|---|---|---:|---:|---:|
| `data_model_runs.tar.zst` | `data/model_runs` | 18 453 | 10 904 312 515 | 3 188 266 039 B |
| `data_processed.tar.zst` | `data/processed` | 10 | 2 492 970 442 | 170 686 351 B |
| **Razem** | oba katalogi | **18 463** | **13 397 282 957** | **3 358 952 390 B** |

Archiwa zajmują około 3,13 GiB, czyli około 25,1% logicznego rozmiaru źródła.

### B.2. Upload i kontrola obiektów

Przed uploadem potwierdzono brak otwartych plików i aktywnych procesów
zapisujących, brak symlinków, plików specjalnych i pustych katalogów oraz pusty
docelowy prefiks. Manifest `PAYLOAD_SHA256SUMS` objął dokładnie 18 463 unikalne
ścieżki i został zweryfikowany przed transferem.

Oba archiwa wysłano bez lokalnego pliku pośredniego potokiem:

```text
tar → licznik bajtów → zstd -T0 -3 → aws s3 cp z SHA-256
```

Transfer trwał 742 sekundy. Po każdym uploadzie wykonano `head-object` z
checksum mode, sprawdzono rozmiar i obecność checksumy SHA-256. Stan bezpośrednio
po backupie obejmował 14 obiektów: dwa archiwa, 11 plików kontrolnych oraz
`BACKUP_COMPLETE.json`. Nie pozostał żaden aktywny multipart upload.

Marker `BACKUP_COMPLETE.json` zachowuje stan z chwili bezpośrednio po uploadzie.
Dlatego jego pole `full_restore_test` ma historyczną wartość `not_run`. Nie jest
to aktualny stan końcowy — późniejsze zaliczenie testu dokumentuje osobny,
niemodyfikujący pierwszego markera plik `RESTORE_VALIDATION_COMPLETE.json`.

### B.3. Pełna walidacja odtworzenia — wykonano

Pełną walidację wykonano 2026-08-23 bez materializowania danych na lokalnym
filesystemie. Dla obu archiwów zastosowano potok:

```text
S3 GET z checksum-mode ENABLED
→ licznik skompresowanych bajtów
→ zstd -d
→ strumieniowy parser TAR
→ SHA-256 każdego regularnego pliku
→ porównanie z PAYLOAD_SHA256SUMS
→ odrzucenie bajtów
```

Wynik:

| Archiwum | Pobrane bajty | Pliki zweryfikowane | Bajty po dekompresji | Wynik |
|---|---:|---:|---:|---|
| `data_model_runs.tar.zst` | 3 188 266 039 | 18 453 | 10 904 312 515 | `PASS` |
| `data_processed.tar.zst` | 170 686 351 | 10 | 2 492 970 442 | `PASS` |
| **Razem** | **3 358 952 390** | **18 463** | **13 397 282 957** | **PASS** |

Właściwe pobieranie, dekompresja i hashowanie trwały około 7 min 26 s.
Potwierdzono:

- zero niezgodnych sum SHA-256,
- zero brakujących, dodatkowych i zduplikowanych członów TAR,
- dokładną zgodność liczby plików i liczby bajtów logicznych,
- brak deserializacji wartości analitycznych,
- brak lokalnego wypakowania i brak modyfikacji źródeł.

Do prefiksu dosłano trzy małe rekordy walidacyjne:

```text
RESTORE_VALIDATION_COMPLETE.json
restore_validation/data_model_runs.json
restore_validation/data_processed.json
```

Po ich zapisaniu snapshot zawiera 17 obiektów o łącznym rozmiarze
3 366 708 498 bajtów i zero niedokończonych multipart uploadów. Terminalny
marker `RESTORE_VALIDATION_COMPLETE.json` został pobrany ponownie z kontrolą
integralności i porównany bajt po bajcie. Jego lokalny SHA-256 to:

```text
57e909ae31859d2502b1011cac14087b6f68a7d3a9a37cb2364ee4ca9f56e6d9
```

### B.4. Odtworzenie w przyszłości

Nie odtwarzaj archiwów bezpośrednio na istniejące `data/model_runs` albo
`data/processed`, ponieważ takie wypakowanie mogłoby połączyć dwa różne stany.
Użyj nowego, pustego katalogu stagingowego z co najmniej 14 GiB wolnego miejsca.

```bash
set -euo pipefail

export QNN_AWS_REGION="eu-central-1"
export QNN_S3_BUCKET="qnn-fs-analysis-raw-data-498283326935-eu-central-1-an"
export QNN_ARTIFACT_SNAPSHOT_ID="20260823T165347Z_git-34c19582"
export QNN_ARTIFACT_S3_PREFIX="s3://$QNN_S3_BUCKET/qnn-financial-statement-analysis/project-artifact-snapshots/$QNN_ARTIFACT_SNAPSHOT_ID"
export QNN_RESTORE_ROOT="/pełna/ścieżka/do/nowego-pustego-katalogu"
export QNN_RESTORE_CONTROL_DIR="$QNN_RESTORE_ROOT/control"

test -d "$QNN_RESTORE_ROOT"
test -z "$(find "$QNN_RESTORE_ROOT" -mindepth 1 -print -quit)"
mkdir -p "$QNN_RESTORE_CONTROL_DIR"

aws s3 cp "$QNN_ARTIFACT_S3_PREFIX/control/" "$QNN_RESTORE_CONTROL_DIR/" \
  --recursive \
  --region "$QNN_AWS_REGION" \
  --checksum-mode ENABLED \
  --only-show-errors

for QNN_ARCHIVE_NAME in \
  data_model_runs.tar.zst \
  data_processed.tar.zst
do
  aws s3 cp "$QNN_ARTIFACT_S3_PREFIX/archives/$QNN_ARCHIVE_NAME" - \
    --region "$QNN_AWS_REGION" \
    --checksum-mode ENABLED \
    --only-show-errors | \
    zstd -d | \
    tar -C "$QNN_RESTORE_ROOT" -xf -
done

cd "$QNN_RESTORE_ROOT"
shasum -a 256 -c "$QNN_RESTORE_CONTROL_DIR/PAYLOAD_SHA256SUMS"
```

Oczekiwany wynik końcowy to 18 463 rekordy `OK`. Dopiero wtedy można rozważać
zamianę katalogów stagingowych z katalogami roboczymi. Operacja zamiany wymaga
osobnej kontroli ścieżek i nie jest częścią tej instrukcji.

### B.5. Polityka lokalnego usuwania

Snapshot potwierdza możliwość odtworzenia, ale nie oznacza zgody na automatyczne
usunięcie lokalnych źródeł. `data/model_runs/classical_mlp_coarse_v1`,
`data/model_runs/post_coarse_v1_3_0` oraz `data/processed` pozostają potrzebne do
PCA-matched controls, interpretowalności i robustness. Marker backupu zachowuje
`delete_local_authorized: false`.

Ewentualne późniejsze czyszczenie należy wykonać dopiero po zakończeniu i
zamrożeniu analiz wtórnych, po osobnym audycie zależności oraz po wykonaniu
nowego backupu ich wyników. Nie używaj rekurencyjnego usuwania całego
`data/model_runs` ani `data/processed`.

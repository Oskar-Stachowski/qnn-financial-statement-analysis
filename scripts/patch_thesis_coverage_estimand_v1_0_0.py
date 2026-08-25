#!/usr/bin/env python3
"""Apply the approved coverage/estimand factual correction to thesis DOCX files.

The patch is intentionally limited to two existing paragraphs. It preserves
the surrounding OOXML, paragraph formatting, runs, styles and package parts.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]

CHAPTER_4 = ROOT / "thesis/chapters/Rozdzial_4_Metodyka_badania_empirycznego.docx"
CHAPTER_5 = ROOT / "thesis/chapters/Rozdzial_5_Ewaluacja_modeli.docx"

CHAPTER_4_OLD = (
    ". Przepływ liczebności od wszystkich historycznych zgłoszeń kotwiczących "
    "do końcowej próby uczenia nadzorowanego oraz różnice w pokryciu danych "
    "pomiędzy latami i grupami spółek przedstawiono w podrozdziale 5.1."
)
CHAPTER_4_NEW = (
    ". W finalnym filing-first universe z lat 2011–2024 target był dostępny dla "
    "26 602 z 64 901 obserwacji (40,99%). W puli train 2011–2020 liczebność "
    "zmniejszyła się z 47 938 do 19 784 po wymogu dostępnego targetu (41,27%), "
    "a następnie do 19 671 po dodatkowym wymogu dopuszczalnego statusu cech "
    "(41,03%). Przepływ liczebności oraz różnice w pokryciu danych pomiędzy "
    "latami i grupami spółek przedstawiono w podrozdziale 5.1."
)

CHAPTER_5_OLD = (
    "Do próby włączono wyłącznie obserwacje spełniające zamrożone kryteria "
    "przynależności do historycznego uniwersum, posiadające dostępny target oraz "
    "dopuszczony status cech X_t. Oznacza to, że estymand ma charakter warunkowy: "
    "wyniki odnoszą się do spółka-lat, dla których można było wiarygodnie "
    "odtworzyć zarówno informacje finansowe dostępne w momencie predykcji, jak i "
    "porównywalną etykietę przyszłego pogorszenia. Nie należy utożsamiać próby z "
    "całą populacją emitentów raportujących do SEC ani z pełnym zbiorem spółek "
    "znajdujących się w trudnej sytuacji finansowej."
)
CHAPTER_5_NEW = (
    "Do próby włączono wyłącznie obserwacje spełniające zamrożone kryteria "
    "przynależności do historycznego uniwersum, posiadające dostępny target oraz "
    "dopuszczony status cech X_t. Pula train 2011–2020 obejmowała 47 938 "
    "kwalifikujących się obserwacji spółka-rok. Po wymogu dostępnego targetu "
    "pozostało 19 784 obserwacji (41,27%), a po dodatkowym wymogu dopuszczalnego "
    "statusu cech X_t — 19 671 (41,03%). W pełnym finalnym filing-first universe "
    "z lat 2011–2024 target był dostępny dla 26 602 z 64 901 obserwacji (40,99%). "
    "Historyczna wartość 52,46% odnosiła się wyłącznie do starszej populacji "
    "freeze-gate 14 122/26 917 i nie opisuje finalnego universe ani próby "
    "modelowej. Oznacza to, że estymand ma charakter warunkowy: wyniki odnoszą "
    "się do spółka-lat, dla których można było wiarygodnie odtworzyć zarówno "
    "informacje finansowe dostępne w momencie predykcji, jak i porównywalną "
    "etykietę przyszłego pogorszenia. Nie należy utożsamiać próby z całą "
    "populacją emitentów raportujących do SEC ani z pełnym zbiorem spółek "
    "znajdujących się w trudnej sytuacji finansowej."
)


def _read_document_xml(path: Path) -> bytes:
    with zipfile.ZipFile(path) as package:
        return package.read("word/document.xml")


def _replacement_state(xml: bytes, old: str, new: str) -> str:
    old_count = xml.count(old.encode("utf-8"))
    new_count = xml.count(new.encode("utf-8"))
    if old_count == 1 and new_count == 0:
        return "pending"
    if old_count == 0 and new_count == 1:
        return "applied"
    raise RuntimeError(
        f"Unexpected replacement state: old_count={old_count}, new_count={new_count}"
    )


def _patch_package(path: Path, old: str, new: str) -> bool:
    document_xml = _read_document_xml(path)
    state = _replacement_state(document_xml, old, new)
    if state == "applied":
        return False

    patched_xml = document_xml.replace(old.encode("utf-8"), new.encode("utf-8"), 1)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}_coverage_estimand_", suffix=".docx", dir=path.parent
    )
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
            temporary_path, "w"
        ) as target:
            target.comment = source.comment
            for member in source.infolist():
                payload = (
                    patched_xml
                    if member.filename == "word/document.xml"
                    else source.read(member.filename)
                )
                target.writestr(member, payload)
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return True


def _check(path: Path, old: str, new: str) -> None:
    state = _replacement_state(_read_document_xml(path), old, new)
    if state != "applied":
        raise RuntimeError(f"Correction has not been applied to {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("apply", "check"))
    args = parser.parse_args()

    patches = (
        (CHAPTER_4, CHAPTER_4_OLD, CHAPTER_4_NEW),
        (CHAPTER_5, CHAPTER_5_OLD, CHAPTER_5_NEW),
    )
    if args.command == "apply":
        for path, old, new in patches:
            changed = _patch_package(path, old, new)
            print(f"{'PATCHED' if changed else 'ALREADY_PATCHED'} {path.relative_to(ROOT)}")
    else:
        for path, old, new in patches:
            _check(path, old, new)
            print(f"PASS {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

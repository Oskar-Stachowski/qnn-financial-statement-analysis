from __future__ import annotations

import csv
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as package:
        xml = package.read("word/document.xml").decode("utf-8")
    return "".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", xml, re.DOTALL))


def test_selection_flow_matches_successor_values() -> None:
    path = ROOT / "reports/classical_eda_for_thesis/tables/01_selection_flow.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert int(rows[0]["n"]) == 47_938
    assert int(rows[2]["n"]) == 19_784
    assert int(rows[2]["pominiete_wobec_poprzedniego_etapu"]) == 28_154
    assert int(rows[3]["n"]) == 19_671
    assert int(rows[3]["pominiete_wobec_poprzedniego_etapu"]) == 113
    assert round(float(rows[2]["udzial_w_raw_pct"]), 2) == 41.27
    assert round(float(rows[3]["udzial_w_raw_pct"]), 2) == 41.03


def test_successor_document_records_final_universe_and_historical_boundary() -> None:
    text = (
        ROOT / "docs/14_1_coverage_estimand_correction_v1_0_0.md"
    ).read_text(encoding="utf-8")
    for required in (
        "26 602",
        "64 901",
        "40,99%",
        "19 784",
        "19 671",
        "41,03%",
        "14 122 / 26 917",
        "52,46%",
        "CURRENT_SUCCESSOR_CORRECTION",
    ):
        assert required in text


def test_current_handoff_uses_successor_correction() -> None:
    text = (ROOT / "docs/15_author_work_handoff_v1_0_0.md").read_text(
        encoding="utf-8"
    )
    assert "docs/14_1_coverage_estimand_correction_v1_0_0.md" in text
    assert "final filing-first universe 2011--2024" in text
    assert "26,602 / 64,901 = 40.99%" in text
    assert "19,671 / 47,938 = 41.03%" in text


def test_chapters_distinguish_current_and_historical_coverage() -> None:
    chapter_4 = _docx_text(
        ROOT / "thesis/chapters/Rozdzial_4_Metodyka_badania_empirycznego.docx"
    )
    chapter_5 = _docx_text(
        ROOT / "thesis/chapters/Rozdzial_5_Ewaluacja_modeli.docx"
    )

    assert "26 602 z 64 901 obserwacji (40,99%)" in chapter_4
    assert "19 784 po wymogu dostępnego targetu (41,27%)" in chapter_4
    assert "19 671 po dodatkowym wymogu" in chapter_4

    assert "47 938 kwalifikujących się obserwacji spółka-rok" in chapter_5
    assert "19 784 obserwacji (41,27%)" in chapter_5
    assert "19 671 (41,03%)" in chapter_5
    assert "26 602 z 64 901 obserwacji (40,99%)" in chapter_5
    assert "Historyczna wartość 52,46%" in chapter_5
    assert "nie opisuje finalnego universe ani próby modelowej" in chapter_5

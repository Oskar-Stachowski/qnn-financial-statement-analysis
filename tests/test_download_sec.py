from pathlib import Path

import pytest

from src.data import download_sec


def test_normalize_cik_pads_to_10_digits() -> None:
    assert download_sec.normalize_cik("320193") == "0000320193"
    assert download_sec.normalize_cik(789019) == "0000789019"
    assert download_sec.normalize_cik("CIK0000320193") == "0000320193"


def test_normalize_cik_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        download_sec.normalize_cik("ABC123")

    with pytest.raises(ValueError):
        download_sec.normalize_cik("12345678901")


def test_download_company_facts_skips_cached_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_dir = tmp_path / "companyfacts"
    output_dir.mkdir()
    cached_file = output_dir / "0000320193.json"
    cached_file.write_text('{"cached": true}', encoding="utf-8")

    def fail_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("cache hit should not call SEC")

    monkeypatch.setattr(download_sec, "_fetch_company_facts", fail_fetch)

    summary = download_sec.download_company_facts(["320193"], output_dir=output_dir)

    assert summary.successes == 0
    assert summary.errors == 0
    assert summary.skipped == 1
    assert cached_file.read_text(encoding="utf-8") == '{"cached": true}'


def test_download_company_facts_force_overwrites_cached_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "companyfacts"
    output_dir.mkdir()
    cached_file = output_dir / "0000320193.json"
    cached_file.write_text('{"cached": true}', encoding="utf-8")

    def fake_fetch(*args, **kwargs):  # type: ignore[no-untyped-def]
        return b'{"fresh": true}'

    monkeypatch.setattr(download_sec, "_fetch_company_facts", fake_fetch)

    summary = download_sec.download_company_facts(["320193"], output_dir=output_dir, force=True)

    assert summary.successes == 1
    assert summary.errors == 0
    assert summary.skipped == 0
    assert cached_file.read_bytes() == b'{"fresh": true}'

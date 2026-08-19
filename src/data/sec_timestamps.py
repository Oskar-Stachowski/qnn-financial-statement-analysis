"""Canonical interpretation of SEC filing acceptance timestamps.

SEC acceptance timestamps without an explicit UTC offset are local civil time
in New York.  Offset-aware inputs retain their represented instant.  Every
timestamp leaves this module as an ISO-8601 UTC value so downstream comparisons
never depend on a process-local timezone.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import re
from typing import Any
from zoneinfo import ZoneInfo


SEC_ACCEPTANCE_TIMEZONE_NAME = "America/New_York"
CANONICAL_TIMEZONE_NAME = "UTC"

_SEC_ACCEPTANCE_TIMEZONE = ZoneInfo(SEC_ACCEPTANCE_TIMEZONE_NAME)
_COMPACT_TIMESTAMP = re.compile(r"^\d{14}(?:\.\d+)?$")


def _clean_timestamp(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "nat", "none"} else text


def _parse_timestamp_text(text: str) -> datetime:
    if _COMPACT_TIMESTAMP.fullmatch(text):
        return datetime.strptime(text[:14], "%Y%m%d%H%M%S")
    normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"Invalid SEC acceptance timestamp: {text!r}") from error


def _localize_sec_civil_time(value: datetime) -> datetime:
    first = value.replace(tzinfo=_SEC_ACCEPTANCE_TIMEZONE, fold=0)
    second = value.replace(tzinfo=_SEC_ACCEPTANCE_TIMEZONE, fold=1)
    if first.utcoffset() != second.utcoffset():
        raise ValueError(f"Ambiguous SEC acceptance local time: {value.isoformat()}")
    round_trip = (
        first.astimezone(timezone.utc)
        .astimezone(_SEC_ACCEPTANCE_TIMEZONE)
        .replace(tzinfo=None)
    )
    if round_trip != value:
        raise ValueError(f"Nonexistent SEC acceptance local time: {value.isoformat()}")
    return first


def parse_sec_acceptance_timestamp(value: Any) -> datetime | None:
    """Return the represented SEC acceptance instant as an aware UTC datetime."""

    text = _clean_timestamp(value)
    if not text:
        return None
    parsed = _parse_timestamp_text(text)
    if parsed.tzinfo is None:
        parsed = _localize_sec_civil_time(parsed)
    return parsed.astimezone(timezone.utc)


def canonical_utc_timestamp(value: datetime) -> str:
    """Serialize an aware datetime as canonical second-precision UTC."""

    if value.tzinfo is None:
        raise ValueError("Canonical UTC serialization requires an aware datetime.")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def normalize_sec_acceptance_timestamp(value: Any) -> str:
    """Normalize SEC Acceptance Time to canonical UTC, preserving missingness."""

    parsed = parse_sec_acceptance_timestamp(value)
    return "" if parsed is None else canonical_utc_timestamp(parsed)

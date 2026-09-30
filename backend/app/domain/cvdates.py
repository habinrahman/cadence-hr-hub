"""Dates read from CV text. A filename is never an input."""

from __future__ import annotations

import re
from datetime import date

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_MONTH = r"January|February|March|April|May|June|July|August|September|October|November|December"
_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_MONTH_YEAR = re.compile(rf"\b({_MONTH})\s+(20\d{{2}})\b", re.IGNORECASE)
_EXPLICIT = re.compile(
    rf"(?i)\b(?:version|revised|revision|as of|updated|dated)\b[^0-9\n]{{0,30}}"
    rf"((?:20\d{{2}}-\d{{2}}-\d{{2}})|(?:{_MONTH})\s+20\d{{2}})"
)


def dates_in_text(text: str) -> list[date]:
    found: list[date] = []
    for year, month, day in _ISO.findall(text):
        parsed = _safe_date(int(year), int(month), int(day))
        if parsed is not None:
            found.append(parsed)
    for month_name, year in _MONTH_YEAR.findall(text):
        parsed = _safe_date(int(year), _MONTHS[month_name.casefold()], 1)
        if parsed is not None:
            found.append(parsed)
    return found


def explicit_dates(text: str) -> list[date]:
    """A date that the document itself labels as a version or revision."""
    found: list[date] = []
    for raw in _EXPLICIT.findall(text):
        found.extend(dates_in_text(raw))
    return found


def is_newer(incoming: list[date], stored: list[date]) -> bool | None:
    if not incoming or not stored:
        return None
    return max(incoming) > max(stored)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None

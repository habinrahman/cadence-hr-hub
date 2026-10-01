"""Email and phone are facts a regex can pull. Names are not."""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\d().\-\s]{7,}\d)")


def normalize_email(value: str) -> str | None:
    text = value.strip().lower().removeprefix("mailto:")
    if EMAIL_RE.fullmatch(text) is None:
        return None
    return text


def normalize_phone(value: str) -> str | None:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 8 or len(digits) > 15:
        return None
    return digits


def find_emails(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in EMAIL_RE.finditer(text):
        raw = match.group(0)
        normalized = normalize_email(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            found.append((raw, normalized))
    return found


def find_phones(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for match in PHONE_RE.finditer(text):
        raw = match.group(0).strip()
        if _looks_like_date(raw):
            continue
        normalized = normalize_phone(raw)
        if normalized and normalized not in seen and normalized not in _email_digit_runs(text):
            seen.add(normalized)
            found.append((raw, normalized))
    return found


def _looks_like_date(raw: str) -> bool:
    """A CV date or date range ("2022 - 2024", "03/2021 - 06/2023", "2023-01-01") is not a phone number.

    Every digit group is a year (1950-2099) or a one- or two-digit day or month, and at least one year is present.
    Real numbers carry a group that is neither ("+1 651 279 7684", "3900 1122"), so they are kept."""
    groups = re.findall(r"\d+", raw)
    years = [g for g in groups if len(g) == 4 and 1950 <= int(g) <= 2099]
    return bool(years) and all(g in years or len(g) <= 2 for g in groups)


def _email_digit_runs(text: str) -> set[str]:
    """Phone regex can swallow digits that only appear inside an email."""
    runs: set[str] = set()
    for match in EMAIL_RE.finditer(text):
        runs.add(re.sub(r"\D", "", match.group(0)))
    return {run for run in runs if run}

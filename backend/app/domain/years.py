"""Years of experience are calculated from verified employment dates."""

from __future__ import annotations

from datetime import date


def span_years(ranges: list[tuple[date, date]]) -> float | None:
    valid = [(start, end) for start, end in ranges if end > start]
    if not valid:
        return None
    ordered = sorted(valid)
    merged: list[list[date]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    days = sum((end - start).days for start, end in merged)
    if days <= 0:
        return None
    return round(days / 365.25, 1)

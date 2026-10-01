"""Name comparison. Filenames are not an input."""

from __future__ import annotations

import re


def name_overlap(left: str | None, right: str | None) -> bool:
    """Two shared name tokens are supporting evidence. One shared token is not."""
    if not left or not right:
        return False
    left_tokens = _name_tokens(left)
    right_tokens = _name_tokens(right)
    if len(left_tokens) < 2 or len(right_tokens) < 2:
        return False
    return len(left_tokens & right_tokens) >= 2


def name_similarity(left: str | None, right: str | None) -> float | None:
    if not left or not right:
        return None
    left_tokens = _name_tokens(left)
    right_tokens = _name_tokens(right)
    if not left_tokens or not right_tokens:
        return None
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def national_phone(normalized: str) -> str:
    """Digits without the trunk or international prefix zeros: 0524449121 and 00972524449121 lose their leading 0s."""
    return normalized.lstrip("0")


def phones_match(left: str, right: str) -> bool:
    """The same number written two ways, such as +972 52 444 9121 and 052 444 9121, or +1 510 570 7106 and
    510 570 7106. The shorter national number must be the end of the longer one, at least 8 digits long, and the
    longer one may only add a country code (1 to 3 digits)."""
    if left == right:
        return True
    short, long = sorted((national_phone(left), national_phone(right)), key=len)
    return len(short) >= 8 and long.endswith(short) and len(long) - len(short) <= 3


def _name_tokens(value: str) -> set[str]:
    stop = {"cv", "resume", "the", "and"}
    tokens = set(re.findall(r"[a-z]{2,}", value.casefold()))
    return tokens - stop

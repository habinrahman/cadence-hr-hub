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


def _name_tokens(value: str) -> set[str]:
    stop = {"cv", "resume", "the", "and"}
    tokens = set(re.findall(r"[a-z]{2,}", value.casefold()))
    return tokens - stop

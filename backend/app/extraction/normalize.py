"""Clean page text for chunks. Callers keep the original pages separately."""

from __future__ import annotations

import re
from collections import Counter

_MIN_EDGE = 12
_PAGE_NUMBER = re.compile(r"(?:page\s+)?\d+(?:\s+of\s+\d+)?", re.IGNORECASE)


def normalize_document(pages: list[str]) -> list[str]:
    """Return one cleaned page per input page, including repeated-edge removal."""
    cleaned = [_clean_layout(page) for page in pages]
    return _drop_repeated_edges(cleaned)


def pages_for_chunks(pages: list[str]) -> list[str]:
    """Drop a later page whose cleaned text is an exact copy of an earlier page."""
    seen: set[str] = set()
    kept: list[str] = []
    for page in pages:
        key = " ".join(page.split())
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        kept.append(page)
    return kept


def _clean_layout(page: str) -> str:
    page = (
        page.replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\u00ad", "")
        .replace("\xa0", " ")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )
    page = re.sub(r"[ \t]+\n", "\n", page)
    page = re.sub(r"[ \t]{2,}", " ", page)
    lines = []
    for line in page.split("\n"):
        stripped = line.strip()
        if stripped and _PAGE_NUMBER.fullmatch(stripped):
            continue
        lines.append(line.rstrip())
    page = "\n".join(lines)
    page = re.sub(r"\n{3,}", "\n\n", page)
    return page.strip()


def _drop_repeated_edges(pages: list[str]) -> list[str]:
    firsts = [_edge(page, first=True) for page in pages]
    lasts = [_edge(page, first=False) for page in pages]
    repeated_headers = {line for line, count in Counter(firsts).items() if line and count >= 2}
    repeated_footers = {line for line, count in Counter(lasts).items() if line and count >= 2}
    if not repeated_headers and not repeated_footers:
        return pages
    header_kept = False
    footer_kept = False
    result: list[str] = []
    for page, header, footer in zip(pages, firsts, lasts, strict=True):
        lines = page.split("\n")
        if header in repeated_headers:
            if header_kept:
                lines = _without_edge(lines, header, first=True)
            else:
                header_kept = True
        if footer in repeated_footers and footer != header:
            if footer_kept:
                lines = _without_edge(lines, footer, first=False)
            else:
                footer_kept = True
        result.append("\n".join(lines).strip())
    return result


def _edge(page: str, *, first: bool) -> str:
    lines = [line for line in page.split("\n") if line.strip()]
    if not lines:
        return ""
    line = " ".join((lines[0] if first else lines[-1]).split())
    if len(line) < _MIN_EDGE:
        return ""
    return line


def _without_edge(lines: list[str], edge: str, *, first: bool) -> list[str]:
    indexes = range(len(lines)) if first else range(len(lines) - 1, -1, -1)
    for index in indexes:
        if " ".join(lines[index].split()) == edge:
            return lines[:index] + lines[index + 1 :]
    return lines

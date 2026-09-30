"""Turn a job description into explicit requirements. Mandatory means the text said so."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.constants import BLOCKED_FIELDS
from app.extraction.textutil import normalize_ws

_INJECTION = re.compile(r"(?i)\b(ignore previous|system prompt|shortlist all|override rules)\b")
_YEARS = re.compile(r"(\d+(?:\.\d+)?)\s*years?", re.IGNORECASE)
_AT_LEAST = re.compile(r"((?:at least|minimum of)\s+\d+(?:\.\d+)?\s+years?)", re.IGNORECASE)
_SLASH_SKILL = re.compile(
    r"(?:strong|solid)\s+([A-Za-z][A-Za-z0-9+#.]*\s*/\s*[A-Za-z][A-Za-z0-9+#.]*(?:\s*/\s*[A-Za-z][A-Za-z0-9+#.]*)*)\s+experience",
    re.IGNORECASE,
)
_WORKING_WITH = re.compile(r"working with\s+([A-Z][A-Za-z0-9+#.]*)")
_PREFERRED_SKILL = re.compile(
    r"([A-Za-z][A-Za-z0-9+#.]*)\s+experience\s+is\s+preferred",
    re.IGNORECASE,
)
_BLOCKED_LINE = re.compile(
    r"(?i)(?<![a-z])(nationality|religion|gender|ethnicity|marital status|date of birth|female|male)(?![a-z])"
)
_INLINE = re.compile(
    r"^(required skills|preferred skills|must have|minimum experience|required education|education|"
    r"required certifications|certifications|required qualifications|qualifications|other)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_HEADINGS = {
    "required skills": ("skill", "mandatory"),
    "required skill": ("skill", "mandatory"),
    "must have": ("skill", "mandatory"),
    "mandatory skills": ("skill", "mandatory"),
    "preferred skills": ("skill", "preferred"),
    "preferred skill": ("skill", "preferred"),
    "nice to have": ("skill", "preferred"),
    "required education": ("education", "mandatory"),
    "education": ("education", "preferred"),
    "required certifications": ("certification", "mandatory"),
    "certifications": ("certification", "preferred"),
    "required qualifications": ("certification", "mandatory"),
    "qualifications": ("certification", "preferred"),
    "other": ("other", "preferred"),
    "other requirements": ("other", "preferred"),
}
_INLINE_KIND = {
    "required skills": ("skill", "mandatory"),
    "must have": ("skill", "mandatory"),
    "preferred skills": ("skill", "preferred"),
    "minimum experience": ("experience", "mandatory"),
    "required education": ("education", "mandatory"),
    "education": ("education", "preferred"),
    "required certifications": ("certification", "mandatory"),
    "certifications": ("certification", "preferred"),
    "required qualifications": ("certification", "mandatory"),
    "qualifications": ("certification", "preferred"),
    "other": ("other", "preferred"),
}


@dataclass(frozen=True)
class RequirementDraft:
    label: str
    text: str
    strength: str
    quote: str


def parse_job_requirements(description: str) -> list[RequirementDraft]:
    return _unique(_parse_labeled(description) + _parse_freeform(description))


def _parse_labeled(description: str) -> list[RequirementDraft]:
    rows: list[RequirementDraft] = []
    mode: tuple[str, str] | None = None
    for raw in description.splitlines():
        line = raw.strip()
        if not line or _skip(line):
            continue
        heading = _HEADINGS.get(line.casefold().strip(":"))
        if heading is not None and ":" not in line:
            mode = heading
            continue
        inline = _INLINE.match(line)
        if inline is not None:
            kind, strength = _INLINE_KIND[inline.group(1).casefold()]
            _append(rows, kind, strength, inline.group(2), line)
            mode = None
            continue
        if mode is None:
            continue
        _append(rows, mode[0], mode[1], line, line)
    return rows


def _parse_freeform(description: str) -> list[RequirementDraft]:
    rows: list[RequirementDraft] = []
    for sentence in re.split(r"[\n.!?]+", description):
        chunk = sentence.strip()
        if not chunk or _skip(chunk):
            continue
        for match in _PREFERRED_SKILL.finditer(chunk):
            _add_skill(rows, match.group(1), "preferred", match.group(0))
        for match in _AT_LEAST.finditer(chunk):
            number = _YEARS.search(match.group(1))
            if number is not None:
                rows.append(RequirementDraft("experience", number.group(1), "mandatory", match.group(1)))
        for match in _SLASH_SKILL.finditer(chunk):
            for part in re.split(r"\s*/\s*", match.group(1)):
                _add_skill(rows, part, "mandatory", match.group(1))
        for match in _WORKING_WITH.finditer(chunk):
            _add_skill(rows, match.group(1), "mandatory", match.group(0))
    return rows


def _add_skill(rows: list[RequirementDraft], name: str, strength: str, quote: str) -> None:
    cleaned = name.strip()
    if not _kept_skill(cleaned):
        return
    if cleaned.casefold() not in quote.casefold():
        return
    rows.append(RequirementDraft("skill", cleaned[:120], strength, quote.strip()))


def quote_in_description(description: str, quote: str) -> bool:
    needle = normalize_ws(quote)
    return bool(needle) and needle in normalize_ws(description)


def _append(rows: list[RequirementDraft], label: str, strength: str, value: str, quote: str) -> None:
    if label == "experience":
        match = _YEARS.search(value)
        if match is None:
            return
        rows.append(RequirementDraft("experience", match.group(1), "mandatory", quote))
        return
    if label == "skill":
        for part in re.split(r"[,،;]", value):
            name = part.strip()
            if _kept_skill(name):
                rows.append(RequirementDraft("skill", name[:120], strength, quote))
        return
    text = value.strip()
    if len(text) < 2 or _skip(text):
        return
    rows.append(RequirementDraft(label, text[:300], strength, quote))


def _kept_skill(name: str) -> bool:
    token = name.strip()
    if len(token) < 2:
        return False
    return token.casefold() not in BLOCKED_FIELDS and _skip(token) is False


def _skip(line: str) -> bool:
    if _INJECTION.search(line):
        return True
    return _BLOCKED_LINE.search(line) is not None


def _unique(rows: list[RequirementDraft]) -> list[RequirementDraft]:
    seen: set[tuple[str, str, str]] = set()
    kept: list[RequirementDraft] = []
    for row in rows:
        key = (row.label, row.text.casefold(), row.strength)
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept

"""Read labeled sections from CV text. This is not a model and it reports no confidence."""

from __future__ import annotations

import re
from uuid import UUID

from app.extraction.contacts import find_emails, find_phones
from app.extraction.draft import (
    CertificateDraft,
    ContactDraft,
    EducationDraft,
    ExperienceDraft,
    ExtractionDraft,
    SkillDraft,
)
from app.extraction.textutil import normalize_ws

_HEADINGS = {
    "experience": "experience",
    "work experience": "experience",
    "employment": "experience",
    "employment history": "experience",
    "الخبرة": "experience",
    "خبرة": "experience",
    "education": "education",
    "التعليم": "education",
    "skills": "skills",
    "المهارات": "skills",
    "certificates": "certificates",
    "certifications": "certificates",
    "الشهادات": "certificates",
    "qualifications": "qualifications",
    "المؤهلات": "qualifications",
}
_DATE_RANGE = re.compile(
    r"(20\d{2}-\d{2}-\d{2})\s*(?:to|-|–)\s*(20\d{2}-\d{2}-\d{2}|present)",
    re.IGNORECASE,
)
_INSTRUCTION = re.compile(r"(?i)\b(ignore previous|system prompt|nationality|religion|gender)\b")


class DeterministicExtractor:
    model_name = "deterministic-section-parser"

    def extract(self, *, document_id: UUID, source_text: str, prompt_version: str) -> ExtractionDraft:
        del document_id, prompt_version
        lines = [line.strip() for line in source_text.splitlines()]
        name, name_quote = _name(lines)
        section = ""
        experiences: list[ExperienceDraft] = []
        education: list[EducationDraft] = []
        skills: list[SkillDraft] = []
        certificates: list[CertificateDraft] = []
        pending_role: str | None = None
        for line in lines:
            if not line or _INSTRUCTION.search(line):
                pending_role = None
                continue
            heading = _HEADINGS.get(line.casefold().strip(":"))
            if heading is not None:
                section = heading
                pending_role = None
                continue
            if section == "experience":
                pending_role = _take_experience(line, pending_role, experiences)
            elif section == "education":
                _take_education(line, education)
            elif section == "skills":
                _take_labeled(line, skills, SkillDraft)
            elif section == "certificates":
                _take_labeled(line, certificates, CertificateDraft, kind="certificate")
            elif section == "qualifications":
                _take_labeled(line, certificates, CertificateDraft, kind="qualification")
        return ExtractionDraft(
            display_name=name,
            display_name_quote=name_quote,
            contacts=_contacts(source_text),
            experiences=experiences,
            education=education,
            skills=skills,
            certificates=certificates,
        )


def assign_pages(draft: ExtractionDraft, pages: list[str]) -> None:
    for item in draft.experiences:
        item.page = _page(pages, item.employer_quote)
    for item in draft.education:
        item.page = _page(pages, item.institution_quote)
    for item in draft.skills:
        item.page = _page(pages, item.quote)
    for item in draft.certificates:
        item.page = _page(pages, item.quote)


def _name(lines: list[str]) -> tuple[str | None, str | None]:
    for line in lines:
        if not line or line.casefold().strip(":") in _HEADINGS or _INSTRUCTION.search(line):
            continue
        if "@" in line or any(character.isdigit() for character in line):
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and all(word[:1].isalpha() for word in words):
            return line, line
    return None, None


def _contacts(text: str) -> list[ContactDraft]:
    rows: list[ContactDraft] = []
    for raw, normalized in find_emails(text):
        rows.append(ContactDraft(kind="email", value=normalized, quote=raw))
    for raw, normalized in find_phones(text):
        rows.append(ContactDraft(kind="phone", value=normalized, quote=raw))
    return rows


def _take_experience(line: str, pending: str | None, rows: list[ExperienceDraft]) -> str | None:
    match = _DATE_RANGE.search(line)
    if match is not None and pending is not None:
        employer, title = _split_role(pending)
        end = match.group(2)
        rows.append(
            ExperienceDraft(
                employer=employer,
                employer_quote=pending,
                title=title,
                title_quote=pending if title else None,
                start_date=match.group(1),
                start_date_quote=line,
                end_date=None if end.casefold() == "present" else end,
                end_date_quote=None if end.casefold() == "present" else line,
            )
        )
        return None
    if match is None:
        return line
    return pending


def _take_education(line: str, rows: list[EducationDraft]) -> None:
    if "," in line:
        institution, credential = [part.strip() for part in line.split(",", 1)]
    else:
        institution, credential = line, None
    if not institution:
        return
    rows.append(
        EducationDraft(
            institution=institution,
            institution_quote=line,
            credential=credential,
            credential_quote=line if credential else None,
        )
    )


def _take_labeled(line: str, rows: list, factory, *, kind: str | None = None) -> None:
    parts = re.split(r"[,،;]", line)
    for part in parts:
        name = part.strip()
        if len(name) < 2 or _INSTRUCTION.search(name):
            continue
        if kind is None:
            rows.append(factory(name=name[:120], quote=line[:1000]))
        else:
            rows.append(factory(name=name[:300], quote=line[:1000], kind=kind))


def _split_role(line: str) -> tuple[str, str | None]:
    if "," not in line:
        return line, None
    employer, title = [part.strip() for part in line.split(",", 1)]
    return employer or line, title or None


def _page(pages: list[str], quote: str | None) -> int | None:
    if not quote:
        return None
    needle = normalize_ws(quote)
    for index, page in enumerate(pages, start=1):
        if needle in normalize_ws(page):
            return index
    return None


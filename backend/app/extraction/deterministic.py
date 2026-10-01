"""Read labeled sections from CV text. This is not a model and it reports no confidence."""

from __future__ import annotations

import re
import unicodedata
from uuid import UUID

from app.constants import MAX_QUOTE_LENGTH
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

_MAX_FIELD = 300  # longest institution, employer or title the draft schema accepts

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
    # Headings real CVs use for the same sections (found in the 488-file corpus).
    "professional experience": "experience",
    "professional experiences": "experience",
    "work history": "experience",
    "relevant experience": "experience",
    "work and leadership experience": "experience",
    "education and training": "education",
    "technical skills": "skills",
    "key skills": "skills",
    "core skills": "skills",
    "licenses": "certificates",
    "licenses and certifications": "certificates",
    "certifications and licenses": "certificates",
    "licenses & certifications": "certificates",
    "certifications & licenses": "certificates",
    # Sections this parser does not read. Naming them ends the section above, so their lines are not filed under it.
    **{
        heading: "other"
        for heading in (
            "interests", "hobbies", "activities", "additional information", "additional hobbies and interest", "languages",
            "references", "awards", "honors", "awards and honors", "volunteer experience", "volunteering", "projects",
            "leadership", "professional summary", "summary", "objective", "professional profile", "coursework",
            "relevant courses", "extracurricular activities", "publications",
        )
    },
}
_INLINE_HEADING = re.compile(r"^([A-Za-z؀-ۿ][A-Za-z؀-ۿ &/]{1,40}?)\s*:\s*(\S.*)$")
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
    "nov": 11, "dec": 12,
}
_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
_POINT = rf"(?:(?:19|20)\d{{2}}-\d{{2}}-\d{{2}}|{_MONTH}\s*,?\s*(?:19|20)\d{{2}}|(?:0?[1-9]|1[0-2])/(?:19|20)\d{{2}}|(?:19|20)\d{{2}})"
_END = rf"(?:{_POINT}|present|current|now|ongoing|today|date)"
# A range, never a single date: "Jun 2024 – Present", "2022 - 2024", "Jan 2023 to Mar 2025", "2024-06-01 to 2025-01-01".
_DATE_RANGE = re.compile(
    rf"(?<![\w/-])({_POINT})\s*(?:-|–|—|to|until|till)\s*({_END})(?![\w/-])",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^\s*(?:[•●▪◦‣∙·*>–—-]|\d+[.)])\s+")
_OPEN_ENDED = {"present", "current", "now", "ongoing", "today", "date"}


def normalize_cv_date(value: str, *, end: bool) -> str | None:
    """A CV date as ISO text, or None. Month-only dates use the 1st; a bare year uses 1 January.
    Nothing is guessed beyond what is written. "Present" is returned as "present" and never turned into a date here."""
    text = value.strip().casefold().rstrip(".")
    if text in _OPEN_ENDED:
        return "present" if end else None
    if re.fullmatch(r"(19|20)\d{2}-\d{2}-\d{2}", text):
        return text
    match = re.fullmatch(r"(0?[1-9]|1[0-2])/((?:19|20)\d{2})", text)
    if match:
        return f"{match.group(2)}-{int(match.group(1)):02d}-01"
    match = re.fullmatch(r"([a-z]+)\.?\s*,?\s*((?:19|20)\d{2})", text)
    if match:
        month = _MONTHS.get(match.group(1)[:4] if match.group(1).startswith("sept") else match.group(1)[:3])
        return f"{match.group(2)}-{month:02d}-01" if month else None
    if re.fullmatch(r"(19|20)\d{2}", text):
        return f"{text}-01-01"
    return None


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
            inline = _INLINE_HEADING.match(line)
            if inline is not None and _HEADINGS.get(inline.group(1).casefold()) is not None:
                # "Skills: Python, SQL" or "Certificates: CFA Level 1, Series 65": the heading and its list share a line.
                section = _HEADINGS[inline.group(1).casefold()]
                pending_role = None
                line = inline.group(2).strip()
            if section in {"skills", "certificates", "qualifications"}:
                # A heading this parser has no section for ("Honors & Awards", "Leadership & Athletics") ends the list;
                # its lines are not skills. A labelled line ("Interests: chess") is read by its label.
                if _is_other_heading(line):
                    section = "other"
                    continue
                if section == "skills":
                    line = _skill_value(line)
                    if line is None:
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


_OTHER_WORDS = frozenset(
    {
        "honors", "honours", "awards", "interests", "interest", "hobbies", "activities", "athletics", "volunteer",
        "volunteering", "extracurricular", "involvement", "clubs", "organizations", "affiliations", "achievements",
        "sports", "personal", "additional", "other", "leadership", "community", "service", "references",
    }
)
_CONNECTORS = frozenset({"&", "and", "/", "+", "-", "|"})
_NOT_SKILL_LABEL = re.compile(
    r"(?i)^(?:interests?|hobbies|activities|other activities|extracurricular(?: activities)?|honors?|awards?|achievements?|"
    r"volunteer(?:ing)?(?: experience)?|leadership|clubs?|athletics|sports|personal(?: interests)?|additional(?: information)?|"
    r"interests? (?:and|&) (?:activities|hobbies)|hobbies (?:and|&) interests?)$"
)
_SKILL_LABEL = re.compile(r"(?i)(?:skill|language|tool|software|framework|technolog|programming|coding|database|platform|tech|proficien|libraries|cloud|certif)")


def _is_other_heading(line: str) -> bool:
    """A short line made only of section-heading words and connectors: "Honors & Awards", "Leadership and Athletics"."""
    words = [w.strip(":.,").casefold() for w in line.split()]
    if not 1 <= len(words) <= 5 or line.rstrip().endswith(","):
        return False
    meaningful = [w for w in words if w not in _CONNECTORS]
    if not meaningful or not all(w in _OTHER_WORDS for w in meaningful):
        return False
    # "Leadership" on its own is a soft skill in a skills list; two or more heading words, or a colon, make a heading.
    return len(meaningful) >= 2 or line.rstrip().endswith(":") or meaningful[0] not in {"leadership", "service", "community", "other", "personal", "sports"}


def _skill_value(line: str) -> str | None:
    """"Programming Languages: Python, Java" gives "Python, Java". A label that is not about skills ("Interests: chess",
    "Other Activities: Investing Club") drops the line: it is not a skill. No label leaves the line unchanged."""
    if ":" not in line:
        return line
    label, _, value = line.partition(":")
    if len(label.split()) > 5:
        return line
    label = label.strip()
    if _NOT_SKILL_LABEL.fullmatch(label):
        return None
    if _SKILL_LABEL.search(label):
        return value.strip() or None
    return line


def assign_pages(draft: ExtractionDraft, pages: list[str]) -> None:
    for item in draft.experiences:
        item.page = _page(pages, item.employer_quote)
    for item in draft.education:
        item.page = _page(pages, item.institution_quote)
    for item in draft.skills:
        item.page = _page(pages, item.quote)
    for item in draft.certificates:
        item.page = _page(pages, item.quote)


_NAME_WINDOW = 15  # a name sits in the CV header; a capitalised line deeper down is an employer, a school or a place
_HEADER_SEPARATORS = re.compile(r"\s*[|•∙·]\s*")


def _name(lines: list[str]) -> tuple[str | None, str | None]:
    """The person's name, or None. None is better than a place or a job title: the name feeds the relationship check,
    and a wrong one links strangers who share it ("Berkeley, CA").

    In order: a header line the CV's first email address corroborates, the first name-shaped header line, then a
    corroborated line further down (two-column layouts put the name at the bottom of the text)."""
    shaped = [
        (index, name)
        for index, line in enumerate(line for line in lines if line)
        if (name := _name_line(line)) is not None
    ]
    locals_ = _email_locals(lines)
    header = [name for index, name in shaped if index < _NAME_WINDOW]
    for value in (
        next((name for name in header if _corroborated(name, locals_)), None),
        header[0] if header else None,
        next((name for _index, name in shaped if _corroborated(name, locals_)), None),
    ):
        if value is not None:
            return value, value
    return None, None


def _name_line(line: str) -> str | None:
    if line.casefold().strip(":") in _HEADINGS or _INSTRUCTION.search(line):
        return None
    # "MANIK SINGH | San Francisco, CA | 925-577-5295": the name is the first part of a one-line header.
    candidate = _HEADER_SEPARATORS.split(line, maxsplit=1)[0].strip()
    if "@" in candidate or any(character.isdigit() for character in candidate):
        return None
    words = candidate.split()
    if 2 <= len(words) <= 5 and all(_bare(word)[:1].isalpha() for word in words) and _name_shaped(candidate, words):
        return candidate
    return None


def _email_locals(lines: list[str]) -> list[str]:
    """The local part of the CV's first email address: the candidate's own. A referee's email further down must not
    vouch for the referee's name."""
    for line in lines:
        for raw, _normalized in find_emails(line):
            return [raw.split("@", 1)[0].casefold()]
    return []


def _corroborated(name: str, locals_: list[str]) -> bool:
    """At least one name token of three or more letters appears in an email address on the same CV."""
    tokens = [token for token in re.findall(r"[^\W\d_]{3,}", name.casefold())]
    return any(token in local for token in tokens for local in locals_)


def _bare(word: str) -> str:
    """A one-word nickname in brackets is part of a name: "Zhouyi (Zoey) Yang". "(Stealth Incubator)" is not."""
    if len(word) > 2 and word.startswith("(") and word.endswith(")"):
        return word[1:-1]
    return word


# Words that make a line a CV section heading ("PROFESSIONAL EXPERIENCE", "Work History", "RELEVANT COURSES"), never a name.
_SECTION_WORDS = frozenset(
    {
        "experience", "experiences", "education", "skills", "projects", "interests", "interest", "activities", "summary", "objective",
        "certifications", "certificates", "leadership", "awards", "honors", "languages", "references", "courses", "coursework",
        "volunteer", "volunteering", "hobbies", "history", "profile", "professional", "additional", "relevant", "employment", "work",
        "publications", "contact", "qualifications", "achievements", "training",
    }
)

# Lower-case particles that are part of real names ("Isabella J. de Souza", "Ahmed bin Khalid").
_NAME_PARTICLES = frozenset({"de", "da", "del", "della", "di", "du", "van", "von", "der", "den", "la", "le", "bin", "bint", "al", "el", "ibn", "y"})


def _name_shaped(line: str, words: list[str]) -> bool:
    """A heading ("Relevant Coursework:") or a sentence fragment ("cumulative underlying notional exposure.") is not a name.

    Found as names in the real corpus before this rule. Names are capitalised apart from known particles, and do not end
    in a colon or a full stop (an initial such as "J." inside the name is fine)."""
    if line.rstrip().endswith((":", ".")):
        return False
    # A comma or colon marks a place ("Berkeley, CA"), an "Employer, Title" line or a labelled fact
    # ("Triple Citizenship: USA, Brazil"). A CV header does not write the person's name that way.
    if any(mark in line for mark in (",", ":", ";", "/", "&")):
        return False
    folded = [_bare(word).casefold().strip(".,:|") for word in words]
    if any(word in _SECTION_WORDS or word in _NOT_NAME_WORDS for word in folded):
        return False
    # "Not lower case" rather than "upper case", so caseless scripts such as Arabic still qualify.
    return all(not _bare(word)[:1].islower() or word.casefold() in _NAME_PARTICLES for word in words) and not words[0][:1].islower()


# Words that make a header line a school, an employer, a job title or a document label, never a person's name.
# Each was read as a candidate's name in the real corpus before this rule.
_NOT_NAME_WORDS = frozenset(
    {
        "university", "college", "school", "institute", "academy", "high", "technological", "polytechnic",
        "inc", "ltd", "llc", "corp", "corporation", "company", "group", "partners", "capital", "consulting",
        "intern", "internship", "research", "engineer", "consultant", "analyst", "manager", "student", "assistant",
        "director", "associate", "developer", "officer", "specialist", "trader", "self-employed", "finalist", "member",
        "president", "champion", "winner", "business", "about", "and", "of", "the", "for", "energy",
        "bachelor", "bachelors", "master", "masters", "b.s", "b.a", "m.s", "m.a", "b.sc", "m.sc", "mba", "phd",
        "science", "sciences", "administration", "engineering", "economics", "studies",
        "resume", "cv", "curriculum", "vitae", "blind", "citizenship", "degree", "page",
    }
)


def _contacts(text: str) -> list[ContactDraft]:
    rows: list[ContactDraft] = []
    for raw, normalized in find_emails(text):
        rows.append(ContactDraft(kind="email", value=normalized, quote=raw))
    for raw, normalized in find_phones(text):
        rows.append(ContactDraft(kind="phone", value=normalized, quote=raw))
    return rows


def _take_experience(line: str, pending: str | None, rows: list[ExperienceDraft]) -> str | None:
    match = _DATE_RANGE.search(line)
    if match is None:
        # A bullet point or a sentence describes work; it is not the role heading the dates belong to.
        if _BULLET.match(line) or len(line.split()) > 12 or line.rstrip().endswith("."):
            return pending
        return line
    start = normalize_cv_date(match.group(1), end=False)
    end = normalize_cv_date(match.group(2), end=True)
    before = line[: match.start()].strip(" 	|·•-–—,")
    role = pending or (before if len(before) >= 3 else None)
    if role is None or start is None:
        return None
    if start != "present" and end not in (None, "present") and end < start:
        end = None  # reversed range: keep the start, do not invent an end
    employer, title = _split_role(role)
    if len(employer) > _MAX_FIELD or len(role) > MAX_QUOTE_LENGTH or len(line) > MAX_QUOTE_LENGTH:
        return None  # prose, not a role heading: skip the row, keep the rest of the CV
    if title is not None and len(title) > _MAX_FIELD:
        title = None
    rows.append(
        ExperienceDraft(
            employer=employer,
            employer_quote=role,
            title=title,
            title_quote=role if title else None,
            start_date=start,
            start_date_quote=line,
            end_date=end,
            end_date_quote=line if end else None,
        )
    )
    return None


def _take_education(line: str, rows: list[EducationDraft]) -> None:
    if "," in line:
        institution, credential = [part.strip() for part in line.split(",", 1)]
    else:
        institution, credential = line, None
    if not institution or len(institution) > _MAX_FIELD or len(line) > MAX_QUOTE_LENGTH:
        return  # a long line under Education is prose, not an institution: skip it, keep the rest of the CV
    if credential is not None and len(credential) > _MAX_FIELD:
        credential = None
    rows.append(
        EducationDraft(
            institution=institution,
            institution_quote=line,
            credential=credential,
            credential_quote=line if credential else None,
        )
    )


def _clean_label(value: str) -> str:
    """A skill or certificate name without icon glyphs (private-use characters), control characters or a leading bullet.

    PDFs from design tools put icon-font glyphs next to words. They are not part of the name, and they show up in emails."""
    text = "".join(ch for ch in value if unicodedata.category(ch) not in {"Co", "Cc", "Cf", "Cs"})
    return _BULLET.sub("", text).strip(" 	|-•")


def _take_labeled(line: str, rows: list, factory, *, kind: str | None = None) -> None:
    if kind is not None and _BULLET.match(line):
        return  # a bullet under Certifications describes what was done, it is not a certificate
    parts = re.split(r"[,،;]", line)
    for part in parts:
        name = _clean_label(part)
        if len(name) < 2 or _INSTRUCTION.search(name):
            continue
        if kind is not None and (len(name.split()) > 12 or name.endswith(".")):
            continue  # a sentence, not a certificate name
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


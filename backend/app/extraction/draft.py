"""Model output is untrusted. A quote must occur in the source before it is stored."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.constants import BLOCKED_FIELDS, MAX_QUOTE_LENGTH
from app.extraction.textutil import normalize_ws


class ContactDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["email", "phone", "location", "link"]
    value: str = Field(min_length=1, max_length=320)
    quote: str = Field(min_length=1, max_length=MAX_QUOTE_LENGTH)
    page: int | None = Field(default=None, ge=1, le=50)


class ExperienceDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employer: str = Field(min_length=1, max_length=300)
    employer_quote: str = Field(min_length=1, max_length=MAX_QUOTE_LENGTH)
    title: str | None = Field(default=None, max_length=300)
    title_quote: str | None = Field(default=None, max_length=MAX_QUOTE_LENGTH)
    location: str | None = Field(default=None, max_length=300)
    location_quote: str | None = Field(default=None, max_length=MAX_QUOTE_LENGTH)
    start_date: str | None = Field(default=None, max_length=32)
    start_date_quote: str | None = Field(default=None, max_length=MAX_QUOTE_LENGTH)
    end_date: str | None = Field(default=None, max_length=32)
    end_date_quote: str | None = Field(default=None, max_length=MAX_QUOTE_LENGTH)
    description: str | None = Field(default=None, max_length=4000)
    description_quote: str | None = Field(default=None, max_length=MAX_QUOTE_LENGTH)
    page: int | None = Field(default=None, ge=1, le=50)


class EducationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution: str = Field(min_length=1, max_length=300)
    institution_quote: str = Field(min_length=1, max_length=MAX_QUOTE_LENGTH)
    credential: str | None = Field(default=None, max_length=300)
    credential_quote: str | None = Field(default=None, max_length=MAX_QUOTE_LENGTH)
    page: int | None = Field(default=None, ge=1, le=50)


class SkillDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    quote: str = Field(min_length=1, max_length=MAX_QUOTE_LENGTH)
    page: int | None = Field(default=None, ge=1, le=50)


class CertificateDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=300)
    quote: str = Field(min_length=1, max_length=MAX_QUOTE_LENGTH)
    issuer: str | None = Field(default=None, max_length=300)
    issuer_quote: str | None = Field(default=None, max_length=MAX_QUOTE_LENGTH)
    kind: Literal["certificate", "qualification"] = "certificate"
    page: int | None = Field(default=None, ge=1, le=50)


class ExtractionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=200)
    display_name_quote: str | None = Field(default=None, max_length=MAX_QUOTE_LENGTH)
    summary: str | None = Field(default=None, max_length=2000)
    summary_quote: str | None = Field(default=None, max_length=MAX_QUOTE_LENGTH)
    contacts: list[ContactDraft] = Field(default_factory=list)
    experiences: list[ExperienceDraft] = Field(default_factory=list)
    education: list[EducationDraft] = Field(default_factory=list)
    skills: list[SkillDraft] = Field(default_factory=list)
    certificates: list[CertificateDraft] = Field(default_factory=list)


class DraftRejected(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_draft(payload: object) -> ExtractionDraft:
    if not isinstance(payload, dict):
        raise DraftRejected("malformed_output")
    blocked = BLOCKED_FIELDS.intersection(payload)
    if blocked:
        raise DraftRejected("blocked_attribute")
    try:
        return ExtractionDraft.model_validate(payload)
    except ValidationError as exc:
        raise DraftRejected("malformed_output") from exc


def quote_in_source(pages: list[str], quote: str, page: int | None) -> bool:
    needle = normalize_ws(quote)
    if not needle or len(quote) > MAX_QUOTE_LENGTH:
        return False
    if page is not None:
        if page < 1 or page > len(pages):
            return False
        return needle in normalize_ws(pages[page - 1])
    return needle in normalize_ws("\n".join(pages))


def parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None

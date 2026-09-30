"""Turn verified draft fields into profile rows. Locked fields are left alone."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.actor import SYSTEM
from app.domain.years import span_years
from app.extraction.draft import (
    ExtractionDraft,
    parse_iso_date,
    quote_in_source,
)
from app.extraction.textutil import page_for_snippet
from app.models import (
    Candidate,
    CandidateCertificate,
    CandidateEducation,
    CandidateExperience,
    CandidateSkill,
    DocumentChunk,
    ExtractionEvidence,
)
from app.services.audit import write_audit
from app.services.locks import is_locked


@dataclass
class ApplyResult:
    accepted: int = 0
    rejected: int = 0
    evidence_ids: list[UUID] = field(default_factory=list)


def apply_draft(
    session: Session,
    *,
    candidate: Candidate,
    document_id: UUID,
    pages: list[str],
    chunks: list[DocumentChunk],
    draft: ExtractionDraft,
    agent_run_id: UUID | None,
) -> ApplyResult:
    result = ApplyResult()
    _apply_candidate_field(
        session, result, candidate, document_id, pages, chunks, agent_run_id,
        field_name="display_name", value=draft.display_name, quote=draft.display_name_quote, page=None,
    )
    _apply_candidate_field(
        session, result, candidate, document_id, pages, chunks, agent_run_id,
        field_name="summary", value=draft.summary, quote=draft.summary_quote, page=None,
    )
    for item in draft.experiences:
        _apply_experience(session, result, candidate, document_id, pages, chunks, agent_run_id, item)
    for item in draft.education:
        _apply_education(session, result, candidate, document_id, pages, chunks, agent_run_id, item)
    for item in draft.skills:
        if _rejected_quote(pages, item.quote, item.page):
            result.rejected += 1
            continue
        row = CandidateSkill(
            candidate_id=candidate.id,
            source_document_id=document_id,
            name=item.name,
            normalized_name=item.name.casefold(),
        )
        session.add(row)
        session.flush()
        result.accepted += 1
        _evidence(
            session, result, document_id, candidate.id, chunks, agent_run_id,
            entity_type="skill", entity_id=row.id, field_name="name",
            value=item.name, quote=item.quote, page=item.page,
        )
    for item in draft.certificates:
        if _rejected_quote(pages, item.quote, item.page):
            result.rejected += 1
            continue
        row = CandidateCertificate(
            candidate_id=candidate.id,
            source_document_id=document_id,
            name=item.name,
            kind=item.kind,
        )
        session.add(row)
        session.flush()
        result.accepted += 1
        _evidence(
            session, result, document_id, candidate.id, chunks, agent_run_id,
            entity_type="certificate", entity_id=row.id, field_name="name",
            value=item.name, quote=item.quote, page=item.page,
        )
    _assign_years(session, result, candidate, document_id, chunks, agent_run_id)
    return result


def _apply_candidate_field(session, result, candidate, document_id, pages, chunks, agent_run_id, *, field_name, value, quote, page):
    if value is None:
        return
    if quote is None or _rejected_quote(pages, quote, page):
        result.rejected += 1
        return
    if page is None:
        page = page_for_snippet(pages, quote)
    if is_locked(session, candidate_id=candidate.id, entity_type="candidate", entity_id=None, field_name=field_name):
        write_audit(
            session,
            actor=SYSTEM,
            action="field_lock_kept",
            entity_type="candidate",
            entity_id=candidate.id,
            detail={"field": field_name, "candidate_id": str(candidate.id)},
        )
        return
    setattr(candidate, field_name, value)
    result.accepted += 1
    _evidence(
        session, result, document_id, candidate.id, chunks, agent_run_id,
        entity_type="candidate", entity_id=candidate.id, field_name=field_name,
        value=value, quote=quote, page=page,
    )


def _apply_experience(session, result, candidate, document_id, pages, chunks, agent_run_id, item):
    if _rejected_quote(pages, item.employer_quote, item.page):
        result.rejected += 1
        return
    row = CandidateExperience(
        candidate_id=candidate.id,
        source_document_id=document_id,
        employer=item.employer,
    )
    session.add(row)
    session.flush()
    result.accepted += 1
    _evidence(
        session, result, document_id, candidate.id, chunks, agent_run_id,
        entity_type="experience", entity_id=row.id, field_name="employer",
        value=item.employer, quote=item.employer_quote, page=item.page,
    )
    _optional_experience_field(session, result, row, document_id, candidate.id, pages, chunks, agent_run_id, item, "title")
    _optional_experience_field(session, result, row, document_id, candidate.id, pages, chunks, agent_run_id, item, "description")
    for date_field in ("start_date", "end_date"):
        raw = getattr(item, date_field)
        quote = getattr(item, f"{date_field}_quote")
        if raw is None:
            continue
        if quote is None or _rejected_quote(pages, quote, item.page) or parse_iso_date(raw) is None:
            result.rejected += 1
            continue
        setattr(row, date_field, parse_iso_date(raw))
        result.accepted += 1
        _evidence(
            session, result, document_id, candidate.id, chunks, agent_run_id,
            entity_type="experience", entity_id=row.id, field_name=date_field,
            value=raw[:10], quote=quote, page=item.page,
        )


def _optional_experience_field(session, result, row, document_id, candidate_id, pages, chunks, agent_run_id, item, field_name):
    value = getattr(item, field_name)
    quote = getattr(item, f"{field_name}_quote")
    if value is None:
        return
    if quote is None or _rejected_quote(pages, quote, item.page):
        result.rejected += 1
        return
    setattr(row, field_name, value)
    result.accepted += 1
    _evidence(
        session, result, document_id, candidate_id, chunks, agent_run_id,
        entity_type="experience", entity_id=row.id, field_name=field_name,
        value=value, quote=quote, page=item.page,
    )


def _apply_education(session, result, candidate, document_id, pages, chunks, agent_run_id, item):
    if _rejected_quote(pages, item.institution_quote, item.page):
        result.rejected += 1
        return
    row = CandidateEducation(
        candidate_id=candidate.id,
        source_document_id=document_id,
        institution=item.institution,
    )
    session.add(row)
    session.flush()
    result.accepted += 1
    _evidence(
        session, result, document_id, candidate.id, chunks, agent_run_id,
        entity_type="education", entity_id=row.id, field_name="institution",
        value=item.institution, quote=item.institution_quote, page=item.page,
    )
    if item.credential and item.credential_quote and not _rejected_quote(pages, item.credential_quote, item.page):
        row.credential = item.credential
        result.accepted += 1
        _evidence(
            session, result, document_id, candidate.id, chunks, agent_run_id,
            entity_type="education", entity_id=row.id, field_name="credential",
            value=item.credential, quote=item.credential_quote, page=item.page,
        )


def _assign_years(session, result, candidate, document_id, chunks, agent_run_id) -> None:
    rows = session.scalars(select_experiences(session, candidate.id))
    ranges = []
    evidence_quote = None
    evidence_page = None
    for row in rows:
        if row.start_date is None or row.end_date is None:
            continue
        ranges.append((row.start_date, row.end_date))
        if evidence_quote is None:
            quote_row = _date_quote(session, document_id, row.id)
            if quote_row is not None:
                evidence_quote = quote_row.source_quote
                evidence_page = quote_row.page
    years = span_years(ranges)
    if years is None or evidence_quote is None:
        return
    if is_locked(session, candidate_id=candidate.id, entity_type="candidate", entity_id=None, field_name="years_of_experience"):
        write_audit(
            session,
            actor=SYSTEM,
            action="field_lock_kept",
            entity_type="candidate",
            entity_id=candidate.id,
            detail={"field": "years_of_experience", "candidate_id": str(candidate.id)},
        )
        return
    candidate.years_of_experience = years
    result.accepted += 1
    _evidence(
        session, result, document_id, candidate.id, chunks, agent_run_id,
        entity_type="candidate", entity_id=candidate.id, field_name="years_of_experience",
        value=f"{years}", quote=evidence_quote, page=evidence_page,
    )


def select_experiences(session, candidate_id):
    from sqlalchemy import select

    from app.models import CandidateExperience

    return select(CandidateExperience).where(CandidateExperience.candidate_id == candidate_id)


def _date_quote(session, document_id, experience_id):
    from sqlalchemy import select

    return session.scalar(
        select(ExtractionEvidence).where(
            ExtractionEvidence.document_id == document_id,
            ExtractionEvidence.entity_id == experience_id,
            ExtractionEvidence.field_name == "start_date",
        )
    )


def _rejected_quote(pages: list[str], quote: str | None, page: int | None) -> bool:
    if quote is None:
        return True
    return not quote_in_source(pages, quote, page)


def _evidence(session, result, document_id, candidate_id, chunks, agent_run_id, *, entity_type, entity_id, field_name, value, quote, page):
    row = ExtractionEvidence(
        document_id=document_id,
        candidate_id=candidate_id,
        chunk_id=_chunk_id(chunks, quote),
        agent_run_id=agent_run_id,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        extracted_value=value,
        source_quote=quote,
        page=page,
        quote_verified=True,
    )
    session.add(row)
    session.flush()
    result.evidence_ids.append(row.id)


def _chunk_id(chunks: list[DocumentChunk], quote: str) -> UUID | None:
    from app.extraction.textutil import normalize_ws

    needle = normalize_ws(quote)
    for chunk in chunks:
        if needle in normalize_ws(chunk.content):
            return chunk.id
    return None

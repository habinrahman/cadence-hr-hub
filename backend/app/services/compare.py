"""Gather comparison signals for one incoming document. The score lives in domain.confidence."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from app.domain.confidence import PairEvidence
from app.domain.cvdates import dates_in_text, explicit_dates, is_newer
from app.domain.identity import name_overlap, name_similarity, national_phone, phones_match
from app.extraction.contacts import normalize_email, normalize_phone
from app.extraction.draft import ExtractionDraft, quote_in_source
from app.models import (
    Application,
    Candidate,
    CandidateContact,
    CandidateDocument,
    CandidateEducation,
    CandidateExperience,
    CandidateSkill,
    DocumentChunk,
)


def contact_pairs(
    session: Session,
    *,
    emails: list[tuple[str, str]],
    phones: list[tuple[str, str]],
    name: str | None,
) -> list[PairEvidence]:
    """Same contact and name lookup as a CV, without document text or embeddings."""

    incoming_emails = {normalized for _raw, normalized in emails if normalize_email(normalized)}
    incoming_phones = {normalized for _raw, normalized in phones if normalize_phone(normalized)}
    email_ids = _ids_for(session, "email", incoming_emails)
    phone_ids = _ids_for(session, "phone", incoming_phones)
    name_ids = _name_ids(session, name)
    candidate_ids = sorted(email_ids | phone_ids | name_ids, key=str)
    pairs: list[PairEvidence] = []
    for candidate_id in candidate_ids:
        candidate = session.get(Candidate, candidate_id)
        if candidate is None:
            continue
        stored_emails, stored_phones = _stored_contacts(session, candidate_id)
        pairs.append(
            PairEvidence(
                candidate_id=candidate_id,
                email_match=_match(incoming_emails, stored_emails),
                phone_match=phone_match(incoming_phones, stored_phones),
                name_similarity=name_similarity(name, candidate.display_name),
                document_hash_match=False,
            )
        )
    return pairs


def build_pairs(
    session: Session,
    *,
    document: CandidateDocument,
    full_text: str,
    emails: list[tuple[str, str]],
    phones: list[tuple[str, str]],
    name: str | None,
    draft: ExtractionDraft | None,
    pages: list[str],
) -> list[PairEvidence]:
    incoming_emails = {normalized for _raw, normalized in emails if normalize_email(normalized)}
    incoming_phones = {normalized for _raw, normalized in phones if normalize_phone(normalized)}
    email_ids = _ids_for(session, "email", incoming_emails)
    phone_ids = _ids_for(session, "phone", incoming_phones)
    name_ids = _name_ids(session, name)
    candidate_ids = sorted(email_ids | phone_ids | name_ids, key=str)
    if not candidate_ids:
        return []

    incoming_dates = dates_in_text(full_text)
    incoming_explicit = explicit_dates(full_text)
    incoming_roles = _roles(draft, pages)
    incoming_schools = _schools(draft, pages)
    incoming_skills = _skills(draft, pages)
    incoming_vector = _vector(
        session.scalar(
            select(DocumentChunk.embedding).where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.embedding.is_not(None),
            )
        )
    )

    pairs: list[PairEvidence] = []
    for candidate_id in candidate_ids:
        candidate = session.get(Candidate, candidate_id)
        if candidate is None:
            continue
        stored_emails, stored_phones = _stored_contacts(session, candidate_id)
        stored_dates = _stored_dates(session, candidate_id)
        pairs.append(
            PairEvidence(
                candidate_id=candidate_id,
                email_match=_match(incoming_emails, stored_emails),
                phone_match=phone_match(incoming_phones, stored_phones),
                name_similarity=name_similarity(name, candidate.display_name),
                document_hash_match=_same_hash(session, candidate_id, document.sha256),
                incoming_is_newer=is_newer(incoming_dates, stored_dates),
                explicit_version_newer=is_newer(incoming_explicit, stored_dates),
                employment_similarity=_jaccard(incoming_roles, _stored_roles(session, candidate_id)),
                education_similarity=_jaccard(incoming_schools, _stored_schools(session, candidate_id)),
                skills_similarity=_jaccard(incoming_skills, _stored_skills(session, candidate_id)),
                semantic_similarity=_cosine(incoming_vector, _stored_vector(session, candidate_id)),
            )
        )
    return pairs


def _ids_for(session: Session, kind: str, values: set[str]) -> set[UUID]:
    if not values:
        return set()
    if kind == "phone":
        return _phone_ids(session, values)
    rows = session.scalars(
        select(CandidateContact.candidate_id).where(
            CandidateContact.kind == kind,
            CandidateContact.value_normalized.in_(values),
        )
    )
    return set(rows)


def _name_ids(session: Session, name: str | None) -> set[UUID]:
    if not name:
        return set()
    found: set[UUID] = set()
    rows = session.execute(
        select(Candidate.id, Candidate.display_name).where(Candidate.display_name.is_not(None))
    )
    for candidate_id, existing in rows:
        if name_overlap(name, existing):
            found.add(candidate_id)
    return found


def _stored_contacts(session: Session, candidate_id: UUID) -> tuple[set[str], set[str]]:
    emails: set[str] = set()
    phones: set[str] = set()
    rows = session.scalars(select(CandidateContact).where(CandidateContact.candidate_id == candidate_id))
    for row in rows:
        if row.kind == "email":
            emails.add(row.value_normalized)
        elif row.kind == "phone":
            phones.add(row.value_normalized)
    return emails, phones


def _stored_dates(session: Session, candidate_id: UUID) -> list[date]:
    found: list[date] = []
    applications = session.scalars(
        select(Application.application_date).where(
            Application.candidate_id == candidate_id,
            Application.application_date.is_not(None),
        )
    )
    found.extend(item for item in applications if item is not None)
    experiences = session.scalars(
        select(CandidateExperience).where(CandidateExperience.candidate_id == candidate_id)
    )
    for row in experiences:
        if row.start_date is not None:
            found.append(row.start_date)
        if row.end_date is not None:
            found.append(row.end_date)
    education = session.scalars(
        select(CandidateEducation).where(CandidateEducation.candidate_id == candidate_id)
    )
    for row in education:
        if row.start_date is not None:
            found.append(row.start_date)
        if row.end_date is not None:
            found.append(row.end_date)
    return found


def _same_hash(session: Session, candidate_id: UUID, sha256: str) -> bool:
    found = session.scalar(
        select(CandidateDocument.id).where(
            CandidateDocument.candidate_id == candidate_id,
            CandidateDocument.sha256 == sha256,
        )
    )
    return found is not None


def _match(incoming: set[str], stored: set[str]) -> bool | None:
    if not incoming or not stored:
        return None
    return bool(incoming & stored)


def phone_match(incoming: set[str], stored: set[str]) -> bool | None:
    """Like _match, but 052 444 9121 and +972 52 444 9121 are one number, not a contradiction."""
    if not incoming or not stored:
        return None
    return any(phones_match(left, right) for left in incoming for right in stored)


def _phone_ids(session: Session, values: set[str]) -> set[UUID]:
    """Candidates holding any of these numbers, in any of the ways phones_match accepts."""
    found: set[UUID] = set()
    for value in values:
        national = national_phone(value)
        if len(national) < 8:
            continue
        stored = func.ltrim(CandidateContact.value_normalized, "0")
        rows = session.execute(
            select(CandidateContact.candidate_id, CandidateContact.value_normalized).where(
                CandidateContact.kind == "phone",
                or_(stored.like("%" + national), literal(national).like(func.concat("%", stored))),
            )
        )
        found.update(candidate_id for candidate_id, other in rows if phones_match(value, other))
    return found


def _roles(draft: ExtractionDraft | None, pages: list[str]) -> set[str]:
    if draft is None:
        return set()
    found: set[str] = set()
    for item in draft.experiences:
        if not quote_in_source(pages, item.employer_quote, item.page):
            continue
        title = item.title or ""
        found.add(f"{item.employer.casefold()}|{title.casefold()}")
    return found


def _schools(draft: ExtractionDraft | None, pages: list[str]) -> set[str]:
    if draft is None:
        return set()
    found: set[str] = set()
    for item in draft.education:
        if not quote_in_source(pages, item.institution_quote, item.page):
            continue
        credential = item.credential or ""
        found.add(f"{item.institution.casefold()}|{credential.casefold()}")
    return found


def _skills(draft: ExtractionDraft | None, pages: list[str]) -> set[str]:
    if draft is None:
        return set()
    return {
        item.name.casefold()
        for item in draft.skills
        if quote_in_source(pages, item.quote, item.page)
    }


def _stored_roles(session: Session, candidate_id: UUID) -> set[str]:
    rows = session.scalars(select(CandidateExperience).where(CandidateExperience.candidate_id == candidate_id))
    return {f"{row.employer.casefold()}|{(row.title or '').casefold()}" for row in rows}


def _stored_schools(session: Session, candidate_id: UUID) -> set[str]:
    rows = session.scalars(select(CandidateEducation).where(CandidateEducation.candidate_id == candidate_id))
    return {f"{row.institution.casefold()}|{(row.credential or '').casefold()}" for row in rows}


def _stored_skills(session: Session, candidate_id: UUID) -> set[str]:
    rows = session.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id))
    return {row.normalized_name for row in rows}


def _stored_vector(session: Session, candidate_id: UUID) -> list[float] | None:
    value = session.scalar(
        select(DocumentChunk.embedding)
        .join(CandidateDocument, CandidateDocument.id == DocumentChunk.document_id)
        .where(
            CandidateDocument.candidate_id == candidate_id,
            DocumentChunk.embedding.is_not(None),
        )
    )
    return _vector(value)


def _vector(value) -> list[float] | None:
    if value is None:
        return None
    return [float(item) for item in value]


def _jaccard(left: set[str], right: set[str]) -> float | None:
    if not left or not right:
        return None
    return len(left & right) / len(left | right)


def _cosine(left: list[float] | None, right: list[float] | None) -> float | None:
    if not left or not right or len(left) != len(right):
        return None
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return None
    return dot / (left_norm * right_norm)

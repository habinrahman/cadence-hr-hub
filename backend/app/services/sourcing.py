"""Recruiter-entered candidates still use CV intake for identity. Nothing is merged here."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.actor import Actor
from app.domain.transitions import TransitionError, utcnow
from app.extraction.contacts import normalize_email, normalize_phone
from app.extraction.media import UnsupportedFile
from app.models import Application, Candidate, CandidateContact, CandidateDocument, CandidateSource, User
from app.services.audit import write_audit
from app.services.compare import contact_pairs
from app.services.ingest import ingest_bytes

SOURCE_TYPES = frozenset({"linkedin", "referral", "other"})


class SourceError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def submit_source(
    session: Session,
    *,
    actor: Actor,
    display_name: str,
    email: str,
    phone: str,
    source_type: str,
    source_reference: str,
    notes: str,
    filename: str | None,
    data: bytes,
) -> CandidateSource:
    user = _recruiter(session, actor)
    name = _name(display_name)
    kind = _kind(source_type)
    reference = _reference(source_reference)
    stored_email = _email(email)
    stored_phone = _phone(phone)
    stored_notes = _notes(notes)
    try:
        result = ingest_bytes(session, filename=filename, data=data, actor=actor)
    except UnsupportedFile:
        raise SourceError("unsupported_file") from None
    existing = session.scalar(
        select(CandidateSource).where(CandidateSource.document_id == result.document.id)
    )
    if existing is not None:
        return existing
    row = CandidateSource(
        document_id=result.document.id,
        candidate_id=result.document.candidate_id,
        created_by_user_id=user.id,
        display_name=name,
        email=stored_email,
        phone=stored_phone,
        source_type=kind,
        source_reference=reference,
        notes=stored_notes,
    )
    session.add(row)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="sourced_cv_attached",
        entity_type="candidate_document",
        entity_id=result.document.id,
        detail={
            "document_id": str(result.document.id),
            "source_type": kind,
            "identity_outcome": "same_document" if not result.created else "received",
        },
    )
    return row


class PossibleExisting(SourceError):
    """The lead may already be on file. Nothing was written: a recruiter chooses the profile or a new one."""

    def __init__(self, matches: list[dict]) -> None:
        super().__init__("possible_existing")
        self.matches = matches


def submit_lead(
    session: Session,
    *,
    actor: Actor,
    display_name: str,
    email: str,
    phone: str,
    source_type: str,
    source_reference: str,
    notes: str,
    attach_to: UUID | None = None,
    create_new: bool = False,
) -> CandidateSource:
    """A person found on LinkedIn or by referral, recorded before any CV exists.

    The same email, phone or name checks a CV gets run first. If anyone matches, nothing is written and the
    recruiter is shown who matched and why; they then add the source to that profile (attach_to) or confirm a new
    profile (create_new). The system never picks between them."""
    user = _recruiter(session, actor)
    name = _name(display_name)
    kind = _kind(source_type)
    reference = _reference(source_reference)
    stored_email = _email(email)
    stored_phone = _phone(phone)
    stored_notes = _notes(notes)
    matches = _existing_matches(session, stored_email, stored_phone, name)
    if attach_to is not None:
        if str(attach_to) not in {item["candidate_id"] for item in matches}:
            raise SourceError("not_a_match")  # only a profile the check found can receive this lead
        candidate = session.get(Candidate, attach_to)
        outcome = "attached_existing"
    elif matches and not create_new:
        raise PossibleExisting(matches)
    else:
        candidate = Candidate(source=kind, display_name=name)
        session.add(candidate)
        session.flush()
        outcome = "new"
    row = CandidateSource(
        document_id=None,
        candidate_id=candidate.id,
        created_by_user_id=user.id,
        display_name=name,
        email=stored_email,
        phone=stored_phone,
        source_type=kind,
        source_reference=reference,
        notes=stored_notes,
    )
    session.add(row)
    session.add(Application(candidate_id=candidate.id, document_id=None, source=kind, received_at=utcnow()))
    _store_declared_contacts(session, row, candidate.id)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="sourced_candidate_created" if outcome == "new" else "sourced_candidate_attached",
        entity_type="candidate",
        entity_id=candidate.id,
        detail={
            "candidate_id": str(candidate.id),
            "source_type": kind,
            "identity_outcome": outcome,
            "human_action": "create_new" if outcome == "new" else "attach_to_existing",
            "count": len(matches),
        },
    )
    return row


def _existing_matches(session: Session, email: str | None, phone: str | None, name: str) -> list[dict]:
    """Profiles sharing the email, the phone or the full name, with the reasons. Merged-away profiles are skipped."""
    pairs = contact_pairs(
        session,
        emails=[(email, email)] if email else [],
        phones=[(phone, phone)] if phone else [],
        name=name,
    )
    found: list[dict] = []
    for pair in pairs:
        candidate = session.get(Candidate, pair.candidate_id)
        if candidate is None or candidate.merged_into_id is not None:
            continue
        reasons = [
            reason
            for reason, present in (
                ("same_email", pair.email_match is True),
                ("same_phone", pair.phone_match is True),
                ("same_name", (pair.name_similarity or 0) >= 0.99),
                ("similar_name", 0 < (pair.name_similarity or 0) < 0.99),
                ("different_email", pair.email_match is False),
                ("different_phone", pair.phone_match is False),
            )
            if present
        ]
        found.append({"candidate_id": str(candidate.id), "display_name": candidate.display_name, "reasons": reasons})
    return found


def declared_contacts(session: Session, document_id: UUID) -> tuple[list[tuple[str, str]], list[tuple[str, str]], str | None]:
    row = session.scalar(select(CandidateSource).where(CandidateSource.document_id == document_id))
    if row is None:
        return [], [], None
    emails: list[tuple[str, str]] = []
    phones: list[tuple[str, str]] = []
    if row.email:
        emails.append((row.email, row.email))
    if row.phone:
        phones.append((row.phone, row.phone))
    return emails, phones, row.display_name


def note_source_outcome(session: Session, document: CandidateDocument, candidate: Candidate | None) -> None:
    row = session.scalar(select(CandidateSource).where(CandidateSource.document_id == document.id))
    if row is None:
        return
    if candidate is not None:
        _retain_on_new_candidate(session, row, candidate, document)
        return
    if document.identity_outcome in {None, "new", "same_document"}:
        return
    write_audit(
        session,
        actor=Actor(kind="system"),
        action="sourced_duplicate_detected",
        entity_type="candidate_document",
        entity_id=document.id,
        detail={
            "document_id": str(document.id),
            "source_type": row.source_type,
            "relationship": document.identity_outcome,
            "identity_outcome": document.identity_outcome,
        },
    )


def record_source_decision(session: Session, document_id: UUID, actor: Actor, action: str) -> None:
    row = session.scalar(select(CandidateSource).where(CandidateSource.document_id == document_id))
    if row is None:
        return
    document = session.get(CandidateDocument, document_id)
    if document is None or document.candidate_id is None:
        return
    candidate = session.get(Candidate, document.candidate_id)
    if candidate is None:
        return
    if action == "create_separate_candidate" and row.candidate_id is None:
        _retain_on_new_candidate(session, row, candidate, document)
    else:
        row.candidate_id = candidate.id
        _store_declared_contacts(session, row, candidate.id)
    write_audit(
        session,
        actor=actor,
        action="sourced_review_decided",
        entity_type="candidate_document",
        entity_id=document.id,
        detail={
            "document_id": str(document.id),
            "candidate_id": str(candidate.id),
            "source_type": row.source_type,
            "human_action": action,
        },
    )


def _retain_on_new_candidate(session, row: CandidateSource, candidate: Candidate, document: CandidateDocument) -> None:
    if candidate.source == "upload":
        candidate.source = row.source_type
    if not candidate.display_name:
        candidate.display_name = row.display_name
    row.candidate_id = candidate.id
    _store_declared_contacts(session, row, candidate.id)
    write_audit(
        session,
        actor=Actor(kind="system"),
        action="sourced_candidate_created",
        entity_type="candidate_document",
        entity_id=document.id,
        detail={
            "document_id": str(document.id),
            "candidate_id": str(candidate.id),
            "source_type": row.source_type,
            "identity_outcome": document.identity_outcome or "new",
        },
    )


def _store_declared_contacts(session: Session, row: CandidateSource, candidate_id: UUID) -> None:
    if row.email:
        _add_contact(session, candidate_id, "email", row.email)
    if row.phone:
        _add_contact(session, candidate_id, "phone", row.phone)


def _add_contact(session: Session, candidate_id: UUID, kind: str, value: str) -> None:
    exists = session.scalar(
        select(CandidateContact.id).where(
            CandidateContact.candidate_id == candidate_id,
            CandidateContact.kind == kind,
            CandidateContact.value_normalized == value,
        )
    )
    if exists is not None:
        return
    session.add(
        CandidateContact(
            candidate_id=candidate_id,
            kind=kind,
            value_raw=value,
            value_normalized=value,
            is_primary=False,
        )
    )


def _recruiter(session: Session, actor: Actor) -> User:
    if actor.kind != "user" or actor.user_id is None:
        raise TransitionError("human_required")
    user = session.get(User, actor.user_id)
    if user is None or user.role != "recruiter":
        raise TransitionError("forbidden")
    return user


def _name(value: str) -> str:
    text = " ".join(value.split())
    if not text or len(text) > 200:
        raise SourceError("invalid_name")
    return text


def _kind(value: str) -> str:
    text = value.strip().lower()
    if text not in SOURCE_TYPES:
        raise SourceError("invalid_source_type")
    return text


def _reference(value: str) -> str:
    text = " ".join(value.split())
    if not text or len(text) > 300:
        raise SourceError("invalid_reference")
    return text


def _email(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    normalized = normalize_email(text)
    if normalized is None:
        raise SourceError("invalid_email")
    return normalized


def _phone(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    normalized = normalize_phone(text)
    if normalized is None:
        raise SourceError("invalid_phone")
    return normalized


def _notes(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    if len(text) > 2000:
        raise SourceError("invalid_notes")
    return text

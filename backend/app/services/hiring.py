"""Hiring requests, explicit requirements, and recruiter shortlist decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import Actor
from app.domain.requirement_schema import ProposalRejected, validate_proposal
from app.domain.transitions import TransitionError, transition
from app.extraction.provider import ExtractorUnavailable
from app.extraction.requirement_provider import get_requirement_reader
from app.extraction.textutil import sha256_bytes, sha256_text
from app.models import (
    AgentRun,
    CandidateMatch,
    HiringRequest,
    MatchRequirementResult,
    RequestAttachment,
    RequestNote,
    RequestRequirement,
    SharingRecord,
    Shortlist,
    ShortlistCandidate,
    User,
)
from app.services.audit import write_audit
from app.storage.local import LocalStorage

NOTE_KINDS = frozenset({"note", "update", "next_step"})


class HiringError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def create_request(
    session: Session,
    *,
    company_name: str,
    job_title: str,
    description: str,
    received_at: datetime,
    actor: Actor,
) -> HiringRequest:
    user = _recruiter(session, actor)
    row = HiringRequest(
        company_name=company_name.strip(),
        job_title=job_title.strip(),
        description=description,
        status="draft",
        received_at=received_at,
        owner_user_id=user.id,
    )
    session.add(row)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="hiring_request_created",
        entity_type="hiring_request",
        entity_id=row.id,
        detail={"request_id": str(row.id), "outcome": "draft"},
    )
    return row


def open_request(session: Session, request_id: UUID, actor: Actor) -> HiringRequest:
    _recruiter(session, actor)
    row = _request(session, request_id)
    if row.status == "draft":
        transition(row, "submitted", machine="hiring_request", actor=actor)
    if row.status == "submitted":
        transition(row, "open", machine="hiring_request", actor=actor)
    return row


def add_note(session: Session, request_id: UUID, body: str, kind: str, actor: Actor) -> RequestNote:
    user = _recruiter(session, actor)
    if kind not in NOTE_KINDS:
        raise HiringError("invalid_note")
    _request(session, request_id)
    row = RequestNote(request_id=request_id, author_user_id=user.id, body=body.strip(), kind=kind)
    session.add(row)
    session.flush()
    return row


def add_attachment(
    session: Session,
    request_id: UUID,
    *,
    filename: str,
    data: bytes,
    media_type: str,
    actor: Actor,
) -> RequestAttachment:
    _recruiter(session, actor)
    _request(session, request_id)
    digest = sha256_bytes(data)
    key = LocalStorage(get_settings().storage_dir).write(digest, data)
    row = RequestAttachment(
        request_id=request_id,
        storage_key=key,
        original_filename=(filename or "attachment")[:500],
        media_type=media_type[:120],
        sha256=digest,
        byte_size=len(data),
    )
    session.add(row)
    session.flush()
    return row


def extract_requirements(session: Session, request_id: UUID, actor: Actor, reader=None) -> list[RequestRequirement]:
    _recruiter(session, actor)
    row = _request(session, request_id)
    reader = reader if reader is not None else get_requirement_reader()
    accepted, rejected, model_name, run_status = _propose(row.description, reader)
    previous = session.scalar(
        select(func.count()).select_from(RequestRequirement).where(RequestRequirement.request_id == request_id)
    )
    _clear_requirements(session, request_id)
    stored: list[RequestRequirement] = []
    for position, item in enumerate(accepted, start=1):
        requirement = RequestRequirement(
            request_id=request_id,
            position=position,
            label=item.label,
            requirement_text=item.text,
            strength=item.strength,
            source_quote=item.quote,
            review_status="proposed",
        )
        session.add(requirement)
        stored.append(requirement)
    session.flush()
    run = AgentRun(
        agent_name="requirement_extractor",
        request_id=row.id,
        model=model_name,
        prompt_version="requirements-v1",
        input_hash=sha256_text(row.description),
        status=run_status,
        validation_result="partial" if rejected and accepted else "accepted" if accepted else "rejected",
        output_ref=f"accepted:{len(stored)}",
        error_code="extractor_unavailable" if run_status != "succeeded" else None,
    )
    session.add(run)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="requirements_changed" if previous else "requirements_extracted",
        entity_type="hiring_request",
        entity_id=row.id,
        detail={
            "request_id": str(row.id),
            "count": len(stored),
            "outcome": "changed" if previous else "extracted",
            "agent_run_id": str(run.id),
        },
    )
    return stored


def update_requirement(
    session: Session,
    request_id: UUID,
    requirement_id: UUID,
    actor: Actor,
    *,
    text: str | None = None,
    strength: str | None = None,
    label: str | None = None,
    quote: str | None = None,
) -> RequestRequirement:
    _recruiter(session, actor)
    request = _request(session, request_id)
    row = _requirement(session, request_id, requirement_id)
    try:
        draft = validate_proposal(
            request.description,
            {
                "label": label or row.label,
                "text": text or row.requirement_text,
                "strength": strength or row.strength,
                "quote": quote or row.source_quote or "",
            },
        )
    except ProposalRejected as exc:
        raise HiringError(exc.code) from exc
    row.label = draft.label
    row.requirement_text = draft.text
    row.strength = draft.strength
    row.source_quote = draft.quote
    row.review_status = "proposed"
    write_audit(
        session,
        actor=actor,
        action="requirements_changed",
        entity_type="request_requirement",
        entity_id=row.id,
        detail={"request_id": str(request_id), "outcome": "edited", "strength": row.strength},
    )
    return row


def approve_requirements(
    session: Session,
    request_id: UUID,
    actor: Actor,
    requirement_ids: list[UUID] | None = None,
) -> list[RequestRequirement]:
    _recruiter(session, actor)
    request = _request(session, request_id)
    rows = session.scalars(
        select(RequestRequirement)
        .where(RequestRequirement.request_id == request_id)
        .order_by(RequestRequirement.position)
    ).all()
    chosen = [row for row in rows if requirement_ids is None or row.id in set(requirement_ids)]
    if requirement_ids is not None and len(chosen) != len(set(requirement_ids)):
        raise HiringError("not_found")
    approved: list[RequestRequirement] = []
    for row in chosen:
        try:
            validate_proposal(
                request.description,
                {
                    "label": row.label,
                    "text": row.requirement_text,
                    "strength": row.strength,
                    "quote": row.source_quote or "",
                },
            )
        except ProposalRejected as exc:
            raise HiringError(exc.code) from exc
        row.review_status = "approved"
        approved.append(row)
    write_audit(
        session,
        actor=actor,
        action="requirements_changed",
        entity_type="hiring_request",
        entity_id=request.id,
        detail={"request_id": str(request.id), "count": len(approved), "outcome": "approved"},
    )
    return approved


def _propose(description: str, reader):
    if reader is None:
        return [], 0, None, "skipped"
    try:
        raw = reader.propose(description)
    except ExtractorUnavailable:
        return [], 0, getattr(reader, "model_name", None), "failed"
    accepted = []
    rejected = 0
    for item in raw:
        try:
            accepted.append(validate_proposal(description, item))
        except ProposalRejected:
            rejected += 1
    return accepted, rejected, getattr(reader, "model_name", None), "succeeded"


def shortlist_match(session: Session, request_id: UUID, match_id: UUID, actor: Actor, note: str | None = None) -> ShortlistCandidate:
    user = _recruiter(session, actor)
    match = _match(session, request_id, match_id)
    if match.disposition not in {"recommended", "needs_review"}:
        raise HiringError("not_shortlistable")
    shortlist = session.scalar(
        select(Shortlist).where(Shortlist.request_id == request_id, Shortlist.status == "draft")
    )
    if shortlist is None:
        shortlist = Shortlist(request_id=request_id, status="draft")
        session.add(shortlist)
        session.flush()
    existing = session.scalar(
        select(ShortlistCandidate).where(
            ShortlistCandidate.shortlist_id == shortlist.id,
            ShortlistCandidate.candidate_id == match.candidate_id,
        )
    )
    if existing is not None:
        return existing
    row = ShortlistCandidate(
        shortlist_id=shortlist.id,
        candidate_id=match.candidate_id,
        match_id=match.id,
        added_by_user_id=user.id,
        review_state="shortlisted",
        note=(note or "").strip() or None,
    )
    session.add(row)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="shortlist_decision",
        entity_type="shortlist_candidate",
        entity_id=row.id,
        detail={
            "request_id": str(request_id),
            "candidate_id": str(match.candidate_id),
            "match_id": str(match.id),
            "shortlist_id": str(shortlist.id),
            "human_action": "shortlist",
        },
    )
    return row


def reject_match(session: Session, request_id: UUID, match_id: UUID, actor: Actor) -> CandidateMatch:
    _recruiter(session, actor)
    match = _match(session, request_id, match_id)
    if match.disposition == "excluded":
        raise HiringError("already_excluded")
    match.disposition = "rejected"
    placed = session.scalars(
        select(ShortlistCandidate).where(ShortlistCandidate.match_id == match.id)
    ).all()
    for item in placed:
        item.review_state = "rejected"
    write_audit(
        session,
        actor=actor,
        action="candidate_rejected",
        entity_type="candidate_match",
        entity_id=match.id,
        detail={
            "request_id": str(request_id),
            "candidate_id": str(match.candidate_id),
            "match_id": str(match.id),
            "human_action": "reject",
            "disposition": "rejected",
        },
    )
    return match


def request_view(session: Session, request_id: UUID) -> dict:
    row = _request(session, request_id)
    notes = session.scalars(
        select(RequestNote).where(RequestNote.request_id == request_id).order_by(RequestNote.created_at)
    ).all()
    attachments = session.scalars(
        select(RequestAttachment).where(RequestAttachment.request_id == request_id)
    ).all()
    requirements = session.scalars(
        select(RequestRequirement)
        .where(RequestRequirement.request_id == request_id)
        .order_by(RequestRequirement.position)
    ).all()
    found = session.scalar(
        select(func.count()).select_from(CandidateMatch).where(
            CandidateMatch.request_id == request_id,
            CandidateMatch.disposition.in_(("recommended", "needs_review")),
        )
    )
    shared = session.scalar(
        select(func.count())
        .select_from(SharingRecord)
        .join(ShortlistCandidate, ShortlistCandidate.candidate_id == SharingRecord.candidate_id)
        .join(Shortlist, Shortlist.id == ShortlistCandidate.shortlist_id)
        .where(Shortlist.request_id == request_id)
    )
    return {
        "id": str(row.id),
        "company": row.company_name,
        "job_title": row.job_title,
        "description": row.description,
        "received_at": row.received_at.isoformat(),
        "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
        "status": row.status,
        "notes": [_note_payload(item) for item in notes if item.kind == "note"],
        "updates": [_note_payload(item) for item in notes if item.kind == "update"],
        "next_steps": [_note_payload(item) for item in notes if item.kind == "next_step"],
        "attachments": [
            {
                "id": str(item.id),
                "filename": item.original_filename,
                "media_type": item.media_type,
                "byte_size": item.byte_size,
            }
            for item in attachments
        ],
        "candidates_found": int(found or 0),
        "candidates_shared": int(shared or 0),
        "requirements": [
            {
                "id": str(item.id),
                "label": item.label,
                "text": item.requirement_text,
                "strength": item.strength,
                "source_quote": item.source_quote,
                "review_status": item.review_status,
            }
            for item in requirements
        ],
    }


def _clear_requirements(session: Session, request_id: UUID) -> None:
    match_ids = list(
        session.scalars(select(CandidateMatch.id).where(CandidateMatch.request_id == request_id)).all()
    )
    if match_ids:
        session.execute(
            delete(MatchRequirementResult).where(MatchRequirementResult.match_id.in_(match_ids))
        )
        session.execute(
            ShortlistCandidate.__table__.update()
            .where(ShortlistCandidate.match_id.in_(match_ids))
            .values(match_id=None)
        )
        session.execute(delete(CandidateMatch).where(CandidateMatch.id.in_(match_ids)))
    session.execute(delete(RequestRequirement).where(RequestRequirement.request_id == request_id))
    session.flush()


def _note_payload(item: RequestNote) -> dict:
    return {
        "id": str(item.id),
        "body": item.body,
        "kind": item.kind,
        "author_user_id": str(item.author_user_id),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _request(session: Session, request_id: UUID) -> HiringRequest:
    row = session.get(HiringRequest, request_id)
    if row is None:
        raise HiringError("not_found")
    return row


def _requirement(session: Session, request_id: UUID, requirement_id: UUID) -> RequestRequirement:
    row = session.get(RequestRequirement, requirement_id)
    if row is None or row.request_id != request_id:
        raise HiringError("not_found")
    return row


def _match(session: Session, request_id: UUID, match_id: UUID) -> CandidateMatch:
    row = session.get(CandidateMatch, match_id)
    if row is None or row.request_id != request_id:
        raise HiringError("not_found")
    return row


def _recruiter(session: Session, actor: Actor) -> User:
    if actor.kind != "user" or actor.user_id is None:
        raise TransitionError("human_required")
    user = session.get(User, actor.user_id)
    if user is None or user.role != "recruiter":
        raise TransitionError("forbidden")
    return user


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

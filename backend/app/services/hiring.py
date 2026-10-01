"""Hiring requests, explicit requirements, and recruiter shortlist decisions."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import Actor
from app.domain.matching import overall_disposition
from app.domain.requirement_schema import ProposalRejected, validate_proposal
from app.domain.transitions import TransitionError, transition
from app.extraction.provider import ExtractorUnavailable
from app.extraction.requirement_provider import get_requirement_reader
from app.extraction.textutil import sha256_bytes, sha256_text
from app.models import (
    AgentRun,
    CandidateMatch,
    HiringRequest,
    Job,
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
    requested_count: int | None = None,
    contact_email: str | None = None,
) -> HiringRequest:
    user = _recruiter(session, actor)
    row = HiringRequest(
        company_name=company_name.strip(),
        job_title=job_title.strip(),
        description=description,
        status="draft",
        received_at=received_at,
        owner_user_id=user.id,
        requested_count=requested_count,
        contact_email=_contact(contact_email),
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


def set_contact(session: Session, request_id: UUID, contact_email: str, actor: Actor) -> HiringRequest:
    """The company contact the shortlist goes to. Changing it is recorded; the address itself never enters the audit."""
    _recruiter(session, actor)
    row = locked_request(session, request_id)
    value = _contact(contact_email)
    if value is None:
        raise HiringError("invalid_recipient")
    if row.contact_email != value:
        row.contact_email = value
        write_audit(
            session,
            actor=actor,
            action="request_contact_changed",
            entity_type="hiring_request",
            entity_id=row.id,
            detail={"request_id": str(row.id), "human_action": "set_contact"},
        )
    return row


def _contact(value: str | None) -> str | None:
    from app.extraction.contacts import normalize_email

    if value is None or not value.strip():
        return None
    normalized = normalize_email(value.strip())
    if normalized is None:
        raise HiringError("invalid_recipient")
    return normalized


def open_pool(session: Session, request_id: UUID, actor: Actor) -> HiringRequest:
    _recruiter(session, actor)
    row = _request(session, request_id)
    if row.last_match_completed_at is None:
        raise HiringError("pool_not_ready")
    seen = row.pool_opened_at
    if seen is not None and row.last_match_completed_at <= seen:
        return row
    row.pool_opened_at = utcnow()
    write_audit(
        session,
        actor=actor,
        action="pool_opened",
        entity_type="hiring_request",
        entity_id=row.id,
        detail={"request_id": str(row.id), "outcome": "opened"},
    )
    return row


def submit_request(session: Session, request_id: UUID, actor: Actor) -> HiringRequest:
    _recruiter(session, actor)
    row = _request(session, request_id)
    if row.status == "draft":
        transition(row, "submitted", machine="hiring_request", actor=actor)
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
    _actor_allowed(session, actor)
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
        prompt_version=getattr(reader, "prompt_version", "requirements-v1"),
        input_hash=sha256_text(row.description),
        status=run_status,
        validation_result="partial" if rejected and accepted else "accepted" if accepted else "rejected",
        # Counts and reason codes only. Never the job description or the proposed text.
        output_ref=_output_ref(len(stored), rejected, getattr(reader, "failure", None) if run_status == "fallback" else None),
        error_code="llm_unavailable" if run_status == "fallback" else "extractor_unavailable" if run_status != "succeeded" else None,
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
    has_pool = session.scalar(
        select(func.count()).select_from(CandidateMatch).where(CandidateMatch.request_id == request_id)
    )
    if has_pool:
        request.pool_stale = True
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
    # "Approve all" never revives a requirement HR rejected; naming it explicitly does.
    chosen = [
        row
        for row in rows
        if (row.review_status != "rejected" if requirement_ids is None else row.id in set(requirement_ids))
    ]
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
    if approved and request.last_match_completed_at is not None:
        # The pool was built before this approval. It stays provisional until the approved-only rematch finishes.
        request.pool_stale = True
    write_audit(
        session,
        actor=actor,
        action="requirements_changed",
        entity_type="hiring_request",
        entity_id=request.id,
        detail={"request_id": str(request.id), "count": len(approved), "outcome": "approved"},
    )
    return approved


def reject_requirement(session: Session, request_id: UUID, requirement_id: UUID, actor: Actor) -> RequestRequirement:
    """HR rejects one proposed (or approved) requirement. The row is kept, labelled rejected, and never matched on.

    If a pool exists it no longer reflects the requirements, so it is stale until the approved-only rematch runs."""
    _recruiter(session, actor)
    request = _request(session, request_id)
    row = _requirement(session, request_id, requirement_id)
    if row.review_status == "rejected":
        return row
    row.review_status = "rejected"
    if request.last_match_completed_at is not None:
        request.pool_stale = True
    write_audit(
        session,
        actor=actor,
        action="requirements_changed",
        entity_type="request_requirement",
        entity_id=row.id,
        detail={"request_id": str(request_id), "outcome": "rejected", "strength": row.strength},
    )
    return row


def _output_ref(accepted: int, rejected: dict[str, int], fallback_reason: str | None = None) -> str:
    ref = f"accepted:{accepted}"
    if rejected:
        ref += ";rejected:" + ",".join(f"{code}={count}" for code, count in sorted(rejected.items()))
    if fallback_reason:
        # Why the model did not answer (description_too_long, model_unreachable, model_reply_malformed). A code, never text.
        ref += f";fallback:{fallback_reason}"
    return ref


def _fallback_reason(ref: str | None) -> str | None:
    for part in (ref or "").split(";"):
        key, _, value = part.partition(":")
        if key == "fallback" and value.replace("_", "").isalnum():
            return value
    return None


def _parse_output_ref(ref: str | None) -> tuple[int | None, dict[str, int]]:
    accepted: int | None = None
    rejected: dict[str, int] = {}
    for part in (ref or "").split(";"):
        key, _, value = part.partition(":")
        if key == "accepted" and value.isdigit():
            accepted = int(value)
        elif key == "rejected":
            for item in value.split(","):
                code, _, count = item.partition("=")
                if code and count.isdigit():
                    rejected[code] = int(count)
    return accepted, rejected


def add_requirement(
    session: Session,
    request_id: UUID,
    actor: Actor,
    *,
    label: str,
    text: str,
    strength: str,
    quote: str,
) -> RequestRequirement:
    """A recruiter adds a requirement by hand. It must still quote the job description and pass every check."""
    _recruiter(session, actor)
    request = _request(session, request_id)
    try:
        draft = validate_proposal(request.description, {"label": label, "text": text, "strength": strength, "quote": quote})
    except ProposalRejected as exc:
        raise HiringError(exc.code) from exc
    position = (
        session.scalar(select(func.max(RequestRequirement.position)).where(RequestRequirement.request_id == request_id)) or 0
    ) + 1
    row = RequestRequirement(
        request_id=request_id,
        position=position,
        label=draft.label,
        requirement_text=draft.text,
        strength=draft.strength,
        source_quote=draft.quote,
        review_status="proposed",
    )
    session.add(row)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="requirements_changed",
        entity_type="request_requirement",
        entity_id=row.id,
        detail={"request_id": str(request_id), "outcome": "added", "strength": row.strength},
    )
    return row


def _propose(description: str, reader):
    if reader is None:
        return [], {}, None, "skipped"
    try:
        raw = reader.propose(description)
    except ExtractorUnavailable:
        return [], {}, getattr(reader, "model_name", None), "failed"
    accepted = []
    rejected: dict[str, int] = {}
    for item in raw:
        try:
            accepted.append(validate_proposal(description, item))
        except ProposalRejected as exc:
            rejected[exc.code] = rejected.get(exc.code, 0) + 1
    # A fallback is a different reader that answered. It is recorded as such, never as the model.
    status = "fallback" if getattr(reader, "fallback_used", False) else "succeeded"
    return accepted, rejected, getattr(reader, "model_name", None), status


def pool_status(session: Session, request: HiringRequest) -> str:
    """none: nothing matched yet. provisional: matched on requirements HR has not approved, or a rematch is pending.
    confirmed: the last match ran on HR-approved requirements only, and every requirement is approved.

    Only a confirmed pool can be shortlisted or shared. Viewing is never gated."""
    if request.last_match_completed_at is None:
        return "none"
    statuses = session.execute(
        select(RequestRequirement.review_status, func.count())
        .where(RequestRequirement.request_id == request.id)
        .group_by(RequestRequirement.review_status)
    ).all()
    counts = {status: count for status, count in statuses}
    # Rejected rows are a decision HR made; only rows still waiting for a decision keep the pool provisional.
    if request.pool_stale or counts.get("proposed") or not counts.get("approved"):
        return "provisional"
    pending = session.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.job_type == "process_request",
            Job.payload["request_id"].astext == str(request.id),
            Job.status.in_(("queued", "leased", "running")),
        )
    )
    # A queued or running rematch may still change the pool.
    return "provisional" if pending else "confirmed"


def shortlist_match(session: Session, request_id: UUID, match_id: UUID, actor: Actor, note: str | None = None) -> ShortlistCandidate:
    user = _recruiter(session, actor)
    # One decision at a time per request: a double click or two tabs must not open two draft shortlists.
    request = locked_request(session, request_id)
    match = _match(session, request_id, match_id)
    if pool_status(session, request) != "confirmed":
        raise HiringError("pool_provisional")
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
        if existing.review_state == "shortlisted":
            return existing  # a repeated click
        # Rejected earlier and restored since: shortlisting again is a new decision, recorded as one.
        existing.review_state = "shortlisted"
        existing.match_id = match.id
        existing.added_by_user_id = user.id
        existing.note = (note or "").strip() or existing.note
        session.flush()
        _audit_shortlist(session, actor, request_id, match, shortlist, existing)
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
    _audit_shortlist(session, actor, request_id, match, shortlist, row)
    return row


def _audit_shortlist(session, actor, request_id, match, shortlist, row) -> None:
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


def restore_match(session: Session, request_id: UUID, match_id: UUID, actor: Actor) -> CandidateMatch:
    """Undo a recruiter's rejection. The candidate goes back to what the requirement verdicts say (eligible, needs
    review or excluded); nothing is shortlisted by this. Rejecting by mistake is recoverable."""
    _recruiter(session, actor)
    locked_request(session, request_id)
    match = _match(session, request_id, match_id)
    if match.disposition != "rejected":
        return match  # nothing to undo (or a repeated click)
    pairs = session.execute(
        select(RequestRequirement.strength, MatchRequirementResult.result)
        .join(MatchRequirementResult, MatchRequirementResult.requirement_id == RequestRequirement.id)
        .where(MatchRequirementResult.match_id == match.id)
    ).all()
    match.disposition = overall_disposition([(strength, result) for strength, result in pairs])
    write_audit(
        session,
        actor=actor,
        action="candidate_restored",
        entity_type="candidate_match",
        entity_id=match.id,
        detail={
            "request_id": str(request_id),
            "candidate_id": str(match.candidate_id),
            "match_id": str(match.id),
            "human_action": "restore",
            "disposition": match.disposition,
        },
    )
    return match


def reject_match(session: Session, request_id: UUID, match_id: UUID, actor: Actor) -> CandidateMatch:
    _recruiter(session, actor)
    locked_request(session, request_id)
    match = _match(session, request_id, match_id)
    if match.disposition == "excluded":
        raise HiringError("already_excluded")
    if match.disposition == "rejected":
        return match  # a repeated click: already decided, nothing new to record
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
    # Candidates actually sent for THIS request. A candidate shared for another request does not count here.
    shared = session.scalar(
        select(func.count(func.distinct(SharingRecord.candidate_id))).where(
            SharingRecord.request_id == request_id,
            SharingRecord.status == "sent",
        )
    )
    from app.services.processing import processing_view

    processing = processing_view(session, request_id)
    latest_run = session.scalar(
        select(AgentRun)
        .where(AgentRun.request_id == request_id, AgentRun.agent_name == "requirement_extractor")
        .order_by(AgentRun.created_at.desc())
        .limit(1)
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
        "requirements_source": (
            {
                "model": latest_run.model,
                "prompt_version": latest_run.prompt_version,
                "fallback": latest_run.status == "fallback",
                "fallback_reason": _fallback_reason(latest_run.output_ref),
                "accepted": _parse_output_ref(latest_run.output_ref)[0],
                "rejected": _parse_output_ref(latest_run.output_ref)[1],
            }
            if latest_run is not None
            else None
        ),
        "processing": processing,
        "pool_stale": row.pool_stale,
        "pool_opened_at": row.pool_opened_at.isoformat() if row.pool_opened_at else None,
        "last_match_completed_at": row.last_match_completed_at.isoformat() if row.last_match_completed_at else None,
        "requested_count": row.requested_count,
        "contact_email": row.contact_email,
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


def locked_request(session: Session, request_id: UUID) -> HiringRequest:
    """The request row, locked until this transaction ends, read fresh. Recruiter decisions on one request run one at
    a time, so a retry sees what the first attempt committed instead of repeating it."""
    row = session.scalar(
        select(HiringRequest)
        .where(HiringRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
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


def _actor_allowed(session: Session, actor: Actor) -> None:
    """Human recruiters and the worker's system actor may run the automatic steps. Nothing else."""
    if actor.kind == "system":
        return
    _recruiter(session, actor)


def _recruiter(session: Session, actor: Actor) -> User:
    if actor.kind != "user" or actor.user_id is None:
        raise TransitionError("human_required")
    user = session.get(User, actor.user_id)
    if user is None or user.role != "recruiter":
        raise TransitionError("forbidden")
    return user


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

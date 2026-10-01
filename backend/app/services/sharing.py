"""A recruiter approves a candidate, then sends a short notice through the mail boundary.

Shortlist sharing is a separate approval. Matching and shortlisting do not send mail.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import Actor
from app.domain.transitions import TransitionError, utcnow
from app.models import (
    ApprovalDecision,
    AuditEvent,
    Candidate,
    CandidateMatch,
    HiringRequest,
    MatchRequirementResult,
    RequestRequirement,
    SharingRecord,
    Shortlist,
    ShortlistCandidate,
    User,
)
from app.services.audit import write_audit
from app.services.mail import LOCAL_SMTP_HOSTS, MailSender, OutboundEmail


class SendError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def share_preview(session: Session, request_id: UUID, candidate_id: UUID, actor: Actor) -> dict:
    _recruiter(session, actor)
    request = _request(session, request_id)
    candidate = _candidate(session, candidate_id)
    entry = _shortlisted(session, request_id, candidate_id)
    record = _sent_share(session, entry)
    return _preview_payload(session, request, candidate, entry, record)


def approve_share(session: Session, request_id: UUID, candidate_id: UUID, actor: Actor) -> ApprovalDecision:
    user = _recruiter(session, actor)
    _confirmed_pool(session, _request(session, request_id))
    entry = _shortlisted(session, request_id, candidate_id, lock=True)
    _still_matched(session, entry)
    existing = _share_approval(session, entry.id)
    if existing is not None:
        return existing
    row = ApprovalDecision(
        subject_type="share",
        subject_id=entry.id,
        decision="approved",
        actor_user_id=user.id,
    )
    session.add(row)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="share_approved",
        entity_type="shortlist_candidate",
        entity_id=entry.id,
        detail={
            "request_id": str(request_id),
            "candidate_id": str(candidate_id),
            "shortlist_id": str(entry.shortlist_id),
            "human_action": "approve_share",
        },
    )
    return row


def send_share(
    session: Session, request_id: UUID, candidate_id: UUID, actor: Actor, sender: MailSender
) -> SharingRecord:
    user = _recruiter(session, actor)
    _local_mail_only()
    request = _request(session, request_id)
    candidate = _candidate(session, candidate_id)
    # The lock is held until the sharing record commits. A second click waits here, then finds the record and
    # returns it: the company receives one email, never one per click.
    entry = _shortlisted(session, request_id, candidate_id, lock=True)
    existing = _sent_share(session, entry)
    if existing is not None:
        return existing
    _confirmed_pool(session, request)
    _still_matched(session, entry)
    if _share_approval(session, entry.id) is None:
        raise SendError("approval_required")
    if not request.contact_email:
        raise SendError("recipient_missing")  # never a default address: the recruiter names the company contact
    settings = get_settings()
    message = _share_message(session, request, candidate, entry)
    try:
        sender.send(message)
    except Exception:
        write_audit(
            session,
            actor=actor,
            action="candidate_share_failed",
            entity_type="candidate",
            entity_id=candidate.id,
            detail={
                "request_id": str(request.id),
                "candidate_id": str(candidate.id),
                "shortlist_id": str(entry.shortlist_id),
                "error_code": "mail_delivery_failed",
            },
        )
        raise SendError("mail_delivery_failed") from None
    record = SharingRecord(
        shortlist_id=entry.shortlist_id,
        request_id=request.id,
        candidate_id=candidate.id,
        actor_user_id=user.id,
        recipient=request.contact_email,
        status="sent",
        sent_at=utcnow(),
        destination=settings.mail_destination,
    )
    session.add(record)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="candidate_shared",
        entity_type="sharing_record",
        entity_id=record.id,
        detail={
            "request_id": str(request.id),
            "candidate_id": str(candidate.id),
            "shortlist_id": str(entry.shortlist_id),
            "outcome": "sent",
            "human_action": "share",
        },
    )
    return record


def share_view(session: Session, record: SharingRecord) -> dict:
    audit = session.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "candidate_shared",
            AuditEvent.entity_id == record.id,
        )
    )
    sender = session.get(User, record.actor_user_id)
    return {
        "id": str(record.id),
        "status": record.status,
        "destination": record.destination,
        "recipient": record.recipient,
        "request_id": str(record.request_id) if record.request_id else None,
        "candidate_id": str(record.candidate_id),
        "shortlist_id": str(record.shortlist_id) if record.shortlist_id else None,
        "sent_at": _iso(record.sent_at),
        "sender": sender.full_name if sender else None,
        "audit": None
        if audit is None
        else {"id": str(audit.id), "action": audit.action, "created_at": _iso(audit.created_at)},
    }


def _preview_payload(session, request, candidate, entry, record) -> dict:
    selected = _selected_information(session, candidate, entry)
    return {
        "company": request.company_name,
        "recipient": request.contact_email,
        "candidate": _public_name(candidate.display_name),
        "candidate_id": str(candidate.id),
        "role": request.job_title,
        "selected": selected,
        "approved": _share_approval(session, entry.id) is not None,
        "sharing": None if record is None else share_view(session, record),
    }


def _share_message(session, request: HiringRequest, candidate: Candidate, entry: ShortlistCandidate) -> OutboundEmail:
    selected = _selected_information(session, candidate, entry)
    met = ", ".join(selected["requirements_met"]) or "none recorded"
    years = selected["years_of_experience"]
    years_line = "not recorded" if years is None else str(years)
    body = (
        "A recruiter approved sharing a shortlisted candidate.\n"
        f"Company: {request.company_name}\n"
        f"Role: {request.job_title}\n"
        f"Candidate: {_public_name(candidate.display_name)}\n"
        f"Years: {years_line}\n"
        f"Requirements met: {met}\n"
        f"Reference: {candidate.id}\n"
    )
    if "@" in body:
        raise SendError("unsafe_share_payload")
    return OutboundEmail(
        to=request.contact_email,
        subject=_subject(request),
        body=body,
    )


def _subject(request: HiringRequest) -> str:
    """Company and role only, on one line: a header never carries a line break or candidate details."""
    text = f"Candidate shortlisted for {request.company_name} — {request.job_title}"
    return " ".join(text.split())[:200]


def _selected_information(session: Session, candidate: Candidate, entry: ShortlistCandidate) -> dict:
    """What the company is told: the years and the requirements of THIS request the candidate met.

    No job title: titles are read from free-form CV lines and a fragment such as "financial, and humanitarian aid
    delivered to Ukraine (" was about to be sent to a company as one. HR still reads titles on the profile.

    Not the raw skills list: a CV's skills section carries hobbies and unrelated detail ("Poker", "Graffiti") that
    has no business leaving Cadence. Every requirement named here was met with evidence the recruiter reviewed."""
    met: list[str] = []
    if entry.match_id is not None:
        rows = session.execute(
            select(RequestRequirement.requirement_text, RequestRequirement.label)
            .join(MatchRequirementResult, MatchRequirementResult.requirement_id == RequestRequirement.id)
            .where(MatchRequirementResult.match_id == entry.match_id, MatchRequirementResult.result == "meets")
            .order_by(RequestRequirement.position)
        ).all()
        met = [f"{text}+ years of experience" if label == "experience" else text for text, label in rows]
    years = None
    if candidate.years_of_experience is not None:
        number = float(candidate.years_of_experience)
        years = int(number) if number.is_integer() else number
    return {
        "years_of_experience": years,
        "requirements_met": [name for name in met if _safe_label(name)],
    }


def _public_name(value: str | None) -> str:
    if value and _safe_label(value):
        return value
    return "Candidate"


def _safe_label(value: str) -> bool:
    return "@" not in value and "\n" not in value and len(value) <= 200


def _local_mail_only() -> None:
    settings = get_settings()
    if settings.environment not in {"local", "demo"}:
        return
    if settings.mail_destination != "smtp" or settings.smtp_host not in LOCAL_SMTP_HOSTS:
        raise SendError("external_mail_blocked")


def _confirmed_pool(session: Session, request: HiringRequest) -> None:
    """Nothing is shared from a provisional pool: its requirements are not yet the ones HR approved."""
    from app.services.hiring import pool_status

    if pool_status(session, request) != "confirmed":
        raise SendError("pool_provisional")


def _still_matched(session: Session, entry: ShortlistCandidate) -> None:
    """A rematch on edited requirements can rule out a candidate who was shortlisted earlier. That candidate is not shared."""
    match = session.get(CandidateMatch, entry.match_id) if entry.match_id else None
    if match is None or match.disposition not in {"recommended", "needs_review"}:
        raise SendError("not_shortlistable")


def _request(session: Session, request_id: UUID) -> HiringRequest:
    row = session.get(HiringRequest, request_id)
    if row is None:
        raise SendError("not_found")
    return row


def _candidate(session: Session, candidate_id: UUID) -> Candidate:
    row = session.get(Candidate, candidate_id)
    if row is None:
        raise SendError("not_found")
    return row


def _shortlisted(session: Session, request_id: UUID, candidate_id: UUID, *, lock: bool = False) -> ShortlistCandidate:
    query = (
        select(ShortlistCandidate)
        .join(Shortlist, Shortlist.id == ShortlistCandidate.shortlist_id)
        .where(
            Shortlist.request_id == request_id,
            ShortlistCandidate.candidate_id == candidate_id,
            ShortlistCandidate.review_state == "shortlisted",
        )
    )
    if lock:
        query = query.with_for_update(of=ShortlistCandidate).execution_options(populate_existing=True)
    row = session.scalar(query)
    if row is None:
        raise SendError("not_shortlisted")
    return row


def _share_approval(session: Session, entry_id: UUID) -> ApprovalDecision | None:
    return session.scalar(
        select(ApprovalDecision).where(
            ApprovalDecision.subject_type == "share",
            ApprovalDecision.subject_id == entry_id,
            ApprovalDecision.decision == "approved",
        )
    )


def _sent_share(session: Session, entry: ShortlistCandidate) -> SharingRecord | None:
    return session.scalar(
        select(SharingRecord).where(
            SharingRecord.shortlist_id == entry.shortlist_id,
            SharingRecord.candidate_id == entry.candidate_id,
            SharingRecord.status == "sent",
        )
    )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _recruiter(session: Session, actor: Actor) -> User:
    if actor.kind != "user" or actor.user_id is None:
        raise TransitionError("human_required")
    user = session.get(User, actor.user_id)
    if user is None or user.role != "recruiter":
        raise TransitionError("forbidden")
    return user

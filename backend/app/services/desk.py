"""Read-only recruiter desk. It lists existing rows and does not decide them."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.actor import Actor
from app.models import (
    ApprovalDecision,
    AuditEvent,
    Candidate,
    CandidateMatch,
    DuplicateReview,
    HiringRequest,
    ProblemReport,
    RequestRequirement,
    SharingRecord,
    Shortlist,
    ShortlistCandidate,
    User,
)
from app.services.hiring import pool_status
from app.services.problems import list_reports
from app.services.processing import processing_view

_AWAITING = ("recommended", "needs_review")
_INACTIVE_REQUESTS = ("closed", "cancelled")
_LIMIT = 20


class DeskError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def dashboard(session: Session, actor: Actor) -> dict:
    user = _recruiter(session, actor)
    reviews = _pending_reviews(session)
    requirements = _proposed_requirements(session)
    matches = _matches_awaiting(session)
    shortlisted = _shortlisted(session)
    shares = [item for item in shortlisted if not _share_approved(session, item.id)]
    reports = [row for row in list_reports(session, actor) if row.status == "open"]
    requests = _active_requests(session)
    received = _requests_received(session)
    pools = _new_pools(session)
    return {
        "counts": {
            "relationship_reviews": len(reviews),
            "requirements_awaiting_approval": len(requirements),
            "matches_awaiting_review": len(matches),
            "shortlisted_candidates": len(shortlisted),
            "shares_awaiting_approval": len(shares),
            "open_problem_reports": len(reports),
            "active_hiring_requests": len(requests),
            "requests_received": len(received),
            "new_matches": len(pools),
            "duplicate_reviews": len(reviews),
            "reviews_needing_attention": len(reviews) + len(requirements) + len(matches) + len(shares),
        },
        "relationship_reviews": [_review_item(session, row) for row in reviews[:_LIMIT]],
        "requirements_awaiting_approval": [_requirement_item(row) for row in requirements[:_LIMIT]],
        "matches_awaiting_review": [_match_item(row) for row in matches[:_LIMIT]],
        "shortlisted_candidates": [_shortlist_item(session, row) for row in shortlisted[:_LIMIT]],
        "shares_awaiting_approval": [_share_item(session, row) for row in shares[:_LIMIT]],
        "open_problem_reports": [_report_item(row) for row in reports[:_LIMIT]],
        "recent_activity": _activity(session),
        "active_hiring_requests": [_request_item(row) for row in requests[:_LIMIT]],
        "new_match_pools": [_request_item(row) for row in pools[:_LIMIT]],
        "needs_you_now": sorted(
            [
                *[
                    _item(
                        "new_matches",
                        _request_label(row),
                        "pool_ready",
                        row.last_match_completed_at,
                        f"/hiring?request={row.id}",
                    )
                    for row in pools
                ],
                *[_share_item(session, row) for row in shares],
                *[_review_item(session, row) for row in reviews],
            ],
            key=lambda item: item["created_at"],
        )[:_LIMIT],
        "viewer_id": str(user.id),
    }


def work_queue(session: Session, actor: Actor) -> dict:
    _recruiter(session, actor)
    items = [
        *[_review_item(session, row) for row in _pending_reviews(session)],
        *[_requirement_item(row) for row in _proposed_requirements(session)],
        *[_match_item(row) for row in _matches_awaiting(session)],
        *[
            _share_item(session, row)
            for row in _shortlisted(session)
            if not _share_approved(session, row.id)
        ],
    ]
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return {"items": items[:50]}


def _recruiter(session: Session, actor: Actor) -> User:
    if actor.kind != "user" or actor.user_id is None:
        raise DeskError("recruiter_required")
    user = session.get(User, actor.user_id)
    if user is None or user.role != "recruiter":
        raise DeskError("recruiter_required")
    return user


def _pending_reviews(session: Session) -> list[DuplicateReview]:
    return list(
        session.scalars(
            select(DuplicateReview)
            .where(DuplicateReview.status == "pending")
            .order_by(DuplicateReview.created_at.desc())
        ).all()
    )


def _untouched_pool_clause():
    """Spec: only reviews in a pool nobody has looked at yet need attention. Opening the pool
    acknowledges it; a re-match after an edit (last_match_completed_at > pool_opened_at) makes
    the pool untouched again. Closed/cancelled requests never nag."""
    return or_(
        HiringRequest.pool_opened_at.is_(None),
        HiringRequest.last_match_completed_at > HiringRequest.pool_opened_at,
    )


def _proposed_requirements(session: Session) -> list[tuple[HiringRequest, int, object]]:
    """One entry per request that still has requirements waiting for a decision: (request, how many, newest).

    A pending approval stays on the list until HR decides it, whether or not anyone has opened the provisional pool."""
    rows = session.execute(
        select(HiringRequest, func.count(RequestRequirement.id), func.max(RequestRequirement.created_at))
        .join(RequestRequirement, RequestRequirement.request_id == HiringRequest.id)
        .where(
            RequestRequirement.review_status == "proposed",
            HiringRequest.status.not_in(_INACTIVE_REQUESTS),
        )
        .group_by(HiringRequest.id)
        .order_by(func.max(RequestRequirement.created_at).desc())
    ).all()
    return [(request, int(count), newest) for request, count, newest in rows]


def _matches_awaiting(session: Session) -> list[tuple[HiringRequest, int, object]]:
    """One entry per CONFIRMED pool nobody has opened yet: (request, candidates awaiting a decision, matched at).

    A provisional pool is not listed here: its next step is the requirement approval above. Shortlisted candidates and
    candidates a recruiter rejected are decided already."""
    shortlisted = select(ShortlistCandidate.match_id).where(
        ShortlistCandidate.review_state == "shortlisted", ShortlistCandidate.match_id.is_not(None)
    )
    rows = session.execute(
        select(HiringRequest, func.count(CandidateMatch.id))
        .join(CandidateMatch, CandidateMatch.request_id == HiringRequest.id)
        .where(
            CandidateMatch.disposition.in_(_AWAITING),
            CandidateMatch.id.not_in(shortlisted),
            HiringRequest.status.not_in(_INACTIVE_REQUESTS),
            _untouched_pool_clause(),
        )
        .group_by(HiringRequest.id)
        .order_by(HiringRequest.last_match_completed_at.desc())
    ).all()
    return [
        (request, int(count), request.last_match_completed_at)
        for request, count in rows
        if pool_status(session, request) == "confirmed"
    ]


def _shortlisted(session: Session) -> list[ShortlistCandidate]:
    """Shortlisted candidates still waiting for a person: not yet sent to the company."""
    sent = select(SharingRecord.id).where(
        SharingRecord.shortlist_id == ShortlistCandidate.shortlist_id,
        SharingRecord.candidate_id == ShortlistCandidate.candidate_id,
        SharingRecord.status == "sent",
    )
    return list(
        session.scalars(
            select(ShortlistCandidate)
            .join(Shortlist, Shortlist.id == ShortlistCandidate.shortlist_id)
            .where(
                ShortlistCandidate.review_state == "shortlisted",
                Shortlist.status == "draft",
                ~sent.exists(),
            )
            .order_by(ShortlistCandidate.created_at.desc())
        ).all()
    )


def _requests_received(session: Session) -> list[HiringRequest]:
    rows = _active_requests(session)
    return [row for row in rows if processing_view(session, row.id)["stage"] != "complete"]


def _new_pools(session: Session) -> list[HiringRequest]:
    out = []
    for row in _active_requests(session):
        if processing_view(session, row.id)["stage"] != "complete" or row.last_match_completed_at is None:
            continue
        if row.pool_opened_at is None or row.last_match_completed_at > row.pool_opened_at:
            out.append(row)
    return out


def _active_requests(session: Session) -> list[HiringRequest]:
    return list(
        session.scalars(
            select(HiringRequest)
            .where(HiringRequest.status.not_in(_INACTIVE_REQUESTS))
            .order_by(HiringRequest.received_at.desc())
        ).all()
    )


def _share_approved(session: Session, entry_id) -> bool:
    found = session.scalar(
        select(ApprovalDecision.id).where(
            ApprovalDecision.subject_type == "share",
            ApprovalDecision.subject_id == entry_id,
            ApprovalDecision.decision == "approved",
        )
    )
    return found is not None


def _review_item(session: Session, row: DuplicateReview) -> dict:
    name = _name(session, row.candidate_id)
    href = f"/?document={row.document_id}" if row.document_id else "/data"
    item = _item("relationship_review", name, row.status, row.created_at, href)
    # What Cadence recommends and how strongly, so a person can see the obvious ones without opening each.
    item["relationship"] = row.likely_relationship
    item["recommended_action"] = row.recommended_action
    item["confidence"] = float(row.confidence) if row.confidence is not None else None
    return item


def _requirement_item(entry: tuple[HiringRequest, int, object]) -> dict:
    request, count, newest = entry
    item = _item("requirement_approval", _request_label(request), "proposed", newest, f"/hiring?request={request.id}")
    item["count"] = count
    return item


def _match_item(entry: tuple[HiringRequest, int, object]) -> dict:
    request, count, matched_at = entry
    item = _item("match_review", _request_label(request), "pool_confirmed", matched_at, f"/hiring?request={request.id}")
    item["count"] = count
    return item


def _shortlist_item(session: Session, row: ShortlistCandidate) -> dict:
    shortlist = session.get(Shortlist, row.shortlist_id)
    request = session.get(HiringRequest, shortlist.request_id) if shortlist else None
    subject = f"{_name(session, row.candidate_id)} · {_request_label(request)}"
    return _item(
        "shortlist",
        subject,
        row.review_state,
        row.created_at,
        f"/hiring?request={shortlist.request_id}&candidate={row.candidate_id}" if shortlist else "/hiring",
    )


def _share_item(session: Session, row: ShortlistCandidate) -> dict:
    item = _shortlist_item(session, row)
    item["type"] = "share_approval"
    item["status"] = "awaiting_approval"
    return item


def _report_item(row: ProblemReport) -> dict:
    return _item("problem_report", row.summary, row.status, row.created_at, "/reports")


def _request_item(row: HiringRequest) -> dict:
    return _item("hiring_request", _request_label(row), row.status, row.received_at, f"/hiring?request={row.id}")


def _activity(session: Session) -> list[dict]:
    """The latest events with who and on what, in the same shape as the audit trail page."""
    from app.services.audit_view import describe_events

    rows = session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(12)).all()
    events = describe_events(session, list(rows))
    for event in events:
        event["actor_kind"] = event["actor"]["kind"]  # kept for older clients
    return events


def _item(kind: str, subject: str, status: str, created, href: str) -> dict:
    return {
        "type": kind,
        "subject": subject,
        "status": status,
        "created_at": created.isoformat() if created is not None else "",
        "href": href,
    }


def _name(session: Session, candidate_id) -> str:
    if candidate_id is None:
        return "Unnamed candidate"
    candidate = session.get(Candidate, candidate_id)
    if candidate is None or not candidate.display_name:
        return "Unnamed candidate"
    return candidate.display_name


def _request_label(request: HiringRequest | None) -> str:
    if request is None:
        return "Hiring request"
    return f"{request.company_name} · {request.job_title}"

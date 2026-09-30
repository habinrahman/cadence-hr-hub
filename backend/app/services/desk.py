"""Read-only recruiter desk. It lists existing rows and does not decide them."""

from __future__ import annotations

from sqlalchemy import select
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
    Shortlist,
    ShortlistCandidate,
    User,
)
from app.services.problems import list_reports

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
    return {
        "counts": {
            "relationship_reviews": len(reviews),
            "requirements_awaiting_approval": len(requirements),
            "matches_awaiting_review": len(matches),
            "shortlisted_candidates": len(shortlisted),
            "shares_awaiting_approval": len(shares),
            "open_problem_reports": len(reports),
            "active_hiring_requests": len(requests),
        },
        "relationship_reviews": [_review_item(session, row) for row in reviews[:_LIMIT]],
        "requirements_awaiting_approval": [_requirement_item(session, row) for row in requirements[:_LIMIT]],
        "matches_awaiting_review": [_match_item(session, row) for row in matches[:_LIMIT]],
        "shortlisted_candidates": [_shortlist_item(session, row) for row in shortlisted[:_LIMIT]],
        "shares_awaiting_approval": [_share_item(session, row) for row in shares[:_LIMIT]],
        "open_problem_reports": [_report_item(row) for row in reports[:_LIMIT]],
        "recent_activity": _activity(session),
        "active_hiring_requests": [_request_item(row) for row in requests[:_LIMIT]],
        "viewer_id": str(user.id),
    }


def work_queue(session: Session, actor: Actor) -> dict:
    _recruiter(session, actor)
    items = [
        *[_review_item(session, row) for row in _pending_reviews(session)],
        *[_requirement_item(session, row) for row in _proposed_requirements(session)],
        *[_match_item(session, row) for row in _matches_awaiting(session)],
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


def _proposed_requirements(session: Session) -> list[RequestRequirement]:
    return list(
        session.scalars(
            select(RequestRequirement)
            .where(RequestRequirement.review_status == "proposed")
            .order_by(RequestRequirement.created_at.desc())
        ).all()
    )


def _matches_awaiting(session: Session) -> list[CandidateMatch]:
    shortlisted_match_ids = {
        item
        for item in session.scalars(
            select(ShortlistCandidate.match_id).where(
                ShortlistCandidate.review_state == "shortlisted",
                ShortlistCandidate.match_id.is_not(None),
            )
        )
        if item is not None
    }
    rows = session.scalars(
        select(CandidateMatch)
        .where(CandidateMatch.disposition.in_(_AWAITING))
        .order_by(CandidateMatch.created_at.desc())
    ).all()
    return [row for row in rows if row.id not in shortlisted_match_ids]


def _shortlisted(session: Session) -> list[ShortlistCandidate]:
    return list(
        session.scalars(
            select(ShortlistCandidate)
            .where(ShortlistCandidate.review_state == "shortlisted")
            .order_by(ShortlistCandidate.created_at.desc())
        ).all()
    )


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
    return _item("relationship_review", name, row.status, row.created_at, href)


def _requirement_item(session: Session, row: RequestRequirement) -> dict:
    request = session.get(HiringRequest, row.request_id)
    subject = _request_label(request)
    return _item("requirement_approval", subject, row.review_status, row.created_at, f"/hiring?request={row.request_id}")


def _match_item(session: Session, row: CandidateMatch) -> dict:
    request = session.get(HiringRequest, row.request_id)
    subject = f"{_name(session, row.candidate_id)} · {_request_label(request)}"
    return _item(
        "match_review",
        subject,
        row.disposition,
        row.created_at,
        f"/hiring?request={row.request_id}",
    )


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
    rows = session.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(12)).all()
    return [
        {
            "action": row.action,
            "actor_kind": row.actor_kind,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


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

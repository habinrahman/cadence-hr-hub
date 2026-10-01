"""Read the audit trail the way a person asks about it: who did what, when, to which request, candidate or file.

Audit rows store ids and codes only (see services.audit). The names a recruiter reads are looked up here, at read
time, from the rows the ids point to, so nothing personal is ever written into the audit table itself.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Candidate, CandidateDocument, HiringRequest, User

MAX_LIMIT = 100
# Opening a page is recorded for privacy, but it is not a decision. "Decisions" leaves these out.
VIEW_ACTIONS = frozenset(
    {"candidate_viewed", "pii_text_access", "review_comparison_viewed", "cv_preview_viewed", "pool_opened"}
)
CATEGORIES = {
    "hiring": frozenset(
        {
            "hiring_request_created",
            "request_contact_changed",
            "requirements_extracted",
            "requirements_changed",
            "matching_run",
            "candidate_recommended",
            "shortlist_decision",
            "candidate_rejected",
            "candidate_restored",
            "share_approved",
            "candidate_shared",
            "candidate_share_failed",
            "hiring_activity_exported",
        }
    ),
    "cvs": frozenset(
        {
            "document_received",
            "document_extracted",
            "same_document",
            "document_needs_ocr",
            "duplicate_review_opened",
            "duplicate_review_rescored",
            "duplicate_review_decided",
            "profiles_merged",
            "excel_import_completed",
            "sourced_cv_attached",
            "sourced_duplicate_detected",
            "sourced_candidate_created",
            "sourced_candidate_attached",
            "sourced_review_decided",
        }
    ),
}


def audit_page(
    session: Session,
    *,
    limit: int = 50,
    before: datetime | None = None,
    category: str | None = None,
    request_id: UUID | None = None,
    candidate_id: UUID | None = None,
) -> dict:
    """Newest first, one page at a time. `before` is the created_at of the last row already shown."""
    limit = max(1, min(limit, MAX_LIMIT))
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    if before is not None:
        query = query.where(AuditEvent.created_at < before)
    if category == "decisions":
        query = query.where(AuditEvent.actor_kind == "user", AuditEvent.action.not_in(VIEW_ACTIONS))
    elif category in CATEGORIES:
        query = query.where(AuditEvent.action.in_(CATEGORIES[category]))
    if request_id is not None:
        query = query.where(or_(AuditEvent.entity_id == request_id, AuditEvent.detail["request_id"].astext == str(request_id)))
    if candidate_id is not None:
        query = query.where(
            or_(AuditEvent.entity_id == candidate_id, AuditEvent.detail["candidate_id"].astext == str(candidate_id))
        )
    rows = session.scalars(query.limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return {
        "events": describe_events(session, rows),
        "next_before": rows[-1].created_at.isoformat() if more and rows else None,
    }


def describe_events(session: Session, rows: list[AuditEvent]) -> list[dict]:
    """Each row with the actor's name and the request, candidate and file it concerns, looked up in one query each."""
    users = _names(session, User, User.full_name, {row.actor_user_id for row in rows})
    request_ids = {_id(row, "request_id", "hiring_request") for row in rows}
    candidate_ids = {_id(row, "candidate_id", "candidate") for row in rows}
    document_ids = {_id(row, "document_id", "candidate_document") for row in rows}
    requests = {
        request.id: f"{request.company_name} · {request.job_title}"
        for request in session.scalars(select(HiringRequest).where(HiringRequest.id.in_(_known(request_ids))))
    }
    candidates = _names(session, Candidate, Candidate.display_name, candidate_ids)
    documents = _names(session, CandidateDocument, CandidateDocument.original_filename, document_ids)
    events = []
    for row in rows:
        request_id = _id(row, "request_id", "hiring_request")
        candidate_id = _id(row, "candidate_id", "candidate")
        document_id = _id(row, "document_id", "candidate_document")
        events.append(
            {
                "id": str(row.id),
                "created_at": row.created_at.isoformat(),
                "action": row.action,
                "actor": {
                    "kind": row.actor_kind,
                    "name": users.get(row.actor_user_id) if row.actor_user_id else None,
                },
                "request": _ref(request_id, requests),
                "candidate": _ref(candidate_id, candidates, fallback="Unnamed candidate"),
                "document": _ref(document_id, documents, fallback="File"),
                "detail": row.detail or {},
            }
        )
    return events


def _id(row: AuditEvent, key: str, entity_type: str) -> UUID | None:
    """The id of the object of this kind: the event's own entity, or the id its detail names."""
    if row.entity_type == entity_type and row.entity_id is not None:
        return row.entity_id
    value = (row.detail or {}).get(key)
    try:
        return UUID(value) if value else None
    except (TypeError, ValueError):
        return None


def _known(ids: set[UUID | None]) -> list[UUID]:
    return [item for item in ids if item is not None]


def _names(session: Session, model, column, ids: set[UUID | None]) -> dict[UUID, str | None]:
    known = _known(ids)
    if not known:
        return {}
    return dict(session.execute(select(model.id, column).where(model.id.in_(known))).all())


def _ref(identifier: UUID | None, labels: dict, *, fallback: str | None = None) -> dict | None:
    """None when there is no id, or the id does not point at a row of this kind."""
    if identifier is None or identifier not in labels:
        return None
    return {"id": str(identifier), "label": labels[identifier] or fallback}

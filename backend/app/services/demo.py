"""Demo operator controls. Local-only tooling; the routes live behind an environment guard."""

from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import Actor
from app.models import (
    Base,
    AgentRun,
    Application,
    ApprovalDecision,
    AuditEvent,
    Candidate,
    CandidateCertificate,
    CandidateContact,
    CandidateDocument,
    CandidateEducation,
    CandidateExperience,
    CandidateMatch,
    CandidateSkill,
    CandidateSource,
    DocumentChunk,
    DocumentPage,
    DuplicateReview,
    ExcelImport,
    ExcelImportRow,
    ExtractionEvidence,
    FieldLock,
    HiringRequest,
    Job,
    MatchRequirementResult,
    ProblemReport,
    QuarantineRecord,
    RequestAttachment,
    RequestNote,
    RequestRequirement,
    SharingRecord,
    Shortlist,
    ShortlistCandidate,
)
from app.services.audit import write_audit
from app.storage.local import LocalStorage

# FK-safe delete order: children before parents. users, audit_events and agent_runs are never deleted.
_DELETE_ORDER = [
    MatchRequirementResult,
    CandidateMatch,
    ShortlistCandidate,
    ApprovalDecision,
    SharingRecord,
    Shortlist,
    RequestNote,
    RequestAttachment,
    RequestRequirement,
    HiringRequest,
    DuplicateReview,
    QuarantineRecord,
    ExtractionEvidence,
    DocumentChunk,
    DocumentPage,
    CandidateExperience,
    CandidateEducation,
    CandidateSkill,
    CandidateCertificate,
    CandidateContact,
    CandidateSource,
    FieldLock,
    Application,
    Job,
    CandidateDocument,
    ExcelImportRow,
    ExcelImport,
    ProblemReport,
    Candidate,
]

IN_FLIGHT = ("received", "extracting")
JOB_OPEN = ("queued", "leased", "running")


def demo_status(session: Session) -> dict:
    by_status = dict(
        session.execute(select(CandidateDocument.status, func.count()).group_by(CandidateDocument.status)).all()
    )
    outcomes = dict(
        session.execute(
            select(CandidateDocument.identity_outcome, func.count())
            .where(CandidateDocument.identity_outcome.is_not(None))
            .group_by(CandidateDocument.identity_outcome)
        ).all()
    )
    documents = sum(by_status.values())
    in_flight = sum(by_status.get(name, 0) for name in IN_FLIGHT)
    open_jobs = session.scalar(select(func.count()).select_from(Job).where(Job.status.in_(JOB_OPEN))) or 0
    return {
        "documents": documents,
        "documents_by_status": by_status,
        "identity_outcomes": outcomes,
        "candidates": session.scalar(
            select(func.count()).select_from(Candidate).where(Candidate.merged_into_id.is_(None))
        )
        or 0,
        "pending_reviews": session.scalar(
            select(func.count()).select_from(DuplicateReview).where(DuplicateReview.status == "pending")
        )
        or 0,
        "needs_ocr": by_status.get("needs_ocr", 0),
        "quarantined": by_status.get("quarantined", 0),
        "failed": by_status.get("failed", 0),
        "processing": in_flight,
        "open_jobs": open_jobs,
        "hiring_requests": session.scalar(select(func.count()).select_from(HiringRequest)) or 0,
        "matches": session.scalar(select(func.count()).select_from(CandidateMatch)) or 0,
        "shortlisted": session.scalar(select(func.count()).select_from(ShortlistCandidate)) or 0,
        "shares": session.scalar(select(func.count()).select_from(SharingRecord)) or 0,
        "last_reset_at": _last_reset(session),
        "quarantine_records": session.scalar(select(func.count()).select_from(QuarantineRecord)) or 0,
    }


def _last_reset(session: Session) -> str | None:
    at = session.scalar(select(func.max(AuditEvent.created_at)).where(AuditEvent.action == "demo_reset"))
    return at.isoformat() if at else None


def reset_demo_data(session: Session, actor: Actor) -> None:
    """Wipe all operational/demo data. Keeps users and the append-only audit trail.

    One transaction: the caller commits or rolls back everything together. The uploaded files
    on disk are operational data too — the most PII-dense artifact — so they are collected
    before the rows go and deleted from storage as part of the reset.
    """
    storage_keys = list(session.scalars(select(CandidateDocument.storage_key)))
    storage_keys += list(session.scalars(select(RequestAttachment.storage_key)))
    # agent_runs are kept: append-only audit rows point at them, and the database rejects any change to audit_events.
    # They hold metadata only, so detach them from the rows that are about to be removed.
    session.execute(update(AgentRun).values(job_id=None, document_id=None, candidate_id=None, request_id=None))
    # Delete in the schema's own foreign-key order (children first), so a hand-kept list cannot fall out of step.
    # _DELETE_ORDER still names every table that is wiped; anything else (users, audit_events, agent_runs) is kept.
    wiped = {model.__table__.name for model in _DELETE_ORDER}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in wiped:
            session.execute(delete(table))
    write_audit(
        session,
        actor=actor,
        action="demo_reset",
        entity_type="demo",
        entity_id=None,
        detail={"outcome": "reset"},
    )
    store = LocalStorage(get_settings().storage_dir)
    for key in storage_keys:
        store.delete(key)

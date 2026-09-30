"""PostgreSQL job queue. Idempotency is a unique key, and a lease can be reclaimed."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import SYSTEM
from app.domain.transitions import transition
from app.jobs.errors import PermanentJobError
from app.models import Job, QuarantineRecord
from app.services.audit import write_audit

EXTRACT_DOCUMENT = "extract_document"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue_extract(session: Session, document_id: UUID) -> Job:
    settings = get_settings()
    payload = {"document_id": str(document_id)}
    existing = session.scalar(
        select(Job).where(
            Job.job_type == EXTRACT_DOCUMENT,
            Job.idempotency_key == str(document_id),
            Job.processing_version == settings.processing_version,
        )
    )
    if existing is not None:
        return existing
    job = Job(
        job_type=EXTRACT_DOCUMENT,
        idempotency_key=str(document_id),
        processing_version=settings.processing_version,
        document_id=document_id,
        payload=payload,
        status="queued",
        attempts=0,
        max_attempts=settings.job_max_attempts,
        run_after=utcnow(),
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(Job).where(
                Job.job_type == EXTRACT_DOCUMENT,
                Job.idempotency_key == str(document_id),
                Job.processing_version == settings.processing_version,
            )
        )
        if existing is None:
            raise
        return existing
    write_audit(
        session,
        actor=SYSTEM,
        action="job_enqueued",
        entity_type="job",
        entity_id=job.id,
        detail={
            "document_id": str(document_id),
            "processing_version": settings.processing_version,
        },
    )
    return job


def claim_next(session: Session, worker_id: str, now: datetime | None = None) -> Job | None:
    moment = now or utcnow()
    _quarantine_exhausted(session, moment)
    statement = (
        select(Job)
        .where(Job.run_after <= moment)
        .where(Job.attempts < Job.max_attempts)
        .where(
            or_(
                Job.status == "queued",
                and_(
                    Job.status.in_(("leased", "running")),
                    Job.lease_expires_at.is_not(None),
                    Job.lease_expires_at < moment,
                ),
            )
        )
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = session.scalar(statement)
    if job is None:
        return None
    if job.status != "queued":
        transition(job, "queued", machine="job", actor=SYSTEM, now=moment)
    transition(job, "leased", machine="job", actor=SYSTEM, now=moment)
    job.attempts += 1
    job.leased_by = worker_id
    job.lease_expires_at = moment + timedelta(seconds=get_settings().job_lease_seconds)
    session.flush()
    return job


def finish_success(session: Session, job: Job) -> None:
    if job.status == "leased":
        transition(job, "running", machine="job", actor=SYSTEM)
    transition(job, "succeeded", machine="job", actor=SYSTEM)
    job.lease_expires_at = None
    job.leased_by = None
    write_audit(
        session,
        actor=SYSTEM,
        action="job_succeeded",
        entity_type="job",
        entity_id=job.id,
        detail={"document_id": str(job.document_id) if job.document_id else None},
    )


def finish_failure(session: Session, job: Job, code: str, *, permanent: bool) -> None:
    safe = _safe_code(code)
    if job.status == "leased":
        transition(job, "running", machine="job", actor=SYSTEM)
    if job.status == "running":
        transition(job, "failed", machine="job", actor=SYSTEM)
    job.error_code = safe
    job.last_error = safe
    job.leased_by = None
    job.lease_expires_at = None
    if permanent or job.attempts >= job.max_attempts:
        transition(job, "quarantined", machine="job", actor=SYSTEM)
        _quarantine(session, job, safe)
        action = "job_quarantined"
    else:
        transition(job, "queued", machine="job", actor=SYSTEM)
        action = "job_retry"
    write_audit(
        session,
        actor=SYSTEM,
        action=action,
        entity_type="job",
        entity_id=job.id,
        detail={"error_code": safe, "document_id": str(job.document_id) if job.document_id else None},
    )


def run_once(session: Session, *, worker_id: str, handler, now: datetime | None = None) -> bool:
    """Claim in one commit, then write the result and the terminal status together."""
    job = claim_next(session, worker_id, now)
    if job is None:
        session.commit()
        return False
    job_id = job.id
    session.commit()
    job = session.get(Job, job_id)
    if job is None:
        return False
    try:
        if job.status == "leased":
            transition(job, "running", machine="job", actor=SYSTEM)
            session.commit()
        handler(session, job)
        finish_success(session, job)
        session.commit()
    except PermanentJobError as exc:
        session.rollback()
        failed = session.get(Job, job_id)
        if failed is not None:
            finish_failure(session, failed, exc.code, permanent=True)
            _fail_document(session, failed, exc.code)
            session.commit()
    except Exception:
        session.rollback()
        failed = session.get(Job, job_id)
        if failed is not None:
            finish_failure(session, failed, "transient", permanent=False)
            session.commit()
    return True


def _fail_document(session: Session, job: Job, code: str) -> None:
    from app.models import CandidateDocument

    if job.document_id is None:
        return
    document = session.get(CandidateDocument, job.document_id)
    if document is None or document.status != "received":
        return
    transition(document, "failed", machine="candidate_document", actor=SYSTEM)
    transition(document, "quarantined", machine="candidate_document", actor=SYSTEM)
    document.error_code = _safe_code(code)


def _quarantine(session: Session, job: Job, code: str) -> None:
    existing = session.scalar(select(QuarantineRecord).where(QuarantineRecord.job_id == job.id))
    if existing is not None:
        return
    session.add(
        QuarantineRecord(
            job_id=job.id,
            document_id=job.document_id,
            error_code=code,
            attempts=job.attempts,
        )
    )


def _quarantine_exhausted(session: Session, now: datetime) -> None:
    statement = (
        select(Job)
        .where(Job.attempts >= Job.max_attempts)
        .where(Job.status.in_(("queued", "failed", "leased", "running")))
        .where(
            or_(
                Job.status.in_(("queued", "failed")),
                and_(Job.lease_expires_at.is_not(None), Job.lease_expires_at < now),
            )
        )
        .with_for_update(skip_locked=True)
    )
    for job in session.scalars(statement):
        if job.status == "queued":
            transition(job, "quarantined", machine="job", actor=SYSTEM, now=now)
        elif job.status == "failed":
            transition(job, "quarantined", machine="job", actor=SYSTEM, now=now)
        elif job.status in {"leased", "running"}:
            transition(job, "queued", machine="job", actor=SYSTEM, now=now)
            transition(job, "quarantined", machine="job", actor=SYSTEM, now=now)
        job.error_code = job.error_code or "max_attempts"
        _quarantine(session, job, job.error_code)


def _safe_code(code: str) -> str:
    if not code or "@" in code or len(code) > 120:
        return "redacted_error"
    return code


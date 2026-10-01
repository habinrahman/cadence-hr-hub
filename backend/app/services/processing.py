"""Automatic processing of a received hiring request.

The first job extracts proposed requirements and matches on them at once. That pool is provisional: it can be
viewed but not shortlisted or shared. Approving requirements enqueues a second job that rematches on approved
requirements only, which makes the pool confirmed. No job ever shortlists or shares."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import SYSTEM
from app.domain.transitions import TransitionError, transition
from app.jobs.errors import PermanentJobError
from app.models import CandidateMatch, HiringRequest, Job, RequestRequirement
from app.services.audit import AuditPayloadError, write_audit
from app.services.hiring import HiringError, extract_requirements, pool_status
from app.services.matching import run_match

PROCESS_REQUEST = "process_request"
_ACTIVE = ("queued", "leased", "running")


def _jobs(session: Session, request_id: UUID) -> list[Job]:
    return list(
        session.scalars(
            select(Job)
            .where(Job.job_type == PROCESS_REQUEST, Job.payload["request_id"].astext == str(request_id))
            .order_by(Job.created_at)
        ).all()
    )


def enqueue_process(session: Session, request_id: UUID) -> Job:
    """One active job per request. A finished request is not queued again."""
    jobs = _jobs(session, request_id)
    if jobs and (jobs[-1].status in _ACTIVE or jobs[-1].status == "succeeded"):
        return jobs[-1]
    return _insert(session, request_id, generation=len(jobs))


def retry_process(session: Session, request_id: UUID) -> Job:
    jobs = _jobs(session, request_id)
    if jobs and jobs[-1].status in _ACTIVE:
        return jobs[-1]
    reason = jobs[-1].payload.get("reason", "received") if jobs else "received"
    return _insert(session, request_id, generation=len(jobs), reason=reason)


def enqueue_match(session: Session, request_id: UUID) -> Job:
    """Called when HR approves requirements. Approving twice before the job starts does not queue twice.

    A job that already started may have read the old requirements, so a new approval queues one more rematch."""
    jobs = _jobs(session, request_id)
    if jobs and jobs[-1].status == "queued" and jobs[-1].payload.get("reason") == "approved":
        return jobs[-1]
    return _insert(session, request_id, generation=len(jobs), reason="approved")


def _approved_count(session: Session, request_id: UUID) -> int:
    return session.scalar(
        select(func.count()).select_from(RequestRequirement).where(
            RequestRequirement.request_id == request_id, RequestRequirement.review_status == "approved"
        )
    ) or 0


def _insert(session: Session, request_id: UUID, *, generation: int, reason: str = "received") -> Job:
    settings = get_settings()
    key = f"{request_id}:{generation}"
    job = Job(
        job_type=PROCESS_REQUEST,
        idempotency_key=key,
        processing_version=settings.processing_version,
        payload={"request_id": str(request_id), "stage": "received", "reason": reason},
        status="queued",
        attempts=0,
        max_attempts=settings.job_max_attempts,
        run_after=datetime.now(timezone.utc),
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(Job).where(Job.job_type == PROCESS_REQUEST, Job.idempotency_key == key)
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
        detail={"request_id": str(request_id), "processing_version": settings.processing_version},
    )
    return job


def _stage(session: Session, job: Job, stage: str) -> None:
    """Forensic marker on the job row. Flushed with the handler's work and committed by
    run_once together with the terminal status — never committed here, so the handler stays
    all-or-nothing and a failure leaves no half-processed request behind."""
    job.payload = {**job.payload, "stage": stage}
    session.flush()


def run_process(session: Session, job: Job) -> None:
    """Worker handler. It never shortlists or shares.

    reason "received": extract proposed requirements, then match on them straight away. The pool is provisional.
    reason "approved": HR approved requirements, so rematch on the approved rows only. The pool becomes confirmed.

    Known domain errors (invalid transitions, audit payload rejections, hiring errors) cannot
    heal by retrying, so they become PermanentJobError with the real code instead of burning
    every attempt and landing in quarantine as "transient"."""
    if job.job_type != PROCESS_REQUEST:
        from app.services.pipeline import run_extract

        return run_extract(session, job)
    request_id = UUID(job.payload["request_id"])
    request = session.get(HiringRequest, request_id)
    if request is None:
        raise PermanentJobError("request_missing")
    reason = job.payload.get("reason", "received")
    try:
        if request.status == "submitted":
            transition(request, "open", machine="hiring_request", actor=SYSTEM)
        if reason == "received":
            has_requirements = session.scalar(
                select(func.count()).select_from(RequestRequirement).where(RequestRequirement.request_id == request_id)
            )
            if not has_requirements:
                _stage(session, job, "extracting")
                # Zero accepted proposals is a valid outcome, not a failure: HR adds or edits requirements.
                extract_requirements(session, request_id, SYSTEM)
            has_requirements = session.scalar(
                select(func.count()).select_from(RequestRequirement).where(RequestRequirement.request_id == request_id)
            )
            if not has_requirements:
                _stage(session, job, "awaiting_approval")
                return
            _stage(session, job, "matching")
            run_match(session, request_id, SYSTEM, provisional=True)
            return
        if not _approved_count(session, request_id):
            _stage(session, job, "awaiting_approval")
            return
        _stage(session, job, "matching")
        run_match(session, request_id, SYSTEM)
    except HiringError as exc:
        raise PermanentJobError(exc.code) from exc
    except TransitionError as exc:
        raise PermanentJobError(exc.code) from exc
    except AuditPayloadError as exc:
        raise PermanentJobError("audit_payload") from exc


def processing_view(session: Session, request_id: UUID) -> dict:
    request = session.get(HiringRequest, request_id)
    matched = session.scalar(
        select(func.count()).select_from(CandidateMatch).where(
            CandidateMatch.request_id == request_id,
            CandidateMatch.disposition.in_(("recommended", "needs_review")),
        )
    )
    jobs = _jobs(session, request_id)
    has_pool = session.scalar(
        select(func.count()).select_from(CandidateMatch).where(CandidateMatch.request_id == request_id)
    )
    approved = _approved_count(session, request_id)
    if not jobs:
        stage = "complete" if has_pool else "awaiting_approval" if not approved else "received"
    else:
        latest = jobs[-1]
        matching_job = latest.payload.get("reason") == "approved"
        if latest.status in ("queued", "leased"):
            stage = "matching" if matching_job else "received"
        elif latest.status == "running":
            # Mid-run stage markers are flushed, not committed, so other sessions only ever
            # see the initial payload; a running job reads as its first real stage.
            stage = "matching" if matching_job else "extracting"
        elif latest.status == "succeeded":
            # awaiting_approval now only means there is nothing to match on: no requirement was proposed.
            matched_once = has_pool or (request is not None and request.last_match_completed_at is not None)
            stage = "complete" if matched_once else "awaiting_approval"
        else:
            stage = "failed"
    return {
        "stage": stage,
        "matched_count": int(matched or 0),
        "requested_count": request.requested_count if request else None,
        "pool_status": pool_status(session, request) if request else "none",
    }

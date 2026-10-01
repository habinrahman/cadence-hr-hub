"""Recruiters file problem reports. Engineers change status. Reports do not carry CV text."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.actor import Actor
from app.domain.report_schema import CreateReport, EngineerUpdate
from app.domain.transitions import TransitionError, transition
from app.models import Candidate, CandidateDocument, HiringRequest, ProblemReport, User
from app.services.audit import write_audit

_MODELS = {
    "candidate": Candidate,
    "hiring_request": HiringRequest,
    "document": CandidateDocument,
}


class ReportError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def create_report(session: Session, body: CreateReport, actor: Actor) -> ProblemReport:
    user = _role(session, actor, "recruiter")
    entity_type, entity_id = _reference(session, body.entity_type, body.entity_id)
    row = ProblemReport(
        reporter_user_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=body.title,
        detail=body.description,
        category=body.category,
        context=body.context.model_dump(exclude_none=True),
        status="open",
    )
    session.add(row)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="problem_report_created",
        entity_type="problem_report",
        entity_id=row.id,
        detail=_detail(row, human_action="create"),
    )
    return row


def list_reports(session: Session, actor: Actor) -> list[ProblemReport]:
    user = _known_user(session, actor)
    statement = select(ProblemReport).order_by(ProblemReport.created_at.desc())
    if user.role == "recruiter":
        statement = statement.where(ProblemReport.reporter_user_id == user.id)
    elif user.role != "engineer":
        raise TransitionError("forbidden")
    return list(session.scalars(statement).all())


def get_report(session: Session, report_id: UUID, actor: Actor) -> ProblemReport:
    user = _known_user(session, actor)
    row = session.get(ProblemReport, report_id)
    if row is None:
        raise ReportError("not_found")
    if user.role == "recruiter" and row.reporter_user_id != user.id:
        raise ReportError("not_found")
    if user.role not in {"recruiter", "engineer"}:
        raise TransitionError("forbidden")
    return row


def update_report(session: Session, report_id: UUID, body: EngineerUpdate, actor: Actor) -> ProblemReport:
    _role(session, actor, "engineer")
    row = session.get(ProblemReport, report_id)
    if row is None:
        raise ReportError("not_found")
    if body.status is None and body.note is None:
        raise ReportError("empty_update")
    if body.note is not None:
        row.engineering_note = body.note
        write_audit(
            session,
            actor=actor,
            action="problem_report_updated",
            entity_type="problem_report",
            entity_id=row.id,
            detail=_detail(row, human_action="engineering_note"),
        )
    if body.status is not None and body.status != row.status:
        previous = row.status
        transition(row, body.status, machine="problem_report", actor=actor)
        write_audit(
            session,
            actor=actor,
            action="problem_report_status_changed",
            entity_type="problem_report",
            entity_id=row.id,
            detail=_detail(row, human_action="status", from_status=previous, to_status=row.status),
        )
        if row.status == "resolved":
            write_audit(
                session,
                actor=actor,
                action="problem_report_resolved",
                entity_type="problem_report",
                entity_id=row.id,
                detail=_detail(row, human_action="resolve", from_status=previous, to_status="resolved"),
            )
    return row


def _reference(session: Session, entity_type: str, entity_id: UUID | None) -> tuple[str, UUID | None]:
    if entity_type == "none":
        if entity_id is not None:
            raise ReportError("invalid_reference")
        return "none", None
    if entity_id is None or session.get(_MODELS[entity_type], entity_id) is None:
        raise ReportError("invalid_reference")
    return entity_type, entity_id


def _detail(row: ProblemReport, *, human_action: str, from_status: str | None = None, to_status: str | None = None) -> dict:
    detail: dict = {"report_id": str(row.id), "human_action": human_action}
    if from_status is not None:
        detail["from_status"] = from_status
    if to_status is not None:
        detail["to_status"] = to_status
    if row.entity_type == "candidate" and row.entity_id is not None:
        detail["candidate_id"] = str(row.entity_id)
    elif row.entity_type == "document" and row.entity_id is not None:
        detail["document_id"] = str(row.entity_id)
    elif row.entity_type == "hiring_request" and row.entity_id is not None:
        detail["request_id"] = str(row.entity_id)
    error_code = row.context.get("error_code") if isinstance(row.context, dict) else None
    if isinstance(error_code, str):
        detail["error_code"] = error_code
    return detail


def _known_user(session: Session, actor: Actor) -> User:
    if actor.kind != "user" or actor.user_id is None:
        raise TransitionError("human_required")
    user = session.get(User, actor.user_id)
    if user is None:
        raise TransitionError("forbidden")
    return user


def _role(session: Session, actor: Actor, role: str) -> User:
    user = _known_user(session, actor)
    if user.role != role:
        raise TransitionError("forbidden")
    return user


def diagnostics(session: Session, row: ProblemReport) -> dict:
    """What an engineer needs to reproduce the report, without personal data: the agent runs, background jobs and
    audit codes for the request, file or candidate it names. Agent runs and audit rows hold ids, hashes and codes
    only (see models.AgentRun and services.audit); job payloads hold ids. Read at view time, never copied."""
    from sqlalchemy import or_, select

    from app.models import AgentRun, AuditEvent, Job

    if row.entity_id is None:
        return {"agent_runs": [], "jobs": [], "audit": []}
    key = str(row.entity_id)
    run_filter = {
        "hiring_request": AgentRun.request_id == row.entity_id,
        "document": AgentRun.document_id == row.entity_id,
        "candidate": AgentRun.candidate_id == row.entity_id,
    }.get(row.entity_type)
    runs = session.scalars(select(AgentRun).where(run_filter).order_by(AgentRun.created_at.desc()).limit(20)).all() if run_filter is not None else []
    job_filter = or_(Job.document_id == row.entity_id, Job.payload["request_id"].astext == key)
    jobs = session.scalars(select(Job).where(job_filter).order_by(Job.created_at.desc()).limit(20)).all()
    events = session.scalars(
        select(AuditEvent)
        .where(
            or_(
                AuditEvent.entity_id == row.entity_id,
                AuditEvent.detail["request_id"].astext == key,
                AuditEvent.detail["document_id"].astext == key,
                AuditEvent.detail["candidate_id"].astext == key,
            )
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(30)
    ).all()
    return {
        "agent_runs": [
            {
                "id": str(run.id),
                "agent": run.agent_name,
                "model": run.model,
                "prompt_version": run.prompt_version,
                "input_hash": run.input_hash,
                "status": run.status,
                "validation_result": run.validation_result,
                "error_code": run.error_code,
                "output_ref": run.output_ref,
                "latency_ms": run.latency_ms,
                "created_at": run.created_at.isoformat(),
            }
            for run in runs
        ],
        "jobs": [
            {
                "id": str(job.id),
                "type": job.job_type,
                "status": job.status,
                "attempts": job.attempts,
                "error_code": getattr(job, "error_code", None),
                "created_at": job.created_at.isoformat(),
            }
            for job in jobs
        ],
        "audit": [
            {"action": event.action, "actor_kind": event.actor_kind, "detail": event.detail, "created_at": event.created_at.isoformat()}
            for event in events
        ],
    }

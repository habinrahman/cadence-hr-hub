"""Problem reports. Viewing one does not grant access to candidates or shares."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import Auth, current_auth, get_session, require_engineer, require_recruiter
from app.domain.report_schema import CreateReport, EngineerUpdate
from app.domain.transitions import TransitionError
from app.models import ProblemReport
from app.services.problems import ReportError, create_report, get_report, list_reports, update_report

router = APIRouter()


@router.post("/problem-reports", status_code=201)
def post_report(
    payload: dict = Body(),
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        body = CreateReport.model_validate(payload)
        row = create_report(session, body, auth.actor)
        session.commit()
    except ValidationError:
        session.rollback()
        raise HTTPException(status_code=422, detail="invalid_context") from None
    except (TransitionError, ReportError) as exc:
        session.rollback()
        raise _error(exc) from None
    return _payload(row)


@router.get("/problem-reports")
def get_reports(
    auth: Auth = Depends(current_auth),
    session: Session = Depends(get_session),
) -> dict:
    try:
        rows = list_reports(session, auth.actor)
    except TransitionError as exc:
        raise _error(exc) from None
    return {"reports": [_payload(row) for row in rows]}


@router.get("/problem-reports/{report_id}")
def get_one(
    report_id: UUID,
    auth: Auth = Depends(current_auth),
    session: Session = Depends(get_session),
) -> dict:
    try:
        row = get_report(session, report_id, auth.actor)
    except (TransitionError, ReportError) as exc:
        raise _error(exc) from None
    return _payload(row)


@router.patch("/problem-reports/{report_id}")
def patch_report(
    report_id: UUID,
    payload: dict = Body(),
    auth: Auth = Depends(require_engineer),
    session: Session = Depends(get_session),
) -> dict:
    try:
        body = EngineerUpdate.model_validate(payload)
        row = update_report(session, report_id, body, auth.actor)
        session.commit()
    except ValidationError:
        session.rollback()
        raise HTTPException(status_code=422, detail="invalid_report") from None
    except (TransitionError, ReportError) as exc:
        session.rollback()
        raise _error(exc) from None
    return _payload(row)


def _payload(row: ProblemReport) -> dict:
    return {
        "id": str(row.id),
        "category": row.category,
        "title": row.summary,
        "description": row.detail,
        "status": row.status,
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id) if row.entity_id else None,
        "context": row.context,
        "engineering_note": row.engineering_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, TransitionError):
        code = "engineer_required" if exc.code == "forbidden" else exc.code
        status = 403
        if exc.code == "invalid_transition":
            status = 409
            code = exc.code
        return HTTPException(status_code=status, detail=code)
    if isinstance(exc, ReportError):
        status = 404 if exc.code == "not_found" else 422
        if exc.code == "empty_update":
            status = 409
        return HTTPException(status_code=status, detail=exc.code)
    raise exc

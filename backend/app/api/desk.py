"""Recruiter dashboard and work queue. Both endpoints only read."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_session, require_recruiter
from app.services.audit_view import audit_page
from app.services.desk import DeskError, dashboard, work_queue
from app.services.pii_access import PiiAccessError, allow_candidate_pii

router = APIRouter()


@router.get("/dashboard")
def get_dashboard(
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    try:
        return dashboard(session, auth.actor)
    except DeskError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from None


@router.get("/work-queue")
def get_work_queue(
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    try:
        return work_queue(session, auth.actor)
    except DeskError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from None


@router.get("/audit")
def get_audit(
    limit: int = Query(50, ge=1, le=100),
    before: datetime | None = None,
    category: Literal["decisions", "hiring", "cvs"] | None = None,
    request_id: UUID | None = None,
    candidate_id: UUID | None = None,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    """The whole audit trail, newest first, with who did it and to which request, candidate or file. Read-only."""
    _pii(auth.role)  # names of candidates and files are shown, so it is recruiter-only like the rest of the desk
    return audit_page(
        session, limit=limit, before=before, category=category, request_id=request_id, candidate_id=candidate_id
    )


def _pii(role: str) -> None:
    try:
        allow_candidate_pii(role)
    except PiiAccessError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from None

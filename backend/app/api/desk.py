"""Recruiter dashboard and work queue. Both endpoints only read."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_session, require_recruiter
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


def _pii(role: str) -> None:
    try:
        allow_candidate_pii(role)
    except PiiAccessError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from None

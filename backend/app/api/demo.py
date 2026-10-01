"""Demo-only controls. Registered only when ENVIRONMENT is local (see app.main)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_session, require_recruiter
from app.services.demo import demo_status, reset_demo_data

router = APIRouter(prefix="/demo")


class ResetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: str


@router.get("/status")
def get_status(auth: Auth = Depends(require_recruiter), session: Session = Depends(get_session)) -> dict:
    del auth
    return demo_status(session)


@router.post("/reset")
def post_reset(
    body: ResetBody,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    if body.confirm != "RESET":
        raise HTTPException(status_code=400, detail="confirm_required")
    try:
        reset_demo_data(session, auth.actor)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return {"reset_at": demo_status(session)["last_reset_at"]}

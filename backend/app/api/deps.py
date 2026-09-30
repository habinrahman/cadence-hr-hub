from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import Actor
from app.models import User


@dataclass(frozen=True)
class Auth:
    actor: Actor
    role: str


def get_session(request: Request):
    session: Session = request.app.state.sessions()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def current_auth(
    authorization: Annotated[str | None, Header()] = None,
    session: Session = Depends(get_session),
) -> Auth:
    if not authorization:
        raise HTTPException(status_code=401, detail="unauthorized")
    token = authorization.removeprefix("Bearer ").strip()
    settings = get_settings()
    if settings.environment != "local" and token.startswith("dev-"):
        raise HTTPException(status_code=401, detail="unauthorized")
    if secrets.compare_digest(token, settings.hub_recruiter_token):
        email = settings.recruiter_email
        role = "recruiter"
    elif secrets.compare_digest(token, settings.hub_engineer_token):
        email = settings.engineer_email
        role = "engineer"
    else:
        raise HTTPException(status_code=401, detail="unauthorized")
    user = session.scalar(select(User).where(User.email == email, User.role == role))
    if user is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    return Auth(actor=Actor(kind="user", user_id=user.id), role=role)


def require_engineer(auth: Auth = Depends(current_auth)) -> Auth:
    if auth.role != "engineer":
        raise HTTPException(status_code=403, detail="engineer_required")
    return auth


def require_recruiter(auth: Auth = Depends(current_auth)) -> Auth:
    if auth.role != "recruiter":
        raise HTTPException(status_code=403, detail="recruiter_required")
    return auth

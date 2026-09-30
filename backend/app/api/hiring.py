"""Recruiter routes for requests, matches, and shortlist decisions. Matching does not share anyone."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_session, require_recruiter
from app.config import get_settings
from app.domain.transitions import TransitionError
from app.models import Candidate, CandidateMatch, MatchRequirementResult, RequestRequirement
from app.services.hiring import (
    HiringError,
    add_attachment,
    add_note,
    approve_requirements,
    create_request,
    extract_requirements,
    open_request,
    reject_match,
    request_view,
    shortlist_match,
    update_requirement,
)
from app.services.mail import MailSender, get_mail_sender
from app.services.matching import run_match
from app.services.sharing import (
    SendError,
    approve_share,
    send_share,
    share_preview,
    share_view,
)

router = APIRouter()


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = Field(min_length=1, max_length=300)
    job_title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1)
    received_at: datetime


class NoteBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1)


class ShortlistBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=2000)


class RequirementEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, min_length=1, max_length=300)
    strength: Literal["mandatory", "preferred"] | None = None
    label: Literal["skill", "experience", "education", "certification", "other"] | None = None
    quote: str | None = Field(default=None, min_length=1, max_length=1000)


class ApproveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_ids: list[UUID] | None = None


def _guard(exc: Exception) -> HTTPException:
    if isinstance(exc, TransitionError):
        status = 403 if exc.code in {"human_required", "forbidden"} else 409
        return HTTPException(status_code=status, detail=exc.code)
    if isinstance(exc, HiringError):
        status = 404 if exc.code == "not_found" else 409
        return HTTPException(status_code=status, detail=exc.code)
    raise exc


@router.post("/hiring-requests", status_code=201)
def post_request(
    body: RequestBody,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        row = create_request(
            session,
            company_name=body.company,
            job_title=body.job_title,
            description=body.description,
            received_at=body.received_at,
            actor=auth.actor,
        )
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"id": str(row.id), "status": row.status}


@router.get("/hiring-requests")
def list_requests(
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    del auth
    from app.models import HiringRequest

    rows = session.scalars(select(HiringRequest).order_by(HiringRequest.received_at.desc()).limit(50)).all()
    return {
        "requests": [
            {
                "id": str(row.id),
                "company": row.company_name,
                "job_title": row.job_title,
                "status": row.status,
                "received_at": row.received_at.isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/hiring-requests/{request_id}")
def get_request(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    del auth
    try:
        payload = request_view(session, request_id)
    except HiringError as exc:
        raise _guard(exc) from None
    return payload


@router.post("/hiring-requests/{request_id}/open")
def post_open(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        row = open_request(session, request_id, auth.actor)
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"id": str(row.id), "status": row.status}


@router.post("/hiring-requests/{request_id}/notes", status_code=201)
def post_note(
    request_id: UUID,
    body: NoteBody,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    return _note(session, request_id, body.body, "note", auth)


@router.post("/hiring-requests/{request_id}/updates", status_code=201)
def post_update(
    request_id: UUID,
    body: NoteBody,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    return _note(session, request_id, body.body, "update", auth)


@router.post("/hiring-requests/{request_id}/next-steps", status_code=201)
def post_next_step(
    request_id: UUID,
    body: NoteBody,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    return _note(session, request_id, body.body, "next_step", auth)


@router.post("/hiring-requests/{request_id}/attachments", status_code=201)
def post_attachment(
    request_id: UUID,
    file: UploadFile = File(...),
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    data = file.file.read(get_settings().max_upload_bytes + 1)
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail="file_too_large")
    try:
        row = add_attachment(
            session,
            request_id,
            filename=file.filename or "attachment",
            data=data,
            media_type=file.content_type or "application/octet-stream",
            actor=auth.actor,
        )
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"id": str(row.id), "filename": row.original_filename}


@router.post("/hiring-requests/{request_id}/requirements")
def post_requirements(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        rows = extract_requirements(session, request_id, auth.actor)
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"requirements": [_requirement_payload(row) for row in rows]}


@router.patch("/hiring-requests/{request_id}/requirements/{requirement_id}")
def patch_requirement(
    request_id: UUID,
    requirement_id: UUID,
    body: RequirementEdit,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        row = update_requirement(
            session,
            request_id,
            requirement_id,
            auth.actor,
            text=body.text,
            strength=body.strength,
            label=body.label,
            quote=body.quote,
        )
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return _requirement_payload(row)


@router.post("/hiring-requests/{request_id}/requirements/approve")
def post_approve(
    request_id: UUID,
    body: ApproveBody | None = Body(default=None),
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        rows = approve_requirements(
            session,
            request_id,
            auth.actor,
            requirement_ids=body.requirement_ids if body else None,
        )
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"requirements": [_requirement_payload(row) for row in rows]}


@router.post("/hiring-requests/{request_id}/matches")
def post_matches(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        rows = run_match(session, request_id, auth.actor)
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"matches": [_match_payload(session, row) for row in rows]}


@router.get("/hiring-requests/{request_id}/matches")
def get_matches(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    del auth
    rows = session.scalars(select(CandidateMatch).where(CandidateMatch.request_id == request_id)).all()
    return {"matches": [_match_payload(session, row) for row in rows]}


@router.post("/hiring-requests/{request_id}/matches/{match_id}/shortlist", status_code=201)
def post_shortlist(
    request_id: UUID,
    match_id: UUID,
    body: ShortlistBody | None = Body(default=None),
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        row = shortlist_match(session, request_id, match_id, auth.actor, note=body.note if body else None)
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {
        "id": str(row.id),
        "shortlist_id": str(row.shortlist_id),
        "request_id": str(request_id),
        "candidate_id": str(row.candidate_id),
        "added_by_user_id": str(row.added_by_user_id) if row.added_by_user_id else None,
        "review_state": row.review_state,
        "note": row.note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("/hiring-requests/{request_id}/matches/{match_id}/reject")
def post_reject(
    request_id: UUID,
    match_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        row = reject_match(session, request_id, match_id, auth.actor)
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"id": str(row.id), "disposition": row.disposition}


@router.get("/hiring-requests/{request_id}/candidates/{candidate_id}/share")
def get_share(
    request_id: UUID,
    candidate_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        return share_preview(session, request_id, candidate_id, auth.actor)
    except (TransitionError, SendError) as exc:
        raise _share_error(exc) from None


@router.post("/hiring-requests/{request_id}/candidates/{candidate_id}/share/approve")
def post_share_approval(
    request_id: UUID,
    candidate_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        row = approve_share(session, request_id, candidate_id, auth.actor)
        session.commit()
    except (TransitionError, SendError) as exc:
        session.rollback()
        raise _share_error(exc) from None
    return {"id": str(row.id), "decision": row.decision}


@router.post("/hiring-requests/{request_id}/candidates/{candidate_id}/share", status_code=201)
def post_share(
    request_id: UUID,
    candidate_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
    sender: MailSender = Depends(get_mail_sender),
) -> dict:
    try:
        record = send_share(session, request_id, candidate_id, auth.actor, sender)
        session.commit()
    except TransitionError as exc:
        session.rollback()
        raise _share_error(exc) from None
    except SendError as exc:
        if exc.code == "mail_delivery_failed":
            session.commit()
        else:
            session.rollback()
        raise _share_error(exc) from None
    return share_view(session, record)


def _share_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TransitionError):
        return HTTPException(status_code=403, detail=exc.code)
    if isinstance(exc, SendError):
        if exc.code == "mail_delivery_failed":
            return HTTPException(status_code=502, detail=exc.code)
        status = 404 if exc.code == "not_found" else 409
        return HTTPException(status_code=status, detail=exc.code)
    raise exc


def _note(session: Session, request_id: UUID, body: str, kind: str, auth: Auth) -> dict:
    try:
        row = add_note(session, request_id, body, kind, auth.actor)
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"id": str(row.id), "kind": row.kind}


def _requirement_payload(row: RequestRequirement) -> dict:
    return {
        "id": str(row.id),
        "label": row.label,
        "text": row.requirement_text,
        "strength": row.strength,
        "source_quote": row.source_quote,
        "review_status": row.review_status,
    }


def _match_payload(session: Session, match: CandidateMatch) -> dict:
    rows = session.execute(
        select(MatchRequirementResult, RequestRequirement)
        .join(RequestRequirement, RequestRequirement.id == MatchRequirementResult.requirement_id)
        .where(MatchRequirementResult.match_id == match.id)
        .order_by(RequestRequirement.position)
    ).all()
    candidate = session.get(Candidate, match.candidate_id)
    strengths = [requirement.requirement_text for result, requirement in rows if result.result == "meets"]
    gaps = [
        f"{requirement.requirement_text} ({requirement.strength}, {result.result})"
        for result, requirement in rows
        if result.result != "meets"
    ]
    return {
        "id": str(match.id),
        "candidate_id": str(match.candidate_id),
        "candidate_name": candidate.display_name if candidate else None,
        "request_id": str(match.request_id),
        "disposition": match.disposition,
        "requirement_met_ratio": float(match.rank_score) if match.rank_score is not None else None,
        "explanation": match.explanation,
        "strengths": strengths,
        "gaps": gaps,
        "processing_version": match.processing_version,
        "requirements": [
            {
                "requirement_id": str(requirement.id),
                "label": requirement.label,
                "text": requirement.requirement_text,
                "strength": requirement.strength,
                "result": result.result,
                "evidence_id": str(result.evidence_id) if result.evidence_id else None,
                "evidence": result.evidence_quote,
                "retrieval": result.retrieval,
            }
            for result, requirement in rows
        ],
    }

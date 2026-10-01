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
from app.models import Candidate, CandidateMatch, HiringRequest, MatchRequirementResult, RequestRequirement
from app.services.hiring import (
    HiringError,
    add_attachment,
    add_note,
    approve_requirements,
    create_request,
    open_pool,
    reject_match,
    submit_request,
    request_view,
    shortlist_match,
    update_requirement,
)
from app.services.mail import MailSender, get_mail_sender
from app.domain.matching import RequirementVerdict, match_summary
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
    requested_count: int | None = Field(default=None, ge=1, le=500)
    contact_email: str | None = Field(default=None, max_length=320)


class ContactBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_email: str = Field(min_length=3, max_length=320)


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
        status = 404 if exc.code == "not_found" else 422 if exc.code == "invalid_recipient" else 409
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
            requested_count=body.requested_count,
            contact_email=body.contact_email,
        )
        submit_request(session, row.id, auth.actor)
        from app.services.processing import enqueue_process

        enqueue_process(session, row.id)
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

    from app.services.processing import processing_view

    rows = session.scalars(select(HiringRequest).order_by(HiringRequest.received_at.desc()).limit(50)).all()
    requests = []
    for row in rows:
        progress = processing_view(session, row.id)
        requests.append(
            {
                "id": str(row.id),
                "company": row.company_name,
                "job_title": row.job_title,
                "status": row.status,
                "received_at": row.received_at.isoformat(),
                "requested_count": row.requested_count,
                "processing": progress["stage"],
                "matched_count": progress["matched_count"],
            }
        )
    return {"requests": requests}


@router.get("/hiring-requests/{request_id}")
def get_request(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    del auth
    # One snapshot for the whole page: the worker can commit between this endpoint's queries, and a mixed read would
    # show "matching complete" beside an empty requirement list for a moment.
    session.rollback()
    session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    try:
        payload = request_view(session, request_id)
    except HiringError as exc:
        raise _guard(exc) from None
    return payload


@router.put("/hiring-requests/{request_id}/contact")
def put_contact(
    request_id: UUID,
    body: ContactBody,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    from app.services.hiring import set_contact

    try:
        row = set_contact(session, request_id, body.contact_email, auth.actor)
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"id": str(row.id), "contact_email": row.contact_email}


@router.post("/hiring-requests/{request_id}/pool/open")
def post_open_pool(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        row = open_pool(session, request_id, auth.actor)
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"pool_opened_at": row.pool_opened_at.isoformat() if row.pool_opened_at else None}


@router.post("/hiring-requests/{request_id}/process/retry", status_code=202)
def post_retry(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    del auth
    try:
        from app.services.hiring import _request
        from app.services.processing import retry_process

        _request(session, request_id)
        job = retry_process(session, request_id)
        session.commit()
    except HiringError as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"job_id": str(job.id), "status": job.status}


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


@router.post("/hiring-requests/{request_id}/requirements/{requirement_id}/reject")
def post_reject_requirement(
    request_id: UUID,
    requirement_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    from app.services.hiring import reject_requirement
    from app.services.processing import _approved_count, enqueue_match

    try:
        row = reject_requirement(session, request_id, requirement_id, auth.actor)
        request = session.get(HiringRequest, request_id)
        if request.last_match_completed_at is not None and _approved_count(session, request_id):
            # The pool was built with this requirement; rematch on what HR still approves.
            enqueue_match(session, request_id)
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return _requirement_payload(row)


class RequirementAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: Literal["skill", "experience", "education", "certification", "other"]
    text: str = Field(min_length=1, max_length=300)
    strength: Literal["mandatory", "preferred"]
    quote: str = Field(min_length=1, max_length=1000)


@router.post("/hiring-requests/{request_id}/requirements/manual", status_code=201)
def post_manual_requirement(
    request_id: UUID,
    body: RequirementAdd,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    from app.services.hiring import add_requirement

    try:
        row = add_requirement(
            session, request_id, auth.actor, label=body.label, text=body.text, strength=body.strength, quote=body.quote
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
        if rows:
            from app.services.processing import enqueue_match

            # Approval queues the rematch on approved rows only; when it finishes the pool is confirmed.
            enqueue_match(session, request_id)
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
    flags = _decision_flags(session, request_id)
    return {"matches": _ranked([_match_payload(session, row, flags) for row in rows])}


@router.get("/hiring-requests/{request_id}/matches")
def get_matches(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    del auth
    rows = session.scalars(select(CandidateMatch).where(CandidateMatch.request_id == request_id)).all()
    flags = _decision_flags(session, request_id)
    return {"matches": _ranked([_match_payload(session, row, flags) for row in rows])}


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


@router.post("/hiring-requests/{request_id}/matches/{match_id}/restore")
def post_restore(
    request_id: UUID,
    match_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    from app.services.hiring import restore_match

    try:
        row = restore_match(session, request_id, match_id, auth.actor)
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


def _decision_flags(session: Session, request_id: UUID) -> dict[str, dict[UUID, bool]]:
    """What a recruiter has already decided for each candidate of THIS request, in three queries for the whole pool.

    shortlisted: on the draft shortlist. share_approved: the share was approved. shared: the email was sent.
    The page used to infer these from the dashboard's lists, which stopped listing a candidate once sent."""
    from app.models import ApprovalDecision, SharingRecord, Shortlist, ShortlistCandidate

    entries = session.execute(
        select(ShortlistCandidate.id, ShortlistCandidate.candidate_id)
        .join(Shortlist, Shortlist.id == ShortlistCandidate.shortlist_id)
        .where(Shortlist.request_id == request_id, ShortlistCandidate.review_state == "shortlisted")
    ).all()
    approved_entries = set(
        session.scalars(
            select(ApprovalDecision.subject_id).where(
                ApprovalDecision.subject_type == "share",
                ApprovalDecision.decision == "approved",
                ApprovalDecision.subject_id.in_([entry_id for entry_id, _ in entries] or [None]),
            )
        )
    )
    sent = set(
        session.scalars(
            select(SharingRecord.candidate_id).where(SharingRecord.request_id == request_id, SharingRecord.status == "sent")
        )
    )
    return {
        "shortlisted": {candidate_id: True for _entry, candidate_id in entries},
        "share_approved": {candidate_id: True for entry_id, candidate_id in entries if entry_id in approved_entries},
        "shared": {candidate_id: True for candidate_id in sent},
    }


def _match_payload(session: Session, match: CandidateMatch, flags: dict | None = None) -> dict:
    rows = session.execute(
        select(MatchRequirementResult, RequestRequirement)
        .join(RequestRequirement, RequestRequirement.id == MatchRequirementResult.requirement_id)
        .where(MatchRequirementResult.match_id == match.id)
        .order_by(RequestRequirement.position)
    ).all()
    candidate = session.get(Candidate, match.candidate_id)
    calculation = _years_calculation(session, candidate)
    summary = match_summary(
        [
            RequirementVerdict(str(requirement.id), _requirement_name(requirement), requirement.strength, result.result)
            for result, requirement in rows
        ]
    )
    # Points per requirement are shown only when they add up to a real ranking score.
    points = summary.breakdown.rows if summary.breakdown else None
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
        "shortlisted": bool(flags and flags["shortlisted"].get(match.candidate_id)),
        "share_approved": bool(flags and flags["share_approved"].get(match.candidate_id)),
        "shared": bool(flags and flags["shared"].get(match.candidate_id)),
        "requirement_met_ratio": float(match.rank_score) if match.rank_score is not None else None,
        # The mandatory gate first; the 0-100 ranking score only for a candidate who passes it, otherwise null.
        "eligibility": summary.eligibility,
        "match_score": summary.match_score,
        "match_score_exact": float(summary.match_score_exact) if summary.match_score_exact is not None else None,
        "score_max": 100,
        "mandatory_met": summary.mandatory_met,
        "mandatory_total": summary.mandatory_total,
        "preferred_met": summary.preferred_met,
        "preferred_total": summary.preferred_total,
        "blocking_requirements": [
            {"requirement_id": row.requirement_id, "name": row.name, "result": row.result} for row in summary.blocking
        ],
        "score_reason": summary.reason,
        "explanation": match.explanation,
        "strengths": strengths,
        "gaps": gaps,
        "processing_version": match.processing_version,
        "years_of_experience": float(candidate.years_of_experience) if candidate and candidate.years_of_experience is not None else None,
        "location": getattr(candidate, "location", None) if candidate else None,
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
                # Years are added up across every dated role; the quote shows one of them. Say so plainly.
                "calculation": calculation if requirement.label == "experience" and result.result in ("meets", "unmet") else None,
                "points_possible": float(points[index].possible) if points else None,
                "points_earned": float(points[index].earned) if points else None,
            }
            for index, (result, requirement) in enumerate(rows)
        ],
    }


def _years_calculation(session: Session, candidate: Candidate | None) -> str | None:
    if candidate is None or candidate.years_of_experience is None:
        return None
    from sqlalchemy import func

    from app.models import CandidateExperience

    roles = session.scalar(
        select(func.count()).select_from(CandidateExperience).where(
            CandidateExperience.candidate_id == candidate.id, CandidateExperience.start_date.is_not(None)
        )
    ) or 0
    years = float(candidate.years_of_experience)
    shown = int(years) if years.is_integer() else years
    if roles <= 1:
        return f"{shown} years, from the dated role on the CV"
    return f"{shown} years in total across {roles} dated roles on the CV (overlapping time counted once)"


def _requirement_name(requirement: RequestRequirement) -> str:
    text = requirement.requirement_text
    return f"{text} years experience" if requirement.label == "experience" else text


_ELIGIBILITY_ORDER = {"eligible": 0, "needs_review": 1, "excluded": 2}


def _ranked(payloads: list[dict]) -> list[dict]:
    """Eligible by match score, then needs review by mandatory requirements met, then excluded.

    A candidate held at the mandatory gate never ranks above one who passed it. Ties keep a fixed order.
    """

    def key(item: dict):
        return (
            _ELIGIBILITY_ORDER[item["eligibility"]],
            -(item["match_score_exact"] or 0),
            -item["mandatory_met"],
            -(item["requirement_met_ratio"] or 0),
            item["candidate_name"] is None,  # a named candidate before an unnamed one
            (item["candidate_name"] or "").casefold(),
            item["id"],
        )

    return sorted(payloads, key=key)

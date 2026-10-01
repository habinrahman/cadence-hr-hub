from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Auth, current_auth, get_session, require_recruiter
from app.config import get_settings
from app.extraction.media import UnsupportedFile
from app.models import (
    AuditEvent,
    Candidate,
    CandidateDocument,
    DocumentChunk,
    DuplicateReview,
    ExtractionEvidence,
)
from app.domain.confidence import STATUS_FOR
from app.domain.transitions import TransitionError
from app.services.audit import write_audit
from app.services.pii_access import PiiAccessError, allow_candidate_pii
from app.services.profile_view import candidate_profile
from app.services.ingest import ingest_bytes
from app.services.merge import MergeError, merge_profiles, preview_merge
from app.services.reviews import decide_duplicate_review
from app.services.sourcing import record_source_decision
from app.services.search import hybrid_search, list_candidates

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/search")
def search_candidates(
    q: str | None = None,
    name: str | None = None,
    skill: str | None = None,
    education: str | None = None,
    experience: str | None = None,
    certificate: str | None = None,
    min_years: float | None = None,
    job_title: str | None = None,
    industry: str | None = None,
    nationality: str | None = None,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    from app.extraction.provider import get_embedder

    hits = hybrid_search(
        session,
        query=q,
        name=name,
        skill=skill,
        education=education,
        experience=experience,
        certificate=certificate,
        min_years=min_years,
        job_title=job_title,
        industry=industry,
        nationality=nationality,
        embedder=get_embedder(),
    )
    ids = [hit.candidate_id for hit in hits if hit.candidate_id]
    names: dict[UUID, str | None] = {}
    if ids:
        found = session.execute(select(Candidate.id, Candidate.display_name).where(Candidate.id.in_(ids)))
        names = {candidate_id: display_name for candidate_id, display_name in found}
    return {
        "results": [
            {
                "candidate_id": str(hit.candidate_id) if hit.candidate_id else None,
                "candidate_name": names.get(hit.candidate_id) if hit.candidate_id else None,
                "document_id": str(hit.document_id) if hit.document_id else None,
                "chunk_id": str(hit.chunk_id) if hit.chunk_id else None,
                "confirmed_profile": hit.confirmed_profile,
                "retrieval_score": hit.retrieval_score,
                "reasons": hit.reasons,
                "evidence": hit.evidence,
            }
            for hit in hits
        ]
    }


@router.get("/candidates")
def list_candidate_profiles(
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    total, items = list_candidates(session, limit=limit, offset=offset)
    return {"total": total, "limit": limit, "offset": offset, "candidates": items}


@router.post("/documents", status_code=201)
def upload_document(
    file: UploadFile,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    data = file.file.read(get_settings().max_upload_bytes + 1)
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail="file_too_large")
    try:
        result = ingest_bytes(session, filename=file.filename, data=data, actor=auth.actor)
        session.commit()
    except UnsupportedFile:
        session.rollback()
        raise HTTPException(status_code=415, detail="unsupported_file") from None
    document = result.document
    return {
        "id": str(document.id),
        "status": document.status,
        "created": result.created,
        "media_type": document.media_type,
    }


@router.get("/documents")
def list_documents(
    auth: Auth = Depends(current_auth),
    session: Session = Depends(get_session),
) -> dict:
    rows = session.scalars(
        select(CandidateDocument).order_by(CandidateDocument.received_at.desc()).limit(50)
    ).all()
    return {"documents": [_document_summary(row, role=auth.role) for row in rows]}


@router.get("/documents/{document_id}")
def get_document(
    document_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    document = session.get(CandidateDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="not_found")
    payload = _document_summary(document, role=auth.role)
    payload["extracted_contacts"] = _extracted_contacts(session, document.id)
    return payload


@router.get("/documents/{document_id}/activity")
def document_activity(
    document_id: UUID,
    auth: Auth = Depends(current_auth),
    session: Session = Depends(get_session),
) -> dict:
    document = session.get(CandidateDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="not_found")
    review_ids = list(
        session.scalars(select(DuplicateReview.id).where(DuplicateReview.document_id == document_id))
    )
    events = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_id.in_([document_id, *review_ids]))
        .order_by(AuditEvent.created_at)
    ).all()
    return {
        "events": [
            {
                "action": event.action,
                "actor_kind": event.actor_kind,
                "created_at": event.created_at.isoformat(),
                "detail": event.detail,
            }
            for event in events
        ]
    }


@router.get("/documents/{document_id}/text")
def get_document_text(
    document_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    document = session.get(CandidateDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="not_found")
    chunks = session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    ).all()
    write_audit(
        session,
        actor=auth.actor,
        action="pii_text_access",
        entity_type="candidate_document",
        entity_id=document.id,
        detail={"count": len(chunks)},
    )
    session.commit()
    return {"id": str(document.id), "text": "\n\n".join(chunk.content for chunk in chunks)}


@router.get("/candidates/{candidate_id}")
def get_candidate(
    candidate_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="not_found")
    write_audit(
        session,
        actor=auth.actor,
        action="candidate_viewed",
        entity_type="candidate",
        entity_id=candidate.id,
        detail={},
    )
    payload = candidate_profile(session, candidate)
    session.commit()
    return payload


class MergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left_id: UUID
    right_id: UUID
    confirm: bool = False


@router.get("/profile-merges/preview")
def get_merge_preview(
    left_id: UUID,
    right_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    try:
        return preview_merge(session, left_id, right_id, auth.actor)
    except MergeError as exc:
        raise HTTPException(status_code=_merge_status(exc.code), detail=exc.code) from None


@router.post("/profile-merges")
def post_merge(
    body: MergeRequest,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    try:
        payload = merge_profiles(
            session,
            body.left_id,
            body.right_id,
            auth.actor,
            confirm=body.confirm,
        )
        session.commit()
    except MergeError as exc:
        session.rollback()
        raise HTTPException(status_code=_merge_status(exc.code), detail=exc.code) from None
    return payload


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accept_update", "record_duplicate", "create_separate_candidate"]
    candidate_id: UUID | None = None


@router.get("/documents/{document_id}/review")
def get_document_review(
    document_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    review = session.scalar(
        select(DuplicateReview)
        .where(DuplicateReview.document_id == document_id)
        .order_by(DuplicateReview.created_at.desc())
    )
    if review is None:
        raise HTTPException(status_code=404, detail="not_found")
    return _review_payload(session, review)


@router.get("/reviews/{review_id}")
def get_review(
    review_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    review = session.get(DuplicateReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="not_found")
    return _review_payload(session, review)


@router.post("/reviews/{review_id}/decision")
def decide_review(
    review_id: UUID,
    body: ReviewDecision,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    # Locked until commit: a double click waits, then sees the first decision instead of applying a second one
    # (two "Create New Candidate" clicks must not create two profiles).
    review = session.scalar(
        select(DuplicateReview)
        .where(DuplicateReview.id == review_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if review is None:
        raise HTTPException(status_code=404, detail="not_found")
    if review.status == STATUS_FOR.get(body.action):
        return _review_payload(session, review)  # the same decision again (a retry): already recorded
    try:
        decide_duplicate_review(
            session,
            review,
            body.action,
            auth.actor,
            candidate_id=body.candidate_id,
        )
        if review.document_id is not None:
            record_source_decision(session, review.document_id, auth.actor, body.action)
        session.commit()
    except TransitionError as exc:
        session.rollback()
        status = 403 if exc.code in {"human_required", "forbidden"} else 409
        raise HTTPException(status_code=status, detail=exc.code) from None
    return _review_payload(session, review)


def _merge_status(code: str) -> int:
    if code in {"human_required", "recruiter_required", "forbidden"}:
        return 403
    if code == "confirmation_required":
        return 422
    if code == "not_found":
        return 404
    return 409


def _pii(role: str) -> None:
    try:
        allow_candidate_pii(role)
    except PiiAccessError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from None


def _document_summary(document: CandidateDocument, *, role: str) -> dict:
    payload = {
        "id": str(document.id),
        "status": document.status,
        "media_type": document.media_type,
        "byte_size": document.byte_size,
        "identity_outcome": document.identity_outcome,
        "error_code": document.error_code,
        "candidate_id": str(document.candidate_id) if document.candidate_id else None,
        "is_current": document.is_current,
        "language_code": document.language_code,
        "received_at": document.received_at.isoformat(),
    }
    if role == "recruiter":
        payload["original_filename"] = document.original_filename
    return payload


def _extracted_contacts(session: Session, document_id: UUID) -> list[dict]:
    rows = session.scalars(
        select(ExtractionEvidence).where(
            ExtractionEvidence.document_id == document_id,
            ExtractionEvidence.entity_type == "contact",
        )
    )
    return [{"kind": row.field_name, "value": row.extracted_value} for row in rows]


def _review_payload(session: Session, review: DuplicateReview) -> dict:
    candidate_ids = review.signals.get("candidate_ids", [])
    names: dict[str, str | None] = {}
    if candidate_ids:
        rows = session.execute(
            select(Candidate.id, Candidate.display_name).where(
                Candidate.id.in_([UUID(item) for item in candidate_ids])
            )
        )
        names = {str(candidate_id): display_name for candidate_id, display_name in rows}
    return {
        "id": str(review.id),
        "document_id": str(review.document_id) if review.document_id else None,
        "excel_import_row_id": str(review.excel_import_row_id) if review.excel_import_row_id else None,
        "source": review.signals.get("source"),
        "status": review.status,
        "confidence": float(review.confidence) if review.confidence is not None else None,
        "likely_relationship": review.likely_relationship,
        "recommended_action": review.recommended_action,
        "offered_actions": review.offered_actions or [],
        "candidate_id": str(review.candidate_id) if review.candidate_id else None,
        "candidate_ids": candidate_ids,
        "candidates": [
            {"id": item, "display_name": names.get(item)} for item in candidate_ids
        ],
        "ambiguous": bool(review.signals.get("ambiguous")),
        "evidence": review.signals.get("evidence", []),
    }

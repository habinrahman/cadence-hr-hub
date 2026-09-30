"""Recruiter entry for candidates found outside the CV folder."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_session, require_recruiter
from app.config import get_settings
from app.domain.transitions import TransitionError
from app.models import AuditEvent, CandidateSource, DuplicateReview
from app.services.sourcing import SourceError, submit_source

router = APIRouter()


@router.post("/sourced-candidates", status_code=201)
def post_sourced_candidate(
    name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    source_type: str = Form(""),
    source_reference: str = Form(""),
    notes: str = Form(""),
    file: UploadFile | None = File(default=None),
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    if file is None:
        raise HTTPException(status_code=422, detail="missing_cv")
    data = file.file.read(get_settings().max_upload_bytes + 1)
    if len(data) > get_settings().max_upload_bytes:
        raise HTTPException(status_code=413, detail="file_too_large")
    try:
        row = submit_source(
            session,
            actor=auth.actor,
            display_name=name,
            email=email,
            phone=phone,
            source_type=source_type,
            source_reference=source_reference,
            notes=notes,
            filename=file.filename,
            data=data,
        )
        session.commit()
    except TransitionError as exc:
        session.rollback()
        raise HTTPException(status_code=403, detail=exc.code) from None
    except SourceError as exc:
        session.rollback()
        status = 415 if exc.code == "unsupported_file" else 422
        raise HTTPException(status_code=status, detail=exc.code) from None
    return _payload(session, row)


@router.get("/sourced-candidates/{source_id}")
def get_sourced_candidate(
    source_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    del auth
    row = session.get(CandidateSource, source_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not_found")
    return _payload(session, row)


def _payload(session: Session, row: CandidateSource) -> dict:
    from app.models import CandidateDocument

    document = session.get(CandidateDocument, row.document_id)
    review = session.scalar(
        select(DuplicateReview)
        .where(DuplicateReview.document_id == row.document_id)
        .order_by(DuplicateReview.created_at.desc())
    )
    events = session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.entity_id == row.document_id,
            AuditEvent.action.in_(
                (
                    "sourced_cv_attached",
                    "sourced_duplicate_detected",
                    "sourced_candidate_created",
                    "sourced_review_decided",
                )
            ),
        )
        .order_by(AuditEvent.created_at)
    ).all()
    return {
        "id": str(row.id),
        "display_name": row.display_name,
        "email": row.email,
        "phone": row.phone,
        "source_type": row.source_type,
        "source_reference": row.source_reference,
        "notes": row.notes,
        "document_id": str(row.document_id),
        "document_status": document.status if document else None,
        "identity_outcome": document.identity_outcome if document else None,
        "candidate_id": str(row.candidate_id) if row.candidate_id else None,
        "review_id": str(review.id) if review else None,
        "events": [
            {"action": event.action, "actor_kind": event.actor_kind, "created_at": event.created_at.isoformat()}
            for event in events
        ],
    }

"""Read-only views for the CV comparison workspace. Neither route decides or changes a review."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_session, require_recruiter
from app.models import CandidateDocument, DocumentPage, DuplicateReview
from app.services.audit import write_audit
from app.services.pii_access import PiiAccessError, allow_candidate_pii
from app.services.review_compare import CompareError, build_comparison

router = APIRouter()


def _pii(role: str) -> None:
    try:
        allow_candidate_pii(role)
    except PiiAccessError as exc:
        raise HTTPException(status_code=403, detail=exc.code) from None


@router.get("/reviews/{review_id}/comparison")
def get_review_comparison(
    review_id: UUID,
    candidate_id: UUID | None = None,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    _pii(auth.role)
    review = session.get(DuplicateReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        payload = build_comparison(session, review, candidate_id=candidate_id)
    except CompareError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.code) from None
    documents = sum(1 for side in ("existing", "incoming") if payload.get(side) and payload[side].get("document"))
    write_audit(
        session,
        actor=auth.actor,
        action="review_comparison_viewed",
        entity_type="duplicate_review",
        entity_id=review.id,
        detail={"review_id": str(review.id), "count": documents},
    )
    session.commit()
    return payload


@router.get("/documents/{document_id}/pages")
def get_document_pages(
    document_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    """Page-by-page text for the comparison viewer. Reading it is recorded like any other CV text access."""
    _pii(auth.role)
    document = session.get(CandidateDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="not_found")
    rows = session.execute(
        select(DocumentPage.page_number, DocumentPage.original_text)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    ).all()
    write_audit(
        session,
        actor=auth.actor,
        action="pii_text_access",
        entity_type="candidate_document",
        entity_id=document.id,
        detail={"count": len(rows)},
    )
    session.commit()
    return {
        "id": str(document.id),
        "page_count": len(rows),
        "pages": [{"number": number, "text": text} for number, text in rows],
    }

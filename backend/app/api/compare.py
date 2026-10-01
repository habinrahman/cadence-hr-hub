"""Read-only views for the CV comparison workspace. Neither route decides or changes a review."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_session, require_recruiter
from app.config import get_settings
from app.models import CandidateDocument, DocumentPage, DuplicateReview
from app.services.audit import write_audit
from app.services.pii_access import PiiAccessError, allow_candidate_pii
from app.services.page_preview import PreviewError, render_page
from app.services.review_compare import CompareError, build_comparison, only_here_lines, review_documents
from app.storage.local import LocalStorage

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


@router.get("/reviews/{review_id}/documents/{document_id}/pages/{number}/preview")
def get_page_preview(
    review_id: UUID,
    document_id: UUID,
    number: int,
    candidate_id: UUID | None = None,
    focus: str | None = Query(default=None, max_length=300),
    width: int = 900,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> Response:
    """One page of one of the review's two CVs as a PNG, with lines that differ marked on it.

    Not a file download: only a rendered image leaves the server, and only for a document that belongs to this review.
    """
    _pii(auth.role)
    review = session.get(DuplicateReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        pair = review_documents(session, review, candidate_id)
    except CompareError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.code) from None
    existing, incoming = pair
    document = next((doc for doc in (existing, incoming) if doc is not None and doc.id == document_id), None)
    if document is None:
        raise HTTPException(status_code=404, detail="not_found")
    if document.media_type != "application/pdf":
        raise HTTPException(status_code=415, detail="preview_unavailable")
    try:
        data = LocalStorage(get_settings().storage_dir).read(document.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file_missing") from None
    which = "existing" if existing is not None and existing.id == document.id else "incoming"
    try:
        result = render_page(
            data,
            number,
            width=width,
            mark=only_here_lines(session, pair, which, number),
            focus=focus,
        )
    except PreviewError as exc:
        status = 404 if exc.code == "page_out_of_range" else 422
        raise HTTPException(status_code=status, detail=exc.code) from None
    write_audit(
        session,
        actor=auth.actor,
        action="cv_preview_viewed",
        entity_type="candidate_document",
        entity_id=document.id,
        detail={"review_id": str(review.id), "document_id": str(document.id)},
    )
    session.commit()
    return Response(
        content=result.png,
        media_type="image/png",
        headers={
            "X-Preview-Pages": str(result.page_count),
            "X-Preview-Highlights": str(result.highlights),
            "Cache-Control": "no-store",
            "Access-Control-Expose-Headers": "X-Preview-Pages, X-Preview-Highlights",
        },
    )

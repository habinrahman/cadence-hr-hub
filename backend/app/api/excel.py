"""Recruiter spreadsheet import and quarterly hiring export."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_session, require_recruiter
from app.config import get_settings
from app.models import DuplicateReview, ExcelImport, ExcelImportRow
from app.services.excel_ops import ExcelError, export_hiring_activity, import_candidates

router = APIRouter()


@router.post("/excel/candidates", status_code=201)
def post_excel_candidates(
    file: UploadFile | None = File(default=None),
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    if file is None:
        raise HTTPException(status_code=422, detail="missing_file")
    data = file.file.read(get_settings().max_upload_bytes + 1)
    try:
        batch = import_candidates(session, actor=auth.actor, filename=file.filename, data=data)
        session.commit()
    except ExcelError as exc:
        session.rollback()
        raise HTTPException(status_code=_status(exc.code), detail=exc.code) from None
    return _payload(session, batch)


@router.get("/excel/candidates/{import_id}")
def get_excel_import(
    import_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    del auth
    batch = session.get(ExcelImport, import_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="not_found")
    return _payload(session, batch)


@router.get("/hiring-activity/export")
def get_hiring_export(
    start: date = Query(),
    end: date = Query(),
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> Response:
    try:
        payload = export_hiring_activity(session, actor=auth.actor, start=start, end=end)
        session.commit()
    except ExcelError as exc:
        session.rollback()
        raise HTTPException(status_code=_status(exc.code), detail=exc.code) from None
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="hiring-activity.xlsx"'},
    )


def _payload(session: Session, batch: ExcelImport) -> dict:
    rows = session.scalars(
        select(ExcelImportRow).where(ExcelImportRow.import_id == batch.id).order_by(ExcelImportRow.row_number)
    ).all()
    review_ids = {}
    if rows:
        found = session.execute(
            select(DuplicateReview.excel_import_row_id, DuplicateReview.id).where(
                DuplicateReview.excel_import_row_id.in_([row.id for row in rows])
            )
        )
        review_ids = {row_id: review_id for row_id, review_id in found if row_id is not None}
    missing = sum(1 for row in rows if "missing_name" in (row.error_codes or []))
    malformed = sum(
        1
        for row in rows
        if "malformed_email" in (row.error_codes or []) or "malformed_phone" in (row.error_codes or [])
    )
    return {
        "id": str(batch.id),
        "sheet_count": batch.sheet_count,
        "row_count": batch.row_count,
        "valid_count": batch.valid_count,
        "invalid_count": batch.invalid_count,
        "missing_required": missing,
        "malformed": malformed,
        "duplicate_count": batch.duplicate_count,
        "relationship_count": batch.relationship_count,
        "created_count": batch.created_count,
        "ignored_column_count": batch.ignored_column_count,
        "rows": [
            {
                "row": row.row_number,
                "outcome": row.outcome,
                "errors": row.error_codes or [],
                "candidate_id": str(row.candidate_id) if row.candidate_id else None,
                "relationship": row.relationship,
                "duplicate_of_row": row.duplicate_of_row,
                "review_id": str(review_ids[row.id]) if row.id in review_ids else None,
            }
            for row in rows
        ],
    }


def _status(code: str) -> int:
    if code == "unsupported_file":
        return 415
    if code == "file_too_large":
        return 413
    return 422

"""Old finished documents are archived and kept. Nothing is deleted."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import AuditEvent, CandidateDocument
from app.services.retention import apply_retention


def _document(session, *, status: str, age_days: int) -> CandidateDocument:
    document = CandidateDocument(
        sha256=f"{status}{age_days:04d}".ljust(64, "a"),
        original_filename="record.pdf",
        media_type="application/pdf",
        byte_size=32,
        storage_key=f"synthetic/{status}-{age_days}",
        status=status,
        is_current=False,
        processing_version=1,
        received_at=datetime.now(UTC) - timedelta(days=age_days),
    )
    session.add(document)
    session.flush()
    return document


def test_old_documents_are_archived_and_retained(session):
    old = _document(session, status="profiled", age_days=800)
    waiting = _document(session, status="needs_ocr", age_days=800)
    recent = _document(session, status="profiled", age_days=10)
    processing = _document(session, status="received", age_days=800)
    session.commit()
    assert apply_retention(session) == 2
    session.commit()
    assert session.get(CandidateDocument, old.id).status == "archived"
    assert session.get(CandidateDocument, waiting.id).status == "archived"
    assert session.get(CandidateDocument, recent.id).status == "profiled"
    assert session.get(CandidateDocument, processing.id).status == "received"
    assert session.scalar(select(func.count()).select_from(CandidateDocument)) == 4
    again = apply_retention(session)
    session.commit()
    assert again == 0
    assert session.get(CandidateDocument, old.id).status == "archived"
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "documents_archived"))
    assert event.detail == {"count": 2}
    assert "@" not in str(event.detail)

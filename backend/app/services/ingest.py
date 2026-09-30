"""Store a file and enqueue extraction. The same bytes are the same document."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import Actor
from app.extraction.media import UnsupportedFile, detect_media_type, safe_filename
from app.extraction.textutil import sha256_bytes
from app.jobs.queue import enqueue_extract
from app.models import CandidateDocument
from app.services.audit import write_audit
from app.storage.local import LocalStorage


class IngestResult:
    def __init__(self, document: CandidateDocument, created: bool) -> None:
        self.document = document
        self.created = created


def ingest_bytes(
    session: Session,
    *,
    filename: str | None,
    data: bytes,
    actor: Actor,
    storage: LocalStorage | None = None,
) -> IngestResult:
    if not data:
        raise UnsupportedFile()
    if len(data) > get_settings().max_upload_bytes:
        raise UnsupportedFile()
    media_type = detect_media_type(data)
    digest = sha256_bytes(data)
    existing = session.scalar(select(CandidateDocument).where(CandidateDocument.sha256 == digest))
    if existing is not None:
        write_audit(
            session,
            actor=actor,
            action="same_document",
            entity_type="candidate_document",
            entity_id=existing.id,
            detail={"identity_outcome": "same_document"},
        )
        return IngestResult(existing, created=False)

    store = storage or LocalStorage(get_settings().storage_dir)
    key = store.write(digest, data)
    document = CandidateDocument(
        sha256=digest,
        original_filename=safe_filename(filename),
        media_type=media_type,
        byte_size=len(data),
        storage_key=key,
        status="received",
        is_current=False,
        processing_version=get_settings().processing_version,
        received_at=datetime.now(timezone.utc),
    )
    session.add(document)
    session.flush()
    enqueue_extract(session, document.id)
    write_audit(
        session,
        actor=actor,
        action="document_received",
        entity_type="candidate_document",
        entity_id=document.id,
        detail={"processing_version": document.processing_version},
    )
    return IngestResult(document, created=True)

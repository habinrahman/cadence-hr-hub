"""Archive finished documents after the retention period. Nothing is deleted."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import SYSTEM, Actor
from app.domain.transitions import transition
from app.models import CandidateDocument
from app.services.audit import write_audit

# Processing states stay as they are. Finished and terminal copies are archived.
RETAINED_STATUSES = frozenset(
    {"extracted", "needs_review", "profiled", "needs_ocr", "failed", "quarantined"}
)


def apply_retention(session: Session, *, now: datetime | None = None, actor: Actor = SYSTEM) -> int:
    moment = now or datetime.now(UTC)
    cutoff = moment - timedelta(days=get_settings().retention_days)
    rows = session.scalars(
        select(CandidateDocument).where(
            CandidateDocument.status.in_(RETAINED_STATUSES),
            CandidateDocument.received_at < cutoff,
        )
    ).all()
    for document in rows:
        transition(document, "archived", machine="candidate_document", actor=actor)
    if rows:
        write_audit(
            session,
            actor=actor,
            action="documents_archived",
            entity_type="candidate_document",
            entity_id=None,
            detail={"count": len(rows)},
        )
    session.flush()
    return len(rows)

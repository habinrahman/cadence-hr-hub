from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FieldLock


def is_locked(
    session: Session,
    *,
    candidate_id: UUID,
    entity_type: str,
    entity_id: UUID | None,
    field_name: str,
) -> bool:
    statement = select(FieldLock.id).where(
        FieldLock.candidate_id == candidate_id,
        FieldLock.entity_type == entity_type,
        FieldLock.field_name == field_name,
    )
    if entity_id is None:
        statement = statement.where(FieldLock.entity_id.is_(None))
    else:
        statement = statement.where(FieldLock.entity_id == entity_id)
    return session.scalar(statement) is not None


def lock_field(
    session: Session,
    *,
    candidate_id: UUID,
    entity_type: str,
    entity_id: UUID | None,
    field_name: str,
    locked_by: UUID,
    reason: str | None = None,
) -> FieldLock:
    existing = session.scalar(
        select(FieldLock).where(
            FieldLock.candidate_id == candidate_id,
            FieldLock.entity_type == entity_type,
            FieldLock.field_name == field_name,
            FieldLock.entity_id.is_(None) if entity_id is None else FieldLock.entity_id == entity_id,
        )
    )
    if existing is not None:
        return existing
    row = FieldLock(
        candidate_id=candidate_id,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        locked_by=locked_by,
        reason=reason[:200] if reason else None,
    )
    session.add(row)
    session.flush()
    return row

"""Audit rows carry ids and codes. They do not carry CV text or contact values.

Rows are insert-only. The database rejects UPDATE and DELETE on audit_events.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.actor import Actor
from app.models import AuditEvent

ALLOWED_DETAIL_KEYS = frozenset(
    {
        "from_status",
        "to_status",
        "machine",
        "outcome",
        "signal",
        "field",
        "error_code",
        "count",
        "processing_version",
        "document_id",
        "candidate_id",
        "job_id",
        "review_id",
        "agent_run_id",
        "identity_outcome",
        "text_source",
        "skipped",
        "validation_result",
        "confidence",
        "relationship",
        "recommended_action",
        "human_action",
        "request_id",
        "match_id",
        "shortlist_id",
        "disposition",
        "result",
        "strength",
        "source_type",
        "report_id",
        "period_start",
        "period_end",
        "created_count",
        "invalid_count",
        "duplicate_count",
        "relationship_count",
        "survivor_id",
        "absorbed_id",
    }
)


class AuditPayloadError(Exception):
    pass


def write_audit(
    session: Session,
    *,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: UUID | None,
    detail: dict | None = None,
    agent_run_id: UUID | None = None,
) -> AuditEvent:
    payload = detail or {}
    _assert_safe(payload)
    event = AuditEvent(
        actor_kind=actor.kind,
        actor_user_id=actor.user_id,
        agent_run_id=agent_run_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=payload,
    )
    session.add(event)
    return event


def _assert_safe(detail: dict) -> None:
    for key, value in detail.items():
        if key not in ALLOWED_DETAIL_KEYS:
            raise AuditPayloadError(key)
        _assert_value(key, value)


def _assert_value(key: str, value: object) -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, str):
        if "@" in value:
            raise AuditPayloadError(key)
        return
    if isinstance(value, list) and all(isinstance(item, str) and "@" not in item for item in value):
        return
    raise AuditPayloadError(key)

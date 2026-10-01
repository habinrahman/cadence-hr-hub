"""Status changes go through this function. Callers do not assign status themselves."""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.actor import Actor

MACHINES: dict[str, dict[str, frozenset[str]]] = {
    # A request is submitted, opened by the worker, and moves between open and matching on each run. Whether its pool
    # may be shortlisted or shared is derived from the requirements (hiring.pool_status), not stored here.
    "hiring_request": {
        "draft": frozenset({"submitted", "cancelled"}),
        "submitted": frozenset({"open", "cancelled"}),
        "open": frozenset({"matching", "closed", "cancelled"}),
        "matching": frozenset({"open", "closed"}),
        "closed": frozenset(),
        "cancelled": frozenset(),
    },
    "candidate_document": {
        "received": frozenset({"extracting", "failed"}),
        "extracting": frozenset({"extracted", "needs_ocr", "needs_review", "failed"}),
        "needs_ocr": frozenset({"extracted", "failed", "archived"}),
        "extracted": frozenset({"profiled", "needs_review", "archived"}),
        "needs_review": frozenset({"profiled", "extracted", "archived"}),
        "profiled": frozenset({"archived", "needs_review"}),
        "failed": frozenset({"quarantined", "archived"}),
        "quarantined": frozenset({"archived"}),
        "archived": frozenset(),
    },
    "job": {
        "queued": frozenset({"leased", "quarantined"}),
        "leased": frozenset({"running", "queued", "quarantined"}),
        "running": frozenset({"succeeded", "failed", "queued"}),
        "failed": frozenset({"queued", "quarantined"}),
        "succeeded": frozenset(),
        "quarantined": frozenset(),
    },
    "duplicate_review": {
        "pending": frozenset({"accepted_update", "recorded_duplicate", "created_separate"}),
        "accepted_update": frozenset(),
        "recorded_duplicate": frozenset(),
        "created_separate": frozenset(),
    },
    "problem_report": {
        "open": frozenset({"in_progress", "resolved"}),
        "in_progress": frozenset({"resolved", "open"}),
        "resolved": frozenset(),
    },
}

# A person has to take these. An agent or the worker cannot.
USER_ONLY = frozenset(
    {
        ("duplicate_review", "accepted_update"),
        ("duplicate_review", "recorded_duplicate"),
        ("duplicate_review", "created_separate"),
    }
)

INITIAL = {
    "hiring_request": "draft",
    "candidate_document": "received",
    "job": "queued",
    "duplicate_review": "pending",
    "problem_report": "open",
}


class TransitionError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def transition(
    entity,
    to_status: str,
    *,
    machine: str,
    actor: Actor,
    now: datetime | None = None,
) -> None:
    """Move entity.status. Writes nothing except the status field."""
    current = entity.status
    allowed = MACHINES[machine].get(current)
    if allowed is None or to_status not in allowed:
        raise TransitionError("invalid_transition")
    if (machine, to_status) in USER_ONLY and actor.kind != "user":
        raise TransitionError("human_required")
    if machine == "job" and current == "running" and to_status == "queued":
        moment = now or utcnow()
        lease = entity.lease_expires_at
        if lease is None or lease >= moment:
            raise TransitionError("lease_still_held")
    if machine == "job" and current == "leased" and to_status == "queued":
        moment = now or utcnow()
        lease = entity.lease_expires_at
        if lease is not None and lease >= moment:
            raise TransitionError("lease_still_held")
    entity.status = to_status

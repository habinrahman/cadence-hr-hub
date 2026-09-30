"""Recruiter merge of two profiles that already exist.

Duplicate detection does not call this. The older profile survives. The newer
profile stays in the database and points at the survivor. Child rows move.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.actor import Actor
from app.models import (
    AgentRun,
    Application,
    Candidate,
    CandidateCertificate,
    CandidateContact,
    CandidateDocument,
    CandidateEducation,
    CandidateExperience,
    CandidateSkill,
    CandidateSource,
    DuplicateReview,
    ExcelImportRow,
    ExtractionEvidence,
    FieldLock,
    SharingRecord,
    User,
)
from app.models.hiring import CandidateMatch, ShortlistCandidate
from app.services.audit import write_audit

_PLAIN = (
    CandidateContact,
    Application,
    CandidateExperience,
    CandidateEducation,
    CandidateSkill,
    CandidateCertificate,
    ExtractionEvidence,
    AgentRun,
    DuplicateReview,
    CandidateSource,
    ExcelImportRow,
    SharingRecord,
)


class MergeError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def preview_merge(session: Session, left_id: UUID, right_id: UUID, actor: Actor) -> dict:
    _recruiter(session, actor)
    survivor, absorbed = _pair(session, left_id, right_id)
    return _payload(session, survivor, absorbed)


def merge_profiles(
    session: Session,
    left_id: UUID,
    right_id: UUID,
    actor: Actor,
    *,
    confirm: bool,
) -> dict:
    _recruiter(session, actor)
    if not confirm:
        raise MergeError("confirmation_required")
    survivor, absorbed = _pair(session, left_id, right_id)
    documents = session.scalars(
        select(CandidateDocument).where(CandidateDocument.candidate_id.in_([survivor.id, absorbed.id]))
    ).all()
    chosen = _current_document(documents)
    for document in documents:
        document.is_current = False
    session.flush()
    document_count = _count(session, CandidateDocument, absorbed.id)
    session.execute(
        update(CandidateDocument)
        .where(CandidateDocument.candidate_id == absorbed.id)
        .values(candidate_id=survivor.id)
    )
    session.flush()
    if chosen is not None:
        current = session.get(CandidateDocument, chosen)
        if current is not None:
            current.is_current = True
    for model in _PLAIN:
        session.execute(update(model).where(model.candidate_id == absorbed.id).values(candidate_id=survivor.id))
    _reassign_unless_conflict(session, FieldLock, absorbed.id, survivor.id, ("entity_type", "entity_id", "field_name"))
    _reassign_unless_conflict(session, CandidateMatch, absorbed.id, survivor.id, ("request_id",))
    _reassign_unless_conflict(session, ShortlistCandidate, absorbed.id, survivor.id, ("shortlist_id",))
    absorbed.merged_into_id = survivor.id
    absorbed.merged_at = datetime.now(UTC)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="profiles_merged",
        entity_type="candidate",
        entity_id=survivor.id,
        detail={
            "human_action": "merge_profiles",
            "candidate_id": str(survivor.id),
            "survivor_id": str(survivor.id),
            "absorbed_id": str(absorbed.id),
            "count": document_count,
        },
    )
    return _payload(session, survivor, absorbed)


def _recruiter(session: Session, actor: Actor) -> User:
    if actor.kind != "user" or actor.user_id is None:
        raise MergeError("human_required")
    user = session.get(User, actor.user_id)
    if user is None or user.role != "recruiter":
        raise MergeError("recruiter_required")
    return user


def _pair(session: Session, left_id: UUID, right_id: UUID) -> tuple[Candidate, Candidate]:
    if left_id == right_id:
        raise MergeError("same_candidate")
    left = session.get(Candidate, left_id)
    right = session.get(Candidate, right_id)
    if left is None or right is None:
        raise MergeError("not_found")
    if left.merged_into_id is not None or right.merged_into_id is not None:
        raise MergeError("already_merged")
    return _survivor(left, right)


def _survivor(left: Candidate, right: Candidate) -> tuple[Candidate, Candidate]:
    left_key = (left.created_at, str(left.id))
    right_key = (right.created_at, str(right.id))
    if left_key <= right_key:
        return left, right
    return right, left


def _current_document(documents: list[CandidateDocument]) -> UUID | None:
    current = [item for item in documents if item.is_current]
    if not current:
        return None
    chosen = max(current, key=lambda item: (item.received_at, str(item.id)))
    return chosen.id


def _reassign_unless_conflict(
    session: Session,
    model,
    absorbed_id: UUID,
    survivor_id: UUID,
    keys: tuple[str, ...],
) -> None:
    rows = session.scalars(select(model).where(model.candidate_id == absorbed_id)).all()
    for row in rows:
        clauses = [model.candidate_id == survivor_id]
        for key in keys:
            value = getattr(row, key)
            column = getattr(model, key)
            clauses.append(column.is_(None) if value is None else column == value)
        conflict = session.scalar(select(model.id).where(*clauses))
        if conflict is None:
            row.candidate_id = survivor_id


def _payload(session: Session, survivor: Candidate, absorbed: Candidate) -> dict:
    return {
        "survivor_id": str(survivor.id),
        "absorbed_id": str(absorbed.id),
        "profiles": [_profile(session, survivor), _profile(session, absorbed)],
    }


def _profile(session: Session, candidate: Candidate) -> dict:
    return {
        "id": str(candidate.id),
        "display_name": candidate.display_name,
        "source": candidate.source,
        "merged_into_id": str(candidate.merged_into_id) if candidate.merged_into_id else None,
        "contacts": [
            {"kind": row.kind, "value": row.value_raw}
            for row in session.scalars(select(CandidateContact).where(CandidateContact.candidate_id == candidate.id))
        ],
        "experiences": [
            {"employer": row.employer, "title": row.title}
            for row in session.scalars(
                select(CandidateExperience).where(CandidateExperience.candidate_id == candidate.id)
            )
        ],
        "education": [
            {"institution": row.institution, "credential": row.credential}
            for row in session.scalars(select(CandidateEducation).where(CandidateEducation.candidate_id == candidate.id))
        ],
        "skills": [
            row.name
            for row in session.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id))
        ],
        "document_count": _count(session, CandidateDocument, candidate.id),
        "application_count": _count(session, Application, candidate.id),
    }


def _count(session: Session, model, candidate_id: UUID) -> int:
    return len(session.scalars(select(model.id).where(model.candidate_id == candidate_id)).all())

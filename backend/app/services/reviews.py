"""A person decides a relationship review. The recommendation is not applied by itself."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.actor import Actor
from app.domain.confidence import (
    ACCEPT_UPDATE,
    ALL_ACTIONS,
    RECORD_DUPLICATE,
    STATUS_FOR,
    signal_payload,
)
from app.domain.transitions import TransitionError, transition
from app.models import (
    Application,
    Candidate,
    CandidateContact,
    CandidateDocument,
    DuplicateReview,
    ExcelImportRow,
    ExtractionEvidence,
    User,
)
from app.services.audit import write_audit
from app.services.pipeline import _attach, profile_document


def decide_duplicate_review(
    session: Session,
    review: DuplicateReview,
    action: str,
    actor: Actor,
    *,
    candidate_id: UUID | None = None,
) -> None:
    status = STATUS_FOR.get(action)
    if status is None:
        raise TransitionError("invalid_transition")
    if actor.kind != "user":
        raise TransitionError("human_required")
    if review.document_id is None:
        _decide_excel_review(session, review, action, actor, status)
        return
    document = session.get(CandidateDocument, review.document_id)
    if document is None:
        raise TransitionError("invalid_transition")
    target: Candidate | None = None
    if action in {ACCEPT_UPDATE, RECORD_DUPLICATE}:
        target = session.get(Candidate, _target_candidate(review, candidate_id))
        if target is None:
            raise TransitionError("invalid_transition")
        if target.merged_into_id is not None:
            # That profile was merged into another since the review opened. Attaching a CV to it would hide the CV
            # on a profile nobody sees; the recruiter re-checks against the surviving profile instead.
            raise TransitionError("candidate_merged")
    transition(review, status, machine="duplicate_review", actor=actor)
    review.decided_by = actor.user_id
    review.decided_at = datetime.now(timezone.utc)
    canonical_id: UUID | None = None
    if action == ACCEPT_UPDATE:
        _link(session, document, target, make_current=True)
    elif action == RECORD_DUPLICATE:
        canonical_id = _archive_duplicate(session, document, target, actor)
    else:
        _link(session, document, Candidate(source="upload"), make_current=True)
    if action != RECORD_DUPLICATE and document.status == "needs_review":
        transition(document, "extracted", machine="candidate_document", actor=actor)
    if action != RECORD_DUPLICATE:
        # The decision attaches the CV; only now does what it says become part of the profile.
        profile_document(session, document, session.get(Candidate, document.candidate_id), actor)
    detail = {
        "human_action": action,
        "recommended_action": review.recommended_action,
        "relationship": review.likely_relationship,
        "confidence": _whole_percent(review.confidence),
        "document_id": str(document.id),
        "candidate_id": str(target.id) if action == RECORD_DUPLICATE else (str(document.candidate_id) if document.candidate_id else None),
    }
    if action == RECORD_DUPLICATE:
        detail["outcome"] = "archived"
        detail["canonical_document_id"] = str(canonical_id) if canonical_id else None
    write_audit(
        session,
        actor=actor,
        action="duplicate_review_decided",
        entity_type="duplicate_review",
        entity_id=review.id,
        detail=detail,
    )


def _archive_duplicate(session: Session, document: CandidateDocument, target: Candidate, actor: Actor) -> UUID | None:
    """Delete Duplicate. Only the duplicate upload is archived, under the retention model: rows and file are kept.

    The document is not attached to the candidate, gets no application and never becomes current, so the candidate
    and the canonical CV are untouched. Returns the canonical (current) document id for the audit trail.
    """
    if document.is_current or document.candidate_id is not None:
        raise TransitionError("invalid_transition")  # never archive a document a candidate already relies on
    canonical = session.scalar(
        select(CandidateDocument.id).where(
            CandidateDocument.candidate_id == target.id,
            CandidateDocument.is_current.is_(True),
        )
    )
    if canonical == document.id:
        raise TransitionError("invalid_transition")
    transition(document, "archived", machine="candidate_document", actor=actor)
    return canonical


def open_excel_relationship_review(session: Session, row: ExcelImportRow, assessment, actor: Actor) -> DuplicateReview:
    """Open the same review record a CV match uses. The row is not applied here."""
    review = DuplicateReview(
        document_id=None,
        excel_import_row_id=row.id,
        candidate_id=assessment.candidate_id,
        status="pending",
        proposed_outcome=assessment.relationship or "uncertain",
        confidence=None if assessment.confidence is None else round(assessment.confidence * 100, 2),
        likely_relationship=assessment.relationship,
        recommended_action=assessment.recommended_action,
        offered_actions=list(ALL_ACTIONS),
        signals={
            "ambiguous": assessment.ambiguous,
            "candidate_ids": [str(item) for item in assessment.candidate_ids],
            "evidence": [signal_payload(item) for item in assessment.signals],
            "source": "excel",
        },
    )
    session.add(review)
    session.flush()
    write_audit(
        session,
        actor=actor,
        action="duplicate_review_opened",
        entity_type="excel_import_row",
        entity_id=row.id,
        detail={
            "review_id": str(review.id),
            "candidate_id": str(assessment.candidate_id) if assessment.candidate_id else None,
            "relationship": assessment.relationship,
            "recommended_action": assessment.recommended_action,
            "confidence": None if assessment.confidence is None else int(round(assessment.confidence * 100)),
            "source_type": "excel",
            "count": len(assessment.candidate_ids),
        },
    )
    return review


def _decide_excel_review(session: Session, review: DuplicateReview, action: str, actor: Actor, status: str) -> None:
    user = session.get(User, actor.user_id) if actor.user_id else None
    if user is None or user.role != "recruiter":
        raise TransitionError("forbidden")
    row = session.get(ExcelImportRow, review.excel_import_row_id) if review.excel_import_row_id else None
    if row is None or row.candidate_id is None:
        raise TransitionError("invalid_transition")
    existing = session.get(Candidate, row.candidate_id)
    if existing is None or existing.merged_into_id is not None:
        raise TransitionError("invalid_transition")
    transition(review, status, machine="duplicate_review", actor=actor)
    review.decided_by = actor.user_id
    review.decided_at = datetime.now(timezone.utc)
    if action == ACCEPT_UPDATE:
        _apply_excel_update(session, existing, row)
        result_id = existing.id
    elif action == RECORD_DUPLICATE:
        _excel_application(session, existing.id)
        result_id = existing.id
    else:
        created = _excel_candidate(session, row)
        row.candidate_id = created.id
        result_id = created.id
    write_audit(
        session,
        actor=actor,
        action="duplicate_review_decided",
        entity_type="duplicate_review",
        entity_id=review.id,
        detail={
            "human_action": action,
            "recommended_action": review.recommended_action,
            "relationship": review.likely_relationship,
            "confidence": _whole_percent(review.confidence),
            "candidate_id": str(result_id),
            "review_id": str(review.id),
            "source_type": "excel",
        },
    )


def _apply_excel_update(session: Session, candidate: Candidate, row: ExcelImportRow) -> None:
    if not candidate.display_name and row.proposed_name:
        candidate.display_name = row.proposed_name
    _add_missing_contact(session, candidate.id, "email", row.proposed_email)
    _add_missing_contact(session, candidate.id, "phone", row.proposed_phone)
    _excel_application(session, candidate.id)


def _excel_candidate(session: Session, row: ExcelImportRow) -> Candidate:
    candidate = Candidate(source="excel", display_name=row.proposed_name)
    session.add(candidate)
    session.flush()
    _add_missing_contact(session, candidate.id, "email", row.proposed_email)
    _add_missing_contact(session, candidate.id, "phone", row.proposed_phone)
    _excel_application(session, candidate.id)
    return candidate


def _excel_application(session: Session, candidate_id: UUID) -> None:
    session.add(
        Application(
            candidate_id=candidate_id,
            document_id=None,
            source="excel",
            received_at=datetime.now(timezone.utc),
        )
    )


def _add_missing_contact(session: Session, candidate_id: UUID, kind: str, normalized: str | None) -> None:
    if not normalized:
        return
    existing = session.scalar(
        select(CandidateContact.id).where(
            CandidateContact.candidate_id == candidate_id,
            CandidateContact.kind == kind,
            CandidateContact.value_normalized == normalized,
        )
    )
    if existing is not None:
        return
    session.add(
        CandidateContact(
            candidate_id=candidate_id,
            kind=kind,
            value_raw=normalized[:320],
            value_normalized=normalized[:320],
            is_primary=False,
        )
    )


def _target_candidate(review: DuplicateReview, candidate_id: UUID | None) -> UUID:
    chosen = candidate_id or review.candidate_id
    if chosen is None:
        raise TransitionError("invalid_transition")
    allowed = {UUID(item) for item in review.signals.get("candidate_ids", [])}
    if allowed and chosen not in allowed:
        raise TransitionError("invalid_transition")
    return chosen


def _whole_percent(value) -> int | None:
    if value is None:
        return None
    return int(round(float(value)))


def _link(session: Session, document: CandidateDocument, candidate: Candidate, *, make_current: bool) -> None:
    if sa_inspect(candidate).transient:
        session.add(candidate)
        session.flush()
    previous = None
    if make_current:
        previous = session.scalar(
            select(CandidateDocument.id).where(
                CandidateDocument.candidate_id == candidate.id,
                CandidateDocument.is_current.is_(True),
            )
        )
    emails, phones = _contacts_from_evidence(session, document.id)
    _attach(
        session,
        document,
        candidate,
        emails,
        phones,
        supersedes=previous,
        write_evidence=False,
        make_current=make_current,
    )
    session.execute(
        update(ExtractionEvidence)
        .where(
            ExtractionEvidence.document_id == document.id,
            ExtractionEvidence.candidate_id.is_(None),
        )
        .values(candidate_id=candidate.id)
    )


def _contacts_from_evidence(session: Session, document_id):
    rows = session.scalars(
        select(ExtractionEvidence).where(
            ExtractionEvidence.document_id == document_id,
            ExtractionEvidence.entity_type == "contact",
        )
    )
    emails = []
    phones = []
    for row in rows:
        pair = (row.source_quote, row.extracted_value)
        if row.field_name == "email":
            emails.append(pair)
        elif row.field_name == "phone":
            phones.append(pair)
    return emails, phones

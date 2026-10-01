"""Re-score every pending CV relationship review with the current identity rules.

A review's score is stored when its CV is read, so a change to the scoring rules does not reach reviews already
waiting for a recruiter. This recomputes them. Email and phone are compared again from the stored contacts, with
the current phone rule; the name, date and content measurements are reused exactly as they were recorded. Decided
reviews are never touched, nothing is merged or deleted, and every change is written to the audit trail.

    python -m app.jobs.rescore_reviews
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import make_session_factory
from app.domain.actor import SYSTEM
from app.domain.confidence import ALL_ACTIONS, PairEvidence, Weights, assess, signal_payload
from app.models import CandidateContact, CandidateDocument, DuplicateReview, ExcelImportRow, ExtractionEvidence
from app.services.audit import write_audit
from app.services.compare import _match, phone_match

_BOOL = {"matched": True, "unmatched": False}


def rescore_pending_reviews(session: Session) -> list[tuple[UUID, float | None, float | None]]:
    """Returns (review id, old confidence, new confidence) for every review whose result changed."""
    settings = get_settings()
    weights = Weights(
        email=settings.identity_weight_email,
        phone=settings.identity_weight_phone,
        name=settings.identity_weight_name,
        dates=settings.identity_weight_dates,
        explicit_version=settings.identity_weight_explicit_version,
        employment=settings.identity_weight_employment,
        education=settings.identity_weight_education,
        skills=settings.identity_weight_skills,
        semantic=settings.identity_weight_semantic,
    )
    changed: list[tuple[UUID, float | None, float | None]] = []
    for review in session.scalars(select(DuplicateReview).where(DuplicateReview.status == "pending")).all():
        signals = review.signals or {}
        candidate_ids = [UUID(item) for item in signals.get("candidate_ids", [])]
        if not candidate_ids:
            continue
        emails, phones = _incoming_contacts(session, review)
        pairs = [_pair(session, candidate_id, signals.get("evidence", []), emails, phones) for candidate_id in candidate_ids]
        result = assess(
            pairs,
            weights=weights,
            high_confidence=settings.identity_high_confidence,
            relationship_cutoff=settings.identity_relationship_cutoff,
        )
        if not result.comparable:
            continue
        old = float(review.confidence) if review.confidence is not None else None
        new = round(result.confidence * 100, 2)
        excel = review.document_id is None
        offered = list(ALL_ACTIONS) if excel else list(result.offered_actions)
        if (old, review.likely_relationship, review.recommended_action, review.offered_actions) == (
            new,
            result.relationship,
            result.recommended_action,
            offered,
        ):
            continue
        review.confidence = new
        review.likely_relationship = result.relationship
        review.proposed_outcome = result.relationship or "uncertain"
        review.recommended_action = result.recommended_action
        review.offered_actions = offered
        review.signals = {
            **signals,
            "ambiguous": result.ambiguous,
            "candidate_ids": [str(item) for item in result.candidate_ids],
            "evidence": [signal_payload(item) for item in result.signals],
        }
        if review.candidate_id is not None or result.candidate_id is not None:
            review.candidate_id = result.candidate_id or review.candidate_id
        if not excel:
            document = session.get(CandidateDocument, review.document_id)
            if document is not None and document.candidate_id is None:
                document.identity_outcome = "ambiguous" if result.ambiguous else result.relationship
        write_audit(
            session,
            actor=SYSTEM,
            action="duplicate_review_rescored",
            entity_type="duplicate_review",
            entity_id=review.id,
            detail={
                "relationship": result.relationship,
                "confidence": int(round(new)),
                "recommended_action": result.recommended_action,
                "count": len(result.candidate_ids),
            },
        )
        changed.append((review.id, old, new))
    return changed


def _incoming_contacts(session: Session, review: DuplicateReview) -> tuple[set[str], set[str]]:
    if review.document_id is None:
        row = session.get(ExcelImportRow, review.excel_import_row_id) if review.excel_import_row_id else None
        if row is None:
            return set(), set()
        return ({row.proposed_email} if row.proposed_email else set()), ({row.proposed_phone} if row.proposed_phone else set())
    rows = session.execute(
        select(ExtractionEvidence.field_name, ExtractionEvidence.extracted_value).where(
            ExtractionEvidence.document_id == review.document_id,
            ExtractionEvidence.entity_type == "contact",
        )
    ).all()
    return {value for field, value in rows if field == "email"}, {value for field, value in rows if field == "phone"}


def _pair(session: Session, candidate_id: UUID, evidence: list[dict], emails: set[str], phones: set[str]) -> PairEvidence:
    recorded = {item["code"]: item for item in evidence if item.get("candidate_id") in (None, str(candidate_id))}
    stored = session.execute(
        select(CandidateContact.kind, CandidateContact.value_normalized).where(CandidateContact.candidate_id == candidate_id)
    ).all()
    stored_emails = {value for kind, value in stored if kind == "email"}
    stored_phones = {value for kind, value in stored if kind == "phone"}

    def flag(code: str) -> bool | None:
        return _BOOL.get(recorded.get(code, {}).get("state"))

    def value(code: str) -> float | None:
        item = recorded.get(code, {})
        return item.get("value") if item.get("state") == "recorded" else None

    # Contacts are compared again; when this review stored none for a side, keep what was recorded at the time.
    email = _match(emails, stored_emails) if emails and stored_emails else flag("email")
    phone = phone_match(phones, stored_phones) if phones and stored_phones else flag("phone")
    return PairEvidence(
        candidate_id=candidate_id,
        email_match=email,
        phone_match=phone,
        name_similarity=value("name"),
        document_hash_match=recorded.get("document_hash", {}).get("state") == "matched",
        incoming_is_newer=flag("cv_dates"),
        explicit_version_newer=flag("explicit_version"),
        employment_similarity=value("employment"),
        education_similarity=value("education"),
        skills_similarity=value("skills"),
        semantic_similarity=value("semantic"),
    )


def main() -> None:
    factory = make_session_factory()
    with factory() as session:
        changed = rescore_pending_reviews(session)
        session.commit()
    for review_id, old, new in changed:
        print(f"{review_id}: {old} -> {new}")
    print(f"re-scored {len(changed)} pending review(s)")


if __name__ == "__main__":
    main()

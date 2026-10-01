"""Candidate read model. It shows stored rows and does not change them."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    AuditEvent,
    Candidate,
    CandidateCertificate,
    CandidateContact,
    CandidateDocument,
    CandidateEducation,
    CandidateExperience,
    CandidateSkill,
    CandidateSource,
    DuplicateReview,
    ExtractionEvidence,
)


def candidate_profile(session: Session, candidate: Candidate) -> dict:
    experiences = list(
        session.scalars(select(CandidateExperience).where(CandidateExperience.candidate_id == candidate.id)).all()
    )
    skills = list(session.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id)).all())
    certificates = list(
        session.scalars(select(CandidateCertificate).where(CandidateCertificate.candidate_id == candidate.id)).all()
    )
    documents = list(
        session.scalars(
            select(CandidateDocument)
            .where(CandidateDocument.candidate_id == candidate.id)
            .order_by(CandidateDocument.received_at.desc())
        ).all()
    )
    # The newest relationship review per document, so the page never has to probe for one.
    reviews: dict = {}
    for document_id, review_id in session.execute(
        select(DuplicateReview.document_id, DuplicateReview.id)
        .where(DuplicateReview.document_id.in_([row.id for row in documents]))
        .order_by(DuplicateReview.created_at)
    ):
        reviews[document_id] = str(review_id)
    applications = list(
        session.scalars(
            select(Application)
            .where(Application.candidate_id == candidate.id)
            .order_by(Application.received_at.desc())
        ).all()
    )
    return {
        "id": str(candidate.id),
        "display_name": candidate.display_name,
        "summary": candidate.summary,
        "narrative": _narrative(candidate, experiences, skills),
        "years_of_experience": (
            float(candidate.years_of_experience) if candidate.years_of_experience is not None else None
        ),
        "source": candidate.source,
        "sources": [
            {
                "source_type": row.source_type,
                "source_reference": row.source_reference,
            }
            for row in session.scalars(
                select(CandidateSource).where(CandidateSource.candidate_id == candidate.id)
            )
        ],
        "contacts": [
            {"kind": row.kind, "value": row.value_raw}
            for row in session.scalars(select(CandidateContact).where(CandidateContact.candidate_id == candidate.id))
        ],
        "experiences": [{"employer": row.employer, "title": row.title} for row in experiences],
        "education": [
            {"institution": row.institution, "credential": row.credential}
            for row in session.scalars(select(CandidateEducation).where(CandidateEducation.candidate_id == candidate.id))
        ],
        "skills": [row.name for row in skills],
        "certificates": [
            {"name": row.name, "kind": row.kind} for row in certificates if row.kind != "qualification"
        ],
        "qualifications": [
            {"name": row.name, "kind": row.kind} for row in certificates if row.kind == "qualification"
        ],
        "applications": [
            {
                "id": str(row.id),
                "source": row.source,
                "received_at": row.received_at.isoformat(),
                "application_date": row.application_date.isoformat() if row.application_date else None,
                "document_id": str(row.document_id) if row.document_id else None,
            }
            for row in applications
        ],
        "documents": [
            {
                "id": str(row.id),
                "original_filename": row.original_filename,
                "status": row.status,
                "is_current": row.is_current,
                "received_at": row.received_at.isoformat(),
                "supersedes_document_id": str(row.supersedes_document_id) if row.supersedes_document_id else None,
                "review_id": reviews.get(row.id),
            }
            for row in documents
        ],
        "evidence": [
            {
                "field": row.field_name,
                "value": row.extracted_value,
                "quote": row.source_quote,
                "page": row.page,
                "quote_verified": row.quote_verified,
            }
            for row in session.scalars(
                select(ExtractionEvidence).where(ExtractionEvidence.candidate_id == candidate.id)
            )
        ],
        "activity": _activity(session, candidate.id, [row.id for row in documents]),
    }


def _narrative(candidate: Candidate, experiences: list[CandidateExperience], skills: list[CandidateSkill]) -> str | None:
    if candidate.summary:
        return candidate.summary
    parts: list[str] = []
    if candidate.years_of_experience is not None:
        parts.append(f"{float(candidate.years_of_experience):g} years of experience")
    if experiences:
        first = experiences[0]
        if first.title and first.employer:
            parts.append(f"{first.title} at {first.employer}")
        elif first.title or first.employer:
            parts.append(first.title or first.employer)
    if skills:
        parts.append("Skills: " + ", ".join(row.name for row in skills[:8]))
    if not parts:
        return None
    return ". ".join(parts)


def _activity(session: Session, candidate_id, document_ids: list) -> list[dict]:
    review_ids = []
    if document_ids:
        review_ids = list(
            session.scalars(select(DuplicateReview.id).where(DuplicateReview.document_id.in_(document_ids))).all()
        )
    ids = [candidate_id, *document_ids, *review_ids]
    rows = session.scalars(
        select(AuditEvent).where(AuditEvent.entity_id.in_(ids)).order_by(AuditEvent.created_at.desc()).limit(20)
    ).all()
    return [
        {
            "action": row.action,
            "actor_kind": row.actor_kind,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]

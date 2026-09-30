"""Hybrid retrieval. Vector similarity is one signal, not the whole answer."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Candidate,
    CandidateCertificate,
    CandidateDocument,
    CandidateEducation,
    CandidateExperience,
    CandidateSkill,
    DocumentChunk,
)

_CONFIRMED = ("extracted", "profiled")
_SNIPPET = 160


@dataclass
class SearchHit:
    candidate_id: UUID | None
    document_id: UUID
    chunk_id: UUID | None
    confirmed_profile: bool
    retrieval_score: float
    reasons: list[str] = field(default_factory=list)
    evidence: str = ""


def hybrid_search(
    session: Session,
    *,
    query: str | None = None,
    name: str | None = None,
    skill: str | None = None,
    education: str | None = None,
    experience: str | None = None,
    certificate: str | None = None,
    min_years: float | None = None,
    job_title: str | None = None,
    industry: str | None = None,
    nationality: str | None = None,
    embedder=None,
    limit: int = 20,
) -> list[SearchHit]:
    filters = [name, skill, education, experience, certificate, min_years, job_title, industry, nationality]
    text = (query or "").strip()
    if not text and not any(item is not None and item != "" for item in filters):
        return []
    allowed = _confirmed_ids(session)
    if any(item is not None and item != "" for item in filters):
        allowed = _apply_filters(
            session,
            allowed,
            name=name,
            skill=skill,
            education=education,
            experience=experience,
            certificate=certificate,
            min_years=min_years,
            job_title=job_title,
            industry=industry,
            nationality=nationality,
        )
        if not allowed:
            return []
    hits: list[SearchHit] = []
    if not text:
        hits.extend(
            _filter_hits(
                session,
                allowed,
                name,
                skill,
                education,
                experience,
                certificate,
                min_years,
                job_title,
                industry,
                nationality,
            )
        )
    else:
        lexical = _keyword_hits(session, allowed, text)
        hits.extend(lexical)
        if embedder is not None and lexical:
            lexical_chunks = {(hit.document_id, hit.chunk_id) for hit in lexical}
            for hit in semantic_search(session, text, embedder, allowed=allowed):
                if (hit.document_id, hit.chunk_id) in lexical_chunks:
                    hits.append(hit)
    return _merge(hits)[:limit]


def semantic_search(
    session: Session,
    query: str,
    embedder,
    *,
    allowed: set[UUID] | None = None,
) -> list[SearchHit]:
    """Rank eligible chunks by vector distance. Hybrid search uses this only to rerank lexical hits."""
    text = query.strip()
    if not text or embedder is None:
        return []
    pool = _confirmed_ids(session) if allowed is None else allowed
    vector = embedder.embed([text])[0]
    return _semantic_hits(session, pool, vector)


def _confirmed_ids(session: Session) -> set[UUID]:
    rows = session.scalars(
        select(CandidateDocument.candidate_id)
        .join(Candidate, Candidate.id == CandidateDocument.candidate_id)
        .where(
            Candidate.merged_into_id.is_(None),
            CandidateDocument.status.in_(_CONFIRMED),
        )
    )
    return {item for item in rows if item is not None}


def _apply_filters(
    session,
    allowed: set[UUID],
    *,
    name,
    skill,
    education,
    experience,
    certificate,
    min_years,
    job_title,
    industry,
    nationality,
) -> set[UUID]:
    if not allowed:
        return set()
    if name:
        matched = set(
            session.scalars(
                select(Candidate.id).where(
                    Candidate.id.in_(allowed),
                    Candidate.display_name.ilike(_like(name)),
                )
            )
        )
        allowed &= matched
        if not allowed:
            return set()
    if skill:
        matched = set(
            session.scalars(
                select(CandidateSkill.candidate_id).where(
                    CandidateSkill.candidate_id.in_(allowed),
                    or_(
                        CandidateSkill.normalized_name.ilike(_like(skill.casefold())),
                        func.similarity(CandidateSkill.normalized_name, skill.casefold()) > 0.4,
                    ),
                )
            )
        )
        allowed &= matched
        if not allowed:
            return set()
    if education:
        matched = set(
            session.scalars(
                select(CandidateEducation.candidate_id).where(
                    CandidateEducation.candidate_id.in_(allowed),
                    or_(
                        CandidateEducation.institution.ilike(_like(education)),
                        CandidateEducation.credential.ilike(_like(education)),
                    ),
                )
            )
        )
        allowed &= matched
        if not allowed:
            return set()
    if experience:
        matched = set(
            session.scalars(
                select(CandidateExperience.candidate_id).where(
                    CandidateExperience.candidate_id.in_(allowed),
                    or_(
                        CandidateExperience.employer.ilike(_like(experience)),
                        CandidateExperience.title.ilike(_like(experience)),
                    ),
                )
            )
        )
        allowed &= matched
        if not allowed:
            return set()
    if certificate:
        matched = set(
            session.scalars(
                select(CandidateCertificate.candidate_id).where(
                    CandidateCertificate.candidate_id.in_(allowed),
                    CandidateCertificate.name.ilike(_like(certificate)),
                )
            )
        )
        allowed &= matched
        if not allowed:
            return set()
    if min_years is not None:
        matched = set(
            session.scalars(
                select(Candidate.id).where(
                    Candidate.id.in_(allowed),
                    Candidate.years_of_experience >= min_years,
                )
            )
        )
        allowed &= matched
        if not allowed:
            return set()
    if job_title:
        matched = set(
            session.scalars(
                select(CandidateExperience.candidate_id).where(
                    CandidateExperience.candidate_id.in_(allowed),
                    CandidateExperience.title.ilike(_like(job_title)),
                )
            )
        )
        allowed &= matched
        if not allowed:
            return set()
    if industry:
        matched = set(
            session.scalars(
                select(CandidateExperience.candidate_id).where(
                    CandidateExperience.candidate_id.in_(allowed),
                    or_(
                        CandidateExperience.employer.ilike(_like(industry)),
                        CandidateExperience.description.ilike(_like(industry)),
                    ),
                )
            )
        )
        allowed &= matched
        if not allowed:
            return set()
    if nationality:
        matched = set(
            session.scalars(
                select(CandidateDocument.candidate_id)
                .join(DocumentChunk, DocumentChunk.document_id == CandidateDocument.id)
                .where(
                    CandidateDocument.candidate_id.in_(allowed),
                    CandidateDocument.status.in_(_CONFIRMED),
                    DocumentChunk.content.ilike(_like(nationality)),
                )
            )
        )
        allowed &= {item for item in matched if item is not None}
    return allowed


def _filter_hits(
    session,
    allowed,
    name,
    skill,
    education,
    experience,
    certificate,
    min_years,
    job_title,
    industry,
    nationality,
) -> list[SearchHit]:
    hits: list[SearchHit] = []
    documents = session.scalars(
        select(CandidateDocument).where(
            CandidateDocument.candidate_id.in_(allowed),
            CandidateDocument.status.in_(_CONFIRMED),
        )
    )
    seen: set[UUID] = set()
    for document in documents:
        if document.candidate_id in seen or document.candidate_id is None:
            continue
        seen.add(document.candidate_id)
        reason = _filter_reason(
            name, skill, education, experience, certificate, min_years, job_title, industry, nationality
        )
        hits.append(
            SearchHit(
                candidate_id=document.candidate_id,
                document_id=document.id,
                chunk_id=None,
                confirmed_profile=True,
                retrieval_score=1.0,
                reasons=[reason],
                evidence=_filter_evidence(
                    session, document, reason, job_title, industry, nationality
                ),
            )
        )
    return hits


def _keyword_hits(session, allowed: set[UUID], query: str) -> list[SearchHit]:
    if not allowed:
        return []
    rank = func.ts_rank(
        DocumentChunk.search_vector,
        func.plainto_tsquery("simple", query),
    )
    rows = session.execute(
        select(DocumentChunk, CandidateDocument, rank.label("rank"))
        .join(CandidateDocument, CandidateDocument.id == DocumentChunk.document_id)
        .where(
            CandidateDocument.candidate_id.in_(allowed),
            CandidateDocument.status.in_(_CONFIRMED),
            DocumentChunk.search_vector.op("@@")(func.plainto_tsquery("simple", query)),
        )
        .order_by(rank.desc())
        .limit(20)
    )
    hits: list[SearchHit] = []
    for chunk, document, score in rows:
        hits.append(
            SearchHit(
                candidate_id=document.candidate_id,
                document_id=document.id,
                chunk_id=chunk.id,
                confirmed_profile=True,
                retrieval_score=float(score or 0),
                reasons=["keyword"],
                evidence=_snippet(chunk.content, query),
            )
        )
    trigram = session.execute(
        select(DocumentChunk, CandidateDocument, func.similarity(DocumentChunk.content, query).label("score"))
        .join(CandidateDocument, CandidateDocument.id == DocumentChunk.document_id)
        .where(
            CandidateDocument.candidate_id.in_(allowed),
            CandidateDocument.status.in_(_CONFIRMED),
            func.similarity(DocumentChunk.content, query) > 0.2,
        )
        .order_by(func.similarity(DocumentChunk.content, query).desc())
        .limit(20)
    )
    for chunk, document, score in trigram:
        hits.append(
            SearchHit(
                candidate_id=document.candidate_id,
                document_id=document.id,
                chunk_id=chunk.id,
                confirmed_profile=True,
                retrieval_score=float(score or 0),
                reasons=["trigram"],
                evidence=_snippet(chunk.content, query),
            )
        )
    return hits


def _semantic_hits(session, allowed: set[UUID], vector: list[float]) -> list[SearchHit]:
    if not allowed:
        return []
    distance = DocumentChunk.embedding.cosine_distance(vector)
    rows = session.execute(
        select(DocumentChunk, CandidateDocument, distance.label("distance"))
        .join(CandidateDocument, CandidateDocument.id == DocumentChunk.document_id)
        .where(
            CandidateDocument.candidate_id.in_(allowed),
            CandidateDocument.status.in_(_CONFIRMED),
            DocumentChunk.embedding.is_not(None),
        )
        .order_by(distance)
        .limit(20)
    )
    hits: list[SearchHit] = []
    for chunk, document, gap in rows:
        similarity = 1 - float(gap)
        hits.append(
            SearchHit(
                candidate_id=document.candidate_id,
                document_id=document.id,
                chunk_id=chunk.id,
                confirmed_profile=True,
                retrieval_score=similarity,
                reasons=["semantic"],
                evidence=_snippet(chunk.content, ""),
            )
        )
    return hits


def _merge(hits: list[SearchHit]) -> list[SearchHit]:
    grouped: dict[tuple, SearchHit] = {}
    for hit in hits:
        current = grouped.get((hit.candidate_id, hit.document_id, hit.chunk_id))
        if current is None:
            grouped[(hit.candidate_id, hit.document_id, hit.chunk_id)] = hit
            continue
        current.retrieval_score += hit.retrieval_score
        for reason in hit.reasons:
            if reason not in current.reasons:
                current.reasons.append(reason)
        if len(hit.evidence) > len(current.evidence):
            current.evidence = hit.evidence
    ordered = sorted(grouped.values(), key=lambda item: item.retrieval_score, reverse=True)
    for hit in ordered:
        hit.retrieval_score = round(hit.retrieval_score, 4)
    return ordered


def _filter_reason(name, skill, education, experience, certificate, min_years, job_title, industry, nationality) -> str:
    if skill:
        return "skill"
    if name:
        return "name"
    if education:
        return "education"
    if experience:
        return "experience"
    if certificate:
        return "certificate"
    if min_years is not None:
        return "years"
    if job_title:
        return "job_title"
    if industry:
        return "industry"
    if nationality:
        return "nationality"
    return "filter"


def _filter_evidence(session, document, reason, job_title, industry, nationality) -> str:
    if reason == "job_title" and job_title:
        title = session.scalar(
            select(CandidateExperience.title).where(
                CandidateExperience.candidate_id == document.candidate_id,
                CandidateExperience.title.ilike(_like(job_title)),
            )
        )
        return title or reason
    if reason == "industry" and industry:
        text = session.scalar(
            select(CandidateExperience.description).where(
                CandidateExperience.candidate_id == document.candidate_id,
                or_(
                    CandidateExperience.employer.ilike(_like(industry)),
                    CandidateExperience.description.ilike(_like(industry)),
                ),
            )
        )
        if text:
            return _snippet(text, industry)
        employer = session.scalar(
            select(CandidateExperience.employer).where(
                CandidateExperience.candidate_id == document.candidate_id,
                CandidateExperience.employer.ilike(_like(industry)),
            )
        )
        return employer or reason
    if reason == "nationality" and nationality:
        content = session.scalar(
            select(DocumentChunk.content)
            .where(
                DocumentChunk.document_id == document.id,
                DocumentChunk.content.ilike(_like(nationality)),
            )
            .limit(1)
        )
        if content:
            return _snippet(content, nationality)
    return reason


def _like(value: str) -> str:
    cleaned = value.replace("\\", "").replace("%", "").replace("_", "")
    return f"%{cleaned}%"


def _snippet(content: str, query: str) -> str:
    compact = " ".join(content.split())
    if not query:
        return compact[:_SNIPPET]
    folded = compact.casefold()
    at = folded.find(query.casefold())
    if at < 0:
        return compact[:_SNIPPET]
    start = max(0, at - 40)
    return compact[start : start + _SNIPPET]

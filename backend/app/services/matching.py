"""Compare confirmed profiles with explicit requirements. Embeddings cannot clear a mandatory gap."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import Actor
from app.domain.matching import explain, overall_disposition
from app.domain.transitions import transition
from app.extraction.provider import get_embedder
from app.extraction.textutil import sha256_text
from app.models import (
    AgentRun,
    Candidate,
    CandidateCertificate,
    CandidateDocument,
    CandidateEducation,
    CandidateMatch,
    CandidateSkill,
    DocumentChunk,
    ExtractionEvidence,
    MatchRequirementResult,
    RequestRequirement,
)
from app.services.audit import write_audit
from app.services.hiring import HiringError, _recruiter, _request
from app.services.search import hybrid_search

_CONFIRMED = ("extracted", "profiled")
_SNIPPET = 160


def run_match(session: Session, request_id: UUID, actor: Actor, embedder=None) -> list[CandidateMatch]:
    _recruiter(session, actor)
    request = _request(session, request_id)
    if request.status != "open":
        raise HiringError("request_not_open")
    requirements = session.scalars(
        select(RequestRequirement)
        .where(
            RequestRequirement.request_id == request_id,
            RequestRequirement.review_status == "approved",
        )
        .order_by(RequestRequirement.position)
    ).all()
    if not requirements:
        raise HiringError("requirements_not_approved")
    if embedder is None:
        embedder = get_embedder()
    transition(request, "matching", machine="hiring_request", actor=actor)
    candidate_ids = _eligible_candidates(session)
    version = get_settings().processing_version
    run = AgentRun(
        agent_name="candidate_matcher",
        request_id=request.id,
        model="deterministic-requirements",
        prompt_version="match-requirements-v1",
        input_hash=sha256_text(request.description),
        status="succeeded",
        output_ref=f"candidate_count:{len(candidate_ids)}",
    )
    session.add(run)
    session.flush()
    matches: list[CandidateMatch] = []
    for candidate_id in candidate_ids:
        matches.append(
            _match_one(session, request_id, candidate_id, requirements, embedder, version)
        )
    transition(request, "open", machine="hiring_request", actor=actor)
    write_audit(
        session,
        actor=actor,
        action="matching_run",
        entity_type="hiring_request",
        entity_id=request.id,
        detail={"request_id": str(request.id), "count": len(matches), "outcome": "completed"},
        agent_run_id=run.id,
    )
    for match in matches:
        if match.disposition != "recommended":
            continue
        write_audit(
            session,
            actor=actor,
            action="candidate_recommended",
            entity_type="candidate_match",
            entity_id=match.id,
            detail={
                "request_id": str(request.id),
                "candidate_id": str(match.candidate_id),
                "match_id": str(match.id),
                "disposition": "recommended",
            },
            agent_run_id=run.id,
        )
    return matches


def _match_one(session, request_id, candidate_id, requirements, embedder, version) -> CandidateMatch:
    existing = session.scalar(
        select(CandidateMatch).where(
            CandidateMatch.request_id == request_id,
            CandidateMatch.candidate_id == candidate_id,
        )
    )
    match = existing or CandidateMatch(
        request_id=request_id,
        candidate_id=candidate_id,
        disposition="needs_review",
    )
    if existing is None:
        session.add(match)
    session.flush()
    session.execute(delete(MatchRequirementResult).where(MatchRequirementResult.match_id == match.id))
    verdicts: list[tuple[str, str, str]] = []
    pairs: list[tuple[str, str]] = []
    met = 0
    for requirement in requirements:
        verdict = _evaluate(session, candidate_id, requirement, embedder)
        if verdict.result == "meets":
            met += 1
        session.add(
            MatchRequirementResult(
                match_id=match.id,
                requirement_id=requirement.id,
                result=verdict.result,
                evidence_id=verdict.evidence_id,
                evidence_quote=verdict.evidence_quote,
                retrieval=verdict.retrieval,
            )
        )
        verdicts.append((requirement.requirement_text, requirement.strength, verdict.result))
        pairs.append((requirement.strength, verdict.result))
    match.disposition = overall_disposition(pairs)
    match.explanation = explain(verdicts)
    match.processing_version = version
    match.rank_score = round(met / len(requirements), 4) if requirements else None
    session.flush()
    return match


class _Verdict:
    def __init__(self, result: str, evidence_id: UUID | None = None, evidence_quote: str | None = None, retrieval: str | None = None):
        self.result = result
        self.evidence_id = evidence_id
        self.evidence_quote = evidence_quote
        self.retrieval = retrieval


def _evaluate(session, candidate_id, requirement, embedder) -> _Verdict:
    label = requirement.label
    if label == "skill":
        return _skill(session, candidate_id, requirement.requirement_text, embedder)
    if label == "experience":
        return _experience(session, candidate_id, requirement.requirement_text)
    if label == "education":
        return _text_field(
            session,
            candidate_id,
            requirement.requirement_text,
            _education_rows(session, candidate_id),
            "education",
            embedder,
        )
    if label == "certification":
        return _text_field(
            session,
            candidate_id,
            requirement.requirement_text,
            _certificate_rows(session, candidate_id),
            "certificate",
            embedder,
        )
    return _other(session, candidate_id, requirement.requirement_text, embedder)


def _skill(session, candidate_id, text: str, embedder) -> _Verdict:
    needle = text.casefold()
    skills = session.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id)).all()
    for skill in skills:
        if needle == skill.normalized_name or needle in skill.normalized_name.split():
            evidence = _evidence_for(session, candidate_id, "skill", skill.id)
            if evidence is None:
                return _Verdict("unknown")
            return _Verdict("meets", evidence.id, _clip(evidence.source_quote), "skill")
    hit = _hybrid_hit(session, candidate_id, text, embedder)
    if hit is not None:
        return _Verdict("partial", evidence_quote=_clip(hit.evidence), retrieval=_retrieval(hit.reasons))
    if skills:
        return _Verdict("unmet")
    return _Verdict("unknown")


def _experience(session, candidate_id, text: str) -> _Verdict:
    try:
        minimum = float(text)
    except ValueError:
        return _Verdict("unknown")
    candidate = session.get(Candidate, candidate_id)
    evidence = _field_evidence(session, candidate_id, "years_of_experience")
    if candidate is None or candidate.years_of_experience is None or evidence is None:
        return _Verdict("unknown")
    result = "meets" if float(candidate.years_of_experience) >= minimum else "unmet"
    if result == "unmet":
        return _Verdict("unmet", evidence.id, _clip(evidence.source_quote), "years")
    return _Verdict("meets", evidence.id, _clip(evidence.source_quote), "years")


def _text_field(session, candidate_id, text: str, rows, entity_type: str, embedder) -> _Verdict:
    needle = text.casefold()
    for row in rows:
        haystack = " ".join(
            part for part in (getattr(row, "institution", None), getattr(row, "credential", None), getattr(row, "name", None)) if part
        ).casefold()
        if needle in haystack:
            evidence = _evidence_for(session, candidate_id, entity_type, row.id)
            if evidence is None:
                return _Verdict("unknown")
            return _Verdict("meets", evidence.id, _clip(evidence.source_quote), entity_type)
    hit = _hybrid_hit(session, candidate_id, text, embedder)
    if hit is not None:
        return _Verdict("partial", evidence_quote=_clip(hit.evidence), retrieval=_retrieval(hit.reasons))
    if rows:
        return _Verdict("unmet")
    return _Verdict("unknown")


def _other(session, candidate_id, text: str, embedder) -> _Verdict:
    hit = _hybrid_hit(session, candidate_id, text, embedder)
    chunks = _chunks(session, candidate_id)
    if hit is not None:
        return _Verdict("meets", evidence_quote=_clip(hit.evidence), retrieval=_retrieval(hit.reasons))
    if chunks:
        return _Verdict("unmet")
    return _Verdict("unknown")


def _hybrid_hit(session, candidate_id, text: str, embedder):
    hits = hybrid_search(session, query=text, embedder=embedder, limit=50)
    for hit in hits:
        if hit.candidate_id == candidate_id and hit.evidence:
            return hit
    return None


def _eligible_candidates(session) -> list[UUID]:
    rows = session.scalars(
        select(CandidateDocument.candidate_id).where(
            CandidateDocument.candidate_id.is_not(None),
            CandidateDocument.status.in_(_CONFIRMED),
            CandidateDocument.is_current.is_(True),
        )
    ).all()
    return list(dict.fromkeys(item for item in rows if item is not None))


def _chunks(session, candidate_id) -> list[DocumentChunk]:
    return list(
        session.scalars(
            select(DocumentChunk)
            .join(CandidateDocument, CandidateDocument.id == DocumentChunk.document_id)
            .where(
                CandidateDocument.candidate_id == candidate_id,
                CandidateDocument.status.in_(_CONFIRMED),
                CandidateDocument.is_current.is_(True),
            )
        ).all()
    )


def _education_rows(session, candidate_id):
    return list(session.scalars(select(CandidateEducation).where(CandidateEducation.candidate_id == candidate_id)).all())


def _certificate_rows(session, candidate_id):
    return list(
        session.scalars(select(CandidateCertificate).where(CandidateCertificate.candidate_id == candidate_id)).all()
    )


def _evidence_for(session, candidate_id, entity_type: str, entity_id: UUID):
    return session.scalar(
        select(ExtractionEvidence).where(
            ExtractionEvidence.candidate_id == candidate_id,
            ExtractionEvidence.entity_type == entity_type,
            ExtractionEvidence.entity_id == entity_id,
            ExtractionEvidence.quote_verified.is_(True),
        )
    )


def _field_evidence(session, candidate_id, field_name: str):
    return session.scalar(
        select(ExtractionEvidence).where(
            ExtractionEvidence.candidate_id == candidate_id,
            ExtractionEvidence.field_name == field_name,
            ExtractionEvidence.quote_verified.is_(True),
        )
    )


def _retrieval(reasons: list[str]) -> str:
    ordered = [reason for reason in ("keyword", "trigram", "semantic") if reason in reasons]
    return "+".join(ordered)[:32] or "keyword"


def _clip(value: str | None) -> str | None:
    if not value:
        return None
    compact = " ".join(value.split())
    return compact[:_SNIPPET]

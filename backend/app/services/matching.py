"""Compare confirmed profiles with explicit requirements, one candidate and one CV at a time.

Every verdict is read from the candidate's own current CV and verified profile facts. A similarity score or a
corpus-wide search rank never sets a verdict, so it can neither clear a mandatory gap nor cause one."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import Actor
from app.domain.matching import explain, overall_disposition
from app.domain.transitions import transition
from app.extraction.textutil import sha256_text
from app.models import (
    AgentRun,
    Candidate,
    CandidateCertificate,
    CandidateDocument,
    CandidateEducation,
    CandidateMatch,
    CandidateSkill,
    DocumentPage,
    ExtractionEvidence,
    MatchRequirementResult,
    RequestRequirement,
)
from app.services.audit import write_audit
from app.services.hiring import HiringError, _actor_allowed, _request

_CONFIRMED = ("extracted", "profiled")
_SNIPPET = 160


def run_match(
    session: Session, request_id: UUID, actor: Actor, *, provisional: bool = False
) -> list[CandidateMatch]:
    """Match every eligible candidate against the request's requirements.

    By default only HR-approved requirements are used, and the result can become the confirmed pool.
    provisional=True is the automatic first match when a request arrives: it uses the proposed requirements too,
    and the pool it produces stays provisional (see hiring.pool_status) until HR approves and it is rematched.
    """
    _actor_allowed(session, actor)
    request = _request(session, request_id)
    if request.status != "open":
        raise HiringError("request_not_open")
    query = select(RequestRequirement).where(RequestRequirement.request_id == request_id)
    if provisional:
        query = query.where(RequestRequirement.review_status != "rejected")
    else:
        query = query.where(RequestRequirement.review_status == "approved")
    requirements = session.scalars(query.order_by(RequestRequirement.position)).all()
    if not requirements:
        # The confirmed path matches only on requirements a person approved.
        raise HiringError("no_requirements" if provisional else "requirements_not_approved")
    before = _requirement_state(session, request_id)
    retriever = _Retriever(session)
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
            _match_one(session, request_id, candidate_id, requirements, retriever, version)
        )
    transition(request, "open", machine="hiring_request", actor=actor)
    request.last_match_completed_at = datetime.now(timezone.utc)
    # An approval or edit committed while this ran means the pool no longer reflects the requirements.
    # It stays stale (so provisional) and the job that approval queued rematches it.
    request.pool_stale = _requirement_state(session, request_id) != before
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


def _requirement_state(session: Session, request_id: UUID) -> list[tuple]:
    """The committed requirement rows, read fresh from the database (a column query bypasses the identity map)."""
    return sorted(
        session.execute(
            select(
                RequestRequirement.id,
                RequestRequirement.requirement_text,
                RequestRequirement.strength,
                RequestRequirement.label,
                RequestRequirement.review_status,
            ).where(RequestRequirement.request_id == request_id)
        ).all()
    )


def _match_one(session, request_id, candidate_id, requirements, retriever, version) -> CandidateMatch:
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
        verdict = _evaluate(session, candidate_id, requirement, retriever)
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
    # A recruiter's rejection of this candidate for this request is a human decision; a rematch refreshes the
    # verdicts and explanation but never reopens it.
    if match.disposition != "rejected":
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


def _evaluate(session, candidate_id, requirement, retriever) -> _Verdict:
    """One requirement against one candidate's own current CV. Nothing here depends on other candidates: a verdict
    never comes from where this CV ranks in a corpus-wide search."""
    label = requirement.label
    text = requirement.requirement_text
    if label == "experience":
        return _experience(session, candidate_id, text)
    if label == "skill":
        return _skill(session, candidate_id, text, retriever)
    if label == "education":
        return _education(session, candidate_id, text, retriever)
    if label == "certification":
        return _certification(session, candidate_id, text, retriever)
    return _other(candidate_id, text, retriever)


def _absent(retriever, candidate_id) -> _Verdict:
    """Nothing on the CV names the requirement. That is "not met" only when the whole CV was read as text; an OCR
    reading can drop or garble words, and a CV with no readable text says nothing, so both stay unknown."""
    if retriever.readable(candidate_id):
        return _Verdict("unmet")
    return _Verdict("unknown")


def _skill(session, candidate_id, text: str, retriever) -> _Verdict:
    names = _skill_names(text)
    skills = session.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id)).all()
    for skill in skills:
        if names & _skill_names(skill.normalized_name) or text.casefold() in skill.normalized_name.split():
            evidence = _evidence_for(session, candidate_id, "skill", skill.id)
            if evidence is not None:
                return _Verdict("meets", evidence.id, _clip(evidence.source_quote), "skill")
    # The skills list is only what the reader found under a skills heading. A CV that names the skill anywhere else,
    # "Built REST APIs in Python" under experience, still says it, and that line is the evidence. A more specific
    # name counts too: a CV listing PostgreSQL or MySQL has SQL.
    line = retriever.mention(candidate_id, names | _implied_by(names))
    if line is not None:
        return _Verdict("meets", evidence_quote=_clip(line), retrieval="keyword")
    return _absent(retriever, candidate_id)


def _education(session, candidate_id, text: str, retriever) -> _Verdict:
    """A field ("Economics") or a degree level ("Bachelor's degree"). Met by a verified education row, or by a degree
    line on the CV that names it. Named elsewhere (coursework, a minor, a degree still expected) is partial."""
    needle = text.casefold()
    level = _degree_level(needle)
    for row in _education_rows(session, candidate_id):
        haystack = " ".join(part for part in (row.institution, row.credential) if part).casefold()
        if needle in haystack or (level is not None and level.search(haystack)):
            evidence = _evidence_for(session, candidate_id, "education", row.id)
            if evidence is not None and not _EXPECTED.search(evidence.source_quote or ""):
                return _Verdict("meets", evidence.id, _clip(evidence.source_quote), "education")
    pattern = level or _mention_pattern({needle})
    lines = retriever.lines_matching(candidate_id, pattern)
    if not lines:
        return _absent(retriever, candidate_id)
    degree = next((line for line in lines if _DEGREE_LINE.search(line) and not _EXPECTED.search(line)), None)
    if degree is not None:
        return _Verdict("meets", evidence_quote=_clip(degree), retrieval="keyword")
    return _Verdict("partial", evidence_quote=_clip(lines[0]), retrieval="keyword")


def _certification(session, candidate_id, text: str, retriever) -> _Verdict:
    """Met by a verified certificate row. Named elsewhere on the CV ("CFA Institute Research Challenge", "Level I
    candidate") is partial: a person checks whether the certificate is actually held."""
    needle = text.casefold()
    for row in _certificate_rows(session, candidate_id):
        if needle in (row.name or "").casefold():
            evidence = _evidence_for(session, candidate_id, "certificate", row.id)
            if evidence is not None:
                return _Verdict("meets", evidence.id, _clip(evidence.source_quote), "certificate")
    lines = retriever.lines_matching(candidate_id, _mention_pattern(_skill_names(text)))
    if lines:
        return _Verdict("partial", evidence_quote=_clip(lines[0]), retrieval="keyword")
    return _absent(retriever, candidate_id)


def _other(candidate_id, text: str, retriever) -> _Verdict:
    """Free text. Met when a CV line names it as written; partial when one line holds all of its main words."""
    lines = retriever.lines_matching(candidate_id, _mention_pattern({text.casefold()}))
    if lines:
        return _Verdict("meets", evidence_quote=_clip(lines[0]), retrieval="keyword")
    words = [word for word in re.findall(r"[^\W_]{4,}", text.casefold()) if word not in _FILLER]
    if len(words) >= 2:
        patterns = [_mention_pattern({word}) for word in words]
        line = next(
            (line for line in retriever.lines_matching(candidate_id, patterns[0]) if all(p.search(line) for p in patterns[1:])),
            None,
        )
        if line is not None:
            return _Verdict("partial", evidence_quote=_clip(line), retrieval="keyword")
    return _absent(retriever, candidate_id)


_FILLER = frozenset({"with", "experience", "experienced", "knowledge", "ability", "strong", "good", "years", "working", "level"})
_DEGREE_LINE = re.compile(
    r"(?i)\b(?:bachelor|master|doctor|ph\.?\s?d|mba|b\.?\s?a\b|b\.?\s?sc?\b|m\.?\s?sc?\b|m\.?\s?a\b|b\.?\s?eng|m\.?\s?eng|degree|major|diploma)"
)
_EXPECTED = re.compile(r"(?i)\b(?:expected|anticipated|candidate|in progress|pursuing|intended)\b")
_DEGREE_LEVELS = (
    (re.compile(r"(?i)\b(?:phd|ph\.d|doctorate|doctoral)\b"), re.compile(r"(?i)\b(?:ph\.?\s?d|doctor(?:ate|al)?)\b")),
    (
        re.compile(r"(?i)\b(?:master|masters|master's|msc|mba|m\.s|m\.a)\b"),
        re.compile(r"(?i)\b(?:master|mba|m\.?\s?sc?\b|m\.?\s?a\b|m\.?\s?eng)"),
    ),
    (
        re.compile(r"(?i)\b(?:bachelor|bachelors|bachelor's|undergraduate degree|bsc|b\.s|b\.a)\b"),
        re.compile(r"(?i)\b(?:bachelor|b\.?\s?sc?\b|b\.?\s?a\b|b\.?\s?eng|bba)"),
    ),
)


def _degree_level(needle: str) -> re.Pattern | None:
    """A degree-level requirement ("Bachelor's degree") is met by any way a CV writes that level ("B.S.", "BSc")."""
    for asked, written in _DEGREE_LEVELS:
        if asked.search(needle):
            return written
    return None


# Names one skill is written under. Only unambiguous spellings: "go" or "r" alone would match ordinary words.
_SKILL_ALIASES = (
    {"postgres", "postgresql"},
    {"javascript", "js"},
    {"typescript", "ts"},
    {"kubernetes", "k8s"},
    {"node.js", "nodejs", "node"},
    {"react", "react.js", "reactjs"},
    {"html", "html5"},
    {"css", "css3"},
    {"aws", "amazon web services"},
    {"gcp", "google cloud", "google cloud platform"},
    {"golang"},
    {"c#", "csharp"},
    {".net", "dotnet"},
    {"sql server", "mssql", "ms sql"},
    {"scikit-learn", "sklearn"},
    {"financial modeling", "financial modelling"},
)

# A CV naming the specific one has the general one: PostgreSQL is SQL. Never the reverse, and never NoSQL.
_IMPLIES = {
    "sql": {"mysql", "postgresql", "postgres", "t-sql", "tsql", "sqlite", "sql server", "mssql", "pl/sql", "spark sql", "oracle sql"},
}


def _skill_names(text: str) -> set[str]:
    name = " ".join(text.casefold().split())
    for group in _SKILL_ALIASES:
        if name in group:
            return set(group)
    return {name}


def _implied_by(names: set[str]) -> set[str]:
    return {specific for name in names for specific in _IMPLIES.get(name, set())}


def _mention_pattern(names: set[str]) -> re.Pattern:
    alternatives = "|".join(re.escape(name).replace(r"\ ", r"\s+") for name in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alternatives})(?![A-Za-z0-9+#])", re.IGNORECASE)


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
    return _Verdict(result, evidence.id, _clip(evidence.source_quote), "years")


class _Retriever:
    """The current CV's lines for each candidate, read once per matching run."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._lines: dict[UUID, list[str]] = {}
        self._sources: dict[UUID, str | None] = {}

    def _cv_lines(self, candidate_id: UUID) -> list[str]:
        lines = self._lines.get(candidate_id)
        if lines is None:
            rows = self._session.execute(
                select(DocumentPage.original_text, CandidateDocument.text_source)
                .join(CandidateDocument, CandidateDocument.id == DocumentPage.document_id)
                .where(CandidateDocument.candidate_id == candidate_id, CandidateDocument.is_current.is_(True))
                .order_by(DocumentPage.page_number)
            ).all()
            lines = [line.strip() for page, _source in rows for line in page.splitlines() if line.strip()]
            self._lines[candidate_id] = lines
            self._sources[candidate_id] = rows[0][1] if rows else None
        return lines

    def readable(self, candidate_id: UUID) -> bool:
        """The CV was read from its own text layer (PDF, Word), not guessed from an image."""
        return bool(self._cv_lines(candidate_id)) and self._sources.get(candidate_id) != "ocr"

    def mention(self, candidate_id: UUID, names: set[str]) -> str | None:
        """The first CV line naming the skill as a whole word, in any of its spellings."""
        found = self.lines_matching(candidate_id, _mention_pattern(names))
        return found[0] if found else None

    def lines_matching(self, candidate_id: UUID, pattern: re.Pattern) -> list[str]:
        return [line for line in self._cv_lines(candidate_id) if pattern.search(line)]


def _eligible_candidates(session) -> list[UUID]:
    rows = session.scalars(
        select(CandidateDocument.candidate_id).where(
            CandidateDocument.candidate_id.is_not(None),
            CandidateDocument.status.in_(_CONFIRMED),
            CandidateDocument.is_current.is_(True),
        )
    ).all()
    return list(dict.fromkeys(item for item in rows if item is not None))


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


def _clip(value: str | None) -> str | None:
    if not value:
        return None
    compact = " ".join(value.split())
    return compact[:_SNIPPET]

"""Relationship confidence from explainable signals.

The number answers one question: how confident are we that the two CVs belong to the same person?
It is computed here. A model's self-reported confidence is not an input. Filename wording is not an input.

Two steps, kept apart:

1. Identity. Each supporting signal removes a share of the remaining doubt (an exact email 90% of it, an exact
   phone 80%, a name up to 50%, overlapping CV content up to 30%), so independent agreements add up without
   passing 100. A signal that could not be read on both CVs is missing: it is left out and lowers nothing.
   A different email or phone on both CVs is a contradiction and cuts the result.
2. Relationship. Only for a pair that looks like one person: newer dates and changed content say updated CV,
   matching content says duplicate. This picks the label. It never lowers the identity number.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

UPDATED_CV = "updated_cv"
DUPLICATE = "duplicate"
DIFFERENT_CANDIDATE = "different_candidate"

ACCEPT_UPDATE = "accept_update"
RECORD_DUPLICATE = "record_duplicate"
CREATE_SEPARATE_CANDIDATE = "create_separate_candidate"

ALL_ACTIONS = (ACCEPT_UPDATE, RECORD_DUPLICATE, CREATE_SEPARATE_CANDIDATE)

# An identifier that on its own removes at least half the doubt (an exact email or phone with the default weights).
STRONG_IDENTIFIER = 0.5

ACTION_FOR = {
    UPDATED_CV: ACCEPT_UPDATE,
    DUPLICATE: RECORD_DUPLICATE,
    DIFFERENT_CANDIDATE: CREATE_SEPARATE_CANDIDATE,
}

STATUS_FOR = {
    ACCEPT_UPDATE: "accepted_update",
    RECORD_DUPLICATE: "recorded_duplicate",
    CREATE_SEPARATE_CANDIDATE: "created_separate",
}


@dataclass(frozen=True)
class Weights:
    # Identity: the share of the remaining doubt a signal removes when it agrees (0 to 1).
    email: float = 0.90
    phone: float = 0.80
    name: float = 0.50  # times the name similarity, so a name on its own never reaches high confidence
    corroboration: float = 0.30  # times the mean content overlap; overlap supports, low overlap is not against
    # Identity: the share of the result taken away when both CVs carry a different value.
    email_conflict: float = 0.50
    phone_conflict: float = 0.40
    # Relationship only: these choose updated against duplicate and never change the identity number.
    dates: float = 0.40
    explicit_version: float = 0.25
    employment: float = 0.15
    education: float = 0.10
    skills: float = 0.10
    semantic: float = 0.15


@dataclass(frozen=True)
class PairEvidence:
    """One existing candidate compared with one incoming CV."""

    candidate_id: UUID
    email_match: bool | None = None
    phone_match: bool | None = None
    name_similarity: float | None = None
    document_hash_match: bool = False
    incoming_is_newer: bool | None = None
    explicit_version_newer: bool | None = None
    employment_similarity: float | None = None
    education_similarity: float | None = None
    skills_similarity: float | None = None
    semantic_similarity: float | None = None


@dataclass(frozen=True)
class SignalRecord:
    code: str
    weight: float
    state: str
    value: float | None = None
    candidate_id: UUID | None = None


@dataclass(frozen=True)
class Assessment:
    comparable: bool
    relationship: str | None
    confidence: float | None
    recommended_action: str | None
    offered_actions: tuple[str, ...]
    candidate_id: UUID | None
    candidate_ids: tuple[UUID, ...]
    signals: tuple[SignalRecord, ...]
    ambiguous: bool = False
    contradictions: tuple[str, ...] = ()


@dataclass
class _Scored:
    candidate_id: UUID
    relationship: str
    confidence: float
    p_same: float | None
    signals: tuple[SignalRecord, ...]
    contradictions: tuple[str, ...] = ()


def assess(
    pairs: list[PairEvidence],
    *,
    weights: Weights,
    high_confidence: float,
    relationship_cutoff: float = 0.5,
) -> Assessment:
    scored = [
        item
        for item in (_score_pair(pair, weights, relationship_cutoff) for pair in pairs)
        if item.p_same is not None
    ]
    if not scored:
        return Assessment(
            comparable=False,
            relationship=None,
            confidence=None,
            recommended_action=None,
            offered_actions=(),
            candidate_id=None,
            candidate_ids=(),
            signals=(),
        )
    same_person = [item for item in scored if item.p_same is not None and item.p_same >= relationship_cutoff]
    if len(same_person) > 1:
        return _ambiguous(scored, high_confidence)
    best = max(scored, key=lambda item: item.confidence)
    return _present(best, high_confidence, candidate_ids=(best.candidate_id,))


def signal_payload(record: SignalRecord) -> dict:
    payload = {
        "code": record.code,
        "weight": record.weight,
        "state": record.state,
        "value": record.value,
    }
    if record.candidate_id is not None:
        payload["candidate_id"] = str(record.candidate_id)
    return payload


def _present(scored: _Scored, high_confidence: float, *, candidate_ids: tuple[UUID, ...]) -> Assessment:
    action = ACTION_FOR[scored.relationship]
    confidence = round(scored.confidence, 4)
    if scored.relationship == DIFFERENT_CANDIDATE:
        # The number is the same-person confidence, so a confident "different person" is a low one.
        high_enough = round(1.0 - scored.confidence, 4) >= high_confidence
    else:
        # A contradicting email or phone never leaves a single merge or duplicate recommendation.
        high_enough = confidence >= high_confidence and not scored.contradictions
    return Assessment(
        comparable=True,
        relationship=scored.relationship,
        confidence=confidence,
        recommended_action=action if high_enough else None,
        offered_actions=(action,) if high_enough else ALL_ACTIONS,
        candidate_id=scored.candidate_id if len(candidate_ids) == 1 else None,
        candidate_ids=candidate_ids,
        signals=scored.signals,
        contradictions=scored.contradictions,
    )


def _ambiguous(scored: list[_Scored], high_confidence: float) -> Assessment:
    best = max(scored, key=lambda item: (item.p_same or 0.0, item.confidence))
    # Two existing people both look related. That cannot be one high-confidence recommendation.
    cap = max(0.0, high_confidence - 0.01)
    confidence = min(best.confidence, cap)
    ids = tuple(item.candidate_id for item in scored)
    signals = tuple(signal for item in scored for signal in item.signals)
    return Assessment(
        comparable=True,
        relationship=best.relationship,
        confidence=round(confidence, 4),
        recommended_action=None,
        offered_actions=ALL_ACTIONS,
        candidate_id=None,
        candidate_ids=ids,
        signals=signals,
        ambiguous=True,
    )


def _score_pair(pair: PairEvidence, weights: Weights, relationship_cutoff: float) -> _Scored:
    signals: list[SignalRecord] = []
    identity: list[tuple[float, float]] = []
    # A contradiction is recorded with the weight it actually carries, which is its conflict strength.
    email_weight = weights.email_conflict if pair.email_match is False else weights.email
    phone_weight = weights.phone_conflict if pair.phone_match is False else weights.phone
    _flag(signals, identity, pair.candidate_id, "email", email_weight, pair.email_match)
    _flag(signals, identity, pair.candidate_id, "phone", phone_weight, pair.phone_match)
    _unit(signals, identity, pair.candidate_id, "name", weights.name, pair.name_similarity)
    # Identical bytes are the same document at ingest. A different hash does not choose a relationship.
    signals.append(
        SignalRecord(
            code="document_hash",
            weight=0.0,
            state="matched" if pair.document_hash_match else "unmatched",
            value=1.0 if pair.document_hash_match else 0.0,
            candidate_id=pair.candidate_id,
        )
    )

    recency: list[tuple[float, float]] = []
    _flag(signals, recency, pair.candidate_id, "cv_dates", weights.dates, pair.incoming_is_newer)
    _flag(
        signals,
        recency,
        pair.candidate_id,
        "explicit_version",
        weights.explicit_version,
        pair.explicit_version_newer,
    )

    content: list[tuple[float, float]] = []
    _unit(signals, content, pair.candidate_id, "employment", weights.employment, pair.employment_similarity)
    _unit(signals, content, pair.candidate_id, "education", weights.education, pair.education_similarity)
    _unit(signals, content, pair.candidate_id, "skills", weights.skills, pair.skills_similarity)
    _unit(signals, content, pair.candidate_id, "semantic", weights.semantic, pair.semantic_similarity)

    # Without an email, phone or name on both CVs there is nothing that says who the person is.
    if not identity:
        return _Scored(pair.candidate_id, DIFFERENT_CANDIDATE, 0.0, None, tuple(signals))

    # These strengths are a starting point for the evaluation set, not a validated model.
    p_same, contradictions = _same_person(pair, weights, content)
    # An exact email or phone in common, with the other one different, is conflicting evidence: people change email
    # addresses. That pair is never labelled a different person. It keeps its lowered number, and the contradiction
    # already rules out any recommendation, so HR decides with both facts in front of them.
    conflicting = bool(contradictions) and (
        (pair.email_match is True and weights.email >= STRONG_IDENTIFIER)
        or (pair.phone_match is True and weights.phone >= STRONG_IDENTIFIER)
    )
    if p_same < relationship_cutoff and not conflicting:
        relationship = DIFFERENT_CANDIDATE
    elif pair.document_hash_match:
        relationship = DUPLICATE
    elif _update_probability(recency, content) >= relationship_cutoff:
        relationship = UPDATED_CV
    else:
        relationship = DUPLICATE
    # The score is the same-person confidence. Whether it is an update or a duplicate only picks the label.
    return _Scored(pair.candidate_id, relationship, p_same, p_same, tuple(signals), contradictions)


def _same_person(
    pair: PairEvidence, weights: Weights, content: list[tuple[float, float]]
) -> tuple[float, tuple[str, ...]]:
    """Each agreeing signal removes its share of the remaining doubt; each contradiction cuts the result.

    Missing evidence is left out. It is not counted for or against. Low content overlap is not against either:
    an updated CV is expected to differ.
    """
    support: list[float] = []
    against: list[float] = []
    contradictions: list[str] = []
    for code, match, strength, conflict in (
        ("email", pair.email_match, weights.email, weights.email_conflict),
        ("phone", pair.phone_match, weights.phone, weights.phone_conflict),
    ):
        if match is True:
            support.append(strength)
        elif match is False:
            against.append(conflict)
            contradictions.append(code)
    if pair.name_similarity is not None:
        support.append(weights.name * _fraction(pair.name_similarity))
    overlap = 1.0 if pair.document_hash_match else _mean(content)
    if overlap is not None:
        support.append(weights.corroboration * overlap)
    doubt = 1.0
    for strength in support:
        doubt *= 1.0 - _fraction(strength)
    kept = 1.0
    for strength in against:
        kept *= 1.0 - _fraction(strength)
    return (1.0 - doubt) * kept, tuple(contradictions)


def _fraction(value: float) -> float:
    return min(1.0, max(0.0, value))


def _update_probability(recency: list[tuple[float, float]], content: list[tuple[float, float]]) -> float:
    """Updated against duplicate, for a pair already judged to be one person. Nothing known is an even 0.5."""
    recency_mean = _mean(recency)
    content_mean = _mean(content)
    if recency_mean is None and content_mean is None:
        return 0.5
    if recency_mean is None:
        return 1.0 - content_mean
    if content_mean is None:
        return recency_mean
    return (0.7 * recency_mean) + (0.3 * (1.0 - content_mean))


def _mean(parts: list[tuple[float, float]]) -> float | None:
    total = sum(weight for weight, _value in parts if weight > 0)
    if total <= 0:
        return None
    return sum(weight * value for weight, value in parts if weight > 0) / total


def _flag(signals, bucket, candidate_id: UUID, code: str, weight: float, value: bool | None) -> None:
    if value is None:
        signals.append(SignalRecord(code=code, weight=weight, state="unknown", candidate_id=candidate_id))
        return
    numeric = 1.0 if value else 0.0
    signals.append(
        SignalRecord(
            code=code,
            weight=weight,
            state="matched" if value else "unmatched",
            value=numeric,
            candidate_id=candidate_id,
        )
    )
    bucket.append((weight, numeric))


def _unit(signals, bucket, candidate_id: UUID, code: str, weight: float, value: float | None) -> None:
    if value is None:
        signals.append(SignalRecord(code=code, weight=weight, state="unknown", candidate_id=candidate_id))
        return
    bounded = min(1.0, max(0.0, value))
    signals.append(
        SignalRecord(code=code, weight=weight, state="recorded", value=bounded, candidate_id=candidate_id)
    )
    bucket.append((weight, bounded))

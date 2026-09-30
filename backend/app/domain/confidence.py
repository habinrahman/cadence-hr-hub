"""Relationship confidence from explainable signals.

The number is computed here. A model's self-reported confidence is not an input.
Filename wording is not an input. An unknown signal is left out of the average;
it is not treated as zero.
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
    email: float = 0.50
    phone: float = 0.30
    name: float = 0.20
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


@dataclass
class _Scored:
    candidate_id: UUID
    relationship: str
    confidence: float
    p_same: float | None
    signals: tuple[SignalRecord, ...]


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
    high_enough = scored.confidence >= high_confidence
    return Assessment(
        comparable=True,
        relationship=scored.relationship,
        confidence=round(scored.confidence, 4),
        recommended_action=action if high_enough else None,
        offered_actions=(action,) if high_enough else ALL_ACTIONS,
        candidate_id=scored.candidate_id if len(candidate_ids) == 1 else None,
        candidate_ids=candidate_ids,
        signals=scored.signals,
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
    _flag(signals, identity, pair.candidate_id, "email", weights.email, pair.email_match)
    _flag(signals, identity, pair.candidate_id, "phone", weights.phone, pair.phone_match)
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

    p_same = _mean(identity)
    if p_same is None:
        return _Scored(pair.candidate_id, DIFFERENT_CANDIDATE, 0.0, None, tuple(signals))

    # An exact contact on a different file is strong identity evidence. Unknown dates
    # stay out of the average; they do not cut that evidence in half. These weights
    # are a starting point for the evaluation set, not a validated model.
    exact_contact = pair.email_match is True or pair.phone_match is True
    contrary_contact = pair.email_match is False or pair.phone_match is False
    if (
        p_same >= relationship_cutoff
        and exact_contact
        and not contrary_contact
        and not recency
        and not content
    ):
        return _Scored(pair.candidate_id, UPDATED_CV, p_same, p_same, tuple(signals))

    p_update = _update_probability(recency, content)
    if p_same >= relationship_cutoff:
        if p_update >= relationship_cutoff:
            relationship = UPDATED_CV
            confidence = p_same * p_update
        else:
            relationship = DUPLICATE
            confidence = p_same * (1.0 - p_update)
    else:
        relationship = DIFFERENT_CANDIDATE
        confidence = 1.0 - p_same
    return _Scored(pair.candidate_id, relationship, confidence, p_same, tuple(signals))


def _update_probability(recency: list[tuple[float, float]], content: list[tuple[float, float]]) -> float:
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

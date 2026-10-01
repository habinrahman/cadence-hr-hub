"""The relationship score answers one question: are these two CVs the same person?

Missing evidence is not evidence against. A different email or phone is. Whether the pair is an update or a
duplicate picks the label and never lowers the score. Nothing is applied until a recruiter decides.
"""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import get_settings
from app.domain.confidence import (
    ACCEPT_UPDATE,
    ALL_ACTIONS,
    RECORD_DUPLICATE,
    PairEvidence,
    Weights,
    assess,
)
from app.main import app
from app.models import AuditEvent, CandidateDocument, DuplicateReview
from tests.test_foundation import BODY, RECRUITER, _actor
from tests.test_relationship_actions import _ingest


def _assess(**fields):
    settings = get_settings()
    return assess(
        [PairEvidence(candidate_id=uuid4(), **fields)],
        weights=Weights(),
        high_confidence=settings.identity_high_confidence,
        relationship_cutoff=settings.identity_relationship_cutoff,
    )


SAME_PERSON = dict(email_match=True, phone_match=True, name_similarity=1.0)


def test_exact_email_phone_and_name_score_near_certain_without_other_sections():
    result = _assess(**SAME_PERSON)
    assert 0.98 <= result.confidence <= 1.0
    assert result.relationship == "updated_cv"
    assert result.recommended_action == ACCEPT_UPDATE
    assert result.offered_actions == (ACCEPT_UPDATE,)
    unknown = {item.code for item in result.signals if item.state == "unknown"}
    assert {"cv_dates", "explicit_version", "employment", "education", "skills", "semantic"} <= unknown


def test_exact_email_and_phone_stay_high_whatever_the_content_says():
    changed = _assess(email_match=True, phone_match=True, employment_similarity=0.1, skills_similarity=0.2)
    same = _assess(email_match=True, phone_match=True, incoming_is_newer=False, employment_similarity=1.0, skills_similarity=1.0)
    assert changed.confidence >= 0.98
    assert same.confidence >= 0.98
    # Content picks the label only.
    assert changed.relationship == "updated_cv"
    assert same.relationship == "duplicate"


def test_same_name_alone_is_not_high_confidence():
    exact = _assess(name_similarity=1.0)
    similar = _assess(name_similarity=0.67)
    assert exact.confidence <= 0.5
    assert similar.confidence < 0.5
    for result in (exact, similar):
        assert result.recommended_action is None
        assert result.offered_actions == ALL_ACTIONS


def test_exact_email_alone_is_strong_but_not_maximum():
    alone = _assess(email_match=True)
    with_name = _assess(email_match=True, name_similarity=1.0)
    full = _assess(**SAME_PERSON)
    assert 0.85 <= alone.confidence < with_name.confidence < full.confidence
    assert alone.relationship == "updated_cv"
    assert alone.recommended_action is None  # not corroborated, so HR chooses with no suggestion


def test_exact_phone_alone_is_strong_but_below_email():
    alone = _assess(phone_match=True)
    with_name = _assess(phone_match=True, name_similarity=1.0)
    assert 0.75 <= alone.confidence < _assess(email_match=True).confidence
    assert alone.confidence < with_name.confidence < _assess(**SAME_PERSON).confidence
    assert alone.recommended_action is None


def test_a_different_email_is_a_recorded_contradiction():
    result = _assess(email_match=False, name_similarity=1.0)
    assert result.contradictions == ("email",)
    assert result.confidence < 0.5
    assert result.relationship == "different_candidate"
    assert result.recommended_action != ACCEPT_UPDATE
    email = next(item for item in result.signals if item.code == "email")
    assert email.state == "unmatched"
    assert email.weight == Weights().email_conflict  # shown with the weight it actually carries
    # Even with a matching email, a different phone blocks a single recommendation at any threshold.
    mixed = assess(
        [PairEvidence(candidate_id=uuid4(), email_match=True, phone_match=False, name_similarity=1.0)],
        weights=Weights(),
        high_confidence=0.5,
    )
    assert mixed.contradictions == ("phone",)
    assert mixed.recommended_action is None
    assert mixed.confidence < _assess(email_match=True, name_similarity=1.0).confidence


def test_same_phone_and_name_with_a_different_email_is_conflicting_not_a_different_person():
    """Real corpus case (AhmedYM_resume.pdf): one phone number and the same full name, a new email address.
    It was labelled "Likely a different person". It is conflicting evidence: lowered, never recommended, never 'different'."""
    result = _assess(email_match=False, phone_match=True, name_similarity=1.0)
    assert result.contradictions == ("email",)
    assert result.relationship in {"updated_cv", "duplicate"}
    assert result.recommended_action is None
    assert result.offered_actions == ALL_ACTIONS
    assert result.confidence < _assess(phone_match=True, name_similarity=1.0).confidence
    # Both contacts different stays a different person.
    assert _assess(email_match=False, phone_match=False, name_similarity=1.0).relationship == "different_candidate"


def test_unavailable_sections_do_not_lower_identity():
    bare = _assess(**SAME_PERSON)
    unreadable = _assess(**SAME_PERSON, employment_similarity=None, education_similarity=None, semantic_similarity=None)
    assert unreadable.confidence == bare.confidence
    # Content that differs is an update, not evidence of another person.
    differing = _assess(**SAME_PERSON, employment_similarity=0.0, education_similarity=0.0)
    assert differing.confidence >= bare.confidence


def test_near_identical_copy_is_a_duplicate():
    result = _assess(
        **SAME_PERSON,
        incoming_is_newer=False,
        employment_similarity=1.0,
        education_similarity=1.0,
        skills_similarity=1.0,
        semantic_similarity=0.99,
    )
    assert result.confidence >= 0.98
    assert result.relationship == "duplicate"
    assert result.recommended_action == RECORD_DUPLICATE
    identical = _assess(email_match=True, phone_match=True, document_hash_match=True)
    assert identical.relationship == "duplicate"


def test_newer_cv_with_new_content_is_an_update():
    result = _assess(
        **SAME_PERSON,
        incoming_is_newer=True,
        employment_similarity=0.6,
        education_similarity=0.5,
        skills_similarity=0.4,
    )
    assert result.confidence >= 0.98
    assert result.relationship == "updated_cv"
    assert result.recommended_action == ACCEPT_UPDATE


def test_high_confidence_still_waits_for_a_recruiter(session):
    actor = _actor(session)
    original = _ingest(session, actor, "a.pdf", BODY)
    incoming = _ingest(session, actor, "b.pdf", BODY.replace("Analytical engines", "Different analytical engines"))
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == incoming.id))
    assert float(review.confidence) >= 98
    assert review.recommended_action == "accept_update"
    # The score applied nothing: no merge, no deletion.
    assert review.status == "pending"
    assert incoming.candidate_id is None
    assert incoming.status == "needs_review"
    assert original.is_current is True
    decided = select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "duplicate_review_decided")
    assert session.scalar(decided) == 0
    with TestClient(app) as client:
        first = client.post(f"/reviews/{review.id}/decision", json={"action": "accept_update"}, headers=RECRUITER)
        assert first.status_code == 200
        again = client.post(f"/reviews/{review.id}/decision", json={"action": "record_duplicate"}, headers=RECRUITER)
        assert again.status_code == 409
    session.expire_all()
    assert session.scalar(decided) == 1
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "duplicate_review_decided"))
    assert event.detail["human_action"] == "accept_update"
    assert event.detail["recommended_action"] == "accept_update"
    assert event.detail["confidence"] >= 98
    # The previous CV stays as history.
    previous = session.get(CandidateDocument, original.id)
    assert previous.is_current is False
    assert previous.candidate_id == session.get(CandidateDocument, incoming.id).candidate_id


# ---------- one number written two ways is not a contradiction ----------

from app.domain.identity import phones_match  # noqa: E402
from app.jobs.rescore_reviews import rescore_pending_reviews  # noqa: E402


def test_national_and_international_forms_of_one_number_match():
    assert phones_match("972524449121", "0524449121")  # +972 52 444 9121 and 052 444 9121
    assert phones_match("15105707106", "5105707106")  # +1 510 570 7106 and (510) 570 7106
    assert phones_match("00972524449121", "972524449121")
    assert not phones_match("972524449121", "972524449122")
    assert not phones_match("1234567", "01234567")  # too short to trust
    assert not phones_match("44155550199", "4155550199999")


def test_a_cv_with_the_local_form_of_the_same_phone_is_not_a_contradiction(session):
    actor = _actor(session)
    _ingest(session, actor, "a.pdf", BODY)  # +14155550199
    local = BODY.replace("+14155550199", "(415) 555-0199").replace("Analytical engines", "Different analytical engines")
    incoming = _ingest(session, actor, "b.pdf", local)
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == incoming.id))
    phone = next(item for item in review.signals["evidence"] if item["code"] == "phone")
    assert phone["state"] == "matched"
    assert float(review.confidence) >= 98
    assert review.recommended_action == "accept_update"


def test_rescore_updates_pending_reviews_only_and_audits_it(session):
    actor = _actor(session)
    _ingest(session, actor, "a.pdf", BODY)
    pending = _ingest(session, actor, "b.pdf", BODY.replace("Analytical engines", "Different analytical engines"))
    decided_doc = _ingest(session, actor, "c.pdf", BODY.replace("Analytical engines", "Other analytical engines"))
    pending_review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == pending.id))
    decided_review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == decided_doc.id))
    # Make both look like they were scored by the old rules.
    for review in (pending_review, decided_review):
        review.confidence = 53
        review.recommended_action = None
        review.offered_actions = list(ALL_ACTIONS)
    decided_review.status = "created_separate"
    session.commit()

    changed = rescore_pending_reviews(session)
    session.commit()
    session.expire_all()
    assert [review_id for review_id, _old, _new in changed] == [pending_review.id]
    pending_review = session.get(DuplicateReview, pending_review.id)
    assert float(pending_review.confidence) >= 98
    assert pending_review.recommended_action == "accept_update"
    assert pending_review.status == "pending"  # re-scoring decides nothing
    assert session.get(CandidateDocument, pending.id).candidate_id is None
    assert float(session.get(DuplicateReview, decided_review.id).confidence) == 53
    audited = select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "duplicate_review_rescored")
    assert session.scalar(audited) == 1
    assert rescore_pending_reviews(session) == []  # running it again changes nothing

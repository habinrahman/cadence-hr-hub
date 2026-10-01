"""The relationship review: a recruiter decides Merge & Update Profile, Delete Duplicate or Create New Candidate.

Nothing is applied by the recommendation. Delete Duplicate archives only the duplicate upload.
"""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.domain.actor import AGENT, SYSTEM, Actor
from app.domain.confidence import PairEvidence, Weights, assess
from app.domain.transitions import TransitionError
from app.jobs.queue import run_once
from app.main import app
from app.models import (
    Application,
    AuditEvent,
    Candidate,
    CandidateContact,
    CandidateDocument,
    DuplicateReview,
)
from app.services.ingest import ingest_bytes
from app.services.pipeline import run_extract
from app.services.reviews import _archive_duplicate, decide_duplicate_review
from tests.test_foundation import BODY, ENGINEER, RECRUITER, _actor, make_pdf

UPDATED = BODY.replace("Analytical engines", "Different analytical engines")
PII = ("ada@example.com", "+14155550199", "14155550199", "Analytical engines")


def _ingest(session, actor, name: str, text: str) -> CandidateDocument:
    result = ingest_bytes(session, filename=name, data=make_pdf(text), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    session.expire_all()
    return session.get(CandidateDocument, result.document.id)


def _pending_update(session):
    """An existing candidate with a current CV, and a second CV for the same email waiting for a recruiter."""
    actor = _actor(session)
    original = _ingest(session, actor, "a.pdf", BODY)
    incoming = _ingest(session, actor, "b.pdf", UPDATED)
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == incoming.id))
    return actor, original, incoming, review


def _decided_events(session):
    return list(session.scalars(select(AuditEvent).where(AuditEvent.action == "duplicate_review_decided")))


def test_updated_cv_is_recommended_but_nothing_merges_until_a_recruiter_acts(session):
    _actor_row, original, incoming, review = _pending_update(session)
    assert review.status == "pending"
    assert review.likely_relationship == "updated_cv"
    assert review.recommended_action == "accept_update"
    # The recommendation applied nothing.
    assert incoming.candidate_id is None
    assert incoming.is_current is False
    assert original.is_current is True
    assert _decided_events(session) == []


def test_merge_and_update_profile_keeps_history_applications_and_audit(session):
    actor, original, incoming, review = _pending_update(session)
    candidate_id = original.candidate_id
    applications_before = session.scalar(select(func.count()).select_from(Application).where(Application.candidate_id == candidate_id))
    decide_duplicate_review(session, review, "accept_update", actor)
    session.commit()
    session.expire_all()
    incoming, original = session.get(CandidateDocument, incoming.id), session.get(CandidateDocument, original.id)
    assert incoming.candidate_id == candidate_id
    assert incoming.is_current is True
    assert incoming.supersedes_document_id == original.id
    # The previous CV is still there, still on the candidate, no longer current.
    assert original.candidate_id == candidate_id
    assert original.is_current is False
    assert original.status != "archived"
    applications_after = session.scalar(select(func.count()).select_from(Application).where(Application.candidate_id == candidate_id))
    assert applications_after == applications_before + 1
    assert session.scalar(select(func.count()).select_from(Candidate)) == 1
    event = _decided_events(session)[0]
    assert event.actor_kind == "user"
    assert event.detail["human_action"] == "accept_update"
    assert event.detail["document_id"] == str(incoming.id)
    assert event.detail["candidate_id"] == str(candidate_id)


def test_delete_duplicate_archives_only_the_duplicate_document(session):
    actor, original, incoming, review = _pending_update(session)
    review.likely_relationship = "duplicate"  # what assess() produces for a duplicate; see the pure test below
    review.recommended_action = "record_duplicate"
    session.commit()
    candidate_id = original.candidate_id
    documents_before = session.scalar(select(func.count()).select_from(CandidateDocument))
    applications_before = session.scalar(select(func.count()).select_from(Application))
    contacts_before = session.scalar(select(func.count()).select_from(CandidateContact))

    decide_duplicate_review(session, review, "record_duplicate", actor)
    session.commit()
    session.expire_all()
    incoming, original = session.get(CandidateDocument, incoming.id), session.get(CandidateDocument, original.id)

    assert review.status == "recorded_duplicate"
    # The duplicate is archived, never current, and not attached to the candidate.
    assert incoming.status == "archived"
    assert incoming.is_current is False
    assert incoming.candidate_id is None
    # The candidate and the canonical CV are untouched.
    assert session.get(Candidate, candidate_id) is not None
    assert original.status in {"profiled", "extracted"}
    assert original.is_current is True
    assert original.candidate_id == candidate_id
    # Nothing was removed and nothing was added for the duplicate: the row is kept under the retention model.
    assert session.scalar(select(func.count()).select_from(CandidateDocument)) == documents_before
    assert session.scalar(select(func.count()).select_from(Application)) == applications_before
    assert session.scalar(select(func.count()).select_from(CandidateContact)) == contacts_before

    event = _decided_events(session)[0]
    assert event.actor_kind == "user"
    assert event.detail["human_action"] == "record_duplicate"
    assert event.detail["recommended_action"] == "record_duplicate"
    assert event.detail["outcome"] == "archived"
    assert event.detail["document_id"] == str(incoming.id)
    assert event.detail["canonical_document_id"] == str(original.id)
    assert event.detail["candidate_id"] == str(candidate_id)


def test_a_document_a_candidate_relies_on_can_never_be_archived_as_a_duplicate(session):
    actor, original, _incoming, _review = _pending_update(session)
    target = session.get(Candidate, original.candidate_id)
    with pytest.raises(TransitionError) as raised:
        _archive_duplicate(session, original, target, actor)
    assert raised.value.code == "invalid_transition"
    assert original.status != "archived"


def test_create_new_candidate_keeps_the_document_on_the_new_profile(session):
    actor, original, incoming, review = _pending_update(session)
    existing_id = original.candidate_id
    decide_duplicate_review(session, review, "create_separate_candidate", actor)
    session.commit()
    session.expire_all()
    incoming, original = session.get(CandidateDocument, incoming.id), session.get(CandidateDocument, original.id)
    assert incoming.candidate_id is not None
    assert incoming.candidate_id != existing_id
    assert incoming.is_current is True
    assert original.candidate_id == existing_id
    assert original.is_current is True
    assert session.scalar(select(func.count()).select_from(Candidate)) == 2
    assert _decided_events(session)[0].detail["human_action"] == "create_separate_candidate"


def test_engineer_and_system_cannot_decide(session):
    actor, original, incoming, review = _pending_update(session)
    with TestClient(app) as client:
        for action in ("accept_update", "record_duplicate", "create_separate_candidate"):
            denied = client.post(f"/reviews/{review.id}/decision", json={"action": action}, headers=ENGINEER)
            assert denied.status_code == 403
    for machine_actor in (SYSTEM, AGENT, Actor(kind="agent")):
        for action in ("accept_update", "record_duplicate", "create_separate_candidate"):
            with pytest.raises(TransitionError) as raised:
                decide_duplicate_review(session, review, action, machine_actor)
            assert raised.value.code == "human_required"
    session.rollback()
    session.expire_all()
    review = session.get(DuplicateReview, review.id)
    assert review.status == "pending"
    assert session.get(CandidateDocument, incoming.id).candidate_id is None
    assert session.get(CandidateDocument, original.id).is_current is True
    assert _decided_events(session) == []


def test_a_recruiter_can_decide_through_the_api(session):
    actor, original, incoming, review = _pending_update(session)
    with TestClient(app) as client:
        response = client.post(f"/reviews/{review.id}/decision", json={"action": "accept_update"}, headers=RECRUITER)
        assert response.status_code == 200
        again = client.post(f"/reviews/{review.id}/decision", json={"action": "record_duplicate"}, headers=RECRUITER)
        assert again.status_code == 409  # a decided review cannot be decided a second time
    session.expire_all()
    assert session.get(DuplicateReview, review.id).status == "accepted_update"
    assert session.get(CandidateDocument, incoming.id).is_current is True


def test_ambiguous_relationship_stays_pending_and_changes_nothing(session):
    actor = _actor(session)
    first = Candidate(source="upload", display_name="Ada Lovelace")
    second = Candidate(source="upload", display_name="Grace Hopper")
    session.add_all([first, second])
    session.flush()
    session.add(CandidateContact(candidate_id=first.id, kind="email", value_raw="ada@example.com", value_normalized="ada@example.com"))
    session.add(CandidateContact(candidate_id=second.id, kind="phone", value_raw="+14155550199", value_normalized="14155550199"))
    session.commit()
    mixed = "Pat Example\nada@example.com\n+14155550199\n" + ("Careful public notes about engines. " * 4)
    incoming = _ingest(session, actor, "mixed.pdf", mixed)
    review = session.scalar(select(DuplicateReview))
    assert review.status == "pending"
    assert review.recommended_action is None
    assert incoming.identity_outcome == "ambiguous"
    assert incoming.candidate_id is None
    assert incoming.status != "archived"
    assert session.scalar(select(func.count()).select_from(Candidate)) == 2
    assert _decided_events(session) == []


def test_a_filename_saying_updated_is_not_identity_evidence(session):
    actor = _actor(session)
    first = _ingest(session, actor, "a.pdf", BODY)
    other = (
        "Grace Hopper\ngrace@example.com\n+14155550123\n"
        + ("Compilers and careful engineering practice across many years. " * 4)
    )
    second = _ingest(session, actor, "Ada Lovelace - UPDATED CV FINAL v2.pdf", other)
    assert session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == second.id)) is None
    assert second.candidate_id is not None
    assert second.candidate_id != first.candidate_id
    assert session.get(CandidateDocument, first.id).is_current is True


def test_audit_details_carry_ids_and_safe_metadata_only(session):
    actor, original, incoming, review = _pending_update(session)
    decide_duplicate_review(session, review, "record_duplicate", actor)
    session.commit()
    for event in session.scalars(select(AuditEvent)):
        blob = json.dumps(event.detail or {})
        for secret in PII:
            assert secret not in blob, (event.action, secret)
    decided = _decided_events(session)[0]
    assert set(decided.detail) <= {
        "human_action",
        "recommended_action",
        "relationship",
        "confidence",
        "document_id",
        "candidate_id",
        "outcome",
        "canonical_document_id",
    }


def test_audit_still_rejects_pii_keys(session):
    from app.services.audit import AuditPayloadError, write_audit

    with pytest.raises(AuditPayloadError):
        write_audit(session, actor=SYSTEM, action="x", entity_type="demo", entity_id=uuid4(), detail={"email": "ada@example.com"})


def test_confidence_logic_recommends_delete_duplicate_for_the_same_person_without_newer_evidence():
    weights = Weights()
    same = PairEvidence(
        candidate_id=uuid4(),
        email_match=True,
        phone_match=True,
        name_similarity=1.0,
        incoming_is_newer=False,
        employment_similarity=1.0,
        education_similarity=1.0,
        skills_similarity=1.0,
    )
    result = assess([same], weights=weights, high_confidence=0.85)
    assert result.relationship == "duplicate"
    assert result.recommended_action == "record_duplicate"
    updated = assess([PairEvidence(candidate_id=uuid4(), email_match=True)], weights=weights, high_confidence=0.85)
    assert updated.relationship == "updated_cv"
    assert updated.recommended_action == "accept_update"
    different = assess([PairEvidence(candidate_id=uuid4(), email_match=False, phone_match=False, name_similarity=0.1)], weights=weights, high_confidence=0.85)
    assert different.relationship == "different_candidate"
    assert different.recommended_action == "create_separate_candidate"


def test_approved_update_adds_the_new_cv_facts_to_the_one_profile(session, monkeypatch):
    from app.extraction.deterministic import DeterministicExtractor
    from app.models import CandidateSkill, ExtractionEvidence

    monkeypatch.setattr("app.services.pipeline.get_extractor", lambda *a, **k: DeterministicExtractor())
    actor = _actor(session)
    first = _ingest(session, actor, "a.pdf", BODY + "\nSkills: Python, Ledger\n")
    candidate_id = first.candidate_id
    second = _ingest(session, actor, "b.pdf", BODY + "\nSkills: Python, Kubernetes\n")
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == second.id))
    names = lambda: sorted(session.scalars(select(CandidateSkill.name).where(CandidateSkill.candidate_id == candidate_id)))
    # Waiting for the decision: nothing from the new CV is in the profile yet.
    assert review.status == "pending"
    assert "Kubernetes" not in names()
    decide_duplicate_review(session, review, "accept_update", actor)
    session.commit()
    # After it: one profile, the new fact is there once, the old facts are not duplicated, and it cites the new CV.
    assert names() == ["Kubernetes", "Ledger", "Python"]
    cited = session.scalar(
        select(func.count()).select_from(ExtractionEvidence).where(
            ExtractionEvidence.document_id == second.id,
            ExtractionEvidence.candidate_id == candidate_id,
            ExtractionEvidence.entity_type == "skill",
        )
    )
    assert cited == 1
    assert session.scalar(select(func.count()).select_from(Candidate)) == 1

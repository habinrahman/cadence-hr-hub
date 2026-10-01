"""Automatic processing: the worker extracts proposed requirements and matches on them at once, giving a provisional
pool that HR can view but not shortlist or share. HR approval queues an approved-only rematch that confirms the pool."""

from datetime import datetime, timezone

from app.models import HiringRequest
from app.services.hiring import create_request
from tests.test_corpus_gates import _actor

JD = "Required skills: Python\nPreferred skills: AWS\n"


def _new(session, actor, **extra):
    row = create_request(
        session,
        company_name="Acme Corp",
        job_title="Senior Backend Engineer",
        description=JD,
        received_at=datetime.now(timezone.utc),
        actor=actor,
        **extra,
    )
    session.commit()
    return row


def test_request_has_processing_columns(session):
    row = _new(session, _actor(session))
    fresh = session.get(HiringRequest, row.id)
    assert fresh.pool_opened_at is None
    assert fresh.last_match_completed_at is None
    assert fresh.pool_stale is False
    assert fresh.requested_count is None


import pytest
from sqlalchemy import select

from app.domain.actor import AGENT, SYSTEM
from app.domain.transitions import TransitionError
from app.models import CandidateMatch, MatchRequirementResult, RequestRequirement, Shortlist, SharingRecord
from app.services.hiring import HiringError, extract_requirements, open_request, pool_status, update_requirement
from app.services.matching import run_match
from tests.test_intelligence import _run
from tests.test_matching import ADA
from tests.test_corpus_gates import _actor as recruiter


def _candidate(session):
    from app.extraction.deterministic import DeterministicExtractor
    from app.extraction.embeddings import LocalFeatureEmbedder
    from tests.test_matching import make_pdf

    return _run(
        session,
        "ada.pdf",
        make_pdf(ADA),
        extractor=DeterministicExtractor(),
        embedder=LocalFeatureEmbedder(),
    )


def _approve(session, row, actor):
    from app.services.hiring import approve_requirements

    approve_requirements(session, row.id, actor)
    session.commit()


def _status(session, row):
    session.expire_all()
    return pool_status(session, session.get(HiringRequest, row.id))


def test_confirmed_match_refuses_unapproved_requirements_and_provisional_match_uses_them(session):
    actor = recruiter(session)
    _candidate(session)
    row = _new(session, actor)
    open_request(session, row.id, actor)
    extract_requirements(session, row.id, actor)
    session.commit()
    with pytest.raises(HiringError) as refused:
        run_match(session, row.id, actor)
    assert refused.value.code == "requirements_not_approved"
    session.rollback()
    assert run_match(session, row.id, actor, provisional=True)
    session.commit()
    assert _status(session, row) == "provisional"
    _approve(session, row, actor)
    assert _status(session, row) == "provisional"  # approved, but the pool was built before the approval
    assert run_match(session, row.id, actor)
    session.commit()
    assert _status(session, row) == "confirmed"


def test_system_actor_can_extract_and_match_but_agent_cannot(session):
    actor = recruiter(session)
    row = _new(session, actor)
    open_request(session, row.id, actor)
    extract_requirements(session, row.id, SYSTEM)
    _approve(session, row, actor)
    run_match(session, row.id, SYSTEM)
    with pytest.raises(TransitionError):
        extract_requirements(session, row.id, AGENT)


def test_edit_marks_pool_stale_and_provisional_until_reapproved_and_rematched(session):
    actor = recruiter(session)
    _candidate(session)
    row = _new(session, actor)
    open_request(session, row.id, actor)
    stored = extract_requirements(session, row.id, actor)
    _approve(session, row, actor)
    run_match(session, row.id, actor)
    session.commit()
    assert _status(session, row) == "confirmed"
    first = session.get(type(row), row.id).last_match_completed_at
    update_requirement(session, row.id, stored[0].id, actor, strength="preferred")
    session.commit()
    assert session.get(type(row), row.id).pool_stale is True
    # An edit sends the row back to "proposed", so the pool is provisional until it is approved and rematched.
    assert session.get(RequestRequirement, stored[0].id).review_status == "proposed"
    assert _status(session, row) == "provisional"
    _approve(session, row, actor)
    run_match(session, row.id, actor)
    session.commit()
    fresh = session.get(type(row), row.id)
    assert fresh.pool_stale is False
    assert fresh.last_match_completed_at > first
    assert _status(session, row) == "confirmed"


def test_matching_never_shortlists_or_shares(session):
    actor = recruiter(session)
    _candidate(session)
    row = _new(session, actor)
    open_request(session, row.id, actor)
    extract_requirements(session, row.id, SYSTEM)
    run_match(session, row.id, SYSTEM, provisional=True)
    _approve(session, row, actor)
    run_match(session, row.id, SYSTEM)
    session.commit()
    assert session.scalar(select(Shortlist.id)) is None
    assert session.scalar(select(SharingRecord.id)) is None


from fastapi.testclient import TestClient

from app.jobs.queue import run_once
from app.main import app
from app.models import AuditEvent, Job
from app.services.hiring import request_view, submit_request
from app.services.processing import (
    PROCESS_REQUEST,
    enqueue_match,
    enqueue_process,
    processing_view,
    retry_process,
    run_process,
)
from tests.test_matching import RECRUITER


def _submitted(session, actor):
    row = _new(session, actor, requested_count=5)
    submit_request(session, row.id, actor)
    enqueue_process(session, row.id)
    session.commit()
    return row


def _drain(session):
    while run_once(session, worker_id="test", handler=run_process):
        pass


def _approve_and_drain(session, row, actor, requirement_ids=None):
    """HR approves requirements through the API; that queues the approved-only rematch, which the worker runs."""
    body = {"requirement_ids": [str(item) for item in requirement_ids]} if requirement_ids else None
    with TestClient(app) as client:
        response = client.post(f"/hiring-requests/{row.id}/requirements/approve", headers=RECRUITER, json=body)
    assert response.status_code == 200
    session.expire_all()
    _drain(session)
    session.expire_all()


def _requirements(session, row):
    return {r.requirement_text: r for r in session.scalars(select(RequestRequirement).where(RequestRequirement.request_id == row.id))}


def _results_used(session, row):
    matches = select(CandidateMatch.id).where(CandidateMatch.request_id == row.id)
    return set(session.scalars(select(MatchRequirementResult.requirement_id).where(MatchRequirementResult.match_id.in_(matches))))


def _first_open_match(session, row):
    return session.scalars(
        select(CandidateMatch).where(
            CandidateMatch.request_id == row.id, CandidateMatch.disposition.in_(("recommended", "needs_review"))
        )
    ).first()


def test_submission_extracts_proposed_requirements_and_matches_them_into_a_provisional_pool(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    assert processing_view(session, row.id)["stage"] == "received"
    _drain(session)
    session.expire_all()
    view = request_view(session, row.id)
    assert view["status"] == "open"
    assert view["processing"]["stage"] == "complete"
    assert view["processing"]["pool_status"] == "provisional"
    assert view["processing"]["matched_count"] >= 1
    assert view["processing"]["requested_count"] == 5
    # Automatic processing never approves anything: every requirement is still proposed, and visibly so.
    assert view["requirements"] and all(r["review_status"] == "proposed" for r in view["requirements"])
    # The provisional pool was matched on the proposed requirements, and every one is shown with its evidence.
    assert _results_used(session, row) == {r.id for r in _requirements(session, row).values()}
    assert session.scalar(select(Shortlist.id)) is None
    assert session.scalar(select(SharingRecord.id)) is None
    actors = {e.actor_kind for e in session.scalars(select(AuditEvent).where(AuditEvent.action == "matching_run"))}
    assert actors == {"system"}
    assert dashboard(session, actor)["counts"]["shortlisted_candidates"] == 0
    session.commit()

    with TestClient(app) as client:
        listed = client.get(f"/hiring-requests/{row.id}/matches", headers=RECRUITER)
    assert listed.status_code == 200
    matches = listed.json()["matches"]
    first = matches[0]
    assert "years_of_experience" in first
    assert first["score_max"] == 100
    for item in matches:
        lines = item["requirements"]
        assert item["eligibility"] in {"eligible", "needs_review", "excluded"}
        assert item["mandatory_total"] == sum(line["strength"] == "mandatory" for line in lines)
        if item["eligibility"] == "eligible":
            # Every point on the 0-100 score traces to one requirement, and the headline is their rounded sum.
            assert 0 <= item["match_score"] <= 100
            assert round(sum(line["points_possible"] for line in lines), 1) == 100.0
            assert round(sum(line["points_earned"] for line in lines), 1) == item["match_score_exact"]
            assert item["match_score"] == int(item["match_score_exact"] + 0.5)
        else:
            # A candidate held at the mandatory gate has no score: null, never 0.
            assert item["match_score"] is None and item["match_score_exact"] is None
            assert all(line["points_earned"] is None for line in lines)
            assert item["blocking_requirements"]
    # Held candidates never rank above one who passed the gate.
    order = {"eligible": 0, "needs_review": 1, "excluded": 2}
    ranks = [order[item["eligibility"]] for item in matches]
    assert ranks == sorted(ranks)


def test_provisional_matches_cannot_be_shortlisted(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    match = _first_open_match(session, row)
    with pytest.raises(HiringError) as refused:
        shortlist_match(session, row.id, match.id, actor)
    assert refused.value.code == "pool_provisional"
    session.rollback()
    with TestClient(app) as client:
        response = client.post(f"/hiring-requests/{row.id}/matches/{match.id}/shortlist", json={}, headers=RECRUITER)
    assert response.status_code == 409
    assert response.json()["detail"] == "pool_provisional"
    session.expire_all()
    assert session.scalar(select(Shortlist.id)) is None


def test_provisional_pool_cannot_be_shared(session):
    """A shortlist made on a confirmed pool cannot be shared once an edit makes the pool provisional again."""
    from app.services.sharing import send_share

    from tests.test_mail import FakeMail

    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    _approve_and_drain(session, row, actor)
    entry = shortlist_match(session, row.id, _first_open_match(session, row).id, actor)
    session.commit()
    python = _requirements(session, row)["Python"]
    update_requirement(session, row.id, python.id, actor, strength="preferred")
    session.commit()
    assert _status(session, row) == "provisional"
    with pytest.raises(SendError) as refused:
        approve_share(session, row.id, entry.candidate_id, actor)
    assert refused.value.code == "pool_provisional"
    session.rollback()
    with pytest.raises(SendError) as refused:
        send_share(session, row.id, entry.candidate_id, actor, FakeMail())
    assert refused.value.code == "pool_provisional"
    session.rollback()
    with TestClient(app) as client:
        response = client.post(f"/hiring-requests/{row.id}/candidates/{entry.candidate_id}/share/approve", headers=RECRUITER)
    assert response.status_code == 409
    assert response.json()["detail"] == "pool_provisional"
    session.expire_all()
    assert session.scalar(select(SharingRecord.id)) is None


def test_approval_triggers_a_rematch_on_approved_requirements_only(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    reqs = _requirements(session, row)
    provisional_at = session.get(HiringRequest, row.id).last_match_completed_at
    jobs_before = session.scalars(select(Job).where(Job.job_type == PROCESS_REQUEST)).all()

    # HR approves only Python. The rematch drops AWS; the pool stays provisional while AWS is unapproved.
    _approve_and_drain(session, row, actor, requirement_ids=[reqs["Python"].id])
    jobs_after = session.scalars(select(Job).where(Job.job_type == PROCESS_REQUEST)).all()
    assert len(jobs_after) == len(jobs_before) + 1
    assert jobs_after[-1].payload["reason"] == "approved" and jobs_after[-1].status == "succeeded"
    fresh = session.get(HiringRequest, row.id)
    assert fresh.last_match_completed_at > provisional_at
    assert _results_used(session, row) == {reqs["Python"].id}
    assert _requirements(session, row)["AWS"].review_status == "proposed"
    assert _status(session, row) == "provisional"

    _approve_and_drain(session, row, actor)
    assert _results_used(session, row) == {reqs["Python"].id, reqs["AWS"].id}
    assert all(r.review_status == "approved" for r in _requirements(session, row).values())
    assert _status(session, row) == "confirmed"
    assert processing_view(session, row.id)["pool_status"] == "confirmed"
    assert {e.actor_kind for e in session.scalars(select(AuditEvent).where(AuditEvent.action == "matching_run"))} == {"system"}


def test_hr_can_reject_a_proposed_requirement_and_the_rematch_ignores_it(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    reqs = _requirements(session, row)
    with TestClient(app) as client:
        from tests.test_mail import ENGINEER

        denied = client.post(f"/hiring-requests/{row.id}/requirements/{reqs['AWS'].id}/reject", headers=ENGINEER)
        assert denied.status_code == 403
        rejected = client.post(f"/hiring-requests/{row.id}/requirements/{reqs['AWS'].id}/reject", headers=RECRUITER)
        assert rejected.status_code == 200 and rejected.json()["review_status"] == "rejected"
    session.expire_all()
    # Python is still proposed, so the pool stays provisional.
    assert _status(session, row) == "provisional"
    # "Approve all" approves what is still proposed and never revives the rejected row.
    _approve_and_drain(session, row, actor)
    fresh = _requirements(session, row)
    assert fresh["AWS"].review_status == "rejected" and fresh["Python"].review_status == "approved"
    assert _results_used(session, row) == {reqs["Python"].id}
    assert _status(session, row) == "confirmed"
    event = session.scalars(
        select(AuditEvent).where(AuditEvent.action == "requirements_changed", AuditEvent.entity_id == reqs["AWS"].id)
    ).one()
    assert event.actor_kind == "user" and event.detail["outcome"] == "rejected"


def test_rejecting_an_approved_requirement_on_a_confirmed_pool_rematches_without_it(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    _approve_and_drain(session, row, actor)
    assert _status(session, row) == "confirmed"
    reqs = _requirements(session, row)
    with TestClient(app) as client:
        assert client.post(f"/hiring-requests/{row.id}/requirements/{reqs['AWS'].id}/reject", headers=RECRUITER).status_code == 200
    session.expire_all()
    assert _status(session, row) == "provisional"  # stale, and the rematch is queued
    _drain(session)
    assert _results_used(session, row) == {reqs["Python"].id}
    assert _status(session, row) == "confirmed"


def test_rejecting_every_requirement_leaves_the_request_intact_and_recoverable(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    with TestClient(app) as client:
        for item in _requirements(session, row).values():
            assert client.post(f"/hiring-requests/{row.id}/requirements/{item.id}/reject", headers=RECRUITER).status_code == 200
        session.expire_all()
        assert _status(session, row) == "provisional"  # nothing approved, so never confirmed
        with pytest.raises(HiringError):
            shortlist_match(session, row.id, _first_open_match(session, row).id, actor)
        session.rollback()
        added = client.post(f"/hiring-requests/{row.id}/requirements/manual", headers=RECRUITER,
                            json={"label": "skill", "text": "Python", "strength": "mandatory", "quote": "Required skills: Python"})
        assert added.status_code == 201
    _approve_and_drain(session, row, actor)
    assert session.get(HiringRequest, row.id).status == "open"
    assert _status(session, row) == "confirmed"


def test_approving_twice_before_the_rematch_starts_queues_one_job(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    with TestClient(app) as client:
        for _ in range(2):
            assert client.post(f"/hiring-requests/{row.id}/requirements/approve", headers=RECRUITER).status_code == 200
    session.expire_all()
    queued = session.scalars(select(Job).where(Job.job_type == PROCESS_REQUEST, Job.status == "queued")).all()
    assert len(queued) == 1
    assert processing_view(session, row.id)["stage"] == "matching"


def test_an_approval_during_a_running_rematch_queues_another_and_keeps_the_pool_provisional(session, monkeypatch):
    """The rematch that was already running read the old requirements, so it cannot confirm the pool.

    The approval is committed from a second connection while the matcher runs. Only the requirement row and a job are
    written there: a real approval also writes the request row, which waits on the running match's lock instead."""
    from sqlalchemy import create_engine, update

    from app.db import make_session_factory
    from app.services import matching
    from app.services.hiring import approve_requirements
    from tests.conftest import TEST_URL

    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    reqs = _requirements(session, row)
    approve_requirements(session, row.id, actor, requirement_ids=[reqs["Python"].id])
    enqueue_match(session, row.id)
    session.commit()

    real = matching._eligible_candidates
    engine = create_engine(TEST_URL)
    other = make_session_factory(engine)

    def approve_meanwhile(db):
        with other() as second:
            second.execute(update(RequestRequirement).where(RequestRequirement.id == reqs["AWS"].id).values(review_status="approved"))
            job = enqueue_match(second, row.id)  # the running job is not reused: a new one is queued
            assert job.status == "queued"
            second.commit()
        return real(db)

    monkeypatch.setattr(matching, "_eligible_candidates", approve_meanwhile)
    assert run_once(session, worker_id="test", handler=run_process)
    monkeypatch.setattr(matching, "_eligible_candidates", real)
    engine.dispose()
    session.expire_all()
    assert session.get(HiringRequest, row.id).pool_stale is True
    assert _status(session, row) == "provisional"
    assert session.scalars(select(Job).where(Job.job_type == PROCESS_REQUEST, Job.status == "queued")).all()
    _drain(session)
    assert _status(session, row) == "confirmed"
    assert _results_used(session, row) == {reqs["Python"].id, reqs["AWS"].id}


def test_confirmed_pool_can_be_shortlisted_and_sharing_still_needs_explicit_hr_approval(session):
    from app.services.sharing import send_share

    from tests.test_mail import FakeMail

    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    _approve_and_drain(session, row, actor)
    assert _status(session, row) == "confirmed"
    match = _first_open_match(session, row)
    with pytest.raises(TransitionError):
        shortlist_match(session, row.id, match.id, SYSTEM)
    session.rollback()
    with TestClient(app) as client:
        placed = client.post(f"/hiring-requests/{row.id}/matches/{match.id}/shortlist", json={}, headers=RECRUITER)
    assert placed.status_code == 201
    session.expire_all()
    # Shortlisting shares nothing, and a send without the explicit share approval is refused.
    assert session.scalar(select(SharingRecord.id)) is None
    with pytest.raises(SendError) as refused:
        send_share(session, row.id, match.candidate_id, actor, FakeMail())
    assert refused.value.code == "approval_required"
    session.rollback()
    with pytest.raises((TransitionError, SendError)):
        approve_share(session, row.id, match.candidate_id, SYSTEM)
    session.rollback()
    approve_share(session, row.id, match.candidate_id, actor)
    session.commit()
    with pytest.raises(SendError) as no_contact:
        send_share(session, row.id, match.candidate_id, actor, FakeMail())
    assert no_contact.value.code == "recipient_missing"  # no default address: the company contact is named first
    session.rollback()
    from app.services.hiring import set_contact

    set_contact(session, row.id, "hiring@northwind.example", actor)
    record = send_share(session, row.id, match.candidate_id, actor, FakeMail())
    session.commit()
    assert record.status == "sent"
    assert record.recipient == "hiring@northwind.example"


def test_double_submit_creates_one_job_and_no_duplicates(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    enqueue_process(session, row.id)
    enqueue_process(session, row.id)
    session.commit()
    assert len(session.scalars(select(Job).where(Job.job_type == PROCESS_REQUEST)).all()) == 1
    _drain(session)
    enqueue_process(session, row.id)  # after completion: still no second job
    session.commit()
    _drain(session)
    reqs = session.scalars(select(RequestRequirement).where(RequestRequirement.request_id == row.id)).all()
    matches = session.scalars(select(CandidateMatch).where(CandidateMatch.request_id == row.id)).all()
    assert len(reqs) == len({r.requirement_text for r in reqs})
    assert len(matches) == len({m.candidate_id for m in matches})
    assert len(session.scalars(select(Job).where(Job.job_type == PROCESS_REQUEST)).all()) == 1


def test_failed_processing_reports_failed_and_retry_works(session, monkeypatch):
    actor = recruiter(session)
    row = _submitted(session, actor)

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.services.processing.extract_requirements", boom)
    from app.config import get_settings

    for _ in range(get_settings().job_max_attempts + 1):
        run_once(session, worker_id="test", handler=run_process)
    assert processing_view(session, row.id)["stage"] == "failed"
    monkeypatch.undo()
    retry_process(session, row.id)
    session.commit()
    _drain(session)
    view = processing_view(session, row.id)
    assert view["stage"] == "complete"
    assert view["pool_status"] == "provisional"


from app.services.desk import dashboard
from app.services.hiring import open_pool


def test_open_pool_is_idempotent_and_audited_once(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    first = open_pool(session, row.id, actor)
    session.commit()
    stamp = first.pool_opened_at
    open_pool(session, row.id, actor)
    session.commit()
    again = session.get(type(row), row.id)
    assert again.pool_opened_at == stamp
    events = session.scalars(select(AuditEvent).where(AuditEvent.action == "pool_opened")).all()
    assert len(events) == 1


def test_new_matches_tile_follows_open_and_rematch(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    assert dashboard(session, actor)["counts"]["new_matches"] == 0
    _drain(session)
    assert dashboard(session, actor)["counts"]["new_matches"] == 1  # the provisional pool is new work for HR
    open_pool(session, row.id, actor)
    session.commit()
    assert dashboard(session, actor)["counts"]["new_matches"] == 0
    stamp = session.get(type(row), row.id).pool_opened_at
    _approve_and_drain(session, row, actor)
    assert session.get(type(row), row.id).pool_opened_at == stamp
    assert dashboard(session, actor)["counts"]["new_matches"] == 1  # the confirmed rematch is new again
    open_pool(session, row.id, actor)
    session.commit()
    assert dashboard(session, actor)["counts"]["new_matches"] == 0


from app.services.hiring import shortlist_match
from app.services.sharing import SendError, approve_share


def test_domain_errors_quarantine_immediately_and_roll_back_all_handler_work(session, monkeypatch):
    """A TransitionError mid-run cannot heal by retrying: one attempt, real error code, and the
    all-or-nothing contract leaves no extracted requirements behind a failed job."""
    actor = recruiter(session)
    row = _submitted(session, actor)

    def invalid(*args, **kwargs):
        raise TransitionError("invalid_transition")

    monkeypatch.setattr("app.services.processing.run_match", invalid)
    run_once(session, worker_id="test", handler=run_process)

    job = session.scalars(select(Job).where(Job.job_type == "process_request")).one()
    assert job.status == "quarantined"  # permanent: no attempts burned on retries
    assert job.error_code == "invalid_transition"
    assert processing_view(session, row.id)["stage"] == "failed"
    assert session.scalars(select(RequestRequirement).where(RequestRequirement.request_id == row.id)).all() == []
    assert session.get(HiringRequest, row.id).status == "submitted"  # open transition rolled back too

"""Demo data tooling: batch-friendly idempotent intake, live status, and a full reset that keeps auth and audit."""

from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bootstrap import provision
from app.config import get_settings, reset_settings
from app.jobs.queue import run_once
from app.main import app, create_app
from app.models import (
    AuditEvent,
    Candidate,
    CandidateDocument,
    DocumentChunk,
    Job,
    User,
)
from app.services.pipeline import run_extract
from tests.test_corpus_gates import BODY, make_pdf
from tests.test_mail import ENGINEER, RECRUITER

OTHER = BODY.replace("Ada Lovelace", "Grace Hopper").replace("ada@example.com", "grace@example.com").replace(
    "+14155550199", "+14155550123"
)


@cache
def _pdf(text: str) -> bytes:
    # make_pdf embeds a timestamp, so identical text is only identical bytes if it is built once.
    return make_pdf(text)


def _upload(client, name: str, text: str = BODY):
    return client.post(
        "/documents",
        files={"file": (name, _pdf(text), "application/pdf")},
        headers=RECRUITER,
    )


def _drain(session):
    def handler(db, job):
        run_extract(db, job)

    while run_once(session, worker_id="test", handler=handler):
        pass


def _count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_reset_is_recruiter_only_and_needs_the_typed_phrase(session):
    provision(session)
    with TestClient(app) as client:
        assert client.post("/demo/reset", json={"confirm": "RESET"}, headers=ENGINEER).status_code == 403
        assert client.get("/demo/status", headers=ENGINEER).status_code == 403
        assert client.post("/demo/reset", json={"confirm": "reset"}, headers=RECRUITER).status_code == 400
        assert client.post("/demo/reset", json={}, headers=RECRUITER).status_code == 422
        assert client.post("/demo/reset", json={"confirm": "RESET"}).status_code == 401


def test_demo_routes_do_not_exist_outside_local(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("HUB_RECRUITER_TOKEN", "production-recruiter-token-0123456789")
    monkeypatch.setenv("HUB_ENGINEER_TOKEN", "production-engineer-token-9876543210")
    reset_settings()
    try:
        paths = set(create_app().openapi()["paths"])
    finally:
        monkeypatch.undo()
        reset_settings()
    assert "/demo/reset" not in paths and "/demo/status" not in paths
    assert "/documents" in paths


def test_reset_empties_operational_data_and_keeps_users_and_audit(session):
    provision(session)
    users = _count(session, User)
    with TestClient(app) as client:
        assert _upload(client, "ada.pdf").status_code == 201
        assert _upload(client, "grace.pdf", OTHER).status_code == 201
        _drain(session)
        session.expire_all()
        assert _count(session, Candidate) == 2
        assert _count(session, DocumentChunk) > 0
        audit_before = _count(session, AuditEvent)
        storage_keys = list(session.scalars(select(CandidateDocument.storage_key)))
        assert len(storage_keys) == 2
        for key in storage_keys:
            assert (Path(get_settings().storage_dir) / key).is_file()

        response = client.post("/demo/reset", json={"confirm": "RESET"}, headers=RECRUITER)
        assert response.status_code == 200 and response.json()["reset_at"]
        session.expire_all()

        assert _count(session, Candidate) == 0
        assert _count(session, CandidateDocument) == 0
        assert _count(session, DocumentChunk) == 0
        assert _count(session, Job) == 0
        assert _count(session, User) == users
        assert _count(session, AuditEvent) == audit_before + 1
        # The uploaded files are operational data too: reset must not leave CV bytes on disk.
        for key in storage_keys:
            assert not (Path(get_settings().storage_dir) / key).exists()
        event = session.scalars(select(AuditEvent).where(AuditEvent.action == "demo_reset")).one()
        assert event.actor_kind == "user" and event.detail == {"outcome": "reset"}

        listed = client.get("/candidates", headers=RECRUITER).json()
        status = client.get("/demo/status", headers=RECRUITER).json()
    assert listed["total"] == 0 and listed["candidates"] == []
    assert status["last_reset_at"] is not None
    assert status["documents"] == 0 and status["candidates"] == 0 and status["open_jobs"] == 0


def test_same_corpus_loads_again_after_reset(session):
    provision(session)
    with TestClient(app) as client:
        first = _upload(client, "ada.pdf")
        _drain(session)
        assert client.post("/demo/reset", json={"confirm": "RESET"}, headers=RECRUITER).status_code == 200
        again = _upload(client, "ada.pdf")
        assert again.status_code == 201 and again.json()["created"] is True
        assert again.json()["id"] != first.json()["id"]
        _drain(session)
        session.expire_all()
        status = client.get("/demo/status", headers=RECRUITER).json()
    assert status["documents"] == 1 and status["candidates"] == 1
    assert status["documents_by_status"] == {"profiled": 1} or status["documents_by_status"] == {"extracted": 1}


def test_retrying_the_same_files_creates_no_duplicate_document_job_or_candidate(session):
    provision(session)
    with TestClient(app) as client:
        first = _upload(client, "ada.pdf")
        retry = _upload(client, "ada-again.pdf")
        assert first.json()["created"] is True and retry.json()["created"] is False
        assert retry.json()["id"] == first.json()["id"]
        _drain(session)
        _upload(client, "ada.pdf")
        _drain(session)
        session.expire_all()
    assert _count(session, CandidateDocument) == 1
    assert _count(session, Job) == 1
    assert _count(session, Candidate) == 1


def test_concurrent_uploads_of_identical_bytes_create_one_document_and_one_job(session):
    provision(session)
    data = _pdf(BODY)

    def send(_):
        with TestClient(app) as client:
            return client.post("/documents", files={"file": ("ada.pdf", data, "application/pdf")}, headers=RECRUITER)

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(send, range(6)))
    session.expire_all()
    assert all(r.status_code == 201 for r in responses)
    assert sum(1 for r in responses if r.json()["created"]) == 1
    assert len({r.json()["id"] for r in responses}) == 1
    assert _count(session, CandidateDocument) == 1
    assert _count(session, Job) == 1


def test_status_reports_documents_reviews_and_outcomes_from_live_tables(session):
    provision(session)
    with TestClient(app) as client:
        empty = client.get("/demo/status", headers=RECRUITER).json()
        assert empty["last_reset_at"] is None
        assert empty["documents"] == 0 and empty["pending_reviews"] == 0 and empty["hiring_requests"] == 0
        _upload(client, "ada.pdf")
        queued = client.get("/demo/status", headers=RECRUITER).json()
        assert queued["documents"] == 1 and queued["processing"] == 1 and queued["open_jobs"] == 1
        _drain(session)
        done = client.get("/demo/status", headers=RECRUITER).json()
    assert done["processing"] == 0 and done["open_jobs"] == 0 and done["candidates"] == 1
    assert sum(done["documents_by_status"].values()) == done["documents"] == 1
    for key in ("needs_ocr", "quarantined", "failed", "pending_reviews", "matches", "shortlisted", "shares"):
        assert key in done


def test_reset_survives_agent_runs_that_audit_rows_point_at(session):
    """Real ingestion writes agent_runs tied to documents, candidates and requests, and audit rows reference them.
    audit_events is append-only, so reset must keep the agent_runs and detach them instead of deleting them."""
    from datetime import datetime, timezone

    from app.models import AgentRun, HiringRequest
    from app.services.audit import write_audit
    from tests.test_corpus_gates import _actor

    actor = _actor(session)
    with TestClient(app) as client:
        assert _upload(client, "ada.pdf").status_code == 201
    _drain(session)
    candidate = session.scalars(select(Candidate)).first()
    document = session.scalars(select(CandidateDocument)).first()
    job = session.scalars(select(Job)).first()
    request = HiringRequest(company_name="Acme", job_title="Engineer", description="Required skills: Python", received_at=datetime.now(timezone.utc), status="draft")
    session.add(request)
    session.flush()
    run = AgentRun(agent_name="matcher", status="ok", job_id=job.id, document_id=document.id, candidate_id=candidate.id, request_id=request.id)
    session.add(run)
    session.flush()
    write_audit(session, actor=actor, action="matching_run", entity_type="hiring_request", entity_id=request.id, agent_run_id=run.id)
    session.commit()
    run_id = run.id

    with TestClient(app) as client:
        response = client.post("/demo/reset", json={"confirm": "RESET"}, headers=RECRUITER)
    assert response.status_code == 200, response.text
    session.expire_all()
    kept = session.get(AgentRun, run_id)
    assert kept is not None
    assert (kept.job_id, kept.document_id, kept.candidate_id, kept.request_id) == (None, None, None, None)
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.agent_run_id == run_id)) == 1
    assert _count(session, HiringRequest) == 0 and _count(session, Candidate) == 0 and _count(session, Job) == 0


def test_reset_works_after_a_full_request_flow_with_shortlist_approval_and_share(session):
    """Regression: reset deleted candidate_matches before the shortlist rows that reference them and failed with 500."""
    from app.models import ApprovalDecision, CandidateMatch, HiringRequest, SharingRecord, Shortlist, ShortlistCandidate
    from app.services.hiring import approve_requirements, create_request, extract_requirements, open_request, shortlist_match
    from app.services.matching import run_match
    from app.services.sharing import approve_share, send_share
    from app.services.mail import get_mail_sender
    from tests.test_corpus_gates import _actor

    provision(session)
    with TestClient(app) as client:
        assert _upload(client, "ada.pdf").status_code == 201
    _drain(session)
    actor = _actor(session)
    row = create_request(session, company_name="Acme", job_title="Engineer", description="Required skills: Analytical", received_at=__import__("datetime").datetime(2026, 9, 1, tzinfo=__import__("datetime").timezone.utc), actor=actor)
    extract_requirements(session, row.id, actor)
    approve_requirements(session, row.id, actor)
    open_request(session, row.id, actor)
    match = next(m for m in run_match(session, row.id, actor) if m.disposition in ("recommended", "needs_review"))
    entry = shortlist_match(session, row.id, match.id, actor)
    approve_share(session, row.id, entry.candidate_id, actor)
    session.commit()
    try:
        send_share(session, row.id, entry.candidate_id, actor, get_mail_sender())
        session.commit()
    except Exception:
        session.rollback()
    assert _count(session, ShortlistCandidate) == 1 and _count(session, ApprovalDecision) >= 1

    with TestClient(app) as client:
        response = client.post("/demo/reset", json={"confirm": "RESET"}, headers=RECRUITER)
    assert response.status_code == 200, response.text
    session.expire_all()
    for model in (HiringRequest, CandidateMatch, Shortlist, ShortlistCandidate, ApprovalDecision, SharingRecord, Candidate, CandidateDocument, Job):
        assert _count(session, model) == 0, model.__tablename__

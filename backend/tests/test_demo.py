"""Reset Demo Data wipes operational tables, keeps users and the append-only audit trail."""

from sqlalchemy import func, select

from app.models import (
    AuditEvent,
    Candidate,
    CandidateDocument,
    DuplicateReview,
    HiringRequest,
    Job,
    User,
)
from app.services.demo import reset_demo_data
from app.jobs.queue import run_once
from app.services.hiring import create_request
from app.services.ingest import ingest_bytes
from app.services.pipeline import run_extract
from tests.test_corpus_gates import _actor
from tests.test_intelligence import make_pdf

from datetime import datetime, timezone


def _operational_counts(session):
    # AgentRun rows are deliberately kept (FKs nulled) because append-only audit_events
    # reference them; that policy is covered by test_demo_data.py::test_reset_survives_agent_runs...
    return {
        "candidates": session.scalar(select(func.count()).select_from(Candidate)),
        "documents": session.scalar(select(func.count()).select_from(CandidateDocument)),
        "requests": session.scalar(select(func.count()).select_from(HiringRequest)),
        "jobs": session.scalar(select(func.count()).select_from(Job)),
        "reviews": session.scalar(select(func.count()).select_from(DuplicateReview)),
    }


def test_reset_wipes_operational_data_and_keeps_users_and_audit(session):
    actor = _actor(session)
    ingest_bytes(session, filename="cv.pdf", data=make_pdf("Ada Lovelace\nPython"), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=lambda db, job: run_extract(db, job))
    create_request(
        session,
        company_name="Acme Corp",
        job_title="Engineer",
        description="Required skills: Python\n",
        received_at=datetime.now(timezone.utc),
        actor=actor,
    )
    session.commit()
    assert sum(_operational_counts(session).values()) > 0
    users_before = session.scalar(select(func.count()).select_from(User))
    audit_before = session.scalar(select(func.count()).select_from(AuditEvent))

    reset_demo_data(session, actor)
    session.commit()

    assert all(count == 0 for count in _operational_counts(session).values())
    assert session.scalar(select(func.count()).select_from(User)) == users_before
    audit_after = session.scalar(select(func.count()).select_from(AuditEvent))
    assert audit_after == audit_before + 1
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "demo_reset"))
    assert event is not None
    assert event.actor_kind == "user"
    assert event.detail == {"outcome": "reset"}
    assert "@" not in str(event.detail)


def test_reset_on_empty_database_is_a_noop_plus_audit(session):
    actor = _actor(session)
    reset_demo_data(session, actor)
    session.commit()
    assert all(count == 0 for count in _operational_counts(session).values())
    assert session.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "demo_reset")) == 1

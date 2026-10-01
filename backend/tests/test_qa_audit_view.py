"""The audit trail answers who, what, when and on which object. Found in the end-to-end pass: the Audit page listed
"Person · Candidate shared" with no name, no candidate and no request, and only the latest 12 events."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditEvent, User
from app.services.audit import write_audit
from tests.test_mail import ENGINEER, RECRUITER
from tests.test_sharing import _candidate, _recruiter, _request


def test_each_event_names_the_person_the_request_and_the_candidate(session):
    actor = _recruiter(session)
    candidate = _candidate(session, name="Quinn Backend")
    request = _request(session)
    write_audit(
        session,
        actor=actor,
        action="candidate_shared",
        entity_type="sharing_record",
        entity_id=None,
        detail={"request_id": str(request.id), "candidate_id": str(candidate.id), "outcome": "sent"},
    )
    session.commit()
    recruiter = session.scalar(select(User).where(User.role == "recruiter"))
    with TestClient(app) as client:
        page = client.get("/audit", headers=RECRUITER)
        denied = client.get("/audit", headers=ENGINEER)
        anonymous = client.get("/audit")
    assert page.status_code == 200
    assert denied.status_code == 403
    assert anonymous.status_code == 401
    event = page.json()["events"][0]
    assert event["action"] == "candidate_shared"
    assert event["actor"] == {"kind": "user", "name": recruiter.full_name}
    assert event["request"]["label"] == "Example Labs · Backend engineer"
    assert event["candidate"] == {"id": str(candidate.id), "label": "Quinn Backend"}
    # Nothing personal is stored in the audit row itself; the names are read at display time.
    stored = session.scalar(select(AuditEvent).where(AuditEvent.action == "candidate_shared"))
    assert "Quinn" not in str(stored.detail)


def test_pages_and_filters(session):
    actor = _recruiter(session)
    request = _request(session)
    for index in range(5):
        write_audit(session, actor=actor, action="candidate_viewed", entity_type="candidate", entity_id=None, detail={})
        write_audit(
            session,
            actor=actor,
            action="requirements_changed",
            entity_type="hiring_request",
            entity_id=request.id,
            detail={"request_id": str(request.id), "count": index},
        )
    session.commit()
    with TestClient(app) as client:
        first = client.get("/audit", params={"limit": 4}, headers=RECRUITER).json()
        assert len(first["events"]) == 4 and first["next_before"]
        decisions = client.get("/audit", params={"category": "decisions"}, headers=RECRUITER).json()["events"]
        for_request = client.get("/audit", params={"request_id": str(request.id)}, headers=RECRUITER).json()["events"]
    assert {event["action"] for event in decisions} == {"requirements_changed"}  # opening a profile is not a decision
    assert len(for_request) == 5
    assert datetime.fromisoformat(first["next_before"]) <= datetime.now(timezone.utc)

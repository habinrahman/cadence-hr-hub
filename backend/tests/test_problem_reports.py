"""Problem reports store safe metadata. They do not store CV text or grant new access."""

import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.bootstrap import provision
from app.main import app
from app.models import AuditEvent, Candidate, ProblemReport, User
from tests.test_mail import ENGINEER, RECRUITER

CV_TEXT = """Ada Lovelace
ada@example.com
+14155550199
Experience
Analytical Engines, Engineer
Reconcile ledger accounts for the public engine team
"""


def _ready(session):
    provision(session)
    session.commit()


def _body(**overrides):
    payload = {
        "category": "intake",
        "title": "Upload stayed on reading",
        "description": "A PDF remained queued after the recruiter uploaded it.",
        "entity_type": "none",
        "context": {"error_code": "stuck_reading", "route": "/source", "action": "upload"},
    }
    payload.update(overrides)
    return payload


def test_recruiter_can_create_a_report_and_see_its_status(session):
    _ready(session)
    with TestClient(app) as client:
        created = client.post("/problem-reports", headers=RECRUITER, json=_body())
        assert created.status_code == 201
        report_id = created.json()["id"]
        listing = client.get("/problem-reports", headers=RECRUITER)
        assert listing.status_code == 200
        assert listing.json()["reports"][0]["id"] == report_id
        assert listing.json()["reports"][0]["status"] == "open"
    row = session.get(ProblemReport, report_id)
    assert row.summary == "Upload stayed on reading"
    assert row.context == {"error_code": "stuck_reading", "route": "/source", "action": "upload"}
    assert CV_TEXT not in json.dumps(row.context)


def test_engineer_can_view_and_update_without_hiring_access(session):
    _ready(session)
    with TestClient(app) as client:
        created = client.post("/problem-reports", headers=RECRUITER, json=_body())
        report_id = created.json()["id"]
        viewed = client.get("/problem-reports", headers=ENGINEER)
        assert viewed.status_code == 200
        assert viewed.json()["reports"][0]["id"] == report_id
        hiring = client.get("/hiring-requests", headers=ENGINEER)
        assert hiring.status_code == 403
        updated = client.patch(
            f"/problem-reports/{report_id}",
            headers=ENGINEER,
            json={"status": "resolved", "note": "The queue worker had stopped."},
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "resolved"
        assert updated.json()["engineering_note"] == "The queue worker had stopped."


def test_unauthorized_user_gets_403(session):
    _ready(session)
    with TestClient(app) as client:
        denied = client.post("/problem-reports", headers=ENGINEER, json=_body())
    assert denied.status_code == 403
    assert denied.json()["detail"] == "recruiter_required"


def test_recruiter_cannot_perform_engineer_actions(session):
    _ready(session)
    with TestClient(app) as client:
        created = client.post("/problem-reports", headers=RECRUITER, json=_body())
        report_id = created.json()["id"]
        denied = client.patch(
            f"/problem-reports/{report_id}",
            headers=RECRUITER,
            json={"status": "resolved", "note": "I fixed it myself."},
        )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "engineer_required"
    assert session.get(ProblemReport, report_id).status == "open"


def test_context_schema_rejects_unexpected_fields(session):
    _ready(session)
    with TestClient(app) as client:
        extra = client.post(
            "/problem-reports",
            headers=RECRUITER,
            json=_body(context={"error_code": "stuck_reading", "cv_text": CV_TEXT, "password": "hunter2"}),
        )
        embedding = client.post(
            "/problem-reports",
            headers=RECRUITER,
            json=_body(context={"embedding": [0.1, 0.2, 0.3]}),
        )
    assert extra.status_code == 422
    assert embedding.status_code == 422
    assert session.scalar(select(ProblemReport)) is None


def test_cv_text_cannot_enter_report_context(session):
    _ready(session)
    with TestClient(app) as client:
        rejected = client.post(
            "/problem-reports",
            headers=RECRUITER,
            json=_body(context={"error_code": CV_TEXT, "route": "/documents/ada@example.com"}),
        )
    assert rejected.status_code == 422
    assert session.scalar(select(ProblemReport)) is None
    assert CV_TEXT not in rejected.text


def test_references_must_point_at_real_records(session):
    _ready(session)
    candidate = Candidate(source="upload", display_name="Ada Lovelace")
    session.add(candidate)
    session.commit()
    missing = str(uuid4())
    with TestClient(app) as client:
        bad = client.post(
            "/problem-reports",
            headers=RECRUITER,
            json=_body(entity_type="candidate", entity_id=missing),
        )
        bad_request = client.post(
            "/problem-reports",
            headers=RECRUITER,
            json=_body(entity_type="hiring_request", entity_id=missing),
        )
        bad_document = client.post(
            "/problem-reports",
            headers=RECRUITER,
            json=_body(entity_type="document", entity_id=missing),
        )
        good = client.post(
            "/problem-reports",
            headers=RECRUITER,
            json=_body(entity_type="candidate", entity_id=str(candidate.id)),
        )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "invalid_reference"
    assert bad_request.json()["detail"] == "invalid_reference"
    assert bad_document.json()["detail"] == "invalid_reference"
    assert good.status_code == 201
    assert good.json()["entity_type"] == "candidate"
    assert good.json()["entity_id"] == str(candidate.id)


def test_recruiter_sees_only_their_own_reports(session):
    _ready(session)
    other = User(email="other.recruiter@cadence.local", full_name="Other Recruiter", role="recruiter")
    session.add(other)
    session.flush()
    session.add(
        ProblemReport(
            reporter_user_id=other.id,
            entity_type="none",
            summary="Hidden queue issue",
            detail="Another recruiter filed this.",
            category="other",
            status="open",
            context={},
        )
    )
    session.commit()
    with TestClient(app) as client:
        own = client.get("/problem-reports", headers=RECRUITER)
        everyone = client.get("/problem-reports", headers=ENGINEER)
    assert own.json()["reports"] == []
    assert len(everyone.json()["reports"]) == 1
    assert everyone.json()["reports"][0]["title"] == "Hidden queue issue"


def test_report_actions_are_audited_without_cv_text(session):
    _ready(session)
    with TestClient(app) as client:
        created = client.post("/problem-reports", headers=RECRUITER, json=_body())
        report_id = created.json()["id"]
        client.patch(
            f"/problem-reports/{report_id}",
            headers=ENGINEER,
            json={"status": "resolved", "note": "The queue worker had stopped."},
        )
    actions = set(session.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == report_id)).all())
    assert actions == {
        "problem_report_created",
        "problem_report_updated",
        "problem_report_status_changed",
        "problem_report_resolved",
    }
    rendered = json.dumps(
        [row.detail for row in session.scalars(select(AuditEvent).where(AuditEvent.entity_id == report_id))]
    )
    assert CV_TEXT not in rendered
    assert "@" not in rendered
    assert "The queue worker had stopped." not in rendered
    assert "Upload stayed on reading" not in rendered

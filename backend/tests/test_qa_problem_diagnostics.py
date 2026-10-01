"""A problem report reaches engineering with what is needed to fix it: the agent runs, jobs and audit codes for the
record it names, and nothing personal. Found in the end-to-end pass: the engineer saw only an entity id."""

import json

from fastapi.testclient import TestClient

from app.main import app
from app.models import AgentRun
from tests.test_mail import ENGINEER, RECRUITER
from tests.test_sharing import _recruiter, _request


def test_the_engineer_sees_agent_runs_for_the_reported_request_and_no_pii(session):
    _recruiter(session)
    request = _request(session)
    session.add(
        AgentRun(agent_name="candidate_matcher", request_id=request.id, model="deterministic-requirements", status="succeeded", output_ref="candidate_count:3")
    )
    session.commit()
    with TestClient(app) as client:
        unsafe = client.post(
            "/problem-reports",
            headers=RECRUITER,
            json={"category": "matching", "title": "Wrong", "description": "my password is hunter2"},
        )
        created = client.post(
            "/problem-reports",
            headers=RECRUITER,
            json={
                "category": "matching",
                "title": "Wrong exclusion",
                "description": "A candidate with PostgreSQL was excluded for SQL.",
                "entity_type": "hiring_request",
                "entity_id": str(request.id),
            },
        ).json()
        as_engineer = client.get(f"/problem-reports/{created['id']}", headers=ENGINEER).json()
        as_recruiter = client.get(f"/problem-reports/{created['id']}", headers=RECRUITER).json()
    assert unsafe.status_code == 422 and unsafe.json()["detail"] == "unsafe_report_text"
    runs = as_engineer["diagnostics"]["agent_runs"]
    assert [run["agent"] for run in runs] == ["candidate_matcher"]
    assert runs[0]["output_ref"] == "candidate_count:3"
    assert "diagnostics" not in as_recruiter
    assert "@" not in json.dumps(as_engineer["diagnostics"])

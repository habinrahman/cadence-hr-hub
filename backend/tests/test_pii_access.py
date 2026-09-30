"""Recruiters read candidate details. Engineers do not receive contacts or CV text."""

from fastapi.testclient import TestClient

from app.bootstrap import provision
from app.main import app
from app.models import Candidate, CandidateContact
from tests.test_mail import ENGINEER, RECRUITER

CONTACT = "ada@example.com"


def test_recruiter_reads_contacts_and_engineer_is_forbidden(session):
    provision(session)
    candidate = Candidate(source="upload", display_name="Ada Lovelace", summary="Ledger work")
    session.add(candidate)
    session.flush()
    session.add(
        CandidateContact(
            candidate_id=candidate.id,
            kind="email",
            value_raw=CONTACT,
            value_normalized=CONTACT,
            is_primary=True,
        )
    )
    session.commit()
    with TestClient(app) as client:
        recruiter = client.get(f"/candidates/{candidate.id}", headers=RECRUITER)
        engineer = client.get(f"/candidates/{candidate.id}", headers=ENGINEER)
        missing = client.get(f"/candidates/{candidate.id}")
        search = client.get("/search", params={"q": "ledger"}, headers=ENGINEER)
        reports = client.get("/problem-reports", headers=ENGINEER)
    assert recruiter.status_code == 200
    assert recruiter.json()["contacts"][0]["value"] == CONTACT
    assert engineer.status_code == 403
    assert engineer.json()["detail"] == "recruiter_required"
    assert CONTACT not in engineer.text
    assert "Ledger work" not in engineer.text
    assert missing.status_code == 401
    assert search.status_code == 403
    assert reports.status_code == 200

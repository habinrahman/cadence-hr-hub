"""GET /candidates lists confirmed profiles for recruiters and writes nothing to the audit trail."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bootstrap import provision
from app.main import app
from app.models import AuditEvent, Candidate, CandidateDocument, CandidateSkill
from tests.test_mail import ENGINEER, RECRUITER
from tests.test_search_filters import _profile


def test_list_is_recruiter_only_and_read_only(session):
    provision(session)
    candidate = _profile(session)
    document = session.scalars(select(CandidateDocument)).one()
    for name in ("Python", "SQL", "Python"):
        session.add(
            CandidateSkill(
                candidate_id=candidate.id,
                source_document_id=document.id,
                name=name,
                normalized_name=name.casefold(),
            )
        )
    session.add(Candidate(source="upload", display_name="Unconfirmed"))
    session.commit()
    before = session.scalar(select(func.count()).select_from(AuditEvent))
    with TestClient(app) as client:
        denied = client.get("/candidates", headers=ENGINEER)
        listed = client.get("/candidates", headers=RECRUITER)
        bad = client.get("/candidates", params={"limit": 500}, headers=RECRUITER)
    session.expire_all()
    assert denied.status_code == 403
    assert bad.status_code == 422
    body = listed.json()
    assert body["total"] == 1
    row = body["candidates"][0]
    assert row["candidate_id"] == str(candidate.id)
    assert row["candidate_name"] == "Ada Lovelace"
    assert row["latest_title"] == "Engineer"
    assert row["skills"] == ["Python", "SQL"]
    assert row["years_of_experience"] == 3.0
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == before


def test_list_pages_and_empty(session):
    provision(session)
    with TestClient(app) as client:
        empty = client.get("/candidates", headers=RECRUITER).json()
        assert empty["total"] == 0 and empty["candidates"] == []
        _profile(session)
        past_end = client.get("/candidates", params={"offset": 5}, headers=RECRUITER).json()
    assert past_end["total"] == 1 and past_end["candidates"] == []

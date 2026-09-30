"""Search filters added for job title, industry text, and nationality words in a CV."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.bootstrap import provision
from app.main import app
from app.models import Candidate, CandidateDocument, CandidateExperience, DocumentChunk
from app.services.search import hybrid_search
from tests.test_mail import ENGINEER, RECRUITER


def _profile(session):
    candidate = Candidate(source="upload", display_name="Ada Lovelace", years_of_experience=3)
    session.add(candidate)
    session.flush()
    document = CandidateDocument(
        candidate_id=candidate.id,
        sha256="c" * 64,
        original_filename="ada.pdf",
        media_type="application/pdf",
        byte_size=40,
        storage_key="search/ada",
        status="profiled",
        is_current=True,
        processing_version=1,
        received_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    session.add(document)
    session.flush()
    session.add(
        CandidateExperience(
            candidate_id=candidate.id,
            source_document_id=document.id,
            employer="Analytical Engines",
            title="Engineer",
            description="Reconcile ledger accounts",
        )
    )
    session.add(
        DocumentChunk(
            document_id=document.id,
            chunk_index=0,
            content="Reconcile ledger accounts. The CV states Bahraini.",
            content_hash="d" * 64,
        )
    )
    session.commit()
    return candidate


def test_new_filters_do_not_change_experience_or_store_nationality(session):
    candidate = _profile(session)
    assert "nationality" not in inspect(Candidate).columns
    assert hybrid_search(session, experience="Analytical Engines")[0].candidate_id == candidate.id
    assert hybrid_search(session, experience="ledger") == []
    assert hybrid_search(session, job_title="Analytical Engines") == []
    titled = hybrid_search(session, job_title="Engineer")
    assert titled[0].candidate_id == candidate.id
    assert titled[0].reasons == ["job_title"]
    assert titled[0].evidence == "Engineer"
    industry = hybrid_search(session, industry="ledger")
    assert industry[0].candidate_id == candidate.id
    assert industry[0].reasons == ["industry"]
    assert "ledger" in industry[0].evidence.casefold()
    nation = hybrid_search(session, nationality="Bahraini")
    assert nation[0].candidate_id == candidate.id
    assert nation[0].reasons == ["nationality"]
    assert "Bahraini" in nation[0].evidence
    keyword = hybrid_search(session, query="ledger")
    assert keyword[0].candidate_id == candidate.id
    assert "keyword" in keyword[0].reasons
    assert keyword[0].chunk_id is not None


def test_search_is_recruiter_only_and_returns_the_visible_fields(session):
    provision(session)
    candidate = _profile(session)
    with TestClient(app) as client:
        denied = client.get("/search", params={"job_title": "Engineer"}, headers=ENGINEER)
        found = client.get("/search", params={"job_title": "Engineer"}, headers=RECRUITER)
    assert denied.status_code == 403
    assert denied.json()["detail"] == "recruiter_required"
    assert found.status_code == 200
    hit = found.json()["results"][0]
    assert hit["candidate_id"] == str(candidate.id)
    assert hit["candidate_name"] == "Ada Lovelace"
    assert hit["document_id"]
    assert hit["evidence"] == "Engineer"
    assert hit["reasons"] == ["job_title"]

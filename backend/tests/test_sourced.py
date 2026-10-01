"""Sourced candidates use the same relationship review as a CV upload."""

import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.bootstrap import provision
from app.jobs.queue import run_once
from app.main import app
from app.models import AuditEvent, Candidate, CandidateSource, DuplicateReview
from app.services.pipeline import run_extract
from tests.test_intelligence import _run, make_pdf
from tests.test_mail import ENGINEER, RECRUITER

ADA = """Ada Lovelace
ada@example.com
+14155550199
Experience
Analytical Engines, Engineer
2020-01-01 to 2022-01-01
Reconcile ledger accounts for the public engine team
Education
University of Example, BSc Mathematics
Skills
Python, SQL
"""

SAM = """Sam Sourced
sam.sourced@example.com
+14155552611
Experience
North Workshop, Builder
2019-06-01 to 2023-06-01
Built shelves and inventory tools for the workshop floor each season
Education
Workshop College, BSc
Skills
Woodwork
"""

NOTES = "Ask the referrer before calling ada@example.com"


def _process(session) -> None:
    def handler(db, job):
        run_extract(db, job)

    run_once(session, worker_id="source-test", handler=handler)


def _post(client, pdf: bytes, **fields):
    data = {
        "name": "Sam Sourced",
        "email": "",
        "phone": "",
        "source_type": "linkedin",
        "source_reference": "https://www.linkedin.com/in/example",
        "notes": NOTES,
    }
    data.update(fields)
    return client.post(
        "/sourced-candidates",
        headers=RECRUITER,
        data=data,
        files={"file": ("sourced.pdf", pdf, "application/pdf")},
    )


def test_recruiter_is_required_to_add_a_sourced_candidate(session):
    _run(session, "ada.pdf", make_pdf(ADA))
    with TestClient(app) as client:
        denied = client.post(
            "/sourced-candidates",
            headers=ENGINEER,
            data={"name": "Sam Sourced", "source_type": "referral", "source_reference": "A colleague"},
            files={"file": ("sourced.pdf", make_pdf(SAM), "application/pdf")},
        )
    assert denied.status_code == 403
    assert denied.json()["detail"] == "recruiter_required"


def test_sourced_entry_rejects_incomplete_or_invalid_fields(session):
    _run(session, "ada.pdf", make_pdf(ADA))
    pdf = make_pdf(SAM)
    with TestClient(app) as client:
        missing_name = _post(client, pdf, name="  ")
        bad_email = _post(client, pdf, email="not-an-email")
        bad_type = _post(client, pdf, source_type="twitter")
        bad_phone = _post(client, pdf, phone="123")
        missing_file = client.post(
            "/sourced-candidates",
            headers=RECRUITER,
            data={"name": "Sam Sourced", "source_type": "referral", "source_reference": "A colleague"},
        )
    assert missing_name.status_code == 422
    assert missing_name.json()["detail"] == "invalid_name"
    assert bad_email.json()["detail"] == "invalid_email"
    assert bad_type.json()["detail"] == "invalid_source_type"
    assert bad_phone.json()["detail"] == "invalid_phone"
    # No CV is not an error: the person is recorded as a lead (see the lead tests below).
    assert missing_file.status_code == 201
    assert missing_file.json()["document_id"] is None
    assert session.scalar(select(func.count()).select_from(CandidateSource)) == 1


def test_declared_email_opens_the_same_review_and_does_not_create_a_profile(session):
    existing = _run(session, "ada.pdf", make_pdf(ADA))
    assert existing.candidate_id is not None
    with TestClient(app) as client:
        created = _post(client, make_pdf(SAM), email="ada@example.com", source_type="referral", source_reference="Jordan at Example Labs")
        assert created.status_code == 201
        source_id = created.json()["id"]
    _process(session)
    session.expire_all()
    row = session.get(CandidateSource, source_id)
    document = session.get(type(existing), row.document_id)
    assert document.status == "needs_review"
    assert document.candidate_id is None
    assert row.candidate_id is None
    assert session.scalar(select(func.count()).select_from(Candidate)) == 1
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == row.document_id))
    assert review.status == "pending"
    assert any(item["code"] == "email" and item["state"] == "matched" for item in review.signals["evidence"])
    detected = session.scalar(select(AuditEvent).where(AuditEvent.action == "sourced_duplicate_detected"))
    attached = session.scalar(select(AuditEvent).where(AuditEvent.action == "sourced_cv_attached"))
    assert detected.detail["relationship"] == document.identity_outcome
    assert attached.detail["source_type"] == "referral"
    rendered = json.dumps(detected.detail) + json.dumps(attached.detail)
    assert NOTES not in rendered
    assert "@" not in rendered
    with TestClient(app) as client:
        decision = client.post(
            f"/reviews/{review.id}/decision",
            headers=RECRUITER,
            json={"action": "accept_update", "candidate_id": str(existing.candidate_id)},
        )
        assert decision.status_code == 200
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Candidate)) == 1
    assert session.get(CandidateSource, source_id).candidate_id == existing.candidate_id
    assert session.get(CandidateSource, source_id).source_reference == "Jordan at Example Labs"
    decided = session.scalar(select(AuditEvent).where(AuditEvent.action == "sourced_review_decided"))
    assert decided.detail["human_action"] == "accept_update"
    assert "@" not in json.dumps(decided.detail)


def test_a_new_sourced_candidate_keeps_the_source(session):
    provision(session)
    session.commit()
    with TestClient(app) as client:
        created = _post(
            client,
            make_pdf(SAM),
            email="sam.sourced@example.com",
            phone="+14155552611",
            source_type="linkedin",
            source_reference="LinkedIn search, backend",
        )
        assert created.status_code == 201
        source_id = created.json()["id"]
    _process(session)
    session.expire_all()
    row = session.get(CandidateSource, source_id)
    candidate = session.get(Candidate, row.candidate_id)
    assert candidate.source == "linkedin"
    assert candidate.display_name == "Sam Sourced"
    assert row.source_reference == "LinkedIn search, backend"
    assert row.notes == NOTES
    created_event = session.scalar(select(AuditEvent).where(AuditEvent.action == "sourced_candidate_created"))
    assert created_event.detail["candidate_id"] == str(candidate.id)
    assert created_event.detail["source_type"] == "linkedin"
    assert "@" not in json.dumps(created_event.detail)
    assert session.scalar(select(AuditEvent).where(AuditEvent.action == "sourced_duplicate_detected")) is None


# ---------- a lead with no CV yet (a LinkedIn profile, a referral) ----------


def _lead(client, **fields):
    data = {"name": "Lena Lead", "source_type": "linkedin", "source_reference": "linkedin.com/in/lena-lead"}
    data.update(fields)
    return client.post("/sourced-candidates", headers=RECRUITER, data=data)


def test_a_lead_without_a_cv_creates_a_findable_profile_that_keeps_its_source(session):
    provision(session)
    session.commit()
    with TestClient(app) as client:
        created = _lead(client, email="lena@example.com", phone="+1 415 555 0101", notes="Met at a meetup")
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["document_id"] is None
        assert body["source_type"] == "linkedin"
        assert body["source_reference"] == "linkedin.com/in/lena-lead"
        profile = client.get(f"/candidates/{body['candidate_id']}", headers=RECRUITER).json()
        found = client.get("/search", params={"name": "Lena"}, headers=RECRUITER).json()["results"]
        listed = client.get("/candidates", headers=RECRUITER).json()["candidates"]
    assert profile["display_name"] == "Lena Lead"
    assert [hit["candidate_id"] for hit in found] == [body["candidate_id"]]
    assert any(item["candidate_id"] == body["candidate_id"] for item in listed)
    audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "sourced_candidate_created"))
    assert audit.detail["human_action"] == "create_new"
    assert "@" not in json.dumps(audit.detail)


def test_a_lead_matching_an_existing_profile_is_never_created_or_merged_silently(session):
    existing = _run(session, "ada.pdf", make_pdf(ADA))
    provision(session)
    session.commit()
    before = session.scalar(select(func.count()).select_from(Candidate))
    with TestClient(app) as client:
        held = _lead(client, name="Ada Lovelace", email="ada@example.com")
        assert held.status_code == 409
        detail = held.json()["detail"]
        assert detail["code"] == "possible_existing"
        assert detail["matches"][0]["candidate_id"] == str(existing.candidate_id)
        assert "same_email" in detail["matches"][0]["reasons"]
        session.expire_all()
        assert session.scalar(select(func.count()).select_from(Candidate)) == before
        assert session.scalar(select(func.count()).select_from(CandidateSource)) == 0
        # A profile the check did not find cannot receive the lead.
        stray = _lead(client, name="Ada Lovelace", email="ada@example.com", attach_to="00000000-0000-0000-0000-000000000001")
        assert stray.status_code == 409
        # The recruiter chooses: add the source to the profile the check found.
        attached = _lead(client, name="Ada Lovelace", email="ada@example.com", attach_to=str(existing.candidate_id))
        assert attached.status_code == 201
        assert attached.json()["candidate_id"] == str(existing.candidate_id)
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Candidate)) == before
    assert session.get(Candidate, existing.candidate_id).merged_into_id is None


def test_a_recruiter_can_confirm_a_new_profile_for_a_same_name_stranger(session):
    existing = _run(session, "ada.pdf", make_pdf(ADA))
    session.get(Candidate, existing.candidate_id).display_name = "Ada Lovelace"
    provision(session)
    session.commit()
    before = session.scalar(select(func.count()).select_from(Candidate))
    with TestClient(app) as client:
        assert _lead(client, name="Ada Lovelace", email="another.ada@example.org").status_code == 409
        confirmed = _lead(client, name="Ada Lovelace", email="another.ada@example.org", create_new="true")
    assert confirmed.status_code == 201
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Candidate)) == before + 1


def test_engineer_cannot_add_a_lead(session):
    provision(session)
    session.commit()
    with TestClient(app) as client:
        denied = client.post(
            "/sourced-candidates",
            headers=ENGINEER,
            data={"name": "Lena Lead", "source_type": "linkedin", "source_reference": "x"},
        )
    assert denied.status_code == 403

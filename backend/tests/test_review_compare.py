"""The comparison workspace reads two stored CVs. It never decides, stores or changes anything."""

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.jobs.queue import run_once
from app.main import app
from app.models import (
    AuditEvent,
    Candidate,
    CandidateDocument,
    DocumentPage,
    DuplicateReview,
    ExcelImport,
    ExcelImportRow,
    User,
)
from app.services.ingest import ingest_bytes
from app.services.pipeline import run_extract
from tests.test_foundation import ENGINEER, RECRUITER, _actor, make_pdf

OLD = """Barak Buta
barak@example.com
+14155550123
Experience
Acme Corp, Software Engineer
2023-01-01 to 2025-01-01
Education
State University, BSc Computer Science
Skills
Python, React
"""

NEW = """Barak Buta
barak@example.com
+14155550123
Revised 2026-09-01
Experience
Acme Corp, Software Engineer
2023-01-01 to 2025-01-01
Google, Senior Engineer
2025-01-01 to present
Education
State University, BSc Computer Science
Skills
Python, React, FastAPI
"""

NO_SKILLS = """Barak Buta
barak@example.com
+14155550123
Experience
Acme Corp, Software Engineer
2023-01-01 to 2025-01-01
Education
State University, BSc Computer Science
"""


def _pair(session, old_text: str, new_text: str):
    """Ingest an older CV, then a second file for the same person, and return the opened review."""
    actor = _actor(session)
    first = ingest_bytes(session, filename="resume_2025.pdf", data=make_pdf(old_text), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    second = ingest_bytes(session, filename="resume_2026.pdf", data=make_pdf(new_text), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == second.document.id))
    assert review is not None, "the second CV should have opened a relationship review"
    return review, first.document, second.document


def _get(review_id, headers=RECRUITER, **params):
    with TestClient(app) as client:
        return client.get(f"/reviews/{review_id}/comparison", headers=headers, params=params)


def _field(body, key):
    return next(item for item in body["fields"] if item["key"] == key)


def test_added_and_same_items_carry_source_evidence(session):
    review, old, new = _pair(session, OLD, NEW)
    response = _get(review.id)
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["existing"]["document"]["id"] == str(old.id)
    assert body["incoming"]["document"]["id"] == str(new.id)

    experience = _field(body, "experience")
    assert experience["comparable"] is True
    by_label = {item["label"]: item for item in experience["items"]}
    acme = next(v for k, v in by_label.items() if k.startswith("Acme Corp"))
    google = next(v for k, v in by_label.items() if k.startswith("Google"))
    assert acme["status"] == "same"
    assert google["status"] == "added"
    assert google["incoming"]["evidence"]["page"] == 1
    assert "Google" in google["incoming"]["evidence"]["quote"]
    assert google["existing"] is None

    skills = {item["label"]: item["status"] for item in _field(body, "skills")["items"]}
    assert skills == {"Python": "same", "React": "same", "FastAPI": "added"}
    education = _field(body, "education")
    assert [item["status"] for item in education["items"]] == ["same"]
    assert {item["status"] for item in _field(body, "email")["items"]} == {"same"}
    assert {item["status"] for item in _field(body, "phone")["items"]} == {"same"}


def test_date_shaped_text_is_never_reported_as_a_phone_number(session):
    # A job that starts on 2025-06-01 must not surface as a "new phone number" (the pipeline's finder matches such dates).
    newer = NEW.replace("2025-01-01 to present", "2025-06-01 to present")
    review, _old, _new = _pair(session, OLD, newer)
    phones = _field(_get(review.id).json(), "phone")
    assert [item["label"] for item in phones["items"]] == ["+14155550123"]
    assert {item["status"] for item in phones["items"]} == {"same"}


def test_a_section_missing_from_one_cv_is_unknown_never_removed(session):
    review, _old, _new = _pair(session, OLD, NO_SKILLS)
    body = _get(review.id).json()
    skills = _field(body, "skills")
    assert skills["comparable"] is False
    assert skills["existing_state"] == "extracted"
    assert skills["incoming_state"] == "not_extracted"
    assert {item["status"] for item in skills["items"]} == {"unknown"}
    # Nothing anywhere may claim that something was removed when the parser simply found nothing.
    statuses = {item["status"] for field in body["fields"] for item in field["items"]}
    assert "removed" not in statuses and "only_existing" not in statuses or _field(body, "skills")["comparable"] is False
    assert all(item["status"] == "unknown" for item in skills["items"])


def test_dates_are_read_from_the_text_and_the_filename_is_ignored(session):
    review, _old, _new = _pair(session, OLD, NEW)
    dates = _get(review.id).json()["dates"]
    assert dates["incoming"]["labelled_version"]["date"] == "2026-09-01"
    assert dates["incoming"]["labelled_version"]["page"] == 1
    assert dates["existing"]["labelled_version"] is None
    assert dates["incoming"]["latest_mentioned"]["date"] == "2026-09-01"
    assert dates["uploaded"]["incoming"]
    assert dates["conflict"] is False


def test_conflicting_date_evidence_is_reported(session):
    older_label = OLD + "Revised 2026-01-01\n"
    newer_mention = NEW.replace("Revised 2026-09-01", "Revised 2025-01-01").replace("to present", "to 2026-06-01")
    review, _old, _new = _pair(session, older_label, newer_mention)
    dates = _get(review.id).json()["dates"]
    # The labelled version date says the existing CV is newer; the latest date mentioned says the incoming one is.
    assert dates["newer_by_labelled"] == "existing"
    assert dates["newer_by_mentioned"] == "incoming"
    assert dates["conflict"] is True


def test_identical_text_reports_no_text_differences(session):
    actor = _actor(session)
    first = ingest_bytes(session, filename="a.pdf", data=make_pdf(OLD), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    second = ingest_bytes(session, filename="b.pdf", data=make_pdf(OLD) + b"\n% different bytes\n", actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == second.document.id))
    body = _get(review.id).json()
    assert first.document.id != second.document.id
    assert body["text_diff"]["available"] is True
    assert body["text_diff"]["incoming_only"] == []
    assert body["text_diff"]["existing_only"] == []
    assert {item["status"] for field in body["fields"] for item in field["items"]} <= {"same"}


def test_text_differences_list_only_lines_found_in_one_document(session):
    review, _old, _new = _pair(session, OLD, NEW)
    diff = _get(review.id).json()["text_diff"]
    incoming_only = " ".join(row["text"] for row in diff["incoming_only"])
    assert "Google, Senior Engineer" in incoming_only
    assert "FastAPI" in incoming_only
    # An edited line ("Python, React" became "Python, React, FastAPI") shows on both sides, which the note explains.
    assert [row["text"] for row in diff["existing_only"]] == ["Python, React"]
    assert diff["note"]


def test_missing_pages_make_the_structured_comparison_unavailable_not_empty(session):
    review, _old, new = _pair(session, OLD, NEW)
    session.execute(delete(DocumentPage).where(DocumentPage.document_id == new.id))
    session.commit()
    body = _get(review.id).json()
    assert body["incoming"]["state"] == "no_text"
    skills = _field(body, "skills")
    assert skills["comparable"] is False
    assert skills["incoming_state"] == "unavailable"
    assert body["text_diff"]["available"] is False


def test_recruiter_only_and_no_candidate_data_for_other_roles(session):
    review, _old, _new = _pair(session, OLD, NEW)
    with TestClient(app) as client:
        anonymous = client.get(f"/reviews/{review.id}/comparison")
        engineer = client.get(f"/reviews/{review.id}/comparison", headers=ENGINEER)
        missing = client.get("/reviews/00000000-0000-4000-8000-000000000000/comparison", headers=RECRUITER)
        bad_candidate = client.get(
            f"/reviews/{review.id}/comparison",
            headers=RECRUITER,
            params={"candidate_id": "00000000-0000-4000-8000-000000000000"},
        )
        malformed = client.get("/reviews/not-a-uuid/comparison", headers=RECRUITER)
    assert anonymous.status_code == 401
    assert engineer.status_code == 403
    assert "barak@example.com" not in engineer.text and "Google" not in engineer.text
    assert missing.status_code == 404
    assert bad_candidate.status_code == 404
    assert malformed.status_code == 422


def test_viewing_the_comparison_is_audited_without_cv_text(session):
    review, _old, _new = _pair(session, OLD, NEW)
    assert _get(review.id).status_code == 200
    session.expire_all()
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "review_comparison_viewed"))
    assert event is not None
    assert event.actor_kind == "user"
    assert event.entity_id == review.id
    assert set(event.detail) <= {"review_id", "count"}
    assert "@" not in str(event.detail) and "Google" not in str(event.detail)


def test_reading_never_changes_the_review_or_documents(session):
    review, old, new = _pair(session, OLD, NEW)
    before = (review.status, old.is_current, new.is_current, new.candidate_id, session.query(Candidate).count())
    for _ in range(3):
        assert _get(review.id).status_code == 200
    session.expire_all()
    review = session.get(DuplicateReview, review.id)
    old = session.get(CandidateDocument, old.id)
    new = session.get(CandidateDocument, new.id)
    after = (review.status, old.is_current, new.is_current, new.candidate_id, session.query(Candidate).count())
    assert before == after
    assert review.status == "pending"
    assert new.candidate_id is None


def test_a_decided_review_can_still_be_read_and_says_so(session):
    review, old, new = _pair(session, OLD, NEW)
    with TestClient(app) as client:
        decided = client.post(f"/reviews/{review.id}/decision", json={"action": "accept_update"}, headers=RECRUITER)
        again = client.post(f"/reviews/{review.id}/decision", json={"action": "record_duplicate"}, headers=RECRUITER)
        body = client.get(f"/reviews/{review.id}/comparison", headers=RECRUITER).json()
    assert decided.status_code == 200
    assert again.status_code == 409
    assert body["status"] == "accepted_update"
    assert body["decided_at"]
    assert "review_decided" in body["warnings"]
    session.expire_all()
    # Both documents are kept. Accepting the update only changes which one is current.
    assert session.get(CandidateDocument, old.id) is not None
    assert session.get(CandidateDocument, new.id).is_current is True
    assert session.get(CandidateDocument, old.id).is_current is False


def test_a_merged_candidate_is_flagged(session):
    review, _old, _new = _pair(session, OLD, NEW)
    candidate = session.get(Candidate, review.candidate_id)
    other = Candidate(source="upload", display_name="Someone Else")
    session.add(other)
    session.flush()
    candidate.merged_into_id = other.id
    session.commit()
    body = _get(review.id).json()
    assert "candidate_merged" in body["warnings"]
    assert body["candidate"]["merged_into_id"] == str(other.id)


def test_a_spreadsheet_review_has_no_documents_to_compare(session):
    actor = _actor(session)
    user = session.get(User, actor.user_id)
    batch = ExcelImport(
        actor_user_id=user.id,
        sheet_count=1,
        row_count=1,
        valid_count=1,
        invalid_count=0,
        duplicate_count=0,
        relationship_count=1,
        created_count=0,
        ignored_column_count=0,
    )
    session.add(batch)
    session.flush()
    row = ExcelImportRow(import_id=batch.id, row_number=1, outcome="existing_relationship", error_codes=[])
    session.add(row)
    session.flush()
    review = DuplicateReview(
        document_id=None,
        excel_import_row_id=row.id,
        status="pending",
        proposed_outcome="updated_cv",
        likely_relationship="updated_cv",
        offered_actions=["accept_update"],
        signals={"ambiguous": False, "candidate_ids": [], "evidence": [], "source": "excel"},
    )
    session.add(review)
    session.commit()
    body = _get(review.id).json()
    assert body["available"] is False
    assert body["reason"] == "excel_row"
    assert body["incoming"] is None


def test_pages_are_recruiter_only_and_audited(session):
    _review, _old, new = _pair(session, OLD, NEW)
    with TestClient(app) as client:
        anonymous = client.get(f"/documents/{new.id}/pages")
        engineer = client.get(f"/documents/{new.id}/pages", headers=ENGINEER)
        recruiter = client.get(f"/documents/{new.id}/pages", headers=RECRUITER)
        missing = client.get("/documents/00000000-0000-4000-8000-000000000000/pages", headers=RECRUITER)
    assert anonymous.status_code == 401
    assert engineer.status_code == 403 and "Google" not in engineer.text
    assert missing.status_code == 404
    assert recruiter.status_code == 200
    pages = recruiter.json()["pages"]
    assert pages[0]["number"] == 1
    assert "Google, Senior Engineer" in pages[0]["text"]
    session.expire_all()
    event = session.scalar(select(AuditEvent).where(AuditEvent.action == "pii_text_access"))
    assert event is not None and event.detail == {"count": len(pages)}

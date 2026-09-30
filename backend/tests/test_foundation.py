import io
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import docx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from app.bootstrap import provision
from app.domain.actor import AGENT, Actor
from app.domain.transitions import TransitionError
from app.extraction.draft import ExtractionDraft
from app.jobs.errors import PermanentJobError
from app.jobs.queue import claim_next, enqueue_extract, run_once
from app.main import app
from app.models import (
    AgentRun,
    Candidate,
    CandidateContact,
    CandidateDocument,
    DocumentChunk,
    DuplicateReview,
    Job,
)
from app.services.ingest import ingest_bytes
from app.services.locks import lock_field
from app.services.pipeline import run_extract
from app.services.reviews import decide_duplicate_review

RECRUITER = {"Authorization": "Bearer dev-recruiter-token"}
ENGINEER = {"Authorization": "Bearer dev-engineer-token"}


def make_pdf(text: str, *, password: str | None = None) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    y = 72
    for line in text.splitlines():
        page.insert_text((72, y), line)
        y += 16
    if password:
        data = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw=password,
            owner_pw=password,
        )
    else:
        data = document.tobytes()
    document.close()
    return data


def make_docx(text: str) -> bytes:
    buffer = io.BytesIO()
    document = docx.Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


BODY = (
    "Ada Lovelace\nada@example.com\n+14155550199\n"
    "Analytical engines and careful notes about computation. " * 4
)


class NamingExtractor:
    model_name = "test-extractor"

    def __init__(self, name: str) -> None:
        self.name = name

    def extract(self, *, document_id, source_text: str, prompt_version: str) -> ExtractionDraft:
        return ExtractionDraft(display_name=self.name, display_name_quote=self.name)


def _actor(session) -> Actor:
    provision(session)
    from app.models import User

    user = session.scalar(select(User).where(User.role == "recruiter"))
    return Actor(kind="user", user_id=user.id)


def test_same_bytes_are_one_document(session):
    actor = _actor(session)
    data = make_pdf(BODY)
    first = ingest_bytes(session, filename="Updated CV.pdf", data=data, actor=actor)
    second = ingest_bytes(session, filename="copy.pdf", data=data, actor=actor)
    session.commit()
    assert first.created is True
    assert second.created is False
    assert first.document.id == second.document.id
    assert session.scalar(select(func.count()).select_from(Job)) == 1
    from app.models import AuditEvent

    same = session.scalar(select(AuditEvent).where(AuditEvent.action == "same_document"))
    assert same is not None
    assert same.detail["identity_outcome"] == "same_document"


def test_extract_does_not_trust_filename_and_keeps_pii_out_of_the_trace(session):
    actor = _actor(session)
    result = ingest_bytes(session, filename="Updated CV.pdf", data=make_pdf(BODY), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    document = session.get(CandidateDocument, result.document.id)
    assert document.status == "extracted"
    assert document.candidate_id is not None
    candidate = session.get(Candidate, document.candidate_id)
    assert candidate.display_name is None
    contact = session.scalar(select(CandidateContact).where(CandidateContact.candidate_id == candidate.id, CandidateContact.kind == "email"))
    assert contact.value_normalized == "ada@example.com"
    run = session.scalar(select(AgentRun))
    visible = " ".join(
        str(value)
        for value in (
            run.agent_name,
            run.model,
            run.prompt_version,
            run.input_hash,
            run.output_ref,
            run.validation_result,
            run.status,
            run.error_code,
        )
    )
    assert "ada@example.com" not in visible
    assert "Ada Lovelace" not in visible


def test_exact_email_recommends_an_update_and_does_not_merge(session):
    from datetime import date

    from app.models import Application, AuditEvent

    actor = _actor(session)
    first = ingest_bytes(session, filename="a.pdf", data=make_pdf(BODY), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    application = session.scalar(select(Application))
    application.application_date = date(2020, 1, 1)
    session.commit()
    other = BODY.replace("Analytical engines", "Analytical engines\n2026-09-01")
    second = ingest_bytes(session, filename="Updated CV.pdf", data=make_pdf(other), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    documents = session.scalars(select(CandidateDocument)).all()
    assert len(documents) == 2
    incoming = session.get(CandidateDocument, second.document.id)
    assert incoming.candidate_id is None
    assert incoming.status == "needs_review"
    original = session.get(CandidateDocument, first.document.id)
    assert original.is_current is True
    review = session.scalar(select(DuplicateReview))
    assert review.likely_relationship == "updated_cv"
    assert float(review.confidence) >= 96
    assert review.recommended_action == "accept_update"
    assert review.offered_actions == ["accept_update"]
    evidence = {item["code"]: item for item in review.signals["evidence"]}
    assert evidence["email"]["state"] == "matched"
    assert evidence["phone"]["state"] == "matched"
    assert evidence["cv_dates"]["state"] == "matched"
    assert evidence["semantic"]["state"] == "unknown"
    assert evidence["document_hash"]["state"] == "unmatched"
    assert evidence["document_hash"]["weight"] == 0.0
    assert "filename" not in evidence
    assert "@" not in str(review.signals)
    opened = session.scalar(select(AuditEvent).where(AuditEvent.action == "duplicate_review_opened"))
    assert opened.detail["recommended_action"] == "accept_update"
    assert opened.detail["relationship"] == "updated_cv"
    session.commit()
    with TestClient(app) as client:
        visible = client.get(f"/documents/{incoming.id}/review", headers=RECRUITER)
        assert visible.status_code == 200
        assert visible.json()["evidence"]
        decided = client.post(
            f"/reviews/{review.id}/decision",
            json={"action": "accept_update"},
            headers=RECRUITER,
        )
        assert decided.status_code == 200
    session.expire_all()
    documents = session.scalars(select(CandidateDocument)).all()
    assert len({row.candidate_id for row in documents}) == 1
    current = [row for row in documents if row.is_current]
    assert len(current) == 1
    assert current[0].id == second.document.id
    kept = [row for row in documents if not row.is_current]
    assert len(kept) == 1
    decided_audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "duplicate_review_decided"))
    assert decided_audit.detail["human_action"] == "accept_update"
    assert "ada@example.com" not in str(decided_audit.detail)


def test_corrupt_file_is_quarantined_and_does_not_block_the_next_file(session):
    actor = _actor(session)
    bad = ingest_bytes(session, filename="bad.pdf", data=b"%PDF-1.7\nnot a pdf", actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    bad_document = session.get(CandidateDocument, bad.document.id)
    assert bad_document.status == "quarantined"
    assert bad_document.error_code == "corrupt_pdf"
    good = ingest_bytes(session, filename="good.pdf", data=make_pdf(BODY), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    good_document = session.get(CandidateDocument, good.document.id)
    assert good_document.status == "extracted"
    assert good_document.candidate_id is not None


def test_encrypted_pdf_is_quarantined(session):
    actor = _actor(session)
    result = ingest_bytes(session, filename="protected.pdf", data=make_pdf(BODY, password="secret"), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    document = session.get(CandidateDocument, result.document.id)
    assert document.status == "quarantined"
    assert document.error_code == "encrypted_pdf"


def test_docx_extraction(session):
    actor = _actor(session)
    result = ingest_bytes(session, filename="cv.docx", data=make_docx(BODY), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    document = session.get(CandidateDocument, result.document.id)
    assert document.status == "extracted"
    assert document.text_source == "docx"


def test_field_lock_survives_reprocessing(session):
    actor = _actor(session)

    def handler(db, job):
        run_extract(db, job, extractor=NamingExtractor("Ada Lovelace"))

    first = ingest_bytes(session, filename="a.pdf", data=make_pdf(BODY), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=handler)
    document = session.get(CandidateDocument, first.document.id)
    candidate = session.get(Candidate, document.candidate_id)
    assert candidate.display_name == "Ada Lovelace"
    lock_field(
        session,
        candidate_id=candidate.id,
        entity_type="candidate",
        entity_id=None,
        field_name="display_name",
        locked_by=actor.user_id,
    )
    session.commit()
    other = BODY.replace("Ada Lovelace", "Ada Lovelace Byron")
    ingest_bytes(session, filename="Updated CV.pdf", data=make_pdf(other), actor=actor)
    session.commit()

    def rename(db, job):
        run_extract(db, job, extractor=NamingExtractor("Ada Lovelace Byron"))

    run_once(session, worker_id="worker-a", handler=rename)
    session.refresh(candidate)
    assert candidate.display_name == "Ada Lovelace"
    second_document = session.scalar(
        select(CandidateDocument).where(CandidateDocument.id != document.id)
    )
    assert second_document.candidate_id is None
    from app.services.apply_draft import apply_draft

    apply_draft(
        session,
        candidate=candidate,
        document_id=second_document.id,
        pages=[other],
        chunks=[],
        draft=ExtractionDraft(display_name="Ada Lovelace Byron", display_name_quote="Ada Lovelace Byron"),
        agent_run_id=None,
    )
    session.refresh(candidate)
    assert candidate.display_name == "Ada Lovelace"
    from app.models import AuditEvent

    kept = session.scalar(select(AuditEvent).where(AuditEvent.action == "field_lock_kept"))
    assert kept is not None
    assert kept.detail["field"] == "display_name"


def test_conflicting_email_and_phone_open_a_review(session):
    actor = _actor(session)
    first = Candidate(source="upload", display_name="Ada Lovelace")
    second = Candidate(source="upload", display_name="Grace Hopper")
    session.add_all([first, second])
    session.flush()
    session.add(CandidateContact(candidate_id=first.id, kind="email", value_raw="ada@example.com", value_normalized="ada@example.com"))
    session.add(CandidateContact(candidate_id=second.id, kind="phone", value_raw="+14155550199", value_normalized="14155550199"))
    session.commit()
    mixed = "Pat Example\nada@example.com\n+14155550199\n" + ("Careful public notes about engines. " * 4)
    result = ingest_bytes(session, filename="mixed.pdf", data=make_pdf(mixed), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    document = session.get(CandidateDocument, result.document.id)
    assert document.identity_outcome == "ambiguous"
    assert document.candidate_id is None
    review = session.scalar(select(DuplicateReview))
    assert review.status == "pending"
    assert review.recommended_action is None
    assert set(review.offered_actions) == {
        "accept_update",
        "record_duplicate",
        "create_separate_candidate",
    }
    with pytest.raises(TransitionError) as raised:
        decide_duplicate_review(session, review, "accept_update", AGENT)
    assert raised.value.code == "human_required"
    decide_duplicate_review(session, review, "create_separate_candidate", actor)
    session.commit()
    session.refresh(document)
    assert document.candidate_id is not None
    assert document.candidate_id not in {first.id, second.id}
    from app.models import AuditEvent

    decided = session.scalar(select(AuditEvent).where(AuditEvent.action == "duplicate_review_decided"))
    assert decided.detail["human_action"] == "create_separate_candidate"


def test_low_confidence_keeps_the_current_cv_until_a_person_chooses(session):
    from sqlalchemy import delete

    actor = _actor(session)
    first = ingest_bytes(session, filename="a.pdf", data=make_pdf(BODY), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    document = session.get(CandidateDocument, first.document.id)
    candidate = session.get(Candidate, document.candidate_id)
    candidate.display_name = "Turki Aldulami"
    session.execute(delete(CandidateContact).where(CandidateContact.candidate_id == candidate.id))
    session.commit()
    text = "Turki Muhanna Aldulami\n" + ("Public notes about engineering work and projects. " * 3)

    def named(db, job):
        run_extract(db, job, extractor=NamingExtractor("Turki Muhanna Aldulami"))

    second = ingest_bytes(session, filename="notes.pdf", data=make_pdf(text), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=named)
    incoming = session.get(CandidateDocument, second.document.id)
    assert incoming.candidate_id is None
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == incoming.id))
    assert float(review.confidence) < 85
    assert review.recommended_action is None
    assert set(review.offered_actions) == {
        "accept_update",
        "record_duplicate",
        "create_separate_candidate",
    }
    decide_duplicate_review(session, review, "record_duplicate", actor)
    session.commit()
    session.refresh(incoming)
    session.refresh(document)
    assert incoming.candidate_id == candidate.id
    assert incoming.is_current is False
    assert document.is_current is True
    from app.models import AuditEvent

    decided = session.scalar(select(AuditEvent).where(AuditEvent.action == "duplicate_review_decided"))
    assert decided.detail["human_action"] == "record_duplicate"


def test_exact_email_without_dates_still_waits_for_hr(session):
    actor = _actor(session)
    first = ingest_bytes(session, filename="a.pdf", data=make_pdf(BODY), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    original = session.get(CandidateDocument, first.document.id)
    other = BODY.replace("Analytical engines", "Different analytical engines")
    second = ingest_bytes(session, filename="Updated CV.pdf", data=make_pdf(other), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    incoming = session.get(CandidateDocument, second.document.id)
    assert incoming.candidate_id is None
    assert original.is_current is True
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == incoming.id))
    assert review.likely_relationship == "updated_cv"
    assert float(review.confidence) >= 85
    assert review.recommended_action == "accept_update"
    assert any(item["code"] == "email" and item["state"] == "matched" for item in review.signals["evidence"])


def test_exact_phone_recommends_an_update_and_waits_for_hr(session):
    from app.models import AuditEvent

    actor = _actor(session)
    first = ingest_bytes(session, filename="a.pdf", data=make_pdf(BODY), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    original = session.get(CandidateDocument, first.document.id)
    phone_only = (
        "Ada Lovelace\n+14155550199\n"
        + ("Later public notes about computation and engines. " * 4)
    )
    second = ingest_bytes(session, filename="phone.pdf", data=make_pdf(phone_only), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    incoming = session.get(CandidateDocument, second.document.id)
    assert incoming.candidate_id is None
    assert original.is_current is True
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == incoming.id))
    assert review.likely_relationship == "updated_cv"
    assert float(review.confidence) >= 85
    assert review.recommended_action == "accept_update"
    assert any(item["code"] == "phone" and item["state"] == "matched" for item in review.signals["evidence"])
    decide_duplicate_review(session, review, "accept_update", actor)
    session.commit()
    session.refresh(incoming)
    session.refresh(original)
    assert incoming.candidate_id == original.candidate_id
    assert incoming.is_current is True
    assert original.is_current is False
    decided = session.scalar(select(AuditEvent).where(AuditEvent.action == "duplicate_review_decided"))
    assert decided.detail["human_action"] == "accept_update"


def test_similar_names_with_different_emails_stay_in_review(session):
    actor = _actor(session)
    first = ingest_bytes(session, filename="a.pdf", data=make_pdf(BODY), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=run_extract)
    original = session.get(CandidateDocument, first.document.id)
    candidate = session.get(Candidate, original.candidate_id)
    candidate.display_name = "Turki Muhanna Aldulami"
    session.commit()
    text = (
        "Turki Aldulami\nother@example.com\n"
        + ("Public notes about a different engineering career. " * 3)
    )

    def named(db, job):
        run_extract(db, job, extractor=NamingExtractor("Turki Aldulami"))

    second = ingest_bytes(session, filename="other.pdf", data=make_pdf(text), actor=actor)
    session.commit()
    run_once(session, worker_id="worker-a", handler=named)
    incoming = session.get(CandidateDocument, second.document.id)
    assert incoming.candidate_id is None
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == incoming.id))
    assert review.status == "pending"
    assert review.recommended_action != "accept_update"
    assert float(review.confidence) < 85
    session.refresh(original)
    assert original.is_current is True
    assert original.candidate_id == candidate.id


def test_failed_handler_does_not_keep_partial_chunks(session):
    actor = _actor(session)
    result = ingest_bytes(session, filename="a.pdf", data=make_pdf(BODY), actor=actor)
    session.commit()

    def boom(db, job):
        db.add(
            DocumentChunk(
                document_id=job.document_id,
                chunk_index=0,
                content="this should roll back",
                content_hash="abc",
            )
        )
        db.flush()
        raise PermanentJobError("corrupt_pdf")

    run_once(session, worker_id="worker-a", handler=boom)
    assert session.scalar(select(func.count()).select_from(DocumentChunk)) == 0
    job = session.scalar(select(Job).where(Job.document_id == result.document.id))
    assert job.status == "quarantined"
    document = session.get(CandidateDocument, result.document.id)
    assert document.status == "quarantined"


def test_lease_can_be_reclaimed_after_it_expires(session):
    actor = _actor(session)
    result = ingest_bytes(session, filename="a.pdf", data=make_pdf(BODY), actor=actor)
    session.commit()
    first = claim_next(session, "worker-a")
    session.commit()
    assert claim_next(session, "worker-b") is None
    first.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    session.commit()
    reclaimed = claim_next(session, "worker-b")
    session.commit()
    assert reclaimed.id == first.id
    assert reclaimed.attempts == 2
    assert result.document.id == reclaimed.document_id


def test_job_idempotency_is_a_database_constraint(session):
    actor = _actor(session)
    result = ingest_bytes(session, filename="a.pdf", data=make_pdf(BODY), actor=actor)
    again = enqueue_extract(session, result.document.id)
    session.commit()
    assert again.id == session.scalar(select(Job.id))
    duplicate = Job(
        job_type="extract_document",
        idempotency_key=str(result.document.id),
        processing_version=1,
        document_id=result.document.id,
        payload={"document_id": str(result.document.id)},
        status="queued",
        attempts=0,
        max_attempts=3,
        run_after=datetime.now(timezone.utc),
    )
    session.add(duplicate)
    with pytest.raises(Exception):
        session.flush()
    session.rollback()


def test_upload_and_recruiter_text_access(session):
    provision(session)
    with TestClient(app) as client:
        denied = client.post("/documents", files={"file": ("a.pdf", make_pdf(BODY), "application/pdf")})
        assert denied.status_code == 401
        created = client.post(
            "/documents",
            files={"file": ("Updated CV.pdf", make_pdf(BODY), "application/pdf")},
            headers=RECRUITER,
        )
        assert created.status_code == 201
        document_id = created.json()["id"]
        run_once(session, worker_id="worker-a", handler=run_extract)
        hidden = client.get(f"/documents/{document_id}/text", headers=ENGINEER)
        assert hidden.status_code == 403
        assert "ada@example.com" not in hidden.text
        visible = client.get(f"/documents/{document_id}/text", headers=RECRUITER)
        assert visible.status_code == 200
        assert "ada@example.com" in visible.json()["text"]
        from app.models import AuditEvent

        audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "pii_text_access"))
        assert "ada@example.com" not in str(audit.detail)


def test_schema_has_no_pii_trace_columns_and_no_inferred_attributes(session):
    bind = session.get_bind()
    tables = set(inspect(bind).get_table_names())
    assert "candidate_claims" not in tables
    assert "agent_steps" not in tables
    assert "agent_runs" in tables
    assert "extraction_evidence" in tables
    agent_columns = {column["name"] for column in inspect(bind).get_columns("agent_runs")}
    assert {"input_hash", "output_ref", "validation_result", "model", "prompt_version"} <= agent_columns
    assert agent_columns.isdisjoint({"prompt", "output", "input_text", "raw_text", "source_quote"})
    candidate_columns = {column["name"] for column in inspect(bind).get_columns("candidates")}
    assert candidate_columns.isdisjoint({"nationality", "gender", "religion", "date_of_birth", "age"})
    review_columns = {column["name"] for column in inspect(bind).get_columns("duplicate_reviews")}
    assert {"confidence", "likely_relationship", "recommended_action", "offered_actions"} <= review_columns
    sharing = {column["name"]: column for column in inspect(bind).get_columns("sharing_records")}
    assert sharing["shortlist_id"]["nullable"] is True
    assert len(tables) >= 28

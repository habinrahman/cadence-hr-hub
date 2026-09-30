"""Regression checks for document type, OCR, normalization, and unchanged identity rules."""

import pymupdf
import pytest
from sqlalchemy import func, select

from app.bootstrap import provision
from app.domain.actor import Actor
from app.domain.transitions import TransitionError
from app.extraction.doctype import classify_document
from app.extraction.normalize import normalize_document
from app.extraction.ocr import OcrUnavailable
from app.extraction.pdf import extract_pdf
from app.jobs.queue import run_once
from app.models import (
    AuditEvent,
    Candidate,
    CandidateDocument,
    DocumentChunk,
    DocumentPage,
    DuplicateReview,
    User,
)
from app.services.ingest import ingest_bytes
from app.services.pipeline import run_extract

HEADER = "Ada Lovelace Header"
BODY = (
    "Ada Lovelace\nada@example.com\n+14155550199\n"
    "Analytical engines and careful notes about computation. " * 4
)
INVOICE = (
    "Invoice\nBill to Northwind Supplies\nTotal due 1200\n"
    "Professional services rendered for the listed account items and delivery. " * 2
)
COVER = (
    "Dear hiring manager\nI am writing to express interest in the open role.\n"
    "The enclosed notes describe the work I would like to discuss with you. " * 2
)
JOB = (
    "Job description\nFinance Manager\nResponsibilities\n"
    "Own the monthly close and the control reviews for the team. " * 2
    + "\nSkills\nExperience with ledgers is required for this role.\n"
)
CV_WITH_INVOICE = (
    "Ada Lovelace\nada@example.com\nExperience\nManaged an invoice workflow for a client project.\n"
    "Education\nMathematics\n" + ("Public notes about computation and engines. " * 3)
)
OCR_CV = (
    "Ada Lovelace\nada@example.com\nExperience\nAnalytical engines and careful public notes.\n"
    "Education\nMathematics\n" + ("Further public notes about computation. " * 3)
)


def make_pdf(text: str, *, password: str | None = None) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    y = 72
    for line in text.splitlines():
        page.insert_text((72, y), line)
        y += 16
    if password:
        data = document.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    else:
        data = document.tobytes()
    document.close()
    return data


def make_two_pages(first: str, second: str) -> bytes:
    document = pymupdf.open()
    for text in (first, second):
        page = document.new_page()
        y = 72
        for line in text.splitlines():
            page.insert_text((72, y), line)
            y += 16
    data = document.tobytes()
    document.close()
    return data


def _actor(session) -> Actor:
    provision(session)
    user = session.scalar(select(User).where(User.role == "recruiter"))
    return Actor(kind="user", user_id=user.id)


def _run(session, filename: str, data: bytes, *, ocr=None, extractor=None):
    actor = _actor(session)
    result = ingest_bytes(session, filename=filename, data=data, actor=actor)
    session.commit()

    def handler(db, job):
        run_extract(db, job, ocr=ocr, extractor=extractor)

    run_once(session, worker_id="worker-a", handler=handler)
    document = session.get(CandidateDocument, result.document.id)
    return document


class EmptyOcr:
    def extract_pages(self, data: bytes, media_type: str) -> list[str]:
        return [" \n "]


class ReadableOcr:
    def extract_pages(self, data: bytes, media_type: str) -> list[str]:
        return [OCR_CV]


class MissingOcr:
    def extract_pages(self, data: bytes, media_type: str) -> list[str]:
        raise OcrUnavailable()


def test_invoice_cover_letter_and_job_description_are_not_candidates(session):
    invoice = _run(session, "Updated CV.pdf", make_pdf(INVOICE))
    assert invoice.status == "quarantined"
    assert invoice.error_code == "non_cv_invoice"
    assert invoice.candidate_id is None
    cover = _run(session, "notes.pdf", make_pdf(COVER))
    assert cover.error_code == "non_cv_cover_letter"
    assert cover.candidate_id is None
    role = _run(session, "role.pdf", make_pdf(JOB))
    assert role.error_code == "non_cv_job_description"
    assert role.candidate_id is None
    assert session.scalar(select(func.count()).select_from(Candidate)) == 0
    assert session.scalar(select(func.count()).select_from(DuplicateReview)) == 0


def test_a_cv_that_mentions_invoice_stays_a_candidate(session):
    document = _run(session, "invoice-project.pdf", make_pdf(CV_WITH_INVOICE))
    assert document.status == "extracted"
    assert document.candidate_id is not None
    assert document.error_code is None


def test_blank_scan_does_not_become_a_candidate(session):
    document = _run(session, "blank_scan.pdf", make_pdf(""), ocr=EmptyOcr())
    assert document.status == "needs_ocr"
    assert document.error_code == "insufficient_text"
    assert document.text_source == "ocr"
    assert document.candidate_id is None
    assert session.scalar(select(func.count()).select_from(Candidate)) == 0
    page = session.scalar(select(DocumentPage).where(DocumentPage.document_id == document.id))
    assert page is not None
    assert page.original_text.strip() == ""


def test_ocr_reads_a_scan_and_records_the_page(session):
    document = _run(session, "scan.pdf", make_pdf(""), ocr=ReadableOcr())
    assert document.status == "extracted"
    assert document.text_source == "ocr"
    assert document.candidate_id is not None
    page = session.scalar(select(DocumentPage).where(DocumentPage.document_id == document.id))
    assert "Experience" in page.original_text
    assert "ada@example.com" in page.original_text


def test_missing_ocr_tool_is_an_explicit_status(session):
    document = _run(session, "scan.pdf", make_pdf(""), ocr=MissingOcr())
    assert document.status == "needs_ocr"
    assert document.error_code == "ocr_unavailable"
    assert document.candidate_id is None
    assert session.scalar(select(func.count()).select_from(DocumentPage)) == 0


def test_encrypted_and_corrupt_pdfs_are_quarantined(session):
    encrypted = _run(session, "protected.pdf", make_pdf(BODY, password="secret"))
    assert encrypted.status == "quarantined"
    assert encrypted.error_code == "encrypted_pdf"
    corrupt = _run(session, "broken.pdf", b"%PDF-1.7\nnot a pdf")
    assert corrupt.status == "quarantined"
    assert corrupt.error_code == "corrupt_pdf"
    assert session.scalar(select(func.count()).select_from(Candidate)) == 0


def test_identical_bytes_do_not_create_a_second_document(session):
    actor = _actor(session)
    data = make_pdf(BODY)
    first = ingest_bytes(session, filename="a.pdf", data=data, actor=actor)
    second = ingest_bytes(session, filename="Updated CV.pdf", data=data, actor=actor)
    session.commit()
    assert first.document.id == second.document.id
    assert second.created is False
    audit = session.scalar(select(AuditEvent).where(AuditEvent.action == "same_document"))
    assert audit.detail["identity_outcome"] == "same_document"


def test_same_email_with_a_different_filename_waits_for_a_person(session):
    original = _run(session, "a.pdf", make_pdf(BODY))
    incoming = _run(session, "other-name.pdf", make_pdf(BODY.replace("Analytical engines", "Different public notes")))
    assert incoming.candidate_id is None
    assert incoming.status == "needs_review"
    assert original.is_current is True
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == incoming.id))
    assert review.likely_relationship == "updated_cv"
    assert review.recommended_action == "accept_update"
    assert review.status == "pending"


def test_updated_filename_is_not_identity_evidence(session):
    document = _run(session, "Updated CV.pdf", make_pdf(BODY))
    assert document.identity_outcome == "new"
    assert document.candidate_id is not None
    assert session.scalar(select(func.count()).select_from(DuplicateReview)) == 0
    assert classify_document("Updated CV").kind == "cv"


def test_similar_names_with_different_emails_stay_separate(session):
    from app.extraction.draft import ExtractionDraft

    class NamingExtractor:
        model_name = "test-extractor"

        def extract(self, *, document_id, source_text: str, prompt_version: str) -> ExtractionDraft:
            return ExtractionDraft(display_name="Turki Aldulami", display_name_quote="Turki Aldulami")

    first = _run(session, "a.pdf", make_pdf(BODY))
    candidate = session.get(Candidate, first.candidate_id)
    candidate.display_name = "Turki Muhanna Aldulami"
    session.commit()
    text = "Turki Aldulami\nother@example.com\n" + ("Public notes about a different engineering career. " * 3)
    incoming = _run(session, "Updated CV.pdf", make_pdf(text), extractor=NamingExtractor())
    assert incoming.candidate_id is None
    review = session.scalar(select(DuplicateReview).where(DuplicateReview.document_id == incoming.id))
    assert review.recommended_action != "accept_update"
    assert float(review.confidence) < 85
    with pytest.raises(TransitionError):
        from app.domain.actor import AGENT
        from app.services.reviews import decide_duplicate_review

        decide_duplicate_review(session, review, "accept_update", AGENT)


def test_normalization_keeps_the_original_page(session):
    first = f"{HEADER}\nada@example.com\nExperience\nEngines and careful public notes about work.\nEducation\nMathematics"
    second = f"{HEADER}\nEducation\nFurther mathematics and public notes about study.\nExperience\nLater engines work."
    document = _run(session, "pages.pdf", make_two_pages(first, second))
    assert document.candidate_id is not None
    pages = session.scalars(select(DocumentPage).order_by(DocumentPage.page_number)).all()
    assert len(pages) == 2
    assert HEADER in pages[1].original_text
    assert HEADER not in pages[1].normalized_text
    chunks = session.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document.id)).all()
    combined = "\n".join(chunk.content for chunk in chunks)
    assert combined.count(HEADER) == 1
    assert HEADER in pages[0].original_text


def test_repeated_header_normalization_is_deterministic():
    pages = normalize_document(
        [
            "Ada Lovelace Header\nExperience\nEngines",
            "Ada Lovelace Header\nEducation\nMathematics",
        ]
    )
    assert pages[0].startswith("Ada Lovelace Header")
    assert "Ada Lovelace Header" not in pages[1]
    assert "Education" in pages[1]


def test_multi_column_text_is_read_down_each_column():
    document = pymupdf.open()
    page = document.new_page()
    left = "Left column experience\n" + "\n".join(f"Left detail {index} about work" for index in range(4))
    right = "Right column skills\n" + "\n".join(f"Right detail {index} about tools" for index in range(4))
    y = 72
    for line in left.splitlines():
        page.insert_text((72, y), line)
        y += 18
    y = 72
    for line in right.splitlines():
        page.insert_text((340, y), line)
        y += 18
    data = document.tobytes()
    document.close()
    extracted = extract_pdf(data)
    assert extracted.layout_pages is not None
    layout = extracted.layout_pages[0]
    assert layout.index("Left column experience") < layout.index("Right column skills")
    assert "Left column experience" in extracted.pages[0]

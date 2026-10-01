"""Read one stored document and persist a candidate, or a review, without a model."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import CHUNK_SIZE, MIN_TEXT_ALNUM
from app.domain.actor import SYSTEM
from app.domain.confidence import Assessment, Weights, assess, signal_payload
from app.domain.transitions import transition
from app.extraction.contacts import find_emails, find_phones, normalize_email, normalize_phone
from app.extraction.docx import extract_docx
from app.extraction.doc_legacy import DocConverter, LibreOfficeDocConverter
from app.extraction.deterministic import assign_pages
from app.extraction.doctype import classify_document
from app.extraction.draft import DraftRejected, ExtractionDraft, parse_draft, quote_in_source
from app.extraction.language import detect_language
from app.extraction.media import DOC, DOCX, JPEG, PDF, PNG
from app.extraction.normalize import normalize_document, pages_for_chunks
from app.extraction.ocr import OcrAdapter, OcrUnavailable, TesseractOcrAdapter
from app.extraction.pdf import extract_pdf
from app.extraction.prompt import PROMPT_VERSION
from app.extraction.provider import ExtractorUnavailable, StructuredExtractor, get_embedder, get_extractor
from app.extraction.textutil import alnum_count, chunk_text, clean_text, page_for_snippet, sha256_text
from app.extraction.types import ExtractedText
from app.jobs.errors import PermanentJobError
from app.models import (
    AgentRun,
    Application,
    Candidate,
    CandidateContact,
    CandidateDocument,
    DocumentChunk,
    DocumentPage,
    DuplicateReview,
    ExtractionEvidence,
)
from app.services.apply_draft import apply_draft
from app.services.audit import write_audit
from app.services.compare import build_pairs
from app.services.sourcing import declared_contacts, note_source_outcome
from app.storage.local import LocalStorage


def run_extract(
    session: Session,
    job,
    *,
    storage: LocalStorage | None = None,
    ocr: OcrAdapter | None = None,
    converter: DocConverter | None = None,
    extractor: StructuredExtractor | None = None,
    embedder=None,
) -> None:
    document = session.get(CandidateDocument, job.document_id)
    if document is None:
        raise PermanentJobError("document_missing")
    store = storage or LocalStorage(get_settings().storage_dir)
    try:
        data = store.read(document.storage_key)
    except FileNotFoundError as exc:
        raise PermanentJobError("storage_missing") from exc

    if extractor is None:
        extractor = get_extractor()
    if embedder is None:
        embedder = get_embedder()

    transition(document, "extracting", machine="candidate_document", actor=SYSTEM)
    extracted = _read(data, document.media_type, converter or LibreOfficeDocConverter())
    if alnum_count(extracted.full_text) < MIN_TEXT_ALNUM:
        extracted = _ocr_or_give_up(session, document, data, ocr or TesseractOcrAdapter(), extracted)

    if document.status == "needs_ocr":
        write_audit(
            session,
            actor=SYSTEM,
            action="document_needs_ocr",
            entity_type="candidate_document",
            entity_id=document.id,
            detail={"error_code": document.error_code or "insufficient_text", "text_source": document.text_source},
        )
        return

    classification = classify_document(extracted.full_text)
    if classification.kind == "non_cv":
        raise PermanentJobError(classification.reason or "non_cv")

    original_pages = extracted.pages or [extracted.full_text]
    normalized_pages = normalize_document(extracted.layout_pages or original_pages)
    document.language_code = detect_language(extracted.full_text)
    _store_pages(session, document, original_pages, normalized_pages)
    chunks = _store_chunks(session, document, pages_for_chunks(normalized_pages))
    emails = find_emails(extracted.full_text)
    phones = find_phones(extracted.full_text)
    declared_emails, declared_phones, declared_name = declared_contacts(session, document.id)
    draft, agent_run = _call_extractor(
        session, job, document, "\n\n".join(normalized_pages), extractor
    )
    if isinstance(draft, ExtractionDraft):
        assign_pages(draft, original_pages)
    accepted_name = _verified_name(draft, original_pages)
    settings = get_settings()
    pairs = build_pairs(
        session,
        document=document,
        full_text=extracted.full_text,
        emails=_with_declared(emails, declared_emails),
        phones=_with_declared(phones, declared_phones),
        name=accepted_name or declared_name,
        draft=draft,
        pages=original_pages,
    )
    assessment = assess(
        pairs,
        weights=_weights(settings),
        high_confidence=settings.identity_high_confidence,
        relationship_cutoff=settings.identity_relationship_cutoff,
    )
    document.text_source = extracted.source
    document.page_count = len(original_pages)
    document.processing_version = settings.processing_version

    candidate = _apply_outcome(session, document, assessment, emails, phones)
    note_source_outcome(session, document, candidate)
    if candidate is not None and draft is not None and agent_run is not None:
        applied = apply_draft(
            session,
            candidate=candidate,
            document_id=document.id,
            pages=original_pages,
            chunks=chunks,
            draft=draft,
            agent_run_id=agent_run.id,
        )
        agent_run.candidate_id = candidate.id
        agent_run.validation_result = _validation_label(applied.accepted, applied.rejected)
        agent_run.output_ref = _output_ref(applied.evidence_ids)
        if applied.accepted:
            transition(document, "profiled", machine="candidate_document", actor=SYSTEM)
    write_audit(
        session,
        actor=SYSTEM,
        action="document_extracted",
        entity_type="candidate_document",
        entity_id=document.id,
        detail={
            "identity_outcome": document.identity_outcome,
            "text_source": extracted.source,
            "candidate_id": str(candidate.id) if candidate else None,
            "count": len(chunks),
            "confidence": _audit_percent(assessment.confidence),
            "relationship": assessment.relationship,
            "recommended_action": assessment.recommended_action,
        },
    )
    if embedder is not None and _can_embed(document):
        _embed_chunks(chunks, embedder)


def profile_document(session: Session, document: CandidateDocument, candidate: Candidate, actor, extractor=None) -> None:
    """Add what a CV says to the profile of the person HR just attached it to.

    A CV that waits for a relationship decision is read but not applied: nothing is written to a profile until a person
    says whose CV it is. This runs once, as part of that decision. Facts an earlier CV already established are kept as
    they are, and every new fact is stored only with a verified quote from this document."""
    extractor = extractor if extractor is not None else get_extractor()
    if extractor is None or document.status in {"quarantined", "needs_ocr", "failed", "archived"}:
        return
    page_rows = session.execute(
        select(DocumentPage.original_text, DocumentPage.normalized_text)
        .where(DocumentPage.document_id == document.id)
        .order_by(DocumentPage.page_number)
    ).all()
    if not page_rows:
        return
    original_pages = [row.original_text for row in page_rows]
    chunks = list(
        session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document.id).order_by(DocumentChunk.chunk_index)
        ).all()
    )
    draft, run = _call_extractor(
        session, None, document, "\n\n".join(row.normalized_text for row in page_rows), extractor
    )
    if not isinstance(draft, ExtractionDraft) or run is None:
        return
    assign_pages(draft, original_pages)
    applied = apply_draft(
        session,
        candidate=candidate,
        document_id=document.id,
        pages=original_pages,
        chunks=chunks,
        draft=draft,
        agent_run_id=run.id,
    )
    run.candidate_id = candidate.id
    run.validation_result = _validation_label(applied.accepted, applied.rejected)
    run.output_ref = _output_ref(applied.evidence_ids)
    if applied.accepted and document.status == "extracted":
        transition(document, "profiled", machine="candidate_document", actor=actor)


def _can_embed(document) -> bool:
    if document.status in {"quarantined", "needs_ocr", "failed", "received", "extracting"}:
        return False
    code = document.error_code or ""
    return not str(code).startswith("non_cv")


def _embed_chunks(chunks: list[DocumentChunk], embedder) -> None:
    if not chunks:
        return
    vectors = embedder.embed([chunk.content for chunk in chunks])
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = vector


def _read(data: bytes, media_type: str, converter: DocConverter) -> ExtractedText:
    if media_type == PDF:
        return extract_pdf(data)
    if media_type == DOCX:
        return extract_docx(data)
    if media_type == DOC:
        converted = converter.convert_to_docx(data)
        text = extract_docx(converted)
        return ExtractedText(pages=text.pages, source="doc")
    if media_type in {JPEG, PNG}:
        return ExtractedText(pages=[], source="image")
    raise PermanentJobError("unsupported_file")


def _ocr_or_give_up(session, document, data: bytes, ocr: OcrAdapter, current: ExtractedText) -> ExtractedText:
    try:
        raw_pages = [clean_text(page) for page in ocr.extract_pages(data, document.media_type)]
    except OcrUnavailable:
        transition(document, "needs_ocr", machine="candidate_document", actor=SYSTEM)
        document.error_code = "ocr_unavailable"
        document.text_source = current.source
        return current
    cleaned = "\n\n".join(page for page in raw_pages if page).strip()
    if _letter_count(cleaned) < MIN_TEXT_ALNUM:
        document.text_source = "ocr"
        document.page_count = len(raw_pages) or 1
        document.error_code = "insufficient_text"
        _store_pages(session, document, raw_pages or [""], raw_pages or [""])
        transition(document, "needs_ocr", machine="candidate_document", actor=SYSTEM)
        return current
    return ExtractedText(pages=raw_pages or [cleaned], source="ocr")


def _letter_count(value: str) -> int:
    return sum(character.isalpha() for character in value)


def _store_pages(session, document, original_pages: list[str], normalized_pages: list[str]) -> None:
    for number, original in enumerate(original_pages, start=1):
        normalized = normalized_pages[number - 1] if number <= len(normalized_pages) else ""
        session.add(
            DocumentPage(
                document_id=document.id,
                page_number=number,
                original_text=original,
                normalized_text=normalized,
            )
        )
    session.flush()


def _store_chunks(session: Session, document: CandidateDocument, pages: list[str]) -> list[DocumentChunk]:
    pieces = chunk_text("\n\n".join(pages), CHUNK_SIZE)
    rows: list[DocumentChunk] = []
    for index, content in enumerate(pieces):
        row = DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            page_start=page_for_snippet(pages, content[:80]),
            page_end=page_for_snippet(pages, content[:80]),
            content=content,
            content_hash=sha256_text(content),
        )
        session.add(row)
        rows.append(row)
    session.flush()
    if document.status == "extracting":
        transition(document, "extracted", machine="candidate_document", actor=SYSTEM)
    return rows


def _call_extractor(session, job, document, source_text: str, extractor: StructuredExtractor | None):
    if extractor is None:
        run = AgentRun(
            agent_name="candidate_extractor",
            job_id=job.id if job is not None else None,
            document_id=document.id,
            prompt_version=PROMPT_VERSION,
            input_hash=sha256_text(source_text),
            status="skipped",
            validation_result="skipped",
            error_code="extractor_unavailable",
        )
        session.add(run)
        session.flush()
        return None, run
    try:
        draft = extractor.extract(
            document_id=document.id, source_text=source_text, prompt_version=PROMPT_VERSION
        )
    except (ExtractorUnavailable, DraftRejected) as exc:
        code = getattr(exc, "code", "extractor_unavailable")
        run = AgentRun(
            agent_name="candidate_extractor",
            job_id=job.id if job is not None else None,
            document_id=document.id,
            prompt_version=PROMPT_VERSION,
            input_hash=sha256_text(source_text),
            status="failed",
            validation_result="rejected",
            error_code=code,
        )
        session.add(run)
        session.flush()
        return None, run
    if not isinstance(draft, ExtractionDraft):
        try:
            draft = parse_draft(draft)
        except DraftRejected:
            run = AgentRun(
                agent_name="candidate_extractor",
                job_id=job.id if job is not None else None,
                document_id=document.id,
                prompt_version=PROMPT_VERSION,
                input_hash=sha256_text(source_text),
                status="failed",
                validation_result="rejected",
                error_code="malformed_output",
            )
            session.add(run)
            session.flush()
            return None, run
    run = AgentRun(
        agent_name="candidate_extractor",
        job_id=job.id if job is not None else None,
        document_id=document.id,
        model=getattr(extractor, "model_name", None),
        prompt_version=PROMPT_VERSION,
        input_hash=sha256_text(source_text),
        status="succeeded",
    )
    session.add(run)
    session.flush()
    return draft, run


def _verified_name(draft: ExtractionDraft | None, pages: list[str]) -> str | None:
    if draft is None or not draft.display_name or not draft.display_name_quote:
        return None
    if not quote_in_source(pages, draft.display_name_quote, None):
        return None
    return draft.display_name


def _with_declared(extracted: list[tuple[str, str]], declared: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen = {normalized for _raw, normalized in extracted}
    combined = list(extracted)
    for raw, normalized in declared:
        if normalized not in seen:
            seen.add(normalized)
            combined.append((raw, normalized))
    return combined


def _weights(settings) -> Weights:
    return Weights(
        email=settings.identity_weight_email,
        phone=settings.identity_weight_phone,
        name=settings.identity_weight_name,
        dates=settings.identity_weight_dates,
        explicit_version=settings.identity_weight_explicit_version,
        employment=settings.identity_weight_employment,
        education=settings.identity_weight_education,
        skills=settings.identity_weight_skills,
        semantic=settings.identity_weight_semantic,
    )


def _score_percent(confidence: float | None) -> float | None:
    if confidence is None:
        return None
    return round(confidence * 100, 2)


def _audit_percent(confidence: float | None) -> int | None:
    if confidence is None:
        return None
    return int(round(confidence * 100))


def _apply_outcome(session, document, assessment: Assessment, emails, phones):
    if not assessment.comparable:
        document.identity_outcome = "new"
        candidate = Candidate(source="upload")
        session.add(candidate)
        session.flush()
        _attach(session, document, candidate, emails, phones, supersedes=None)
        return candidate
    document.identity_outcome = "ambiguous" if assessment.ambiguous else assessment.relationship
    _open_review(session, document, assessment)
    _store_unlinked_contacts(session, document, emails, phones)
    if document.status == "extracted":
        transition(document, "needs_review", machine="candidate_document", actor=SYSTEM)
    return None


def _attach(
    session,
    document,
    candidate,
    emails,
    phones,
    supersedes: UUID | None,
    *,
    write_evidence: bool = True,
    make_current: bool = True,
) -> None:
    if make_current:
        session.execute(
            update(CandidateDocument)
            .where(
                CandidateDocument.candidate_id == candidate.id,
                CandidateDocument.is_current.is_(True),
                CandidateDocument.id != document.id,
            )
            .values(is_current=False)
        )
        session.flush()
    document.candidate_id = candidate.id
    document.is_current = make_current
    document.supersedes_document_id = supersedes if make_current else None
    session.add(
        Application(
            candidate_id=candidate.id,
            document_id=document.id,
            source="upload",
            received_at=document.received_at,
        )
    )
    for raw, normalized in emails:
        _add_contact(session, candidate.id, document, "email", raw, normalized, write_evidence=write_evidence)
    for raw, normalized in phones:
        _add_contact(session, candidate.id, document, "phone", raw, normalized, write_evidence=write_evidence)
    session.flush()


def _add_contact(session, candidate_id, document, kind, raw, normalized, *, write_evidence: bool) -> None:
    if normalize_email(normalized) is None and kind == "email":
        return
    if kind == "phone" and normalize_phone(normalized) is None:
        return
    exists = session.scalar(
        select(CandidateContact.id).where(
            CandidateContact.candidate_id == candidate_id,
            CandidateContact.kind == kind,
            CandidateContact.value_normalized == normalized,
        )
    )
    if exists is not None:
        return
    session.add(
        CandidateContact(
            candidate_id=candidate_id,
            kind=kind,
            value_raw=raw[:320],
            value_normalized=normalized[:320],
            is_primary=True,
        )
    )
    session.flush()
    if not write_evidence:
        return
    session.add(
        ExtractionEvidence(
            document_id=document.id,
            candidate_id=candidate_id,
            entity_type="contact",
            field_name=kind,
            extracted_value=normalized[:320],
            source_quote=raw[:1000],
            page=_page_for_quote(session, document.id, raw),
            quote_verified=True,
        )
    )


def _store_unlinked_contacts(session, document, emails, phones) -> None:
    for kind, pairs in (("email", emails), ("phone", phones)):
        for raw, normalized in pairs:
            session.add(
                ExtractionEvidence(
                    document_id=document.id,
                    entity_type="contact",
                    field_name=kind,
                    extracted_value=normalized[:320],
                    source_quote=raw[:1000],
                    page=_page_for_quote(session, document.id, raw),
                    quote_verified=True,
                )
            )


def _page_for_quote(session, document_id, quote: str) -> int | None:
    pages = session.scalars(
        select(DocumentPage.original_text)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    ).all()
    return page_for_snippet(list(pages), quote)


def _open_review(session, document, assessment: Assessment) -> None:
    session.add(
        DuplicateReview(
            document_id=document.id,
            candidate_id=assessment.candidate_id,
            status="pending",
            proposed_outcome=assessment.relationship or "uncertain",
            confidence=_score_percent(assessment.confidence),
            likely_relationship=assessment.relationship,
            recommended_action=assessment.recommended_action,
            offered_actions=list(assessment.offered_actions),
            signals={
                "ambiguous": assessment.ambiguous,
                "candidate_ids": [str(item) for item in assessment.candidate_ids],
                "evidence": [signal_payload(item) for item in assessment.signals],
            },
        )
    )
    write_audit(
        session,
        actor=SYSTEM,
        action="duplicate_review_opened",
        entity_type="candidate_document",
        entity_id=document.id,
        detail={
            "relationship": assessment.relationship,
            "confidence": _audit_percent(assessment.confidence),
            "recommended_action": assessment.recommended_action,
            "count": len(assessment.candidate_ids),
        },
    )


def _validation_label(accepted: int, rejected: int) -> str:
    if accepted and not rejected:
        return "accepted"
    if accepted and rejected:
        return "partial"
    return "rejected"


def _output_ref(evidence_ids: list[UUID]) -> str:
    if not evidence_ids:
        return "evidence_count:0"
    joined = ",".join(str(item) for item in evidence_ids)
    if len(joined) <= 480:
        return f"evidence:{joined}"
    return f"evidence_count:{len(evidence_ids)}"


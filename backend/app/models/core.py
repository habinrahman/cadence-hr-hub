"""Ingestion and candidate records. Profile text lives here, not on agent runs."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.constants import EMBEDDING_DIMENSIONS
from app.models.base import Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))


class Candidate(IdMixin, TimestampMixin, Base):
    __tablename__ = "candidates"

    display_name: Mapped[str | None] = mapped_column(String(200))
    summary: Mapped[str | None] = mapped_column(String(2000))
    years_of_experience: Mapped[float | None] = mapped_column(Numeric(4, 1))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="upload")
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"))
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CandidateContact(IdMixin, TimestampMixin, Base):
    __tablename__ = "candidate_contacts"
    __table_args__ = (Index("ix_candidate_contacts_lookup", "kind", "value_normalized"),)

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    value_raw: Mapped[str] = mapped_column(String(320), nullable=False)
    value_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Application(IdMixin, TimestampMixin, Base):
    """A CV submission. This is not a match against a hiring request."""

    __tablename__ = "applications"

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidate_documents.id"))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    application_date: Mapped[date | None] = mapped_column(Date)


class CandidateDocument(IdMixin, TimestampMixin, Base):
    __tablename__ = "candidate_documents"
    __table_args__ = (
        Index("ix_candidate_documents_sha256", "sha256"),
        Index(
            "uq_one_current_document",
            "candidate_id",
            unique=True,
            postgresql_where=text("is_current AND candidate_id IS NOT NULL"),
        ),
    )

    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"))
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="received")
    identity_outcome: Mapped[str | None] = mapped_column(String(32))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supersedes_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_documents.id")
    )
    text_source: Mapped[str | None] = mapped_column(String(32))
    language_code: Mapped[str | None] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(120))
    processing_version: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CandidateExperience(IdMixin, TimestampMixin, Base):
    __tablename__ = "candidate_experiences"

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_documents.id"), nullable=False
    )
    employer: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str | None] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(300))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(4000))


class CandidateEducation(IdMixin, TimestampMixin, Base):
    __tablename__ = "candidate_education"

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_documents.id"), nullable=False
    )
    institution: Mapped[str] = mapped_column(String(300), nullable=False)
    credential: Mapped[str | None] = mapped_column(String(300))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)


class CandidateSkill(IdMixin, TimestampMixin, Base):
    __tablename__ = "candidate_skills"

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_documents.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)


class CandidateCertificate(IdMixin, TimestampMixin, Base):
    """kind is certificate or qualification. There is no separate qualifications table."""

    __tablename__ = "candidate_certificates"

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_documents.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(300))
    issued_on: Mapped[date | None] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="certificate")


class DocumentChunk(IdMixin, TimestampMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_position"),
        Index("ix_document_chunks_search", "search_vector", postgresql_using="gin"),
        Index(
            "ix_document_chunks_trgm",
            "content",
            postgresql_using="gin",
            postgresql_ops={"content": "gin_trgm_ops"},
        ),
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_documents.id"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(content, ''))", persisted=True),
    )


class DocumentPage(IdMixin, Base):
    """Original page text stays here. Chunks store the normalized copy."""

    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_document_pages_number"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_documents.id"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)


class ExtractionEvidence(IdMixin, TimestampMixin, Base):
    __tablename__ = "extraction_evidence"
    __table_args__ = (CheckConstraint("quote_verified", name="quote_verified"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_documents.id"), nullable=False
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"))
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("document_chunks.id"))
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_value: Mapped[str] = mapped_column(String(4000), nullable=False)
    source_quote: Mapped[str] = mapped_column(String(1000), nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    quote_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)


class FieldLock(IdMixin, Base):
    __tablename__ = "field_locks"
    __table_args__ = (
        Index(
            "uq_field_locks_target",
            "candidate_id",
            "entity_type",
            text("COALESCE(entity_id, '00000000-0000-0000-0000-000000000000')"),
            "field_name",
            unique=True,
        ),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    locked_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(String(200))


class AgentRun(IdMixin, TimestampMixin, Base):
    """Metadata only. Raw CV text and model output do not belong in this table."""

    __tablename__ = "agent_runs"

    agent_name: Mapped[str] = mapped_column(String(80), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidate_documents.id"))
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hiring_requests.id"))
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(80))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    output_ref: Mapped[str | None] = mapped_column(String(500))
    validation_result: Mapped[str | None] = mapped_column(String(32))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120))


class Job(IdMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "job_type",
            "idempotency_key",
            "processing_version",
            name="uq_jobs_idempotency",
        ),
        Index("ix_jobs_claim", "status", "run_after"),
    )

    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    processing_version: Mapped[int] = mapped_column(Integer, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidate_documents.id"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    leased_by: Mapped[str | None] = mapped_column(String(80))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(120))
    last_error: Mapped[str | None] = mapped_column(String(120))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class QuarantineRecord(IdMixin, TimestampMixin, Base):
    __tablename__ = "quarantine_records"

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), unique=True, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidate_documents.id"))
    error_code: Mapped[str] = mapped_column(String(120), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DuplicateReview(IdMixin, TimestampMixin, Base):
    __tablename__ = "duplicate_reviews"

    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidate_documents.id"))
    excel_import_row_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("excel_import_rows.id"))
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    proposed_outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 2))
    likely_relationship: Mapped[str | None] = mapped_column(String(32))
    recommended_action: Mapped[str | None] = mapped_column(String(64))
    offered_actions: Mapped[list | None] = mapped_column(JSONB)
    signals: Mapped[dict] = mapped_column(JSONB, nullable=False)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(IdMixin, Base):
    __tablename__ = "audit_events"

    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CandidateSource(IdMixin, TimestampMixin, Base):
    """Where a recruiter found a person. The CV still goes through intake review."""

    __tablename__ = "candidate_sources"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_documents.id"), unique=True, nullable=False)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)


class ProblemReport(IdMixin, TimestampMixin, Base):
    __tablename__ = "problem_reports"

    reporter_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="none", server_default="none")
    entity_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="other", server_default="other")
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    engineering_note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ExcelImport(IdMixin, TimestampMixin, Base):
    """One spreadsheet upload. Row text stays out of this table."""

    __tablename__ = "excel_imports"

    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    sheet_count: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    invalid_count: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False)
    relationship_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ignored_column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class ExcelImportRow(IdMixin, Base):
    __tablename__ = "excel_import_rows"

    import_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("excel_imports.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"))
    relationship: Mapped[str | None] = mapped_column(String(32))
    duplicate_of_row: Mapped[int | None] = mapped_column(Integer)
    proposed_name: Mapped[str | None] = mapped_column(String(200))
    proposed_email: Mapped[str | None] = mapped_column(String(320))
    proposed_phone: Mapped[str | None] = mapped_column(String(32))

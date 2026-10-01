"""Hiring, matching, and shortlist tables. Approval and company send write two of them."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class HiringRequest(IdMixin, TimestampMixin, Base):
    __tablename__ = "hiring_requests"

    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    job_title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    pool_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_match_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pool_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    requested_count: Mapped[int | None] = mapped_column(Integer)
    # The company contact the shortlist is sent to. Nothing is sent until it is set.
    contact_email: Mapped[str | None] = mapped_column(String(320))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RequestRequirement(IdMixin, TimestampMixin, Base):
    __tablename__ = "request_requirements"

    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hiring_requests.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    requirement_text: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[str] = mapped_column(String(32), nullable=False)
    source_quote: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed", server_default="proposed")


class RequestNote(IdMixin, TimestampMixin, Base):
    __tablename__ = "request_notes"

    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hiring_requests.id"), nullable=False)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="note", server_default="note")


class RequestAttachment(IdMixin, TimestampMixin, Base):
    __tablename__ = "request_attachments"

    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hiring_requests.id"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)


class CandidateMatch(IdMixin, TimestampMixin, Base):
    __tablename__ = "candidate_matches"
    __table_args__ = (UniqueConstraint("request_id", "candidate_id", name="uq_match_candidate"),)

    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hiring_requests.id"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    rank_score: Mapped[float | None] = mapped_column(Numeric(8, 4))
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str | None] = mapped_column(String(500))
    processing_version: Mapped[int | None] = mapped_column(Integer)


class MatchRequirementResult(IdMixin, TimestampMixin, Base):
    __tablename__ = "match_requirement_results"
    __table_args__ = (
        UniqueConstraint("match_id", "requirement_id", name="uq_match_requirement"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidate_matches.id"), nullable=False)
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("request_requirements.id"), nullable=False
    )
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("extraction_evidence.id"))
    evidence_quote: Mapped[str | None] = mapped_column(String(160))
    retrieval: Mapped[str | None] = mapped_column(String(32))


class Shortlist(IdMixin, TimestampMixin, Base):
    __tablename__ = "shortlists"

    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hiring_requests.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ShortlistCandidate(IdMixin, TimestampMixin, Base):
    __tablename__ = "shortlist_candidates"
    __table_args__ = (
        UniqueConstraint("shortlist_id", "candidate_id", name="uq_shortlist_candidate"),
    )

    shortlist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shortlists.id"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    match_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidate_matches.id"))
    added_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    review_state: Mapped[str] = mapped_column(String(32), nullable=False, default="shortlisted", server_default="shortlisted")
    note: Mapped[str | None] = mapped_column(Text)


class ApprovalDecision(IdMixin, TimestampMixin, Base):
    __tablename__ = "approval_decisions"

    subject_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    suggestion_code: Mapped[str | None] = mapped_column(String(80))


class SharingRecord(IdMixin, TimestampMixin, Base):
    __tablename__ = "sharing_records"

    shortlist_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shortlists.id"))
    request_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("hiring_requests.id"))
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    recipient: Mapped[str | None] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="sent", server_default="sent")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    destination: Mapped[str] = mapped_column(String(64), nullable=False, default="local_mailcatcher")

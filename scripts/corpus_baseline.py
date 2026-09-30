"""Run the current ingestion pipeline on cvs/ and write a text-free baseline.

Outputs stay under backend/var/baseline/, which is gitignored. The report
contains counts, codes, and filenames. It does not contain CV text.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CVS = REPO / "cvs"
OUT = REPO / "backend" / "var" / "baseline"
STORAGE = OUT / "storage"
DATABASE_URL = "postgresql+psycopg://hub:hub@localhost:15432/hub_baseline"
ADMIN_URL = "postgresql://hub:hub@localhost:15432/hub"

os.environ["ENVIRONMENT"] = "local"
os.environ["DATABASE_URL"] = DATABASE_URL
os.environ["HUB_RECRUITER_TOKEN"] = "dev-recruiter-token"
os.environ["HUB_ENGINEER_TOKEN"] = "dev-engineer-token"
os.environ["STORAGE_DIR"] = str(STORAGE)
os.environ["EXTRACTOR_PROVIDER"] = "none"
os.environ["PROCESSING_VERSION"] = "1"

sys.path.insert(0, str(REPO / "backend"))


def prepare_database() -> None:
    import psycopg
    from alembic import command
    from alembic.config import Config

    with psycopg.connect(ADMIN_URL, autocommit=True) as connection:
        connection.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'hub_baseline'"
        )
        connection.execute("DROP DATABASE IF EXISTS hub_baseline")
        connection.execute("CREATE DATABASE hub_baseline")
    config = Config(str(REPO / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(REPO / "backend" / "alembic"))
    command.upgrade(config, "head")


def filename_flags(name: str) -> list[str]:
    flags = []
    patterns = {
        "filename_updated": r"(?<![A-Za-z0-9])updated(?![A-Za-z0-9])",
        "filename_invoice": r"(?<![A-Za-z0-9])invoice(?![A-Za-z0-9])",
        "filename_transcript": r"(?<![A-Za-z0-9])transcript(?![A-Za-z0-9])",
        "filename_blank": r"(?<![A-Za-z0-9])blank(?![A-Za-z0-9])",
        "filename_scan": r"(?<![A-Za-z0-9])scan(?![A-Za-z0-9])",
        "filename_cover_letter": r"cover letter",
        "filename_job_description": r"job description",
    }
    for flag, pattern in patterns.items():
        if re.search(pattern, name, re.IGNORECASE):
            flags.append(flag)
    if re.search(r"[\u0600-\u06FF]", name):
        flags.append("filename_arabic")
    return flags


def stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "min": None, "max": None, "mean": None}
    return {
        "count": len(values),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "mean": round(sum(values) / len(values), 2),
    }


def outcome_for(status: str | None, created: bool) -> str:
    if not created:
        return "same_document"
    if status == "needs_ocr":
        return "needs_ocr"
    if status == "quarantined":
        return "quarantined"
    if status in {"extracted", "needs_review", "profiled"}:
        return "processed"
    return "failed"


def run() -> None:
    prepare_database()
    from app.config import reset_settings

    reset_settings()

    from sqlalchemy import func, select

    from app.bootstrap import provision
    from app.db import make_engine, make_session_factory
    from app.domain.actor import Actor
    from app.extraction.media import UnsupportedFile
    from app.jobs.queue import run_once
    from app.models import (
        Candidate,
        CandidateDocument,
        DocumentChunk,
        DuplicateReview,
        Job,
        User,
    )
    from app.services.ingest import ingest_bytes
    from app.services.pipeline import run_extract

    OUT.mkdir(parents=True, exist_ok=True)
    STORAGE.mkdir(parents=True, exist_ok=True)
    factory = make_session_factory(make_engine())
    session = factory()
    provision(session)
    user = session.scalar(select(User).where(User.role == "recruiter"))
    actor = Actor(kind="user", user_id=user.id)
    session.commit()

    files = sorted(path for path in CVS.rglob("*") if path.is_file())
    rows: list[dict] = []
    detail_path = OUT / "files.jsonl"
    with detail_path.open("w", encoding="utf-8") as handle:
        for index, path in enumerate(files, start=1):
            row = ingest_one(session, path, actor, ingest_bytes, run_once, run_extract, UnsupportedFile)
            rows.append(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if index % 25 == 0 or index == len(files):
                print(f"{index}/{len(files)} {row['pipeline_outcome']}", flush=True)

    lengths = {
        document_id: (characters, chunks)
        for document_id, characters, chunks in session.execute(
            select(
                DocumentChunk.document_id,
                func.sum(func.char_length(DocumentChunk.content)),
                func.count(),
            ).group_by(DocumentChunk.document_id)
        )
    }
    for row in rows:
        document_id = row.get("document_id")
        if document_id is None:
            continue
        from uuid import UUID

        characters, chunks = lengths.get(UUID(document_id), (0, 0))
        row["text_characters"] = int(characters or 0)
        row["chunk_count"] = int(chunks or 0)

    with detail_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = build_summary(session, rows, Candidate, CandidateDocument, DuplicateReview, Job)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT / "report.md").write_text(render_report(summary, rows), encoding="utf-8")
    session.close()
    print(f"wrote {OUT / 'report.md'}")


def ingest_one(session, path: Path, actor, ingest_bytes, run_once, run_extract, unsupported) -> dict:
    from app.config import get_settings

    data = path.read_bytes()
    relative = path.relative_to(CVS).as_posix()
    base = {
        "path": relative,
        "filename": path.name,
        "extension": path.suffix.lower() or "(none)",
        "byte_size": len(data),
        "filename_flags": filename_flags(path.name),
        "sha256": hashlib.sha256(data).hexdigest() if data else None,
        "document_id": None,
        "detected_media_type": None,
        "pipeline_outcome": None,
        "document_status": None,
        "error_code": None,
        "identity_outcome": None,
        "text_source": None,
        "page_count": None,
        "text_characters": None,
        "chunk_count": None,
        "processing_ms": None,
        "review_created": False,
        "created_document": False,
    }
    started = time.perf_counter()
    try:
        if not data:
            base["pipeline_outcome"] = "rejected"
            base["error_code"] = "empty_file"
            return base
        if len(data) > get_settings().max_upload_bytes:
            base["pipeline_outcome"] = "rejected"
            base["error_code"] = "file_too_large"
            return base
        result = ingest_bytes(session, filename=path.name, data=data, actor=actor)
        session.commit()
    except unsupported:
        session.rollback()
        base["pipeline_outcome"] = "rejected"
        base["error_code"] = "unsupported_file"
        base["processing_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return base
    except Exception as exc:
        session.rollback()
        base["pipeline_outcome"] = "failed"
        base["error_code"] = type(exc).__name__
        base["processing_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return base

    document = result.document
    base["document_id"] = str(document.id)
    base["detected_media_type"] = document.media_type
    base["created_document"] = result.created
    if result.created:
        from sqlalchemy import select

        from app.models import DuplicateReview, Job

        for _ in range(8):
            job = session.scalar(select(Job).where(Job.document_id == document.id))
            if job is not None and job.status in {"succeeded", "quarantined"}:
                break
            worked = run_once(session, worker_id="baseline", handler=run_extract)
            if not worked:
                break
        review = session.scalar(select(DuplicateReview.id).where(DuplicateReview.document_id == document.id))
        base["review_created"] = review is not None
    session.expire_all()
    document = session.get(type(document), document.id)
    base["document_status"] = document.status
    base["error_code"] = document.error_code
    base["identity_outcome"] = document.identity_outcome
    base["text_source"] = document.text_source
    base["page_count"] = document.page_count
    base["pipeline_outcome"] = outcome_for(document.status, result.created)
    base["processing_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return base


def build_summary(session, rows: list[dict], candidate_model, document_model, review_model, job_model) -> dict:
    from sqlalchemy import func, select

    outcomes = Counter(row["pipeline_outcome"] for row in rows)
    extensions = Counter(row["extension"] for row in rows)
    media = Counter(row["detected_media_type"] or "rejected_before_detect" for row in rows)
    errors = Counter(row["error_code"] for row in rows if row["error_code"])
    identities = Counter(row["identity_outcome"] for row in rows if row["identity_outcome"])
    sources = Counter(row["text_source"] for row in rows if row["text_source"])
    statuses = Counter(row["document_status"] for row in rows if row["document_status"])
    file_hashes: dict[str, list[str]] = {}
    for row in rows:
        if not row.get("sha256"):
            continue
        file_hashes.setdefault(row["sha256"], []).append(row["filename"])
    duplicate_groups = [
        {"sha256": digest, "count": len(names), "filenames": names}
        for digest, names in sorted(file_hashes.items())
        if len(names) > 1
    ]

    pages = [row["page_count"] for row in rows if isinstance(row["page_count"], int)]
    characters = [row["text_characters"] for row in rows if isinstance(row["text_characters"], int)]
    timings = [row["processing_ms"] for row in rows if isinstance(row["processing_ms"], (int, float))]
    candidates = session.scalar(select(func.count()).select_from(candidate_model))
    reviews = session.scalar(select(func.count()).select_from(review_model))
    attached_existing = session.scalar(
        select(func.count()).select_from(document_model).where(
            document_model.candidate_id.is_not(None),
            document_model.identity_outcome.is_not(None),
            document_model.identity_outcome.notin_(["new"]),
        )
    )
    stuck_jobs = session.scalar(
        select(func.count()).select_from(job_model).where(job_model.status.notin_(["succeeded", "quarantined"]))
    )
    accounted = len(rows)
    unexpected = [
        {
            "filename": row["filename"],
            "pipeline_outcome": row["pipeline_outcome"],
            "document_status": row["document_status"],
            "error_code": row["error_code"],
        }
        for row in rows
        if row["pipeline_outcome"] == "failed"
        or (row["created_document"] and row["document_status"] not in {"extracted", "needs_review", "profiled", "needs_ocr", "quarantined"})
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": "hub_baseline",
        "extractor_provider": "none",
        "embedding_provider": "none",
        "language_detection": "not_available",
        "ocr_tool_on_path": bool(shutil.which("tesseract") or Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe").exists()),
        "libreoffice_on_path": bool(shutil.which("soffice")),
        "files_discovered": accounted,
        "files_accounted": accounted,
        "by_extension": dict(extensions),
        "by_detected_media_type": dict(media),
        "pipeline_outcome": dict(outcomes),
        "document_status": dict(statuses),
        "error_code": dict(errors),
        "identity_outcome": dict(identities),
        "text_source": dict(sources),
        "successfully_extracted": outcomes.get("processed", 0),
        "needs_ocr": outcomes.get("needs_ocr", 0),
        "encrypted_or_password_protected": errors.get("encrypted_pdf", 0),
        "corrupt_or_unreadable": errors.get("corrupt_pdf", 0) + errors.get("corrupt_docx", 0),
        "rejected": outcomes.get("rejected", 0),
        "non_cv_rejected_by_pipeline": sum(count for code, count in errors.items() if str(code).startswith("non_cv")),
        "documents_created": sum(1 for row in rows if row["created_document"]),
        "duplicate_byte_groups": len(duplicate_groups),
        "duplicate_extra_files": sum(item["count"] - 1 for item in duplicate_groups),
        "duplicate_groups": duplicate_groups,
        "candidates_created": int(candidates or 0),
        "documents_attached_to_existing_candidates": int(attached_existing or 0),
        "relationship_reviews_created": int(reviews or 0),
        "reviews_opened_this_run": sum(1 for row in rows if row["review_created"]),
        "same_document": outcomes.get("same_document", 0),
        "stuck_jobs": int(stuck_jobs or 0),
        "unexpected_failures": unexpected,
        "pages": stats(pages),
        "text_characters": stats(characters),
        "processing_ms": stats(timings),
        "filename_flag_counts": dict(Counter(flag for row in rows for flag in row["filename_flags"])),
    }


def render_report(summary: dict, rows: list[dict]) -> str:
    def lines(mapping: dict) -> str:
        if not mapping:
            return "- none"
        return "\n".join(f"- {key}: {value}" for key, value in sorted(mapping.items(), key=lambda item: str(item[0])))

    watched = []
    interesting = ("protected", "kareem", "final", "blank", "scan", "transcript", "invoice", "cover", "ahmed", "updated", "maryam")
    for row in rows:
        name = row["filename"].casefold()
        if any(token in name for token in interesting) or row["pipeline_outcome"] in {"needs_ocr", "quarantined", "rejected", "failed"}:
            watched.append(row)
    edge_lines = [
        f"- `{row['filename']}`: {row['pipeline_outcome']}"
        + (f", status {row['document_status']}" if row["document_status"] else "")
        + (f", {row['error_code']}" if row["error_code"] else "")
        + (f", source {row['text_source']}" if row["text_source"] else "")
        + (f", {row['page_count']} pages" if row["page_count"] is not None else "")
        + (f", {row['text_characters']} characters" if row["text_characters"] is not None else "")
        + (", review opened" if row["review_created"] else "")
        for row in watched
    ]
    duplicate_lines = [
        "- " + ", ".join(f"`{name}`" for name in group["filenames"])
        for group in summary["duplicate_groups"]
    ]
    unexpected = summary["unexpected_failures"]
    unexpected_lines = [
        f"- `{item['filename']}`: {item['pipeline_outcome']} / {item['document_status']} / {item['error_code']}"
        for item in unexpected
    ] or ["- none"]
    return f"""# Corpus baseline

Generated {summary['generated_at']}. Database `{summary['database']}`. Extractor `{summary['extractor_provider']}`. Embeddings were not run. Language detection is not part of this pipeline.

OCR tool on PATH: {summary['ocr_tool_on_path']}. LibreOffice on PATH: {summary['libreoffice_on_path']}. A file with no text layer stays needs_ocr when OCR cannot read it. A blank scan is not turned into a candidate.

## Totals

- Files discovered: {summary['files_discovered']}
- Files accounted for: {summary['files_accounted']}
- Successfully extracted: {summary['successfully_extracted']}
- Needs OCR: {summary['needs_ocr']}
- Encrypted or password-protected: {summary['encrypted_or_password_protected']}
- Corrupt or unreadable: {summary['corrupt_or_unreadable']}
- Rejected before a document was stored: {summary['rejected']}
- Non-CV documents rejected by the pipeline: {summary['non_cv_rejected_by_pipeline']}
- Identical-byte groups: {summary['duplicate_byte_groups']} ({summary['duplicate_extra_files']} extra files recognized as the same document)
- Documents created: {summary['documents_created']}
- Candidate profiles created: {summary['candidates_created']}
- Documents attached to an existing candidate: {summary['documents_attached_to_existing_candidates']}
- Relationship reviews created: {summary['relationship_reviews_created']}
- Stuck jobs: {summary['stuck_jobs']}

Non-CV decisions use the extracted text, not the filename. Filename tokens below are observations only.

## Files by extension

{lines(summary['by_extension'])}

## Files by detected type

{lines(summary['by_detected_media_type'])}

## Pipeline outcome

{lines(summary['pipeline_outcome'])}

## Document status

{lines(summary['document_status'])}

## Error codes

{lines(summary['error_code'])}

## Identity outcome

{lines(summary['identity_outcome'])}

## Extraction method

{lines(summary['text_source'])}

## Extraction statistics

Language detection: {summary['language_detection']}

Pages: count {summary['pages']['count']}, min {summary['pages']['min']}, max {summary['pages']['max']}, mean {summary['pages']['mean']}

Extracted characters: count {summary['text_characters']['count']}, min {summary['text_characters']['min']}, max {summary['text_characters']['max']}, mean {summary['text_characters']['mean']}

Processing time (ms): count {summary['processing_ms']['count']}, min {summary['processing_ms']['min']}, max {summary['processing_ms']['max']}, mean {summary['processing_ms']['mean']}

## Filename observations

These did not change any decision.

{lines(summary['filename_flag_counts'])}

## Identical bytes

{chr(10).join(duplicate_lines) if duplicate_lines else '- none'}

## Edge cases and every non-processed file

{chr(10).join(edge_lines) if edge_lines else '- none'}

## Unexpected failures

{chr(10).join(unexpected_lines)}
"""


if __name__ == "__main__":
    run()

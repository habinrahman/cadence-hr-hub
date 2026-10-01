# Request-Driven Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A logged hiring request is extracted and matched automatically by the background worker, producing a broad candidate pool that Cadence HR reviews, filters, shortlists, approves and shares by hand.

**Architecture:** `POST /hiring-requests` submits the request and enqueues one idempotent `process_request` job. The worker (system actor) extracts requirements as `proposed`, runs matching, and stops. `processing.stage` is derived from the job row and is the only source of truth for automatic processing. The business status stays `open`. Shortlist, share approval and sharing stay `USER_ONLY`. The UI drops "Run matching" from the normal flow, gets a processing card and a filterable pool, and the shell is regrouped as a Cadence HR desk.

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, PostgreSQL job queue, pytest (backend, `cadence-hr-hub/backend`); Next.js 15, React, vitest (frontend, `cadence-hr-hub/web`).

## Global Constraints

- Target app is `cadence-hr-hub` only. Do not touch `cadence-hackathon/`.
- Automatic = requirement extraction + candidate matching. Never automatic: shortlist, share approval, external sharing. `USER_ONLY` in `app/domain/transitions.py` must not change.
- Requirement approval is non-blocking. It is not a lifecycle step.
- `processing.stage` is one of `received | extracting | matching | complete | failed`. Business status stays `open` after processing.
- Lifecycle: Received → Requirements extracted → Matching complete → HR review → Shortlisted → Share approved → Shared.
- New candidate matches = stage `complete` AND (`pool_opened_at` is null OR `last_match_completed_at` > `pool_opened_at`).
- Opening the pool is idempotent: never overwrite `pool_opened_at`, never write a second "pool opened" audit event.
- Submission is idempotent: one active `process_request` job per request.
- No subsidiary login, no public endpoint. Subsidiaries appear only as "received from <company>".
- CV Intake and Excel import/export stay in navigation, under Candidates.
- RBAC is not changed.
- The folder is not a git repo. Steps say "Checkpoint" where a commit would go. Do not `git init`, push, or add AI attribution trailers.

## Spec deviations to record (found while reading the code)

The spec lists two new columns. The code needs four, all on `hiring_requests`:
`pool_opened_at`, `last_match_completed_at`, `pool_stale` (boolean, default false), `requested_count` (nullable int). `requested_count` is needed for "23 matched · 5 requested". Nothing stores it today. `run_match` also now matches on all requirements, not only approved ones, so `tests/test_requirement_review.py` needs one updated assertion (Task 2).

## File Structure

Backend (`cadence-hr-hub/backend`):
- Create `alembic/versions/a9d3c5e17b42_request_processing.py`: four columns.
- Modify `app/models/hiring.py`: four mapped columns.
- Modify `app/services/hiring.py`: system-capable actor check, `submit_request`, `open_pool`, stale flag on edit, `processing_view`, `request_view` additions.
- Modify `app/services/matching.py`: match all requirements, stamp `last_match_completed_at`, clear stale, allow system actor.
- Create `app/services/processing.py`: `enqueue_process`, `retry_process`, `run_process` (job handler).
- Modify `app/jobs/worker.py`: dispatch by `job_type`.
- Modify `app/api/hiring.py`: `requested_count` in body, submit flow, `/pool/open`, `/process/retry`, list payload.
- Modify `app/services/desk.py`: new counts and "needs you now".
- Tests: create `tests/test_request_processing.py`; modify `tests/test_requirement_review.py`, `tests/test_dashboard.py`.

Frontend (`cadence-hr-hub/web`):
- Modify `lib/api.ts`, `lib/lifecycle.ts`, `lib/labels.ts`, `lib/use-desk-counts.ts`, `lib/__tests__/lifecycle.test.ts`.
- Create `lib/pool-filters.ts` + `lib/__tests__/pool-filters.test.ts`.
- Create `app/hiring/processing-card.tsx`, `app/hiring/pool.tsx`.
- Modify `app/hiring/workspace.tsx`, `matches.tsx`, `requirements.tsx`, `new-request.tsx`, `index-view.tsx`.
- Modify `components/shell/nav.ts`, `sidebar.tsx`; create `lib/__tests__/nav.test.ts`.
- Modify `app/command/command-center.tsx`, `app/queue/queue.tsx`.

Backend test command: `cd cadence-hr-hub/backend && python -m pytest <path> -v` (Postgres on `localhost:15432` must be up: `docker compose up -d db` from `cadence-hr-hub`). Frontend: `cd cadence-hr-hub/web && npx vitest run <path>`.

---

### Task 1: Schema and model columns

**Files:**
- Create: `backend/alembic/versions/a9d3c5e17b42_request_processing.py`
- Modify: `backend/app/models/hiring.py:14-26`
- Test: `backend/tests/test_request_processing.py`

**Interfaces:**
- Produces: `HiringRequest.pool_opened_at: datetime | None`, `.last_match_completed_at: datetime | None`, `.pool_stale: bool` (default False), `.requested_count: int | None`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_request_processing.py`:

```python
"""Automatic processing: extraction and matching run in the worker. People decide everything after."""

from datetime import datetime, timezone

from app.models import HiringRequest
from app.services.hiring import create_request
from tests.test_corpus_gates import _actor

JD = "Required: Python\nPreferred: AWS\n"


def _new(session, actor, **extra):
    row = create_request(
        session,
        company_name="Acme Corp",
        job_title="Senior Backend Engineer",
        description=JD,
        received_at=datetime.now(timezone.utc),
        actor=actor,
        **extra,
    )
    session.commit()
    return row


def test_request_has_processing_columns(session):
    row = _new(session, _actor(session))
    fresh = session.get(HiringRequest, row.id)
    assert fresh.pool_opened_at is None
    assert fresh.last_match_completed_at is None
    assert fresh.pool_stale is False
    assert fresh.requested_count is None
```

- [ ] **Step 2: Run it to see it fail**

Run: `cd cadence-hr-hub/backend && python -m pytest tests/test_request_processing.py::test_request_has_processing_columns -v`
Expected: FAIL with `AttributeError: 'HiringRequest' object has no attribute 'pool_opened_at'`.

- [ ] **Step 3: Add the columns**

In `backend/app/models/hiring.py`, change the import line and add columns after `owner_user_id`:

```python
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
```

```python
    pool_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_match_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pool_stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    requested_count: Mapped[int | None] = mapped_column(Integer)
```

Create `backend/alembic/versions/a9d3c5e17b42_request_processing.py`:

```python
"""request processing state

Revision ID: a9d3c5e17b42
Revises: c8f1d4a07e63
Create Date: 2026-09-30 15:30:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9d3c5e17b42"
down_revision: Union[str, None] = "c8f1d4a07e63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("hiring_requests", sa.Column("pool_opened_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hiring_requests", sa.Column("last_match_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hiring_requests", sa.Column("pool_stale", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("hiring_requests", sa.Column("requested_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("hiring_requests", "requested_count")
    op.drop_column("hiring_requests", "pool_stale")
    op.drop_column("hiring_requests", "last_match_completed_at")
    op.drop_column("hiring_requests", "pool_opened_at")
```

- [ ] **Step 4: Make `create_request` accept `requested_count`**

In `backend/app/services/hiring.py`, add `requested_count: int | None = None,` to the `create_request` keyword parameters (after `actor: Actor,`) and `requested_count=requested_count,` to the `HiringRequest(...)` constructor.

- [ ] **Step 5: Run the test**

Run: `python -m pytest tests/test_request_processing.py::test_request_has_processing_columns -v`
Expected: PASS. (The session fixture upgrades to head, so the new migration is exercised. If `hub_test` already exists at an old revision, `alembic downgrade base` runs at the end of each session, so it is safe.)

- [ ] **Step 6: Checkpoint** (no git). Run `python -m pytest -q` and confirm nothing else regressed.

---

### Task 2: Matching without approval, system actor, stale and timestamps

**Files:**
- Modify: `backend/app/services/hiring.py` (`_recruiter` neighbours, `extract_requirements`, `update_requirement`)
- Modify: `backend/app/services/matching.py:35-90`
- Modify: `backend/tests/test_requirement_review.py:105-125`
- Test: `backend/tests/test_request_processing.py`

**Interfaces:**
- Produces: `hiring._actor_allowed(session, actor) -> None` (recruiter user or system actor; raises `TransitionError("forbidden")` otherwise). `run_match` and `extract_requirements` accept `SYSTEM`. `run_match` matches all requirements, sets `last_match_completed_at = now`, sets `pool_stale = False`. `update_requirement` sets `pool_stale = True` when the request has matches.
- Consumes: `SYSTEM` from `app.domain.actor`.

- [ ] **Step 1: Write failing tests** (append to `tests/test_request_processing.py`)

```python
import pytest
from sqlalchemy import select

from app.domain.actor import AGENT, SYSTEM
from app.domain.transitions import TransitionError
from app.models import CandidateMatch, RequestRequirement, Shortlist, SharingRecord
from app.services.hiring import extract_requirements, open_request, update_requirement
from app.services.matching import run_match
from tests.test_intelligence import _run
from tests.test_matching import ADA
from tests.test_corpus_gates import _actor as recruiter


def _candidate(session):
    from tests.test_matching import make_pdf  # noqa: F401  (same helper module the matching tests use)
    return _run(session, "ada.pdf", make_pdf(ADA))


def test_run_match_uses_unapproved_requirements(session):
    actor = recruiter(session)
    _candidate(session)
    row = _new(session, actor)
    open_request(session, row.id, actor)
    extract_requirements(session, row.id, actor)
    session.commit()
    matches = run_match(session, row.id, actor)
    session.commit()
    assert matches, "proposed requirements must be enough to match"
    assert session.get(type(row), row.id).last_match_completed_at is not None


def test_system_actor_can_extract_and_match_but_agent_cannot(session):
    actor = recruiter(session)
    row = _new(session, actor)
    open_request(session, row.id, actor)
    extract_requirements(session, row.id, SYSTEM)
    run_match(session, row.id, SYSTEM)
    with pytest.raises(TransitionError):
        extract_requirements(session, row.id, AGENT)


def test_edit_marks_pool_stale_and_rematch_clears_it(session):
    actor = recruiter(session)
    _candidate(session)
    row = _new(session, actor)
    open_request(session, row.id, actor)
    stored = extract_requirements(session, row.id, actor)
    run_match(session, row.id, actor)
    session.commit()
    first = session.get(type(row), row.id).last_match_completed_at
    update_requirement(session, row.id, stored[0].id, actor, strength="preferred")
    session.commit()
    assert session.get(type(row), row.id).pool_stale is True
    run_match(session, row.id, actor)
    session.commit()
    fresh = session.get(type(row), row.id)
    assert fresh.pool_stale is False
    assert fresh.last_match_completed_at > first


def test_matching_never_shortlists_or_shares(session):
    actor = recruiter(session)
    _candidate(session)
    row = _new(session, actor)
    open_request(session, row.id, actor)
    extract_requirements(session, row.id, SYSTEM)
    run_match(session, row.id, SYSTEM)
    session.commit()
    assert session.scalar(select(Shortlist.id)) is None
    assert session.scalar(select(SharingRecord.id)) is None
```

- [ ] **Step 2: Run to see failures**

Run: `python -m pytest tests/test_request_processing.py -v`
Expected: FAIL. `requirements_not_approved`, then `TransitionError: human_required` for SYSTEM.

- [ ] **Step 3: Implement**

In `backend/app/services/hiring.py` add next to `_recruiter`:

```python
def _actor_allowed(session: Session, actor: Actor) -> None:
    """Human recruiters and the worker's system actor may run the automatic steps. Nothing else."""
    if actor.kind == "system":
        return
    _recruiter(session, actor)
```

Replace `_recruiter(session, actor)` with `_actor_allowed(session, actor)` in `extract_requirements` only.

In `update_requirement`, after `row.review_status = "proposed"` add:

```python
    has_pool = session.scalar(
        select(func.count()).select_from(CandidateMatch).where(CandidateMatch.request_id == request_id)
    )
    if has_pool:
        request.pool_stale = True
```

In `backend/app/services/matching.py`:

```python
from datetime import datetime, timezone
from app.services.hiring import HiringError, _actor_allowed, _request
```

(drop `_recruiter` from that import), then in `run_match` replace `_recruiter(session, actor)` with `_actor_allowed(session, actor)` and change the requirement query:

```python
    requirements = session.scalars(
        select(RequestRequirement)
        .where(RequestRequirement.request_id == request_id)
        .order_by(RequestRequirement.position)
    ).all()
    if not requirements:
        raise HiringError("no_requirements")
```

After `transition(request, "open", ...)` add:

```python
    request.last_match_completed_at = datetime.now(timezone.utc)
    request.pool_stale = False
```

- [ ] **Step 4: Update the old assertion**

In `tests/test_requirement_review.py` replace the block from `open_request(...)` through the end of the verdict assertions (the "blocked" check and the Python-only approval) with:

```python
    open_request(session, request.id, actor)
    matches = run_match(session, request.id, actor)
    assert len(matches) == 1
    assert matches[0].candidate_id == document.candidate_id
    verdicts = session.execute(
        select(RequestRequirement.requirement_text, MatchRequirementResult.result)
        .join(MatchRequirementResult, MatchRequirementResult.requirement_id == RequestRequirement.id)
        .where(MatchRequirementResult.match_id == matches[0].id)
    ).all()
    assert {text.casefold() for text, _result in verdicts} == {row.requirement_text.casefold() for row in stored}
```

Keep the earlier `update_requirement` assertions above it. Remove the now-unused `approve_requirements` import only if nothing else uses it.

- [ ] **Step 5: Run**

Run: `python -m pytest tests/test_request_processing.py tests/test_requirement_review.py tests/test_matching.py -v`
Expected: PASS. If `test_matching.py` assumes approval before matching, keep its approve calls (they still work) and fix any assertion on `requirements_not_approved`.

- [ ] **Step 6: Checkpoint.** Run `python -m pytest -q`.

---

### Task 3: The `process_request` job, submission and processing view

**Files:**
- Create: `backend/app/services/processing.py`
- Modify: `backend/app/jobs/worker.py`, `backend/app/services/hiring.py` (`submit_request`, `request_view`), `backend/app/api/hiring.py:34-45,90-133`
- Test: `backend/tests/test_request_processing.py`

**Interfaces:**
- Produces:
  - `hiring.submit_request(session, request_id, actor) -> HiringRequest` (draft → submitted only).
  - `processing.PROCESS_REQUEST = "process_request"`.
  - `processing.enqueue_process(session, request_id) -> Job` (idempotent: returns the active job if one exists).
  - `processing.retry_process(session, request_id) -> Job` (new job after a failed one; the active one if still running).
  - `processing.run_process(session, job) -> None` (handler; stage kept in `job.payload["stage"]`).
  - `processing.processing_view(session, request_id) -> dict` returning `{"stage": ..., "matched_count": int, "requested_count": int | None}`.
  - `request_view(...)` gains `processing`, `pool_stale`, `pool_opened_at`, `last_match_completed_at`.
- Consumes: `create_request`, `extract_requirements`, `run_match`, `SYSTEM`.

Stage rules for `processing_view`: no `process_request` job → `complete` if the request has matches, else `received`. Latest job `queued`/`leased` → `received`; `running` → `payload["stage"]` (`extracting` or `matching`); `succeeded` → `complete`; `quarantined` or `failed` → `failed`.

- [ ] **Step 1: Write failing tests** (append)

```python
from app.jobs.queue import run_once
from app.models import AuditEvent, Job
from app.services.hiring import request_view, submit_request
from app.services.processing import (
    PROCESS_REQUEST,
    enqueue_process,
    processing_view,
    retry_process,
    run_process,
)


def _submitted(session, actor):
    row = _new(session, actor, requested_count=5)
    submit_request(session, row.id, actor)
    enqueue_process(session, row.id)
    session.commit()
    return row


def _drain(session):
    while run_once(session, worker_id="test", handler=run_process):
        pass


def test_worker_extracts_and_matches_then_stops_before_any_decision(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    assert processing_view(session, row.id)["stage"] == "received"
    _drain(session)
    session.expire_all()
    view = request_view(session, row.id)
    assert view["status"] == "open"
    assert view["processing"]["stage"] == "complete"
    assert view["processing"]["matched_count"] >= 1
    assert view["processing"]["requested_count"] == 5
    assert all(r["review_status"] == "proposed" for r in view["requirements"])
    assert session.scalar(select(Shortlist.id)) is None
    assert session.scalar(select(SharingRecord.id)) is None
    actors = {e.actor_kind for e in session.scalars(select(AuditEvent).where(AuditEvent.action == "matching_run"))}
    assert actors == {"system"}


def test_double_submit_creates_one_job_and_no_duplicates(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    enqueue_process(session, row.id)
    enqueue_process(session, row.id)
    session.commit()
    assert len(session.scalars(select(Job).where(Job.job_type == PROCESS_REQUEST)).all()) == 1
    _drain(session)
    enqueue_process(session, row.id)  # after completion: still no second job
    session.commit()
    _drain(session)
    reqs = session.scalars(select(RequestRequirement).where(RequestRequirement.request_id == row.id)).all()
    matches = session.scalars(select(CandidateMatch).where(CandidateMatch.request_id == row.id)).all()
    assert len(reqs) == len({r.requirement_text for r in reqs})
    assert len(matches) == len({m.candidate_id for m in matches})
    assert len(session.scalars(select(Job).where(Job.job_type == PROCESS_REQUEST)).all()) == 1


def test_failed_processing_reports_failed_and_retry_works(session, monkeypatch):
    actor = recruiter(session)
    row = _submitted(session, actor)

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.services.processing.extract_requirements", boom)
    from app.config import get_settings

    for _ in range(get_settings().job_max_attempts + 1):
        run_once(session, worker_id="test", handler=run_process)
    assert processing_view(session, row.id)["stage"] == "failed"
    monkeypatch.undo()
    retry_process(session, row.id)
    session.commit()
    _drain(session)
    assert processing_view(session, row.id)["stage"] == "complete"
```

- [ ] **Step 2: Run to see failures.**

Run: `python -m pytest tests/test_request_processing.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.processing`.

- [ ] **Step 3: Implement `submit_request`** in `hiring.py` (next to `open_request`):

```python
def submit_request(session: Session, request_id: UUID, actor: Actor) -> HiringRequest:
    _recruiter(session, actor)
    row = _request(session, request_id)
    if row.status == "draft":
        transition(row, "submitted", machine="hiring_request", actor=actor)
    return row
```

- [ ] **Step 4: Implement `app/services/processing.py`**

```python
"""Automatic processing of a received hiring request. The worker extracts and matches, and stops there."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain.actor import SYSTEM
from app.domain.transitions import transition
from app.jobs.errors import PermanentJobError
from app.models import CandidateMatch, HiringRequest, Job
from app.services.audit import write_audit
from app.services.hiring import HiringError, extract_requirements
from app.services.matching import run_match

PROCESS_REQUEST = "process_request"
_ACTIVE = ("queued", "leased", "running")


def _jobs(session: Session, request_id: UUID) -> list[Job]:
    return list(
        session.scalars(
            select(Job)
            .where(Job.job_type == PROCESS_REQUEST, Job.payload["request_id"].astext == str(request_id))
            .order_by(Job.created_at)
        ).all()
    )


def enqueue_process(session: Session, request_id: UUID) -> Job:
    """One active job per request. A finished request is not queued again."""
    jobs = _jobs(session, request_id)
    if jobs and (jobs[-1].status in _ACTIVE or jobs[-1].status == "succeeded"):
        return jobs[-1]
    return _insert(session, request_id, generation=len(jobs))


def retry_process(session: Session, request_id: UUID) -> Job:
    jobs = _jobs(session, request_id)
    if jobs and jobs[-1].status in _ACTIVE:
        return jobs[-1]
    return _insert(session, request_id, generation=len(jobs))


def _insert(session: Session, request_id: UUID, *, generation: int) -> Job:
    settings = get_settings()
    key = f"{request_id}:{generation}"
    job = Job(
        job_type=PROCESS_REQUEST,
        idempotency_key=key,
        processing_version=settings.processing_version,
        payload={"request_id": str(request_id), "stage": "received"},
        status="queued",
        attempts=0,
        max_attempts=settings.job_max_attempts,
        run_after=datetime.now(timezone.utc),
    )
    try:
        with session.begin_nested():
            session.add(job)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(Job).where(Job.job_type == PROCESS_REQUEST, Job.idempotency_key == key)
        )
        if existing is None:
            raise
        return existing
    write_audit(
        session,
        actor=SYSTEM,
        action="job_enqueued",
        entity_type="job",
        entity_id=job.id,
        detail={"request_id": str(request_id), "processing_version": settings.processing_version},
    )
    return job


def _stage(session: Session, job: Job, stage: str) -> None:
    job.payload = {**job.payload, "stage": stage}
    session.commit()


def run_process(session: Session, job: Job) -> None:
    """Worker handler. Extracts requirements and runs matching. It never shortlists or shares."""
    if job.job_type != PROCESS_REQUEST:
        from app.services.pipeline import run_extract

        return run_extract(session, job)
    request_id = UUID(job.payload["request_id"])
    request = session.get(HiringRequest, request_id)
    if request is None:
        raise PermanentJobError("request_missing")
    if request.status == "submitted":
        transition(request, "open", machine="hiring_request", actor=SYSTEM)
    has_pool = session.scalar(
        select(func.count()).select_from(CandidateMatch).where(CandidateMatch.request_id == request_id)
    )
    if has_pool:
        return  # already processed. A retry after success must not duplicate anything.
    _stage(session, job, "extracting")
    try:
        extract_requirements(session, request_id, SYSTEM)
    except HiringError as exc:
        raise PermanentJobError(exc.code) from exc
    session.commit()
    _stage(session, job, "matching")
    try:
        run_match(session, request_id, SYSTEM)
    except HiringError as exc:
        raise PermanentJobError(exc.code) from exc


def processing_view(session: Session, request_id: UUID) -> dict:
    request = session.get(HiringRequest, request_id)
    matched = session.scalar(
        select(func.count()).select_from(CandidateMatch).where(
            CandidateMatch.request_id == request_id,
            CandidateMatch.disposition.in_(("recommended", "needs_review")),
        )
    )
    jobs = _jobs(session, request_id)
    if not jobs:
        stage = "complete" if matched else "received"
    else:
        latest = jobs[-1]
        if latest.status in ("queued", "leased"):
            stage = "received"
        elif latest.status == "running":
            stage = latest.payload.get("stage", "extracting")
        elif latest.status == "succeeded":
            stage = "complete"
        else:
            stage = "failed"
    return {
        "stage": stage,
        "matched_count": int(matched or 0),
        "requested_count": request.requested_count if request else None,
    }
```

Note: the stage commits inside the handler commit the job row's payload while `run_once` still owns status, which is fine because `run_once` re-reads via the same session. If `job.payload` mutation is not detected, keep the reassignment (`job.payload = {**...}`) as written.

- [ ] **Step 5: Dispatch in the worker.** In `backend/app/jobs/worker.py` replace `from app.services.pipeline import run_extract` with `from app.services.processing import run_process` and `handler=run_extract` with `handler=run_process` (`run_process` delegates `extract_document` jobs to `run_extract`).

- [ ] **Step 6: Add the view fields.** In `hiring.request_view`, before `return {`, add `from app.services.processing import processing_view` (import inside the function to avoid a cycle) and `processing = processing_view(session, request_id)`; add to the returned dict:

```python
        "processing": processing,
        "pool_stale": row.pool_stale,
        "pool_opened_at": row.pool_opened_at.isoformat() if row.pool_opened_at else None,
        "last_match_completed_at": row.last_match_completed_at.isoformat() if row.last_match_completed_at else None,
        "requested_count": row.requested_count,
```

- [ ] **Step 7: Wire the API.** In `backend/app/api/hiring.py`: add `requested_count: int | None = Field(default=None, ge=1, le=500)` to `RequestBody`; import `submit_request` and `enqueue_process, retry_process`; in `post_request` after `create_request(..., requested_count=body.requested_count)` call:

```python
        submit_request(session, row.id, auth.actor)
        enqueue_process(session, row.id)
```

before `session.commit()`. Add the retry route:

```python
@router.post("/hiring-requests/{request_id}/process/retry", status_code=202)
def post_retry(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    del auth
    try:
        from app.services.hiring import _request

        _request(session, request_id)
        job = retry_process(session, request_id)
        session.commit()
    except HiringError as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"job_id": str(job.id), "status": job.status}
```

In `list_requests`, add `"requested_count": row.requested_count` and a `processing` field: `"processing": processing_view(session, row.id)["stage"]` and `"matched_count"` (import `processing_view`).

- [ ] **Step 8: Run.**

Run: `python -m pytest tests/test_request_processing.py tests/test_requirement_review.py tests/test_matching.py tests/test_foundation.py -v`
Expected: PASS. Then `python -m pytest -q` for the full suite.

- [ ] **Step 9: Checkpoint.**

---

### Task 4: Open the pool (idempotent) and the new desk counts

**Files:**
- Modify: `backend/app/services/hiring.py`, `backend/app/api/hiring.py`, `backend/app/services/desk.py`
- Test: `backend/tests/test_request_processing.py`, `backend/tests/test_dashboard.py`

**Interfaces:**
- Produces: `hiring.open_pool(session, request_id, actor) -> HiringRequest`. Route `POST /hiring-requests/{id}/pool/open` → `{"pool_opened_at": iso}`. `dashboard()["counts"]` gains `requests_received`, `new_matches`, `reviews_needing_attention`, `duplicate_reviews`. Dashboard gains `needs_you_now: list[DeskItem]`.
- A request counts as "received" while `processing_view.stage != "complete"`. A pool is "new" per the Global Constraints formula.

- [ ] **Step 1: Failing tests** (append to `test_request_processing.py`)

```python
from app.services.desk import dashboard
from app.services.hiring import open_pool


def test_open_pool_is_idempotent_and_audited_once(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    first = open_pool(session, row.id, actor)
    session.commit()
    stamp = first.pool_opened_at
    open_pool(session, row.id, actor)
    session.commit()
    again = session.get(type(row), row.id)
    assert again.pool_opened_at == stamp
    events = session.scalars(select(AuditEvent).where(AuditEvent.action == "pool_opened")).all()
    assert len(events) == 1


def test_new_matches_tile_follows_open_and_rematch(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    assert dashboard(session, actor)["counts"]["new_matches"] == 0
    _drain(session)
    assert dashboard(session, actor)["counts"]["new_matches"] == 1
    open_pool(session, row.id, actor)
    session.commit()
    assert dashboard(session, actor)["counts"]["new_matches"] == 0
    stamp = session.get(type(row), row.id).pool_opened_at
    run_match(session, row.id, actor)  # a re-run makes a new pool
    session.commit()
    assert session.get(type(row), row.id).pool_opened_at == stamp
    assert dashboard(session, actor)["counts"]["new_matches"] == 1
    open_pool(session, row.id, actor)  # opening again after a re-run moves the stamp forward
    session.commit()
    assert dashboard(session, actor)["counts"]["new_matches"] == 0
```

Note the last two lines: "opening once must not overwrite" applies to repeated opens of the *same* pool. After a re-run (`last_match_completed_at > pool_opened_at`), opening acknowledges the new pool. Implement `open_pool` accordingly: it writes the stamp and audit event only when `pool_opened_at is None or last_match_completed_at > pool_opened_at`. This keeps the spec's idempotency for repeat opens and makes the tile drop after re-match. Record this refinement in the spec's `pool_opened_at` bullet.

- [ ] **Step 2: Run to see failures** (`ImportError: open_pool`).

- [ ] **Step 3: Implement `open_pool`** in `hiring.py`:

```python
def open_pool(session: Session, request_id: UUID, actor: Actor) -> HiringRequest:
    _recruiter(session, actor)
    row = _request(session, request_id)
    if row.last_match_completed_at is None:
        raise HiringError("pool_not_ready")
    seen = row.pool_opened_at
    if seen is not None and row.last_match_completed_at <= seen:
        return row  # this pool was already opened. No new stamp, no new event.
    row.pool_opened_at = utcnow()
    write_audit(
        session,
        actor=actor,
        action="pool_opened",
        entity_type="hiring_request",
        entity_id=row.id,
        detail={"request_id": str(row.id), "outcome": "opened"},
    )
    return row
```

Route in `api/hiring.py`:

```python
@router.post("/hiring-requests/{request_id}/pool/open")
def post_open_pool(
    request_id: UUID,
    auth: Auth = Depends(require_recruiter),
    session: Session = Depends(get_session),
) -> dict:
    try:
        row = open_pool(session, request_id, auth.actor)
        session.commit()
    except (TransitionError, HiringError) as exc:
        session.rollback()
        raise _guard(exc) from None
    return {"pool_opened_at": row.pool_opened_at.isoformat() if row.pool_opened_at else None}
```

Add `open_pool` to the imports from `app.services.hiring`.

- [ ] **Step 4: Desk counts** in `desk.py`. Add helpers and extend `dashboard`:

```python
from app.services.processing import processing_view


def _requests_received(session: Session) -> list[HiringRequest]:
    rows = _active_requests(session)
    return [row for row in rows if processing_view(session, row.id)["stage"] != "complete"]


def _new_pools(session: Session) -> list[HiringRequest]:
    out = []
    for row in _active_requests(session):
        if processing_view(session, row.id)["stage"] != "complete" or row.last_match_completed_at is None:
            continue
        if row.pool_opened_at is None or row.last_match_completed_at > row.pool_opened_at:
            out.append(row)
    return out
```

In `dashboard`, compute `received = _requests_received(session)`, `pools = _new_pools(session)` and add to `counts`:

```python
            "requests_received": len(received),
            "new_matches": len(pools),
            "duplicate_reviews": len(reviews),
            "reviews_needing_attention": len(reviews) + len(requirements) + len(matches) + len(shares),
```

Add `"new_match_pools": [_request_item(row) for row in pools[:_LIMIT]]` and:

```python
        "needs_you_now": sorted(
            [
                *[_item("new_matches", _request_label(r), "pool_ready", r.last_match_completed_at, f"/hiring?request={r.id}") for r in pools],
                *[_share_item(session, row) for row in shares],
                *[_review_item(session, row) for row in reviews],
            ],
            key=lambda item: item["created_at"],
        )[:_LIMIT],
```

(Oldest first, since these are waiting on a person. `created_at` is an ISO string so string sort is chronological.)

- [ ] **Step 5: Extend `tests/test_dashboard.py`** with one assertion that a fresh dashboard has `counts["new_matches"] == 0` and `needs_you_now == []`. Run it.

- [ ] **Step 6: Run everything.** `python -m pytest -q` Expected: all PASS. Also add to the boundary test: `assert dashboard(...)["counts"]["shortlisted_candidates"] == 0` after processing.

- [ ] **Step 7: Checkpoint.**

---

### Task 5: Share approval stays human (test only)

**Files:**
- Test: `backend/tests/test_request_processing.py`

- [ ] **Step 1: Write the test** (append). Follow the existing pattern in `tests/test_sharing.py`; read it first to reuse its fixtures for a shortlisted candidate.

```python
from app.services.hiring import shortlist_match
from app.services.sharing import SendError, approve_share


def test_share_path_is_human_only(session):
    actor = recruiter(session)
    _candidate(session)
    row = _submitted(session, actor)
    _drain(session)
    match = session.scalars(select(CandidateMatch).where(CandidateMatch.request_id == row.id)).first()
    with pytest.raises(TransitionError):
        shortlist_match(session, row.id, match.id, SYSTEM)
    entry = shortlist_match(session, row.id, match.id, actor)
    session.commit()
    with pytest.raises((TransitionError, SendError)):
        approve_share(session, row.id, entry.candidate_id, SYSTEM)
    approve_share(session, row.id, entry.candidate_id, actor)  # explicit human approval works
```

- [ ] **Step 2: Run.** `python -m pytest tests/test_request_processing.py::test_share_path_is_human_only -v`. Expected: PASS. If `approve_share` by the same recruiter is rejected, RBAC requires a distinct approver: assert exactly what RBAC does and do not change RBAC.

- [ ] **Step 3: Checkpoint.**

---

### Task 6: Frontend API types and lifecycle

**Files:**
- Modify: `web/lib/api.ts` (types around 217-272, 308-313, 522-525, Dashboard type at 127)
- Modify: `web/lib/lifecycle.ts`, `web/lib/__tests__/lifecycle.test.ts`, `web/lib/labels.ts`

**Interfaces:**
- Produces:
  - `type ProcessingStage = "received" | "extracting" | "matching" | "complete" | "failed"`
  - `type Processing = { stage: ProcessingStage; matched_count: number; requested_count: number | null }`
  - `HiringRequestDetail` gains `processing: Processing; pool_stale: boolean; pool_opened_at: string | null; last_match_completed_at: string | null; requested_count: number | null`
  - `RequestSummary` gains `processing: ProcessingStage; matched_count: number; requested_count: number | null`
  - `createHiringRequest` input gains `requested_count?: number`
  - `openPool(id): Promise<{pool_opened_at: string | null}>`, `retryProcessing(id): Promise<{job_id: string; status: string}>`
  - `Dashboard.counts` gains `requests_received, new_matches, duplicate_reviews, reviews_needing_attention`; `Dashboard.needs_you_now: DeskItem[]`
  - `deriveLifecycle(input: LifecycleInput): Step[]` with new `LifecycleInput = { processing: ProcessingStage; matchCount: number; reviewed: number; shortlisted: number | null; sharesApproved: number; shared: number }` and step keys `received | extracted | matched | review | shortlist | approved | shared`.

- [ ] **Step 1: Rewrite `lib/__tests__/lifecycle.test.ts`**

```typescript
import { describe, it, expect } from "vitest";
import { deriveLifecycle } from "@/lib/lifecycle";

const base = { processing: "complete" as const, matchCount: 23, reviewed: 0, shortlisted: 0, sharesApproved: 0, shared: 0 };
const states = (i: Parameters<typeof deriveLifecycle>[0]) => deriveLifecycle(i).map((s) => s.state);

describe("deriveLifecycle", () => {
  it("has the seven stages in order, without a requirement-approval step", () => {
    expect(deriveLifecycle(base).map((s) => s.label)).toEqual([
      "Received",
      "Requirements extracted",
      "Matching complete",
      "HR review",
      "Shortlisted",
      "Share approved",
      "Shared",
    ]);
  });
  it("is waiting on extraction while received", () => {
    expect(states({ ...base, processing: "received", matchCount: 0 })).toEqual(["done", "current", "locked", "locked", "locked", "locked", "locked"]);
  });
  it("is waiting on matching while extracting is done", () => {
    expect(states({ ...base, processing: "matching", matchCount: 0 })).toEqual(["done", "done", "current", "locked", "locked", "locked", "locked"]);
  });
  it("hands over to HR review once matching completes", () => {
    expect(states(base)).toEqual(["done", "done", "done", "current", "locked", "locked", "locked"]);
  });
  it("moves to shortlist after HR has decided on someone", () => {
    expect(states({ ...base, reviewed: 3 })).toEqual(["done", "done", "done", "done", "current", "locked", "locked"]);
  });
  it("moves to share approval once someone is shortlisted", () => {
    expect(states({ ...base, reviewed: 5, shortlisted: 5 })).toEqual(["done", "done", "done", "done", "done", "current", "locked"]);
  });
  it("completes when a share was sent", () => {
    expect(states({ ...base, reviewed: 5, shortlisted: 5, sharesApproved: 1, shared: 1 })).toEqual(Array(7).fill("done"));
  });
  it("shows the failure on the processing step", () => {
    const steps = deriveLifecycle({ ...base, processing: "failed", matchCount: 0 });
    expect(steps[1].detail).toMatch(/failed/i);
  });
  it("treats an unknown shortlist as not done and says so", () => {
    const steps = deriveLifecycle({ ...base, shortlisted: null });
    expect(steps[4].detail).toMatch(/unknown/i);
  });
  it("says how far sharing got", () => {
    const steps = deriveLifecycle({ ...base, reviewed: 1, shortlisted: 1, sharesApproved: 1 });
    expect(steps[5].detail).toBe("1 approved, not sent");
  });
});
```

- [ ] **Step 2: Run to see failure.** `cd cadence-hr-hub/web && npx vitest run lib/__tests__/lifecycle.test.ts` → FAIL.

- [ ] **Step 3: Rewrite `lib/lifecycle.ts`**

```typescript
import type { ProcessingStage } from "@/lib/api";

export type StepState = "done" | "current" | "locked";
export type Step = {
  key: "received" | "extracted" | "matched" | "review" | "shortlist" | "approved" | "shared";
  label: string;
  state: StepState;
  detail: string;
};
export type LifecycleInput = {
  /** Automatic processing. This is the source of truth for the first three steps. */
  processing: ProcessingStage;
  matchCount: number;
  /** Matches HR shortlisted or rejected. */
  reviewed: number;
  /** null when the shortlist could not be read. */
  shortlisted: number | null;
  sharesApproved: number;
  shared: number;
};

/**
 * Requirement approval is not a step. Requirements are extracted automatically and usable for matching;
 * HR may review them at any time and an edit only makes the pool stale.
 */
export function deriveLifecycle(input: LifecycleInput): Step[] {
  const extracted = ["matching", "complete"].includes(input.processing);
  const matched = input.processing === "complete";
  const shortlisted = input.shortlisted ?? 0;
  const reviewDone = input.reviewed > 0 || shortlisted > 0 || input.shared > 0;
  const shortlistDone = shortlisted > 0 || input.shared > 0;
  const approvedDone = input.sharesApproved > 0 || input.shared > 0;
  const sharedDone = input.shared > 0;
  const failed = input.processing === "failed";

  const raw: { key: Step["key"]; label: string; done: boolean; detail: string }[] = [
    { key: "received", label: "Received", done: true, detail: "Logged by Cadence HR" },
    {
      key: "extracted",
      label: "Requirements extracted",
      done: extracted,
      detail: failed ? "Processing failed" : extracted ? "Automatic" : "In progress",
    },
    {
      key: "matched",
      label: "Matching complete",
      done: matched,
      detail: matched ? `${input.matchCount} matched` : failed ? "Processing failed" : "In progress",
    },
    {
      key: "review",
      label: "HR review",
      done: reviewDone,
      detail: reviewDone ? `${input.reviewed} decided` : matched ? "Nothing decided yet" : "After matching",
    },
    {
      key: "shortlist",
      label: "Shortlisted",
      done: shortlistDone,
      detail:
        input.shortlisted === null && matched ? "State unknown" : shortlistDone ? `${shortlisted} shortlisted` : "None yet",
    },
    {
      key: "approved",
      label: "Share approved",
      done: approvedDone,
      detail: approvedDone ? (sharedDone ? "Approved" : `${input.sharesApproved} approved, not sent`) : "Needs a shortlist",
    },
    { key: "shared", label: "Shared", done: sharedDone, detail: sharedDone ? `${input.shared} shared` : "Not sent" },
  ];

  let currentAssigned = false;
  return raw.map((step) => {
    if (step.done) return { key: step.key, label: step.label, state: "done", detail: step.detail };
    if (!currentAssigned) {
      currentAssigned = true;
      return { key: step.key, label: step.label, state: "current", detail: step.detail };
    }
    return { key: step.key, label: step.label, state: "locked", detail: step.detail };
  });
}
```

- [ ] **Step 4: Update `lib/api.ts`.** Add the types listed under Interfaces. Concretely: add `export type ProcessingStage = "received" | "extracting" | "matching" | "complete" | "failed";` and `export type Processing = {...}` above `HiringRequestDetail`; extend `HiringRequestDetail`, `RequestSummary` and `Dashboard["counts"]` as listed, add `needs_you_now: DeskItem[]` and `new_match_pools: DeskItem[]` to `Dashboard`; extend `createHiringRequest`'s input with `requested_count?: number`; add:

```typescript
export function openPool(id: string) {
  return request<{ pool_opened_at: string | null }>(`/hiring-requests/${id}/pool/open`, { method: "POST" });
}

export function retryProcessing(id: string) {
  return request<{ job_id: string; status: string }>(`/hiring-requests/${id}/process/retry`, { method: "POST" });
}
```

Leave `runHiringMatch` (it becomes the secondary "Re-run matching"). In `lib/labels.ts` add:

```typescript
export const PROCESSING_STAGE: Record<string, string> = {
  received: "Received",
  extracting: "Extracting requirements",
  matching: "Matching candidates",
  complete: "Matching complete",
  failed: "Processing failed",
};
```

- [ ] **Step 5: Run.** `npx vitest run lib` → lifecycle tests PASS. `npx tsc --noEmit` will fail in `workspace.tsx` until Task 8; that is expected.

- [ ] **Step 6: Checkpoint.**

---

### Task 7: Pool filters (pure logic)

**Files:**
- Create: `web/lib/pool-filters.ts`, `web/lib/__tests__/pool-filters.test.ts`

**Interfaces:**
- Produces:
  - `type PoolFilters = { matchStatus: "all" | "strong" | "review"; skill: string; location: string; minYears: number | null }`
  - `EMPTY_FILTERS: PoolFilters`
  - `filterPool(matches: PoolMatch[], filters: PoolFilters): PoolMatch[]`
  - `PoolMatch = CandidateMatch & { years_of_experience?: number | null; location?: string | null }`
  - `matchBadge(disposition: string): { label: "Strong match" | "Needs review" | "Excluded" | "Rejected"; tone: Tone }`

Backend gap: `_match_payload` does not return candidate years or location. Add `years_of_experience` (from `Candidate.years_of_experience`) and `location` in Step 4 below. If `Candidate` has no location column, return `None` and show the Location filter only when at least one match has a location.

- [ ] **Step 1: Write the failing tests**

```typescript
import { describe, it, expect } from "vitest";
import { EMPTY_FILTERS, filterPool, matchBadge, type PoolMatch } from "@/lib/pool-filters";

const m = (over: Partial<PoolMatch>): PoolMatch =>
  ({
    id: "1",
    candidate_id: "c1",
    candidate_name: "Ada",
    disposition: "recommended",
    explanation: null,
    strengths: ["Python"],
    gaps: [],
    requirements: [],
    years_of_experience: 6,
    location: "Berlin",
    ...over,
  }) as PoolMatch;

describe("filterPool", () => {
  const pool = [
    m({ id: "1", disposition: "recommended", years_of_experience: 8, location: "Berlin", strengths: ["Python", "SQL"] }),
    m({ id: "2", disposition: "needs_review", years_of_experience: 2, location: "Lagos", strengths: ["SQL"] }),
    m({ id: "3", disposition: "excluded", years_of_experience: 10, location: "Berlin", strengths: [] }),
  ];
  it("returns everything with empty filters", () => {
    expect(filterPool(pool, EMPTY_FILTERS)).toHaveLength(3);
  });
  it("filters by match status", () => {
    expect(filterPool(pool, { ...EMPTY_FILTERS, matchStatus: "strong" }).map((x) => x.id)).toEqual(["1"]);
    expect(filterPool(pool, { ...EMPTY_FILTERS, matchStatus: "review" }).map((x) => x.id)).toEqual(["2"]);
  });
  it("filters by skill, case-insensitively, against strengths", () => {
    expect(filterPool(pool, { ...EMPTY_FILTERS, skill: "python" }).map((x) => x.id)).toEqual(["1"]);
  });
  it("filters by minimum years", () => {
    expect(filterPool(pool, { ...EMPTY_FILTERS, minYears: 5 }).map((x) => x.id)).toEqual(["1", "3"]);
  });
  it("filters by location", () => {
    expect(filterPool(pool, { ...EMPTY_FILTERS, location: "lag" }).map((x) => x.id)).toEqual(["2"]);
  });
  it("drops candidates with unknown years when a minimum is set", () => {
    expect(filterPool([m({ years_of_experience: null })], { ...EMPTY_FILTERS, minYears: 1 })).toHaveLength(0);
  });
});

describe("matchBadge", () => {
  it("labels dispositions for HR", () => {
    expect(matchBadge("recommended").label).toBe("Strong match");
    expect(matchBadge("needs_review").label).toBe("Needs review");
  });
});
```

- [ ] **Step 2: Run to see failure** (`Cannot find module`).

- [ ] **Step 3: Implement `lib/pool-filters.ts`**

```typescript
import type { CandidateMatch } from "@/lib/api";
import type { Tone } from "@/lib/labels";

export type PoolMatch = CandidateMatch & { years_of_experience?: number | null; location?: string | null };

export type PoolFilters = {
  matchStatus: "all" | "strong" | "review";
  skill: string;
  location: string;
  minYears: number | null;
};

export const EMPTY_FILTERS: PoolFilters = { matchStatus: "all", skill: "", location: "", minYears: null };

export function matchBadge(disposition: string): { label: "Strong match" | "Needs review" | "Excluded" | "Rejected"; tone: Tone } {
  switch (disposition) {
    case "recommended":
      return { label: "Strong match", tone: "proposed" };
    case "needs_review":
      return { label: "Needs review", tone: "warn" };
    case "rejected":
      return { label: "Rejected", tone: "neutral" };
    default:
      return { label: "Excluded", tone: "neutral" };
  }
}

export function filterPool(matches: PoolMatch[], f: PoolFilters): PoolMatch[] {
  const skill = f.skill.trim().toLowerCase();
  const place = f.location.trim().toLowerCase();
  return matches.filter((m) => {
    if (f.matchStatus === "strong" && m.disposition !== "recommended") return false;
    if (f.matchStatus === "review" && m.disposition !== "needs_review") return false;
    if (skill && !m.strengths.some((s) => s.toLowerCase().includes(skill))) return false;
    if (place && !(m.location ?? "").toLowerCase().includes(place)) return false;
    if (f.minYears !== null && (m.years_of_experience ?? -1) < f.minYears) return false;
    return true;
  });
}
```

- [ ] **Step 4: Backend: expose years and location in the match payload.** In `backend/app/api/hiring.py::_match_payload` add to the returned dict:

```python
        "years_of_experience": float(candidate.years_of_experience) if candidate and candidate.years_of_experience is not None else None,
        "location": getattr(candidate, "location", None) if candidate else None,
```

Then add `years_of_experience?: number | null; location?: string | null;` to `CandidateMatch` in `web/lib/api.ts` and use `CandidateMatch` in place of the `PoolMatch` intersection if you prefer. Add a one-line assertion in `tests/test_request_processing.py::test_worker_extracts_and_matches...` that `"years_of_experience"` is a key of the first match from `GET /hiring-requests/{id}/matches` (use `TestClient(app)` with the `RECRUITER` header as in `tests/test_matching.py`).

- [ ] **Step 5: Run.** `npx vitest run lib/__tests__/pool-filters.test.ts` → PASS.

- [ ] **Step 6: Checkpoint.**

---

### Task 8: Request detail page (processing card, pool, requirements panel)

**Files:**
- Create: `web/app/hiring/processing-card.tsx`, `web/app/hiring/pool.tsx`
- Modify: `web/app/hiring/workspace.tsx`, `web/app/hiring/requirements.tsx`, `web/app/hiring/new-request.tsx`
- Modify: `web/app/hiring/matches.tsx` (becomes the row component only, see Step 4)
- Test: `web/app/hiring/__tests__/processing-card.test.tsx`

**Interfaces:**
- Consumes: `Processing`, `openPool`, `retryProcessing`, `filterPool`, `matchBadge`, `deriveLifecycle` (new input).
- Produces: `<ProcessingCard processing={Processing} status={string} onRetry={() => void} />`; `<Pool matches shortlist busy filters onFilters selected onSelect onShortlistSelected onReject onShare />`.

Design notes for the implementer: keep the existing `PanelRow`/`Tag`/`Button` primitives. Polling: while `processing.stage` is `received|extracting|matching`, call `detailQ.reload()` and `matchesQ.reload()` every 2 s with `setInterval` in a `useEffect` keyed on the stage, and clear it on unmount.

- [ ] **Step 1: Write the failing component test** (`web/app/hiring/__tests__/processing-card.test.tsx`). Look at `app/compare/__tests__/compare-view.test.tsx` first and copy its render setup.

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ProcessingCard } from "../processing-card";

describe("ProcessingCard", () => {
  it("shows the finished checklist and the pool summary", () => {
    render(<ProcessingCard processing={{ stage: "complete", matched_count: 23, requested_count: 5 }} status="open" onRetry={vi.fn()} />);
    expect(screen.getByText(/Requirements extracted/)).toBeInTheDocument();
    expect(screen.getByText(/Candidate matching completed/)).toBeInTheDocument();
    expect(screen.getByText(/23 candidates matched/)).toBeInTheDocument();
    expect(screen.getByText(/Requested: 5/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /run matching/i })).toBeNull();
  });
  it("shows progress while matching", () => {
    render(<ProcessingCard processing={{ stage: "matching", matched_count: 0, requested_count: 5 }} status="open" onRetry={vi.fn()} />);
    expect(screen.getByText(/Matching candidates/)).toBeInTheDocument();
  });
  it("offers a retry when processing failed", () => {
    const retry = vi.fn();
    render(<ProcessingCard processing={{ stage: "failed", matched_count: 0, requested_count: null }} status="open" onRetry={retry} />);
    screen.getByRole("button", { name: /retry/i }).click();
    expect(retry).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run** `npx vitest run app/hiring` → FAIL (module missing).

- [ ] **Step 3: Implement `processing-card.tsx`**

```tsx
"use client";

import type { Processing } from "@/lib/api";
import { REQUEST_STATUS } from "@/lib/labels";
import { Button, LinkButton } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { StatusText } from "@/components/ui/tag";

const ORDER = ["received", "extracting", "matching", "complete"] as const;

function Row({ done, active, children }: { done: boolean; active: boolean; children: React.ReactNode }) {
  return (
    <li className="flex items-center gap-2 text-[14px]">
      <span aria-hidden="true" className={done ? "text-ok-ink" : active ? "text-human-ink" : "text-mut"}>
        {done ? "✓" : active ? "…" : "○"}
      </span>
      <span className={done || active ? "" : "text-mut"}>{children}</span>
    </li>
  );
}

export function ProcessingCard({
  processing,
  status,
  onRetry,
}: {
  processing: Processing;
  status: string;
  onRetry: () => void;
}) {
  const at = ORDER.indexOf(processing.stage as (typeof ORDER)[number]);
  const failed = processing.stage === "failed";
  const complete = processing.stage === "complete";
  return (
    <Panel as="section" className="space-y-3 p-5" aria-label="Request processing">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-mut">Request received</h2>
        <StatusText tone={status === "open" ? "ok" : "neutral"}>{REQUEST_STATUS[status] ?? status}</StatusText>
      </div>
      <ul className="space-y-1.5">
        <Row done active={false}>Request received</Row>
        <Row done={at >= 2} active={processing.stage === "extracting"}>
          {processing.stage === "extracting" ? "Extracting requirements" : "Requirements extracted"}
        </Row>
        <Row done={complete} active={processing.stage === "matching"}>
          {processing.stage === "matching" ? "Matching candidates" : "Candidate matching completed"}
        </Row>
      </ul>
      {failed ? (
        <div role="alert" className="flex flex-wrap items-center gap-3">
          <span className="text-bad-ink">Automatic processing failed.</span>
          <Button onClick={onRetry}>Retry processing</Button>
        </div>
      ) : null}
      {complete ? (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-3">
          <p>
            <span className="text-[22px] font-semibold tabular-nums">{processing.matched_count} candidates matched</span>
            {processing.requested_count ? <span className="ml-3 text-mut">Requested: {processing.requested_count}</span> : null}
          </p>
          <LinkButton variant="primary" href="#pool">
            View candidate pool
          </LinkButton>
        </div>
      ) : null}
    </Panel>
  );
}
```

If `Panel` does not accept `aria-label`, wrap the content in a `<section aria-label=...>` instead. Check `components/ui/panel.tsx`.

- [ ] **Step 4: Implement `pool.tsx`.** The pool has a filter bar (match status chips: All / Strong match / Needs review; text inputs for skill and location; number input for minimum years), a `N results` count using `filterPool`, one row per candidate (checkbox, name link, `matchBadge`, met/total requirements, "Shortlisted" tag, an "unreviewed requirements" note when `match.requirements.some(r => r.strength)` is not needed: instead show a small "Based on auto-extracted requirements" line once in the header), and a sticky bottom bar **Shortlist selected (n)**. Reuse `MatchCard` from `matches.tsx` for expanded evidence by exporting it. Selection state is `Set<string>` of match ids; the bar calls `onShortlistSelected(ids)` which the workspace implements by calling `shortlistMatch` sequentially and then clearing the selection. Never pre-select anything. Chips use `Chip` from `components/ui/chip.tsx` (see `prefer-chips-for-short-choices`: match status is a short single-select). Component skeleton:

```tsx
"use client";

import { useMemo, useState } from "react";
import type { CandidateMatch } from "@/lib/api";
import { EMPTY_FILTERS, filterPool, matchBadge, type PoolFilters } from "@/lib/pool-filters";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { Tag } from "@/components/ui/tag";
import { MatchCard, type ShortlistState } from "./matches";

export function Pool({
  matches,
  shortlist,
  busy,
  jobTitle,
  onShortlistSelected,
  onReject,
  onShare,
}: {
  matches: CandidateMatch[];
  shortlist: Record<string, ShortlistState>;
  busy: boolean;
  jobTitle: string;
  onShortlistSelected: (matchIds: string[]) => void;
  onReject: (match: CandidateMatch) => void;
  onShare: (match: CandidateMatch) => void;
}) {
  const [filters, setFilters] = useState<PoolFilters>(EMPTY_FILTERS);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [limit, setLimit] = useState(20);
  const shown = useMemo(() => filterPool(matches, filters), [matches, filters]);
  const toggle = (id: string) =>
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  // ...render: filter bar, "{shown.length} results", rows (checkbox + MatchCard), Show more, sticky bar
  return null;
}
```

Fill in the render body using the same primitives as `matches.tsx` (`Panel`, `Button`, `Tag`). Required accessibility: each checkbox labelled `Select <name>`, the bar `role="region" aria-label="Shortlist selection"`, filter inputs with `<label>`s. The **Shortlist selected** button is disabled when `selected.size === 0` and only enabled for matches whose disposition is `recommended`/`needs_review` and not already shortlisted; already-shortlisted rows show "Review share…" (existing `onShare`) instead of a checkbox.

In `matches.tsx`: export `MatchCard` and `ShortlistState`, delete the `Matches` wrapper and its "Run matching" `Button` (the file keeps only `MatchCard` and its types). Remove the `Matches` import from `workspace.tsx`.

- [ ] **Step 5: Update `workspace.tsx`.**
  1. Imports: drop `extractHiringRequirements`, `approveHiringRequirements`, `openHiringRequest`; add `openPool`, `retryProcessing`; import `ProcessingCard` and `Pool`.
  2. Replace `onExtract`/`onApprove`/`onRun` with:

```tsx
  const onRetry = async () => {
    if (await run(() => retryProcessing(requestId), "Processing restarted")) detailQ.reload();
  };
  const onRerun = async () => {
    if (await run(() => runHiringMatch(requestId), "Matching re-run. Nothing was shortlisted or shared.")) {
      setShortlist({});
      matchesQ.reload();
      detailQ.reload();
    }
  };
  const onShortlistSelected = async (matchIds: string[]) => {
    for (const id of matchIds) {
      const match = matches.find((m) => m.id === id);
      if (!match) continue;
      const ok = await run(() => shortlistMatch(requestId, id));
      if (ok) setShortlist((cur) => ({ ...cur, [match.candidate_id]: "yes" }));
    }
    notify("Shortlist updated. Nothing was shared.");
    void refreshDesk();
  };
```

  3. On the first render where `detail.processing.stage === "complete"`, call `openPool(requestId)` once (a `useEffect` guarded by a `useRef` boolean). It is idempotent on the server, so a duplicate call is harmless. Then `void refreshDesk()` so the sidebar and tiles update.
  4. Polling effect:

```tsx
  const stage = detail?.processing.stage;
  useEffect(() => {
    if (!stage || !["received", "extracting", "matching"].includes(stage)) return;
    const id = setInterval(() => {
      detailQ.reload();
      matchesQ.reload();
    }, 2000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);
```

  5. Lifecycle call becomes:

```tsx
  const reviewed = matches.filter((m) => m.disposition === "rejected").length + shortlistedCount;
  const steps = deriveLifecycle({
    processing: detail?.processing.stage ?? "received",
    matchCount: detail?.processing.matched_count ?? 0,
    reviewed,
    shortlisted: anyUnknown ? null : shortlistedCount,
    sharesApproved: approvedShares,
    shared: detail?.candidates_shared ?? 0,
  });
```

  6. Delete the sentence under the stepper that says progress is worked out from requirement approvals. Replace with nothing.
  7. Header sub: `Received from <strong>{company}</strong> · {date}`; keep the status `StatusText` (business status), it now sits beside the processing card's own status chip, so remove it from `PageHeader.actions` to avoid duplication.
  8. Layout order in the left column: `<ProcessingCard .../>`, then `<section id="pool">` with `RuleHeading` "Matched candidates" and `<Pool .../>` (show only when `stage === "complete"`), then the requirements panel.
  9. Sharing: `SharePanel` and the "Review share…" button already only exist for shortlisted candidates. Keep. Add a line above the pool: `Shortlisted: {shortlistedCount} of {matches.length}` (this is the visible transition asserted in the walkthrough).

- [ ] **Step 6: Requirements panel.** In `requirements.tsx` remove the "Extract requirements" and "Approve" buttons from the normal flow. Wrap the panel in `<details>` (collapsed) with summary `Requirements · Auto-extracted · Review optional`. Keep inline edit. Add props `poolStale: boolean; onRerun: () => void`. When `poolStale`, render above the list:

```tsx
<div role="status" className="proposal px-3 py-2">
  <strong>Candidate pool may be stale.</strong> Requirements changed after matching.
  <Button className="ml-3" variant="primary" busy={busy} onClick={onRerun}>Re-run matching</Button>
</div>
```

Label each row `Unreviewed` (a `Tag tone="proposed"`) when `review_status === "proposed"`. The tag text must never say "approved" for unreviewed items.

- [ ] **Step 7: New request form.** In `new-request.tsx`: title "Log received request"; sub "Enter what the subsidiary sent Cadence HR. Requirements are extracted and candidates matched automatically. A person decides what happens next."; add a number field `Candidates requested` (`min=1`) bound to `requested`, sent as `requested_count`; button label `Log request`; after success `notify("Request logged. Processing has started.")`.

- [ ] **Step 8: Run.**

Run: `npx vitest run` → all PASS. `npx tsc --noEmit` → no errors. `npm run lint` if configured.

- [ ] **Step 9: Checkpoint.**

---

### Task 9: Navigation regroup and filter views

**Files:**
- Modify: `web/components/shell/nav.ts`, `web/components/shell/sidebar.tsx`, `web/app/hiring/index-view.tsx`, `web/app/queue/queue.tsx`, `web/lib/use-desk-counts.ts`
- Create: `web/lib/__tests__/nav.test.ts`, `web/lib/request-views.ts`, `web/lib/__tests__/request-views.test.ts`

**Interfaces:**
- Produces:
  - `NavItem` gains `children?: { href: string; label: string; match: (path: string, search: URLSearchParams) => boolean; badge?: "reviews" }[]`.
  - `NAV_GROUPS` per the spec tree.
  - `requestView(r: RequestSummary): "processing" | "complete" | "closed"` and `filterRequests(rows, view: "all" | "processing" | "complete" | "closed")` in `lib/request-views.ts`.
  - Hiring index reads `?view=`; queue reads `?type=` (already does).

- [ ] **Step 1: Failing tests**

`lib/__tests__/request-views.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { filterRequests } from "@/lib/request-views";
import type { RequestSummary } from "@/lib/api";

const r = (over: Partial<RequestSummary>): RequestSummary =>
  ({ id: "1", company: "Acme", job_title: "SBE", status: "open", received_at: "2026-09-30T00:00:00Z", processing: "complete", matched_count: 0, requested_count: null, ...over }) as RequestSummary;

const rows = [r({ id: "a", processing: "matching" }), r({ id: "b" }), r({ id: "c", status: "closed" })];

describe("filterRequests", () => {
  it("all returns everything", () => expect(filterRequests(rows, "all")).toHaveLength(3));
  it("new / processing", () => expect(filterRequests(rows, "processing").map((x) => x.id)).toEqual(["a"]));
  it("matching complete excludes closed", () => expect(filterRequests(rows, "complete").map((x) => x.id)).toEqual(["b"]));
  it("completed means closed or shared", () => expect(filterRequests(rows, "closed").map((x) => x.id)).toEqual(["c"]));
});
```

`lib/__tests__/nav.test.ts`:

```typescript
import { describe, it, expect } from "vitest";
import { ALL_NAV, NAV_GROUPS, pageLabel } from "@/components/shell/nav";

describe("navigation", () => {
  it("keeps CV intake and Excel import under Candidates", () => {
    const candidates = NAV_GROUPS.flatMap((g) => g.items).find((i) => i.label === "Candidates");
    const labels = candidates?.children?.map((c) => c.label);
    expect(labels).toEqual(["Candidate Intelligence", "Search", "Source Candidate", "CV Intake", "Excel Import & Export"]);
  });
  it("has the four hiring request views", () => {
    const hiring = ALL_NAV.find((i) => i.label === "Hiring Requests");
    expect(hiring?.children?.map((c) => c.label)).toEqual(["All Requests", "New / Processing", "Matching Complete", "Completed"]);
  });
  it("has the four review queue views", () => {
    const queue = ALL_NAV.find((i) => i.label === "Review Queue");
    expect(queue?.children?.map((c) => c.label)).toEqual(["CV Updates / Duplicates", "Requirement Reviews", "Match Reviews", "Sharing Approvals"]);
  });
  it("labels the hiring detail page", () => expect(pageLabel("/hiring")).toBe("Hiring Requests"));
});
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implement `lib/request-views.ts`**

```typescript
import type { RequestSummary } from "@/lib/api";

export type RequestView = "all" | "processing" | "complete" | "closed";

export function filterRequests(rows: RequestSummary[], view: RequestView): RequestSummary[] {
  const done = (r: RequestSummary) => ["closed", "shared", "cancelled"].includes(r.status);
  if (view === "processing") return rows.filter((r) => !done(r) && r.processing !== "complete");
  if (view === "complete") return rows.filter((r) => !done(r) && r.processing === "complete");
  if (view === "closed") return rows.filter(done);
  return rows;
}
```

- [ ] **Step 4: Rewrite `nav.ts`** groups. Keep `IconName`s that exist (`grid`, `users`, `briefcase`, `upload`, `inbox`, `link`, `table`, `shield`, `alert`). Structure (top-level items with `children`; `href` of the parent points at its first child):

```typescript
export const NAV_GROUPS: { label: string; items: NavItem[] }[] = [
  {
    label: "Cadence HR desk",
    items: [
      { href: "/", label: "Command Center", icon: "grid", match: (p) => p === "/" },
      {
        href: "/hiring",
        label: "Hiring Requests",
        icon: "briefcase",
        match: (p) => p.startsWith("/hiring"),
        children: [
          { href: "/hiring", label: "All Requests", match: (p, q) => p.startsWith("/hiring") && !q.get("view") },
          { href: "/hiring?view=processing", label: "New / Processing", match: (p, q) => p.startsWith("/hiring") && q.get("view") === "processing" },
          { href: "/hiring?view=complete", label: "Matching Complete", match: (p, q) => p.startsWith("/hiring") && q.get("view") === "complete" },
          { href: "/hiring?view=closed", label: "Completed", match: (p, q) => p.startsWith("/hiring") && q.get("view") === "closed" },
        ],
      },
      {
        href: "/candidates",
        label: "Candidates",
        icon: "users",
        match: (p) => ["/candidates", "/merge", "/search", "/source", "/intake", "/data"].some((s) => p.startsWith(s)),
        children: [
          { href: "/candidates", label: "Candidate Intelligence", match: (p) => p.startsWith("/candidates") || p.startsWith("/merge") },
          { href: "/search", label: "Search", match: (p) => p.startsWith("/search") },
          { href: "/source", label: "Source Candidate", match: (p) => p.startsWith("/source") },
          { href: "/intake", label: "CV Intake", match: (p) => p.startsWith("/intake") },
          { href: "/data", label: "Excel Import & Export", match: (p) => p.startsWith("/data") },
        ],
      },
      {
        href: "/queue",
        label: "Review Queue",
        icon: "inbox",
        badge: "decisions",
        match: (p) => p.startsWith("/queue") || p.startsWith("/compare"),
        children: [
          { href: "/queue?type=relationship_review", label: "CV Updates / Duplicates", match: (p, q) => p.startsWith("/compare") || q.get("type") === "relationship_review" },
          { href: "/queue?type=requirement_approval", label: "Requirement Reviews", match: (p, q) => q.get("type") === "requirement_approval" },
          { href: "/queue?type=match_review", label: "Match Reviews", match: (p, q) => q.get("type") === "match_review" },
          { href: "/queue?type=share_approval", label: "Sharing Approvals", match: (p, q) => q.get("type") === "share_approval" },
        ],
      },
    ],
  },
  {
    label: "Oversight",
    items: [
      { href: "/reports", label: "Reports", icon: "table", match: (p) => p.startsWith("/reports") && false },
      { href: "/audit", label: "Audit Trail", icon: "shield", match: (p) => p.startsWith("/audit") },
      { href: "/reports", label: "Problem Reports", icon: "alert", match: (p) => p.startsWith("/reports"), badge: "reports" },
    ],
  },
];
```

Check what `/reports` actually is before wiring "Reports": in this app `/reports` is the Problem Reports page (`app/reports`, `Problem reports` label). If there is no separate analytics page, do **not** add a duplicate "Reports" item; keep one item labelled "Problem Reports" and note in the checkpoint that the spec's "Reports" line refers to the same page. Delete the placeholder "Reports" entry above if so. Update `pageLabel`, `MOBILE_TABS` (unchanged) and export `NavChild` type. `NavItem.match` keeps its `(path)` signature; children use `(path, search)`.

- [ ] **Step 5: Sidebar.** In `sidebar.tsx` `NavList`, read `useSearchParams()` (wrap the component in `<Suspense>` in `Sidebar`/`NavDrawer` as Next requires), render each item, and when `item.match(path)` is true render its `children` as an indented `<ul>` of links with `aria-current` from `child.match(path, search)`. Show the badge on the parent as today. Footer text: `Cadence HR desk` / `Internal workspace`. Brand subtitle: `HR intelligence hub` (unchanged).

- [ ] **Step 6: Hiring index view.** In `index-view.tsx` read `const view = (useSearchParams().get("view") ?? "all") as RequestView`, apply `filterRequests(data.requests, view)`, title per view (`All requests`, `New / processing`, `Matching complete`, `Completed`), rename the header action to `Log received request` and the empty-state to "No requests yet. Log what a subsidiary sends Cadence HR and it is processed automatically." Add columns `Processing` (`PROCESSING_STAGE[r.processing]`) and `Matched` (`{matched_count}` plus ` · {requested_count} requested` when present). Ensure `page.tsx` wraps `IndexView` in `Suspense` if it does not already.

- [ ] **Step 7: Queue.** `queue.tsx` already supports `?type=`. Confirm each of the four types in the nav filters the list; no change is expected. If it does not filter, add the filter using `groupQueue`'s existing group `type`.

- [ ] **Step 8: Desk counts hook.** In `use-desk-counts.ts` set `decisions: c.reviews_needing_attention` (falling back to the old sum if the field is missing).

- [ ] **Step 9: Run** `npx vitest run` → PASS; `npx tsc --noEmit` → clean.

- [ ] **Step 10: Checkpoint.**

---

### Task 10: Command Center as the Cadence HR desk

**Files:**
- Modify: `web/app/command/command-center.tsx`
- Test: `web/app/command/__tests__/command-center.test.tsx`

**Interfaces:**
- Consumes: `Dashboard.counts.{requests_received,new_matches,reviews_needing_attention,shortlisted_candidates,shares_awaiting_approval,duplicate_reviews,open_problem_reports}`, `Dashboard.needs_you_now`.

- [ ] **Step 1: Failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Loaded } from "../command-center";
import type { Dashboard } from "@/lib/api";

const desk = {
  counts: {
    requests_received: 2,
    new_matches: 1,
    reviews_needing_attention: 6,
    shortlisted_candidates: 3,
    shares_awaiting_approval: 2,
    duplicate_reviews: 1,
    open_problem_reports: 4,
    relationship_reviews: 1,
    requirements_awaiting_approval: 1,
    matches_awaiting_review: 2,
    active_hiring_requests: 3,
  },
  needs_you_now: [{ type: "new_matches", subject: "Acme Corp · Senior Backend Engineer", status: "pool_ready", created_at: "2026-09-30T10:00:00Z", href: "/hiring?request=1" }],
  new_match_pools: [],
  relationship_reviews: [], requirements_awaiting_approval: [], matches_awaiting_review: [], shortlisted_candidates: [],
  shares_awaiting_approval: [], open_problem_reports: [], recent_activity: [], active_hiring_requests: [], viewer_id: "u",
} as unknown as Dashboard;

describe("Command Center", () => {
  it("shows the seven desk tiles and needs-you-now, framed as an internal workspace", () => {
    render(<Loaded desk={desk} />);
    for (const label of [
      /Hiring requests received/,
      /New candidate matches/,
      /Reviews needing attention/,
      /Shortlists awaiting action/,
      /Sharing approvals/,
      /Duplicate \/ update reviews/,
      /Problem reports/,
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByText(/Needs you now/)).toBeInTheDocument();
    expect(screen.getByText(/Acme Corp/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** → FAIL (`Loaded` not exported / tiles missing).

- [ ] **Step 3: Implement.** In `command-center.tsx`: `export function Loaded`; page header eyebrow `Cadence HR desk` / `Internal workspace`; sub `Requests received from subsidiaries are processed automatically. What happens next is your decision.`; primary action `Log received request` (href `/hiring?new=1`). Replace the Kpi panel with a grid of seven `Tile` links (reuse `Kpi`'s layout wrapped in `Link`):

| Label | Value | Note | href |
|---|---|---|---|
| Hiring requests received | `requests_received` | New and processing | `/hiring?view=processing` |
| New candidate matches | `new_matches` | Pool ready, not yet opened | `/hiring?view=complete` |
| Reviews needing attention | `reviews_needing_attention` | Across all review types | `/queue` |
| Shortlists awaiting action | `shortlisted_candidates` | Shortlisted, not yet shared | `/queue?type=share_approval` |
| Sharing approvals | `shares_awaiting_approval` | Waiting for a person | `/queue?type=share_approval` |
| Duplicate / update reviews | `duplicate_reviews` | CVs that may match a profile | `/queue?type=relationship_review` |
| Problem reports | `open_problem_reports` | Reported by the team | `/reports` |

Replace the "Attention needed" panel with **Needs you now**: `desk.needs_you_now` rows (title `subject`, sub `Waiting {relativeAge(created_at)}`, right-aligned type tag mapped: `new_matches`→"New pool", `share_approval`→"Share approval", `relationship_review`→"CV review"), empty state "Nothing is waiting for you." Keep "Requests in progress" (rename "Requests from subsidiaries", subject already reads `Company · Title`) and the audit panel. Subsidiary names only ever appear as request sources in row text.

- [ ] **Step 4: Run** `npx vitest run app/command` → PASS; `npx tsc --noEmit` clean.

- [ ] **Step 5: Checkpoint.**

---

### Task 11: End-to-end walkthrough

**Files:**
- Create: `scripts/walkthrough-request-flow.md` (the recorded results; screenshots go in `docs/superpowers/walkthrough/`)
- Modify (seed): `scripts/` seed script if one exists. Check `ls scripts` first.

This task produces evidence, not code. Use the `run` skill / the browser tools available in the session. Report failures as they occur; do not paper over them.

- [ ] **Step 1: Bring the stack up.** From `cadence-hr-hub`: `docker compose up -d --build`. Confirm API, worker and web are healthy (`docker compose ps`). The worker must be running: it does the processing.

- [ ] **Step 2: Seed demo data** so a request for **5** candidates yields about **23** matches: ingest at least 23 CVs that satisfy the demo job description (use `cvs/` and any seed script in `scripts/`; check `ls ../cvs scripts`). Write the job description with two mandatory requirements that most CVs meet. Record how many CVs were ingested.

- [ ] **Step 3: Walk the flow in the browser** and capture a screenshot at each numbered point:
  1. Log a received request: company Acme Corp, "Senior Backend Engineer", requested 5. The processing card advances through Received → extracting → matching.
  2. Command Center: "New candidate matches" shows 1 and "Needs you now" lists the request.
  3. Open the request. It reads **N candidates matched · Requested: 5** (target ≈ 23). The tile drops to 0 on return to the Command Center. Reload the request page and confirm the tile stays 0 (idempotent).
  4. Filter by skill and by match status; the results count changes. Compare two candidates in the evidence view.
  5. Select some candidates and press **Shortlist selected**. Confirm nothing was shared, that the count reads `Shortlisted: k of N`, and that **Review share…** appears only on shortlisted rows.
  6. Edit a requirement. The stale banner appears; press **Re-run matching**; the banner clears; the Command Center tile shows 1 again; open the pool; 0.
  7. Approve the share explicitly, then share (local mail sender in dev).
  8. Audit trail: every step is present, with `system` shown for extraction/matching/job events and `user` for shortlist, share approval and share.

- [ ] **Step 4: Boundary check in the database.** Right after processing completes and before step 5, run:

```bash
docker compose exec db psql -U hub -d hub -c "select (select count(*) from shortlists) as shortlists, (select count(*) from sharing_records) as shares;"
```

Expected: `0 | 0`.

- [ ] **Step 5: Double-submit check.** Submit the same request form twice quickly (double-click). Confirm one request is created, or, if two requests are created (the form is not deduplicated), that each has exactly one `process_request` job: `select payload->>'request_id', count(*) from jobs where job_type='process_request' group by 1;`. Note that two requests from two submits is expected and is not the guarded case. The guarded case is `enqueue_process` called twice for one request, covered by the Task 3 test.

- [ ] **Step 6: Write `scripts/walkthrough-request-flow.md`** with the counts observed, the screenshots' paths, and any failures. State plainly what passed and what did not.

- [ ] **Step 7: Run all suites one last time.** `cd backend && python -m pytest -q`; `cd ../web && npx vitest run && npx tsc --noEmit`. Report exact counts.

---

## Self-review against the spec

- Automatic extraction + matching via worker job: Tasks 2, 3. No shortlist/share by the worker: Tasks 2, 3, 5 tests.
- `processing.stage` source of truth, `open` business status: Task 3 `processing_view`, Task 8 card.
- Non-blocking, unreviewed requirements: Task 2 (matches all), Task 8 Step 6 (Unreviewed tag, stale banner, secondary re-run).
- `pool_opened_at`, `last_match_completed_at`, idempotent open, re-match makes the pool new: Task 1, Task 4.
- Submission idempotency: Task 3 test.
- Desk tiles and "Needs you now": Tasks 4, 10. Navigation with CV Intake and Excel kept: Task 9.
- Lifecycle without a requirement-approval step: Task 6.
- Requested count and 23-vs-5 demo: Task 1 (`requested_count`), Task 8 (card), Task 11.
- Shortlist count visible and share approval only for shortlisted: Task 8 Step 5.9, Task 11 step 5.
- Spec deviations (four columns; matching on all requirements; `open_pool` re-acknowledges a re-run pool): recorded at the top and in Task 4. Update the spec's backend bullets to match when executing.

Known open points the executor must resolve by reading code, not guess: whether a `Candidate.location` column exists (Task 7 Step 4), whether `/reports` is only Problem Reports (Task 9 Step 4), whether `Panel` accepts `aria-label` (Task 8 Step 3), and whether RBAC lets the same recruiter approve their own shortlist (Task 5).

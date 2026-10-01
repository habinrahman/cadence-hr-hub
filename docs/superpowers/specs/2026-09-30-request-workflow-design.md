# Request-driven workflow: automatic matching, HR-owned decisions

Target app: `cadence-hr-hub` (backend + `web`). The copies under `cadence-hackathon/` are not touched.

## Product model

A subsidiary sends Cadence HR a hiring requirement. The system does the intelligence work immediately and gives Cadence HR a broad candidate pool. Cadence HR makes every decision.

- **Automatic:** requirement extraction and candidate matching.
- **Human:** requirement review/editing, filtering, shortlisting, share approval, sharing.
- **Never automatic:** shortlist, share approval, external sharing. The worker actor is refused these transitions (`USER_ONLY` in `app/domain/transitions.py` stays as is).

Subsidiaries are request sources ("received from Acme Corp"), not users. Requests enter through an internal **Log received request** form; there is no subsidiary login or public endpoint.

## Update 2026-09-30: provisional and confirmed pools (final, supersedes decision 1 and the design-1 approval gate)

Flow: request → extract proposed requirements → automatic matching → **provisional** pool → HR reviews/edits/approves
requirements → automatic rematch on approved requirements only → **confirmed** pool → shortlist → share approval → share.

- Matching is never blocked on approval. The `received` job extracts, then runs `run_match(..., provisional=True)` on the
  proposed rows. Proposed requirements stay proposed and are labelled "Proposed · not approved".
- Approving requirements marks the pool stale and queues a `process_request` job with reason `approved`, which runs
  `run_match` on approved rows only (the default; it refuses with `requirements_not_approved` when there are none).
- `hiring.pool_status(request)` is derived, with no new column: `none` before any match; `confirmed` only when every
  requirement is approved, `pool_stale` is false and no matching job is queued or running; otherwise `provisional`.
  It is returned as `processing.pool_status`.
- A rematch compares the committed requirement rows before and after it runs. If an approval or edit landed meanwhile it
  leaves `pool_stale` set, and `enqueue_match` queues a fresh job instead of reusing one that already started.
- Gate: `shortlist_match` refuses with `pool_provisional` (409), and `approve_share` and `send_share` refuse with
  `pool_provisional` (409), unless the pool is confirmed. Viewing the provisional pool is never gated. Share approval is
  still a separate, explicit recruiter action. Scoring, duplicate/update, audit and RBAC are unchanged.
- An edit sends that requirement back to proposed, so the pool is provisional again until re-approval and rematch.
- `awaiting_approval` now only means no requirement was proposed: nothing can be matched until HR adds one.
- UI: "Provisional match pool — Based on automatically extracted requirements — review requirements before
  shortlisting." with shortlist, share and reject disabled (a rejection would not survive the approval rematch, which
  rewrites dispositions); "Confirmed match pool — Matched against HR-approved requirements." once confirmed.

## Decisions

1. Requirement approval is **non-blocking**. Matching runs on extracted (`proposed`) requirements. HR may review or edit them; an edit marks the pool stale and exposes a secondary **Re-run matching**.
2. Automatic processing is a **backend job** on submit, reusing the existing job queue and worker.
3. `processing.stage` (`received | extracting | matching | complete | failed`) is the source of truth for automatic processing. The business status stays `open` after processing and is displayed separately.

## Backend changes (small, no re-architecture)

- `POST /hiring-requests` moves the request to `submitted` and enqueues a `process_request` job. The job opens the request, extracts requirements (kept as `proposed`), runs matching, and leaves the request `open`.
- `run_match` no longer requires approved requirements. Requirement flow: `proposed` → used for initial automatic matching → marked **unreviewed** in match results → HR may review/edit → if edited, pool is stale and re-match is offered. The UI never implies auto-extracted requirements are HR-approved facts.
- Editing a requirement sets a pool-stale flag. Re-running matching clears it.
- Request view returns `processing: { stage, matched_count, requested_count }`, plus `pool_stale`, `pool_opened_at` and `last_match_completed_at`.
- Migration adds four columns to the hiring request: `pool_opened_at` and `last_match_completed_at` (nullable), `pool_stale` (boolean, default false) and `requested_count` (nullable int, entered on the Log received request form; needed for "23 matched · 5 requested"). `run_match` matches on all requirements, approved or not. Opening the pool after a re-run acknowledges the new pool: the stamp and one audit event are written only when the pool was never opened or `last_match_completed_at` > `pool_opened_at`; repeat opens of the same pool change nothing.
- (Original wording follows.) Migration adds `pool_opened_at` and `last_match_completed_at` (both nullable) to the hiring request. `last_match_completed_at` is set every time matching completes (initial run and re-runs). Opening the pool sets `pool_opened_at` and writes one audit event. That operation is **idempotent**: reopening does not overwrite the timestamp or create another event. A re-run does not reset `pool_opened_at`; it moves `last_match_completed_at` past it, which is what makes the pool "new" again.
- A failed job sets stage `failed`; retry re-enqueues.
- **Submission is idempotent.** Only one active `process_request` job exists per request (use the existing job idempotency key infrastructure). A duplicate submit or retry must not create a second job or duplicate requirements/match rows.
- Desk counts service gains: requests received, new matches, sharing approvals. **New candidate matches** = stage `complete` AND (`pool_opened_at` is null OR `last_match_completed_at` > `pool_opened_at`).

## Hiring request detail (`hiring/workspace.tsx`, `lib/lifecycle.ts`)

Top to bottom:

1. Header: role title, "Received from <company> · date", business status chip (OPEN).
2. Processing card driven by `processing.stage`: Request received / Requirements extracted / Candidate matching completed. Spinner and polling while running; retry on failure.
3. Summary: "N candidates matched · Requested: M" with **View candidate pool** as the primary action. No "Run matching" in the normal flow.
4. Matched candidates: filters (experience, skills, location, match status), badges (Strong match / Needs review), checkbox selection, **Shortlist selected** bar. Shortlisting is a deliberate HR click.
5. Requirements panel, collapsed: "Auto-extracted · Review optional". After an edit: "Candidate pool may be stale" with **Re-run matching**.
6. Sharing approval becomes available once candidates are shortlisted.

Lifecycle steps: Received → Requirements extracted → Matching complete → HR review → Shortlisted → Share approved → Shared. Requirement approval is not a step.

## Command Center and navigation

Framed as the **Cadence HR Desk**. Tiles, each linking to its view:

- Hiring requests received (new and processing)
- New candidate matches: processing complete and the current pool not yet opened (never opened, or re-matched since it was opened)
- Reviews needing attention: sum of pending duplicate reviews, untouched requirement reviews, match reviews (`Needs review` in an unopened/unreviewed pool) and sharing approvals
- Shortlists awaiting action
- Sharing approvals
- Duplicate / update reviews
- Problem reports

"Needs you now" list below, ordered by age, each row linking to its item. Recent activity feed kept.

Navigation (mobile tabs unchanged):

```
Command Center
Hiring Requests: All Requests | New / Processing | Matching Complete | Completed   (/hiring?view=)
Candidates: Candidate Intelligence | Search | Source Candidate | CV Intake | Excel Import & Export
Review Queue: CV Updates / Duplicates | Requirement Reviews | Match Reviews | Sharing Approvals   (/queue?type=)
Reports
Audit Trail
Problem Reports
```

Filter views are query params on existing pages, not new pages.

## Kept unchanged

Candidate profile, evidence-first comparison, duplicate compare workspace, matching, requirement extraction, shortlist, approval, sharing, audit, RBAC, problem reports, Excel, CV intake. The system proposes, HR reviews, HR decides.

## Testing

Backend (pytest):
- Create request, run worker: requirements `proposed`, matches exist, `processing.stage == complete`, status `open`.
- Boundary: after processing there are zero shortlist rows and zero sharing records; the worker actor is refused shortlist approval and sharing.
- `run_match` works with unapproved requirements and marks results unreviewed; requirement edit sets stale; re-run clears it.
- Job failure gives stage `failed`; retry works.
- Duplicate submission/retry is idempotent: one active `process_request` job per request, no duplicated requirements or match rows.
- `pool_opened_at` set once, one audit event, idempotent on reopen; desk counts reflect it.
- Re-match after open: `pool_opened_at` unchanged, `last_match_completed_at` advances, the new-matches count goes back to 1, and drops to 0 when the pool is opened again.
- Share approval is a separate explicit human action (shortlist, request share approval, human approval, share), and the worker/system cannot perform that transition. Whether approver must differ from requester depends on the current RBAC model; the test asserts what RBAC actually supports, without changing RBAC.
- Existing backend tests still pass.

Frontend (vitest): lifecycle derivation from `processing.stage`; nav grouping and filter matching; desk tile mapping.

## End-to-end walkthrough (docker compose, browser-driven, screenshots)

Demo data: the request asks for **5** candidates and matching produces about **23**, so the UI reads "23 candidates matched · 5 requested". HR works from the 23; the system never picks exactly 5.

1. Log a received request from Acme Corp; processing card advances through its stages.
2. Command Center "New candidate matches" shows 1.
3. Open the pool; tile drops to 0; reopening changes nothing.
4. Filter by skills and match status; compare two candidates.
5. Shortlist selected candidates; confirm nothing was shared. Confirm the shortlist count updates (e.g. Shortlisted: 5 of 23) and that the sharing approval action is available only for shortlisted candidates.
6. Edit a requirement; see the stale banner; re-run matching.
7. Request share approval, approve explicitly, share.
8. Audit trail shows each step, with worker and human actors distinguished.

Failures are reported as they occur.

## Delivery order

1. Backend hook, migration, tests
2. Lifecycle and request detail page
3. Navigation and Command Center
4. End-to-end walkthrough

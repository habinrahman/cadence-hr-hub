# Demo Data: batch CV intake and reset — design

Date: 2026-09-30
Status: approved in conversation; not committed (user instruction: do not commit or push)

## Purpose

The Isa demo loop needs to start from an empty operational database, ingest the full CV corpus quickly, run the request → matching → review → shortlist → share walkthrough, then reset and repeat. Today the UI only uploads one CV at a time and there is no reset.

Two operator controls on a new `/demo` page solve this. They are demo tooling, separate from the normal product flow: CV Intake (`/intake`) stays the production-style single-CV path and is not changed.

## Decisions (locked in conversation)

- Upload goes through the **existing** `POST /documents` endpoint, one file per request, controlled concurrency (~4). No bulk endpoint, no server-side folder ingest, no demo-only seed path. The ingestion pipeline is untouched.
- All displayed counts are **dynamic**, derived from upload responses and a live status endpoint. Nothing about the corpus outcome (documents created, reviews, OCR, quarantined) is hard-coded.
- Reset wipes all operational/demo data and keeps users, tokens, and the append-only audit trail. The reset itself writes one `demo_reset` audit event so the wipe is a visible administrative action.
- Reset is recruiter-only and the route exists only when `environment == "local"` (the demo runs locally from Docker). Elsewhere it is a 404.
- No commit and no push of any of this work.

## Components

### 1. `POST /demo/reset` (backend)

- Recruiter role required; engineer receives 403.
- Router is registered only when `settings.environment == "local"`; otherwise the route does not exist.
- Body must be `{"confirm": "RESET"}`; anything else is a 400.
- One service function `reset_demo_data(session, actor)` runs bulk `DELETE`s in FK-safe order across every operational table: match requirement results, candidate matches, shortlist candidates, shortlists, approval decisions, sharing records, request notes, request attachments, request requirements, hiring requests, duplicate reviews, quarantine records, extraction evidence, document chunks, document pages, candidate experiences, education, skills, certificates, contacts, candidate sources, applications, candidate documents, field locks, agent runs, jobs, Excel import rows and imports, problem reports, candidates.
- Kept: `users`, `audit_events`.
- All deletes and the audit insert are one transaction; any failure rolls everything back.
- After the deletes, append `AuditEvent(action="demo_reset", actor=<the recruiter>)` with minimal allowlisted detail (`outcome: "reset"`; no counts, no PII).
- Response: `{"reset_at": "<iso>"}`.

### 2. `GET /demo/status` (backend)

- Same recruiter-only, local-only registration as reset.
- Returns live counts from existing tables: candidates, documents (total and by status), pending relationship/duplicate reviews, quarantined documents, OCR-flagged documents (per the codebase's existing status/text-source vocabulary), hiring requests, matches, shortlists, shares.
- Read-only; used by the demo page to render the ingestion panel and the post-reset zero state.

### 3. `/demo` page (frontend)

New sidebar group at the bottom: **DEMO / DATA** with one item, "Demo data". The page has two panels.

**Load CV corpus**

- Folder picker (`webkitdirectory`) for selecting the whole `cvs/` folder, with multi-select as fallback.
- Shows `N files selected` (dynamic), then uploads with concurrency 4 via the existing `uploadDocument` client.
- Live progress: `Uploaded x / N`, plus running `Uploaded` and `Failed` counts. Per-file failures (unsupported type, too large, network) are collected with their reason and listed at the end; the loop continues.
- After uploads finish, an **Ingestion** section polls `GET /demo/status` every few seconds while any document is still processing and renders the reported counts (documents created, processed, relationship reviews, OCR required, quarantined) — whatever the backend actually reports.
- Closing line points at CV Intake for per-document review.

**Reset demo data**

- Danger-styled panel. The confirm dialog requires typing `RESET` before the confirm button enables.
- On success shows the returned timestamp and notes the action is recorded as `demo_reset`.
- The page shows "Last reset: …" from the most recent `demo_reset` audit event (via the existing audit list endpoint), and the zeroed status counts after a reset.

## Error handling

- Upload loop: per-file errors are caught and reported; the batch continues. The final summary lists failures by filename and reason.
- Reset: all-or-nothing transaction; on failure nothing is wiped and the error is shown.
- Status polling failure shows a quiet inline error and stops polling; it never blocks the page.

## Testing

Backend (pytest):

- Reset empties every listed table and keeps users and audit events.
- Exactly one `demo_reset` audit event is written, by the recruiter, with no PII in detail.
- Engineer role → 403; wrong/missing confirm phrase → 400; route absent (404) when `environment != "local"`.
- After reset, uploading a CV through `POST /documents` works and status counts move off zero (the demo loop as a test).
- `GET /demo/status` returns the documented count fields and is recruiter-only.

Frontend (vitest):

- `upload-batch.ts` pure logic: concurrency cap respected, progress callbacks fire, per-file failures collected without aborting the batch.
- Reset dialog requires the typed phrase `RESET`.
- Demo page renders dynamic counts from mocked responses; no hard-coded corpus numbers anywhere.

## Out of scope

- Bulk upload endpoint; server-side folder ingest; any change to the ingestion pipeline or to CV Intake.
- Deleting audit events or users, ever.
- Committing or pushing this work.

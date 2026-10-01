# Demo-cycle validation — measured evidence (2026-09-30)

Real end-to-end run of the demo loop against the Compose stack (api :8000, worker, web :3000, postgres, mailpit),
driven by `scripts/demo_cycle.py` (same endpoints the browser uses) and `scripts/spotcheck_demo_page.py` (headless Chrome).
Corpus: `cvs/` = 488 files (459 PDF, 26 DOCX, 3 JPEG/JPG).

## Scripted cycle (`python scripts/demo_cycle.py`), verbatim output

```
reset ok, zero verified (5.6s)
488 files in cvs/
uploaded 488 (472 new), failed 0, in 8.7s
processing settled in 78.6s
{
  "documents": 472,
  "documents_by_status": {
    "profiled": 348,
    "quarantined": 5,
    "extracted": 3,
    "needs_ocr": 2,
    "needs_review": 114
  },
  "identity_outcomes": {
    "updated_cv": 59,
    "duplicate": 10,
    "ambiguous": 3,
    "different_candidate": 42,
    "new": 351
  },
  "candidates": 351,
  "pending_reviews": 114,
  "needs_ocr": 2,
  "quarantined": 5,
  "failed": 0,
  "processing": 0,
  "open_jobs": 0,
  "hiring_requests": 0,
  "matches": 0,
  "shortlisted": 0,
  "shares": 0,
  "last_reset_at": "2026-09-30T13:10:06.553656+00:00",
  "quarantine_records": 5
}
second reset ok, zero verified (total 95.0s)
```

## What passed

- Reset -> zero verified (documents 0, candidates 0) before and after the load.
- 488 files uploaded through `POST /documents` at concurrency 4 in 8.7 s, 0 upload failures.
  472 created new documents; 16 were byte-identical duplicates already on record (dedupe held: no duplicate documents/jobs/candidates).
- Worker drained the queue in 78.6 s after upload finished (0 failed documents). Full cycle wall time: 95.0 s.
- Final state: 472 documents (348 profiled, 114 needs_review, 5 quarantined, 3 extracted, 2 needs_ocr), 351 candidates.
- Browser spot-check (`scripts/spotcheck_demo_page.py`, headless system Chrome) after the cycle's closing reset:
  - `/demo` renders live counts from `GET /demo/status` (zeros), folder picker input carries `webkitdirectory`, both picker buttons present.
  - Sidebar shows the `Demo / Data` group; the page shows `Last reset: 30 Sep 2026, 13:11 UTC` (the cycle's second reset).
  - Reset dialog confirm stays disabled for empty and lowercase `reset`, enables only on exact `RESET`. Dialog was cancelled; no extra reset performed.
  - 0 browser console errors.
  - Screenshots: `docs/superpowers/demo-cycle/demo-page-zero-state.png`, `docs/superpowers/demo-cycle/demo-reset-dialog.png`.

## Honest caveats

- 3 documents rest at `extracted` (not `profiled`) with `open_jobs` 0 — stable end state, also seen in an earlier informal run; not an error, but visible on the page.
- Identity outcomes vary slightly run to run (informal run: updated_cv 61 / ambiguous 4 / different_candidate 39; this run: 59 / 3 / 42; `new` 351 both times). Concurrent processing order affects which near-duplicate is resolved first.
- Timings are this machine, this corpus, local deterministic extraction. Do not quote "processes in seconds" for other hardware/corpora; the measured numbers are above.

## Second run (after final-review fixes)

The final whole-branch review landed six fixes after the first run (desk counts scoped to untouched pools,
all-or-nothing `run_process`, permanent-error mapping, shortlist toast honesty, storage cleanup on reset,
restored verdict assertions). The stack was rebuilt and the cycle re-run against the fixed code:

```
reset ok, zero verified (1.1s)
488 files in cvs/
uploaded 488 (472 new), failed 0, in 21.7s
processing settled in 75.6s
second reset ok, zero verified (total 101.9s)
```

Final counts matched the first run's shape (348 profiled, 114 needs_review, 5 quarantined, 3 extracted,
2 needs_ocr; 351 candidates; 0 failed). After the closing reset, the shared storage volume held **0 files** —
the reset now removes uploaded CV bytes from disk, not just the database rows. (482 orphaned files from
pre-fix runs were cleaned manually once, with the database verified empty first.)

## Full suites after the fixes

- Backend: `python -m pytest -q` — 187 passed (includes the new desk-scoping and permanent-error tests).
- Frontend: `npx vitest run` — 127 passed (19 files); `npx tsc --noEmit` — clean.
- Note: between the start and end of this validation, files from outside this session appeared in the working tree
  (OneDrive sync from another session/machine): `backend/app/services/page_preview.py`, `backend/tests/test_page_preview.py`,
  `backend/tests/test_score.py`, and modifications to `backend/app/api/compare.py` and `backend/app/domain/matching.py`
  (a page-preview endpoint and a points-based scoring model). The 185-pass count includes their tests; they are not part
  of the demo-data or request-workflow work and were not reviewed here.

## Stack state

- cadence-hr-hub Compose stack left RUNNING (web :3000, api :8000, worker, postgres :15432, mailpit :8025) with an empty database (post-reset).
- cadence-hackathon stack remains stopped (volumes untouched, corpus preserved). Restart it with `docker compose start` in `cadence-hackathon` when needed; stop hr-hub first if ports clash.
- Nothing was committed or pushed.

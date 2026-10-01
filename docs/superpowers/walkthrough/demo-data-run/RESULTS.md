# Demo data: batch intake, reset and re-ingestion, measured

2026-09-30, `cadence-hr-hub` stack, driven through the real UI (`/demo`) with Playwright. Raw log: `evidence.json`.
Corpus: `cvs/`, 488 files, 71 MB. One worker container, four uploads at a time from the browser.

## Timing (one run)

| Step | Measured |
|---|---|
| Upload of all 488 files finished | 12.7 s |
| Empty database to ingestion complete (worker has nothing left) | **134.4 s (2 min 14 s)**. The page's own clock said 2 min 15 s |
| Same 488 files sent again | 13 s, nothing created |

This is one run on this machine. Another session was sharing the disk and the Postgres server at times, so treat it as roughly 2 to 2.5 minutes, not as a benchmark. It is not instant, and it is not seconds.

## Resulting counts (from `GET /demo/status`, the live tables)

| | |
|---|---|
| Files selected / uploaded | 488 / 488, 0 upload failures |
| New documents / already on record | 472 / 16 (byte-identical files inside the corpus) |
| Documents on record | 472 (348 profiled, 3 extracted, 114 needs review, 5 quarantined, 2 needs OCR) |
| Processing failed | 0 |
| Candidate profiles | 351 |
| Relationship reviews pending | 114 |
| How CVs were matched | 351 new candidate, 61 updated CV, 39 different candidate, 10 duplicate, 4 needs a choice |
| Extraction jobs | 472: 467 succeeded, 5 quarantined |
| Hiring requests, matches, shortlists, shares | 0 |

A previous load of the same corpus by another session gave 113 pending reviews and 62 updated CVs, so identity outcomes shift by a document or two between runs.
Documents are read in the order they arrive, and four uploads race. The counts of documents and candidates were the same.

## Reset

- The UI needs `RESET` typed exactly. The confirm button stayed disabled for an empty box and for `reset`.
- After reset: 0 documents, candidates, requests, jobs, matches, shortlists, shares. Users (2) and audit events (2312) were kept, and one `demo_reset` audit event was written by the recruiter.
- `/candidates` then shows "No confirmed profiles yet".
- The same corpus loaded again straight after the reset and produced the counts above.

## Idempotency

Sending the same 488 files again: documents, jobs and candidates were 472, 472 and 351 before and after. The page reported "new 0, already on record 488". Concurrent uploads of identical bytes are serialised by a per-digest lock, and a backend test covers six simultaneous uploads producing one document and one job.

## Defects found by this run and fixed

1. **Reset failed on real data.** The reset code that was written alongside mine deleted `hiring_requests` before `agent_runs`, which still pointed at it, and tried to `UPDATE audit_events`, which the append-only trigger forbids. Its tests used data with no agent runs, so they passed. Reset now detaches `agent_runs` from the rows being removed and keeps them, and never touches audit. A regression test uses an agent run linked to a candidate, document, job and request, with an audit row pointing at it.
2. **Confirm dialogs sat in the top-left corner.** The base `dialog` style had no `margin: auto`, so the reset dialog (and the share approval dialogs) were not centred. One line added in `globals.css`.

## Tests

- Backend `pytest`: 172 passed. Run with `HUB_TEST_DB=hub_test_demo` so it could not collide with other sessions using `hub_test`.
- Frontend `vitest`: 17 files, 112 passed. `tsc --noEmit`: clean.

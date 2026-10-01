# Request workflow, live run against the `cadence-hr-hub` stack

Run on 2026-09-30, request `2bfdabfe-f1c3-488d-b88c-72cdfac9faf8` (Acme Corp, Senior Backend Engineer, requested 5).
Stack: `docker compose -p cadence-hr-hub up --build -d` from `cadence-hr-hub`, empty database, current code.
Driver: `request-flow.mjs` (Playwright, real UI) plus SQL and HTTP checks below. The `cadence-hackathon` containers and volumes were not touched.

Another session used the same stack at the same time (requests 3ecd9ef4, b0ca9407 and two Northwind Traders "Platform Engineer"
requests, each with 5 shortlisted). Every number below is filtered to request `2bfdabfe`. Table-wide counts are not evidence.

## Seed

`scripts/seed_request_demo.py 30` uploads the first 30 CVs by filename from `cvs/` through `POST /documents`.
Result: 22 profiled, 7 needs_review (duplicate/update reviews), 1 duplicate file. 31 confirmed candidates.
JD: `Required skills: Python, SQL` and `Preferred skills: Docker`. No location data was added; the API returns `location: null`.

## Screenshots (this folder)

| Step | File |
|---|---|
| Request submission | `01-request-submission.png` |
| Processing state (worker held, job queued) | `02-processing-state.png`, `02b-processing-matching.png` |
| Matching complete | `03-matching-complete.png` |
| Candidate pool | `04-candidate-pool.png` |
| HR shortlist | `05-hr-shortlist.png`, `05-hr-shortlist-viewport.png` |
| Share approval | `06-share-approval.png` (full page, overlay drawn mid-page), `06-share-approval-viewport.png` |

## Checks

| Check | Result |
|---|---|
| Double-click on "Log request" | 1 request created (the form ignores the second click) |
| `process_request` jobs for the request | exactly 1 (`queued` while the worker was held, then `succeeded`, attempts 1) |
| Stages seen | received, matching, complete |
| Matching result | 23 matched / requested 5. Pool holds 31 rows: 2 recommended, 21 needs_review, 8 excluded |
| Matching stops before any decision | audit for the request: `user hiring_request_created`, `system requirements_extracted`, `system matching_run`, `user pool_opened`. First shortlist row at 10:55:02.801, after `last_match_completed_at` 10:54:54.863. `sharing_records` for the request: 0 |
| HR shortlist | 3 selected in the UI, 3 `shortlist_candidates` rows, audit `user shortlist_decision`. Counter reads "Shortlisted: 3 of 31" |
| "Review share…" only on shortlisted rows | 3 buttons for 3 shortlisted |
| Share approval | Send disabled until Approve; after Approve, Send enabled. 1 `approval_decisions` row, audit `user share_approved`. Nothing was sent (0 `sharing_records`) |
| System actor is refused | in-process on the live DB, rolled back: `shortlist_match(SYSTEM)` and `approve_share(SYSTEM)` both refused with `human_required` |
| Engineer token is refused | `POST shortlist`, `share/approve`, `share`, `matches` all return 403. Shortlist count stayed 3 |

## Observations

- "23 candidates matched" (recommended + needs_review) sits next to "Shortlisted: 3 of 31" (all 31 rows, including 8 excluded). Two different denominators on one page.
- Skill extraction keeps fragments such as `backtesting)` and `Technical: Python`, and the share panel shows "Latest title: Not recorded, Experience: Not recorded" because no CV in the set yielded them. These are deterministic-extractor limits, not seed problems.
- 21 of 23 matches are needs_review because the JD skills appear in CV text but not as extracted skills (verdict `partial`).

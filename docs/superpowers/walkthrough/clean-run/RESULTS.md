# Request workflow, clean-volume run

Request `2e9fd3a2-9bb3-48de-ad6a-93f98c78d801` (Acme Corp, Senior Backend Engineer, requested 5), 2026-09-30.
Stack: `cadence-hr-hub` compose project. Only `cadence-hr-hub_pgdata` was recreated. `cadence-hackathon_*` volumes and `cadence-hr-hub_storage` were untouched.
Driver: `request-flow.mjs` (Playwright, real UI) with hard assertions. It aborts if the database is not clean at the start.
This run supersedes `../run-2bfdabfe/`, which shared the stack with another session.

## Caveat: the live database changed after this run

The counts and screenshots below were captured and asserted during the run (11:08 to 11:09 UTC); `evidence.json` holds the raw log.
At about 11:10 UTC something else recreated the `hub` database and ran its own flow (request `b55eb683`, 5 shortlisted, 1 approval).
Request `2e9fd3a2` no longer exists in the live database, so it cannot be re-queried now. The database is not in this run's final state.

## Start state, asserted

Counts are `requests | process_request jobs | shortlists | shortlisted candidates | approvals | sharing records`.

| Moment | Counts |
|---|---|
| After the volume reset and the 30-CV seed | `0 | 0 | 0 | 0 | 0 | 0` |
| After one double-click on "Log request" | `1 | 1 | 0 | 0 | 0 | 0` |
| After the worker finished extraction and matching | `1 | 1 | 0 | 0 | 0 | 0` |
| After HR shortlisted 3 candidates | `1 | 1 | 1 | 3 | 0 | 0` |
| After HR approved 1 share (nothing sent) | `1 | 1 | 1 | 3 | 1 | 0` |

Seed: `scripts/seed_request_demo.py 30` gave 22 profiled and 7 in duplicate review, so 22 confirmed candidates. No location data was added.
JD: `Required skills: Python, SQL`, `Preferred skills: Docker`.

## Findings

- **Double-click:** exactly 1 request and 1 `process_request` job (`queued`, attempts 0 while the worker was held, then `succeeded`, 1 attempt).
- **Worker boundary:** stages received, matching, complete. The worker left shortlists, shortlisted candidates, approvals and sharing records at 0. Audit for the request: `system requirements_extracted`, `system matching_run`, `user hiring_request_created`, `user pool_opened`. The only other system decision rows are 2 `candidate_recommended`.
- **Pool:** "16 candidates matched, requested 5". 22 candidates were compared: 2 recommended, 14 needs_review, 6 excluded. The page lists the 16 and says "6 excluded by an unmet mandatory requirement, not shown". The counter reads "Shortlisted: 3 of 16".
- **HR shortlist:** 3 selected in the UI, 3 rows, audit `user shortlist_decision` ×3. "Review share…" appears on exactly 3 rows.
- **Share approval:** Send is disabled until Approve. After explicit approval it is enabled. 1 approval, audit `user share_approved`. No email was sent.
- **Full audit for the run:** system actions are document extraction, duplicate reviews, job events, `requirements_extracted`, `matching_run` and 2 `candidate_recommended`. User actions are `hiring_request_created`, `pool_opened`, `shortlist_decision` ×3 and `share_approved`.

## Screenshots

`01-request-submission.png`, `02-processing-state.png` (worker held, job queued), `02b-processing-matching.png` if the state was caught, `03-matching-complete.png`, `04-candidate-pool.png`, `05-hr-shortlist.png`, `06-share-approval.png`.

## Automated checks, run afterwards

- Backend: `pytest -q` gave 155 passed. A first run right after the walkthrough showed 7 failed and 5 errors (`uq_users_email`). Other pytest processes were running against the shared `hub_test` database. After they exited, the rerun passed with no code change.
- Frontend: `tsc --noEmit` exit 0. `vitest run` gave 14 files and 93 passed.

## Observations, not defects

- 16 matched, not the 23 of the earlier run. The earlier run's database also held CVs ingested by the other session. With only these 30 CVs the pool is 16 against 5 requested. About 10 more CVs from `cvs/` would raise it.
- One candidate's display name is "University of California, Berkeley". The CV's first line was parsed as the name. It is what the extractor produced, and I didn't alter it.
- 21 of the earlier 23 matches were needs_review, and 14 of 16 are here, because Python and SQL appear in CV text but not always as extracted skills.

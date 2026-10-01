# Cadence HR Intelligence Hub — final verification

2026-09-30, `cadence-hr-hub` on `main` at `fbe94b3` plus the uncommitted working tree. Stack: `docker compose -p cadence-hr-hub` from wiped volumes; the optional `docker-compose.ollama.yml` for the LLM checks. Nothing committed or pushed.

## Verdict

**NOT FULLY VERIFIED — BLOCKERS REMAIN**

## Blockers

1. **Requirements are matched before HR approves them.** The worker extracts requirements and immediately matches every candidate on `proposed` rows (verified: 351 candidates scored on unapproved rows). `SUBMISSION.md` says the opposite in six places (§3 3.1 and 5.3, §5 table, §6 agents, §8 AI inventory).
2. **Protected traits are filtered by a keyword list only.** `validate_proposal` accepts "Muslim", "Christian", "Saudi", "single" and "aged 25-30" when the sentence has no injection phrase. Live, the real model stored `25 (experience)` quoting "Candidates must be single and aged 25-30", and it was used for matching before approval.
3. **A job description whose proposals are all rejected fails the whole request.** The malicious JD produced 0 accepted rows, matching raised `no_requirements`, the job was quarantined, the request shows "processing failed", and the rollback also discards the record of what the model proposed.
4. **`SUBMISSION.md` is stale or wrong on points a judge will test**: 126 tests (now 213 + 1 skipped); "a language model is not one of the running components" (the Ollama reader exists); approval-before-matching claims; corpus baseline counts from a different configuration (364 profiles / 97 reviews / 6 OCR vs 351 / 114 / 2 today); profile "experience, years" marked PASS while the real corpus yields none.
5. **No experience is extracted from the real corpus.** The parser accepts only `YYYY-MM-DD to YYYY-MM-DD`; 348 CVs have an Experience section, 0 experience rows and 0 years were stored. Experience requirements are always `unknown`, `min_years` and employer search find only synthetic CVs.

## Fixed during this run (minimal, with regression test)

- **Demo reset returned 500 on any database with a shortlist.** It deleted `candidate_matches` before the `shortlist_candidates` that reference them. `services/demo.py` now deletes in the schema's foreign-key order; new test `test_reset_works_after_a_full_request_flow_with_shortlist_approval_and_share` failed before and passes after. Live reset on a full database then took 3.9 s and removed 490 stored files.

## Incident caused by the verification

- A `TRUNCATE audit_events` probe succeeded and emptied the live audit trail of this run's events (only this run's; the volume had been wiped at the start). The append-only trigger covers UPDATE and DELETE, not TRUNCATE, and the app connects as the table owner.

## Matrix

| # | Area | Result | Evidence | Notes |
|---|---|---|---|---|
| 1 | Build | PASS | `compose up --build` exit 0, 27 s (cached layers) | not a `--no-cache` build |
| 2 | Migrations | PASS | head `a9d3c5e17b42`, 2 users provisioned | |
| 3 | Backend tests | PASS | 213 passed, 1 skipped (opt-in live test), isolated `hub_test_verify` | after the reset fix |
| 4 | Frontend tests | PASS | 21 files, 138 passed | |
| 5 | TypeScript | PASS | `tsc --noEmit` exit 0 | |
| 6 | Authentication | PASS | 52 routes: no token → 401, bad token → 401; `/health`, `/docs`, `/openapi.json` public; dev tokens refused outside local | |
| 7 | RBAC | PARTIAL | engineer 403 on 45 routes, reaches only health, document list (no filenames/PII), activity, problem reports | engineer can `POST /documents` (upload a CV) |
| 8 | Audit | PARTIAL | UPDATE/DELETE refused; no contacts, CV text or model output in 294 events / 492 agent runs | TRUNCATE not blocked |
| 9 | CV ingestion | PASS | 488 files, 0 failures, 0 stuck jobs, 73.2 s and 75.2 s | |
| 10 | Extraction | PARTIAL | 16,604 evidence quotes all on their cited page | 0 experience/years; education rows noisy (median 12 per candidate) |
| 11 | Classification | PASS | encrypted, corrupt, invoice, cover letter, job description quarantined; 0 candidates from them | |
| 12 | Duplicate/update | PASS | identical bytes reused (16); same-name-only → review; all three decisions via UI with correct backend state | old walkthrough labels stale |
| 13 | Merge | PASS | recruiter only, confirm required, docs/contacts/applications moved, absorbed points to survivor, audited, re-merge 409; system/agent refused | |
| 14 | CV comparison | PASS | real PDF page rendered, `cv_preview_viewed` with ids only | Word notice unit-tested only |
| 15 | Search | PARTIAL | name, skill, text, filters, certificate, evidence on every hit, 0 hits on unconfirmed docs | title/years/employer only hit synthetic CVs; vectors are local hash, not semantic |
| 16 | Hiring request | PASS | ack 112 ms, 1 request + 1 job on double-click, no shortlist/share by system | |
| 17 | Real LLM | PARTIAL | `ollama:qwen2.5:3b-instruct`, quotes verbatim, agent run recorded | missed SQL; followed an injection (validators caught it) |
| 18 | LLM fallback | PASS | model stopped → deterministic reader, run `fallback/llm_unavailable`, UI says AI was unavailable | |
| 19 | Requirement approval | FAIL | approval works, but matching already ran on proposed rows | blocker 1 |
| 20 | Matching | PASS | verdicts on every row; excluded ⇒ unmet mandatory | runs before approval |
| 21 | Scoring | PASS | 351/351 recomputed exactly | one-kind requests give that kind 100, not 70/30 |
| 22 | Shortlist | PASS | 5 via UI, system/agent/engineer refused | |
| 23 | Sharing | PASS | Send disabled until approval; non-shortlisted 409 | |
| 24 | Mailpit | PASS | 1 message to `company@localhost`, no contact details | |
| 25 | Sourced candidates | PASS | profile created, same person → review, source kept, engineer 403 | |
| 26 | Excel | PASS | 10 rows kept, malformed/missing/duplicate/untrusted flagged, formulas not evaluated, no auto-merge, engineer 403 | |
| 27 | Export | PASS | allowed columns only, no email/phone, audited, engineer 403 | |
| 28 | Problem reports | PASS | unsafe context/prose 422, engineer workflow, recruiter can't resolve, audited | |
| 29 | Dashboard | PASS | counts equal database; every tile opens the right queue | |
| 30 | Work queue | PASS | Open navigates, pending count unchanged | |
| 31 | Candidate profile | PARTIAL | sections render, engineer 403 | experience empty; console 404 per document without a review |
| 32 | Global search | PASS | `/`, groups, Escape, Enter, no-result state | |
| 33 | Mobile | PASS | 14 routes at 390/820/1440: no overflow | |
| 34 | Failure recovery | PASS | worker killed mid-job → reclaimed, succeeded on attempt 2, still 1 job | |
| 35 | Demo reset | PASS (after fix) | 3.9 s, rows and files removed, users and audit kept, reload identical | failed before the fix |
| 36 | Security | FAIL | protected-trait filter | blocker 2 |
| 37 | Privacy | PARTIAL | no secrets; 0 real contact values in 321 repo files | `cvs/` (488 real CVs) is tracked in git by your choice; some screenshots show real names |
| 38 | Backup/retention | PARTIAL | local backup + 730-day retention tested (unit) | not run live; no production backup |
| 39 | Submission consistency | FAIL | see blocker 4 | |
| 40 | Final walkthrough | PARTIAL | every step run live in pieces | not as one uninterrupted judge session |

## Timings (measured)

Stack up (cached build) 27 s · corpus upload 12.4 s · corpus to ingestion complete 73.2 s / 75.2 s · re-upload of same files 10 s · request acknowledgement 112 ms · request to pool with the LLM 83 s · warm LLM call 9–14 s · fallback request to pool 12 s · re-match after approval 5.2 s · reset (full DB) 3.9 s · worker-kill recovery 74 s.

## Evidence

`corpus/`, `corpus-reload/`, `hiring/`, `llm-edges/`, `ui/`, `workflows.json` in this folder. Scripts in the session scratchpad (`corpus-final.mjs`, `final-hiring.mjs`, `final-llm-edges.mjs`, `final-ui.mjs`, `final_workflows.py`, `rbac.py`, `dec-new.mjs`).

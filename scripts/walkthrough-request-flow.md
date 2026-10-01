# Request workflow walkthrough

Recorded 2026-09-30 against the `cadence-hr-hub` Compose stack (web :3000, api :8000, worker, Postgres, Mailpit).
Driver: `scripts/walkthrough_request_flow.py` (Chrome via Playwright). Screenshots: `docs/superpowers/walkthrough/`.
Nothing was committed or pushed.

## Setup

- The five running `cadence-hackathon` containers were stopped with `docker stop`. Nothing was removed.
- `docker compose up -d --build` from `cadence-hr-hub`. Fresh volumes, fresh database.
- Seed: `python scripts/seed_demo.py --count 40` uploads the first 40 PDF/DOCX files (sorted by name) from `cvs/` through
  the API. Result: 32 profiled candidates, 8 CVs waiting on duplicate/update review. Every candidate is a real file.
- Demo request: "Required education: University / Preferred skills: Python", 5 requested.
  Real skills in the corpus are sparse (at most 2 candidates share any skill), so a mandatory skill gave a pool of about 2.
  A mandatory education requirement gave a pool of 29 real candidates. No number was invented.

## Result (final run, fresh seed)

| Step | Observed |
|---|---|
| Submit | Form logs the request; status `submitted`, stage `received` at first paint |
| Processing | Worker ran extraction then matching; request status `open`; stage `complete` |
| Pool size | **29 candidates matched · Requested: 5**; pool list shows 29 results |
| Boundary | `shortlists=0`, `sharing_records=0` after processing; actor kind on `matching_run` and `requirements_extracted` is `system` |
| Requirements | All stay `proposed` (unreviewed) |
| Command Center | "New candidate matches" 0 before, **1** while the pool was unopened |
| Pool opened | `pool_opened_at` set once; reload did not move it; exactly 1 `pool_opened` audit event |
| Filters | Match status "Needs review": 1 result. Location filter absent, as no match carries a location |
| Selection | 20 checkboxes visible, 0 checked before any click |
| Shortlist | Selected 5; `Shortlisted: 5 of 29`; 5 "Review share…" buttons; 0 shares sent |
| Share approval | Send disabled until Approve; approved as a separate confirmed step; still 0 sent |
| Send | Confirmed separately; 1 `sharing_records` row; 1 message in Mailpit |
| Audit | Shortlist, approval and share events all have actor kind `user` |
| Console | 0 errors |

## Defects the walkthrough found

1. Fixed: the pool listed 31 results (including 2 candidates excluded for an unmet mandatory requirement) while the card said 29.
   The pool now shows only recommended and needs-review candidates and says how many were excluded.
2. Fixed: "Shortlisted: 0 of 0" flashed before matches loaded. It now shows a loading line.

## Open findings (not fixed)

- The Skill filter matches the requirements a candidate met (`strengths`), not the candidate's skills, so
  searching a real skill such as "sql" returned 0 results. The match payload needs the candidate's skills.
- "Reviews needing attention" (166 in an earlier run, the Review Queue badge too) counts one item per matched
  candidate plus one per proposed requirement. With a broad pool this swamps the queue.
- The 7-step stepper wraps to a second row at 1440 px, leaving "Shared" alone.
- The pool is acknowledged silently when a completed request loads. If that call fails, the tile stays lit and the next load
  retries. No error state is shown.
- Something other than this work reset the database once during the session, and other files already sat in
  the walkthrough folder. The final run was on a freshly re-seeded database.

## Checks after the last change

- `python -m pytest -q` in `backend`: 155 passed.
- `npx tsc --noEmit` in `web`: exit 0.
- `npx vitest run` in `web`: 14 files, 93 passed.

## Final clean evidence run

Evidence: `docs/superpowers/walkthrough-final/` (11 screenshots, `walkthrough-log.txt`, `final.diff`).
Run with `python scripts/walkthrough_request_flow.py --final` after `docker compose down -v` and `up -d --build` on the
`cadence-hr-hub` project only, then `python scripts/seed_demo.py --count 40`. Zero state was verified first (0 requests,
candidates, shortlists, shares, jobs, 0 Mailpit messages). The run stops at approved-but-not-sent.

Verified from the database and API: 1 request; 1 `process_request` job; 29 matched / 5 requested; 0 shortlist and 0 share rows
after worker processing; the system actor performed no shortlist, approval, share or rejection; 5 `shortlist_decision` events, all
`user`; 1 `share_approved` event, `user`; `sharing_records=0` and 0 Mailpit messages after approval; location filter absent.
The system actor's actions include `document_extracted` and `duplicate_review_opened`. Those come from the CV seed (worker
intake), not from the request.

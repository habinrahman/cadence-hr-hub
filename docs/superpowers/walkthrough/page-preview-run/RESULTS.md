# CV page preview, live check with real PDFs

2026-09-30, `cadence-hr-hub` stack rebuilt with the new code. Spec: `docs/superpowers/specs/2026-09-30-cv-page-preview-design.md`. Plan: `docs/superpowers/plans/2026-09-30-cv-page-preview.md`.
Two real PDFs per person (an older and a newer CV) went through the actual upload, worker and duplicate-review pipeline. The pipeline itself opened the review: "likely an updated CV", confidence 79.29. Raw log: `evidence.json`.

## What was verified in the browser

| Check | Result |
|---|---|
| Preview requests before "Open page view" is pressed | 0 (desktop and phone) |
| Both CVs shown as real pages | 900 x 1274 PNG per page, `image/png`, 200 |
| Marks on the pages | Previous CV: 1 mark. New CV: 4 marks (the "Revised" line, the Google role, its dates line, the added skill) |
| Evidence link ("Show in the new CV") | One more request, with the quote `Google, Senior Engineer`, and a blue outline on that line |
| Page navigation | "Page 1 of 1", Previous and Next disabled for a one-page CV. Multi-page movement is covered by the component tests |
| Phone (390 px) | One CV at a time via the existing toggle, page fits the screen, no horizontal overflow |
| Desktop | No horizontal overflow |
| Existing comparison walkthrough | 21 of 21 |

Screenshots: `desktop-01-before-opening.png`, `desktop-02-both-pages.png`, `desktop-02b-both-pages-full.png`, `desktop-03-evidence-outlined.png`, and the `phone-` equivalents.

## Audit verification (database)

- `cv_preview_viewed` rows: 8 in total across two live runs of the check (each run: previous CV, new CV, then the evidence re-render of the new CV, on desktop and again on phone).
- Every row is `actor_kind = user`, `entity_type = candidate_document`. The `detail` keys are exactly `document_id` and `review_id`.
- The rows point at 4 documents, and those are the older and newer CV of the two seeded pairs. No other document was previewed.
- The quote, and any text such as "Google", "Engineer" or "@", appears in none of them.
- Nothing is written when a request is refused or a page is out of range (backend tests).

## Tests

- Backend `pytest`: 185 passed (13 new in `test_page_preview.py`).
- Frontend `vitest`: 19 files, 127 passed (9 new component tests, 6 new unit tests). `tsc --noEmit`: clean.

## Existing behaviour I changed on purpose

- A PDF now opens on Page view, with Text one click away. Two existing tests and the old comparison walkthrough assumed the text view, so they now select Text first.
- The evidence link read "Show in the new CV text". It now reads "Show in the new CV", because it drives the page image as well.

## Limits, stated plainly

- Marks are best effort. A line that wraps across text runs may not be located on the page, and the panel says so.
- On a 1440 px screen each side is about 330 px wide, because the decision panel takes the right third. The page is drawn at 900 px, so the pixels are there, but small print is hard to read at that size. There is no zoom or enlarge control, because the spec puts it out of scope.
- Word documents show "Visual preview unavailable for Word document. Text comparison is available below." Only backend and component tests cover that path. No Word file was used in the live run.
- Nothing is cached: each page view renders again.

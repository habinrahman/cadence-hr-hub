# CV comparison workspace

A recruiter opens a relationship review at `/compare?document=<id>` (or `?review=<id>`) and sees both CVs, why Cadence
thinks they are related, what differs, and the source text, then decides. Cadence recommends; the recruiter decides.

Entry points: the Inbox's "Review and decide" on a CV relationship, and "Compare the two CVs" on a file in Intake.

## What it adds

Two read-only, recruiter-only endpoints. Neither decides, stores or changes anything.

| Endpoint | Purpose | Audit |
|---|---|---|
| `GET /reviews/{id}/comparison?candidate_id=` | The two documents, structured differences with source quotes, dates, and a line-level text comparison | `review_comparison_viewed` (review id and a count only) |
| `GET /documents/{id}/pages` | Page-by-page text for the viewer, fetched only when the recruiter opens it | `pii_text_access` (count only) |

Decisions still use `POST /reviews/{id}/decision`. A second decision on the same review returns 409, and the page
reports "already decided" and refreshes.

## Rules the comparison follows

- A section the reader found nothing in is **not compared**. It is never shown as removed, and the word does not appear.
- Items are labelled added, changed or not found only when **both** CVs produced items for that section.
- Every item carries the quote and page it came from. An item whose quote is not in the page text is dropped.
- Filenames are never evidence. Dates come from the text; the upload date is shown separately and labelled as such.
- Conflicting date evidence (labelled version date and latest mentioned date pointing at different CVs) is flagged.
- The score is a **same-person confidence** shown under the signals it is built from, never as a model's confidence.
  Each agreeing signal removes a share of the remaining doubt (exact email 90%, exact phone 80%, name up to 50%,
  content overlap up to 30%). A signal not available on both CVs is left out and lowers nothing; a different email
  (keeps 50%) or phone (keeps 60%) is a contradiction and blocks a recommendation. Dates and content choose updated
  against duplicate; they never lower the score. One action is recommended only at 98 or above.

What each decision does (from the backend, and stated in the confirmation dialog):

- **Accept as updated CV**: the incoming CV becomes current; the previous one stays in history.
- **Record as duplicate**: the incoming CV is linked but does not become current.
- **It's a different person**: a new candidate is created; the existing one is unchanged.

## Limits and existing behaviour worth knowing

- The incoming CV's experience, education and skills are **not stored while a review is pending**. The comparison
  re-reads each CV's stored pages with the existing deterministic section parser. That parser only recognises labelled
  headings and ISO date ranges (`2023-01-01 to present`), so on ordinary CVs many sections will show "not compared".
- There is no endpoint that serves the original file, so the viewer shows extracted text page by page, not the PDF.
- **The phone finder treats date-shaped digits (`2023-01-01`) as phone numbers.** This is in the existing pipeline and
  was not changed. Two different people who share such a date can be matched as "same phone" and get a relationship
  review. The comparison ignores date-shaped values when listing phone numbers, and when the stored phone signal says
  "matched" but the CVs share no phone number, the page says so instead of claiming the same number.
- Accepting an update makes the new file current, but the existing backend does not apply the new CV's experience or
  skills to the profile.

## Tests

- Backend: `backend/tests/test_review_compare.py` (15 tests: evidence, missing sections, dates and conflicts, roles,
  audit, read-only behaviour, decided and merged states, spreadsheet reviews, pages).
- Web: `web/lib/__tests__/compare.test.ts` and `web/app/compare/__tests__/compare-view.test.tsx` (jsdom component tests
  covering the recommendation/decision split, confirmation, double click, conflicts, network failure, keyboard, small
  screens).

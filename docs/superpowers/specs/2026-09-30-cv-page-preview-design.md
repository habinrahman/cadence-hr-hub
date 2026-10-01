# CV page preview for the comparison workspace — design

Date: 2026-09-30
Status: awaiting review. Not committed (standing instruction: do not commit or push).

## Purpose

During a duplicate/update review, HR should see the two actual CVs next to each other, page by page, with what differs marked on the real page, and then decide. Today the comparison workspace (`/compare`) shows extracted text page by page, text lines marked as "only here", field differences with evidence links, and the decision panel. It cannot show the real page.

The feature is only this: compare two candidate documents during a review. It is not a general document viewer.

## Decisions (locked in conversation)

- Render stored **PDF** pages server-side and show them side by side. Return **page images**, never the original file.
- No generic `/files/{id}` endpoint. One authenticated, recruiter-only, audited preview endpoint tied to a review.
- **PDF only** in the first version. A Word document shows: "Visual preview unavailable for Word document. Text comparison is available below." Nothing is converted or faked.
- Highlights come from what the comparison already knows (text only in this CV, and the evidence quote the user selected). No new matching logic.
- The locked visual language is unchanged.

## Backend

### `GET /reviews/{review_id}/documents/{document_id}/pages/{number}/preview`

Query: `candidate_id` (optional, same meaning as on the comparison route), `focus` (optional evidence quote, at most 300 characters), `width` (optional, clamped to 600–1400, default 900).

Rules:

- Recruiter role and the existing PII gate, as for `/reviews/{id}/comparison`.
- `document_id` must be one of the two documents of that review: the incoming document, or the existing document resolved with the same rule the comparison uses. Anything else is 404, so the route cannot be used to read arbitrary CVs.
- Media type must be `application/pdf`. Otherwise 415 with `preview_unavailable`. A file that cannot be opened or rendered is 422 `preview_failed`. `number` outside `1..page_count` is 404.
- The original bytes are read through the existing storage adapter, rendered with the PDF library the pipeline already uses, and returned as `image/png`.
- Response headers: `X-Preview-Pages` (page count), `X-Preview-Highlights` (boxes drawn on this page), `Cache-Control: no-store`.

Highlighting, drawn into the PNG so the browser needs no coordinate maths:

- Amber translucent boxes over lines that the comparison's text diff marks as only in this document, located on the page with the PDF library's text search.
- A blue outline around the `focus` quote, when given and found on the page.
- Best effort: a line split across text runs may not be found. The UI says so and never claims every difference is marked.

Audit: one `cv_preview_viewed` event per page rendered, entity `candidate_document`, detail limited to the allowlist (`review_id`, `document_id`). The `focus` quote is never stored, and no page text is logged.

Nothing is cached in the first version. No new tables, no migration.

## Frontend

- In the existing viewer panel for each side, add a **Page view** tab beside the text tab. For a PDF it shows the rendered page with previous/next and "Page n of N".
- Images are fetched with the session's Authorization header and shown from a blob URL, because an `<img src>` cannot send headers. Blob URLs are revoked on change.
- Evidence links already set the page and a focus quote for the text tab. They also drive the page image and its blue outline.
- Word documents show the hatched notice above instead of a page image. A PDF with no text layer still renders, with no highlights and a plain note.
- Loading, error (with retry) and "no preview on file" states follow the existing viewer.
- Opening a page image is recorded in the audit trail, and the panel says so, as the text tab already does.

## Error handling

- 401/403 use the existing session and permission states.
- 415 shows the Word notice. 422 shows "This page could not be drawn" with a retry and a pointer to the text tab.
- A missing document or page is a quiet not-available message, never an exception.

## Testing

Backend (pytest, private test database):

- Recruiter gets a PNG (valid signature) for a real generated PDF. Engineer gets 403, no token 401.
- A document that is not part of the review is 404. A page outside the range is 404. A DOCX is 415. A corrupt PDF is 422.
- The highlight count is greater than zero when the incoming CV contains a line the previous one lacks, and zero when the two CVs are identical.
- One `cv_preview_viewed` row per render, with no quote or text in its detail. The `focus` value is not stored anywhere.
- Width and quote length limits are enforced.

Frontend (vitest):

- PDF side requests the preview and shows the image. Word side shows the notice and makes no request.
- Next/previous move the page. An evidence link sets the page and sends the focus quote.
- Error and retry states. Blob URLs are revoked.

Live check: reseed a review pair with real PDFs, open the comparison, capture desktop and phone screenshots, confirm the audit rows, and rerun the existing comparison walkthrough.

## Out of scope

Downloading originals, a general document viewer, Word-to-PDF conversion, OCR overlays, zoom and pan, caching, changing any review rule or decision behaviour.

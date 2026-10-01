# CV Page Preview Implementation Plan

> For agentic workers: implement task by task. Steps use checkbox syntax. Do not commit or push (standing instruction).

**Goal:** In a duplicate/update review, show the two real PDF CVs side by side as server-rendered page images, with the lines that differ marked on the page, without adding any general file access.

**Architecture:** One new read-only route on the existing compare router returns a PNG of one page of one of the review's two documents. Membership in the review is decided with the comparison's own `_existing_document` rule. Highlights reuse the comparison's `_lines` diff for the requested side. The web viewer gets a Page view tab per side that fetches the image with the session token.

**Tech Stack:** FastAPI, SQLAlchemy, pymupdf (already a dependency), Next.js client components, vitest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-30-cv-page-preview-design.md`. No scope beyond it.
- Do not change `build_comparison`, its diff logic, or any review decision code. New code only calls the existing private helpers.
- Recruiter role plus the existing PII gate. Return PNG images only, never the original file. No generic file route.
- PDF only. Word documents get a 415 and a plain notice in the UI. No conversion.
- Audit: one `cv_preview_viewed` event per render, detail limited to `review_id` and `document_id`. The `focus` quote is never stored or logged.
- Limits: `width` clamped 600 to 1400 (default 900); `focus` at most 300 characters; `Cache-Control: no-store`.
- Locked visual language. No commits, no pushes.

## File Structure

- Modify `backend/app/services/review_compare.py`: add `review_documents()` and `only_here_lines()` (new functions, nothing existing edited).
- Create `backend/app/services/page_preview.py`: render one page to PNG with highlights.
- Modify `backend/app/api/compare.py`: add the preview route.
- Create `backend/tests/test_page_preview.py`.
- Modify `web/lib/api.ts`: `fetchPagePreview()`.
- Create `web/lib/page-preview.ts`: URL builder and notice rules, with `web/lib/__tests__/page-preview.test.ts`.
- Modify `web/components/compare/document-viewer.tsx`: Page view tab.
- Create `web/components/compare/__tests__/page-preview.test.tsx`.

---

### Task 1: Which documents a review may show, and which lines to mark

**Files:** modify `backend/app/services/review_compare.py`

**Interfaces**
- Produces `review_documents(session, review, candidate_id) -> tuple[CandidateDocument | None, CandidateDocument | None]` returning `(existing, incoming)` using the same candidate and existing-document rules as `build_comparison`. Raises `CompareError("not_found")` for a candidate that is not one of the review's.
- Produces `only_here_lines(session, review_documents_pair, which, page) -> list[str]`: the normalised lines on `page` of the `which` side ("existing" or "incoming") that the other CV does not contain, using `_lines`. Empty when either side has no readable text.

- [ ] Add both functions below the existing helpers. Load each side with pages only (no extraction draft): rows from `DocumentPage`, wrapped in `Side`, state checked with `Side.state`.
- [ ] Verified in Task 3 tests.

### Task 2: Render a page

**Files:** create `backend/app/services/page_preview.py`

**Interfaces**
- Produces `render_page(data: bytes, number: int, *, width: int, mark: list[str], focus: str | None) -> PreviewResult(png: bytes, page_count: int, highlights: int)`.
- Raises `PreviewError(code)` with `preview_failed` (cannot open, encrypted, render error) or `page_out_of_range`.

- [ ] Open with `pymupdf.open(stream=data, filetype="pdf")`; refuse if `needs_pass`.
- [ ] For each line in `mark`, `page.search_for(line[:200])`, falling back to the first 60 characters; draw an amber translucent box for every hit.
- [ ] If `focus` is given, `search_for(focus[:300])` (fallback first 60) and draw a blue outline.
- [ ] Render at `zoom = width / page.rect.width`; return PNG bytes and the counts. Close the document in `finally`.

### Task 3: The route and its tests

**Files:** modify `backend/app/api/compare.py`; create `backend/tests/test_page_preview.py`

- [ ] Route `GET /reviews/{review_id}/documents/{document_id}/pages/{number}/preview` with query `candidate_id`, `focus`, `width`. Order of checks: recruiter and PII gate, review exists, `document_id` is one of the pair (else 404), media type is PDF (else 415 `preview_unavailable`), storage read (missing file 404), render (422 `preview_failed`, 404 for a page out of range), audit, commit, return `Response(png, media_type="image/png")` with `X-Preview-Pages`, `X-Preview-Highlights`, `Cache-Control: no-store`.
- [ ] Tests, on a private test database (`HUB_TEST_DB`): recruiter gets a valid PNG for two real generated PDFs of one person; engineer 403; no token 401; a document outside the review 404; page 0 and page beyond the count 404; a DOCX-typed document 415; a corrupt PDF 422; highlight count above zero when the incoming CV has a line the previous lacks and zero for identical text; exactly one `cv_preview_viewed` row per render with `detail == {"review_id", "document_id"}` and no quote text anywhere in the audit table; `width` clamped and over-long `focus` rejected with 422.
- [ ] Run the new tests, then the whole backend suite.

### Task 4: Web client and rules

**Files:** modify `web/lib/api.ts`; create `web/lib/page-preview.ts` and its test

- [ ] `fetchPagePreview(url)` fetches with the session Authorization header and returns `{ blob, pages, highlights }` from the response and headers; a non-OK response throws `ApiError(status, detail)`.
- [ ] `previewUrl({reviewId, documentId, page, candidateId, focus, width})` builds the path with encoded parameters and truncates `focus` to 300 characters.
- [ ] `previewKind(mediaType)` returns `"pdf"` for `application/pdf` and `"unavailable"` otherwise.
- [ ] Tests for URL encoding, truncation, and `previewKind`.

### Task 5: The Page view tab

**Files:** modify `web/components/compare/document-viewer.tsx`; create `web/components/compare/__tests__/page-preview.test.tsx`

- [ ] Give each side's panel a Tabs control: Page view and Text. A PDF defaults to Page view; anything else shows only Text and, in place of Page view, the hatched notice "Visual preview unavailable for Word document. Text comparison is available below." (wording uses "Word document" only for the Word media types, and "this file type" otherwise).
- [ ] Page view loads on a button press ("Open page view"), like the text tab, and says that opening it is recorded in the audit trail. Evidence links open it on the cited page and pass the quote as `focus`.
- [ ] Previous/next and "Page n of N" from `X-Preview-Pages`. Blob URLs are created per page and revoked on change and unmount. Loading, error with retry, 422 and 415 states.
- [ ] Note under the image: "Amber marks lines found only in this CV. Some lines may not be located on the page."
- [ ] Tests: PDF requests and shows an image; a Word side shows the notice and makes no request; next moves the page; an evidence focus passes the quote and page; a failed fetch shows retry; blob URLs revoked.
- [ ] Run vitest and `tsc --noEmit`.

### Task 6: Live check

- [ ] Rebuild the stack. Seed a review pair from two real PDFs of one person (`seed_compare.py`). Open the comparison in the browser, open both page views, select an evidence link, capture desktop and phone screenshots.
- [ ] Verify the audit rows in the database: `cv_preview_viewed` per render, ids only, no quote text.
- [ ] Rerun the existing comparison walkthrough. Report results honestly.

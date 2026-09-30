# Cadence frontend redesign: design

Date: 2026-09-30. Scope: `web/` only. Status: awaiting review.

## 1. Goal and hard constraints

Redesign the Cadence HR Intelligence Hub frontend as one coherent internal operations product. The design starts from the data model, the API contracts and the HR workflows, not from the existing screens.

**Do not change:** anything under `backend/`, the database schema, business logic, matching, authentication and RBAC, audit behaviour, API contracts, or the existing 126 backend tests. The frontend only consumes existing endpoints. Where the API cannot support an idea, the UI shows what is available and says so.

**Principle:** Cadence proposes, HR decides. The UI makes the difference between a *proposal*, a *human decision* and a *stored fact* visible everywhere.

## 2. Product truths the UI must respect

Taken from the code and `SUBMISSION.md`.

1. **No language model runs.** Extraction, relationship scoring, requirement proposal and matching are deterministic. The UI says "Proposed by Cadence". It never says "AI". The relationship number is real (weighted from listed signals), so it is shown as *signal strength* beside those signals, never alone.
2. **A hiring request's stored status is only `draft` → `open`** (it flips to `matching` and back during a run). `pending_approval` and `shared` exist in the state machine but are never set. The lifecycle stepper is therefore **derived** from requirement `review_status`, matches, shortlist and share approval.
3. **The work queue is thin and repetitive.** Each item has only `type, subject, status, created_at, href`. It emits one row per proposed requirement and per match. It is capped at 50; dashboard lists at 20.
4. **PII access is audited.** `GET /candidates/{id}` writes `candidate_viewed`. `GET /documents/{id}/text` writes `pii_text_access`. The UI never prefetches or hover-loads a profile or CV text, and the "Show CV text" control says the view is recorded.
5. **Shortlisting is idempotent** (returns the existing row). Match list payloads do not say who is shortlisted; `GET …/candidates/{id}/share` returns 409 `not_shortlisted` when not.
6. **Roles.** The web app sends the recruiter token baked in at build time. Engineer routes and recruiter routes return 403 to the wrong role. There is no `/me` endpoint, so the UI does not claim to know a user's name or role. `viewer_id` from `/dashboard` and `owner_user_id` on a request allow "owner: you" only.
7. **Audit events expose only** `action, actor_kind, created_at` (plus `detail` on document activity). No person names.

### Not available from the API (the UI must not fake these)

| Wanted | Reality | UI behaviour |
|---|---|---|
| Candidate directory or list | Only search, review links, known ids | No "all candidates" page. Candidates page is search. |
| Edit a candidate | No endpoint | Profile is read-only; one line explains it is built from CVs. |
| Candidate-level match or sharing history | No endpoint | Not shown. |
| Request-level audit log | None (per document / candidate only) | Request record shows notes, updates, next steps, files. |
| Download a request attachment | No endpoint | List filename, type, size only. |
| Person names in audit or notes | Ids and actor kinds only | "You" (via `viewer_id`) or "Another recruiter". |
| Field-lock display | Not in profile payload | Not shown. |
| Real semantic ranking | Vector is a token hash | Reasons labelled Exact vs Approximate; no score bar. |

## 3. Information architecture and navigation

**Top bar, no sidebar.** Four destinations by frequency of use: **Inbox · Requests · Candidates · Intake**. Plus a global find (`/` shortcut, jumps to Candidates with the query), an **Add** menu, and a **Desk** menu.

- **Add:** Upload a CV · Source a candidate · Import an Excel list · New hiring request.
- **Desk:** Problem reports · Hiring-activity export · Merge two profiles.
- Below 768 px: the four destinations become a bottom tab bar; Add stays in the top bar; Desk moves into an overflow sheet.

Why: HR opens Cadence to decide things, work a request, or find someone. Two-pane review screens need horizontal space a sidebar would waste. Only four destinations are used daily, so a bar suffices.

### Routes (existing paths are kept because the backend emits links to them)

| Route | Screen | Notes |
|---|---|---|
| `/` | Inbox | If `?document=` is present, redirect to `/intake?document=…` (backend emits `/?document=`). |
| `/intake` | Intake: files list and detail | Same behaviour as the current `/`. |
| `/hiring` | Requests index; with `?request=` the request workspace; `?candidate=` opens the share panel | Backend emits `/hiring?request=&candidate=`. |
| `/candidates` | Candidate search | Filters stored in the URL. |
| `/candidates/[id]` | Candidate profile | |
| `/search` | Redirect to `/candidates`, params kept | |
| `/queue`, `/dashboard` | Redirect to `/` | Their content is folded into Inbox. |
| `/source`, `/data`, `/merge`, `/reports` | Kept as they are today in path and function | Reached from Add / Desk. Backend emits `/data` and `/reports`. |

## 4. Design system

### Direction: "case file", palette A (Ocean)

Provenance is the primary visual signal.

| Meaning | Treatment |
|---|---|
| **Proposed by Cadence**, waiting for HR | Dashed amber border, tinted amber fill, label "Proposed" |
| **Decided by a person** | Solid decision-blue tag, "Decided", time |
| **Extracted fact with source** | Evidence quote block: steel-blue left bar, monospace source line `CV p.2 ✓ verified`; unverified quotes flagged "quote not verified" |
| **Stored fact** | Plain text, no chrome |
| **Unknown / not extracted** | Hatched grey tag "Unknown" or "Not extracted" (never silently blank) |
| **Verdicts** | Meets = green filled; Not met = red filled; Partial = amber; Unknown = hatched |
| **Object hue** (stripe on rows, top strip of a page) | CV relationship violet · Requirements cyan · Match green · Share rose |

Every decision case uses the same **spine**: Found → Evidence → Proposed → Decision → Record.

### Tokens

Defined as CSS variables in `app/globals.css` and mapped into Tailwind 4 via `@theme`.

| Token | Value | Use |
|---|---|---|
| `--nav` | `#0B3954` | Top bar |
| `--nav-ink` | `#CFE4F0` | Top bar text |
| `--canvas` | `#EEF5F8` | Page background |
| `--panel` | `#FFFFFF` | Panels |
| `--rule` | `#C9DAE3` | Hairlines |
| `--ink` | `#0E2230` | Text |
| `--mut` | `#4A6272` | Secondary text |
| `--human` / `--human-bg` | `#0A6CC2` / `#E1F0FC` | Decisions, primary buttons, current step |
| `--prop` / `--prop-bg` | `#B86E00` / `#FFF0D2` | Proposals (borders and fills) |
| `--ok`, `--bad`, `--ev` | `#1B8A5A`, `#C8412F`, `#4F7591` | Meets, not met, evidence |
| `--t-rel`, `--t-req`, `--t-match`, `--t-share` | `#6C5CE7`, `#00A6C8`, `#2BA57A`, `#E0567A` | Object hues |

**Contrast rule (implementation must verify):** the values above are for borders, fills and stripes. Any hue used as *text* or as a *filled tag with white text* uses a darker `-ink` variant chosen to reach at least 4.5:1 (for example proposal text ≈ `#8F5400`, verdict fills ≈ `#17784F`). A contrast check on every text/background pair is part of the verification step.

**Type:** system UI stack (no web font dependency), base 14 px for dense data, 15–16 px for reading text, scale 12 / 13 / 14 / 16 / 20 / 26. Tabular numerals for counts and dates. Monospace for ids, filenames and source lines. Section labels 12 px uppercase, tracked.

**Space and shape:** 4 px base (4, 8, 12, 16, 24, 32, 48). Radius 3–4 px on controls and panels; no large rounded cards; hairline borders instead of shadows. Touch targets ≥ 44 px on mobile.

### Components

`components/ui/`: Button (primary, secondary, quiet, danger), Field (label, hint, error, `aria-describedby`), TextInput, Select, Textarea, FileDrop, Chip (filter, removable), Tag (proposed, decided, verdict, status), Panel, Table (collapses to stacked rows under 640 px), Tabs, Dialog (native `<dialog>`), ConfirmDialog, SlideOver, Toast and live region, Skeleton, EmptyState, ErrorState (maps 401, 403, 404, 409, 5xx to plain wording), Stepper, Menu.

`components/domain/`: `DecisionCase` (spine layout), `RelationshipReview` (one implementation replacing three copies in intake, source and Excel), `EvidenceQuote`, `SignalList`, `RequirementMatrix`, `ShareReview`, `AuditLine`, `CandidateHeader`, `SourceTag`.

`lib/`: `labels.ts` (single label source), `lifecycle.ts` (derive stepper state), `queue.ts` (group queue rows by request), `evidence.ts` (attach evidence to items), `format.ts`, `useAsync.ts`. `lib/api.ts` stays; changes are **additive only** (new types and functions for endpoints that already exist).

### States (every screen)

- **Loading:** skeleton shaped like the content, `aria-busy`.
- **Empty:** says why it is empty and the next action (for example "Nothing needs a decision. New CVs and requests appear here").
- **Error:** what failed, the server's reason when safe, retry. 401 → "Your session is not accepted. Sign in again." 403 → "This role cannot open this." No raw JSON.
- **Pending / decided:** proposals dashed; decisions solid with time. Approved and rejected states are visible on the item, not only in a toast.
- **Confirm:** irreversible actions (merge, approve share, send, reject) use a confirm dialog naming the object and consequence.

### Accessibility

Visible focus ring (2 px, offset), full keyboard operation, native `<dialog>` focus trap, `aria-live` for save/decision results, status conveyed by text and shape, not colour alone, reduced-motion respected, landmarks and one `h1` per page, skip link.

## 5. Screens

### 5.1 Inbox (`/`)

Data: `GET /work-queue`, `GET /dashboard`.

- Header "Needs your decision" with the sentence "Cadence proposes. Nothing changes until you decide. Opening an item does not change it."
- Filter chips by type with counts (from `/dashboard` counts).
- **Rows grouped by request** for requirement and match items (from the `href`), so three proposed requirements are one row "3 proposed". Each row: type stripe and label, subject, age, one fixed explanatory line per type, action button linking to the existing `href`.
- **Preview evidence** expands a relationship row and fetches `GET /documents/{id}/review` on demand, showing signals (`Email ✓ match`), the proposed action in a dashed block, and signal strength. Match rows expand from `GET /hiring-requests/{id}/matches`.
- Side column: requests in progress (`active_hiring_requests`), open problem reports count (link to `/reports`), recently recorded (`recent_activity`, 12 events, actor kind, action label).
- Footer note when the list is at the 50-item cap.
- No charts. Counts are the real counts.

### 5.2 Intake (`/intake`)

Data: `/documents`, `/documents/{id}`, `/activity`, `/review`, `/candidates/{id}`, `/reviews/{id}/decision`, `POST /documents`.

Two panes: files list (status tag, filename with truncate and full name on focus/title) and detail. Status tags cover `received, extracting, extracted, needs_review, needs_ocr, profiled, failed, quarantined, archived` with a plain explanation (for example "No text layer. OCR needed" for `needs_ocr`; the code for `error_code`). Polling behaviour preserved (1.5 s while `received|extracting`). The relationship review uses `DecisionCase`. The extracted profile preview and the per-document audit remain. Upload is a file drop with the accepted types.

### 5.3 Candidate profile (`/candidates/[id]`)

Data: `GET /candidates/{id}` (audited), `GET /documents/{id}/text` on click only.

- **Header:** name (wraps; long names never overflow), years, latest role from experience, contacts with copy buttons, current CV (filename, date, "replaces N earlier"), source(s).
- **Actions:** Show CV text (with the audit note) · Merge with another profile (opens `/merge` with the id pre-filled).
- **Main column:** Summary (labelled "built from stored fields"), Experience, Education, Skills, Certificates, Qualifications. Each item shows its **source quote and page next to it** (`CV p.1 ✓ verified` or a flagged unverified state). Evidence is attached by matching `value` to the item (employer, title, institution, credential, skill, certificate). Evidence that does not attach appears under "Other extracted evidence".
- **Side column (record):** CV versions (Current / Superseded, in date order), Applications, Activity (last 20 events).
- Empty sections say "Not extracted" (the 488-file baseline ran without the section parser) rather than "None".
- One line: "This profile is built from CVs and cannot be edited here."
- Mobile: sections with sticky anchor chips.

### 5.4 Candidate search (`/candidates`)

Data: `GET /search`.

- Main box "Words in the CV" plus **Add filter** menu (Skill, Minimum years, Job title, Industry, Education, Certificate or qualification, Experience, Name, Nationality). Active filters are removable chips. State is in the URL, so searches are shareable and survive reload.
- Notes: filters combine with AND; only confirmed profiles are searched; nationality matches text already in the CV and is never inferred.
- Results **grouped by candidate**. Each shows reasons split into **Exact** (keyword, skill, name, education, experience, certificate, years, job title, industry, nationality-in-text) and **Approximate** (similar wording, related wording), the evidence snippet with query terms highlighted, a "Passage" vs "Profile fields" label, `confirmed_profile`, and Open profile. An approximate-only hit carries "Only approximate wording matched. Read the CV before relying on this."
- No score display. Results arrive relevance-ordered from the API.
- No criteria → prompt, not "No matches". Zero results → suggests removing a filter.

### 5.5 Hiring requests (`/hiring`)

Index: `GET /hiring-requests` (50 most recent): company, title, status, received date, link. New request form (company, title, description, received date). No pre-filled demo text.

Workspace (`?request=`): `GET /hiring-requests/{id}` and `/matches`.

- Header: company and title, received date, owner ("you" if `owner_user_id == viewer_id`), status.
- **Stepper (derived):** 1 Request → 2 Requirements (n proposed, m approved) → 3 Review matches (found, shortlisted) → 4 Share (approved, sent). The current step is the first incomplete one. Each locked step says what unlocks it.
- **Requirements:** editable rows (text, strength, label), source quote, review status tag, Approve. Editing re-proposes; the UI says so, as the current copy does.
- **Matching:** "Run matching" performs the existing sequence (open, then match). Candidates sorted by disposition. Each candidate shows "n of m requirements met" (computed from the requirement rows) and a **requirement matrix**: requirement, strength, verdict, evidence quote with source. Strengths and gaps summarised. A preferred requirement with no evidence is "Unknown. Not treated as a gap". A dashed "Proposed" block states the disposition and that the matcher never shortlists.
- **Decision:** Add to shortlist, Reject (confirm). Shortlist state is hydrated per candidate by the read-only share-preview call (409 means not shortlisted); it is limited to the first 20 shortlistable matches and shows "unknown" if it fails.
- **Share:** side panel from `GET …/share`. It states what leaves Cadence (company, public name, title, years, skills) and what does not (contact details, CV file). Approve share and Send email are separate steps, each with a confirm dialog naming the recipient. The sent result shows status, recipient, sent time, sender, destination and the audit action.
- **Request record:** description, Notes, Updates, Next steps (add via the existing POST endpoints; list from the request payload; author shown as You / Another recruiter), Files (upload; list filename, type, size).

### 5.6 Other screens

- **Source (`/source`):** same fields and flow; uses `RelationshipReview`; source type shown as a tag.
- **Excel (`/data`):** import result summary plus per-row table (stacks on mobile) with inline `RelationshipReview`; export dates with validation (start ≤ end).
- **Merge (`/merge`):** two profile pickers (search by name using `/search`, or paste an id), side-by-side preview, older profile marked as kept, confirm dialog, result state.
- **Problem reports (`/reports`):** form with category and related record; list with status tags; engineer note shown.

## 6. Responsive behaviour

- Desktop ≥ 1024: two-column layouts, full top bar.
- Tablet 768–1023: side columns collapse under the main column; detail panes open as a slide-over.
- Mobile < 768: bottom tab bar, single column, tables become stacked rows, decision buttons in a sticky bottom bar, 44 px touch targets, no horizontal page scroll.

## 6a. Installable app (PWA)

Requested via `PWA_GUIDE.md`, which describes a Vite setup. Cadence is Next.js 15, so the guide's *behaviour* is kept and its *tooling* is not (`vite-plugin-pwa` does not apply).

**Adopted from the guide**
- Web app manifest: name "Cadence HR", short name "Cadence", `display: standalone`, `scope: /`, `start_url: /` (the Inbox), `theme_color` = `--nav` (`#0B3954`), `background_color` = `--canvas` (`#EEF5F8`), 192 and 512 px icons plus a maskable icon. Served by `app/manifest.ts`.
- iOS tags via the Next `metadata` export: `apple-touch-icon`, `appleWebApp` (capable, title "Cadence", status bar style), and `themeColor`.
- Auto-updating service worker: `skipWaiting`, `clientsClaim`, old caches deleted on activate. Registered only in production builds, never in `next dev`.
- Install banner: Android uses the captured `beforeinstallprompt`; iOS Safari shows the Share, then Add to Home Screen instructions. Gates as in the guide: not already installed, phone or tablet viewport, 30-day dismissal in `localStorage` (wrapped in try/catch), 15 s delay, `appinstalled` hides it. Built with Cadence tokens and no icon library. A permanent "Install app" item in the Desk menu recovers dismissed users.
- HTTPS is required in production; `localhost` is exempt for development. Verify on a real Android phone and on iOS Safari.

**Adapted because this app holds candidate PII and uses bearer-token API calls to another origin**
- The service worker is hand-written (`public/sw.js`, about 40 lines), with no new runtime dependency. It precaches nothing dynamic. It caches only hashed static assets under `/_next/static/` and the icons, and serves a small static `/offline` page when a navigation fails.
- **It never caches, intercepts or replays any request to the API origin** (`NEXT_PUBLIC_API_URL`), any non-GET request, or any page or RSC payload. Candidate, CV, review and hiring data therefore never enter the browser cache, and offline mode does not show stale HR data. Offline shows only "You are offline. Cadence needs a connection to show candidate information."
- The banner is shown only inside the app shell, not on error pages.
- Because the recruiter token is compiled into the bundle (existing design), an installed copy carries it as well. This is recorded as a known limitation and is not changed here.

**Not delivered (as in the guide):** push notifications, background sync, app-store distribution, offline data.

## 7. Implementation shape

- Keep Next.js 15, React 19, Tailwind 4. Add no runtime UI dependency. Native `<dialog>`, `<details>` and semantic elements.
- Each screen: `page.tsx` (server, thin) plus client components as today. Shared behaviour moves to `components/` and `lib/`, so `intake.tsx` (492 lines) and `hiring/desk.tsx` (543 lines) split into focused files.
- Query-param routing stays as the backend emits it.
- Additive changes to `lib/api.ts`: types for `requirement_met_ratio`, notes and updates, attachments, `viewer_id`, `confirmed_profile`, `retrieval_score`, `created_at` on problem reports; functions for `GET /hiring-requests`, notes, updates, next-steps, attachments, `GET /documents/{id}/text`, `GET /excel/candidates/{id}`.

## 8. Verification

1. `next build` and `tsc --noEmit` pass.
2. Unit tests (Vitest, dev dependency only) for the pure logic: lifecycle derivation, queue grouping, evidence attachment, label mapping, URL filter state.
3. Backend suite run unchanged and reported as it is (it needs Postgres; run through the compose stack). No backend file is edited.
3a. PWA: manifest and service worker are served in `next build && next start`; installability passes the DevTools Application panel; the worker is absent in `next dev`; a network trace confirms no API request or HTML page is ever served from cache; offline shows only the offline page; update flow verified by deploying a second build.
4. Contrast check on every text/background token pair (≥ 4.5:1 body, ≥ 3:1 large text and UI edges).
5. Browser walkthrough of the running stack at 1280, 820 and 390 px covering: loading, empty and error states; a bad token (401) and a wrong-role call (403); long candidate names and 120-character filenames; a large result set; pending, approved, rejected and shortlisted states; relationship review through to a recorded decision; requirement approval through to a sent share; keyboard-only pass through dialogs.

## 9. Out of scope

Backend, schema and API changes; per-person sign-in; SharePoint or OneDrive; a candidate directory; profile editing; request-level audit; attachment download; charts and analytics; push notifications and offline data (PWA is install and static-shell only). The recruiter token is compiled into the web bundle by the existing design (`NEXT_PUBLIC_RECRUITER_TOKEN`); this is noted but not changed.

## 10. Changes made during implementation (found by running it)

Verification against the real stack changed four decisions from the sections above.

- **Inbox data source.** The work-queue endpoint returns only the newest 50 rows across all types. With hundreds of pending match rows it hid every relationship review. The Inbox is built from `/dashboard` instead: up to 20 rows per type plus exact counts. Chips show the exact counts, groups show "20+" when a type is truncated, and a note says how many rows are shown of how many exist.
- **Shortlist state.** Read from the dashboard's shortlist and share-awaiting lists when they are complete (count fits in 20), which is silent. The share-preview probe (which answers 409 to everyone not shortlisted and logs console errors) is only a fallback when those lists are truncated.
- **Offline page.** A plain `public/offline.html` with no scripts, not a Next route: the route's JavaScript chunks are not cached, so hydration failed offline.
- **Long lists.** Match cards (351 in the test data), profile experience, education and unattached evidence show the first few with a "show more" control. Explanatory text on Inbox rows appears once per type.
- **Profile open on intake.** The extracted profile in Intake loads on request ("Show extracted profile"), because opening a profile is audited.
- **CSS layering.** Element defaults live in `@layer base` and shared classes in `@layer components`. Unlayered rules had overridden Tailwind utilities (link colours).

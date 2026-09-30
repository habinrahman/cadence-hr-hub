# Cadence Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `web/` frontend as a coherent internal HR operations product (Ocean palette, provenance-first "case file" design, installable PWA) without touching the backend.

**Architecture:** Keep Next.js 15 / React 19 / Tailwind 4 and the existing query-param routes the backend links to. Add `components/ui` (primitives), `components/domain` (decision-case pieces), and `lib/` pure-logic modules (lifecycle, queue grouping, evidence linking, search state, error mapping) that are unit-tested. `lib/api.ts` changes are additive only.

**Tech Stack:** Next.js 15, React 19, Tailwind CSS 4, TypeScript 5.9 strict, Vitest (dev only), native `<dialog>`.

## Global Constraints

Copied from the spec (`docs/superpowers/specs/2026-09-30-cadence-frontend-redesign-design.md`):

- Do not modify anything under `backend/`, the schema, business logic, auth/RBAC, audit behaviour, API contracts, or the 126 backend tests. Frontend only.
- Do not invent backend functionality. Unavailable data is not faked: no candidate directory, no profile editing, no candidate-level match/share history, no request audit log, no attachment download, no person names in audit.
- Wording: "Proposed by Cadence", never "AI". Relationship confidence is shown as "signal strength" beside its signals.
- Never prefetch `GET /candidates/{id}` or `GET /documents/{id}/text` (both write audit events). CV text loads only on an explicit click with a recorded-view note.
- Keep routes: `/` (Inbox; `?document=` redirects to `/intake?document=`), `/intake`, `/hiring` (`?request=`, `?candidate=`), `/candidates`, `/candidates/[id]`, `/search` (redirect), `/queue` and `/dashboard` (redirect to `/`), `/source`, `/data`, `/merge`, `/reports`.
- Palette A (Ocean): `--nav #0B3954`, `--nav-ink #CFE4F0`, `--canvas #EEF5F8`, `--panel #FFFFFF`, `--rule #C9DAE3`, `--ink #0E2230`, `--mut #4A6272`, `--human #0A6CC2`, `--human-bg #E1F0FC`, `--prop #B86E00`, `--prop-bg #FFF0D2`, `--ok #1B8A5A`, `--bad #C8412F`, `--ev #4F7591`, object hues `--t-rel #6C5CE7`, `--t-req #00A6C8`, `--t-match #2BA57A`, `--t-share #E0567A`.
- Contrast: hues above are for borders, fills, stripes. Text and white-on-fill tags use darker `-ink` variants that reach 4.5:1 (body) / 3:1 (large text, UI edges).
- Type: system UI stack (no web font), scale 12/13/14/16/20/26, 14 px base, tabular numerals, monospace for ids/filenames/source lines. Space base 4 px. Radius 3–4 px, hairline borders, no big rounded cards. Touch targets ≥ 44 px on mobile.
- Every screen has loading (skeleton, `aria-busy`), empty, error (401/403/404/409/5xx wording) and pending/decided states. Irreversible actions (merge, approve share, send, reject) use a confirm dialog naming the object.
- Accessibility: visible focus ring, keyboard operable, native `<dialog>`, `aria-live` results, status not by colour alone, reduced motion, one `h1` per page, skip link.
- PWA: `app/manifest.ts`, `public/sw.js` (hashed static assets under `/_next/static/` and icons only; never API origin, non-GET, pages or RSC payloads), `/offline` page, production-only registration, install banner (not installed, phone/tablet viewport, 15 s delay, 30-day `localStorage` dismissal in try/catch), Desk-menu "Install app".
- No new runtime dependency. Dev dependency allowed: `vitest`.

## File Structure

```
web/
  app/
    globals.css                  tokens + base styles (Task 2)
    layout.tsx                   shell, metadata, skip link (Task 5)
    manifest.ts                  PWA manifest (Task 13)
    offline/page.tsx             offline fallback (Task 13)
    page.tsx                     Inbox (Task 7)
    inbox/{inbox.tsx,row.tsx}
    intake/{page.tsx,intake.tsx,file-list.tsx,document-detail.tsx}
    hiring/{page.tsx,index-view.tsx,new-request.tsx,workspace.tsx,requirements.tsx,matches.tsx,share-panel.tsx,record.tsx}
    candidates/{page.tsx,search.tsx,result-group.tsx}
    candidates/[id]/{page.tsx,view.tsx,facts.tsx,record.tsx}
    search/page.tsx queue/page.tsx dashboard/page.tsx   redirects
    source/ data/ merge/ reports/  restyled forms
  components/
    ui/        button.tsx tag.tsx chip.tsx panel.tsx field.tsx skeleton.tsx states.tsx toast.tsx
               dialog.tsx menu.tsx tabs.tsx table.tsx stepper.tsx slide-over.tsx
    shell/     top-bar.tsx bottom-tabs.tsx add-menu.tsx desk-menu.tsx install-banner.tsx sw-register.tsx
    domain/    decision-case.tsx relationship-review.tsx signal-list.tsx evidence-quote.tsx
               audit-line.tsx requirement-matrix.tsx candidate-header.tsx
  lib/
    api.ts (additive)  errors.ts  labels.ts  format.ts  lifecycle.ts  queue.ts  evidence.ts
    search-state.ts    use-async.ts
  lib/__tests__/*.test.ts        vitest specs
  public/sw.js  public/icons/*
  vitest.config.ts
```

---

### Task 1: Tooling and green baseline

**Files:**
- Modify: `web/package.json`
- Create: `web/vitest.config.ts`

**Interfaces:**
- Produces: `npm test` (vitest run), alias `@` → project root.

- [ ] **Step 0: Commit the untouched frontend as a rollback point**

`web/` is untracked in this clone. Run: `git add web/app web/lib web/package.json web/package-lock.json web/next.config.ts web/postcss.config.mjs web/tsconfig.json web/Dockerfile web/.dockerignore web/.env.example web/next-env.d.ts && git commit -m "chore(web): baseline before redesign"`
Expected: one commit containing the original sources (node_modules and build output are already ignored).

- [ ] **Step 1: Record the baseline**

Run (in `web/`): `npx tsc --noEmit` and `npm run build`
Expected: both pass on the current code. If not, stop and report what fails before changing anything.

- [ ] **Step 2: Add Vitest**

Run: `npm install -D vitest@^3`

Edit `web/package.json` scripts to add `"test": "vitest run"` and `"typecheck": "tsc --noEmit"`.

- [ ] **Step 3: Configure**

`web/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: { alias: { "@": path.resolve(__dirname) } },
  test: { include: ["lib/__tests__/**/*.test.ts"], environment: "node" },
});
```

- [ ] **Step 4: Prove the runner works**

Create `web/lib/__tests__/smoke.test.ts` with `import { it, expect } from "vitest"; it("runs", () => expect(1).toBe(1));`
Run: `npm test`
Expected: 1 passed. Delete `smoke.test.ts`.

- [ ] **Step 5: Commit**

```bash
git add web/package.json web/package-lock.json web/vitest.config.ts
git commit -m "chore(web): add vitest and typecheck scripts"
```

---

### Task 2: Pure logic libraries (TDD) and additive API client

**Files:**
- Create: `web/lib/errors.ts`, `labels.ts`, `format.ts`, `lifecycle.ts`, `queue.ts`, `evidence.ts`, `search-state.ts`, `use-async.ts`
- Create tests: `web/lib/__tests__/{errors,format,lifecycle,queue,evidence,search-state}.test.ts`
- Modify: `web/lib/api.ts` (additive)

**Interfaces (produced, used by later tasks):**

```ts
// errors.ts
export class ApiError extends Error { status: number; code: string; constructor(status: number, code: string) }
export type ErrorKind = "auth" | "forbidden" | "missing" | "conflict" | "server" | "network" | "input";
export function describeError(error: unknown): { kind: ErrorKind; title: string; body: string }

// format.ts
export function shortDate(iso: string | null | undefined): string          // "28 Sep 2026" or "—"
export function relativeAge(iso: string, now?: Date): string                // "today" | "2 days ago" | "3 weeks ago"
export function plural(n: number, one: string, many?: string): string

// lifecycle.ts
export type StepState = "done" | "current" | "locked";
export type Step = { key: "request" | "requirements" | "matches" | "share"; label: string; state: StepState; detail: string };
export type LifecycleInput = {
  requirements: { review_status: string }[];
  matchCount: number;                 // matches returned by the API
  shortlisted: number | null;         // null = unknown (probe failed)
  sharesApproved: number;
  shared: number;                     // request.candidates_shared
};
export function deriveLifecycle(input: LifecycleInput): Step[]

// queue.ts
export type QueueItem = DeskItem;     // from api.ts
export type QueueGroup = { key: string; type: string; subject: string; names: string[]; count: number;
  status: string; created_at: string; href: string; requestId: string | null };
export function requestIdFromHref(href: string): string | null
export function groupQueue(items: QueueItem[]): QueueGroup[]

// evidence.ts
export type EvidenceRow = CandidateProfile["evidence"][number];
export function splitEvidence(profile: CandidateProfile): { find: (field: string, value: string | null | undefined) => EvidenceRow | undefined; other: EvidenceRow[] }

// search-state.ts
export const FILTERS: { name: string; label: string; note?: string }[]
export function parseSearch(params: URLSearchParams): Record<string, string>
export function toQueryString(values: Record<string, string>): string
export type CandidateGroup = { key: string; candidateId: string | null; name: string | null; hits: SearchHit[]; exact: string[]; approximate: string[]; approximateOnly: boolean }
export function groupHits(hits: SearchHit[]): CandidateGroup[]
export function hasCriteria(values: Record<string, string>): boolean
```

- [ ] **Step 1: Failing tests for errors and format**

`web/lib/__tests__/errors.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { ApiError, describeError } from "@/lib/errors";

describe("describeError", () => {
  it("explains 401", () => {
    const e = describeError(new ApiError(401, "unauthorized"));
    expect(e.kind).toBe("auth");
    expect(e.title).toMatch(/not accepted/i);
  });
  it("explains 403 by role", () => {
    const e = describeError(new ApiError(403, "recruiter_required"));
    expect(e.kind).toBe("forbidden");
    expect(e.body).toMatch(/role/i);
  });
  it("maps known conflict codes to plain words", () => {
    expect(describeError(new ApiError(409, "requirements_not_approved")).body).toMatch(/approve/i);
    expect(describeError(new ApiError(409, "not_shortlisted")).body).toMatch(/shortlist/i);
    expect(describeError(new ApiError(409, "request_not_open")).kind).toBe("conflict");
  });
  it("handles unknown 5xx and network failure", () => {
    expect(describeError(new ApiError(500, "boom")).kind).toBe("server");
    expect(describeError(new TypeError("Failed to fetch")).kind).toBe("network");
  });
  it("never returns raw JSON", () => {
    expect(describeError(new ApiError(422, "[object Object]")).body).not.toMatch(/object Object/);
  });
});
```

`web/lib/__tests__/format.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { shortDate, relativeAge, plural } from "@/lib/format";

const now = new Date("2026-09-30T12:00:00Z");
describe("format", () => {
  it("formats dates", () => {
    expect(shortDate("2026-09-28T09:00:00Z")).toBe("28 Sep 2026");
    expect(shortDate(null)).toBe("—");
    expect(shortDate("")).toBe("—");
  });
  it("gives relative ages", () => {
    expect(relativeAge("2026-09-30T08:00:00Z", now)).toBe("today");
    expect(relativeAge("2026-09-28T12:00:00Z", now)).toBe("2 days ago");
    expect(relativeAge("2026-09-09T12:00:00Z", now)).toBe("3 weeks ago");
  });
  it("pluralises", () => {
    expect(plural(1, "item")).toBe("1 item");
    expect(plural(3, "item")).toBe("3 items");
    expect(plural(2, "match", "matches")).toBe("2 matches");
  });
});
```

- [ ] **Step 2: Run to see them fail**

Run: `npm test`
Expected: FAIL, cannot resolve `@/lib/errors` and `@/lib/format`.

- [ ] **Step 3: Implement `errors.ts` and `format.ts`**

`web/lib/errors.ts`:

```ts
export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

export type ErrorKind = "auth" | "forbidden" | "missing" | "conflict" | "server" | "network" | "input";

const CONFLICT_WORDS: Record<string, string> = {
  requirements_not_approved: "Approve at least one requirement before running matching.",
  request_not_open: "This request is not open for matching.",
  not_shortlisted: "This candidate has not been shortlisted for this request.",
  not_shortlistable: "Only recommended or needs-review candidates can be shortlisted.",
  approval_required: "Approve the share before sending it.",
  invalid_transition: "That action is not allowed in the current state.",
  human_required: "A recruiter has to take this action.",
  external_mail_blocked: "Sending is blocked outside the local mail catcher in this environment.",
  mail_delivery_failed: "The mail server did not accept the message. Nothing was recorded as sent.",
  empty_update: "Nothing to update.",
};

function clean(code: string): string {
  if (!code || code.includes("[object") || code.startsWith("{") || code.startsWith("[")) return "";
  return code.replaceAll("_", " ");
}

export function describeError(error: unknown): { kind: ErrorKind; title: string; body: string } {
  if (error instanceof ApiError) {
    const { status, code } = error;
    if (status === 401)
      return { kind: "auth", title: "Your session is not accepted", body: "The desk could not verify you. Sign in again or ask an administrator to check your access." };
    if (status === 403)
      return { kind: "forbidden", title: "This role cannot open this", body: "Your role does not allow this action. Recruiter-only screens return this for other roles." };
    if (status === 404) return { kind: "missing", title: "Not found", body: "That record does not exist or was removed." };
    if (status === 409 || CONFLICT_WORDS[code])
      return { kind: "conflict", title: "Cannot do that now", body: CONFLICT_WORDS[code] ?? (clean(code) || "The record is in a different state.") };
    if (status === 413) return { kind: "input", title: "File too large", body: "Choose a smaller file." };
    if (status === 415) return { kind: "input", title: "File type not supported", body: "Use PDF, Word or an image of a scan." };
    if (status === 422) return { kind: "input", title: "Check the entries", body: clean(code) || "Some fields were not accepted." };
    if (status === 502) return { kind: "server", title: "Could not deliver", body: CONFLICT_WORDS[code] ?? "A downstream service failed." };
    if (status >= 500) return { kind: "server", title: "The server had a problem", body: "Try again. If it keeps happening, file a problem report." };
    return { kind: "server", title: "Request failed", body: clean(code) || `Status ${status}.` };
  }
  if (error instanceof TypeError)
    return { kind: "network", title: "Cannot reach the server", body: "Check your connection and try again." };
  const message = error instanceof Error ? error.message : "";
  return { kind: "server", title: "Something went wrong", body: clean(message) || "Try again." };
}
```

`web/lib/format.ts`:

```ts
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

export function relativeAge(iso: string, now: Date = new Date()): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const days = Math.floor((now.getTime() - then) / 86_400_000);
  if (days < 1) return "today";
  if (days < 7) return `${days} ${days === 1 ? "day" : "days"} ago`;
  const weeks = Math.floor(days / 7);
  if (days < 60) return `${weeks} ${weeks === 1 ? "week" : "weeks"} ago`;
  const months = Math.floor(days / 30);
  return `${months} months ago`;
}

export function plural(n: number, one: string, many?: string): string {
  return `${n} ${n === 1 ? one : (many ?? `${one}s`)}`;
}
```

- [ ] **Step 4: Run tests, expect pass**

Run: `npm test`
Expected: errors and format suites pass.

- [ ] **Step 5: Failing tests for lifecycle, queue, evidence, search-state**

`web/lib/__tests__/lifecycle.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { deriveLifecycle } from "@/lib/lifecycle";

const base = { requirements: [], matchCount: 0, shortlisted: 0, sharesApproved: 0, shared: 0 };
const states = (i: Parameters<typeof deriveLifecycle>[0]) => deriveLifecycle(i).map((s) => s.state);

describe("deriveLifecycle", () => {
  it("starts on requirements when none exist", () => {
    expect(states(base)).toEqual(["done", "current", "locked", "locked"]);
  });
  it("stays on requirements while any is unapproved", () => {
    const r = [{ review_status: "approved" }, { review_status: "proposed" }];
    expect(states({ ...base, requirements: r })).toEqual(["done", "current", "locked", "locked"]);
  });
  it("moves to review once all are approved", () => {
    const r = [{ review_status: "approved" }];
    expect(states({ ...base, requirements: r })).toEqual(["done", "done", "current", "locked"]);
  });
  it("moves to share once someone is shortlisted", () => {
    const r = [{ review_status: "approved" }];
    expect(states({ ...base, requirements: r, matchCount: 3, shortlisted: 1 })).toEqual(["done", "done", "done", "current"]);
  });
  it("completes when a share was sent", () => {
    const r = [{ review_status: "approved" }];
    expect(states({ ...base, requirements: r, matchCount: 3, shortlisted: 1, sharesApproved: 1, shared: 1 })).toEqual(["done", "done", "done", "done"]);
  });
  it("treats unknown shortlist state as not done and says so", () => {
    const r = [{ review_status: "approved" }];
    const steps = deriveLifecycle({ ...base, requirements: r, matchCount: 3, shortlisted: null });
    expect(steps[2].state).toBe("current");
    expect(steps[2].detail).toMatch(/unknown/i);
  });
  it("details count proposals and approvals", () => {
    const r = [{ review_status: "approved" }, { review_status: "proposed" }, { review_status: "proposed" }];
    expect(deriveLifecycle({ ...base, requirements: r })[1].detail).toBe("1 approved · 2 proposed");
  });
});
```

`web/lib/__tests__/queue.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { groupQueue, requestIdFromHref } from "@/lib/queue";

const item = (type: string, subject: string, href: string, created_at = "2026-09-30T10:00:00Z") =>
  ({ type, subject, status: "proposed", created_at, href });

describe("queue", () => {
  it("extracts request ids", () => {
    expect(requestIdFromHref("/hiring?request=abc&candidate=x")).toBe("abc");
    expect(requestIdFromHref("/?document=d1")).toBeNull();
  });
  it("groups requirement rows by request", () => {
    const g = groupQueue([
      item("requirement_approval", "Example Labs · Backend engineer", "/hiring?request=r1"),
      item("requirement_approval", "Example Labs · Backend engineer", "/hiring?request=r1", "2026-09-30T11:00:00Z"),
      item("requirement_approval", "Harbor · Accountant", "/hiring?request=r2"),
    ]);
    expect(g).toHaveLength(2);
    const r1 = g.find((x) => x.requestId === "r1")!;
    expect(r1.count).toBe(2);
    expect(r1.created_at).toBe("2026-09-30T11:00:00Z");
  });
  it("groups matches and lists candidate names", () => {
    const g = groupQueue([
      item("match_review", "Amira Khan · Example Labs · Backend engineer", "/hiring?request=r1"),
      item("match_review", "Jonas Weber · Example Labs · Backend engineer", "/hiring?request=r1"),
    ]);
    expect(g).toHaveLength(1);
    expect(g[0].names).toEqual(["Amira Khan", "Jonas Weber"]);
    expect(g[0].subject).toBe("Example Labs · Backend engineer");
  });
  it("keeps relationship and share rows separate", () => {
    const g = groupQueue([
      item("relationship_review", "Amira Khan", "/?document=d1"),
      item("relationship_review", "Amira Khan", "/?document=d2"),
      item("share_approval", "Jonas · Example Labs · Backend", "/hiring?request=r1&candidate=c1"),
      item("share_approval", "Lena · Example Labs · Backend", "/hiring?request=r1&candidate=c2"),
    ]);
    expect(g).toHaveLength(4);
  });
  it("orders newest first", () => {
    const g = groupQueue([
      item("relationship_review", "Old", "/?document=a", "2026-09-01T00:00:00Z"),
      item("relationship_review", "New", "/?document=b", "2026-09-29T00:00:00Z"),
    ]);
    expect(g[0].subject).toBe("New");
  });
});
```

`web/lib/__tests__/evidence.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { splitEvidence } from "@/lib/evidence";
import type { CandidateProfile } from "@/lib/api";

const profile = {
  id: "c1", display_name: "Amira Khan", summary: null, narrative: null, years_of_experience: 6.5, source: "upload",
  sources: [], contacts: [],
  experiences: [{ employer: "Northwind", title: "Backend engineer" }],
  education: [{ institution: "Univ. of Sharjah", credential: "BSc" }],
  skills: ["Python"], certificates: [{ name: "AWS SA", kind: "certificate" }], qualifications: [],
  applications: [], documents: [], activity: [],
  evidence: [
    { field: "employer", value: "Northwind", quote: "Backend engineer at Northwind", page: 1, quote_verified: true },
    { field: "title", value: "Backend engineer", quote: "Backend engineer at Northwind", page: 1, quote_verified: true },
    { field: "name", value: "Python", quote: "Built services in Python", page: 1, quote_verified: true },
    { field: "name", value: "AWS SA", quote: "AWS Solutions Architect", page: 2, quote_verified: false },
    { field: "institution", value: "Univ. of Sharjah", quote: "BSc, Univ. of Sharjah", page: 2, quote_verified: true },
    { field: "start_date", value: "2018-01-01", quote: "2018 to 2021", page: 1, quote_verified: true },
  ],
} as CandidateProfile;

describe("splitEvidence", () => {
  const { find, other } = splitEvidence(profile);
  it("finds evidence by field and value", () => {
    expect(find("employer", "Northwind")?.page).toBe(1);
    expect(find("name", "Python")?.quote).toMatch(/Python/);
    expect(find("name", "AWS SA")?.quote_verified).toBe(false);
  });
  it("returns undefined when nothing is stored", () => {
    expect(find("name", "Docker")).toBeUndefined();
    expect(find("employer", null)).toBeUndefined();
  });
  it("puts unattached evidence in other", () => {
    expect(other.map((e) => e.field)).toEqual(["start_date"]);
  });
});
```

`web/lib/__tests__/search-state.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { parseSearch, toQueryString, groupHits, hasCriteria, FILTERS } from "@/lib/search-state";
import type { SearchHit } from "@/lib/api";

const hit = (over: Partial<SearchHit>): SearchHit => ({
  candidate_id: "c1", candidate_name: "Amira", document_id: "d1", chunk_id: "k1",
  evidence: "…python…", reasons: ["keyword"], retrieval_score: 1, ...over,
});

describe("search state", () => {
  it("parses only known fields", () => {
    const v = parseSearch(new URLSearchParams("q=python&skill=sql&evil=1&min_years="));
    expect(v).toEqual({ q: "python", skill: "sql" });
  });
  it("round-trips", () => {
    const qs = toQueryString({ q: "a b", skill: "sql", name: " " });
    expect(qs).toBe("q=a+b&skill=sql");
  });
  it("knows whether there are criteria", () => {
    expect(hasCriteria({})).toBe(false);
    expect(hasCriteria({ q: "  " })).toBe(false);
    expect(hasCriteria({ skill: "x" })).toBe(true);
  });
  it("lists nationality with a note", () => {
    expect(FILTERS.find((f) => f.name === "nationality")?.note).toMatch(/never inferred|already written/i);
  });
  it("groups hits by candidate and splits reasons", () => {
    const g = groupHits([
      hit({ reasons: ["keyword", "skill"] }),
      hit({ chunk_id: "k2", reasons: ["semantic"] }),
      hit({ candidate_id: "c2", candidate_name: "Jonas", reasons: ["trigram"] }),
    ]);
    expect(g).toHaveLength(2);
    expect(g[0].hits).toHaveLength(2);
    expect(g[0].exact).toEqual(["keyword", "skill"]);
    expect(g[0].approximate).toEqual(["semantic"]);
    expect(g[0].approximateOnly).toBe(false);
    expect(g[1].approximateOnly).toBe(true);
  });
  it("keeps hits with no candidate separate", () => {
    const g = groupHits([hit({ candidate_id: null, document_id: "d1" }), hit({ candidate_id: null, document_id: "d2" })]);
    expect(g).toHaveLength(2);
  });
});
```

- [ ] **Step 6: Run to see failure**

Run: `npm test`
Expected: FAIL, missing modules `lifecycle`, `queue`, `evidence`, `search-state`.

- [ ] **Step 7: Implement the four modules**

`web/lib/lifecycle.ts`:

```ts
export type StepState = "done" | "current" | "locked";
export type Step = {
  key: "request" | "requirements" | "matches" | "share";
  label: string;
  state: StepState;
  detail: string;
};
export type LifecycleInput = {
  requirements: { review_status: string }[];
  matchCount: number;
  shortlisted: number | null;
  sharesApproved: number;
  shared: number;
};

export function deriveLifecycle(input: LifecycleInput): Step[] {
  const approved = input.requirements.filter((r) => r.review_status === "approved").length;
  const pending = input.requirements.length - approved;
  const requirementsDone = approved > 0 && pending === 0;
  const shortlisted = input.shortlisted ?? 0;
  const reviewDone = shortlisted > 0 || input.shared > 0;
  const shareDone = input.shared > 0;

  const raw: { key: Step["key"]; label: string; done: boolean; detail: string }[] = [
    { key: "request", label: "Request", done: true, detail: "Saved" },
    {
      key: "requirements",
      label: "Requirements",
      done: requirementsDone,
      detail: input.requirements.length === 0 ? "None proposed yet" : `${approved} approved · ${pending} proposed`,
    },
    {
      key: "matches",
      label: "Review matches",
      done: reviewDone,
      detail:
        input.shortlisted === null && input.matchCount > 0
          ? `${input.matchCount} found · shortlist state unknown`
          : input.matchCount === 0
            ? "Matching not run"
            : `${input.matchCount} found · ${shortlisted} shortlisted`,
    },
    {
      key: "share",
      label: "Share",
      done: shareDone,
      detail: shareDone ? `${input.shared} shared` : input.sharesApproved > 0 ? `${input.sharesApproved} approved, not sent` : "Approve, then send",
    },
  ];
  let currentAssigned = false;
  return raw.map((step) => {
    if (step.done) return { key: step.key, label: step.label, state: "done", detail: step.detail };
    if (!currentAssigned) {
      currentAssigned = true;
      return { key: step.key, label: step.label, state: "current", detail: step.detail };
    }
    return { key: step.key, label: step.label, state: "locked", detail: step.detail };
  });
}
```

`web/lib/queue.ts`:

```ts
import type { DeskItem } from "@/lib/api";

export type QueueItem = DeskItem;
export type QueueGroup = {
  key: string;
  type: string;
  subject: string;
  names: string[];
  count: number;
  status: string;
  created_at: string;
  href: string;
  requestId: string | null;
};

export function requestIdFromHref(href: string): string | null {
  const query = href.split("?")[1];
  if (!query) return null;
  return new URLSearchParams(query).get("request");
}

const GROUPED = new Set(["requirement_approval", "match_review"]);

export function groupQueue(items: QueueItem[]): QueueGroup[] {
  const groups = new Map<string, QueueGroup>();
  items.forEach((item, index) => {
    const requestId = requestIdFromHref(item.href);
    const grouped = GROUPED.has(item.type) && requestId !== null;
    const key = grouped ? `${item.type}:${requestId}` : `${item.type}:${item.href}:${index}`;
    let subject = item.subject;
    const names: string[] = [];
    if (grouped && item.type === "match_review") {
      const cut = item.subject.indexOf(" · ");
      if (cut > 0) {
        names.push(item.subject.slice(0, cut));
        subject = item.subject.slice(cut + 3);
      }
    }
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, { key, type: item.type, subject, names, count: 1, status: item.status, created_at: item.created_at, href: item.href, requestId });
      return;
    }
    existing.count += 1;
    existing.names.push(...names);
    if (item.created_at > existing.created_at) existing.created_at = item.created_at;
  });
  return [...groups.values()].sort((a, b) => (a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0));
}
```

`web/lib/evidence.ts`:

```ts
import type { CandidateProfile } from "@/lib/api";

export type EvidenceRow = CandidateProfile["evidence"][number];

const key = (field: string, value: string) => `${field}\u0000${value}`;

export function splitEvidence(profile: CandidateProfile) {
  const byKey = new Map<string, EvidenceRow>();
  for (const row of profile.evidence) {
    const k = key(row.field, row.value);
    if (!byKey.has(k)) byKey.set(k, row);
  }
  const wanted = new Set<string>();
  const want = (field: string, value: string | null | undefined) => {
    if (value) wanted.add(key(field, value));
  };
  want("display_name", profile.display_name);
  want("summary", profile.summary);
  if (profile.years_of_experience !== null) want("years_of_experience", String(profile.years_of_experience));
  for (const e of profile.experiences) {
    want("employer", e.employer);
    want("title", e.title);
  }
  for (const e of profile.education) {
    want("institution", e.institution);
    want("credential", e.credential);
  }
  for (const s of profile.skills) want("name", s);
  for (const c of [...profile.certificates, ...profile.qualifications]) want("name", c.name);

  return {
    find(field: string, value: string | null | undefined): EvidenceRow | undefined {
      return value ? byKey.get(key(field, value)) : undefined;
    },
    other: profile.evidence.filter((row) => !wanted.has(key(row.field, row.value))),
  };
}
```

`web/lib/search-state.ts`:

```ts
import type { SearchHit } from "@/lib/api";

export const FILTERS: { name: string; label: string; note?: string }[] = [
  { name: "skill", label: "Skill" },
  { name: "min_years", label: "Minimum years" },
  { name: "job_title", label: "Job title" },
  { name: "industry", label: "Industry experience" },
  { name: "education", label: "Education" },
  { name: "certificate", label: "Certificate or qualification" },
  { name: "experience", label: "Experience" },
  { name: "name", label: "Name" },
  {
    name: "nationality",
    label: "Nationality",
    note: "Use only when the role requires it. It matches words already written in the CV and is never inferred.",
  },
];

const KNOWN = new Set(["q", ...FILTERS.map((f) => f.name)]);

export function parseSearch(params: URLSearchParams): Record<string, string> {
  const out: Record<string, string> = {};
  params.forEach((value, name) => {
    if (KNOWN.has(name) && value.trim()) out[name] = value;
  });
  return out;
}

export function toQueryString(values: Record<string, string>): string {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(values)) {
    if (KNOWN.has(name) && value.trim()) params.set(name, value);
  }
  return params.toString();
}

export function hasCriteria(values: Record<string, string>): boolean {
  return Object.values(values).some((v) => v.trim() !== "");
}

const APPROXIMATE = new Set(["trigram", "semantic"]);

export type CandidateGroup = {
  key: string;
  candidateId: string | null;
  name: string | null;
  hits: SearchHit[];
  exact: string[];
  approximate: string[];
  approximateOnly: boolean;
};

export function groupHits(hits: SearchHit[]): CandidateGroup[] {
  const groups = new Map<string, CandidateGroup>();
  for (const hit of hits) {
    const key = hit.candidate_id ?? `doc:${hit.document_id}`;
    let group = groups.get(key);
    if (!group) {
      group = { key, candidateId: hit.candidate_id, name: hit.candidate_name, hits: [], exact: [], approximate: [], approximateOnly: false };
      groups.set(key, group);
    }
    group.hits.push(hit);
    for (const reason of hit.reasons) {
      const list = APPROXIMATE.has(reason) ? group.approximate : group.exact;
      if (!list.includes(reason)) list.push(reason);
    }
  }
  const out = [...groups.values()];
  for (const g of out) g.approximateOnly = g.exact.length === 0 && g.approximate.length > 0;
  return out;
}
```

`web/lib/use-async.ts`:

```ts
"use client";
import { useCallback, useEffect, useRef, useState } from "react";

export type AsyncState<T> = { data: T | null; error: unknown; loading: boolean; reload: () => void };

export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loadRef.current()
      .then((value) => !cancelled && setData(value))
      .catch((reason) => !cancelled && setError(reason))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((n) => n + 1), []);
  return { data, error, loading, reload };
}
```

`web/lib/labels.ts` (single label source; move the maps now duplicated across `intake.tsx`, `source/form.tsx`, `data/form.tsx`, `hiring/desk.tsx`, `search/form.tsx`, `queue/form.tsx`, `reports/form.tsx`):

```ts
export const SIGNAL_LABELS: Record<string, string> = {
  email: "Email", phone: "Phone", name: "Name", document_hash: "Identical file", cv_dates: "CV dates",
  explicit_version: "Version date in the CV", employment: "Employment", education: "Education",
  skills: "Skills", semantic: "Wording similarity",
};
export const SIGNAL_STATE_LABELS: Record<string, string> = {
  matched: "Match", unmatched: "No match", unknown: "Not available", recorded: "Compared",
};
export const ACTION_LABELS: Record<string, string> = {
  accept_update: "Update the existing profile",
  record_duplicate: "Record as duplicate",
  create_separate_candidate: "Save as a different candidate",
};
export const ACTION_SHORT: Record<string, string> = {
  accept_update: "Update profile", record_duplicate: "Duplicate", create_separate_candidate: "Different person",
};
export const RELATIONSHIP_LABELS: Record<string, string> = {
  updated_cv: "Updated CV", duplicate: "Duplicate", different_candidate: "Different candidate",
  new: "New candidate", ambiguous: "Needs a choice",
};
export const DOCUMENT_STATUS: Record<string, { label: string; note: string }> = {
  received: { label: "Queued", note: "Waiting for the reader." },
  extracting: { label: "Reading", note: "The reader is extracting text. This page updates on its own." },
  extracted: { label: "Extracted", note: "Text and profile fields were read." },
  needs_review: { label: "Needs a decision", note: "A recruiter has to decide how this CV relates to an existing profile." },
  needs_ocr: { label: "Needs OCR", note: "No text layer was found. The file cannot be searched until it is read by OCR." },
  profiled: { label: "Profiled", note: "Linked to a candidate profile." },
  failed: { label: "Failed", note: "Processing failed." },
  quarantined: { label: "Quarantined", note: "Set aside so it cannot become a profile. See the problem code." },
  archived: { label: "Archived", note: "Kept on record after the retention period." },
};
export const QUEUE_TYPE: Record<string, { label: string; hue: "rel" | "req" | "match" | "share"; why: string }> = {
  relationship_review: { label: "CV relationship", hue: "rel", why: "A CV overlaps an existing profile. You decide whether it updates, duplicates or is a different person." },
  requirement_approval: { label: "Requirements", hue: "req", why: "Proposed from the job description. They do not drive matching until you approve them." },
  match_review: { label: "Match review", hue: "match", why: "Candidates compared with approved requirements. Matching never shortlists." },
  share_approval: { label: "Share approval", hue: "share", why: "Shortlisted. Nothing has left Cadence until you approve and send." },
};
export const DISPOSITION: Record<string, { label: string; tone: "ok" | "prop" | "bad" | "human" | "unk" }> = {
  recommended: { label: "Recommended", tone: "prop" },
  needs_review: { label: "Needs review", tone: "prop" },
  excluded: { label: "Excluded", tone: "bad" },
  rejected: { label: "Rejected", tone: "bad" },
};
export const VERDICT: Record<string, { label: string; tone: "ok" | "prop" | "bad" | "unk" }> = {
  meets: { label: "Meets", tone: "ok" },
  partial: { label: "Partial", tone: "prop" },
  unmet: { label: "Not met", tone: "bad" },
  unknown: { label: "Unknown", tone: "unk" },
};
export const SEARCH_REASON: Record<string, string> = {
  keyword: "Keyword in the CV", trigram: "Similar wording", semantic: "Related wording", skill: "Skill",
  name: "Name", education: "Education", experience: "Experience", certificate: "Certificate",
  years: "Years of experience", job_title: "Job title", industry: "Industry experience",
  nationality: "Nationality written in the CV", filter: "Filter",
};
export const AUDIT_ACTION: Record<string, string> = {
  document_received: "File received", document_extracted: "Extraction finished", same_document: "Identical file recognised",
  duplicate_review_opened: "Recommendation prepared", duplicate_review_decided: "Recruiter decided",
  accepted_update: "Accepted update", recorded_duplicate: "Marked duplicate", created_separate: "Saved as a different candidate",
  field_lock_kept: "Locked field kept", candidate_viewed: "Profile opened", pii_text_access: "CV text opened",
  shortlist_decision: "Shortlisted", share_approved: "Share approved", candidate_shared: "Candidate shared",
  candidate_share_failed: "Share failed", matching_run: "Matching run", hiring_request_created: "Request created",
  sourced_cv_attached: "CV attached", sourced_duplicate_detected: "Duplicate detected",
  sourced_review_decided: "Recruiter decision", sourced_candidate_created: "Candidate created",
};
export const STATUS_LABELS: Record<string, string> = { open: "Open", in_progress: "In progress", resolved: "Resolved" };
export const REQUEST_STATUS: Record<string, string> = {
  draft: "Draft", submitted: "Submitted", open: "Open", matching: "Matching", closed: "Closed", cancelled: "Cancelled",
  needs_info: "Needs info", pending_approval: "Pending approval", shared: "Shared",
};

export function labelAudit(action: string): string {
  return AUDIT_ACTION[action] ?? action.replaceAll("_", " ");
}
```

- [ ] **Step 8: Additive change to `web/lib/api.ts`**

Replace the error branch in `request<T>` and the one in `downloadHiringExport` with `throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : \`Request failed (${response.status})\`);` and add `import { ApiError } from "./errors";`. Add these exports (nothing existing is removed or renamed):

```ts
export type RequestNote = { id: string; body: string; kind: string; author_user_id: string; created_at: string | null };
export type RequestAttachment = { id: string; filename: string; media_type: string; byte_size: number };
export type RequestSummary = { id: string; company: string; job_title: string; status: string; received_at: string };

export function listHiringRequests() {
  return request<{ requests: RequestSummary[] }>("/hiring-requests");
}
export function addRequestNote(id: string, kind: "notes" | "updates" | "next-steps", body: string) {
  return request<{ id: string; kind: string }>(`/hiring-requests/${id}/${kind}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body }),
  });
}
export function addRequestAttachment(id: string, file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<{ id: string; filename: string }>(`/hiring-requests/${id}/attachments`, { method: "POST", body });
}
export function getDocumentText(id: string) {
  return request<{ id: string; text: string }>(`/documents/${id}/text`);
}
export function getExcelImport(id: string) {
  return request<ExcelImportReport>(`/excel/candidates/${id}`);
}
```

Extend types additively: `HiringRequestDetail` gets `received_at: string; owner_user_id: string | null; notes: RequestNote[]; updates: RequestNote[]; next_steps: RequestNote[]; attachments: RequestAttachment[]`; `Dashboard` gets `viewer_id: string`; `CandidateMatch` gets `request_id?: string; requirement_met_ratio?: number | null; processing_version?: number | null`; `SearchHit` gets `confirmed_profile?: boolean`; `ProblemReport` gets `created_at?: string | null`; `ActivityEvent` unchanged.

- [ ] **Step 9: Run everything**

Run: `npm test && npx tsc --noEmit`
Expected: all suites pass; typecheck clean (existing pages still compile because changes are additive).

- [ ] **Step 10: Commit**

```bash
git add web/lib
git commit -m "feat(web): pure logic libs with tests and additive api client"
```

---

### Task 3: Design tokens, base styles and core primitives

**Files:**
- Modify: `web/app/globals.css`
- Create: `web/components/ui/{button,tag,chip,panel,field,skeleton,states,toast}.tsx`
- Create: `web/scripts/contrast.mjs`

**Interfaces (produced):**

```ts
// button.tsx
export function Button(props: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet" | "danger"; busy?: boolean }): JSX.Element
export function LinkButton(props: React.AnchorHTMLAttributes<HTMLAnchorElement> & { variant?: "primary" | "secondary" | "quiet" }): JSX.Element
// tag.tsx
export type Tone = "proposed" | "decided" | "ok" | "warn" | "bad" | "unknown" | "neutral";
export function Tag(props: { tone: Tone; children: React.ReactNode; title?: string }): JSX.Element
// chip.tsx
export function Chip(props: { children: React.ReactNode; onRemove?: () => void; removeLabel?: string; hue?: "rel" | "req" | "match" | "share" }): JSX.Element
// panel.tsx
export function Panel(props: { children: React.ReactNode; className?: string; as?: "div" | "section" | "article" }): JSX.Element
export function PanelRow(props: { children: React.ReactNode; hue?: "rel" | "req" | "match" | "share"; className?: string }): JSX.Element
export function SectionLabel(props: { children: React.ReactNode; id?: string }): JSX.Element
export function PageHeader(props: { title: string; sub?: React.ReactNode; hue?: "rel" | "req" | "match" | "share" | "candidate"; actions?: React.ReactNode }): JSX.Element
// field.tsx
export function Field(props: { label: string; hint?: string; error?: string | null; children: (ids: { id: string; describedBy?: string }) => React.ReactNode }): JSX.Element
export const inputClass: string
// skeleton.tsx
export function Skeleton(props: { lines?: number; className?: string }): JSX.Element
// states.tsx
export function EmptyState(props: { title: string; body?: string; action?: React.ReactNode }): JSX.Element
export function ErrorState(props: { error: unknown; onRetry?: () => void }): JSX.Element
// toast.tsx
export function ToastProvider(props: { children: React.ReactNode }): JSX.Element
export function useToast(): { notify: (message: string, tone?: "ok" | "bad") => void }
```

- [ ] **Step 1: Write the tokens**

Replace `web/app/globals.css` with Tailwind import, `:root` variables from Global Constraints plus the darker text variants (`--prop-ink #8F5400`, `--ok-ink #14704A`, `--bad-ink #A83324`, `--human-ink #0A5EA8`, `--t-rel-ink #5443C9`, `--t-req-ink #00738C`, `--t-match-ink #17795A`, `--t-share-ink #B02F5E`), an `@theme inline` mapping every variable to a Tailwind colour name (`--color-canvas: var(--canvas)` etc.), base styles (system font stack, `font-variant-numeric: tabular-nums` on `body`, `:focus-visible { outline: 2px solid var(--human); outline-offset: 2px }`, `@media (prefers-reduced-motion: reduce)` disabling transitions and animations, `.sr-only` via Tailwind), a `.hatch` class (135° repeating stripes for Unknown), and a `.proposal` class (1px dashed `--prop` border on `--prop-bg`).

- [ ] **Step 2: Implement primitives**

Each primitive is a small file, native elements only. Requirements per file:
- `Button`: `min-h-11` on touch (`sm:min-h-8`), variants map to `--human` filled / bordered / borderless / `--bad` outline; `busy` sets `aria-busy` and `disabled`, shows "…" text via children unchanged; never removes the focus ring.
- `Tag`: uppercase 11 px bold. `proposed` = dashed `--prop` border, `--prop-bg` fill, `--prop-ink` text. `decided` = `--human` fill, white text. `ok`/`bad` = filled with `--ok-ink`/`--bad-ink` and white text. `warn` = amber outline. `unknown` = `.hatch` with `--mut` text. `neutral` = bordered. Always carries visible text (never colour alone).
- `Chip`: bordered pill; with `onRemove`, renders a real `<button aria-label={removeLabel}>×</button>`.
- `Panel`/`PanelRow`: white, 1px `--rule` border, radius 4 px; `PanelRow` hue draws a 5 px left stripe using `--t-*`.
- `PageHeader`: one `<h1>`, a 5 px top strip in the hue (gradient of the hue to `--human`), optional actions aligned right, wraps on mobile.
- `Field`: `useId`, `<label htmlFor>`, hint and error linked via `aria-describedby`, error with `role="alert"`.
- `Skeleton`: `aria-hidden` bars with a pulse that is disabled under reduced motion; the parent sets `aria-busy`.
- `ErrorState`: calls `describeError`; renders title, body, a Retry button when `onRetry` is given; `role="alert"`.
- `EmptyState`: title, one sentence of why, optional action.
- `Toast`: a visually and semantically live region (`role="status" aria-live="polite"`); auto-dismisses after 6 s; the message is also kept in the page's inline notice by callers when the result matters.

- [ ] **Step 3: Contrast script**

`web/scripts/contrast.mjs` parses `globals.css` for the listed pairs and exits non-zero if any fails. Pairs to check (text on background, minimum ratio): `ink/canvas 4.5`, `ink/panel 4.5`, `mut/canvas 4.5`, `mut/panel 4.5`, `human-ink/panel 4.5`, `human-ink/human-bg 4.5`, `prop-ink/prop-bg 4.5`, `ok-ink/panel 4.5`, `bad-ink/panel 4.5`, `ev/panel 4.5`, `white/human 4.5`, `white/ok-ink 4.5`, `white/bad-ink 4.5`, `nav-ink/nav 4.5`, `white/nav 4.5`, and `t-*-ink/panel 4.5` for the four hues. Implementation: hex → relative luminance (WCAG 2.1 formula) → ratio.

- [ ] **Step 4: Run and adjust**

Run: `node web/scripts/contrast.mjs`
Expected: all listed pairs `PASS`. If a pair fails, darken the `-ink` variant (never the border/fill hue) until it passes and re-run.

- [ ] **Step 5: Typecheck and commit**

Run: `npx tsc --noEmit`
Expected: clean.

```bash
git add web/app/globals.css web/components/ui web/scripts
git commit -m "feat(web): design tokens and core ui primitives"
```

---

### Task 4: Overlay and structure primitives

**Files:**
- Create: `web/components/ui/{dialog,menu,tabs,table,stepper,slide-over}.tsx`

**Interfaces (produced):**

```ts
export function ConfirmDialog(props: { open: boolean; title: string; body: React.ReactNode; confirmLabel: string; tone?: "primary" | "danger"; busy?: boolean; onConfirm: () => void; onCancel: () => void }): JSX.Element
export function Menu(props: { label: string; children: React.ReactNode; align?: "left" | "right"; tone?: "dark" | "light" }): JSX.Element
export function MenuItem(props: { href?: string; onSelect?: () => void; children: React.ReactNode }): JSX.Element
export function Tabs(props: { tabs: { id: string; label: string }[]; value: string; onChange: (id: string) => void; label: string }): JSX.Element
export function ResponsiveTable<T>(props: { rows: T[]; rowKey: (row: T) => string; columns: { header: string; cell: (row: T) => React.ReactNode; primary?: boolean }[]; caption: string }): JSX.Element
export function Stepper(props: { steps: Step[] }): JSX.Element
export function SlideOver(props: { open: boolean; title: string; onClose: () => void; children: React.ReactNode }): JSX.Element
```

- [ ] **Step 1: Implement**

- `ConfirmDialog` uses native `<dialog>`: `useEffect` calls `showModal()` when `open` becomes true and `close()` when false; `onCancel`/Escape/backdrop click call `onCancel`; focus moves to the cancel button first for `danger`, confirm button for `primary`; body text names the object and consequence (callers supply it); confirm button uses `busy`.
- `SlideOver` is the same `<dialog>` positioned to the right (full width under 640 px) with a close button and `aria-labelledby`.
- `Menu` uses a `<button aria-haspopup="menu" aria-expanded>` and a popover list with `role="menu"`/`menuitem`; arrow keys move focus, Escape closes and returns focus, outside click closes.
- `Tabs` implements the WAI-ARIA tab pattern with roving `tabindex` and arrow keys.
- `ResponsiveTable` renders a real `<table>` with `<caption class="sr-only">` from 640 px up and stacked `<dl>` cards below it (the `primary` column becomes the card heading).
- `Stepper` renders an ordered list; each step shows a number, label, detail and state text ("Done", "Current", "Locked") plus `aria-current="step"` on the current one; horizontal from 768 px, vertical below.

- [ ] **Step 2: Verify by typecheck and a dev-server smoke page**

Run: `npx tsc --noEmit`, then start `npm run dev` and create a throwaway `app/_kit/page.tsx` (deleted before commit) that renders every primitive from Tasks 3–4 in all states.
Expected: no type errors; keyboard: Tab reaches every control, Escape closes dialogs and menus, focus returns to the trigger.

- [ ] **Step 3: Commit**

```bash
git add web/components/ui
git commit -m "feat(web): dialog, menu, tabs, responsive table, stepper, slide-over"
```

---

### Task 5: App shell and redirects

**Files:**
- Create: `web/components/shell/{top-bar,bottom-tabs,add-menu,desk-menu}.tsx`
- Modify: `web/app/layout.tsx`, delete `web/app/nav.tsx`
- Replace with redirects: `web/app/search/page.tsx`, `web/app/queue/page.tsx`, `web/app/dashboard/page.tsx` (delete their `form.tsx`)

**Interfaces:**
- Consumes: `Menu`, `MenuItem` (Task 4).
- Produces: shell with nav items `Inbox /`, `Requests /hiring`, `Candidates /candidates`, `Intake /intake`; `Add` menu (Upload a CV → `/intake`, Source a candidate → `/source`, Import an Excel list → `/data`, New hiring request → `/hiring?new=1`); `Desk` menu (Problem reports → `/reports`, Hiring-activity export → `/data#export`, Merge two profiles → `/merge`, Install app).

- [ ] **Step 1: Build the shell**

`TopBar` is a client component using `usePathname()` to set `aria-current="page"` and the active underline (`--t-req` colour). It contains a brand link, four `<nav aria-label="Primary">` links, a "Find a candidate" form (`method="get" action="/candidates"`, input name `q`), the Add and Desk menus. The Inbox link shows the count from a small `useInboxCount()` hook that calls `getDashboard()` once and reads `counts.relationship_reviews + requirements_awaiting_approval + matches_awaiting_review + shares_awaiting_approval`; if the call fails it shows no badge. `/` focuses the find input when no input is focused. `BottomTabs` renders the four links fixed at the bottom under 768 px (`md:hidden`), with 44 px targets and the same active state; the page body gets bottom padding to clear it.

- [ ] **Step 2: Layout**

`layout.tsx`: `<body class="bg-canvas text-ink">`, a first-in-DOM skip link ("Skip to main content") targeting `<main id="main">`, `TopBar`, `{children}` inside `<main id="main" class="mx-auto max-w-[1200px] px-4 py-5 sm:px-6 pb-24 md:pb-8">`, `BottomTabs`, `ToastProvider`. Metadata title "Cadence HR". Individual pages no longer wrap themselves in `<main>`.

- [ ] **Step 3: Redirect pages**

Each of `/search`, `/queue`, `/dashboard` is a server component using `redirect()` from `next/navigation`. `/search` forwards `searchParams` to `/candidates`; the others go to `/`.

- [ ] **Step 4: Verify**

Run: `npx tsc --noEmit && npm run build`
Expected: builds. Manual (dev server): each nav item highlights on its route; `/search?skill=sql` lands on `/candidates?skill=sql`; below 768 px the bottom bar shows and the top links hide.

- [ ] **Step 5: Commit**

```bash
git add web/components/shell web/app
git commit -m "feat(web): app shell, navigation and route redirects"
```

---

### Task 6: Domain components

**Files:**
- Create: `web/components/domain/{decision-case,signal-list,evidence-quote,audit-line,relationship-review,requirement-matrix,candidate-header}.tsx`

**Interfaces (produced):**

```ts
export function DecisionCase(props: {
  found: React.ReactNode; evidence?: React.ReactNode; proposed?: React.ReactNode;
  decision: React.ReactNode; record?: React.ReactNode; hue?: "rel" | "req" | "match" | "share"; }): JSX.Element
export function SignalList(props: { evidence: EvidenceItem[] }): JSX.Element
export function EvidenceQuote(props: { quote: string; page?: number | null; verified?: boolean; source?: string; highlight?: string }): JSX.Element
export function AuditLine(props: { action: string; actorKind: string; at: string }): JSX.Element
export function RelationshipReview(props: {
  review: Review; targetId: string; onTarget: (id: string) => void; busy: boolean; onDecide: (action: string) => void; candidateHref?: (id: string) => string; }): JSX.Element
export function RequirementMatrix(props: { requirements: MatchRequirement[] }): JSX.Element
export function CandidateHeader(props: { profile: CandidateProfile; onShowText?: () => void }): JSX.Element
```

- [ ] **Step 1: Implement**

- `DecisionCase` lays out the five stages as labelled sections in order (Found, Evidence, Proposed, Decision, Record), omitting empty optional ones; `Proposed` content is wrapped in the `.proposal` block with a `Tag tone="proposed"`; `Decision` uses `Tag tone="decided"` once decided (callers pass it).
- `SignalList` lists signals from `EvidenceItem[]` as `label — state` using `SIGNAL_LABELS` / `SIGNAL_STATE_LABELS`; `recorded` shows the value as a whole percent; states use text and an icon glyph (✓, –, ?), not colour alone.
- `EvidenceQuote` renders a `<blockquote>` with the `--ev` left bar, optional `<mark>` highlighting of `highlight` terms (case-insensitive, escaped), and a monospace source line: `CV p.{page} ✓ verified` or `quote not verified` (warn tone) or the provided `source`.
- `RelationshipReview` is the single replacement for the three copies: found sentence built from `likely_relationship` (`RELATIONSHIP_LABELS`), `SignalList`, the proposal block "Proposed: {ACTION_LABELS[recommended_action]}" plus "Signal strength {confidence} / 100, weighted from the signals above. Not a model's confidence." (only when `confidence !== null`); when `recommended_action` is null it says "Below the high-confidence setting. Choose an action." When `pending && candidates.length > 1` a labelled `<select>` picks the existing candidate (links to profiles open in a new tab so the task is not lost). Action buttons come from `offered_actions`, the recommended one is primary; clicking calls `onDecide` (callers wrap in the same behaviour as today). When decided it shows a `Tag tone="decided"` "Decided" with the outcome label.
- `RequirementMatrix` renders a `ResponsiveTable` with columns Requirement (text with `shownText` rule for `label === "experience"` and a strength tag), Verdict (`VERDICT` tag), Evidence (`EvidenceQuote` when `evidence` present, else a hatched "No evidence found" note; for a preferred requirement with `unknown` add "Not treated as a gap").
- `CandidateHeader` shows name (`break-words`), years, latest role (first experience with a title), contact chips with a copy button (`navigator.clipboard`, toast on success), current document line, source line, and the actions (Show CV text if provided, Merge link `/merge?left={id}`).

- [ ] **Step 2: Verify**

Run: `npx tsc --noEmit`
Expected: clean. Add the components to the throwaway kit page and check: a 60-character candidate name wraps, keyboard focus order is Found → Decision, screen-reader text reads "Proposed" before the proposal.

- [ ] **Step 3: Commit**

```bash
git add web/components/domain
git commit -m "feat(web): decision case, relationship review, evidence and matrix components"
```

---

### Task 7: Inbox

**Files:**
- Create: `web/app/inbox/{inbox.tsx,row.tsx}`
- Modify: `web/app/page.tsx`

**Interfaces:**
- Consumes: `getWorkQueue`, `getDashboard`, `getReview`, `listHiringMatches`, `groupQueue`, `QUEUE_TYPE`, `relativeAge`, `PageHeader`, `Panel`, `PanelRow`, `Chip`, `Skeleton`, `EmptyState`, `ErrorState`, `RelationshipReview`-like read-only view, `AuditLine`.
- Produces: default route `/`.

- [ ] **Step 1: Redirect gate**

`app/page.tsx` is a server component: `export default async function Page({ searchParams })`. If `searchParams.document` is a string, `redirect('/intake?document=' + encodeURIComponent(value))`; otherwise render `<Inbox />`.

- [ ] **Step 2: Inbox component**

Client component. `useAsync` loads `getWorkQueue()` and `getDashboard()` in parallel; either failing shows `ErrorState` with retry (a 403 shows the forbidden wording). Header: "Needs your decision" with sub "Cadence proposes. Nothing changes until you decide. Opening an item does not change it." Filter chips (All plus each queue type with its group count, `aria-pressed`, keyed in the URL as `?type=`). Rows come from `groupQueue(items)`. Each `InboxRow`: `PanelRow` with the hue stripe, small mono label `{QUEUE_TYPE.label} · {count > 1 ? count : ""} · {relativeAge}`, subject as `<h3>`, the fixed `why` line, and a primary `LinkButton` to `href` (label per type: "Review and decide", "Review {n} requirements", "Review matches", "Review share"). Matches show the candidate names when count ≤ 3. Relationship rows have a "Preview evidence" `<button aria-expanded>` that on first open loads `getReview(documentId)` (document id from `href` `?document=`; rows whose href is `/data` have no preview) and shows `SignalList`, the proposed action in the proposal block and the signal strength; loading is a `Skeleton`, failure an inline `ErrorState`. Match rows expand to the candidates from `listHiringMatches(requestId)` with dispositions. Side column: "Requests in progress" from `dashboard.active_hiring_requests` (subject, status, date, link), "Also waiting" showing `open_problem_reports` count linking to `/reports` (hidden at 0), "Recently recorded" from `recent_activity` using `AuditLine`. When `items.length >= 50` show "Showing the 50 most recent items (the server caps this list)." Empty state: title "Nothing needs a decision", body "New CVs, requests and matches appear here when they need you."

- [ ] **Step 3: Verify**

Run: `npx tsc --noEmit && npm run build`, then with the stack running (Task 14 has the commands) load `/`.
Expected: rows match the counts on the chips; `/?document=X` redirects to `/intake?document=X`; a stopped API shows the network error state with Retry; below 768 px the side column stacks below the list.

- [ ] **Step 4: Commit**

```bash
git add web/app/page.tsx web/app/inbox
git commit -m "feat(web): inbox replaces dashboard and work queue"
```

---

### Task 8: Intake

**Files:**
- Create: `web/app/intake/{page.tsx,intake.tsx,file-list.tsx,document-detail.tsx}`
- Delete: `web/app/intake.tsx` (moved and split)

**Interfaces:**
- Consumes: `listDocuments`, `getDocument`, `getActivity`, `getReview`, `getCandidate`, `decideReview`, `uploadDocument`, `RelationshipReview`, `DOCUMENT_STATUS`, `labelAudit`, `ConfirmDialog`.

- [ ] **Step 1: Move behaviour unchanged, then restyle**

Port the state machine from the old `intake.tsx` exactly: `PROCESSING` set polling at 1500 ms, `REVIEW_OUTCOMES`, `?document=` selection on mount, the `needsTarget` rule (`action !== "create_separate_candidate" && review.candidates.length > 1` requires a chosen target), the "already in the hub" notice when `created` is false, `refreshList` after decisions. Split into: `intake.tsx` (state and effects), `file-list.tsx` (list with status tags from `DOCUMENT_STATUS`, filename truncated with `title` and `break-all` in the detail heading, selected item `aria-current`), `document-detail.tsx` (status card with the `note` text and `error_code` as "Problem code", extracted profile preview (name, contacts, latest roles, skills) with a link "Open full profile" to `/candidates/{id}` (a normal link, not a prefetch: set `prefetch={false}`), `RelationshipReview`, audit list via `AuditLine` using `event.detail.human_action` and `recommended_action` as today).
- Upload is a `FileDrop`-style label (keyboard focusable, `accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"`) with the accepted types printed.
- Two panes from 1024 px; below that the list becomes a `<select>`-like disclosure above the detail.
- Relationship decisions stay one click, as today: they are recorded, reversible only by a new review, and shown at once as an audit line plus a toast. Confirm dialogs are reserved for merge, share approve/send and reject (spec §4, States).

- [ ] **Step 2: Verify**

Run: `npx tsc --noEmit && npm run build`. With the stack: upload a PDF, watch status go Queued → Reading → Extracted or Needs a decision; upload the same bytes and see the notice; make a decision and see the audit line and toast; a `needs_ocr` file shows its explanation; a 120-character filename does not overflow at 390 px.

- [ ] **Step 3: Commit**

```bash
git add web/app/intake web/app/intake.tsx
git commit -m "feat(web): intake screen on shared components"
```

---

### Task 9: Candidate profile

**Files:**
- Modify: `web/app/candidates/[id]/view.tsx`
- Create: `web/app/candidates/[id]/{facts.tsx,record.tsx}`

**Interfaces:**
- Consumes: `getCandidate`, `getDocumentText`, `splitEvidence`, `CandidateHeader`, `EvidenceQuote`, `Tag`, `Tabs`, `AuditLine`, `shortDate`, `ErrorState`, `Skeleton`.

- [ ] **Step 1: Layout**

`view.tsx` loads once with `useAsync(() => getCandidate(id), [id])`. Header via `CandidateHeader`. From 1024 px: main column `facts.tsx` (Summary, Experience, Education, Skills, Certificates, Qualifications, "Other extracted evidence") and side column `record.tsx` (CV versions, Applications, Record). Below 1024 px a sticky anchor chip row (`Profile`, `Evidence`, `CVs`, `Record`) scrolls to sections (`scroll-margin-top`).
- Each Experience/Education/Certificate item renders the fact and, from `splitEvidence(profile).find(field, value)`, an `EvidenceQuote` collapsed in a `<details>` labelled "Source"; if no evidence exists the source line reads "No source quote stored".
- Skills are chips; a chip with evidence is a `<button>` that opens its quote inline (a `<details>` under the list); others are plain.
- Empty sections say "Not extracted" (hatched tag) rather than "None stored". Summary heading carries "(built from stored fields; no model wrote this)" when `profile.summary` is null and `narrative` is derived.
- CV versions: current = `Tag tone="ok"` "Current", others = `Tag tone="unknown"` "Superseded", sorted as the API returns; each shows filename (mono, wraps), status, `shortDate`. Header line: "Replaces {n} earlier CV(s)" from superseded count.
- "Show CV text" button: first click opens a `ConfirmDialog` ("This view is recorded in the audit trail.") then calls `getDocumentText(currentDocumentId)` and shows the text in a `SlideOver` in a `<pre class="whitespace-pre-wrap">`; failure shows `ErrorState`. Never called before the click.
- Footer line: "This profile is built from CVs and cannot be edited here."
- 403 (wrong role) and 404 render `ErrorState` with the mapped wording.

- [ ] **Step 2: Verify**

Run: `npx tsc --noEmit && npm run build`. With the stack: open a profile with evidence (upload with the section parser on) and one without; confirm quotes attach; confirm no network call to `/documents/{id}/text` until the dialog is confirmed (DevTools Network); a 90-character name wraps at 390 px.

- [ ] **Step 3: Commit**

```bash
git add "web/app/candidates/[id]"
git commit -m "feat(web): candidate profile with inline evidence and record"
```

---

### Task 10: Candidate search

**Files:**
- Create: `web/app/candidates/{page.tsx,search.tsx,result-group.tsx}`
- Delete: `web/app/search/form.tsx`

**Interfaces:**
- Consumes: `searchCandidates`, `FILTERS`, `parseSearch`, `toQueryString`, `hasCriteria`, `groupHits`, `SEARCH_REASON`, `Chip`, `Menu`, `EvidenceQuote`, `EmptyState`, `ErrorState`.

- [ ] **Step 1: Implement**

`page.tsx` wraps `<Suspense>` around the client `Search` (needed for `useSearchParams`). `Search`: reads `parseSearch(useSearchParams())`; a main text input "Words in the CV" (`name="q"`), an "Add filter" `Menu` listing the `FILTERS` not already active, active filters as removable `Chip`s (each with an inline labelled input to edit its value, `Enter` applies), a Search button. Submit does `router.replace('/candidates?' + toQueryString(values))` and then runs `searchCandidates(values)`; the same runs on first load if the URL has criteria. Notes under the controls: "Filters combine with AND. Only confirmed profiles are searched. Nationality searches words already written in the CV."
- `hasCriteria` false → `EmptyState` "Search the CVs" with three example queries as links; results empty with criteria → "No matches" and a hint to remove the last filter.
- Results: header "N candidates · M passages · ordered by relevance (no score shown)". `ResultGroup` per `CandidateGroup`: name (`break-words`), Open profile `LinkButton` (`prefetch={false}`), tags "Exact" for each exact reason (`SEARCH_REASON`) and "Approximate" hatched tags for approximate ones, then up to 3 hits each with `EvidenceQuote` (`highlight` = the `q` terms and the skill value; source label "Passage from a CV" if `chunk_id` else "Profile fields"; `confirmed_profile === false` adds "Profile not confirmed"), "Show N more passages" if more. `approximateOnly` groups add the line "Only approximate wording matched. Read the CV before relying on this."
- `aria-live="polite"` region announces the result count; busy state disables the button and marks results `aria-busy`.

- [ ] **Step 2: Verify**

Run: `npx tsc --noEmit && npm run build`. Manual: type a query, filters appear as chips and in the URL; reload restores them; empty submit shows the prompt; a candidate with several passages appears once.

- [ ] **Step 3: Commit**

```bash
git add web/app/candidates web/app/search
git commit -m "feat(web): candidate search with url state and grouped evidence"
```

---

### Task 11: Hiring requests (index, new, workspace)

**Files:**
- Modify: `web/app/hiring/page.tsx`; delete `web/app/hiring/desk.tsx`
- Create: `web/app/hiring/{index-view,new-request,workspace,requirements,matches,share-panel,record}.tsx`

**Interfaces:**
- Consumes: every hiring function in `lib/api.ts` (existing plus `listHiringRequests`, `addRequestNote`, `addRequestAttachment`), `getDashboard` (for `viewer_id`), `deriveLifecycle`, `Stepper`, `RequirementMatrix`, `ConfirmDialog`, `REQUEST_STATUS`, `DISPOSITION`.

- [ ] **Step 1: Routing and index**

`page.tsx` (client) reads `request`, `candidate`, `new` from `useSearchParams` inside `<Suspense>`. `?request=` → `Workspace`; `?new=1` → `NewRequest`; otherwise `IndexView`. `IndexView`: `listHiringRequests()` table (`ResponsiveTable`: Company, Job title, Status tag, Received) with each row linking to `/hiring?request={id}`, a "New request" button, empty and error states, and the note "Showing the 50 most recent requests." `NewRequest`: the three fields plus a received-date input defaulting to today (submits `received_at` as ISO of that date at 00:00 UTC); **no demo pre-fill text**; on success navigates to the workspace.

- [ ] **Step 2: Workspace state**

`workspace.tsx` loads `getHiringRequest(id)`, `listHiringMatches(id)` and `getDashboard()` (for `viewer_id`) with `useAsync`. Header: company · title, received date, owner ("you" if `owner_user_id === viewer_id`, "another recruiter" otherwise, omitted if null), status tag from `REQUEST_STATUS`. Shortlist hydration: after matches load, for the first 20 matches with disposition `recommended` or `needs_review` call `getSharePreview(id, candidate_id)` sequentially with a concurrency of 4; a 200 means shortlisted (and gives `approved` and `sharing`), a `409 not_shortlisted` means not, any other error marks that candidate "unknown"; if any probe is unknown `shortlisted` in `deriveLifecycle` is `null`. Stepper from `deriveLifecycle({requirements, matchCount: matches.length, shortlisted, sharesApproved, shared: detail.candidates_shared})`.

- [ ] **Step 3: Requirements panel (`requirements.tsx`)**

Rows editable (text input, strength select `mandatory|preferred`, label select `skill|experience|education|certification|other`), status tag, source quote with `EvidenceQuote source="Job description"`, per-row Save (`editHiringRequirement`) with the notice "Edit saved. Approve the requirement again before it is used." Buttons: "Extract requirements" (`extractHiringRequirements`, only when none exist or explicitly re-run behind a `ConfirmDialog` "This replaces the proposed list"), "Approve requirements" (`approveHiringRequirements`, `ConfirmDialog` naming the count). `RequirementRow` local state resets when the server row changes (`key={item.id + item.review_status}`).

- [ ] **Step 4: Matches panel (`matches.tsx`)**

"Run matching" performs `openHiringRequest` then `runHiringMatch` then reload (same order as today), disabled with an explanation until at least one requirement is approved. Candidates sorted: recommended, needs_review, shortlisted, excluded, rejected. Each candidate card: name link (`/candidates/{candidate_id}`, `prefetch={false}`), disposition tag, "{met} of {total} requirements met" computed from `match.requirements`, `RequirementMatrix`, strengths and gaps lists, a proposal block "Proposed: {disposition label}. The matcher never shortlists." and actions: "Add to shortlist" (`shortlistMatch`, enabled for `recommended|needs_review`, idempotent), "Reject" (`ConfirmDialog` "Reject {name} for {job title}? This is recorded."), "Share…" when shortlisted. After each action update local state from the response and show the toast and an inline decided tag ("Shortlisted", "Rejected").

- [ ] **Step 5: Share panel (`share-panel.tsx`)**

Opens as a `SlideOver` from "Share…" or when `?candidate=` is present. Loads `getSharePreview`. Sections: "What leaves Cadence" (company, recipient, candidate public name, role, title, years, skills) and "Not included: email, phone, the CV file." Two separate buttons: "Approve share" (`ConfirmDialog`: "Approve sharing {candidate} with {company} ({recipient})?") then, once `approved`, "Send email" (`ConfirmDialog`: "Send now to {recipient}? This cannot be undone."). Sent state shows status, recipient, sent time (`shortDate` plus time), sender, destination as returned, audit action or "missing". `502 mail_delivery_failed` shows the mapped message and keeps Send enabled.

- [ ] **Step 6: Request record (`record.tsx`)**

Description; three sections Notes, Updates, Next steps each listing entries (author: "You" if `author_user_id === viewer_id` else "Another recruiter", `shortDate`) and an "Add" inline composer (`addRequestNote(id, "notes"|"updates"|"next-steps", body)`, `Field` with error, reload on success); Files listing filename (mono, wraps), type, size (KB) with an "Upload file" input (`addRequestAttachment`) and the line "Files are listed only; downloads are not available." Empty sections say "None yet".

- [ ] **Step 7: Verify**

Run: `npx tsc --noEmit && npm run build`. With the stack: create a request, extract, edit, approve, run matching, shortlist, reject, open share (`?request=…&candidate=…` deep link from the Inbox works), approve, send; add a note, update, next step and a file; reload mid-way and confirm the stepper and shortlist tags are restored; try Run matching with nothing approved and read the explanation.

- [ ] **Step 8: Commit**

```bash
git add web/app/hiring
git commit -m "feat(web): hiring requests index and lifecycle workspace"
```

---

### Task 12: Source, Excel, Merge, Reports

**Files:**
- Modify: `web/app/source/form.tsx`, `web/app/data/form.tsx`, `web/app/merge/form.tsx`, `web/app/reports/form.tsx`

**Interfaces:**
- Consumes: `Field`, `inputClass`, `Button`, `RelationshipReview`, `ResponsiveTable`, `ConfirmDialog`, `Tag`, `PageHeader`, `labels.ts`.

- [ ] **Step 1: Source**

Keep fields, polling (800 ms start, 1000 ms repeat while `received|extracting`) and API calls unchanged. Replace the local review copy with `RelationshipReview`; add validation (name and CV required, message via `Field` error); show source type as a tag and keep "Source kept on the candidate record". Audit list via `AuditLine` with `EVENT` labels from `labels.ts`.

- [ ] **Step 2: Excel**

Keep import and export. Stats as a compact summary bar; per-row results in `ResponsiveTable` (Row, Outcome tag, Detail); inline `RelationshipReview` for rows with `review_id` (loads `getReviewRecord`, decides via `decideReview(reviewId, action)` with no candidate id as today). Export: validate `start <= end` before calling; id `export` for the `#export` anchor; success shows the toast. Import copy: ".xlsx with name, email and phone columns. Cell text is not shown back here."

- [ ] **Step 3: Merge**

Keep `previewMerge` and `confirmMerge`. Add: read `left` and `right` from the query string; each side gets a picker: a text input that searches by name with `searchCandidates({ name })` (debounced 300 ms) and shows up to 5 results by name (no ids), or accepts a pasted id; selecting sets the id and shows the name. Preview shows both profiles side by side with a "Kept" tag (survivor) and "Joined into the kept profile" tag; the confirm button opens a `ConfirmDialog` ("Merge {absorbed} into {survivor}? Documents and applications stay on record. This cannot be undone here."). Refuse identical ids client-side with a `Field` error.

- [ ] **Step 4: Reports**

Keep create and list. Restyle with `Field`s; status via `Tag`; show `created_at` when present and the engineer note in a labelled block; validation on title and description. Copy: "Describe the problem in your own words. Context is limited to an error code, a route and an action."

- [ ] **Step 5: Verify and commit**

Run: `npx tsc --noEmit && npm run build`. Manual: each form shows inline errors and success states; Excel with a duplicate row opens the inline review; merge picker finds by name.

```bash
git add web/app/source web/app/data web/app/merge web/app/reports
git commit -m "feat(web): restyle source, excel, merge and reports on shared components"
```

---

### Task 13: Installable PWA

**Files:**
- Create: `web/app/manifest.ts`, `web/app/offline/page.tsx`, `web/public/sw.js`, `web/public/icons/{icon-192.png,icon-512.png,maskable-512.png,apple-touch-icon.png}`, `web/components/shell/{sw-register,install-banner}.tsx`
- Modify: `web/app/layout.tsx`, `web/components/shell/desk-menu.tsx`

**Interfaces:**
- Produces: `/manifest.webmanifest`, `/sw.js`, `/offline`; `<SwRegister />`; `<InstallBanner />`; a Desk-menu "Install app" item wired through a shared `useInstallPrompt()` hook exported from `install-banner.tsx`.

- [ ] **Step 1: Icons**

Generate four PNG icons from a simple mark (the brand square gradient on `--nav`) with a small Node script `web/scripts/make-icons.mjs` using only built-in modules (write raw PNGs via zlib) or, if that is not practical, commit hand-made PNGs. The maskable icon keeps the mark inside the 80 % safe zone.

- [ ] **Step 2: Manifest and metadata**

`manifest.ts` returns `MetadataRoute.Manifest`: `name "Cadence HR"`, `short_name "Cadence"`, `description "Internal HR operations desk."`, `start_url "/"`, `scope "/"`, `display "standalone"`, `theme_color "#0B3954"`, `background_color "#EEF5F8"`, `lang "en"`, icons 192, 512 (`any`) and maskable 512. In `layout.tsx` add `metadata.appleWebApp = { capable: true, title: "Cadence", statusBarStyle: "default" }`, `metadata.icons = { apple: "/icons/apple-touch-icon.png" }` and `export const viewport = { themeColor: "#0B3954" }`.

- [ ] **Step 3: Service worker**

`public/sw.js`:

```js
const STATIC = "cadence-static-v1";
const OFFLINE_URL = "/offline";
const ASSETS = ["/icons/icon-192.png", "/icons/icon-512.png", OFFLINE_URL];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(STATIC).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== STATIC).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // API is another origin: never touched
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.open(STATIC).then(async (cache) => {
        const hit = await cache.match(request);
        if (hit) return hit;
        const response = await fetch(request);
        if (response.ok) cache.put(request, response.clone());
        return response;
      }),
    );
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
  }
});
```

Pages and RSC payloads are never cached; only hashed static assets and the listed icons and offline page are. `offline/page.tsx` is a static page with the text "You are offline. Cadence needs a connection to show candidate information." and a Retry link.

- [ ] **Step 4: Registration and banner**

`SwRegister` (client, rendered in the layout): in `useEffect`, only when `process.env.NODE_ENV === "production"` and `"serviceWorker" in navigator`, call `navigator.serviceWorker.register("/sw.js")`. `useInstallPrompt()` captures `beforeinstallprompt` (`preventDefault`, store), exposes `{ canInstall, isIos, install() }` and clears on `appinstalled`. `InstallBanner`: shows after a 15 s delay only if not standalone (`display-mode: standalone` or `navigator.standalone`), viewport ≤ 1024 px, not dismissed within 30 days (`localStorage` key `cadence.pwa.dismissed.v1`, every read and write in try/catch), and either a captured prompt (Install button) or iOS Safari (text "Tap Share, then Add to Home Screen"). Dismiss and "Not now" store the timestamp. `role="region" aria-label="Install Cadence"`, positioned above the bottom tab bar, 44 px targets. The Desk menu shows "Install app" when `canInstall` or `isIos`, calling `install()` or opening a small dialog with the iOS steps.

- [ ] **Step 5: Verify**

Run: `npm run build && npm run start` (port 3000).
Expected: `/manifest.webmanifest` and `/sw.js` respond 200; DevTools → Application shows the manifest with no installability errors and the worker active; there is no worker under `npm run dev`; Network with the API up shows no API request served from the worker or cache; going offline and navigating shows the offline page and no candidate data.

- [ ] **Step 6: Commit**

```bash
git add web/app web/public web/components/shell web/scripts
git commit -m "feat(web): installable PWA with static-only service worker"
```

---

### Task 14: Full verification

**Files:** none created; evidence recorded in the final report.

- [ ] **Step 1: Static checks**

Run (in `web/`): `npm test && npx tsc --noEmit && node scripts/contrast.mjs && npm run build`
Expected: all pass. Fix anything red before continuing.

- [ ] **Step 2: Backend suite, unchanged**

From the repository root confirm nothing under `backend/` changed: `git diff --stat c2ac29f -- backend` (the backend is untracked in this clone, so instead run `git status --short backend` and compare file timestamps with `find backend -newer docs/superpowers/specs/2026-09-30-cadence-frontend-redesign-design.md -type f`; expected: no files listed).
Then run the suite through the stack: `docker compose up --build -d`, then `docker compose exec api pytest -q`.
Expected: 126 passed. If the environment cannot run it, say so and report what was run instead.

- [ ] **Step 3: Browser walkthrough**

With the stack up and `web` running, walk these at 1280, 820 and 390 px (use the browser tools available; record pass/fail per row):
1. Inbox: loading, empty (fresh DB), populated, network error (stop the API), `?document=` redirect.
2. 401: rebuild web with a wrong `NEXT_PUBLIC_RECRUITER_TOKEN` and confirm every screen shows the "session is not accepted" state. 403: call a recruiter route with the engineer token via `curl` and confirm the mapped wording in the UI by pointing the web at it once.
3. Intake: upload, same-bytes notice, `needs_review` decision, `needs_ocr` file, 120-character filename.
4. Candidate: long name, evidence attached, CV text only after the confirm dialog (Network check), superseded versions.
5. Search: URL-state reload, grouped results, approximate-only warning, 200 results scroll performance.
6. Hiring: full lifecycle including reload restoring the stepper, pending, approved, rejected and shortlisted states, share approve then send.
7. Source, Excel (duplicate row), Merge (picker by name), Reports.
8. Keyboard-only pass through every dialog, menu and slide-over; visible focus everywhere.
9. PWA checks from Task 13, Step 5.

- [ ] **Step 4: Fix, re-run, report**

Fix defects found, re-run Steps 1–3 for the affected areas, then report each check with its actual result (including anything not verified and why). Do not claim success for a check that was not run.

- [ ] **Step 5: Commit any fixes**

```bash
git add web
git commit -m "fix(web): verification fixes"
```

---

## Self-Review

**Spec coverage:** §3 navigation and routes → Tasks 5, 7, 8, 10, 11 (redirects and kept routes in 5, 7, 12). §4 tokens, provenance, components, states, accessibility → Tasks 3, 4, 6. §5.1 Inbox → 7. §5.2 Intake → 8. §5.3 Profile → 9. §5.4 Search → 10. §5.5 Hiring incl. notes, updates, next steps, files, share → 11. §5.6 → 12. §6 responsive → each task's mobile line plus Task 14. §6a PWA → 13. §7 additive api → Task 2. §8 verification → Task 14. §9 out of scope respected (no backend, no directory, no editing).

**Type consistency:** `Step`, `StepState`, `LifecycleInput` defined in Task 2 and used by `Stepper` (Task 4) and the workspace (Task 11). `QueueGroup` fields (`requestId`, `names`, `count`) used identically in Task 7. `CandidateGroup` fields (`exact`, `approximate`, `approximateOnly`) used in Task 10. `describeError` returns `{kind,title,body}` used by `ErrorState`. `Tone` names in `Tag` (`proposed|decided|ok|warn|bad|unknown|neutral`) differ from the `tone` strings in `labels.ts` (`ok|prop|bad|human|unk`): the `Tag` component maps `prop→proposed`, `human→decided`, `unk→unknown` through a small `toneFor()` helper exported from `tag.tsx`; both `DISPOSITION` and `VERDICT` are passed through it.

**Placeholders:** none; UI tasks specify behaviour and data wiring per component, and every pure-logic step has full code and tests.

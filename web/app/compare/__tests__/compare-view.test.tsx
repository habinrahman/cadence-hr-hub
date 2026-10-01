// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Comparison, Review } from "@/lib/api";
import { ApiError } from "@/lib/errors";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams("review=r1"),
  useRouter: () => ({ replace: () => {}, push: () => {} }),
  usePathname: () => "/compare",
}));

vi.mock("@/lib/api", async (original) => ({
  ...(await original<typeof import("@/lib/api")>()),
  getReviewRecord: vi.fn(),
  getReview: vi.fn(),
  getReviewComparison: vi.fn(),
  getActivity: vi.fn(),
  decideReview: vi.fn(),
  getDocumentPages: vi.fn(),
}));

import * as api from "@/lib/api";
import { CompareView } from "../compare-view";

const CAND = "c-1";

const review = (over: Partial<Review> = {}): Review => ({
  id: "r1",
  document_id: "d-new",
  status: "pending",
  confidence: 96,
  likely_relationship: "updated_cv",
  recommended_action: "accept_update",
  offered_actions: ["accept_update", "record_duplicate", "create_separate_candidate"],
  candidate_id: CAND,
  candidate_ids: [CAND],
  candidates: [{ id: CAND, display_name: "Barak Buta" }],
  ambiguous: false,
  evidence: [
    { code: "email", weight: 0.5, state: "matched", value: 1, candidate_id: CAND },
    { code: "phone", weight: 0.3, state: "matched", value: 1, candidate_id: CAND },
    { code: "name", weight: 0.2, state: "recorded", value: 1, candidate_id: CAND },
    { code: "explicit_version", weight: 0.25, state: "unknown", value: null, candidate_id: CAND },
  ],
  ...over,
});

const doc = (id: string, filename: string, over = {}) => ({
  id,
  filename,
  media_type: "application/pdf",
  byte_size: 110000,
  received_at: "2026-09-30T05:14:00Z",
  page_count: 1,
  status: "extracted",
  is_current: false,
  text_source: "text_layer",
  language_code: "en",
  error_code: null,
  ...over,
});

const value = (label: string, page = 1) => ({ label, evidence: { quote: label, page } });

const comparison = (over: Partial<Comparison> = {}): Comparison => ({
  review_id: "r1",
  status: "pending",
  decided_at: null,
  available: true,
  reason: null,
  warnings: [],
  candidates: [{ id: CAND, name: "Barak Buta", merged_into_id: null }],
  candidate: { id: CAND, name: "Barak Buta", merged_into_id: null },
  existing: { state: "ok", document: doc("d-old", "resume_2025.pdf", { is_current: true }) },
  incoming: { state: "ok", document: doc("d-new", "resume_2026.pdf") },
  identical_bytes: false,
  fields: [
    {
      key: "experience",
      label: "Experience",
      comparable: true,
      existing_state: "extracted",
      incoming_state: "extracted",
      note: null,
      items: [
        { status: "added", label: "Google — Senior Engineer", existing: null, incoming: value("Google, Senior Engineer") },
        { status: "changed", label: "Initech — Lead", existing: value("Initech — Engineer"), incoming: value("Initech — Lead") },
        { status: "only_existing", label: "Old Co", existing: value("Old Co"), incoming: null },
        { status: "same", label: "Acme Corp — Software Engineer", existing: value("Acme Corp"), incoming: value("Acme Corp") },
      ],
    },
    {
      key: "skills",
      label: "Skills",
      comparable: false,
      existing_state: "extracted",
      incoming_state: "not_extracted",
      note: "Nothing was extracted from the new CV for this section, so it cannot be compared. That does not mean the information is absent.",
      items: [{ status: "unknown", label: "Python", existing: value("Python"), incoming: null }],
    },
  ],
  dates: {
    existing: { latest_mentioned: { date: "2025-01-01", page: 1 }, labelled_version: null },
    incoming: { latest_mentioned: { date: "2026-09-01", page: 1 }, labelled_version: { date: "2026-09-01", page: 1 } },
    uploaded: { existing: "2025-08-15T00:00:00Z", incoming: "2026-09-30T05:14:00Z" },
    newer_by_mentioned: "incoming",
    newer_by_labelled: null,
    conflict: false,
  },
  text_diff: {
    available: true,
    note: "Lines are compared after collapsing spaces.",
    incoming_only: [{ page: 1, text: "Google, Senior Engineer" }],
    existing_only: [],
    incoming_only_count: 1,
    existing_only_count: 0,
    truncated: false,
  },
  ...over,
});

const mocked = vi.mocked(api);

function setup(opts: { review?: Review; comparison?: Comparison } = {}) {
  mocked.getReviewRecord.mockResolvedValue(opts.review ?? review());
  mocked.getReviewComparison.mockResolvedValue(opts.comparison ?? comparison());
  mocked.getActivity.mockResolvedValue({
    events: [{ action: "duplicate_review_opened", actor_kind: "system", created_at: "2026-09-30T05:14:05Z", detail: {} }],
  });
  return render(<CompareView />);
}

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(cleanup);

const loaded = () => screen.findByRole("heading", { name: "Previous CV vs new CV" });

describe("comparison workspace", () => {
  it("names the existing and new CVs and their files", async () => {
    setup();
    await loaded();
    const existing = screen.getByRole("region", { name: "Previous CV" });
    const incoming = screen.getByRole("region", { name: "New CV" });
    expect(within(existing).getByText("resume_2025.pdf")).toBeTruthy();
    expect(within(incoming).getByText("resume_2026.pdf")).toBeTruthy();
    expect(within(existing).getByText("Current on file")).toBeTruthy();
    expect(within(incoming).getByText("Awaiting decision")).toBeTruthy();
    expect(within(existing).getByText("Barak Buta")).toBeTruthy();
    expect(screen.getByText(/never used as evidence/i)).toBeTruthy();
  });

  it("shows the system's recommendation apart from the recruiter's decision", async () => {
    setup();
    await loaded();
    const recommendation = screen.getByRole("region", { name: /Proposed by Cadence/ });
    const decision = screen.getByRole("region", { name: /Your decision/ });
    expect(recommendation).not.toBe(decision);
    expect(within(recommendation).getByText("Likely an updated CV")).toBeTruthy();
    expect(within(recommendation).getByText(/Cadence recommends. You decide./)).toBeTruthy();
    // A recommendation carries no buttons. Only the decision panel can change anything.
    expect(within(recommendation).queryAllByRole("button")).toHaveLength(0);
    expect(within(decision).getAllByRole("button").length).toBe(3);
    expect(within(decision).getByText("Suggested by Cadence")).toBeTruthy();
    expect(within(decision).queryByText("Decided")).toBeNull();
  });

  it("explains why the CVs are related in plain sentences, with the number last", async () => {
    setup();
    await loaded();
    const why = screen.getByRole("region", { name: /Why Cadence thinks/ });
    expect(within(why).getByText("Same email address — strong identity evidence")).toBeTruthy();
    expect(within(why).getByText("Same phone number — strong identity evidence")).toBeTruthy();
    expect(within(why).getByText("Name similarity 100%")).toBeTruthy();
    expect(within(why).getByText("Version date — not available")).toBeTruthy();
    expect(within(why).getByText(/not a model.s confidence/i)).toBeTruthy();
    // A missing signal shows no weight: it is left out of the score, not counted against it.
    expect(within(why).getByText("Version date — not available").closest("li")?.textContent).not.toMatch(/weight/);
    expect(within(why).getByText(/do not lower it/)).toBeTruthy();
  });

  it("labels added, changed, not-found and same items, and never says removed", async () => {
    setup();
    await loaded();
    const experience = screen.getByRole("region", { name: "Experience" });
    // Each status appears as a tag, so look for the tag by its exact label.
    const tags = within(experience).getAllByText((_, node) => node?.tagName === "SPAN" && node.className.includes("uppercase"));
    const labels = tags.map((tag) => tag.textContent?.replace(/^[+~?=·]\s*/, "").trim());
    expect(labels).toEqual(expect.arrayContaining(["Added in new CV", "Changed", "Not found in new CV", "Same"]));
    // The empty cell on the incoming side says the same thing in plain text.
    expect(within(experience).getAllByText("Not found in new CV").length).toBeGreaterThan(0);
    expect(document.body.textContent?.toLowerCase()).not.toContain("removed");
  });

  it("does not treat a section missing from one CV as a difference", async () => {
    setup();
    await loaded();
    const skills = screen.getByRole("region", { name: "Skills" });
    expect(within(skills).getAllByText("Not compared").length).toBeGreaterThan(0);
    expect(within(skills).getByText(/does not mean the information is absent/)).toBeTruthy();
    expect(within(skills).queryByText(/Added in incoming|Changed|Not found in incoming/)).toBeNull();
    expect(within(skills).getByText("Nothing extracted")).toBeTruthy();
  });

  it("opens the source page for a piece of evidence and loads the text only then", async () => {
    mocked.getDocumentPages.mockResolvedValue({ id: "d-new", page_count: 1, pages: [{ number: 1, text: "Barak Buta\nGoogle, Senior Engineer\n2025-01-01 to present" }] });
    const user = userEvent.setup();
    setup();
    await loaded();
    expect(mocked.getDocumentPages).not.toHaveBeenCalled();
    // A PDF opens on its page view. This test is about the text view.
    await user.click(within(screen.getByRole("group", { name: "New CV view" })).getByRole("button", { name: "Text" }));
    const experience = screen.getByRole("region", { name: "Experience" });
    await user.click(within(experience).getAllByText(/Source · page 1/)[0]);
    await user.click(within(experience).getAllByRole("button", { name: /Show in the new CV/ })[0]);
    await waitFor(() => expect(mocked.getDocumentPages).toHaveBeenCalledWith("d-new"));
    const text = await screen.findByLabelText("New CV, page 1");
    expect(text.textContent).toContain("Google, Senior Engineer");
    expect(mocked.getDocumentPages).toHaveBeenCalledTimes(1);
  });

  it("marks lines that appear only in one CV, in words as well as colour", async () => {
    mocked.getDocumentPages.mockResolvedValue({ id: "d-new", page_count: 1, pages: [{ number: 1, text: "Barak Buta\nGoogle, Senior Engineer" }] });
    const user = userEvent.setup();
    setup();
    await loaded();
    await user.click(within(screen.getByRole("group", { name: "New CV view" })).getByRole("button", { name: "Text" }));
    await user.click(within(screen.getByRole("region", { name: "New CV text" })).getByRole("button", { name: "Open CV text" }));
    const text = await screen.findByLabelText("New CV, page 1");
    expect(within(text).getByText(/Only in this CV:/)).toBeTruthy();
  });
});

describe("making a decision", () => {
  it("asks for confirmation in words about what will happen, and does nothing on cancel", async () => {
    const user = userEvent.setup();
    setup();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Merge & Update Profile" }));
    const dialog = await screen.findByRole("dialog", { name: "Merge this CV into the existing profile?" });
    expect(within(dialog).getByText(/becomes their current CV/)).toBeTruthy();
    expect(within(dialog).getByText(/stays in the candidate's history/)).toBeTruthy();
    expect(mocked.decideReview).not.toHaveBeenCalled();
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(mocked.decideReview).not.toHaveBeenCalled();
  });

  it("records the decision once, then shows the decided state and removes the controls", async () => {
    const user = userEvent.setup();
    setup();
    await loaded();
    mocked.decideReview.mockResolvedValue(review({ status: "accepted_update" }));
    mocked.getReviewRecord.mockResolvedValue(review({ status: "accepted_update" }));
    mocked.getReviewComparison.mockResolvedValue(comparison({ status: "accepted_update", decided_at: "2026-09-30T06:00:00Z", warnings: ["review_decided"] }));
    mocked.getActivity.mockResolvedValue({
      events: [
        { action: "duplicate_review_opened", actor_kind: "system", created_at: "2026-09-30T05:14:05Z", detail: {} },
        { action: "duplicate_review_decided", actor_kind: "user", created_at: "2026-09-30T06:00:00Z", detail: { human_action: "accept_update" } },
      ],
    });
    await user.click(screen.getByRole("button", { name: "Merge & Update Profile" }));
    const dialog = await screen.findByRole("dialog");
    await user.dblClick(within(dialog).getByRole("button", { name: "Yes, merge and update" }));
    await waitFor(() => expect(screen.getByText("Decision recorded: Merge & Update Profile.")).toBeTruthy());
    expect(mocked.decideReview).toHaveBeenCalledTimes(1);
    expect(mocked.decideReview).toHaveBeenCalledWith("r1", "accept_update", undefined);
    const decision = screen.getByRole("region", { name: /Your decision/ });
    expect(within(decision).getAllByText("Decided").length).toBeGreaterThan(0);
    expect(within(decision).queryAllByRole("button")).toHaveLength(0);
    expect(within(decision).getByText(/Recruiter decided/)).toBeTruthy();
  });

  it("says the review was already decided when the backend reports a conflict, and refreshes", async () => {
    const user = userEvent.setup();
    setup();
    await loaded();
    mocked.decideReview.mockRejectedValue(new ApiError(409, "invalid_transition"));
    mocked.getReviewRecord.mockResolvedValue(review({ status: "recorded_duplicate" }));
    mocked.getReviewComparison.mockResolvedValue(comparison({ status: "recorded_duplicate", warnings: ["review_decided"] }));
    const before = mocked.getReviewComparison.mock.calls.length;
    await user.click(screen.getByRole("button", { name: "Merge & Update Profile" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Yes, merge and update" }));
    await waitFor(() => expect(screen.getByText(/This review has already been decided/)).toBeTruthy());
    expect(screen.queryByText(/Decision recorded/)).toBeNull();
    expect(mocked.getReviewComparison.mock.calls.length).toBeGreaterThan(before);
    expect(within(screen.getByRole("region", { name: /Your decision/ })).queryAllByRole("button")).toHaveLength(0);
  });

  it("keeps the controls available and reports a network failure", async () => {
    const user = userEvent.setup();
    setup();
    await loaded();
    mocked.decideReview.mockRejectedValue(new TypeError("Failed to fetch"));
    await user.click(screen.getByRole("button", { name: "Delete Duplicate" }));
    await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Yes, delete duplicate" }));
    await waitFor(() => expect(screen.getByText("Cannot reach the server")).toBeTruthy());
    expect(screen.queryByText(/Decision recorded/)).toBeNull();
    expect(within(screen.getByRole("region", { name: /Your decision/ })).getAllByRole("button").length).toBe(3);
  });

  it("can be operated from the keyboard", async () => {
    const user = userEvent.setup();
    setup();
    await loaded();
    const first = screen.getByRole("button", { name: "Merge & Update Profile" });
    first.focus();
    expect(document.activeElement).toBe(first);
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("dialog", { name: "Merge this CV into the existing profile?" })).toBeTruthy();
  });
});

describe("states the backend can be in", () => {
  it("shows a decided review as a record with no decision buttons", async () => {
    setup({ review: review({ status: "accepted_update" }), comparison: comparison({ status: "accepted_update", warnings: ["review_decided"] }) });
    await loaded();
    expect(screen.getByText(/already been decided/)).toBeTruthy();
    expect(within(screen.getByRole("region", { name: /Your decision/ })).queryAllByRole("button")).toHaveLength(0);
  });

  it("blocks attaching a CV to a merged candidate but still allows a separate candidate", async () => {
    setup({
      comparison: comparison({
        warnings: ["candidate_merged"],
        candidate: { id: CAND, name: "Barak Buta", merged_into_id: "other" },
      }),
    });
    await loaded();
    expect((screen.getByRole("button", { name: "Merge & Update Profile" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Delete Duplicate" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Create New Candidate" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("says when the comparison is unavailable instead of inventing one", async () => {
    setup({
      comparison: comparison({
        available: false,
        reason: "excel_row",
        existing: null,
        incoming: null,
        fields: [],
        dates: null,
        text_diff: null,
      }),
    });
    await loaded();
    expect(screen.getByText(/Comparison unavailable/)).toBeTruthy();
    expect(screen.getByText(/spreadsheet row/)).toBeTruthy();
    expect(screen.queryByRole("region", { name: /Your decision/ })).toBeNull();
  });

  it("explains a new scan with no readable text and does not compare its fields", async () => {
    setup({
      comparison: comparison({
        incoming: { state: "needs_ocr", document: doc("d-new", "scan.pdf", { status: "needs_ocr" }) },
        text_diff: { available: false, note: "", incoming_only: [], existing_only: [], incoming_only_count: 0, existing_only_count: 0, truncated: false },
      }),
    });
    await loaded();
    expect(within(screen.getByRole("region", { name: "New CV" })).getByText(/scan that has not been read yet/)).toBeTruthy();
    expect(screen.getByText(/text comparison is not available/i)).toBeTruthy();
  });

  it("does not claim a shared phone number when the stored signal matched but the CVs show none", async () => {
    setup({
      comparison: comparison({
        fields: [
          ...comparison().fields,
          {
            key: "phone",
            label: "Phone",
            comparable: true,
            existing_state: "extracted",
            incoming_state: "extracted",
            note: null,
            items: [
              { status: "added", label: "+971 50 000 0000", existing: null, incoming: value("+971 50 000 0000") },
              { status: "only_existing", label: "+44 20 0000 0000", existing: value("+44 20 0000 0000"), incoming: null },
            ],
          },
        ],
      }),
    });
    await loaded();
    const why = screen.getByRole("region", { name: /Why Cadence thinks/ });
    expect(within(why).getByText(/Phone signal matched, but the two CVs show no phone number in common/)).toBeTruthy();
    expect(within(why).queryByText(/^Same phone number/)).toBeNull();
    // It is not offered as supporting evidence next to the recommendation either.
    const recommendation = screen.getByRole("region", { name: /Proposed by Cadence/ });
    expect(within(recommendation).queryByText(/^Same phone number/)).toBeNull();
  });

  it("flags conflicting date evidence", async () => {
    setup({
      comparison: comparison({
        warnings: ["date_conflict"],
        dates: { ...comparison().dates!, conflict: true, newer_by_labelled: "existing", newer_by_mentioned: "incoming" },
      }),
    });
    await loaded();
    expect(screen.getAllByText(/Date information conflicts/).length).toBeGreaterThan(0);
  });

  it("shows a forbidden state to a role that cannot read candidate data", async () => {
    mocked.getReviewRecord.mockRejectedValue(new ApiError(403, "recruiter_required"));
    render(<CompareView />);
    expect(await screen.findByText("This role cannot open this")).toBeTruthy();
    expect(screen.queryByRole("region", { name: /Your decision/ })).toBeNull();
  });
});

describe("small screens", () => {
  it("offers a toggle between the two CV texts so neither is squeezed into a narrow column", async () => {
    const user = userEvent.setup();
    setup();
    await loaded();
    const tabs = screen.getByRole("tablist", { name: "Choose a CV" });
    const existing = within(tabs).getByRole("tab", { name: "Previous CV" });
    const incoming = within(tabs).getByRole("tab", { name: "New CV" });
    expect(incoming.getAttribute("aria-selected")).toBe("true");
    expect(document.getElementById("panel-existing")!.className).toContain("hidden md:block");
    await user.click(existing);
    expect(existing.getAttribute("aria-selected")).toBe("true");
    expect(document.getElementById("panel-existing")!.className).toBe("block");
    expect(document.getElementById("panel-incoming")!.className).toContain("hidden md:block");
  });
});

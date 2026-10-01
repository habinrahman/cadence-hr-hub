// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/ui/toast";

const api = vi.hoisted(() => ({
  getHiringRequest: vi.fn(),
  listHiringMatches: vi.fn(),
  getDashboard: vi.fn(),
  getSharePreview: vi.fn(),
  shortlistMatch: vi.fn(),
  rejectMatch: vi.fn(),
  restoreMatch: vi.fn(),
  approveHiringRequirements: vi.fn(),
  addHiringRequirement: vi.fn(),
  editHiringRequirement: vi.fn(),
  rejectHiringRequirement: vi.fn(),
  runHiringMatch: vi.fn(),
  retryProcessing: vi.fn(),
  openPool: vi.fn(),
}));
vi.mock("@/lib/api", () => api);
vi.mock("next/link", () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));

import { Workspace } from "../workspace";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function defaults() {
  api.openPool.mockResolvedValue({ pool_opened_at: null });
  api.getSharePreview.mockRejectedValue(new Error("not probed: the server sends the flags"));
}

const detail = {
  id: "r1",
  company: "Northwind",
  job_title: "Analyst",
  description: "Required skills: Python",
  status: "open",
  received_at: "2026-10-01T00:00:00Z",
  owner_user_id: "u1",
  notes: [],
  updates: [],
  next_steps: [],
  attachments: [],
  candidates_found: 1,
  candidates_shared: 0,
  requirements: [{ id: "q1", label: "skill", text: "Python", strength: "mandatory", source_quote: "Required skills: Python", review_status: "approved" }],
  requirements_source: null,
  processing: { stage: "complete", matched_count: 1, requested_count: null, pool_status: "confirmed" },
  pool_stale: false,
  pool_opened_at: null,
  last_match_completed_at: "2026-10-01T00:00:00Z",
  requested_count: null,
  contact_email: "hiring@northwind.example",
};

const match = (flags: { shortlisted: boolean }) => ({
  id: "m1",
  candidate_id: "c1",
  candidate_name: "Ada Example",
  disposition: "recommended",
  eligibility: "eligible",
  match_score: 100,
  match_score_exact: 100,
  score_max: 100,
  mandatory_met: 1,
  mandatory_total: 1,
  preferred_met: 0,
  preferred_total: 0,
  blocking_requirements: [],
  score_reason: "1/1 mandatory requirements met",
  explanation: null,
  strengths: ["Python"],
  gaps: [],
  requirements: [],
  years_of_experience: 3,
  share_approved: false,
  shared: false,
  ...flags,
});

const emptyDesk = {
  counts: { shortlisted_candidates: 0 },
  shortlisted_candidates: [],
  shares_awaiting_approval: [],
  viewer_id: "u1",
};

describe("the pool page shows what the server says was decided", () => {
  it("keeps a card shortlisted after the dashboard refresh that follows the click", async () => {
    defaults();
    api.getHiringRequest.mockResolvedValue(detail);
    // The dashboard is stale on purpose: it has not caught up with the click yet.
    api.getDashboard.mockImplementation(async () => ({ ...emptyDesk })); // a new object per call, like the real API
    api.listHiringMatches
      .mockResolvedValueOnce({ matches: [match({ shortlisted: false })] })
      .mockResolvedValue({ matches: [match({ shortlisted: true })] });
    api.shortlistMatch.mockResolvedValue({ review_state: "shortlisted" });
    render(
      <ToastProvider>
        <Workspace requestId="r1" initialCandidate={null} />
      </ToastProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Add to shortlist" }));
    await screen.findByRole("button", { name: "Review share…" });
    await waitFor(() => expect(api.getDashboard.mock.calls.length).toBeGreaterThan(1)); // the refresh ran
    // The overwrite, when the bug is present, lands just after the refresh resolves. Let it settle, then look again.
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(screen.getByRole("button", { name: "Review share…" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Add to shortlist" })).toBeNull();
  });

  it("shows an already-shared candidate as shortlisted on first load, not as a candidate to add", async () => {
    defaults();
    api.getHiringRequest.mockResolvedValue({ ...detail, candidates_shared: 1 });
    api.getDashboard.mockImplementation(async () => ({ ...emptyDesk })); // a new object per call, like the real API // the dashboard no longer lists a candidate once sent
    api.listHiringMatches.mockResolvedValue({ matches: [{ ...match({ shortlisted: true }), share_approved: true, shared: true }] });
    render(
      <ToastProvider>
        <Workspace requestId="r1" initialCandidate={null} />
      </ToastProvider>,
    );
    await screen.findByRole("button", { name: "Review share…" });
    expect(screen.queryByRole("button", { name: "Add to shortlist" })).toBeNull();
  });
});

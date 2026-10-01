// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CandidateMatch, HiringRequirement } from "@/lib/api";
import { deriveLifecycle } from "@/lib/lifecycle";
import { Pool } from "../pool";
import { ProcessingCard } from "../processing-card";
import { RejectedLine, Requirements } from "../requirements";

afterEach(cleanup);

const req = (over: Partial<HiringRequirement> = {}): HiringRequirement =>
  ({ id: "r1", label: "skill", text: "Python", strength: "mandatory", source_quote: "strong Python", review_status: "proposed", ...over }) as HiringRequirement;

const match = (over: Partial<CandidateMatch> = {}): CandidateMatch =>
  ({
    id: "m1",
    candidate_id: "c1",
    candidate_name: "Ada Example",
    disposition: "recommended",
    eligibility: "eligible",
    match_score: 100,
    match_score_exact: 100,
    score_max: 100,
    mandatory_met: 0,
    mandatory_total: 0,
    preferred_met: 0,
    preferred_total: 0,
    blocking_requirements: [],
    score_reason: "No requirements to compare",
    explanation: null,
    strengths: [],
    gaps: [],
    requirements: [],
    years_of_experience: null,
    ...over,
  }) as CandidateMatch;

function renderPool(poolStatus: "provisional" | "confirmed", shortlisted = false) {
  const handlers = { onShortlistSelected: vi.fn(), onReject: vi.fn(), onShare: vi.fn() };
  render(
    <Pool
      matches={[match()]}
      shortlist={{ c1: shortlisted ? "yes" : "no" }}
      busy={false}
      jobTitle="Engineer"
      poolStatus={poolStatus}
      {...handlers}
    />,
  );
  return handlers;
}

describe("automatic matching gives a provisional pool; approval confirms it", () => {
  it("shows the provisional pool as matched, waiting for HR to approve the requirements", () => {
    render(
      <ProcessingCard processing={{ stage: "complete", matched_count: 12, requested_count: 5, pool_status: "provisional" }} status="open" onRetry={vi.fn()} />,
    );
    expect(screen.getByText("Candidate matching completed")).toBeTruthy();
    expect(screen.getByText("Waiting for HR to review and approve the requirements")).toBeTruthy();
    expect(screen.getByText(/12 candidates matched/)).toBeTruthy();
    expect(screen.getByText("Provisional")).toBeTruthy();
  });

  it("shows the confirmed pool once the requirements are approved", () => {
    render(
      <ProcessingCard processing={{ stage: "complete", matched_count: 9, requested_count: 5, pool_status: "confirmed" }} status="open" onRetry={vi.fn()} />,
    );
    expect(screen.getByText("Requirements approved by HR")).toBeTruthy();
    expect(screen.getByText("Confirmed")).toBeTruthy();
  });

  it("explains an empty proposal: nothing to match until HR adds a requirement", () => {
    render(<ProcessingCard processing={{ stage: "awaiting_approval", matched_count: 0, requested_count: 5 }} status="open" onRetry={vi.fn()} />);
    expect(screen.getByRole("status").textContent).toMatch(/No requirement was proposed, so nothing could be matched/);
    expect(screen.queryByText(/candidates matched/)).toBeNull();
  });

  it("labels a provisional pool and blocks shortlisting, sharing and rejecting, but still shows the candidate", () => {
    const handlers = renderPool("provisional");
    expect(screen.getByText("Provisional match pool")).toBeTruthy();
    expect(screen.getByText(/Based on automatically extracted requirements — review requirements before shortlisting/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Ada Example" })).toBeTruthy();
    expect(screen.getByLabelText("Match score 100 out of 100")).toBeTruthy();
    const add = screen.getByRole("button", { name: "Add to shortlist" }) as HTMLButtonElement;
    expect(add.disabled).toBe(true);
    fireEvent.click(add);
    expect(handlers.onShortlistSelected).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: /Shortlist selected/ }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Reject…" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("checkbox", { name: /Select Ada Example/ })).toBeNull();
  });

  it("blocks a share from a provisional pool even for a candidate shortlisted earlier", () => {
    const handlers = renderPool("provisional", true);
    const share = screen.getByRole("button", { name: "Review share…" }) as HTMLButtonElement;
    expect(share.disabled).toBe(true);
    fireEvent.click(share);
    expect(handlers.onShare).not.toHaveBeenCalled();
  });

  it("unlocks shortlisting on a confirmed pool", () => {
    const handlers = renderPool("confirmed");
    expect(screen.getByText("Confirmed match pool")).toBeTruthy();
    expect(screen.getByText("Matched against HR-approved requirements.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add to shortlist" }));
    expect(handlers.onShortlistSelected).toHaveBeenCalledWith(["m1"]);
  });

  it("shows proposed requirements as not approved and offers Approve once", () => {
    const approve = vi.fn();
    render(<Requirements requirements={[req(), req({ id: "r2", text: "AWS", strength: "preferred" })]} busy={false} poolStale={false} onApprove={approve} onRerun={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getAllByText("Proposed · not approved")).toHaveLength(2);
    expect(screen.getByText(/2 requirements are waiting for approval/)).toBeTruthy();
    expect(screen.getByText(/The candidate pool stays provisional until they are approved/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Approve requirements" }));
    expect(approve).toHaveBeenCalledTimes(1);
  });

  it("lets HR reject one requirement, labels it, and leaves only proposed rows waiting", () => {
    const reject = vi.fn();
    render(
      <Requirements
        requirements={[req(), req({ id: "r2", text: "AWS", strength: "preferred", review_status: "rejected" })]}
        busy={false}
        poolStale={false}
        onApprove={vi.fn()}
        onReject={reject}
        onRerun={vi.fn()}
        onEdit={vi.fn()}
      />,
    );
    expect(screen.getByText("Rejected · not matched on")).toBeTruthy();
    expect(screen.getByText(/1 requirement is waiting for approval/)).toBeTruthy();
    // Only the row that is not already rejected offers Reject.
    const buttons = screen.getAllByRole("button", { name: "Reject requirement" });
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    expect(reject).toHaveBeenCalledWith(expect.objectContaining({ id: "r1" }));
  });

  it("shows no Approve button once everything is approved", () => {
    render(<Requirements requirements={[req({ review_status: "approved" })]} busy={false} poolStale={false} onApprove={vi.fn()} onRerun={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Approve requirements" })).toBeNull();
    expect(screen.getByText("Approved")).toBeTruthy();
  });

  it("does not offer a manual re-run while the approval rematch is running", () => {
    render(<Requirements requirements={[req({ review_status: "approved" })]} busy={false} poolStale rematching onRerun={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "Re-run matching" })).toBeNull();
  });

  it("lets HR add a requirement by hand when every proposal was refused", async () => {
    const add = vi.fn().mockResolvedValue(true);
    render(<Requirements requirements={[]} busy={false} poolStale={false} awaitingApproval onAdd={add} onRerun={vi.fn()} onEdit={vi.fn()} />);
    expect(screen.getByText(/No requirement was proposed/)).toBeTruthy();
    const add_btn = screen.getByRole("button", { name: "Add requirement" }) as HTMLButtonElement;
    expect(add_btn.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Requirement"), { target: { value: "Excel" } });
    fireEvent.change(screen.getByLabelText("Quote from the job description"), { target: { value: "Excel is required" } });
    fireEvent.click(add_btn);
    await waitFor(() => expect(add).toHaveBeenCalledWith({ label: "skill", text: "Excel", strength: "mandatory", quote: "Excel is required" }));
  });

  it("lists refused proposals by reason, never by their text", () => {
    render(<RejectedLine source={{ model: "ollama:m", prompt_version: "p", fallback: false, accepted: 0, rejected: { blocked_attribute: 2, injected_instruction: 1 } }} />);
    expect(screen.getByText(/3 proposals were refused and not stored: 2 a protected characteristic, 1 an instruction inside the text/)).toBeTruthy();
  });

  it("puts matching before approval in the lifecycle, and keeps shortlisting behind a confirmed pool", () => {
    const provisional = deriveLifecycle({ processing: "complete", poolStatus: "provisional", matchCount: 12, reviewed: 0, shortlisted: 0, sharesApproved: 0, shared: 0 });
    expect(provisional.find((s) => s.key === "matched")?.state).toBe("done");
    expect(provisional.find((s) => s.key === "matched")?.detail).toBe("12 matched · provisional");
    expect(provisional.find((s) => s.key === "review")?.detail).toBe("Approve requirements first");
    expect(provisional.find((s) => s.key === "shortlist")?.detail).toBe("Needs a confirmed pool");
    const confirmed = deriveLifecycle({ processing: "complete", poolStatus: "confirmed", matchCount: 9, reviewed: 0, shortlisted: 0, sharesApproved: 0, shared: 0 });
    expect(confirmed.find((s) => s.key === "matched")?.detail).toBe("9 matched · confirmed");
    expect(confirmed.find((s) => s.key === "extracted")?.detail).toBe("Approved by HR");
  });
});

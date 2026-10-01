// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Loaded } from "../command-center";
import type { Dashboard } from "@/lib/api";

const desk = {
  counts: {
    requests_received: 2,
    new_matches: 1,
    reviews_needing_attention: 6,
    shortlisted_candidates: 3,
    shares_awaiting_approval: 2,
    duplicate_reviews: 1,
    open_problem_reports: 4,
    relationship_reviews: 1,
    requirements_awaiting_approval: 1,
    matches_awaiting_review: 2,
    active_hiring_requests: 3,
  },
  needs_you_now: [{ type: "new_matches", subject: "Acme Corp · Senior Backend Engineer", status: "pool_ready", created_at: "2026-09-30T10:00:00Z", href: "/hiring?request=1" }],
  new_match_pools: [],
  relationship_reviews: [], requirements_awaiting_approval: [], matches_awaiting_review: [], shortlisted_candidates: [],
  shares_awaiting_approval: [], open_problem_reports: [], recent_activity: [], active_hiring_requests: [], viewer_id: "u",
} as unknown as Dashboard;

describe("Command Center", () => {
  it("shows the eight desk tiles and needs-you-now, framed as an internal workspace", () => {
    render(<Loaded desk={desk} />);
    for (const label of [
      /Requests being processed/,
      /Requirements to approve/,
      /New candidate matches/,
      /Reviews needing attention/,
      /Shortlisted, not yet sent/,
      /Sharing approvals/,
      /Duplicate \/ update reviews/,
      /Problem reports/,
    ]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
    expect(screen.getByText(/Needs you now/)).toBeTruthy();
    expect(screen.getByText(/Acme Corp/)).toBeTruthy();
  });
});

// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import type { MatchRequirement } from "@/lib/api";
import { RequirementMatrix, scoreLine } from "../requirement-matrix";

const req = (over: Partial<MatchRequirement>): MatchRequirement => ({
  requirement_id: "r1",
  label: "skill",
  text: "Python",
  strength: "mandatory",
  result: "meets",
  evidence_id: null,
  evidence: "Software Engineer, Python, 2019-2026",
  retrieval: null,
  points_possible: 23.4,
  points_earned: 23.4,
  ...over,
});

describe("RequirementMatrix points", () => {
  it("shows the points earned out of the points possible beside each requirement's evidence", () => {
    render(
      <RequirementMatrix
        requirements={[
          req({}),
          req({ requirement_id: "r2", text: "SQL", result: "partial", points_earned: 11.7, points_possible: 23.3, evidence: "Used SQL daily" }),
          req({ requirement_id: "r3", text: "AWS", strength: "preferred", result: "unknown", points_earned: 0, points_possible: 15, evidence: null }),
        ]}
      />,
    );
    expect(screen.getAllByText("+23.4").length).toBeGreaterThan(0);
    expect(screen.getAllByText("+11.7").length).toBeGreaterThan(0);
    expect(screen.getAllByText("+0").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Software Engineer, Python/).length).toBeGreaterThan(0);
  });

  it("explains how the headline score was rounded", () => {
    expect(scoreLine([req({}), req({})], 63, 62.5)).toBe("62.5 of 100 points earned across 2 requirements (62.5 rounded to 63)");
    expect(scoreLine([req({})], 100, 100)).toBe("100 of 100 points earned across 1 requirement");
    expect(scoreLine([], null, null)).toBeNull();
  });
});

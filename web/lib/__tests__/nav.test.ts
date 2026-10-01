import { describe, it, expect } from "vitest";
import { ALL_NAV, NAV_GROUPS, pageLabel } from "@/components/shell/nav";

describe("navigation", () => {
  it("keeps CV intake and Excel import under Candidates", () => {
    const candidates = NAV_GROUPS.flatMap((g) => g.items).find((i) => i.label === "Candidates");
    const labels = candidates?.children?.map((c) => c.label);
    expect(labels).toEqual(["Candidate Intelligence", "Search", "Source Candidate", "CV Intake", "Excel Import & Export"]);
  });
  it("has the three hiring request views (nothing closes a request, so there is no Completed view)", () => {
    const hiring = ALL_NAV.find((i) => i.label === "Hiring Requests");
    expect(hiring?.children?.map((c) => c.label)).toEqual(["All Requests", "New / Processing", "Matching Complete"]);
  });
  it("has the four review queue views", () => {
    const queue = ALL_NAV.find((i) => i.label === "Review Queue");
    expect(queue?.children?.map((c) => c.label)).toEqual(["CV Updates / Duplicates", "Requirement Reviews", "Match Reviews", "Sharing Approvals"]);
  });
  it("labels the hiring detail page", () => expect(pageLabel("/hiring")).toBe("Hiring Requests"));
});

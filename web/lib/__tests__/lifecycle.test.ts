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

import { describe, it, expect } from "vitest";
import { deriveLifecycle } from "@/lib/lifecycle";

const base = { processing: "complete" as const, matchCount: 23, reviewed: 0, shortlisted: 0, sharesApproved: 0, shared: 0 };
const states = (i: Parameters<typeof deriveLifecycle>[0]) => deriveLifecycle(i).map((s) => s.state);

describe("deriveLifecycle", () => {
  it("has the seven stages in order, without a requirement-approval step", () => {
    expect(deriveLifecycle(base).map((s) => s.label)).toEqual([
      "Received",
      "Requirements extracted",
      "Matching complete",
      "HR review",
      "Shortlisted",
      "Share approved",
      "Shared",
    ]);
  });
  it("is waiting on extraction while received", () => {
    expect(states({ ...base, processing: "received", matchCount: 0 })).toEqual(["done", "current", "locked", "locked", "locked", "locked", "locked"]);
  });
  it("is waiting on matching while extracting is done", () => {
    expect(states({ ...base, processing: "matching", matchCount: 0 })).toEqual(["done", "done", "current", "locked", "locked", "locked", "locked"]);
  });
  it("hands over to HR review once matching completes", () => {
    expect(states(base)).toEqual(["done", "done", "done", "current", "locked", "locked", "locked"]);
  });
  it("moves to shortlist after HR has decided on someone", () => {
    expect(states({ ...base, reviewed: 3 })).toEqual(["done", "done", "done", "done", "current", "locked", "locked"]);
  });
  it("moves to share approval once someone is shortlisted", () => {
    expect(states({ ...base, reviewed: 5, shortlisted: 5 })).toEqual(["done", "done", "done", "done", "done", "current", "locked"]);
  });
  it("completes when a share was sent", () => {
    expect(states({ ...base, reviewed: 5, shortlisted: 5, sharesApproved: 1, shared: 1 })).toEqual(Array(7).fill("done"));
  });
  it("shows the failure on the processing step", () => {
    const steps = deriveLifecycle({ ...base, processing: "failed", matchCount: 0 });
    expect(steps[1].detail).toMatch(/failed/i);
  });
  it("treats an unknown shortlist as not done and says so", () => {
    const steps = deriveLifecycle({ ...base, shortlisted: null });
    expect(steps[4].detail).toMatch(/unknown/i);
  });
  it("says how far sharing got", () => {
    const steps = deriveLifecycle({ ...base, reviewed: 1, shortlisted: 1, sharesApproved: 1 });
    expect(steps[5].detail).toBe("1 approved, not sent");
  });
});

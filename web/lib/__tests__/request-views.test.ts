import { describe, it, expect } from "vitest";
import { filterRequests } from "@/lib/request-views";
import type { RequestSummary } from "@/lib/api";

const r = (over: Partial<RequestSummary>): RequestSummary =>
  ({ id: "1", company: "Acme", job_title: "SBE", status: "open", received_at: "2026-09-30T00:00:00Z", processing: "complete", matched_count: 0, requested_count: null, ...over }) as RequestSummary;

const rows = [r({ id: "a", processing: "matching" }), r({ id: "b" }), r({ id: "c", status: "closed" })];

describe("filterRequests", () => {
  it("all returns everything", () => expect(filterRequests(rows, "all")).toHaveLength(3));
  it("new / processing", () => expect(filterRequests(rows, "processing").map((x) => x.id)).toEqual(["a"]));
  it("matching complete excludes closed", () => expect(filterRequests(rows, "complete").map((x) => x.id)).toEqual(["b"]));
  it("completed means closed or shared", () => expect(filterRequests(rows, "closed").map((x) => x.id)).toEqual(["c"]));
});

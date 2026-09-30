import { describe, it, expect } from "vitest";
import { parseSearch, toQueryString, groupHits, hasCriteria, FILTERS } from "@/lib/search-state";
import type { SearchHit } from "@/lib/api";

const hit = (over: Partial<SearchHit>): SearchHit => ({
  candidate_id: "c1", candidate_name: "Amira", document_id: "d1", chunk_id: "k1",
  evidence: "python", reasons: ["keyword"], retrieval_score: 1, ...over,
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

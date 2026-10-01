import { describe, it, expect } from "vitest";
import { EMPTY_FILTERS, comparePool, filterPool, matchBadge, requirementCounts, type PoolMatch } from "@/lib/pool-filters";

const m = (over: Partial<PoolMatch>): PoolMatch =>
  ({
    id: "1",
    candidate_id: "c1",
    candidate_name: "Ada",
    disposition: "recommended",
    explanation: null,
    strengths: ["Python"],
    gaps: [],
    requirements: [],
    years_of_experience: 6,
    location: "Berlin",
    ...over,
  }) as PoolMatch;

describe("filterPool", () => {
  const pool = [
    m({ id: "1", disposition: "recommended", eligibility: "eligible", years_of_experience: 8, location: "Berlin", strengths: ["Python", "SQL"] }),
    m({ id: "2", disposition: "needs_review", eligibility: "needs_review", years_of_experience: 2, location: "Lagos", strengths: ["SQL"] }),
    m({ id: "3", disposition: "excluded", eligibility: "excluded", years_of_experience: 10, location: "Berlin", strengths: [] }),
  ];
  it("shows the candidates still in play by default; excluded and rejected are one filter away", () => {
    expect(filterPool(pool, EMPTY_FILTERS).map((x) => x.id)).toEqual(["1", "2"]);
    expect(filterPool(pool, { ...EMPTY_FILTERS, matchStatus: "excluded" }).map((x) => x.id)).toEqual(["3"]);
    const rejected = m({ id: "4", disposition: "rejected", eligibility: "eligible" });
    expect(filterPool([...pool, rejected], { ...EMPTY_FILTERS, matchStatus: "rejected" }).map((x) => x.id)).toEqual(["4"]);
    expect(filterPool([...pool, rejected], EMPTY_FILTERS).map((x) => x.id)).toEqual(["1", "2"]);
  });
  it("filters by match status", () => {
    expect(filterPool(pool, { ...EMPTY_FILTERS, matchStatus: "eligible" }).map((x) => x.id)).toEqual(["1"]);
    expect(filterPool(pool, { ...EMPTY_FILTERS, matchStatus: "review" }).map((x) => x.id)).toEqual(["2"]);
  });
  it("filters by skill, case-insensitively, against strengths", () => {
    expect(filterPool(pool, { ...EMPTY_FILTERS, skill: "python" }).map((x) => x.id)).toEqual(["1"]);
  });
  it("filters by minimum years", () => {
    expect(filterPool(pool, { ...EMPTY_FILTERS, minYears: 5 }).map((x) => x.id)).toEqual(["1"]);
  });
  it("filters by location", () => {
    expect(filterPool(pool, { ...EMPTY_FILTERS, location: "lag" }).map((x) => x.id)).toEqual(["2"]);
  });
  it("drops candidates with unknown years when a minimum is set", () => {
    expect(filterPool([m({ years_of_experience: null })], { ...EMPTY_FILTERS, minYears: 1 })).toHaveLength(0);
  });
});

describe("matchBadge", () => {
  it("labels dispositions for HR", () => {
    expect(matchBadge("recommended").label).toBe("Match");
    expect(matchBadge("needs_review").label).toBe("Needs review");
    expect(matchBadge("excluded").label).toBe("Excluded");
  });
});

describe("requirementCounts", () => {
  it("keeps mandatory and preferred apart", () => {
    expect(requirementCounts({ mandatory_met: 4, mandatory_total: 4, preferred_met: 0, preferred_total: 1 })).toBe("4/4 mandatory · 0/1 preferred");
    expect(requirementCounts({ mandatory_met: 2, mandatory_total: 3, preferred_met: 0, preferred_total: 0 })).toBe("2/3 mandatory");
  });
});

describe("comparePool", () => {
  it("never ranks a held candidate above an eligible one, whatever its counts", () => {
    const held = m({ id: "h", eligibility: "needs_review", match_score: null, match_score_exact: null, mandatory_met: 9 });
    const low = m({ id: "e", eligibility: "eligible", match_score: 70, match_score_exact: 70, mandatory_met: 1 });
    const high = m({ id: "f", eligibility: "eligible", match_score: 100, match_score_exact: 100, mandatory_met: 1 });
    const out = m({ id: "x", eligibility: "excluded", match_score: null, match_score_exact: null, mandatory_met: 9 });
    expect([out, held, low, high].sort(comparePool).map((x) => x.id)).toEqual(["f", "e", "h", "x"]);
  });
});

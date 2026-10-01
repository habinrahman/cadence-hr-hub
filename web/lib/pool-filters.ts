import type { CandidateMatch } from "@/lib/api";
import type { Tone } from "@/lib/labels";

export type PoolMatch = CandidateMatch & { years_of_experience?: number | null; location?: string | null };

export type PoolFilters = {
  /** open: eligible and needs review, the candidates still in play. Excluded and rejected stay one click away. */
  matchStatus: "open" | "eligible" | "review" | "excluded" | "rejected";
  skill: string;
  location: string;
  minYears: number | null;
};

export const EMPTY_FILTERS: PoolFilters = { matchStatus: "open", skill: "", location: "", minYears: null };

/** Which status group a candidate falls in. A recruiter's rejection outranks the matcher's verdict. */
export function statusGroup(m: Pick<CandidateMatch, "disposition" | "eligibility">): Exclude<PoolFilters["matchStatus"], "open"> {
  if (m.disposition === "rejected") return "rejected";
  if (m.eligibility === "excluded") return "excluded";
  return m.eligibility === "eligible" ? "eligible" : "review";
}

export function matchBadge(disposition: string): { label: "Match" | "Needs review" | "Excluded" | "Rejected"; tone: Tone } {
  switch (disposition) {
    case "recommended":
      return { label: "Match", tone: "proposed" };
    case "needs_review":
      return { label: "Needs review", tone: "warn" };
    case "rejected":
      return { label: "Rejected", tone: "neutral" };
    default:
      return { label: "Excluded", tone: "neutral" };
  }
}

/** "4/4 mandatory · 0/1 preferred". Mandatory and preferred are never added together. */
export function requirementCounts(m: Pick<CandidateMatch, "mandatory_met" | "mandatory_total" | "preferred_met" | "preferred_total">): string {
  const parts: string[] = [];
  if (m.mandatory_total > 0) parts.push(`${m.mandatory_met}/${m.mandatory_total} mandatory`);
  if (m.preferred_total > 0) parts.push(`${m.preferred_met}/${m.preferred_total} preferred`);
  return parts.join(" · ") || "No requirements compared";
}

const ELIGIBILITY_ORDER = { eligible: 0, needs_review: 1, excluded: 2 } as const;

/**
 * Pool order: eligible by match score, then needs review by mandatory requirements met, then excluded. A candidate
 * held at the mandatory gate never ranks above one who passed it. Ties keep the server's order (Array.sort is stable).
 */
export function comparePool(a: CandidateMatch, b: CandidateMatch): number {
  return (
    ELIGIBILITY_ORDER[a.eligibility] - ELIGIBILITY_ORDER[b.eligibility] ||
    (b.match_score_exact ?? 0) - (a.match_score_exact ?? 0) ||
    b.mandatory_met - a.mandatory_met
  );
}

export function filterPool(matches: PoolMatch[], f: PoolFilters): PoolMatch[] {
  const skill = f.skill.trim().toLowerCase();
  const place = f.location.trim().toLowerCase();
  return matches.filter((m) => {
    const group = statusGroup(m);
    if (f.matchStatus === "open" ? group !== "eligible" && group !== "review" : group !== f.matchStatus) return false;
    if (skill && !m.strengths.some((s) => s.toLowerCase().includes(skill))) return false;
    if (place && !(m.location ?? "").toLowerCase().includes(place)) return false;
    if (f.minYears !== null && (m.years_of_experience ?? -1) < f.minYears) return false;
    return true;
  });
}

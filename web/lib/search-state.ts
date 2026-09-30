import type { SearchHit } from "@/lib/api";

export const FILTERS: { name: string; label: string; note?: string }[] = [
  { name: "skill", label: "Skill" },
  { name: "min_years", label: "Minimum years" },
  { name: "job_title", label: "Job title" },
  { name: "industry", label: "Industry experience" },
  { name: "education", label: "Education" },
  { name: "certificate", label: "Certificate or qualification" },
  { name: "experience", label: "Experience" },
  { name: "name", label: "Name" },
  {
    name: "nationality",
    label: "Nationality",
    note: "Use only when the role requires it. It matches words already written in the CV and is never inferred.",
  },
];

const KNOWN = new Set(["q", ...FILTERS.map((f) => f.name)]);

export function parseSearch(params: URLSearchParams): Record<string, string> {
  const out: Record<string, string> = {};
  params.forEach((value, name) => {
    if (KNOWN.has(name) && value.trim()) out[name] = value;
  });
  return out;
}

export function toQueryString(values: Record<string, string>): string {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(values)) {
    if (KNOWN.has(name) && value.trim()) params.set(name, value);
  }
  return params.toString();
}

export function hasCriteria(values: Record<string, string>): boolean {
  return Object.values(values).some((v) => v.trim() !== "");
}

/** The vector is a token hash, so similar and related wording are approximate, not semantic proof. */
const APPROXIMATE = new Set(["trigram", "semantic"]);

export type CandidateGroup = {
  key: string;
  candidateId: string | null;
  name: string | null;
  hits: SearchHit[];
  exact: string[];
  approximate: string[];
  approximateOnly: boolean;
};

export function groupHits(hits: SearchHit[]): CandidateGroup[] {
  const groups = new Map<string, CandidateGroup>();
  for (const hit of hits) {
    const key = hit.candidate_id ?? `doc:${hit.document_id}`;
    let group = groups.get(key);
    if (!group) {
      group = {
        key,
        candidateId: hit.candidate_id,
        name: hit.candidate_name,
        hits: [],
        exact: [],
        approximate: [],
        approximateOnly: false,
      };
      groups.set(key, group);
    }
    group.hits.push(hit);
    for (const reason of hit.reasons) {
      const list = APPROXIMATE.has(reason) ? group.approximate : group.exact;
      if (!list.includes(reason)) list.push(reason);
    }
  }
  const out = [...groups.values()];
  for (const g of out) g.approximateOnly = g.exact.length === 0 && g.approximate.length > 0;
  return out;
}

import type { CandidateProfile } from "@/lib/api";

export type EvidenceRow = CandidateProfile["evidence"][number];

const key = (field: string, value: string) => `${field}\u0000${value}`;

/**
 * The profile payload gives evidence as field name, value, quote and page only.
 * Attach each row to a profile item by matching field and value; the rest is "other".
 */
export function splitEvidence(profile: CandidateProfile) {
  const byKey = new Map<string, EvidenceRow>();
  for (const row of profile.evidence) {
    const k = key(row.field, row.value);
    if (!byKey.has(k)) byKey.set(k, row);
  }
  const wanted = new Set<string>();
  const want = (field: string, value: string | null | undefined) => {
    if (value) wanted.add(key(field, value));
  };
  want("display_name", profile.display_name);
  want("summary", profile.summary);
  if (profile.years_of_experience !== null) want("years_of_experience", String(profile.years_of_experience));
  for (const e of profile.experiences) {
    want("employer", e.employer);
    want("title", e.title);
  }
  for (const e of profile.education) {
    want("institution", e.institution);
    want("credential", e.credential);
  }
  for (const s of profile.skills) want("name", s);
  for (const c of [...profile.certificates, ...profile.qualifications]) want("name", c.name);

  return {
    find(field: string, value: string | null | undefined): EvidenceRow | undefined {
      return value ? byKey.get(key(field, value)) : undefined;
    },
    other: profile.evidence.filter((row) => !wanted.has(key(row.field, row.value))),
  };
}

import { describe, it, expect } from "vitest";
import { splitEvidence } from "@/lib/evidence";
import type { CandidateProfile } from "@/lib/api";

const profile = {
  id: "c1", display_name: "Amira Khan", summary: null, narrative: null, years_of_experience: 6.5, source: "upload",
  sources: [], contacts: [],
  experiences: [{ employer: "Northwind", title: "Backend engineer" }],
  education: [{ institution: "Univ. of Sharjah", credential: "BSc" }],
  skills: ["Python"], certificates: [{ name: "AWS SA", kind: "certificate" }], qualifications: [],
  applications: [], documents: [], activity: [],
  evidence: [
    { field: "employer", value: "Northwind", quote: "Backend engineer at Northwind", page: 1, quote_verified: true },
    { field: "title", value: "Backend engineer", quote: "Backend engineer at Northwind", page: 1, quote_verified: true },
    { field: "name", value: "Python", quote: "Built services in Python", page: 1, quote_verified: true },
    { field: "name", value: "AWS SA", quote: "AWS Solutions Architect", page: 2, quote_verified: false },
    { field: "institution", value: "Univ. of Sharjah", quote: "BSc, Univ. of Sharjah", page: 2, quote_verified: true },
    { field: "start_date", value: "2018-01-01", quote: "2018 to 2021", page: 1, quote_verified: true },
  ],
} as CandidateProfile;

describe("splitEvidence", () => {
  const { find, other } = splitEvidence(profile);
  it("finds evidence by field and value", () => {
    expect(find("employer", "Northwind")?.page).toBe(1);
    expect(find("name", "Python")?.quote).toMatch(/Python/);
    expect(find("name", "AWS SA")?.quote_verified).toBe(false);
  });
  it("returns undefined when nothing is stored", () => {
    expect(find("name", "Docker")).toBeUndefined();
    expect(find("employer", null)).toBeUndefined();
  });
  it("puts unattached evidence in other", () => {
    expect(other.map((e) => e.field)).toEqual(["start_date"]);
  });
});

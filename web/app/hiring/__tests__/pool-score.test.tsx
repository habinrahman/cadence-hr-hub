// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CandidateMatch, Eligibility, MatchRequirement } from "@/lib/api";
import { yearsLine } from "../matches";
import { Pool } from "../pool";

afterEach(cleanup);

// Shaped like a live GET /hiring-requests/{id}/matches item; names and evidence are made up.
function line(text: string, strength: string, result: string, possible: number | null = null, earned: number | null = null): MatchRequirement {
  return {
    requirement_id: `req-${text}`,
    label: text.endsWith("experience") ? "experience" : "skill",
    text: text.endsWith("experience") ? text.split(" ")[0] : text,
    strength,
    result,
    evidence_id: null,
    evidence: result === "unknown" ? null : `${text} used in production`,
    retrieval: result === "unknown" ? null : "keyword",
    points_possible: possible,
    points_earned: earned,
  };
}

const DISPOSITION: Record<Eligibility, string> = { eligible: "recommended", needs_review: "needs_review", excluded: "excluded" };

function match(
  id: string,
  name: string,
  eligibility: Eligibility,
  score: number | null,
  requirements: MatchRequirement[],
  reason: string,
  years: number | null = null,
): CandidateMatch {
  const mandatory = requirements.filter((r) => r.strength === "mandatory");
  const preferred = requirements.filter((r) => r.strength !== "mandatory");
  const blocking = mandatory.filter((r) => (eligibility === "excluded" ? r.result === "unmet" : r.result !== "meets"));
  return {
    id,
    candidate_id: `cand-${id}`,
    candidate_name: name,
    request_id: "req-1",
    disposition: DISPOSITION[eligibility],
    requirement_met_ratio: 0,
    eligibility,
    match_score: score,
    match_score_exact: score,
    score_max: 100,
    mandatory_met: mandatory.filter((r) => r.result === "meets").length,
    mandatory_total: mandatory.length,
    preferred_met: preferred.filter((r) => r.result === "meets").length,
    preferred_total: preferred.length,
    blocking_requirements: blocking.map((r) => ({
      requirement_id: r.requirement_id,
      name: r.label === "experience" ? `${r.text} years experience` : r.text,
      result: r.result,
    })),
    score_reason: reason,
    explanation: null,
    strengths: [],
    gaps: [],
    processing_version: 1,
    years_of_experience: years,
    location: null,
    requirements,
  };
}

function renderPool(matches: CandidateMatch[]) {
  const shortlist = Object.fromEntries(matches.map((m) => [m.candidate_id, "no" as const]));
  render(
    <Pool
      matches={matches}
      shortlist={shortlist}
      busy={false}
      jobTitle="Engineer"
      onShortlistSelected={vi.fn()}
      onReject={vi.fn()}
      onShare={vi.fn()}
    />,
  );
}

const card = (name: string) => screen.getByRole("heading", { name }).closest("div.space-y-3") as HTMLElement;
const renderedScores = () => screen.queryAllByLabelText(/^Match score \d+ out of 100$/).map((el) => el.textContent);
const order = () => screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);

// Carlos: three technical requirements met, experience unknown. The old arithmetic showed 53/100.
const carlos = () =>
  match(
    "carlos",
    "Carlos",
    "needs_review",
    null,
    [
      line("Python", "mandatory", "meets"),
      line("FastAPI", "mandatory", "meets"),
      line("PostgreSQL", "mandatory", "meets"),
      line("3 years experience", "mandatory", "unknown"),
      line("AWS", "preferred", "unmet"),
    ],
    "Mandatory requirement unresolved: 3 years experience",
  );

// Danila: only the experience requirement met. The old arithmetic showed 18/100.
const danila = () =>
  match(
    "danila",
    "Danila",
    "needs_review",
    null,
    [
      line("Python", "mandatory", "unknown"),
      line("FastAPI", "mandatory", "unknown"),
      line("PostgreSQL", "mandatory", "unknown"),
      line("3 years experience", "mandatory", "meets"),
      line("AWS", "preferred", "unknown"),
    ],
    "Mandatory requirements unresolved: Python, FastAPI, PostgreSQL",
  );

const eligible = (id: string, name: string, score: number, aws: string, reason: string) =>
  match(
    id,
    name,
    "eligible",
    score,
    [
      line("Python", "mandatory", "meets", 17.5, 17.5),
      line("FastAPI", "mandatory", "meets", 17.5, 17.5),
      line("PostgreSQL", "mandatory", "meets", 17.5, 17.5),
      line("3 years experience", "mandatory", "meets", 17.5, 17.5),
      line("AWS", "preferred", aws, 30, aws === "meets" ? 30 : aws === "partial" ? 15 : 0),
    ],
    reason,
  );

describe("candidate pool: the mandatory gate first, then a score for eligible candidates", () => {
  it("shows a score only on eligible cards, as N / 100 — Match", () => {
    renderPool([eligible("e70", "Eligible Seventy", 70, "unknown", "4/4 mandatory requirements met · AWS preferred not found")]);
    const c = card("Eligible Seventy");
    expect(within(c).getByLabelText("Match score 70 out of 100").textContent).toBe("70/ 100");
    expect(within(c).getByText("Match")).toBeTruthy();
    expect(within(c).getByText("4/4 mandatory · 0/1 preferred requirements met")).toBeTruthy();
    expect(within(c).queryByLabelText("Blocking requirements")).toBeNull();
  });

  it("never shows 53/100 for a candidate with an unresolved mandatory requirement", () => {
    renderPool([carlos()]);
    const c = card("Carlos");
    expect(renderedScores()).toEqual([]);
    expect(c.textContent).not.toMatch(/53/);
    expect(within(c).getAllByText("Needs review").length).toBeGreaterThan(0);
    expect(within(c).getByText("3/4 mandatory · 0/1 preferred requirements met")).toBeTruthy();
    const blocking = within(c).getByLabelText("Blocking requirements");
    expect(blocking.textContent).toMatch(/3 years experience — Unknown/);
    expect(within(c).getByText(/No match score: mandatory requirement unresolved: 3 years experience/)).toBeTruthy();
  });

  it("never shows 18/100 for a candidate with three unresolved mandatory requirements", () => {
    renderPool([danila()]);
    const c = card("Danila");
    expect(renderedScores()).toEqual([]);
    expect(c.textContent).not.toMatch(/18/);
    expect(within(c).getByText(/1\/4 mandatory/)).toBeTruthy();
    const blocking = within(c).getByLabelText("Blocking requirements").textContent;
    expect(blocking).toMatch(/Python — Unknown/);
    expect(blocking).toMatch(/FastAPI — Unknown/);
    expect(blocking).toMatch(/PostgreSQL — Unknown/);
  });

  it("hides the per-requirement points of a held candidate, so they cannot be added up into a score", () => {
    renderPool([carlos()]);
    const c = card("Carlos");
    expect(within(c).queryByText(/points earned/)).toBeNull();
    expect(within(c).queryByText(/^\+/)).toBeNull();
  });

  it("names the unmet mandatory requirement on an excluded card", () => {
    const excluded = match(
      "x",
      "Excluded One",
      "excluded",
      null,
      [line("Python", "mandatory", "meets"), line("PostgreSQL", "mandatory", "unmet"), line("AWS", "preferred", "meets")],
      "Mandatory requirement not met: PostgreSQL",
    );
    renderPool([excluded]);
    fireEvent.click(screen.getByRole("radio", { name: /^Excluded/ }));
    const c = card("Excluded One");
    expect(renderedScores()).toEqual([]);
    expect(within(c).getAllByText("Excluded").length).toBeGreaterThan(0);
    expect(within(c).getByLabelText("Blocking requirements").textContent).toMatch(/PostgreSQL — Not met/);
  });

  it("ranks every eligible candidate above held ones, eligible by score and held by mandatory met", () => {
    renderPool([
      danila(),
      carlos(),
      eligible("e70", "Eligible Seventy", 70, "unknown", "4/4 mandatory requirements met · AWS preferred not found"),
      eligible("e85", "Eligible Partial", 85, "partial", "4/4 mandatory requirements met · AWS preferred partly met"),
      eligible("e100", "Eligible Full", 100, "meets", "4/4 mandatory requirements met"),
    ]);
    expect(order()).toEqual(["Eligible Full", "Eligible Partial", "Eligible Seventy", "Carlos", "Danila"]);
    expect(renderedScores()).toEqual(["100/ 100", "85/ 100", "70/ 100"]);
  });

  it("filters eligible and needs-review candidates by the gate", () => {
    renderPool([carlos(), eligible("e100", "Eligible Full", 100, "meets", "4/4 mandatory requirements met")]);
    fireEvent.click(screen.getByRole("radio", { name: /^Eligible/ }));
    expect(order()).toEqual(["Eligible Full"]);
    fireEvent.click(screen.getByRole("radio", { name: /^Needs review/ }));
    expect(order()).toEqual(["Carlos"]);
  });

  it("keeps a rejected candidate one filter away, with a way to restore them", () => {
    const onRestore = vi.fn();
    const rejected = { ...eligible("e100", "Rejected Person", 100, "meets", "4/4 mandatory requirements met"), disposition: "rejected" };
    render(
      <Pool
        matches={[rejected, carlos()]}
        shortlist={{}}
        busy={false}
        poolStatus="confirmed"
        jobTitle="Engineer"
        onShortlistSelected={vi.fn()}
        onReject={vi.fn()}
        onShare={vi.fn()}
        onRestore={onRestore}
      />,
    );
    expect(order()).toEqual(["Carlos"]);
    fireEvent.click(screen.getByRole("radio", { name: /^Rejected/ }));
    expect(order()).toEqual(["Rejected Person"]);
    fireEvent.click(screen.getByRole("button", { name: "Restore to pool" }));
    expect(onRestore).toHaveBeenCalledTimes(1);
  });

  it("explains how an eligible score was built", () => {
    renderPool([eligible("e85", "Eligible Partial", 85, "partial", "4/4 mandatory requirements met · AWS preferred partly met")]);
    expect(screen.getByText(/85 of 100 points earned across 5 requirements/)).toBeTruthy();
    expect(screen.getByText(/only to candidates who meet every mandatory requirement/)).toBeTruthy();
  });

  it("formats years from the payload value", () => {
    expect(yearsLine(4.2)).toBe("4.2 years experience");
    expect(yearsLine(1)).toBe("1 year experience");
    expect(yearsLine(7)).toBe("7 years experience");
    expect(yearsLine(3.25)).toBe("3.3 years experience");
    expect(yearsLine(null)).toBeNull();
    expect(yearsLine(undefined)).toBeNull();
  });
});

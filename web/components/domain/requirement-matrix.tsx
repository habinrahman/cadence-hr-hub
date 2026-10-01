import type { MatchRequirement } from "@/lib/api";
import { VERDICT } from "@/lib/labels";
import { ResponsiveTable } from "@/components/ui/table";
import { StrengthTag } from "@/components/ui/strength";
import { Tag } from "@/components/ui/tag";
import { EvidenceQuote } from "./evidence-quote";

export function shownText(item: { label: string; text: string }) {
  return item.label === "experience" ? `${item.text} years experience` : item.text;
}

export function countMet(requirements: MatchRequirement[]) {
  return { met: requirements.filter((r) => r.result === "meets").length, total: requirements.length };
}

const points = (value: number) => (Number.isInteger(value) ? String(value) : value.toFixed(1));

/** How the score was built: the sum of the points earned per requirement, rounded half up for the headline. */
export function scoreLine(requirements: MatchRequirement[], score?: number | null, exact?: number | null) {
  if (score == null || exact == null) return null;
  const rounded = Number.isInteger(exact) ? "" : ` (${points(exact)} rounded to ${score})`;
  return `${points(exact)} of 100 points earned across ${requirements.length} requirement${requirements.length === 1 ? "" : "s"}${rounded}`;
}

/** Why there is no quote, in words that match the verdict. */
export function noEvidence(r: MatchRequirement): string {
  if (r.result === "unmet") return "Not mentioned anywhere in the CV. The whole CV was read.";
  if (r.result === "unknown" && r.label === "experience") return "Years could not be worked out: the CV has no dated roles Cadence could read.";
  if (r.result === "unknown")
    return `Could not be checked: the CV was read from a scan or has no readable text.${
      r.strength === "preferred" ? " A preferred requirement with no evidence is not treated as a gap." : ""
    }`;
  return "No evidence found.";
}

/** Requirement, verdict and the CV evidence for it, side by side. */
export function RequirementMatrix({ requirements }: { requirements: MatchRequirement[] }) {
  if (requirements.length === 0) return <p className="text-mut">No approved requirements were compared.</p>;
  return (
    <ResponsiveTable
      caption="Requirements compared with this candidate"
      rows={requirements}
      rowKey={(r) => r.requirement_id}
      columns={[
        {
          header: "Requirement",
          primary: true,
          cell: (r) => (
            <span>
              {shownText(r)} <StrengthTag strength={r.strength} />
            </span>
          ),
        },
        {
          header: "Verdict",
          cell: (r) => {
            const verdict = VERDICT[r.result] ?? { label: r.result, tone: "neutral" as const };
            return <Tag tone={verdict.tone}>{verdict.label}</Tag>;
          },
        },
        {
          header: "Points",
          cell: (r) =>
            r.points_possible == null || r.points_earned == null ? (
              <span className="text-mut">—</span>
            ) : (
              <span className="whitespace-nowrap font-semibold">
                +{points(r.points_earned)} <span className="font-normal text-mut">of {points(r.points_possible)}</span>
              </span>
            ),
        },
        {
          header: "Evidence from the CV",
          cell: (r) => (
            <>
              {r.calculation ? <p className="mb-1 text-[13px] font-semibold">{r.calculation}</p> : null}
              {r.evidence ? (
                <EvidenceQuote quote={r.evidence} source={r.retrieval ? `CV · found by ${r.retrieval}` : "CV"} />
              ) : (
                <span className="text-mut">{noEvidence(r)}</span>
              )}
            </>
          ),
        },
      ]}
    />
  );
}

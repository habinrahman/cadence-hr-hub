import type { MatchRequirement } from "@/lib/api";
import { VERDICT } from "@/lib/labels";
import { ResponsiveTable } from "@/components/ui/table";
import { Tag } from "@/components/ui/tag";
import { EvidenceQuote } from "./evidence-quote";

export function shownText(item: { label: string; text: string }) {
  return item.label === "experience" ? `${item.text} years experience` : item.text;
}

export function countMet(requirements: MatchRequirement[]) {
  return { met: requirements.filter((r) => r.result === "meets").length, total: requirements.length };
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
              {shownText(r)} <span className="text-xs font-normal text-mut">· {r.strength}</span>
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
          header: "Evidence from the CV",
          cell: (r) =>
            r.evidence ? (
              <EvidenceQuote quote={r.evidence} source={r.retrieval ? `CV · found by ${r.retrieval}` : "CV"} />
            ) : (
              <span className="text-mut">
                No evidence found.
                {r.result === "unknown" && r.strength === "preferred" ? " A preferred requirement with no evidence is not treated as a gap." : ""}
              </span>
            ),
        },
      ]}
    />
  );
}

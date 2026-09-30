import type { Comparison, Review } from "@/lib/api";
import { decisionCopy, recommendation, summarize, type SignalContext } from "@/lib/compare";
import { Tag } from "@/components/ui/tag";
import { supportingSignals } from "./why-related";

/**
 * What Cadence suggests. It is drawn as a dashed proposal, never as a decision:
 * it has no buttons, and it does not change when the recruiter decides.
 */
export function Recommendation({
  review,
  comparison,
  candidateId,
  context,
}: {
  review: Review;
  comparison: Comparison | null;
  candidateId: string | null;
  context?: SignalContext;
}) {
  const rec = recommendation(review);
  const summary = comparison?.available ? summarize(comparison) : null;
  const support = supportingSignals(review.evidence, candidateId, context);
  return (
    <section aria-labelledby="rec-heading" className="proposal px-3.5 py-3">
      <h2 id="rec-heading" className="flex flex-wrap items-center gap-2 text-xs font-bold uppercase tracking-[0.07em] text-prop-ink">
        <Tag tone="proposed">Proposed by Cadence</Tag>
        <span>Not applied</span>
      </h2>
      <p className="mt-2 text-[17px] font-bold leading-snug">{rec.headline}</p>
      {rec.action ? (
        <p className="mt-0.5">
          Suggested action: <span className="font-semibold">{decisionCopy(rec.action).label}</span>
        </p>
      ) : (
        <p className="mt-0.5">No action is suggested. Choose one yourself.</p>
      )}
      <p className="mt-1 text-xs text-prop-ink">{rec.basis}</p>
      {support.length > 0 ? (
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[13px]">
          {support.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      {summary ? (
        <p className="mt-2 text-[13px]">
          {summary.differences === 0
            ? "No differences were found in the sections that could be compared."
            : `Found in the compared sections: ${summary.added} added, ${summary.changed} changed, ${summary.notFound} not found in the incoming CV.`}
          {summary.notCompared.length > 0 ? ` Not compared: ${summary.notCompared.join(", ").toLowerCase()}.` : ""}
        </p>
      ) : null}
      <p className="mt-2 border-t border-dashed border-prop pt-2 text-xs font-semibold">Cadence recommends. You decide.</p>
    </section>
  );
}

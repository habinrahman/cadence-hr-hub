import type { EvidenceItem } from "@/lib/api";
import { describeSignal } from "@/lib/compare";

const GLYPH = { match: "✓", mismatch: "✗", unknown: "?", info: "≈" } as const;
const KIND_LABEL = { match: "Supports", mismatch: "Against", unknown: "Not available", info: "Measured" } as const;

/**
 * The stored signals the relationship was scored from. Only these are shown: nothing is inferred here,
 * and there is no free-text reasoning.
 */
export function WhyRelated({
  signals,
  candidateId,
  confidence,
}: {
  signals: EvidenceItem[];
  candidateId: string | null;
  confidence: number | null;
}) {
  const relevant = signals.filter((s) => !s.candidate_id || !candidateId || s.candidate_id === candidateId);
  // Weight zero means the signal is informational and is not part of the score.
  const ordered = [...relevant].sort((a, b) => b.weight - a.weight);
  return (
    <section aria-labelledby="why-heading">
      <h2 id="why-heading" className="mb-2 text-xs font-bold uppercase tracking-[0.07em] text-human-ink">
        Why Cadence thinks these are related
      </h2>
      {ordered.length === 0 ? (
        <p className="text-mut">No signals were recorded for this review.</p>
      ) : (
        <ul className="divide-y divide-rule rounded border border-rule bg-panel">
          {ordered.map((signal) => {
            const described = describeSignal(signal);
            return (
              <li key={`${signal.code}-${signal.candidate_id ?? ""}`} className="flex items-start gap-3 px-3 py-2">
                <span aria-hidden="true" className="w-4 shrink-0 text-center font-bold">
                  {GLYPH[described.kind]}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="sr-only">{KIND_LABEL[described.kind]}: </span>
                  {described.text}
                </span>
                {signal.weight > 0 ? <span className="shrink-0 text-xs text-mut">weight {signal.weight}</span> : null}
              </li>
            );
          })}
        </ul>
      )}
      {confidence !== null ? (
        <p className="mt-1.5 text-xs text-mut">
          Signal strength {Math.round(confidence)} / 100, weighted from the signals above. It is a score of these signals, not a
          model&apos;s confidence.
        </p>
      ) : null}
    </section>
  );
}

/** The few strongest supporting signals, for the short version next to the recommendation. */
export function supportingSignals(signals: EvidenceItem[], candidateId: string | null): string[] {
  return signals
    .filter((s) => (!s.candidate_id || !candidateId || s.candidate_id === candidateId) && s.weight > 0)
    .map((s) => describeSignal(s))
    .filter((d) => d.kind === "match")
    .map((d) => d.text)
    .slice(0, 4);
}

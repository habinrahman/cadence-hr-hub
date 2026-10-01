import type { EvidenceItem } from "@/lib/api";
import { describeSignal, type SignalContext } from "@/lib/compare";

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
  context,
}: {
  signals: EvidenceItem[];
  candidateId: string | null;
  confidence: number | null;
  context?: SignalContext;
}) {
  // "Not a byte-identical file" carries no weight and says nothing useful, so only an identical file is listed.
  const relevant = signals.filter(
    (s) =>
      (!s.candidate_id || !candidateId || s.candidate_id === candidateId) && !(s.code === "document_hash" && s.state !== "matched"),
  );
  // Weight zero means the signal is informational and is not part of the score.
  const ordered = [...relevant].sort((a, b) => b.weight - a.weight);
  return (
    <section aria-labelledby="why-heading">
      <h2 id="why-heading" className="mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-mut">
        Why Cadence thinks these are related
      </h2>
      {ordered.length === 0 ? (
        <p className="text-mut">No signals were recorded for this review.</p>
      ) : (
        <ul className="divide-y divide-rule border border-rule bg-panel">
          {ordered.map((signal) => {
            const described = describeSignal(signal, context);
            return (
              <li key={`${signal.code}-${signal.candidate_id ?? ""}`} className="flex items-start gap-3 px-3 py-2">
                <span aria-hidden="true" className="w-4 shrink-0 text-center font-bold">
                  {GLYPH[described.kind]}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="sr-only">{KIND_LABEL[described.kind]}: </span>
                  {described.text}
                </span>
                {signal.weight > 0 && signal.state !== "unknown" ? (
                  <span className="shrink-0 text-xs text-mut">weight {signal.weight}</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
      {confidence !== null ? (
        <p className="mt-1.5 text-xs text-mut">
          Same-person confidence {Math.round(confidence)} / 100, from the email, phone, name and content overlap above. Signals
          that are not available are left out and do not lower it; a different email or phone does. Dates only decide update
          or duplicate. It is a score of these signals, not a model&apos;s confidence.
        </p>
      ) : null}
    </section>
  );
}

/** The few strongest supporting signals, for the short version next to the recommendation. */
export function supportingSignals(signals: EvidenceItem[], candidateId: string | null, context?: SignalContext): string[] {
  return signals
    .filter((s) => (!s.candidate_id || !candidateId || s.candidate_id === candidateId) && s.weight > 0)
    .map((s) => describeSignal(s, context))
    .filter((d) => d.kind === "match")
    .map((d) => d.text)
    .slice(0, 4);
}

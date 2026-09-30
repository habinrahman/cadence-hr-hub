import type { EvidenceItem } from "@/lib/api";
import { SIGNAL_LABELS, SIGNAL_STATE_LABELS } from "@/lib/labels";

const GLYPH: Record<string, string> = { matched: "✓", unmatched: "✗", unknown: "?", recorded: "≈" };

/** The signals a relationship score is built from. State is text plus a glyph, not colour. */
export function SignalList({ evidence }: { evidence: EvidenceItem[] }) {
  if (evidence.length === 0) return <p className="text-mut">No signals were recorded.</p>;
  return (
    <ul className="divide-y divide-rule rounded border border-rule bg-panel">
      {evidence.map((item) => (
        <li key={`${item.code}-${item.candidate_id ?? ""}`} className="flex items-center justify-between gap-3 px-3 py-1.5">
          <span>{SIGNAL_LABELS[item.code] ?? item.code}</span>
          <span className="text-mut">
            <span aria-hidden="true" className="mr-1 font-bold text-ink">
              {GLYPH[item.state] ?? "·"}
            </span>
            {SIGNAL_STATE_LABELS[item.state] ?? item.state}
            {item.state === "recorded" && item.value !== null ? ` ${Math.round(item.value * 100)}%` : ""}
          </span>
        </li>
      ))}
    </ul>
  );
}

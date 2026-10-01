import type { ReactNode } from "react";
import type { Tone } from "@/lib/labels";

/**
 * Provenance labels. "Proposed" is dashed amber (not applied); "Decided" is solid blue (a person did this).
 * Everything else is a quiet outlined label. Status is always carried by the words, never by colour alone.
 */
const TONE: Record<Tone, string> = {
  proposed: "proposal text-prop-ink",
  decided: "border border-human-ink bg-human-ink text-white",
  ok: "border border-ok/40 bg-ok-bg text-ok-ink",
  warn: "border border-prop/50 bg-prop-bg text-prop-ink",
  bad: "border border-bad/40 bg-bad-bg text-bad-ink",
  unknown: "hatch border border-rule text-mut",
  neutral: "border border-rule bg-inset text-ink",
};

export function Tag({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-block rounded-[2px] px-1.5 py-px font-mono text-[10.5px] font-medium uppercase leading-[1.6] tracking-[0.08em] ${TONE[tone]}`}
    >
      {children}
    </span>
  );
}

const DOT: Record<Tone, string> = {
  proposed: "bg-prop",
  decided: "bg-human",
  ok: "bg-ok",
  warn: "bg-prop",
  bad: "bg-bad",
  unknown: "bg-rule-strong",
  neutral: "bg-rule-strong",
};

const TEXT: Record<Tone, string> = {
  proposed: "text-prop-ink",
  decided: "text-human-ink",
  ok: "text-ok-ink",
  warn: "text-prop-ink",
  bad: "text-bad-ink",
  unknown: "text-mut",
  neutral: "text-mut",
};

/** Record status as the approved designs show it: a dot and mono text ("● Profiled"). */
export function StatusText({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 font-mono text-[12px] ${TEXT[tone]}`}>
      <span aria-hidden="true" className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT[tone]}`} />
      {children}
    </span>
  );
}

/** A skill or keyword chip, as in the candidate table and record. */
export function Pill({ children }: { children: ReactNode }) {
  return (
    <span className="inline-block rounded-[2px] border border-rule bg-inset px-2 py-0.5 text-[12px] text-ink">{children}</span>
  );
}

import type { ReactNode } from "react";
import type { Tone } from "@/lib/labels";

const TONE: Record<Tone, string> = {
  proposed: "proposal text-prop-ink",
  decided: "border border-human-ink bg-human-ink text-white",
  ok: "border border-ok-ink bg-ok-ink text-white",
  warn: "border border-prop bg-prop-bg text-prop-ink",
  bad: "border border-bad-ink bg-bad-ink text-white",
  unknown: "hatch border border-rule-strong text-mut",
  neutral: "border border-rule-strong bg-panel text-ink",
};

/** Status is always carried by the words, never by colour alone. */
export function Tag({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-block rounded-[3px] px-1.5 py-px text-[11px] font-bold uppercase leading-[1.5] tracking-wider ${TONE[tone]}`}
    >
      {children}
    </span>
  );
}

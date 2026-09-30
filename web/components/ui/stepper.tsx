import type { Step } from "@/lib/lifecycle";

const STATE_TEXT = { done: "Done", current: "Current", locked: "Locked" } as const;

const STYLE = {
  done: "bg-ok-ink text-white",
  current: "bg-human-ink text-white",
  locked: "bg-inset text-mut",
} as const;

/** Lifecycle derived from real data. State is written out in words as well as colour. */
export function Stepper({ steps, label = "Request progress" }: { steps: Step[]; label?: string }) {
  return (
    <ol aria-label={label} className="flex flex-col overflow-hidden rounded border border-rule-strong md:flex-row">
      {steps.map((step, index) => (
        <li
          key={step.key}
          aria-current={step.state === "current" ? "step" : undefined}
          className={`flex-1 border-t border-white/20 px-3 py-2 first:border-t-0 md:border-l md:border-t-0 md:first:border-l-0 ${STYLE[step.state]}`}
        >
          <span className="block text-[11px] font-bold uppercase tracking-wider opacity-90">
            {index + 1} · {STATE_TEXT[step.state]}
          </span>
          <span className="block text-[14px] font-bold">{step.label}</span>
          <span className="block text-xs">{step.detail}</span>
        </li>
      ))}
    </ol>
  );
}

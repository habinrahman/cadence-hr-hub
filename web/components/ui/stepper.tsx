import type { Step } from "@/lib/lifecycle";
import { Icon } from "./icons";

const STATE_TEXT = { done: "Done", current: "Current", locked: "Not yet" } as const;

/**
 * The request lifecycle, worked out from real data. Each stage says where it stands in words as well as by its marker.
 */
export function Stepper({ steps, label = "Request progress" }: { steps: Step[]; label?: string }) {
  return (
    <ol aria-label={label} className="grid grid-cols-[minmax(0,1fr)] border border-rule bg-panel sm:grid-cols-3 xl:grid-cols-6">
      {steps.map((step, index) => (
        <li
          key={step.key}
          aria-current={step.state === "current" ? "step" : undefined}
          className={`relative flex gap-3 border-t border-rule px-4 py-3.5 first:border-t-0 sm:[&:nth-child(-n+3)]:border-t-0 xl:border-t-0 xl:border-l xl:first:border-l-0 sm:border-l sm:[&:nth-child(3n+1)]:border-l-0 xl:[&:nth-child(3n+1)]:border-l ${
            step.state === "current" ? "bg-human-bg" : ""
          }`}
        >
          <span
            aria-hidden="true"
            className={`mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-mono text-[11px] ${
              step.state === "done"
                ? "bg-ok text-white"
                : step.state === "current"
                  ? "bg-human text-white"
                  : "border border-rule-strong/60 bg-panel text-mut"
            }`}
          >
            {step.state === "done" ? <Icon name="check" size={13} strokeWidth={2.4} /> : index + 1}
          </span>
          <span className="min-w-0">
            <span className="block font-mono text-[10.5px] uppercase tracking-[0.12em] text-mut">{STATE_TEXT[step.state]}</span>
            <span className="block text-[14px] font-semibold leading-tight">{step.label}</span>
            <span className="block text-[12px] text-mut">{step.detail}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

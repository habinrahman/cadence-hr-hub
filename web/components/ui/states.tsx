import type { ReactNode } from "react";
import { describeError } from "@/lib/errors";
import { Button } from "./button";

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="rounded border border-dashed border-rule-strong bg-panel px-5 py-8 text-center">
      <p className="text-base font-bold">{title}</p>
      {body ? <p className="mx-auto mt-1 max-w-md text-mut">{body}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { title, body } = describeError(error);
  return (
    <div role="alert" className="rounded border border-bad-ink bg-bad-bg px-4 py-3">
      <p className="font-bold text-bad-ink">{title}</p>
      <p className="mt-0.5 text-ink">{body}</p>
      {onRetry ? (
        <div className="mt-3">
          <Button onClick={onRetry}>Try again</Button>
        </div>
      ) : null}
    </div>
  );
}

/** Inline notice for a result that matters (kept in the page, not only in a toast). */
export function Notice({ tone = "ok", children }: { tone?: "ok" | "warn"; children: ReactNode }) {
  const style = tone === "ok" ? "border-ok-ink bg-ok-bg" : "border-prop bg-prop-bg";
  return (
    <p role="status" className={`rounded border px-3 py-2 text-[13px] ${style}`}>
      {children}
    </p>
  );
}

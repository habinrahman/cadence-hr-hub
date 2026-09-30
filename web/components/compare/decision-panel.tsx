"use client";

import { useState, type ReactNode } from "react";
import type { Review } from "@/lib/api";
import { decisionCopy, isDecided } from "@/lib/compare";
import { labelAudit } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Tag } from "@/components/ui/tag";

/**
 * The recruiter's decision. It is the only place that can change anything, and every action first asks for
 * confirmation in words that describe what the backend will actually do.
 */
export function DecisionPanel({
  review,
  recommendedAction,
  busy,
  candidateMerged,
  candidateName,
  onDecide,
  record,
}: {
  review: Review;
  recommendedAction: string | null;
  busy: boolean;
  candidateMerged: boolean;
  candidateName: string | null;
  onDecide: (action: string) => void;
  record?: ReactNode;
}) {
  const [confirming, setConfirming] = useState<string | null>(null);
  const decided = isDecided(review.status);
  const copy = confirming ? decisionCopy(confirming) : null;

  return (
    <section id="decision" aria-labelledby="decision-heading" className="rounded border-2 border-human-ink bg-panel px-3.5 py-3">
      <h2 id="decision-heading" className="flex flex-wrap items-center gap-2 text-xs font-bold uppercase tracking-[0.07em] text-human-ink">
        Your decision
        {decided ? <Tag tone="decided">Decided</Tag> : null}
      </h2>

      {decided ? (
        <p className="mt-2 font-semibold">{labelAudit(review.status)}</p>
      ) : (
        <>
          <p className="mt-1 text-[13px] text-mut">
            Nothing changes until you choose. The previous CV is never deleted; it stays in the candidate&apos;s history.
          </p>
          {candidateMerged ? (
            <p role="status" className="hatch mt-2 rounded border border-rule-strong px-2.5 py-1.5 text-[13px]">
              This candidate was merged into another profile, so attaching the CV to it is disabled.
            </p>
          ) : null}
          <ul className="mt-3 space-y-2">
            {review.offered_actions.map((action) => {
              const text = decisionCopy(action);
              const blocked = candidateMerged && action !== "create_separate_candidate";
              const suggested = action === recommendedAction;
              return (
                <li key={action}>
                  <Button
                    variant={suggested ? "primary" : "secondary"}
                    className="w-full justify-start whitespace-normal py-2 text-left"
                    busy={busy}
                    disabled={blocked}
                    onClick={() => setConfirming(action)}
                  >
                    {text.label}
                  </Button>
                  {suggested ? <span className="mt-0.5 block text-xs text-prop-ink">Suggested by Cadence</span> : null}
                </li>
              );
            })}
          </ul>
        </>
      )}

      {record ? <div className="mt-3 border-t border-rule pt-2">{record}</div> : null}

      <ConfirmDialog
        open={confirming !== null}
        title={copy?.title ?? ""}
        body={
          <div className="space-y-2">
            {candidateName ? <p className="font-semibold break-words">{candidateName}</p> : null}
            <p>{copy?.body}</p>
            <p className="text-xs text-mut">This decision is recorded in the audit trail with the time it was made.</p>
          </div>
        }
        confirmLabel={copy?.confirmLabel ?? "Confirm"}
        tone={copy?.tone ?? "primary"}
        busy={busy}
        onConfirm={() => {
          const action = confirming;
          setConfirming(null);
          if (action) onDecide(action);
        }}
        onCancel={() => setConfirming(null)}
      />
    </section>
  );
}

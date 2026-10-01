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
  const copy = confirming ? decisionCopy(confirming, review.document_id != null) : null;

  return (
    <section id="decision" aria-labelledby="decision-heading" className="border border-human-ink bg-panel">
      <h2
        id="decision-heading"
        className="flex flex-wrap items-center justify-between gap-2 bg-human-ink px-4 py-2.5 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-white"
      >
        Your decision
        {decided ? <span className="border border-white/70 px-1.5 py-px text-[10.5px]">Decided</span> : null}
      </h2>
      <div className="px-4 py-3.5">
      {decided ? (
        <p className="font-semibold">{labelAudit(review.status)}</p>
      ) : (
        <>
          <p className="text-[13px] text-mut">
            Nothing changes until you choose. Merge keeps the previous CV in the candidate&apos;s history. Delete Duplicate
            archives only this duplicate upload; the candidate and their current CV are never touched.
          </p>
          {candidateMerged ? (
            <p role="status" className="hatch mt-2 border border-rule-strong px-2.5 py-1.5 text-[13px]">
              This candidate was merged into another profile, so attaching the CV to it is disabled.
            </p>
          ) : null}
          {(() => {
            const suggested = recommendedAction && review.offered_actions.includes(recommendedAction) ? recommendedAction : null;
            const others = review.offered_actions.filter((action) => action !== suggested);
            const button = (action: string, main: boolean) => {
              const text = decisionCopy(action, review.document_id != null);
              return (
                <Button
                  variant={main ? "primary" : "secondary"}
                  size={main ? "lg" : "md"}
                  className="w-full justify-start whitespace-normal py-2.5 text-left"
                  busy={busy}
                  disabled={candidateMerged && action !== "create_separate_candidate"}
                  onClick={() => setConfirming(action)}
                >
                  {text.label}
                </Button>
              );
            };
            return (
              <>
                {suggested ? (
                  <div className="mt-3">
                    {button(suggested, true)}
                    <span className="mt-0.5 block text-xs text-prop-ink">Suggested by Cadence</span>
                  </div>
                ) : null}
                {others.length > 0 ? (
                  <div className={suggested ? "mt-4 border-t border-rule pt-3" : "mt-3"}>
                    {suggested ? <p className="mb-1.5 text-[12px] text-mut">Or, if the evidence says otherwise:</p> : null}
                    <ul className="space-y-1.5">
                      {others.map((action) => (
                        <li key={action}>{button(action, false)}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            );
          })()}
        </>
      )}

      {record ? <div className="mt-3 border-t border-rule pt-2">{record}</div> : null}
      </div>

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

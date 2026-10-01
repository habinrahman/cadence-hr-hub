"use client";

import { useState } from "react";
import type { Review } from "@/lib/api";
import { decisionCopy } from "@/lib/compare";
import { RELATIONSHIP_LABELS, actionLabel, labelAudit } from "@/lib/labels";
import { plural } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Tag } from "@/components/ui/tag";
import { DecisionCase } from "./decision-case";
import { SignalList } from "./signal-list";

/**
 * The one implementation of the relationship review, used by intake, sourced candidates and Excel rows.
 * The recommendation is a proposal. Nothing changes until a person chooses an action.
 */
export function RelationshipReview({
  review,
  targetId,
  onTarget,
  busy,
  onDecide,
  candidateHref,
  compact = false,
}: {
  review: Review;
  targetId?: string;
  onTarget?: (id: string) => void;
  busy: boolean;
  onDecide: (action: string) => void;
  candidateHref?: (id: string) => string;
  compact?: boolean;
}) {
  const [confirming, setConfirming] = useState<string | null>(null);
  const hasDocument = review.document_id != null;
  const copy = confirming ? decisionCopy(confirming, hasDocument) : null;
  const pending = review.status === "pending";
  const relationship = review.likely_relationship
    ? (RELATIONSHIP_LABELS[review.likely_relationship] ?? review.likely_relationship)
    : "Not classified";
  const existing = review.candidates.length;
  const foundText = review.ambiguous
    ? `This matches ${plural(existing, "existing profile")}. A person has to choose which one, or say it is someone new.`
    : existing > 0
      ? `Overlaps ${plural(existing, "existing profile")}: ${review.candidates.map((c) => c.display_name ?? "Unnamed candidate").join(", ")}.`
      : "No existing profile is linked to this review.";

  const proposed = pending ? (
    review.recommended_action ? (
      <div>
        <p className="font-semibold">
          {relationship}: {actionLabel(review.recommended_action, hasDocument)}
        </p>
        {review.confidence !== null ? (
          <p className="mt-0.5 text-xs text-prop-ink">
            Same-person confidence {Math.round(review.confidence)} / 100, from the signals above. Signals that are not
            available do not lower it. It is not a model&apos;s confidence.
          </p>
        ) : null}
      </div>
    ) : (
      <p>
        Cadence is not confident enough to propose an action ({relationship.toLowerCase()}). Choose one below.
      </p>
    )
  ) : null;

  return (
    <>
    <DecisionCase
      hue="rel"
      found={
        <div>
          <p className="font-semibold">{relationship}</p>
          <p className="text-mut">{foundText}</p>
        </div>
      }
      evidence={compact ? undefined : <SignalList evidence={review.evidence} />}
      proposed={proposed}
      decision={
        pending ? (
          <div className="space-y-3">
            {review.candidates.length > 1 && onTarget ? (
              <div>
                <label htmlFor={`target-${review.id}`} className="mb-1 block text-[13px] font-semibold">
                  Which existing candidate?
                </label>
                <select
                  id={`target-${review.id}`}
                  className="block min-h-11 w-full rounded border border-rule-strong bg-panel px-2.5 sm:min-h-9"
                  value={targetId ?? ""}
                  onChange={(event) => onTarget(event.target.value)}
                >
                  {review.candidates.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.display_name ?? "Unnamed candidate"}
                    </option>
                  ))}
                </select>
                {candidateHref && targetId ? (
                  <a className="mt-1 inline-block text-xs" href={candidateHref(targetId)} target="_blank" rel="noreferrer">
                    Open the selected profile in a new tab
                  </a>
                ) : null}
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              {review.offered_actions.map((action) => (
                <Button
                  key={action}
                  variant={action === review.recommended_action ? "primary" : "secondary"}
                  busy={busy}
                  onClick={() => setConfirming(action)}
                >
                  {actionLabel(action, hasDocument)}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <p>
            <Tag tone="decided">Decided</Tag> <span className="font-semibold">{labelAudit(review.status)}</span>
          </p>
        )
      }
    />
    <ConfirmDialog
      open={confirming !== null}
      title={copy?.title ?? ""}
      body={
        <div className="space-y-2">
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
    </>
  );
}

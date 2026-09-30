"use client";

import { useId, useState } from "react";
import { getReview, listHiringMatches, type CandidateMatch, type Review } from "@/lib/api";
import { ACTION_LABELS, DISPOSITION, QUEUE_TYPE, RELATIONSHIP_LABELS } from "@/lib/labels";
import { plural, relativeAge } from "@/lib/format";
import type { QueueGroup } from "@/lib/queue";
import { Button, LinkButton } from "@/components/ui/button";
import { HUE_TEXT, PanelRow } from "@/components/ui/panel";
import { Tag } from "@/components/ui/tag";
import { ErrorState } from "@/components/ui/states";
import { Skeleton } from "@/components/ui/skeleton";
import { SignalList } from "@/components/domain/signal-list";
import { countMet } from "@/components/domain/requirement-matrix";

function documentIdFromHref(href: string): string | null {
  const query = href.split("?")[1];
  return query ? new URLSearchParams(query).get("document") : null;
}

function ctaFor(group: QueueGroup, atLeast: boolean): string {
  const base = QUEUE_TYPE[group.type]?.cta ?? "Open";
  if (group.type === "requirement_approval" && group.count > 1 && !atLeast) return `Review ${group.count} requirements`;
  return base;
}

const PREVIEW_LIMIT = 8;

type Preview =
  | { kind: "review"; review: Review }
  | { kind: "matches"; matches: CandidateMatch[] };

export function InboxRow({ group, atLeast = false, showWhy = true }: { group: QueueGroup; atLeast?: boolean; showWhy?: boolean }) {
  const meta = QUEUE_TYPE[group.type] ?? {
    label: group.type.replaceAll("_", " "),
    hue: "req" as const,
    why: "",
    cta: "Open",
  };
  const documentId = group.type === "relationship_review" ? documentIdFromHref(group.href) : null;
  const canPreview = documentId !== null || (group.type === "match_review" && group.requestId !== null);

  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const regionId = useId();

  async function load() {
    setLoading(true);
    setError(null);
    try {
      if (documentId) setPreview({ kind: "review", review: await getReview(documentId) });
      else if (group.requestId) setPreview({ kind: "matches", matches: (await listHiringMatches(group.requestId)).matches });
    } catch (reason) {
      setError(reason);
    } finally {
      setLoading(false);
    }
  }

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !preview && !loading) void load();
  }

  const label = [meta.label, group.count > 1 || atLeast ? `${group.count}${atLeast ? "+" : ""}` : null, relativeAge(group.created_at)]
    .filter(Boolean)
    .join(" · ");

  return (
    <PanelRow hue={meta.hue}>
      <p className={`font-mono text-[11px] font-bold uppercase tracking-wide ${HUE_TEXT[meta.hue]}`}>{label}</p>
      <h3 className="mt-0.5 break-words text-base font-bold">{group.subject}</h3>
      {group.names.length > 0 ? (
        <p className="text-mut">
          {group.names.length <= 3
            ? group.names.join(", ")
            : `${group.names.slice(0, 3).join(", ")} and ${group.names.length - 3} more`}
        </p>
      ) : null}
      {meta.why && showWhy ? <p className="mt-1 text-mut">{meta.why}</p> : null}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <LinkButton variant="primary" href={documentId ? `/compare?document=${documentId}` : group.href}>
          {ctaFor(group, atLeast)} →
        </LinkButton>
        {canPreview ? (
          <Button variant="quiet" aria-expanded={open} aria-controls={regionId} onClick={toggle}>
            {open ? "Hide evidence" : "Preview evidence"}
          </Button>
        ) : null}
      </div>
      {open ? (
        <div id={regionId} className="mt-3" aria-busy={loading}>
          {loading ? <Skeleton lines={4} /> : null}
          {error ? <ErrorState error={error} onRetry={() => void load()} /> : null}
          {preview?.kind === "review" ? <ReviewPreview review={preview.review} /> : null}
          {preview?.kind === "matches" ? <MatchPreview matches={preview.matches} /> : null}
        </div>
      ) : null}
    </PanelRow>
  );
}

function ReviewPreview({ review }: { review: Review }) {
  const relationship = review.likely_relationship
    ? (RELATIONSHIP_LABELS[review.likely_relationship] ?? review.likely_relationship)
    : "Not classified";
  return (
    <div className="space-y-2">
      <p>
        <span className="font-semibold">{relationship}.</span>{" "}
        <span className="text-mut">
          Overlaps {plural(review.candidates.length, "existing profile")}
          {review.candidates.length ? `: ${review.candidates.map((c) => c.display_name ?? "Unnamed candidate").join(", ")}` : ""}.
        </span>
      </p>
      <SignalList evidence={review.evidence} />
      <div className="proposal px-3 py-2">
        <Tag tone="proposed">Proposed by Cadence</Tag>{" "}
        {review.status !== "pending" ? (
          <span>Already decided.</span>
        ) : review.recommended_action ? (
          <span>
            {ACTION_LABELS[review.recommended_action] ?? review.recommended_action}
            {review.confidence !== null ? (
              <span className="block text-xs text-prop-ink">
                Signal strength {Math.round(review.confidence)} / 100, weighted from the signals above. Not applied.
              </span>
            ) : null}
          </span>
        ) : (
          <span>No action proposed. Below the high-confidence setting.</span>
        )}
      </div>
    </div>
  );
}

function MatchPreview({ matches }: { matches: CandidateMatch[] }) {
  if (matches.length === 0) return <p className="text-mut">No matches have been run for this request.</p>;
  return (
    <div>
    <ul className="divide-y divide-rule rounded border border-rule bg-panel">
      {matches.slice(0, PREVIEW_LIMIT).map((m) => {
        const disposition = DISPOSITION[m.disposition] ?? { label: m.disposition, tone: "neutral" as const };
        const { met, total } = countMet(m.requirements);
        return (
          <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
            <span className="min-w-0 break-words font-semibold">{m.candidate_name ?? "Unnamed candidate"}</span>
            <span className="flex items-center gap-2 text-mut">
              {met} of {total} met <Tag tone={disposition.tone}>{disposition.label}</Tag>
            </span>
          </li>
        );
      })}
    </ul>
    {matches.length > PREVIEW_LIMIT ? (
      <p className="mt-1 text-xs text-mut">
        {matches.length - PREVIEW_LIMIT} more candidates are in the request. Open it to review them all.
      </p>
    ) : null}
    </div>
  );
}

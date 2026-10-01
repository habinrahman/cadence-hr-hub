"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { getDashboard, type Dashboard } from "@/lib/api";
import { recommendation } from "@/lib/compare";
import { QUEUE_TYPE, actionLabel, type Hue } from "@/lib/labels";
import { relativeAge, shortDate } from "@/lib/format";
import { groupQueue, type QueueGroup } from "@/lib/queue";
import { useAsync } from "@/lib/use-async";
import { LinkButton } from "@/components/ui/button";
import { Icon, type IconName } from "@/components/ui/icons";
import { IconTile, PageHeader, Panel } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { StatusText } from "@/components/ui/tag";

/** The dashboard lists at most 20 rows per kind but carries the exact count of each. */
const TYPE_COUNT: Record<string, keyof Dashboard["counts"]> = {
  relationship_review: "relationship_reviews",
  requirement_approval: "requirements_awaiting_approval",
  match_review: "matches_awaiting_review",
  share_approval: "shares_awaiting_approval",
};

const ICON: Record<string, IconName> = {
  relationship_review: "compare",
  requirement_approval: "file",
  match_review: "users",
  share_approval: "shield",
};

const STATUS: Record<string, string> = {
  relationship_review: "Awaiting decision",
  requirement_approval: "Proposed",
  match_review: "Awaiting review",
  share_approval: "Awaiting approval",
};

function documentIdFromHref(href: string): string | null {
  const query = href.split("?")[1];
  return query ? new URLSearchParams(query).get("document") : null;
}

/** Relationship reviews open the comparison workspace; everything else opens where the backend points. */
function actionFor(group: QueueGroup): { href: string; label: string } {
  const documentId = group.type === "relationship_review" ? documentIdFromHref(group.href) : null;
  if (documentId) return { href: `/compare?document=${documentId}`, label: "Compare & decide" };
  const label =
    group.type === "requirement_approval"
      ? "Review requirements"
      : group.type === "match_review"
        ? "Review matches"
        : group.type === "share_approval"
          ? "Review share"
          : "Open";
  return { href: group.href, label };
}

export function ReviewQueue() {
  const router = useRouter();
  const params = useSearchParams();
  const filter = params.get("type") ?? "all";
  const { data: desk, error, loading, reload } = useAsync(() => getDashboard(), []);

  // The work-queue endpoint returns only the newest 50 rows across all kinds, so hundreds of match rows
  // would hide every other decision. The dashboard lists each kind separately, with exact counts.
  const rows = useMemo(
    () =>
      desk ? [...desk.relationship_reviews, ...desk.requirements_awaiting_approval, ...desk.matches_awaiting_review, ...desk.shares_awaiting_approval] : [],
    [desk],
  );
  const groups = useMemo(() => groupQueue(rows), [rows]);
  const truth = (type: string) => (desk ? desk.counts[TYPE_COUNT[type]] : 0);
  const loadedRows = useMemo(() => {
    const out: Record<string, number> = {};
    for (const r of rows) out[r.type] = (out[r.type] ?? 0) + 1;
    return out;
  }, [rows]);
  const truncated = (type: string) => truth(type) > (loadedRows[type] ?? 0);
  const total = Object.keys(TYPE_COUNT).reduce((sum, type) => sum + truth(type), 0);
  const shown = filter === "all" ? groups : groups.filter((g) => g.type === filter);

  const choose = (next: string) => router.replace(next === "all" ? "/queue" : `/queue?type=${next}`);

  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Review queue"
        sub="Decisions that need a person. Cadence proposes; nothing changes until you decide, and opening an item does not change it."
      />

      {error ? <ErrorState error={error} onRetry={reload} /> : null}
      {loading && !desk ? (
        <div aria-busy="true" aria-label="Loading the review queue">
          <PanelSkeleton rows={5} />
        </div>
      ) : null}

      {desk ? (
        <>
          <div role="group" aria-label="Filter by type" className="mb-4 flex flex-wrap gap-2">
            {[["all", "All", total] as const, ...Object.keys(TYPE_COUNT).map((t) => [t, QUEUE_TYPE[t].label, truth(t)] as const)].map(
              ([key, label, count]) => (
                <button
                  key={key}
                  type="button"
                  aria-pressed={filter === key}
                  onClick={() => choose(key)}
                  className={`inline-flex min-h-11 items-center gap-2 rounded-[2px] border px-3.5 text-[13px] sm:min-h-9 ${
                    filter === key ? "border-nav bg-nav text-white" : "border-rule bg-panel text-ink hover:border-rule-strong"
                  }`}
                >
                  {label}
                  <span className={`font-mono text-[12px] ${filter === key ? "text-nav-ink" : "text-mut"}`}>{count}</span>
                </button>
              ),
            )}
          </div>

          {shown.length === 0 ? (
            <EmptyState title="Nothing needs a decision" body="New CVs, requests and matches appear here when they need you." />
          ) : (
            <Panel as="section" className="overflow-hidden">
              <h2 className="sr-only">Waiting decisions</h2>
              <div
                aria-hidden="true"
                className="hidden grid-cols-[13rem_minmax(0,1.1fr)_minmax(0,1.3fr)_9.5rem_6.5rem_11rem] gap-4 border-b border-rule bg-inset px-5 py-3 font-mono text-[11px] uppercase tracking-[0.12em] text-mut xl:grid"
              >
                <span>Type</span>
                <span>Subject</span>
                <span>Why it needs attention</span>
                <span>Status</span>
                <span>Created</span>
                <span className="text-right">Action</span>
              </div>
              <ul>
                {shown.map((group) => {
                  const meta = QUEUE_TYPE[group.type] ?? { label: group.type, hue: "req" as Hue, why: "", cta: "Open" };
                  const action = actionFor(group);
                  const more = truncated(group.type) ? "+" : "";
                  return (
                    <li
                      key={group.key}
                      className="grid grid-cols-[minmax(0,1fr)] gap-x-4 gap-y-2 border-t border-rule px-5 py-4 first:border-t-0 xl:grid-cols-[13rem_minmax(0,1.1fr)_minmax(0,1.3fr)_9.5rem_6.5rem_11rem] xl:items-center"
                    >
                      <span className="flex items-center gap-3">
                        <IconTile name={ICON[group.type] ?? "inbox"} tone={meta.hue} />
                        <span className="text-[13px] font-semibold">
                          {meta.label}
                          {group.count > 1 ? <span className="ml-1 font-mono text-[12px] font-normal text-mut">×{group.count}{more}</span> : null}
                        </span>
                      </span>
                      <span className="min-w-0">
                        <span className="block break-words text-[14px] font-semibold text-ink">{group.subject}</span>
                        {group.names.length > 0 ? (
                          <span className="block truncate text-[12.5px] text-mut">
                            {group.names.slice(0, 3).join(", ")}
                            {group.names.length > 3 ? ` and ${group.names.length - 3} more` : ""}
                          </span>
                        ) : null}
                      </span>
                      <span className="text-[13px] text-mut">
                        {group.type === "relationship_review" && group.relationship ? (
                          group.recommendedAction ? (
                            <>
                              <strong className="block font-semibold text-ink">
                                {group.confidence !== null ? (
                                  <span title="Same-person confidence out of 100, from the matching details. Missing details do not lower it. Not a model's confidence.">
                                    {Math.round(group.confidence)} / 100 —{" "}
                                  </span>
                                ) : null}
                                {recommendation({ likely_relationship: group.relationship, recommended_action: group.recommendedAction, confidence: group.confidence, ambiguous: false }).headline}
                              </strong>
                              Suggested: {actionLabel(group.recommendedAction)}. Open to see the evidence and decide.
                            </>
                          ) : (
                            <>
                              <strong className="block font-semibold text-ink">Needs your choice</strong>
                              Not confident enough to recommend an action. Open to compare.
                            </>
                          )
                        ) : (
                          meta.why
                        )}
                      </span>
                      <span>
                        <StatusText tone="proposed">{STATUS[group.type] ?? group.status}</StatusText>
                      </span>
                      <span className="text-[13px] text-mut" title={shortDate(group.created_at)}>
                        {relativeAge(group.created_at)}
                      </span>
                      <span className="xl:text-right">
                        <LinkButton variant="primary" href={action.href} className="w-full sm:w-auto">
                          {action.label} <Icon name="arrowUpRight" size={15} />
                        </LinkButton>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </Panel>
          )}

          {Object.keys(TYPE_COUNT)
            .filter((type) => truncated(type) && (filter === "all" || filter === type))
            .map((type) => (
              <p key={type} className="mt-2 text-[12.5px] text-mut">
                Showing {loadedRows[type] ?? 0} of {truth(type)} {QUEUE_TYPE[type].label.toLowerCase()} rows. The server lists at most 20 of
                each kind here; open a request to see all of its candidates.
              </p>
            ))}
          {desk.counts.open_problem_reports > 0 ? (
            <p className="mt-4 text-[13px]">
              Also waiting: <Link href="/reports" prefetch={false}>{desk.counts.open_problem_reports} open problem report{desk.counts.open_problem_reports === 1 ? "" : "s"}</Link>.
            </p>
          ) : null}
        </>
      ) : null}
    </>
  );
}

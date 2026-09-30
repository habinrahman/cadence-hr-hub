"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";
import { getDashboard, type Dashboard } from "@/lib/api";
import { QUEUE_TYPE, REQUEST_STATUS } from "@/lib/labels";
import { plural, relativeAge } from "@/lib/format";
import { groupQueue } from "@/lib/queue";
import { useAsync } from "@/lib/use-async";
import { AuditLine } from "@/components/domain/audit-line";
import { PageHeader, Panel, PanelRow, SectionLabel } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { InboxRow } from "./row";

/** The dashboard lists at most 20 per type but carries the exact count of each. */
const TYPE_COUNT: Record<string, keyof Dashboard["counts"]> = {
  relationship_review: "relationship_reviews",
  requirement_approval: "requirements_awaiting_approval",
  match_review: "matches_awaiting_review",
  share_approval: "shares_awaiting_approval",
};

export function Inbox() {
  const router = useRouter();
  const params = useSearchParams();
  const filter = params.get("type") ?? "all";

  const { data: desk, error, loading, reload } = useAsync(() => getDashboard(), []);
  const data = desk ? { desk } : null;

  // The work-queue endpoint returns only the newest 50 rows across all types, so hundreds of match rows
  // would hide every other kind of decision. The dashboard lists each type separately, with exact counts.
  const rows = useMemo(
    () =>
      desk
        ? [...desk.relationship_reviews, ...desk.requirements_awaiting_approval, ...desk.matches_awaiting_review, ...desk.shares_awaiting_approval]
        : [],
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

  function choose(next: string) {
    router.replace(next === "all" ? "/" : `/?type=${next}`);
  }

  return (
    <>
      <PageHeader
        hue="rel"
        title="Needs your decision"
        sub="Cadence proposes. Nothing changes until you decide. Opening an item does not change it."
      />

      {error ? <ErrorState error={error} onRetry={reload} /> : null}

      {loading && !data ? (
        <div aria-busy="true" aria-label="Loading decisions">
          <PanelSkeleton rows={4} />
        </div>
      ) : null}

      {data ? (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <section aria-label="Decisions waiting">
            <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Filter by type">
              <FilterChip active={filter === "all"} onClick={() => choose("all")}>
                All {total}
              </FilterChip>
              {Object.entries(QUEUE_TYPE).map(([type, meta]) => (
                <FilterChip key={type} active={filter === type} onClick={() => choose(type)}>
                  {meta.label} {truth(type)}
                </FilterChip>
              ))}
            </div>

            {shown.length === 0 ? (
              <EmptyState
                title="Nothing needs a decision"
                body="New CVs, requests and matches appear here when they need you."
              />
            ) : (
              <Panel as="section">
                {shown.map((group, index) => (
                  <InboxRow
                    key={group.key}
                    group={group}
                    atLeast={truncated(group.type)}
                    showWhy={shown.findIndex((g) => g.type === group.type) === index}
                  />
                ))}
              </Panel>
            )}
            {Object.keys(TYPE_COUNT)
              .filter((type) => truncated(type) && (filter === "all" || filter === type))
              .map((type) => (
                <p key={type} className="mt-2 text-xs text-mut">
                  Showing {loadedRows[type] ?? 0} of {truth(type)} {QUEUE_TYPE[type].label.toLowerCase()} rows. The server lists at most 20 of each
                  kind here; open the request to see all of its candidates.
                </p>
              ))}
          </section>

          <aside className="space-y-6" aria-label="Context">
            <section>
              <SectionLabel>Requests in progress</SectionLabel>
              {data.desk.active_hiring_requests.length === 0 ? (
                <p className="text-mut">No active requests.</p>
              ) : (
                <Panel>
                  {data.desk.active_hiring_requests.map((r) => (
                    <PanelRow key={r.href}>
                      <Link href={r.href} prefetch={false} className="break-words font-semibold">
                        {r.subject}
                      </Link>
                      <p className="text-xs text-mut">
                        {REQUEST_STATUS[r.status] ?? r.status} · received {relativeAge(r.created_at)}
                      </p>
                    </PanelRow>
                  ))}
                </Panel>
              )}
            </section>

            {data.desk.counts.open_problem_reports > 0 ? (
              <section>
                <SectionLabel>Also waiting</SectionLabel>
                <Panel>
                  <PanelRow>
                    <Link href="/reports" prefetch={false} className="font-semibold">
                      {plural(data.desk.counts.open_problem_reports, "open problem report")} →
                    </Link>
                  </PanelRow>
                </Panel>
              </section>
            ) : null}

            <section>
              <SectionLabel>Recently recorded</SectionLabel>
              {data.desk.recent_activity.length === 0 ? (
                <p className="text-mut">No events yet.</p>
              ) : (
                <Panel>
                  <ul className="space-y-1.5 px-3.5 py-3">
                    {data.desk.recent_activity.map((e, i) => (
                      <AuditLine key={`${e.created_at}-${i}`} action={e.action} actorKind={e.actor_kind} at={e.created_at} />
                    ))}
                  </ul>
                </Panel>
              )}
            </section>
          </aside>
        </div>
      ) : null}
    </>
  );
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`min-h-11 rounded-[3px] border px-3 text-[13px] font-semibold sm:min-h-8 ${
        active ? "border-human-ink bg-human-ink text-white" : "border-rule-strong bg-panel text-ink hover:bg-inset"
      }`}
    >
      {children}
    </button>
  );
}

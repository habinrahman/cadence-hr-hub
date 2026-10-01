"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { listHiringRequests, type RequestSummary } from "@/lib/api";
import { useAsync } from "@/lib/use-async";
import { PHASE } from "@/lib/request-phase";
import { filterRequests, type RequestView } from "@/lib/request-views";
import { useRequestPhases } from "@/lib/use-request-phases";
import { shortDate } from "@/lib/format";
import { LinkButton } from "@/components/ui/button";
import { PageHeader, Panel } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { ResponsiveTable } from "@/components/ui/table";
import { StatusText } from "@/components/ui/tag";

const TITLES: Record<RequestView, string> = {
  all: "All requests",
  processing: "New / processing",
  complete: "Matching complete",
  // Nothing in the backend closes a request yet, so this view is not linked anywhere.
  closed: "Closed requests",
};

export function IndexView() {
  const params = useSearchParams();
  const view = (params.get("view") ?? "all") as RequestView;
  const { data, error, loading, reload } = useAsync(() => listHiringRequests(), []);
  const rows = data ? filterRequests(data.requests, view) : [];
  const phases = useRequestPhases(rows);
  return (
    <>
      <PageHeader
        title={TITLES[view] ?? "All requests"}
        sub="Requests received from subsidiaries are processed automatically. Open one to see the pool and decide what happens next."
        actions={
          <LinkButton variant="primary" href="/hiring?new=1">
            Log received request
          </LinkButton>
        }
      />
      {error ? <ErrorState error={error} onRetry={reload} /> : null}
      {loading && !data ? (
        <div aria-busy="true">
          <PanelSkeleton rows={4} />
        </div>
      ) : null}
      {data ? (
        rows.length === 0 ? (
          <EmptyState
            title="No requests yet"
            body="Log what a subsidiary sends Cadence HR and it is processed automatically."
            action={
              <LinkButton variant="primary" href="/hiring?new=1">
                Log received request
              </LinkButton>
            }
          />
        ) : (
          <>
            <Panel className="px-3 py-1">
              <ResponsiveTable<RequestSummary>
                caption="Hiring requests, most recent first"
                rows={rows}
                rowKey={(r) => r.id}
                columns={[
                  {
                    header: "Company",
                    primary: true,
                    cell: (r) => (
                      <Link href={`/hiring?request=${r.id}`} prefetch={false} className="break-words font-semibold">
                        {r.company}
                      </Link>
                    ),
                  },
                  { header: "Job title", cell: (r) => <span className="break-words">{r.job_title}</span> },
                  {
                    header: "Stage",
                    cell: (r) => {
                      const phase = phases[r.id];
                      if (phase) return <StatusText tone={PHASE[phase].tone}>{PHASE[phase].label}</StatusText>;
                      return <span className="text-[12.5px] text-mut">{phase === undefined ? "Checking…" : "Stage unavailable"}</span>;
                    },
                  },
                  {
                    header: "Matched",
                    cell: (r) =>
                      r.processing === "complete" || r.matched_count > 0 ? (
                        <span>
                          {r.matched_count} candidate{r.matched_count === 1 ? "" : "s"}
                          {phases[r.id] === "needs_approval" || phases[r.id] === "needs_rerun" ? (
                            <span className="text-mut"> · provisional</span>
                          ) : phases[r.id] === "ready" || phases[r.id] === "active" ? (
                            <span className="text-mut"> · confirmed</span>
                          ) : null}
                          {r.requested_count ? <span className="text-mut"> · {r.requested_count} requested</span> : null}
                        </span>
                      ) : (
                        <span className="text-mut">Not yet</span>
                      ),
                  },
                  { header: "Received", cell: (r) => shortDate(r.received_at) },
                ]}
              />
            </Panel>
            <p className="mt-2 text-xs text-mut">Showing the 50 most recent requests.</p>
          </>
        )
      ) : null}
    </>
  );
}

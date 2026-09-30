"use client";

import Link from "next/link";
import { listHiringRequests, type RequestSummary } from "@/lib/api";
import { useAsync } from "@/lib/use-async";
import { REQUEST_STATUS } from "@/lib/labels";
import { shortDate } from "@/lib/format";
import { LinkButton } from "@/components/ui/button";
import { PageHeader, Panel } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { ResponsiveTable } from "@/components/ui/table";
import { Tag } from "@/components/ui/tag";

export function IndexView() {
  const { data, error, loading, reload } = useAsync(() => listHiringRequests(), []);
  return (
    <>
      <PageHeader
        hue="req"
        title="Hiring requests"
        sub="Each request moves from requirements, to approval, to matching, to review, to sharing. Open one to see where it is."
        actions={
          <LinkButton variant="primary" href="/hiring?new=1">
            New request
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
        data.requests.length === 0 ? (
          <EmptyState
            title="No hiring requests yet"
            body="Enter a company's request to propose requirements and match candidates."
            action={
              <LinkButton variant="primary" href="/hiring?new=1">
                New request
              </LinkButton>
            }
          />
        ) : (
          <>
            <Panel className="px-3 py-1">
              <ResponsiveTable<RequestSummary>
                caption="Hiring requests, most recent first"
                rows={data.requests}
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
                    header: "Status",
                    cell: (r) => <Tag tone={r.status === "open" ? "decided" : "neutral"}>{REQUEST_STATUS[r.status] ?? r.status}</Tag>,
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

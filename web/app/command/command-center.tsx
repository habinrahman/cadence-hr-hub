"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getDashboard, type Dashboard, type DeskItem } from "@/lib/api";
import { RELATIONSHIP_LABELS, actionLabel } from "@/lib/labels";
import { relativeAge } from "@/lib/format";
import { PHASE } from "@/lib/request-phase";
import { useAsync } from "@/lib/use-async";
import { useRequestPhases } from "@/lib/use-request-phases";
import { AuditLine, auditObject } from "@/components/domain/audit-line";
import { LinkButton } from "@/components/ui/button";
import { Icon, type IconName } from "@/components/ui/icons";
import { IconTile, PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { StatusText } from "@/components/ui/tag";

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function useToday() {
  // Computed after mount so the server render and the browser never disagree about the time of day.
  const [today, setToday] = useState<{ label: string; greeting: string } | null>(null);
  useEffect(() => {
    const now = new Date();
    const hour = now.getHours();
    setToday({
      label: `${WEEKDAYS[now.getDay()]}, ${now.getDate()} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`,
      greeting: hour < 12 ? "Good morning." : hour < 18 ? "Good afternoon." : "Good evening.",
    });
  }, []);
  return today;
}

type Tone = "rel" | "req" | "match" | "share" | "human" | "prop" | "bad" | "ok";

function Tile({
  href,
  icon,
  tone,
  label,
  value,
  note,
}: {
  href: string;
  icon: IconName;
  tone: Tone;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <Link href={href} prefetch={false} className="flex items-start gap-3.5 bg-panel px-5 py-5 text-ink no-underline hover:bg-inset">
      <IconTile name={icon} tone={tone} />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] text-mut">{label}</p>
        <p className="mt-0.5 text-[24px] font-semibold leading-tight tracking-tight">{value}</p>
        <p className="mt-1 font-mono text-[11px] text-ok-ink">{note}</p>
      </div>
    </Link>
  );
}

const NEEDS_SHOWN = 6;

function requestIdOf(href: string): string {
  return new URLSearchParams(href.split("?")[1] ?? "").get("request") ?? href;
}

type Need = {
  key: string;
  kind: string;
  subject: string;
  happened: string;
  recommendation: string;
  signal: string | null;
  action: { label: string; href: string };
  at: string;
};

function documentId(href: string): string | null {
  const query = href.split("?")[1];
  return query ? new URLSearchParams(query).get("document") : null;
}

/**
 * One row per thing that waits for a person: what happened, what Cadence suggests, and the one button that does it.
 *
 * Built from the dashboard's per-kind lists rather than its combined list: that one keeps only the 20 oldest items,
 * so a backlog of CV reviews would hide every hiring decision. Work closest to a hiring outcome comes first (sending,
 * then approving requirements, then reviewing a confirmed pool), then CV reviews; the longest wait first within each.
 */
const ORDER = ["share", "req", "pool", "rel"] as const;

export function needsFromDesk(desk: Dashboard): Need[] {
  const out: Need[] = [];
  const seen = new Set<string>();
  const add = (need: Need) => {
    if (seen.has(need.key)) return;
    seen.add(need.key);
    out.push(need);
  };

  for (const item of desk.shares_awaiting_approval) {
    add({
      key: `share:${item.href}`,
      kind: "Share approval",
      subject: item.subject,
      happened: "Shortlisted. Nothing has been sent to the company.",
      recommendation: "Check what would be shared, then approve & send.",
      signal: null,
      action: { label: "Review share", href: item.href },
      at: item.created_at,
    });
  }
  for (const item of desk.requirements_awaiting_approval) {
    add({
      key: `req:${item.href}`,
      kind: "Requirements",
      subject: item.subject,
      happened: "Requirements were proposed from the job description. The pool matched on them is provisional.",
      recommendation: "Check the requirements and approve them to confirm the pool.",
      signal: item.count ? `${item.count} requirement${item.count === 1 ? "" : "s"} to approve` : null,
      action: { label: "Review requirements", href: item.href },
      at: item.created_at,
    });
  }
  for (const item of desk.matches_awaiting_review) {
    add({
      key: `pool:${item.href}`,
      kind: "Match review",
      subject: item.subject,
      happened: "Matching finished on the approved requirements. Nobody has opened the pool yet.",
      recommendation: "Review the candidates and add the right ones to the shortlist.",
      signal: item.count ? `${item.count} candidate${item.count === 1 ? "" : "s"} to review` : null,
      action: { label: "Review matches", href: item.href },
      at: item.created_at,
    });
  }
  for (const item of desk.needs_you_now) {
    // A new pool the lists above do not cover: provisional with nothing left to approve, or one to look at again.
    if (item.type === "new_matches" && !seen.has(`req:${item.href}`) && !seen.has(`pool:${item.href}`)) {
      add({
        key: `pool:${item.href}`,
        kind: "New pool",
        subject: item.subject,
        happened: "Matching finished and nobody has opened this pool yet.",
        recommendation: "Open the request to see the pool and the next step.",
        signal: null,
        action: { label: "Open request", href: item.href },
        at: item.created_at,
      });
    }
    if (item.type !== "relationship_review") continue;
    const doc = documentId(item.href);
    const relationship = item.relationship ? (RELATIONSHIP_LABELS[item.relationship] ?? item.relationship) : null;
    add({
      key: `rel:${item.href}`,
      kind: "CV review",
      subject: item.subject,
      happened: "A new CV looks related to an existing profile.",
      recommendation: item.recommended_action
        ? `${relationship ?? "Related"}: ${actionLabel(item.recommended_action)}`
        : "Not confident enough to suggest an action. Compare and choose.",
      signal: item.confidence != null ? `Same-person confidence ${Math.round(item.confidence)} / 100` : null,
      action: { label: "Compare & decide", href: doc ? `/compare?document=${doc}` : item.href },
      at: item.created_at,
    });
  }
  const rank = (need: Need) => ORDER.indexOf(need.key.split(":")[0] as (typeof ORDER)[number]);
  return out.sort((a, b) => rank(a) - rank(b) || (a.at < b.at ? -1 : a.at > b.at ? 1 : 0));
}

export function CommandCenter() {
  const today = useToday();
  const { data, error, loading, reload } = useAsync(() => getDashboard(), []);

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <span>Cadence HR desk</span>
            <span aria-hidden="true" className="text-mut">
              |
            </span>
            <span>Internal workspace</span>
            <span aria-hidden="true" className="text-mut">
              |
            </span>
            <span suppressHydrationWarning>{today?.label ?? "Today"}</span>
          </>
        }
        title={today?.greeting ?? "Welcome back."}
        sub="Requests received from subsidiaries are processed automatically. What happens next is your decision."
        actions={
          <LinkButton variant="primary" size="lg" href="/hiring?new=1">
            Log received request <Icon name="arrowUpRight" size={16} />
          </LinkButton>
        }
      />

      {error ? <ErrorState error={error} onRetry={reload} /> : null}
      {loading && !data ? (
        <div aria-busy="true" aria-label="Loading the command center">
          <PanelSkeleton rows={4} />
        </div>
      ) : null}
      {data ? <Loaded desk={data} /> : null}
    </>
  );
}

export function Loaded({ desk }: { desk: Dashboard }) {
  const c = desk.counts;
  const needs = needsFromDesk(desk);
  // The lists behind "needs" hold at most 20 of each kind; the count covers all of them.
  const waiting = Math.max(needs.length, c.reviews_needing_attention);
  const requests = desk.active_hiring_requests.slice(0, 7);
  const phases = useRequestPhases(requests.map((r) => ({ id: requestIdOf(r.href), processing: "complete" })));
  return (
    <div className="space-y-6">
      <section aria-label="Desk" className="grid grid-cols-[minmax(0,1fr)] gap-px border border-rule bg-rule sm:grid-cols-2 lg:grid-cols-4">
        <h2 className="sr-only">Cadence HR desk</h2>
        <Tile href="/hiring?view=processing" icon="inbox" tone="human" label="Requests being processed" value={String(c.requests_received)} note="Received, still being read and matched" />
        <Tile href="/queue?type=requirement_approval" icon="file" tone="req" label="Requirements to approve" value={String(c.requirements_awaiting_approval)} note="Requests waiting for your approval" />
        <Tile href="/hiring?view=complete" icon="users" tone="match" label="New candidate matches" value={String(c.new_matches)} note="Pool ready, not yet opened" />
        <Tile href="/queue" icon="inbox" tone="req" label="Reviews needing attention" value={String(c.reviews_needing_attention)} note="Across all review types" />
        <Tile href="/queue?type=share_approval" icon="check" tone="prop" label="Shortlisted, not yet sent" value={String(c.shortlisted_candidates)} note="Waiting to be shared with the company" />
        <Tile href="/queue?type=share_approval" icon="shield" tone="share" label="Sharing approvals" value={String(c.shares_awaiting_approval)} note="Waiting for your approval" />
        <Tile href="/queue?type=relationship_review" icon="compare" tone="rel" label="Duplicate / update reviews" value={String(c.duplicate_reviews)} note="CVs that may match a profile" />
        <Tile href="/reports" icon="alert" tone="bad" label="Problem reports" value={String(c.open_problem_reports)} note="Reported by the team" />
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <Panel as="section">
          <PanelHeader
            eyebrow="Decisions"
            title="Needs you now"
            action={
              <Link href="/queue" prefetch={false} className="inline-flex items-center gap-1 text-[13px] font-semibold text-human-ink no-underline">
                View queue <Icon name="arrowUpRight" size={15} />
              </Link>
            }
          />
          {needs.length === 0 ? (
            <p className="px-5 py-6 text-mut">Nothing is waiting for you.</p>
          ) : (
            <ul>
              {needs.slice(0, NEEDS_SHOWN).map((need) => (
                <li key={need.key} className="flex flex-col gap-3 border-t border-rule px-5 py-4 first:border-t-0 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                      <StatusText tone="proposed">{need.kind}</StatusText>
                      <span className="text-[12px] text-mut">Waiting {relativeAge(need.at)}</span>
                    </p>
                    <p className="mt-1 break-words text-[14px] font-semibold">{need.subject}</p>
                    <p className="text-[12.5px] text-mut">{need.happened}</p>
                    <p className="mt-1 text-[13px]">
                      <span className="text-prop-ink">Cadence suggests:</span> {need.recommendation}
                      {need.signal ? <span className="ml-1 font-mono text-[12px] text-mut">· {need.signal}</span> : null}
                    </p>
                  </div>
                  <LinkButton variant="primary" href={need.action.href} className="w-full shrink-0 sm:w-auto">
                    {need.action.label}
                  </LinkButton>
                </li>
              ))}
            </ul>
          )}
          {waiting > Math.min(needs.length, NEEDS_SHOWN) ? (
            <p className="border-t border-rule px-5 py-2.5 text-[12.5px] text-mut">
              {waiting - Math.min(needs.length, NEEDS_SHOWN)} more in the <Link href="/queue" prefetch={false}>Review queue</Link>.
            </p>
          ) : null}
        </Panel>

        <Panel as="section">
          <PanelHeader
            eyebrow="Hiring activity"
            title="Requests from subsidiaries"
            action={
              <Link href="/hiring" prefetch={false} className="inline-flex items-center gap-1 text-[13px] font-semibold text-human-ink no-underline">
                All requests <Icon name="arrowUpRight" size={15} />
              </Link>
            }
          />
          {desk.active_hiring_requests.length === 0 ? (
            <p className="px-5 py-6 text-mut">No active hiring requests.</p>
          ) : (
            <ul>
              {requests.map((r) => {
                const phase = phases[requestIdOf(r.href)];
                return (
                  <li key={r.href} className="border-t border-rule first:border-t-0">
                    <Link href={r.href} prefetch={false} className="flex items-center gap-4 px-5 py-3.5 text-ink no-underline hover:bg-inset">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-[14px] font-semibold">{r.subject}</span>
                        <span className="block text-[12.5px] text-mut">Received {relativeAge(r.created_at)}</span>
                      </span>
                      {phase ? <StatusText tone={PHASE[phase].tone}>{PHASE[phase].label}</StatusText> : null}
                      <Icon name="arrowUpRight" size={16} className="text-mut" />
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
          {desk.active_hiring_requests.length > 7 ? (
            <p className="border-t border-rule px-5 py-2.5 text-[12.5px] text-mut">
              {desk.active_hiring_requests.length - 7} more in <Link href="/hiring" prefetch={false}>Hiring requests</Link>.
            </p>
          ) : null}
        </Panel>
      </div>

      <Panel as="section">
        <PanelHeader
          eyebrow="Audit trail"
          title="Recently recorded"
          action={
            <Link href="/audit" prefetch={false} className="inline-flex items-center gap-1 text-[13px] font-semibold text-human-ink no-underline">
              Audit trail <Icon name="arrowUpRight" size={15} />
            </Link>
          }
        />
        {desk.recent_activity.length === 0 ? (
          <p className="px-5 py-6 text-mut">No events yet.</p>
        ) : (
          <ul className="space-y-2 px-5 py-4">
            {desk.recent_activity.slice(0, 8).map((e, i) => (
              <AuditLine
                key={`${e.created_at}-${i}`}
                action={e.action}
                actorKind={e.actor_kind}
                actorName={e.actor?.name}
                at={e.created_at}
                extra={auditObject(e)}
              />
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

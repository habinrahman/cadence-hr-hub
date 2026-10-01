"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { type AuditEventView, getAudit } from "@/lib/api";
import { shortDateTime } from "@/lib/format";
import { labelAudit } from "@/lib/labels";
import { actorLabel } from "@/components/domain/audit-line";
import { Button } from "@/components/ui/button";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { StatusText } from "@/components/ui/tag";

const FILTERS = [
  { key: "", label: "Everything" },
  { key: "decisions", label: "Decisions by people" },
  { key: "hiring", label: "Hiring requests" },
  { key: "cvs", label: "CVs and profiles" },
] as const;

const TONE: Record<string, "decided" | "neutral" | "proposed"> = { user: "decided", system: "neutral", agent: "proposed" };

/** The whole append-only log, newest first: when, who, what, and the request, candidate or file it concerns. */
export function AuditTrail() {
  const [filter, setFilter] = useState<string>("");
  const [events, setEvents] = useState<AuditEventView[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function load(before: string | null) {
    setBusy(true);
    setError(null);
    try {
      const page = await getAudit({ category: filter || undefined, before });
      setEvents((current) => (before && current ? [...current, ...page.events] : page.events));
      setNext(page.next_before);
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    setEvents(null);
    void load(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  return (
    <>
      <PageHeader
        eyebrow="Oversight"
        title="Audit trail"
        sub="Every important action, append-only: who did what, when, and to which request, candidate or file. CV text and contact details are never stored here."
      />
      <div role="group" aria-label="Show" className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((item) => (
          <button
            key={item.key}
            type="button"
            aria-pressed={filter === item.key}
            onClick={() => setFilter(item.key)}
            className={`inline-flex min-h-11 items-center rounded-[2px] border px-3.5 text-[13px] sm:min-h-9 ${
              filter === item.key ? "border-nav bg-nav text-white" : "border-rule bg-panel text-ink hover:border-rule-strong"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>
      {error ? <ErrorState error={error} onRetry={() => void load(null)} /> : null}
      {events === null && !error ? (
        <div aria-busy="true">
          <PanelSkeleton rows={6} />
        </div>
      ) : null}
      {events ? (
        <Panel as="section">
          <PanelHeader eyebrow="Newest first" title={events.length === 0 ? "No events" : `${events.length} events shown`} />
          {events.length === 0 ? (
            <p className="px-5 py-6 text-mut">Nothing recorded for this filter yet.</p>
          ) : (
            <ul>
              {events.map((event) => (
                <li key={event.id} className="grid gap-x-4 gap-y-0.5 border-t border-rule px-4 py-3 sm:grid-cols-[11rem_12rem_minmax(0,1fr)] sm:px-5">
                  <span className="font-mono text-[12px] text-mut">{shortDateTime(event.created_at)}</span>
                  <span>
                    <StatusText tone={TONE[event.actor.kind] ?? "neutral"}>{actorLabel(event.actor.kind, event.actor.name)}</StatusText>
                  </span>
                  <span className="min-w-0">
                    <span className="font-semibold">{labelAudit(event.action)}</span>
                    <AuditAbout event={event} />
                  </span>
                </li>
              ))}
            </ul>
          )}
          {next ? (
            <div className="border-t border-rule px-5 py-3">
              <Button busy={busy} onClick={() => void load(next)}>
                Show older events
              </Button>
            </div>
          ) : null}
        </Panel>
      ) : null}
    </>
  );
}

function AuditAbout({ event }: { event: AuditEventView }) {
  const links: { href: string; label: string }[] = [];
  if (event.candidate) links.push({ href: `/candidates/${event.candidate.id}`, label: event.candidate.label });
  if (event.request) links.push({ href: `/hiring?request=${event.request.id}`, label: event.request.label });
  if (event.document && !event.candidate) links.push({ href: `/intake?document=${event.document.id}`, label: event.document.label });
  if (links.length === 0) return null;
  return (
    <span className="mt-0.5 block break-words text-[13px] text-mut">
      {links.map((link, index) => (
        <span key={link.href}>
          {index > 0 ? " · " : ""}
          <Link href={link.href} prefetch={false}>
            {link.label}
          </Link>
        </span>
      ))}
    </span>
  );
}

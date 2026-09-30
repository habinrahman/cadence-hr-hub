"use client";

import Link from "next/link";
import { useState } from "react";
import { getCandidate, type ActivityEvent, type CandidateProfile, type DocumentSummary, type Review } from "@/lib/api";
import { ACTION_LABELS, DOCUMENT_STATUS } from "@/lib/labels";
import { shortDate } from "@/lib/format";
import { AuditLine } from "@/components/domain/audit-line";
import { RelationshipReview } from "@/components/domain/relationship-review";
import { Button, LinkButton } from "@/components/ui/button";
import { Panel, PanelRow, SectionLabel } from "@/components/ui/panel";
import { ErrorState } from "@/components/ui/states";
import { Tag } from "@/components/ui/tag";

const PROCESSING = new Set(["received", "extracting"]);

export function DocumentDetail({
  document,
  review,
  targetId,
  onTarget,
  busy,
  onDecide,
  activity,
}: {
  document: DocumentSummary;
  review: Review | null;
  targetId: string;
  onTarget: (id: string) => void;
  busy: boolean;
  onDecide: (action: string) => void;
  activity: ActivityEvent[];
}) {
  const status = DOCUMENT_STATUS[document.status] ?? { label: document.status, note: "", tone: "neutral" as const };
  return (
    <div className="space-y-5">
      <Panel as="section">
        <PanelRow>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <h2 className="min-w-0 break-all font-mono text-[15px] font-bold">{document.original_filename}</h2>
            <Tag tone={status.tone}>{status.label}</Tag>
          </div>
          <p className="mt-1 text-mut" aria-live="polite">
            {status.note} Received {shortDate(document.received_at)}.
          </p>
          {PROCESSING.has(document.status) ? (
            <p className="mt-1 text-xs text-mut">Reading the file. This page updates on its own.</p>
          ) : null}
          {document.error_code ? (
            <p className="mt-2 font-mono text-[12px] font-semibold text-bad-ink">Problem code: {document.error_code}</p>
          ) : null}
        </PanelRow>
      </Panel>

      <section aria-label="Extracted information">
        <SectionLabel>Extracted information</SectionLabel>
        <ExtractedProfile document={document} />
      </section>

      {review ? (
        <section aria-label="Relationship review">
          <SectionLabel>Relationship to existing profiles</SectionLabel>
          <div className="mb-2 flex flex-wrap items-center gap-3">
            <LinkButton variant="primary" href={`/compare?document=${document.id}`}>
              Compare the two CVs →
            </LinkButton>
            <span className="text-xs text-mut">Side-by-side evidence, then decide. You can also decide here.</span>
          </div>
          <Panel>
            <RelationshipReview
              review={review}
              targetId={targetId}
              onTarget={onTarget}
              busy={busy}
              onDecide={onDecide}
              candidateHref={(id) => `/candidates/${id}`}
            />
          </Panel>
        </section>
      ) : null}

      <section aria-label="Record">
        <SectionLabel>Record</SectionLabel>
        {activity.length === 0 ? (
          <p className="text-mut">No events yet.</p>
        ) : (
          <Panel>
            <ul className="space-y-1.5 px-3.5 py-3">
              {activity.map((event) => (
                <AuditLine
                  key={`${event.created_at}-${event.action}`}
                  action={event.action}
                  actorKind={event.actor_kind}
                  at={event.created_at}
                  extra={extraFor(event)}
                />
              ))}
            </ul>
          </Panel>
        )}
      </section>
    </div>
  );
}

function extraFor(event: ActivityEvent): string | undefined {
  const parts: string[] = [];
  const human = event.detail.human_action;
  const recommended = event.detail.recommended_action;
  if (human) parts.push(ACTION_LABELS[String(human)] ?? String(human));
  if (recommended) parts.push(`recommended: ${ACTION_LABELS[String(recommended)] ?? String(recommended)}`);
  return parts.length ? parts.join(" · ") : undefined;
}

/** Contacts come with the document. The full profile is fetched only on request, because opening a profile is audited. */
function ExtractedProfile({ document }: { document: DocumentSummary }) {
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const contacts = profile?.contacts ?? document.extracted_contacts ?? [];

  async function show() {
    if (!document.candidate_id) return;
    setLoading(true);
    setError(null);
    try {
      setProfile(await getCandidate(document.candidate_id));
    } catch (reason) {
      setError(reason);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Panel>
      <PanelRow>
        {contacts.length === 0 ? (
          <p className="text-mut">No contact details extracted yet.</p>
        ) : (
          <ul className="space-y-0.5">
            {contacts.map((c) => (
              <li key={`${c.kind}-${c.value}`}>
                <span className="text-mut">{c.kind}: </span>
                <span className="break-all font-mono text-[13px]">{c.value}</span>
              </li>
            ))}
          </ul>
        )}
      </PanelRow>
      {profile ? (
        <PanelRow className="space-y-2">
          <p className="text-base font-bold">{profile.display_name ?? "Name not extracted"}</p>
          {profile.experiences.length > 0 ? (
            <ul>
              {profile.experiences.slice(0, 4).map((e) => (
                <li key={`${e.employer}-${e.title}`}>
                  {e.title ? `${e.title}, ` : ""}
                  {e.employer}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-mut">
              <Tag tone="unknown">Not extracted</Tag> Experience
            </p>
          )}
          {profile.skills.length > 0 ? <p className="text-mut">{profile.skills.slice(0, 12).join(", ")}</p> : null}
          <Link href={`/candidates/${profile.id}`} prefetch={false}>
            Open the full profile
          </Link>
        </PanelRow>
      ) : document.candidate_id ? (
        <PanelRow>
          <Button onClick={show} busy={loading}>
            Show extracted profile
          </Button>
          <p className="mt-1 text-xs text-mut">Opening a profile is recorded in the audit trail.</p>
        </PanelRow>
      ) : null}
      {error ? (
        <PanelRow>
          <ErrorState error={error} onRetry={show} />
        </PanelRow>
      ) : null}
    </Panel>
  );
}

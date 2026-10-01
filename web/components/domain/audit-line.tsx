import { labelAudit } from "@/lib/labels";
import { shortDateTime } from "@/lib/format";

const ACTOR_KIND: Record<string, string> = { user: "A recruiter", system: "System", agent: "Cadence agent" };

/** Who acted: the person's name when the server knows it, otherwise the kind of actor in plain words. */
export function actorLabel(kind: string, name?: string | null): string {
  if (name) return name;
  return ACTOR_KIND[kind] ?? kind;
}

/** What an audit row concerns, in words: the request, the candidate and the file, whichever it names. */
export function auditObject(event: {
  request?: { label: string } | null;
  candidate?: { label: string } | null;
  document?: { label: string } | null;
}): string | null {
  const parts = [event.candidate?.label, event.request?.label, event.candidate ? null : event.document?.label].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

/** One append-only audit row: when · who · what · about which object. */
export function AuditLine({
  action,
  actorKind,
  actorName,
  at,
  extra,
}: {
  action: string;
  actorKind: string;
  actorName?: string | null;
  at?: string;
  extra?: string | null;
}) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 font-mono text-[12px]">
      {at ? <span className="text-mut">{shortDateTime(at)}</span> : null}
      <span className="text-mut">· {actorLabel(actorKind, actorName)}</span>
      <span className="font-semibold text-ink">{labelAudit(action)}</span>
      {extra ? <span className="break-words text-mut">· {extra}</span> : null}
    </li>
  );
}

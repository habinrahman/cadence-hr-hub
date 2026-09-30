import { labelAudit } from "@/lib/labels";
import { shortDateTime } from "@/lib/format";

/** One append-only audit row. The API exposes the actor kind, not a person's name. */
export function AuditLine({
  action,
  actorKind,
  at,
  extra,
}: {
  action: string;
  actorKind: string;
  at?: string;
  extra?: string;
}) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 font-mono text-[12px]">
      {at ? <span className="text-mut">{shortDateTime(at)}</span> : null}
      <span className="text-mut">· {actorKind}</span>
      <span className="font-semibold text-ink">{labelAudit(action)}</span>
      {extra ? <span className="text-mut">· {extra}</span> : null}
    </li>
  );
}

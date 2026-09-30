import type { CandidateProfile } from "@/lib/api";
import { shortDate } from "@/lib/format";
import { AuditLine } from "@/components/domain/audit-line";
import { Panel, PanelRow, SectionLabel } from "@/components/ui/panel";
import { Tag } from "@/components/ui/tag";

export function Record({ profile }: { profile: CandidateProfile }) {
  return (
    <div className="space-y-6">
      <section id="cvs" aria-labelledby="h-cvs" className="scroll-mt-16">
        <SectionLabel id="h-cvs">CV versions</SectionLabel>
        {profile.documents.length === 0 ? (
          <p className="text-mut">No documents stored.</p>
        ) : (
          <Panel>
            {profile.documents.map((d) => (
              <PanelRow key={d.id}>
                <Tag tone={d.is_current ? "ok" : "unknown"}>{d.is_current ? "Current" : "Superseded"}</Tag>
                <p className="mt-1 break-all font-mono text-[12px] font-semibold">{d.original_filename}</p>
                <p className="text-xs text-mut">
                  {shortDate(d.received_at)} · {d.status.replaceAll("_", " ")}
                </p>
              </PanelRow>
            ))}
          </Panel>
        )}
      </section>

      <section aria-labelledby="h-apps">
        <SectionLabel id="h-apps">Applications</SectionLabel>
        {profile.applications.length === 0 ? (
          <p className="text-mut">No applications stored.</p>
        ) : (
          <Panel>
            {profile.applications.map((a) => (
              <PanelRow key={a.id}>
                <span className="font-semibold">{shortDate(a.received_at)}</span>
                <span className="text-mut">
                  {" "}
                  · {a.source}
                  {a.application_date ? ` · applied ${shortDate(a.application_date)}` : ""}
                </span>
              </PanelRow>
            ))}
          </Panel>
        )}
      </section>

      <section id="record" aria-labelledby="h-rec" className="scroll-mt-16">
        <SectionLabel id="h-rec">Record</SectionLabel>
        {profile.activity.length === 0 ? (
          <p className="text-mut">No events yet.</p>
        ) : (
          <Panel>
            <ul className="space-y-1.5 px-3.5 py-3">
              {profile.activity.map((e, i) => (
                <AuditLine key={`${e.created_at}-${i}`} action={e.action} actorKind={e.actor_kind} at={e.created_at} />
              ))}
            </ul>
            <p className="border-t border-rule px-3.5 py-2 text-xs text-mut">Last 20 events. The audit trail is append-only.</p>
          </Panel>
        )}
      </section>
    </div>
  );
}

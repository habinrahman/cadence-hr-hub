"use client";

import Link from "next/link";
import type { CandidateProfile } from "@/lib/api";
import { SOURCE_TYPE } from "@/lib/labels";
import { plural, shortDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/panel";
import { useToast } from "@/components/ui/toast";

function CopyChip({ kind, value }: { kind: string; value: string }) {
  const { notify } = useToast();
  return (
    <span className="inline-flex items-center gap-1 rounded-[3px] border border-rule-strong bg-panel py-px pl-2 pr-0.5 text-xs">
      <span className="text-mut">{kind}</span>
      <span className="font-mono break-all">{value}</span>
      <button
        type="button"
        aria-label={`Copy ${kind} ${value}`}
        className="inline-flex h-6 w-6 items-center justify-center rounded text-mut hover:bg-inset hover:text-ink"
        onClick={() => {
          navigator.clipboard
            ?.writeText(value)
            .then(() => notify(`${kind} copied`))
            .catch(() => notify("Could not copy", "bad"));
        }}
      >
        <span aria-hidden="true">⧉</span>
      </button>
    </span>
  );
}

export function CandidateHeader({ profile, onShowText }: { profile: CandidateProfile; onShowText?: () => void }) {
  const current = profile.documents.find((d) => d.is_current);
  const earlier = profile.documents.filter((d) => !d.is_current).length;
  const latestRole = profile.experiences.find((e) => e.title);
  const facts = [
    profile.years_of_experience !== null ? `${profile.years_of_experience} years experience` : null,
    latestRole ? `${latestRole.title}${latestRole.employer ? ` at ${latestRole.employer}` : ""}` : null,
  ].filter(Boolean);

  return (
    <div className="rounded border border-rule bg-panel px-4 py-4">
      <PageHeader
        hue="candidate"
        title={profile.display_name ?? "Name not extracted"}
        sub={facts.length ? facts.join(" · ") : "No experience details extracted yet."}
        actions={
          <>
            {onShowText && current ? <Button onClick={onShowText}>Show CV text</Button> : null}
            <Link
              href={`/merge?left=${profile.id}`}
              prefetch={false}
              className="inline-flex min-h-11 items-center rounded px-3 text-[13px] font-semibold no-underline hover:bg-human-bg sm:min-h-8"
            >
              Merge with another profile…
            </Link>
          </>
        }
      />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-2">
        <div>
          <p className="mb-1.5 text-xs font-bold uppercase tracking-wider text-mut">Contact</p>
          {profile.contacts.length === 0 ? (
            <p className="text-mut">No contact details stored.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {profile.contacts.map((c) => (
                <CopyChip key={`${c.kind}-${c.value}`} kind={c.kind} value={c.value} />
              ))}
            </div>
          )}
        </div>
        <div className="text-[13px]">
          <p className="mb-1.5 text-xs font-bold uppercase tracking-wider text-mut">Current CV</p>
          {current ? (
            <p>
              <span className="font-mono break-all">{current.original_filename}</span>
              <span className="text-mut">
                {" "}
                · received {shortDate(current.received_at)}
                {earlier > 0 ? ` · replaces ${plural(earlier, "earlier CV")}` : ""}
              </span>
            </p>
          ) : (
            <p className="text-mut">No current CV on record.</p>
          )}
          <p className="mt-1 text-mut">
            Source: {SOURCE_TYPE[profile.source] ?? profile.source}
            {profile.sources.length > 0
              ? ` · ${profile.sources.map((s) => `${SOURCE_TYPE[s.source_type] ?? s.source_type} ${s.source_reference}`).join(", ")}`
              : ""}
          </p>
        </div>
      </div>
      {onShowText && current ? <p className="mt-3 text-xs text-mut">Opening the CV text is recorded in the audit trail.</p> : null}
    </div>
  );
}

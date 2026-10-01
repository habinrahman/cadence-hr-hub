"use client";

import { useState, type ReactNode } from "react";
import type { CandidateProfile } from "@/lib/api";
import { realPhones } from "@/lib/contacts";
import { DOCUMENT_STATUS } from "@/lib/labels";
import { LinkButton } from "@/components/ui/button";
import { Icon, type IconName } from "@/components/ui/icons";
import { Eyebrow, PageHeader, Panel } from "@/components/ui/panel";
import { StatusText } from "@/components/ui/tag";
import { useToast } from "@/components/ui/toast";

function CopyValue({ kind, value }: { kind: string; value: string }) {
  const { notify } = useToast();
  return (
    <span className="flex items-center gap-1.5">
      <span className="min-w-0 break-all text-[14px] font-semibold text-ink">{value}</span>
      <button
        type="button"
        aria-label={`Copy ${kind} ${value}`}
        className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[2px] text-mut hover:bg-inset hover:text-ink"
        onClick={() => {
          navigator.clipboard
            ?.writeText(value)
            .then(() => notify(`${kind} copied`))
            .catch(() => notify("Could not copy", "bad"));
        }}
      >
        <span aria-hidden="true" className="text-[13px]">
          ⧉
        </span>
      </button>
    </span>
  );
}

function Cell({ icon, label, children }: { icon: IconName; label: string; children: ReactNode }) {
  return (
    <div className="flex items-start gap-3.5 px-5 py-4">
      <Icon name={icon} size={17} className="mt-1 text-mut" />
      <div className="min-w-0 flex-1">
        <p className="text-[12px] text-mut">{label}</p>
        <div className="mt-1 space-y-0.5">{children}</div>
      </div>
    </div>
  );
}

const SHOWN = 2;

function Values({ kind, values }: { kind: string; values: string[] }) {
  const [all, setAll] = useState(false);
  if (values.length === 0) return <p className="text-[14px] text-mut">Not on file</p>;
  const shown = all ? values : values.slice(0, SHOWN);
  return (
    <>
      {shown.map((v) => (
        <CopyValue key={v} kind={kind} value={v} />
      ))}
      {values.length > SHOWN ? (
        <button type="button" aria-expanded={all} className="text-[12px] font-semibold text-human-ink underline" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `+${values.length - SHOWN} more`}
        </button>
      ) : null}
    </>
  );
}

/**
 * The record header: name, role, status and the four facts a recruiter reaches for first.
 * Everything shown is read from the stored profile. Nothing is filled in.
 */
export function CandidateHeader({ profile, compareHref }: { profile: CandidateProfile; compareHref: string | null }) {
  const current = profile.documents.find((d) => d.is_current);
  const status = current ? (DOCUMENT_STATUS[current.status] ?? { label: current.status, tone: "neutral" as const }) : null;
  const latestRole = profile.experiences.find((e) => e.title);
  const facts = [
    latestRole ? `${latestRole.title}${latestRole.employer ? ` at ${latestRole.employer}` : ""}` : null,
    profile.years_of_experience !== null ? `${profile.years_of_experience} years` : null,
  ].filter(Boolean);
  const emails = profile.contacts.filter((c) => c.kind === "email").map((c) => c.value);
  const phones = realPhones(profile.contacts);
  const sources = profile.sources.map((s) => s.source_reference).filter(Boolean);
  const verified = profile.evidence.filter((e) => e.quote_verified).length;

  return (
    <>
      <PageHeader
        eyebrow="Candidate record"
        title={profile.display_name ?? "Name not extracted"}
        sub={facts.length ? facts.join(" · ") : "No experience has been extracted from this candidate's CVs yet."}
        actions={
          <>
            {status ? <StatusText tone={status.tone}>{status.label}</StatusText> : <StatusText tone="unknown">No current CV</StatusText>}
            <LinkButton href="#history">
              <Icon name="clock" size={15} /> View history
            </LinkButton>
            {compareHref ? (
              // The profile does not say whether that review is still open, so this is a way in, not the next step.
              <LinkButton href={compareHref}>
                Compare CVs <Icon name="arrowUpRight" size={15} />
              </LinkButton>
            ) : null}
          </>
        }
      />
      <Panel as="section" className="grid grid-cols-[minmax(0,1fr)] divide-y divide-rule sm:grid-cols-2 sm:divide-y-0 lg:grid-cols-4 lg:divide-x">
        <h2 className="sr-only">Key facts</h2>
        <Cell icon="mail" label="Email">
          <Values kind="Email" values={emails} />
        </Cell>
        <Cell icon="phone" label="Phone">
          <Values kind="Phone" values={phones} />
        </Cell>
        <Cell icon="link" label="Source">
          <p className="break-words text-[14px] font-semibold">{profile.source.replaceAll("_", " ")}</p>
          {sources.length > 0 ? <p className="break-all text-[12.5px] text-mut">{sources.join(", ")}</p> : null}
        </Cell>
        <Cell icon="shield" label="Record">
          <p className="text-[14px] font-semibold">
            {profile.documents.length} {profile.documents.length === 1 ? "CV" : "CVs"} · {profile.applications.length}{" "}
            {profile.applications.length === 1 ? "application" : "applications"}
          </p>
          <p className="text-[12.5px] text-mut">{verified} sourced {verified === 1 ? "fact" : "facts"} with a verified quote</p>
        </Cell>
      </Panel>
      <Eyebrow className="sr-only">End of key facts</Eyebrow>
    </>
  );
}

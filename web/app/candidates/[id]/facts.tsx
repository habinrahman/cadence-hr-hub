"use client";

import { useMemo, useState } from "react";
import type { CandidateProfile } from "@/lib/api";
import { splitEvidence, type EvidenceRow } from "@/lib/evidence";
import { EvidenceQuote } from "@/components/domain/evidence-quote";
import { Icon } from "@/components/ui/icons";
import { Panel, RuleHeading } from "@/components/ui/panel";
import { Tag } from "@/components/ui/tag";

const FIELD_LABEL: Record<string, string> = {
  display_name: "Name",
  summary: "Summary",
  years_of_experience: "Years of experience",
  employer: "Employer",
  title: "Job title",
  institution: "Institution",
  credential: "Credential",
  name: "Name",
  start_date: "Start date",
  end_date: "End date",
};

function NotExtracted({ what }: { what: string }) {
  return (
    <p className="text-[13.5px] text-mut">
      <Tag tone="unknown">Not extracted</Tag> {what} was not read from a CV.
    </p>
  );
}

/** Extracted lists can be very long. Show the first few and let the recruiter expand. */
function Limited<T>({ items, limit, label, children }: { items: T[]; limit: number; label: string; children: (shown: T[]) => React.ReactNode }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, limit);
  return (
    <>
      {children(shown)}
      {items.length > limit ? (
        <button
          type="button"
          aria-expanded={all}
          className="mt-3 min-h-11 text-[13px] font-semibold text-human-ink underline sm:min-h-0"
          onClick={() => setAll(!all)}
        >
          {all ? `Show fewer ${label}` : `Show ${items.length - limit} more ${label}`}
        </button>
      ) : null}
    </>
  );
}

function Source({ evidence }: { evidence?: EvidenceRow }) {
  if (!evidence) return <p className="mt-0.5 font-mono text-[11px] text-mut">No source quote stored</p>;
  return (
    <details className="mt-1">
      <summary className="cursor-pointer font-mono text-[11.5px] text-human-ink">Source</summary>
      <EvidenceQuote quote={evidence.quote} page={evidence.page} verified={evidence.quote_verified} />
    </details>
  );
}

/** What we know about the person, each fact next to the quote it was read from. */
export function Facts({ profile }: { profile: CandidateProfile }) {
  const { find, other } = useMemo(() => splitEvidence(profile), [profile]);
  return (
    <div className="space-y-10">
      <section id="profile" aria-labelledby="h-summary" className="scroll-mt-20 border-t border-rule pt-6">
        <RuleHeading id="h-summary">Overview</RuleHeading>
        <p className="max-w-3xl break-words text-[15px] text-ink/90">{profile.narrative ?? "No summary stored."}</p>
        {profile.summary === null && profile.narrative ? (
          <p className="mt-2 font-mono text-[11px] text-mut">Built from stored fields. No model wrote this sentence.</p>
        ) : null}
      </section>

      <section aria-labelledby="h-exp" className="border-t border-rule pt-6">
        <RuleHeading id="h-exp">Experience</RuleHeading>
        {profile.experiences.length === 0 ? (
          <NotExtracted what="Experience" />
        ) : (
          <Limited items={profile.experiences} limit={8} label="roles">
            {(shown) => (
              <ol className="relative ml-1 space-y-6 border-l border-rule pl-6">
                {shown.map((e, i) => (
                  <li key={`${e.employer}-${e.title}-${i}`} className="relative">
                    <span aria-hidden="true" className="absolute -left-[29px] top-1.5 h-2 w-2 rounded-full bg-human" />
                    <p className="break-words text-[15px] font-semibold">{e.title ?? "Role not stated"}</p>
                    <p className="break-words text-[13.5px] text-mut">{e.employer}</p>
                    <Source evidence={find("employer", e.employer) ?? find("title", e.title)} />
                  </li>
                ))}
              </ol>
            )}
          </Limited>
        )}
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-10 border-t border-rule pt-6 md:grid-cols-2">
        <section aria-labelledby="h-edu">
          <RuleHeading id="h-edu">Education</RuleHeading>
          {profile.education.length === 0 ? (
            <NotExtracted what="Education" />
          ) : (
            <Limited items={profile.education} limit={6} label="entries">
              {(shown) => (
                <ul className="space-y-3">
                  {shown.map((e, i) => (
                    <li key={`${e.institution}-${e.credential}-${i}`}>
                      <p className="break-words text-[14px]">
                        <span className="font-semibold">{e.credential ?? "Credential not stated"}</span>
                        <span className="text-mut"> · {e.institution}</span>
                      </p>
                      <Source evidence={find("institution", e.institution) ?? find("credential", e.credential)} />
                    </li>
                  ))}
                </ul>
              )}
            </Limited>
          )}
        </section>

        <section aria-labelledby="h-cert">
          <RuleHeading id="h-cert">Certificates</RuleHeading>
          {profile.certificates.length + profile.qualifications.length === 0 ? (
            <NotExtracted what="Certificates and qualifications" />
          ) : (
            <ul className="space-y-3">
              {[...profile.certificates.map((c) => ({ ...c, kind: "certificate" })), ...profile.qualifications.map((c) => ({ ...c, kind: "qualification" }))].map((c) => (
                <li key={`${c.kind}-${c.name}`}>
                  <p className="flex items-start gap-2 break-words text-[14px]">
                    <Icon name="cap" size={16} className="mt-0.5 text-human" />
                    <span>
                      {c.name} <span className="text-mut">· {c.kind}</span>
                    </span>
                  </p>
                  <Source evidence={find("name", c.name)} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section id="evidence" aria-labelledby="h-other" className="scroll-mt-20 border-t border-rule pt-6">
        <RuleHeading id="h-other">Other extracted evidence</RuleHeading>
        {other.length === 0 ? (
          <p className="text-[13.5px] text-mut">Every stored quote is shown next to the fact it supports.</p>
        ) : (
          <Panel>
            <Limited items={other} limit={8} label="quotes">
              {(shown) =>
                shown.map((row, i) => (
                  <div key={`${row.field}-${i}`} className="border-t border-rule px-5 py-3 first:border-t-0">
                    <p className="text-[12.5px] text-mut">
                      {FIELD_LABEL[row.field] ?? row.field}: <span className="break-words text-ink">{row.value}</span>
                    </p>
                    <EvidenceQuote quote={row.quote} page={row.page} verified={row.quote_verified} />
                  </div>
                ))
              }
            </Limited>
          </Panel>
        )}
      </section>
    </div>
  );
}

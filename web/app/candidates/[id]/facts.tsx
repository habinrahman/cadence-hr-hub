"use client";

import { useMemo, useState } from "react";
import type { CandidateProfile } from "@/lib/api";
import { splitEvidence, type EvidenceRow } from "@/lib/evidence";
import { EvidenceQuote } from "@/components/domain/evidence-quote";
import { Panel, PanelRow, SectionLabel } from "@/components/ui/panel";
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

/** Extracted lists can be very long. Show the first few and let the recruiter expand. */
function Limited<T>({ items, limit, label, children }: { items: T[]; limit: number; label: string; children: (shown: T[]) => React.ReactNode }) {
  const [all, setAll] = useState(false);
  const shown = all ? items : items.slice(0, limit);
  return (
    <>
      {children(shown)}
      {items.length > limit ? (
        <PanelRow>
          <button type="button" aria-expanded={all} className="min-h-11 text-[13px] font-semibold text-human-ink underline sm:min-h-0" onClick={() => setAll(!all)}>
            {all ? `Show fewer ${label}` : `Show ${items.length - limit} more ${label}`}
          </button>
        </PanelRow>
      ) : null}
    </>
  );
}

function NotExtracted({ what }: { what: string }) {
  return (
    <p className="text-mut">
      <Tag tone="unknown">Not extracted</Tag> {what} was not read from a CV.
    </p>
  );
}

/** A stored fact with its source quote directly beneath it. */
function Fact({ children, evidence }: { children: React.ReactNode; evidence?: EvidenceRow }) {
  return (
    <PanelRow>
      <div className="break-words">{children}</div>
      {evidence ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-xs font-semibold text-human-ink">Source</summary>
          <EvidenceQuote quote={evidence.quote} page={evidence.page} verified={evidence.quote_verified} />
        </details>
      ) : (
        <p className="mt-0.5 font-mono text-[11px] text-mut">No source quote stored</p>
      )}
    </PanelRow>
  );
}

export function Facts({ profile }: { profile: CandidateProfile }) {
  const { find, other } = useMemo(() => splitEvidence(profile), [profile]);
  const [openSkill, setOpenSkill] = useState<string | null>(null);
  const skillEvidence = openSkill ? find("name", openSkill) : undefined;

  return (
    <div className="space-y-6">
      <section id="profile" aria-labelledby="h-summary" className="scroll-mt-16">
        <SectionLabel id="h-summary">Summary</SectionLabel>
        <Panel>
          <PanelRow>
            <p className="break-words">{profile.narrative ?? "No summary stored."}</p>
            {profile.summary === null && profile.narrative ? (
              <p className="mt-1 font-mono text-[11px] text-mut">Built from stored fields. No model wrote this sentence.</p>
            ) : null}
          </PanelRow>
        </Panel>
      </section>

      <section aria-labelledby="h-exp">
        <SectionLabel id="h-exp">Experience</SectionLabel>
        {profile.experiences.length === 0 ? (
          <NotExtracted what="Experience" />
        ) : (
          <Panel>
            <Limited items={profile.experiences} limit={8} label="roles">
              {(shown) =>
                shown.map((e) => (
                  <Fact key={`${e.employer}-${e.title}`} evidence={find("employer", e.employer) ?? find("title", e.title)}>
                    <span className="font-semibold">{e.title ?? "Role not stated"}</span>
                    <span className="text-mut"> · {e.employer}</span>
                  </Fact>
                ))
              }
            </Limited>
          </Panel>
        )}
      </section>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 md:grid-cols-2">
        <section aria-labelledby="h-edu">
          <SectionLabel id="h-edu">Education</SectionLabel>
          {profile.education.length === 0 ? (
            <NotExtracted what="Education" />
          ) : (
            <Panel>
              <Limited items={profile.education} limit={6} label="entries">
                {(shown) =>
                  shown.map((e, i) => (
                    <Fact key={`${e.institution}-${e.credential}-${i}`} evidence={find("institution", e.institution) ?? find("credential", e.credential)}>
                      <span className="font-semibold">{e.credential ?? "Credential not stated"}</span>
                      <span className="text-mut"> · {e.institution}</span>
                    </Fact>
                  ))
                }
              </Limited>
            </Panel>
          )}
        </section>

        <section aria-labelledby="h-cert">
          <SectionLabel id="h-cert">Certificates and qualifications</SectionLabel>
          {profile.certificates.length + profile.qualifications.length === 0 ? (
            <NotExtracted what="Certificates and qualifications" />
          ) : (
            <Panel>
              {profile.certificates.map((c) => (
                <Fact key={`c-${c.name}`} evidence={find("name", c.name)}>
                  <span className="font-semibold">{c.name}</span> <span className="text-mut">· certificate</span>
                </Fact>
              ))}
              {profile.qualifications.map((c) => (
                <Fact key={`q-${c.name}`} evidence={find("name", c.name)}>
                  <span className="font-semibold">{c.name}</span> <span className="text-mut">· qualification</span>
                </Fact>
              ))}
            </Panel>
          )}
        </section>
      </div>

      <section aria-labelledby="h-skills">
        <SectionLabel id="h-skills">Skills</SectionLabel>
        {profile.skills.length === 0 ? (
          <NotExtracted what="Skills" />
        ) : (
          <Panel>
            <PanelRow>
              <ul className="flex flex-wrap gap-1.5">
                {profile.skills.map((skill) => {
                  const has = Boolean(find("name", skill));
                  return (
                    <li key={skill}>
                      {has ? (
                        <button
                          type="button"
                          aria-pressed={openSkill === skill}
                          onClick={() => setOpenSkill(openSkill === skill ? null : skill)}
                          className={`min-h-8 rounded-[3px] border px-2 text-xs font-semibold ${
                            openSkill === skill ? "border-human-ink bg-human-bg text-human-ink" : "border-rule-strong bg-panel hover:bg-inset"
                          }`}
                        >
                          {skill} <span aria-hidden="true">✓</span>
                          <span className="sr-only"> has a source quote</span>
                        </button>
                      ) : (
                        <span className="inline-block rounded-[3px] border border-rule bg-panel px-2 py-1 text-xs">{skill}</span>
                      )}
                    </li>
                  );
                })}
              </ul>
              {skillEvidence ? (
                <div aria-live="polite">
                  <EvidenceQuote quote={skillEvidence.quote} page={skillEvidence.page} verified={skillEvidence.quote_verified} />
                </div>
              ) : (
                <p className="mt-2 text-xs text-mut">Skills marked ✓ have a stored source quote. Select one to read it.</p>
              )}
            </PanelRow>
          </Panel>
        )}
      </section>

      <section id="evidence" aria-labelledby="h-other" className="scroll-mt-16">
        <SectionLabel id="h-other">Other extracted evidence</SectionLabel>
        {other.length === 0 ? (
          <p className="text-mut">Every stored quote is shown next to the fact it supports.</p>
        ) : (
          <Panel>
            <Limited items={other} limit={8} label="quotes">
              {(shown) =>
                shown.map((row, i) => (
                  <PanelRow key={`${row.field}-${i}`}>
                    <p className="text-xs font-semibold text-mut">
                      {FIELD_LABEL[row.field] ?? row.field}: <span className="text-ink break-words">{row.value}</span>
                    </p>
                    <EvidenceQuote quote={row.quote} page={row.page} verified={row.quote_verified} />
                  </PanelRow>
                ))
              }
            </Limited>
          </Panel>
        )}
      </section>
    </div>
  );
}

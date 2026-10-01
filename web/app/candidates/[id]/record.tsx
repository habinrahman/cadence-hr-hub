"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { CandidateProfile } from "@/lib/api";
import { splitEvidence } from "@/lib/evidence";
import { shortDate } from "@/lib/format";
import { DOCUMENT_STATUS, SOURCE_TYPE } from "@/lib/labels";
import { AuditLine } from "@/components/domain/audit-line";
import { EvidenceQuote } from "@/components/domain/evidence-quote";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icons";
import { Panel, RuleHeading } from "@/components/ui/panel";
import { StatusText } from "@/components/ui/tag";

const SKILLS_SHOWN = 24;

function Skills({ profile }: { profile: CandidateProfile }) {
  const { find } = useMemo(() => splitEvidence(profile), [profile]);
  const [open, setOpen] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const shown = all ? profile.skills : profile.skills.slice(0, SKILLS_SHOWN);
  const evidence = open ? find("name", open) : undefined;
  return (
    <section aria-labelledby="h-skills" className="border-t border-rule pt-6">
      <RuleHeading id="h-skills">Skills</RuleHeading>
      {profile.skills.length === 0 ? (
        <p className="text-[13.5px] text-mut">No skills were extracted.</p>
      ) : (
        <>
          <ul className="flex flex-wrap gap-1.5">
            {shown.map((skill) => {
              const has = Boolean(find("name", skill));
              return (
                <li key={skill}>
                  {has ? (
                    <button
                      type="button"
                      aria-pressed={open === skill}
                      onClick={() => setOpen(open === skill ? null : skill)}
                      className={`min-h-8 rounded-[2px] border px-2.5 text-[12.5px] ${
                        open === skill ? "border-human bg-human-bg text-human-ink" : "border-rule bg-inset text-ink hover:border-rule-strong"
                      }`}
                    >
                      {skill}
                      <span className="sr-only"> has a source quote</span>
                    </button>
                  ) : (
                    <span className="inline-block rounded-[2px] border border-rule bg-inset px-2.5 py-1 text-[12.5px]">{skill}</span>
                  )}
                </li>
              );
            })}
          </ul>
          {profile.skills.length > SKILLS_SHOWN ? (
            <button type="button" aria-expanded={all} className="mt-2 min-h-11 text-[13px] font-semibold text-human-ink underline sm:min-h-0" onClick={() => setAll(!all)}>
              {all ? "Show fewer" : `Show ${profile.skills.length - SKILLS_SHOWN} more`}
            </button>
          ) : null}
          <div aria-live="polite">
            {evidence ? (
              <EvidenceQuote quote={evidence.quote} page={evidence.page} verified={evidence.quote_verified} />
            ) : (
              <p className="mt-2 text-[12px] text-mut">Select a skill to read the quote it was taken from.</p>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function Documents({ profile, onShowText }: { profile: CandidateProfile; onShowText?: () => void }) {
  const current = profile.documents.find((d) => d.is_current);
  // Newest first: the CV that was replaced most recently sits at the top of the history.
  const previous = profile.documents.filter((d) => !d.is_current).sort((a, b) => (a.received_at < b.received_at ? 1 : -1));
  const replacedBy = (id: string) => profile.documents.find((d) => d.supersedes_document_id === id);
  const replaces = current?.supersedes_document_id ? profile.documents.find((d) => d.id === current.supersedes_document_id) : undefined;
  return (
    <section id="cvs" aria-labelledby="h-docs" className="scroll-mt-20 border-t border-rule pt-6 first:border-t-0 first:pt-0">
      <RuleHeading id="h-docs">CVs</RuleHeading>
      {profile.documents.length === 0 ? (
        <p className="text-[13.5px] text-mut">No documents stored.</p>
      ) : (
        <div className="space-y-4">
          <div>
            <p className="mb-1.5 font-mono text-[10.5px] uppercase tracking-[0.12em] text-mut">Current CV</p>
            {current ? (
              <Panel className="border-l-2 border-l-ok">
                <div className="flex items-start gap-3 px-4 py-3">
                  <Icon name="paperclip" size={16} className="mt-0.5 text-mut" />
                  <div className="min-w-0 flex-1">
                    <p className="break-all font-mono text-[12px] font-semibold" title={current.original_filename}>
                      {current.original_filename}
                    </p>
                    <p className="text-[12px] text-mut">
                      Uploaded {shortDate(current.received_at)} · {DOCUMENT_STATUS[current.status]?.label ?? current.status.replaceAll("_", " ")}
                    </p>
                    {replaces ? <p className="break-all text-[12px] text-mut">Replaced {replaces.original_filename}</p> : null}
                    <p className="mt-1 text-[12px] text-mut">The profile facts on this page are read from this CV.</p>
                  </div>
                  <StatusText tone="ok">Current</StatusText>
                </div>
                {onShowText ? (
                  <div className="border-t border-rule px-4 py-3">
                    <Button onClick={onShowText}>Show current CV text</Button>
                    <p className="mt-1.5 text-[12px] text-mut">Opening CV text is recorded in the audit trail.</p>
                  </div>
                ) : null}
              </Panel>
            ) : (
              <p className="text-[13.5px] text-mut">No CV is marked current.</p>
            )}
          </div>
          <div>
            <p className="mb-1.5 font-mono text-[10.5px] uppercase tracking-[0.12em] text-mut">Previous CVs ({previous.length})</p>
            {previous.length === 0 ? (
              <p className="text-[13px] text-mut">None. This is the only CV on file.</p>
            ) : (
              <Panel>
                <ul>
                  {previous.map((d) => {
                    const newer = replacedBy(d.id);
                    return (
                      <li key={d.id} className="flex items-start gap-3 border-t border-rule px-4 py-3 first:border-t-0">
                        <Icon name="paperclip" size={16} className="mt-0.5 text-mut" />
                        <div className="min-w-0 flex-1">
                          <p className="break-all font-mono text-[12px] font-semibold" title={d.original_filename}>
                            {d.original_filename}
                          </p>
                          <p className="text-[12px] text-mut">
                            Uploaded {shortDate(d.received_at)} · {DOCUMENT_STATUS[d.status]?.label ?? d.status.replaceAll("_", " ")}
                          </p>
                          {newer ? <p className="break-all text-[12px] text-mut">Replaced by {newer.original_filename}</p> : null}
                        </div>
                        <StatusText tone="unknown">{d.status === "archived" ? "Archived" : "Superseded"}</StatusText>
                      </li>
                    );
                  })}
                </ul>
              </Panel>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function Provenance({ profile }: { profile: CandidateProfile }) {
  return (
    <section aria-labelledby="h-source" className="border-t border-rule pt-6">
      <RuleHeading id="h-source">Source &amp; provenance</RuleHeading>
      <div className="border-l-2 border-human bg-human-bg px-4 py-3">
        <p className="break-words text-[14px] font-semibold text-ink">{SOURCE_TYPE[profile.source] ?? profile.source.replaceAll("_", " ")}</p>
        {profile.sources.length > 0 ? (
          <ul className="mt-0.5 space-y-0.5 text-[13px]">
            {profile.sources.map((s, i) => (
              <li key={i} className="break-all">
                {SOURCE_TYPE[s.source_type] ?? s.source_type} · {s.source_reference}
              </li>
            ))}
          </ul>
        ) : null}
        <p className="mt-1 text-[12.5px] text-mut">Source recorded with the candidate record.</p>
      </div>
      <p className="mt-3 text-[13px]">
        <Link href={`/merge?left=${profile.id}`} prefetch={false}>
          Merge with another profile…
        </Link>
      </p>
    </section>
  );
}

function Applications({ profile }: { profile: CandidateProfile }) {
  return (
    <section aria-labelledby="h-apps" className="border-t border-rule pt-6">
      <RuleHeading id="h-apps">Applications</RuleHeading>
      {profile.applications.length === 0 ? (
        <p className="text-[13.5px] text-mut">No applications stored.</p>
      ) : (
        <ul className="space-y-2 text-[13.5px]">
          {profile.applications.map((a) => (
            <li key={a.id}>
              <span className="font-semibold">{shortDate(a.received_at)}</span>
              <span className="text-mut">
                {" "}
                · {SOURCE_TYPE[a.source] ?? a.source}
                {a.application_date ? ` · applied ${shortDate(a.application_date)}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The right-hand rail: what the candidate can do, and where the record came from. */
export function Rail({ profile, onShowText }: { profile: CandidateProfile; onShowText?: () => void }) {
  return (
    <div className="space-y-6">
      <Documents profile={profile} onShowText={onShowText} />
      <Skills profile={profile} />
      <Provenance profile={profile} />
      <Applications profile={profile} />
    </div>
  );
}

export function History({ profile }: { profile: CandidateProfile }) {
  return (
    <section id="history" aria-labelledby="h-history" className="scroll-mt-20 border-t border-rule pt-6">
      <RuleHeading id="h-history">History</RuleHeading>
      {profile.activity.length === 0 ? (
        <p className="text-[13.5px] text-mut">No events yet.</p>
      ) : (
        <Panel>
          <ul className="space-y-2 px-5 py-4">
            {profile.activity.map((e, i) => (
              <AuditLine key={`${e.created_at}-${i}`} action={e.action} actorKind={e.actor_kind} at={e.created_at} />
            ))}
          </ul>
          <p className="border-t border-rule px-5 py-2.5 text-[12.5px] text-mut">Last 20 events. The audit trail is append-only.</p>
        </Panel>
      )}
    </section>
  );
}

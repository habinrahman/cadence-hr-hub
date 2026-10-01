"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  type LeadMatch,
  type Review,
  type SourcedCandidate,
  decideReview,
  getReview,
  getSourcedCandidate,
  submitSourcedCandidate,
} from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { SOURCE_TYPE } from "@/lib/labels";
import { RelationshipReview } from "@/components/domain/relationship-review";
import { AuditLine } from "@/components/domain/audit-line";
import { Button } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { PageHeader, Panel, PanelRow, SectionLabel } from "@/components/ui/panel";
import { ErrorState, Notice } from "@/components/ui/states";
import { Tag } from "@/components/ui/tag";
import { useToast } from "@/components/ui/toast";

const PROCESSING = new Set(["received", "extracting"]);

const LEAD_REASON: Record<string, string> = {
  same_email: "Same email",
  same_phone: "Same phone",
  same_name: "Same name",
  similar_name: "Similar name",
  different_email: "Different email",
  different_phone: "Different phone",
};

export function SourceDesk() {
  const { notify } = useToast();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [sourceType, setSourceType] = useState("linkedin");
  const [reference, setReference] = useState("");
  const [notes, setNotes] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [entry, setEntry] = useState<SourcedCandidate | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  // A lead with no CV that may already be on file: nothing is saved until the recruiter picks one of these.
  const [matches, setMatches] = useState<LeadMatch[] | null>(null);

  useEffect(() => {
    if (!entry) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const loadReview = async (documentId: string) => {
      const opened = await getReview(documentId);
      if (!cancelled) setReview(opened);
    };

    const poll = async () => {
      try {
        const next = await getSourcedCandidate(entry.id);
        if (cancelled) return;
        setEntry(next);
        if (PROCESSING.has(next.document_status ?? "")) {
          timer = setTimeout(poll, 1000);
          return;
        }
        if (next.review_id && next.document_id) await loadReview(next.document_id);
      } catch (reason) {
        if (!cancelled) setFailure(reason);
      }
    };

    if (PROCESSING.has(entry.document_status ?? "")) {
      timer = setTimeout(poll, 800);
    } else if (entry.review_id && entry.document_id) {
      loadReview(entry.document_id).catch((reason) => setFailure(reason));
    }

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entry?.id, entry?.document_status, entry?.review_id]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = "Enter the candidate's name.";
    if (!reference.trim()) next.reference = "Add where they were found: a profile link or the referrer's name.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    await submit({});
  }

  /** choice is empty on the first try; after a possible match it says which profile, or a new one. */
  async function submit(choice: { attachTo?: string; createNew?: boolean }) {
    setBusy(true);
    setFailure(null);
    setReview(null);
    const body = new FormData();
    body.set("name", name);
    body.set("email", email);
    body.set("phone", phone);
    body.set("source_type", sourceType);
    body.set("source_reference", reference);
    body.set("notes", notes);
    if (file) body.set("file", file);
    if (choice.attachTo) body.set("attach_to", choice.attachTo);
    if (choice.createNew) body.set("create_new", "true");
    try {
      const created = await submitSourcedCandidate(body);
      setMatches(null);
      setEntry(created);
      if (created.document_id) {
        setNotice("CV attached. The same duplicate check as an uploaded CV is running.");
      } else if (choice.attachTo) {
        setNotice("Source added to the existing profile. Nothing on that profile was replaced.");
      } else {
        setNotice("Candidate added without a CV. When their CV arrives, upload it in Intake; it is matched to this profile for your review.");
      }
      notify("Sourced candidate saved");
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "possible_existing") {
        const detail = reason.detail as { matches?: LeadMatch[] } | null;
        setMatches(detail?.matches ?? []);
      } else {
        setFailure(reason);
      }
    } finally {
      setBusy(false);
    }
  }

  async function onDecide(action: string) {
    if (!review) return;
    setBusy(true);
    setFailure(null);
    try {
      const decided = await decideReview(review.id, action, review.candidate_id ?? undefined);
      setReview(decided);
      if (entry) setEntry(await getSourcedCandidate(entry.id));
      setNotice("Decision recorded.");
      notify("Decision recorded");
    } catch (reason) {
      setFailure(reason);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
title="Source a candidate"
        sub="Add someone found on LinkedIn, by referral or another approved source — with or without a CV. Cadence checks whether they are already on file first; if they may be, you decide."
      />

      <Panel as="section" className="max-w-3xl p-5">
        <form onSubmit={onSubmit} noValidate className="grid grid-cols-[minmax(0,1fr)] gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Field label="Name" error={errors.name}>
              {({ id, describedBy, invalid }) => (
                <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
              )}
            </Field>
          </div>
          <Field label="Email">
            {({ id }) => <input id={id} type="email" className={inputClass} value={email} onChange={(e) => setEmail(e.target.value)} />}
          </Field>
          <Field label="Phone">
            {({ id }) => <input id={id} type="tel" className={inputClass} value={phone} onChange={(e) => setPhone(e.target.value)} />}
          </Field>
          <Field label="Where were they found?">
            {({ id }) => (
              <select id={id} className={inputClass} value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
                <option value="linkedin">LinkedIn</option>
                <option value="referral">Referral</option>
                <option value="other">Other approved source</option>
              </select>
            )}
          </Field>
          <Field label="Source reference" hint="A profile link, a referrer's name, or another pointer back to the source." error={errors.reference}>
            {({ id, describedBy, invalid }) => (
              <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={inputClass} value={reference} onChange={(e) => setReference(e.target.value)} />
            )}
          </Field>
          <div className="sm:col-span-2">
            <Field label="Notes">
              {({ id }) => <textarea id={id} className={`${inputClass} min-h-20 sm:min-h-20`} value={notes} onChange={(e) => setNotes(e.target.value)} />}
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="CV (optional)" hint="PDF, Word, or an image of a scan. No CV yet? Leave this empty and add it later in Intake." error={errors.file}>
              {({ id, describedBy, invalid }) => (
                <input
                  id={id}
                  aria-describedby={describedBy}
                  aria-invalid={invalid}
                  type="file"
                  accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
                  className="block w-full text-[13px]"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
              )}
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Button type="submit" variant="primary" busy={busy}>
              Add sourced candidate
            </Button>
          </div>
        </form>
        {notice ? (
          <div className="mt-4">
            <Notice>{notice}</Notice>
          </div>
        ) : null}
      </Panel>

      {matches ? (
        <section aria-label="Possible existing profile" className="mt-6 max-w-3xl">
          <SectionLabel>This person may already be on file</SectionLabel>
          <Panel>
            <div className="px-3.5 py-3">
              <p className="text-[13.5px]">
                Nothing has been saved yet. Cadence found {matches.length === 1 ? "a profile" : `${matches.length} profiles`} that
                share details with <strong className="break-words">{name}</strong>. Choose what is true.
              </p>
              <ul className="mt-3 space-y-3">
                {matches.map((match) => (
                  <li key={match.candidate_id} className="rounded border border-rule px-3 py-2">
                    <p className="font-semibold">
                      <Link href={`/candidates/${match.candidate_id}`} prefetch={false} target="_blank">
                        {match.display_name ?? "Unnamed profile"}
                      </Link>
                    </p>
                    <ul className="mt-1 flex flex-wrap gap-1.5">
                      {match.reasons.map((reason) => (
                        <li key={reason}>
                          <Tag tone={reason.startsWith("different") ? "warn" : "ok"}>{LEAD_REASON[reason] ?? reason.replaceAll("_", " ")}</Tag>
                        </li>
                      ))}
                    </ul>
                    <div className="mt-2">
                      <Button busy={busy} onClick={() => void submit({ attachTo: match.candidate_id })}>
                        Same person — add source to this profile
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
              <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-rule pt-3">
                <Button busy={busy} onClick={() => void submit({ createNew: true })}>
                  Different person — create a new profile
                </Button>
                <Button variant="quiet" onClick={() => setMatches(null)}>
                  Cancel
                </Button>
              </div>
            </div>
          </Panel>
        </section>
      ) : null}

      {failure ? (
        <div className="mt-4 max-w-3xl">
          <ErrorState error={failure} />
        </div>
      ) : null}

      {entry ? (
        <div className="mt-8 max-w-3xl space-y-6">
          <section aria-label="Source">
            <SectionLabel>Source</SectionLabel>
            <Panel>
              <PanelRow>
                <p className="break-words text-base font-bold">{entry.display_name}</p>
                <p className="mt-0.5 text-mut">
                  <Tag tone="neutral">{SOURCE_TYPE[entry.source_type] ?? entry.source_type}</Tag>{" "}
                  <span className="break-all">{entry.source_reference}</span>
                </p>
                <p className="mt-1 text-mut">{entry.document_id ? `CV status: ${entry.document_status ?? "unknown"}` : "No CV yet"}</p>
                {entry.candidate_id && review?.status !== "pending" ? (
                  <p className="mt-1">
                    Source kept on the candidate record.{" "}
                    <Link href={`/candidates/${entry.candidate_id}`} prefetch={false}>
                      Open the profile
                    </Link>
                  </p>
                ) : null}
              </PanelRow>
            </Panel>
          </section>

          {review ? (
            <section aria-label="Relationship review">
              <SectionLabel>Does this candidate already exist?</SectionLabel>
              <Panel>
                <RelationshipReview review={review} busy={busy} onDecide={onDecide} candidateHref={(id) => `/candidates/${id}`} />
              </Panel>
            </section>
          ) : null}

          <section aria-label="Record">
            <SectionLabel>Record</SectionLabel>
            <Panel>
              <ul className="space-y-1.5 px-3.5 py-3">
                {entry.events.map((event) => (
                  <AuditLine key={`${event.action}-${event.created_at}`} action={event.action} actorKind={event.actor_kind} at={event.created_at} />
                ))}
              </ul>
            </Panel>
          </section>
        </div>
      ) : null}
    </>
  );
}

"use client";

import { useEffect, useState } from "react";
import {
  type Review,
  type SourcedCandidate,
  decideReview,
  getReview,
  getSourcedCandidate,
  submitSourcedCandidate,
} from "@/lib/api";
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
        if (next.review_id) await loadReview(next.document_id);
      } catch (reason) {
        if (!cancelled) setFailure(reason);
      }
    };

    if (PROCESSING.has(entry.document_status ?? "")) {
      timer = setTimeout(poll, 800);
    } else if (entry.review_id) {
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
    if (!file) next.file = "Choose a CV to attach.";
    setErrors(next);
    if (Object.keys(next).length > 0 || !file) return;
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
    body.set("file", file);
    try {
      const created = await submitSourcedCandidate(body);
      setEntry(created);
      setNotice("CV attached. The same duplicate check as an uploaded CV is running.");
    } catch (reason) {
      setFailure(reason);
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
        hue="rel"
        title="Source a candidate"
        sub="LinkedIn and referral candidates go through the same duplicate check as an uploaded CV. If they may already be on file, a recruiter decides."
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
          <Field label="Source reference" hint="A profile link, a referrer's name, or another pointer back to the source.">
            {({ id, describedBy }) => (
              <input id={id} aria-describedby={describedBy} className={inputClass} value={reference} onChange={(e) => setReference(e.target.value)} />
            )}
          </Field>
          <div className="sm:col-span-2">
            <Field label="Notes">
              {({ id }) => <textarea id={id} className={`${inputClass} min-h-20`} value={notes} onChange={(e) => setNotes(e.target.value)} />}
            </Field>
          </div>
          <div className="sm:col-span-2">
            <Field label="CV" hint="PDF, Word, or an image of a scan." error={errors.file}>
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
                <p className="mt-1 text-mut">File status: {entry.document_status ?? "unknown"}</p>
                {entry.candidate_id && review?.status !== "pending" ? <p className="mt-1">Source kept on the candidate record.</p> : null}
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

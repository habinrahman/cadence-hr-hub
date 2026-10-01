"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createHiringRequest } from "@/lib/api";
import { Button, LinkButton } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { PageHeader, Panel } from "@/components/ui/panel";
import { ErrorState } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";

function today() {
  return new Date().toISOString().slice(0, 10);
}

export function NewRequest() {
  const router = useRouter();
  const { notify } = useToast();
  const [company, setCompany] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [received, setReceived] = useState(today());
  const [requested, setRequested] = useState("");
  const [contact, setContact] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!company.trim()) next.company = "Enter the company.";
    if (!title.trim()) next.title = "Enter the job title.";
    if (!description.trim()) next.description = "Paste the job description or the company's request.";
    if (!received) next.received = "Enter the date the request was received.";
    if (requested && Number(requested) < 1) next.requested = "Enter at least 1 candidate.";
    if (contact.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contact.trim())) next.contact = "Enter an email address such as hiring@company.com.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    setBusy(true);
    setFailure(null);
    try {
      const created = await createHiringRequest({
        company: company.trim(),
        job_title: title.trim(),
        description,
        received_at: `${received}T00:00:00Z`,
        ...(requested ? { requested_count: Number(requested) } : {}),
        ...(contact.trim() ? { contact_email: contact.trim() } : {}),
      });
      notify("Request logged. Processing has started.");
      router.push(`/hiring?request=${created.id}`);
    } catch (reason) {
      setFailure(reason);
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Log received request"
        sub="Enter what the subsidiary sent Cadence HR. Requirements are extracted and candidates matched automatically. A person decides what happens next."
      />
      <Panel as="section" className="max-w-2xl p-5">
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <Field label="Company" error={errors.company}>
            {({ id, describedBy, invalid }) => (
              <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={inputClass} value={company} onChange={(e) => setCompany(e.target.value)} />
            )}
          </Field>
          <Field
            label="Company contact email"
            hint="Shortlisted candidates are sent here, only after you approve each one. You can add it later."
            error={errors.contact}
          >
            {({ id, describedBy, invalid }) => (
              <input id={id} type="email" aria-describedby={describedBy} aria-invalid={invalid} className={inputClass} value={contact} onChange={(e) => setContact(e.target.value)} />
            )}
          </Field>
          <Field label="Job title" error={errors.title}>
            {({ id, describedBy, invalid }) => (
              <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
            )}
          </Field>
          <Field label="Date received" error={errors.received}>
            {({ id, describedBy, invalid }) => (
              <input id={id} type="date" aria-describedby={describedBy} aria-invalid={invalid} className={inputClass} value={received} onChange={(e) => setReceived(e.target.value)} />
            )}
          </Field>
          <Field label="Candidates requested" hint="How many candidates the subsidiary asked for. Leave blank if they did not say." error={errors.requested}>
            {({ id, describedBy, invalid }) => (
              <input
                id={id}
                type="number"
                min={1}
                aria-describedby={describedBy}
                aria-invalid={invalid}
                className={inputClass}
                value={requested}
                onChange={(e) => setRequested(e.target.value)}
              />
            )}
          </Field>
          <Field
            label="Job description"
            hint="Requirements are extracted automatically from the description."
            error={errors.description}
          >
            {({ id, describedBy, invalid }) => (
              <textarea id={id} aria-describedby={describedBy} aria-invalid={invalid} className={`${inputClass} min-h-40 sm:min-h-40`} value={description} onChange={(e) => setDescription(e.target.value)} />
            )}
          </Field>
          {failure ? <ErrorState error={failure} /> : null}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" busy={busy}>
              Log request
            </Button>
            <LinkButton variant="quiet" href="/hiring">
              Cancel
            </LinkButton>
          </div>
        </form>
      </Panel>
    </>
  );
}

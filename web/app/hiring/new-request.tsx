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
      });
      notify("Request saved");
      router.push(`/hiring?request=${created.id}`);
    } catch (reason) {
      setFailure(reason);
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        hue="req"
        title="New hiring request"
        sub="Save the request first. Cadence then proposes requirements from the description, and a recruiter approves them before anyone is matched."
      />
      <Panel as="section" className="max-w-2xl p-5">
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          <Field label="Company" error={errors.company}>
            {({ id, describedBy, invalid }) => (
              <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={inputClass} value={company} onChange={(e) => setCompany(e.target.value)} />
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
          <Field
            label="Job description"
            hint="Requirements are read from labelled lines and common phrases. Anything not recognised stays in the description for you."
            error={errors.description}
          >
            {({ id, describedBy, invalid }) => (
              <textarea id={id} aria-describedby={describedBy} aria-invalid={invalid} className={`${inputClass} min-h-40`} value={description} onChange={(e) => setDescription(e.target.value)} />
            )}
          </Field>
          {failure ? <ErrorState error={failure} /> : null}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="primary" busy={busy}>
              Save request
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

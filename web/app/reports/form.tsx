"use client";

import { useEffect, useState } from "react";
import { type ProblemReport, createProblemReport, listProblemReports } from "@/lib/api";
import { REPORT_STATUS } from "@/lib/labels";
import { shortDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { PageHeader, Panel, PanelRow, SectionLabel } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { Tag } from "@/components/ui/tag";
import { useToast } from "@/components/ui/toast";

export function ReportDesk() {
  const { notify } = useToast();
  const [category, setCategory] = useState("intake");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [entityType, setEntityType] = useState("none");
  const [entityId, setEntityId] = useState("");
  const [errorCode, setErrorCode] = useState("");
  const [route, setRoute] = useState("");
  const [action, setAction] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [reports, setReports] = useState<ProblemReport[] | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [listError, setListError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listProblemReports()
      .then((payload) => setReports(payload.reports))
      .catch(setListError);
  }, []);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!title.trim()) next.title = "Give the problem a short title.";
    if (!description.trim()) next.description = "Describe what happened and what you expected.";
    if (entityType !== "none" && !entityId.trim()) next.entityId = "Enter the id of the related record, or choose None.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    setBusy(true);
    setFailure(null);
    const context: { error_code?: string; route?: string; action?: string } = {};
    if (errorCode.trim()) context.error_code = errorCode.trim();
    if (route.trim()) context.route = route.trim();
    if (action.trim()) context.action = action.trim();
    try {
      const created = await createProblemReport({
        category,
        title: title.trim(),
        description,
        entity_type: entityType,
        entity_id: entityType === "none" || !entityId.trim() ? null : entityId.trim(),
        context,
      });
      setReports((current) => [created, ...(current ?? [])]);
      setTitle("");
      setDescription("");
      notify("Report submitted. An engineer can see it now.");
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
        title="Problem reports"
        sub="Describe the problem in your own words. Context is limited to an error code, a route and an action. Candidate details are never attached."
      />

      <div className="grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel as="section" className="p-5">
          <h2 className="mb-3 text-base font-bold">Report a problem</h2>
          <form onSubmit={onSubmit} noValidate className="space-y-4">
            <Field label="Category">
              {({ id }) => (
                <select id={id} className={inputClass} value={category} onChange={(e) => setCategory(e.target.value)}>
                  <option value="intake">Intake</option>
                  <option value="matching">Matching</option>
                  <option value="sharing">Sharing</option>
                  <option value="sourcing">Sourcing</option>
                  <option value="other">Other</option>
                </select>
              )}
            </Field>
            <Field label="Title" error={errors.title}>
              {({ id, describedBy, invalid }) => (
                <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
              )}
            </Field>
            <Field label="What happened?" error={errors.description}>
              {({ id, describedBy, invalid }) => (
                <textarea id={id} aria-describedby={describedBy} aria-invalid={invalid} className={`${inputClass} min-h-28`} value={description} onChange={(e) => setDescription(e.target.value)} />
              )}
            </Field>
            <Field label="Related record">
              {({ id }) => (
                <select id={id} className={inputClass} value={entityType} onChange={(e) => setEntityType(e.target.value)}>
                  <option value="none">None</option>
                  <option value="candidate">Candidate</option>
                  <option value="hiring_request">Hiring request</option>
                  <option value="document">Document</option>
                </select>
              )}
            </Field>
            {entityType !== "none" ? (
              <Field label="Related record id" error={errors.entityId}>
                {({ id, describedBy, invalid }) => (
                  <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={`${inputClass} font-mono`} value={entityId} onChange={(e) => setEntityId(e.target.value)} />
                )}
              </Field>
            ) : null}
            <fieldset className="grid grid-cols-[minmax(0,1fr)] gap-3 rounded border border-rule p-3 sm:grid-cols-3">
              <legend className="px-1 text-xs font-bold uppercase tracking-wider text-mut">Context (optional)</legend>
              <Field label="Error code">
                {({ id }) => <input id={id} className={`${inputClass} font-mono`} value={errorCode} onChange={(e) => setErrorCode(e.target.value)} />}
              </Field>
              <Field label="Route">
                {({ id }) => <input id={id} className={`${inputClass} font-mono`} value={route} onChange={(e) => setRoute(e.target.value)} />}
              </Field>
              <Field label="Action">
                {({ id }) => <input id={id} className={inputClass} value={action} onChange={(e) => setAction(e.target.value)} />}
              </Field>
            </fieldset>
            {failure ? <ErrorState error={failure} /> : null}
            <Button type="submit" variant="primary" busy={busy}>
              Submit report
            </Button>
          </form>
        </Panel>

        <section aria-label="Your reports">
          <SectionLabel>Reports</SectionLabel>
          {listError ? <ErrorState error={listError} /> : null}
          {!listError && reports === null ? (
            <div aria-busy="true">
              <PanelSkeleton rows={3} />
            </div>
          ) : null}
          {reports && reports.length === 0 ? <EmptyState title="No reports yet" body="Problems you report appear here with their status." /> : null}
          {reports && reports.length > 0 ? (
            <Panel>
              {reports.map((report) => {
                const status = REPORT_STATUS[report.status] ?? { label: report.status, tone: "neutral" as const };
                return (
                  <PanelRow key={report.id}>
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <p className="min-w-0 break-words font-bold">{report.title}</p>
                      <Tag tone={status.tone}>{status.label}</Tag>
                    </div>
                    <p className="mt-0.5 text-xs text-mut">
                      {report.category}
                      {report.created_at ? ` · ${shortDate(report.created_at)}` : ""}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap break-words text-mut">{report.description}</p>
                    {report.engineering_note ? (
                      <div className="mt-2 rounded border border-rule bg-inset px-3 py-2 text-[13px]">
                        <p className="text-xs font-bold uppercase tracking-wider text-mut">Engineer&apos;s note</p>
                        <p className="whitespace-pre-wrap break-words">{report.engineering_note}</p>
                      </div>
                    ) : null}
                  </PanelRow>
                );
              })}
            </Panel>
          ) : null}
        </section>
      </div>
    </>
  );
}

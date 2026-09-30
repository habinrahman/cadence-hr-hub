"use client";

import { useEffect, useState } from "react";
import {
  type ExcelImportReport,
  type Review,
  decideReview,
  downloadHiringExport,
  getReviewRecord,
  importExcelCandidates,
} from "@/lib/api";
import { RelationshipReview } from "@/components/domain/relationship-review";
import { Button } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { PageHeader, Panel, PanelRow, SectionLabel } from "@/components/ui/panel";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState, Notice } from "@/components/ui/states";
import { ResponsiveTable } from "@/components/ui/table";
import { Tag } from "@/components/ui/tag";
import { useToast } from "@/components/ui/toast";
import type { Tone } from "@/lib/labels";

const OUTCOME: Record<string, { label: string; tone: Tone }> = {
  created: { label: "Created", tone: "ok" },
  existing_relationship: { label: "Existing candidate", tone: "proposed" },
  duplicate_row: { label: "Duplicate row", tone: "warn" },
  invalid: { label: "Invalid", tone: "bad" },
};

type Row = ExcelImportReport["rows"][number];

export function DataDesk() {
  const { notify } = useToast();
  const [report, setReport] = useState<ExcelImportReport | null>(null);
  const [start, setStart] = useState("2026-01-01");
  const [end, setEnd] = useState("2026-03-31");
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function onFile(file: File) {
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      setReport(await importExcelCandidates(file));
      setNotice("Import finished. Every row is listed below.");
    } catch (reason) {
      setFailure(reason);
    } finally {
      setBusy(false);
    }
  }

  async function onExport() {
    if (!start || !end) {
      setRangeError("Choose both dates.");
      return;
    }
    if (start > end) {
      setRangeError("The start date must be on or before the end date.");
      return;
    }
    setRangeError(null);
    setBusy(true);
    setFailure(null);
    try {
      const blob = await downloadHiringExport(start, end);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `hiring-activity-${start}-to-${end}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
      notify("Export downloaded");
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
        title="Excel import and export"
        sub="Import a candidate list, or download hiring activity for a date range. Cell text is not shown back here."
      />

      {failure ? (
        <div className="mb-5">
          <ErrorState error={failure} />
        </div>
      ) : null}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-2">
        <Panel as="section" className="p-5">
          <h2 className="mb-1 text-base font-bold">Import a candidate list</h2>
          <p className="mb-3 text-mut">An .xlsx file with name, email and phone columns. A row that matches an existing email or phone opens a review; nothing is changed until you decide.</p>
          <label className="flex min-h-24 cursor-pointer flex-col items-center justify-center gap-1 rounded border border-dashed border-rule-strong px-4 py-6 text-center focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-human hover:bg-inset">
            <span className="font-bold">{busy ? "Working…" : "Choose an Excel file"}</span>
            <span className="text-xs text-mut">.xlsx only</span>
            <input
              className="sr-only"
              type="file"
              accept=".xlsx"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void onFile(file);
                event.target.value = "";
              }}
            />
          </label>
          {notice ? (
            <div className="mt-3">
              <Notice>{notice}</Notice>
            </div>
          ) : null}
        </Panel>

        <Panel as="section" className="scroll-mt-16 p-5">
          <h2 id="export" className="mb-1 scroll-mt-16 text-base font-bold">
            Hiring activity export
          </h2>
          <p className="mb-3 text-mut">A workbook of requests, candidates found and shared in the date range. Cells holding an email address or a long number are blanked.</p>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-2">
            <Field label="From">
              {({ id }) => <input id={id} type="date" className={inputClass} value={start} onChange={(e) => setStart(e.target.value)} />}
            </Field>
            <Field label="To" error={rangeError}>
              {({ id, describedBy, invalid }) => (
                <input id={id} type="date" aria-describedby={describedBy} aria-invalid={invalid} className={inputClass} value={end} onChange={(e) => setEnd(e.target.value)} />
              )}
            </Field>
          </div>
          <div className="mt-4">
            <Button variant="primary" busy={busy} onClick={onExport}>
              Download export
            </Button>
          </div>
        </Panel>
      </div>

      {report ? (
        <section className="mt-8" aria-label="Import result">
          <SectionLabel>Import result</SectionLabel>
          <Panel className="mb-4">
            <dl className="grid grid-cols-2 gap-px bg-rule sm:grid-cols-4">
              {[
                ["Rows", report.row_count],
                ["Valid", report.valid_count],
                ["Invalid", report.invalid_count],
                ["Missing fields", report.missing_required],
                ["Malformed", report.malformed],
                ["Duplicate rows", report.duplicate_count],
                ["Existing candidates", report.relationship_count],
                ["Created", report.created_count],
              ].map(([label, value]) => (
                <div key={label as string} className="bg-panel px-3 py-2">
                  <dt className="text-xs text-mut">{label}</dt>
                  <dd className="text-xl font-bold">{value}</dd>
                </div>
              ))}
            </dl>
          </Panel>
          <Panel className="px-3 py-1">
            <ResponsiveTable<Row>
              caption="Every imported row and its outcome"
              rows={report.rows}
              rowKey={(row) => String(row.row)}
              columns={[
                { header: "Row", primary: true, cell: (row) => `Row ${row.row}` },
                {
                  header: "Outcome",
                  cell: (row) => {
                    const o = OUTCOME[row.outcome] ?? { label: row.outcome, tone: "neutral" as const };
                    return <Tag tone={o.tone}>{o.label}</Tag>;
                  },
                },
                {
                  header: "Detail",
                  cell: (row) => (
                    <span className="break-words">
                      {row.relationship ? `Relationship: ${row.relationship}. ` : ""}
                      {row.duplicate_of_row ? `Duplicate of row ${row.duplicate_of_row}. ` : ""}
                      {row.errors.length > 0 ? row.errors.join(", ") : ""}
                      {!row.relationship && !row.duplicate_of_row && row.errors.length === 0 ? "—" : ""}
                    </span>
                  ),
                },
                { header: "Review", cell: (row) => (row.review_id ? <ExcelReview reviewId={row.review_id} /> : <span className="text-mut">Not needed</span>) },
              ]}
            />
          </Panel>
        </section>
      ) : null}
    </>
  );
}

function ExcelReview({ reviewId }: { reviewId: string }) {
  const { notify } = useToast();
  const [review, setReview] = useState<Review | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open || review) return;
    getReviewRecord(reviewId).then(setReview).catch(setFailure);
  }, [open, review, reviewId]);

  async function onDecide(action: string) {
    setBusy(true);
    setFailure(null);
    try {
      setReview(await decideReview(reviewId, action));
      notify("Decision recorded");
    } catch (reason) {
      setFailure(reason);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-w-56">
      <Button variant="quiet" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Hide review" : "Open review"}
      </Button>
      {open ? (
        <div className="mt-2">
          {failure ? <ErrorState error={failure} /> : null}
          {!review && !failure ? <Skeleton lines={3} /> : null}
          {review ? (
            <Panel>
              <PanelRow className="p-0">
                <RelationshipReview review={review} busy={busy} onDecide={onDecide} candidateHref={(id) => `/candidates/${id}`} />
              </PanelRow>
            </Panel>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

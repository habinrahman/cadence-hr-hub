"use client";

import type { ReactNode } from "react";
import type { Processing } from "@/lib/api";
import { PHASE, type RequestPhase } from "@/lib/request-phase";
import { Button, LinkButton } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { StatusText, Tag } from "@/components/ui/tag";

type RowState = "done" | "active" | "todo" | "warn";

const MARK: Record<RowState, string> = { done: "✓", active: "●", todo: "○", warn: "!" };
const MARK_CLASS: Record<RowState, string> = {
  done: "text-ok-ink",
  active: "text-human-ink",
  todo: "text-mut",
  warn: "text-prop-ink",
};
const STATE_WORD: Record<RowState, string> = { done: "Done", active: "In progress", todo: "Not yet", warn: "Needs you" };

function Row({ state, children, note }: { state: RowState; children: ReactNode; note?: ReactNode }) {
  return (
    <li className="flex items-start gap-2.5 text-[14px]">
      <span aria-hidden="true" className={`w-4 shrink-0 text-center font-bold ${MARK_CLASS[state]}`}>
        {MARK[state]}
      </span>
      <span className="min-w-0">
        <span className="sr-only">{STATE_WORD[state]}: </span>
        <span className={state === "todo" ? "text-mut" : state === "active" || state === "warn" ? "font-semibold" : ""}>{children}</span>
        {note ? <span className="block text-[12.5px] text-mut">{note}</span> : null}
      </span>
    </li>
  );
}

/** One request-level number. "—" means the step has not happened, never zero. */
function Fact({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="bg-panel px-3 py-2.5">
      <dt className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-mut">{label}</dt>
      <dd className="mt-0.5 text-[20px] font-semibold leading-tight tabular-nums">{value}</dd>
      {hint ? <dd className="text-[11.5px] text-mut">{hint}</dd> : null}
    </div>
  );
}

/**
 * What the automatic processing has done, in the order the backend does it: the first run extracts requirements and
 * matches on them straight away (a provisional pool), then HR approves the requirements and matching re-runs on the
 * approved ones (the confirmed pool). There is no percentage, because the server does not report one.
 */
export function ProcessingCard({
  processing,
  phase = null,
  shortlisted,
  shared,
  onRetry,
}: {
  processing: Processing;
  /** Request status from the server. Not shown: "open" says nothing HR can act on. */
  status?: string;
  phase?: RequestPhase | null;
  /** null when the shortlist could not be read; undefined when not known on this screen. */
  shortlisted?: number | null;
  shared?: number;
  onRetry: () => void;
}) {
  const stage = processing.stage;
  const failed = stage === "failed";
  const complete = stage === "complete";
  const confirmed = processing.pool_status === "confirmed";
  const noRequirements = stage === "awaiting_approval";
  const rematching = stage === "matching";
  const working = stage === "received" || stage === "extracting" || rematching;
  // The first job extracts and matches in one go, so a provisional pool exists by the time HR can approve anything.
  const provisionalDone = complete || rematching;

  return (
    <section aria-label="Request processing" aria-busy={working}>
      <Panel className="space-y-3 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-mut">Progress</h2>
          {phase ? <StatusText tone={PHASE[phase].tone}>{PHASE[phase].label}</StatusText> : null}
        </div>
        <ul className="space-y-2">
          <Row state="done">Request received</Row>
          <Row
            state={stage === "received" ? "todo" : stage === "extracting" ? "active" : noRequirements ? "warn" : failed ? "todo" : "done"}
            note={noRequirements ? "None were proposed from the job description." : undefined}
          >
            {stage === "extracting" ? "Extracting requirements" : stage === "received" ? "Extract requirements" : "Requirements extracted"}
          </Row>
          <Row
            state={provisionalDone ? "done" : "todo"}
            note={provisionalDone && !confirmed ? "On the extracted requirements, before HR approval. A preview: nothing can be shortlisted from it." : undefined}
          >
            {provisionalDone ? "Candidate matching completed" : "Provisional matching"}
            {provisionalDone ? <span className="text-mut"> · {confirmed ? "provisional preview, since replaced" : "provisional pool"}</span> : null}
          </Row>
          <Row state={confirmed || rematching ? "done" : complete ? "warn" : "todo"}>
            {confirmed || rematching
              ? "Requirements approved by HR"
              : phase === "needs_rerun"
                ? "Requirements changed after matching. Re-run matching below"
                : complete
                  ? "Waiting for HR to review and approve the requirements"
                  : "HR approves the requirements"}
          </Row>
          <Row state={rematching ? "active" : complete && confirmed ? "done" : "todo"} note={rematching ? "On the approved requirements only." : undefined}>
            {rematching ? "Matching candidates" : complete && confirmed ? "Matched on the approved requirements" : "Re-match on the approved requirements"}
          </Row>
          <Row state={complete && confirmed ? "done" : "todo"}>Ready for HR review</Row>
        </ul>

        {working ? (
          <p aria-live="polite" className="border-t border-rule pt-3 text-[13px] text-mut">
            This page updates by itself. A first run can take up to about two minutes while the model starts up.
          </p>
        ) : null}
        {noRequirements ? (
          <p role="status" className="border-t border-rule pt-3 text-[14px]">
            No requirement was proposed, so nothing could be matched. Add a requirement below; matching then runs automatically.
          </p>
        ) : null}
        {failed ? (
          <div role="alert" className="flex flex-wrap items-center gap-3 border-t border-rule pt-3">
            <span className="text-bad-ink">Automatic processing failed. Nothing was matched or shared.</span>
            <Button onClick={onRetry}>Retry processing</Button>
          </div>
        ) : null}
        {complete ? (
          <div className="space-y-3 border-t border-rule pt-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="text-[22px] font-semibold tabular-nums">{processing.matched_count} candidates matched</span>
                {processing.pool_status && processing.pool_status !== "none" ? (
                  <Tag tone={confirmed ? "decided" : "proposed"}>{confirmed ? "Confirmed" : "Provisional"}</Tag>
                ) : null}
                {processing.requested_count ? <span className="text-mut">Requested: {processing.requested_count}</span> : null}
              </p>
              <LinkButton variant={confirmed ? "primary" : "secondary"} href="#pool">
                View candidate pool
              </LinkButton>
            </div>
            {processing.pool_status && processing.pool_status !== "none" ? (
              <dl aria-label="Request facts" className="grid grid-cols-2 gap-px border border-rule bg-rule sm:grid-cols-4">
                <Fact label="Provisional matches" value={confirmed ? "—" : String(processing.matched_count)} hint={confirmed ? "Replaced by the confirmed pool" : "Preview only"} />
                <Fact label="Confirmed matches" value={confirmed ? String(processing.matched_count) : "—"} hint={confirmed ? undefined : "After HR approval"} />
                <Fact
                  label="Shortlisted"
                  value={shortlisted === undefined ? "—" : shortlisted === null ? "?" : String(shortlisted)}
                  hint={shortlisted === null ? "Could not be read" : undefined}
                />
                <Fact label="Shared" value={shared === undefined ? "—" : String(shared)} />
              </dl>
            ) : null}
          </div>
        ) : null}
      </Panel>
    </section>
  );
}

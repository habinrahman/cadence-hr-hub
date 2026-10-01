"use client";

import { useState } from "react";
import type { HiringRequestDetail, HiringRequirement } from "@/lib/api";
import { Field } from "@/components/ui/field";
import { EvidenceQuote } from "@/components/domain/evidence-quote";
import { Button } from "@/components/ui/button";
import { inputClass } from "@/components/ui/field";
import { Panel, PanelRow } from "@/components/ui/panel";
import { StrengthTag } from "@/components/ui/strength";
import { Tag } from "@/components/ui/tag";

type Patch = {
  text?: string;
  strength?: "mandatory" | "preferred";
  label?: "skill" | "experience" | "education" | "certification" | "other";
};

const LABELS = ["skill", "experience", "education", "certification", "other"] as const;

export function Requirements({
  requirements,
  busy,
  poolStale,
  source = null,
  awaitingApproval = false,
  rematching = false,
  onRerun,
  onEdit,
  onApprove,
  onReject,
  onAdd,
}: {
  /** HR rejects one requirement: kept and labelled, never matched on. */
  onReject?: (item: HiringRequirement) => void;
  requirements: HiringRequirement[];
  busy: boolean;
  poolStale: boolean;
  source?: HiringRequestDetail["requirements_source"];
  /** No requirement was proposed: HR adds one. */
  awaitingApproval?: boolean;
  /** An approval rematch is queued or running, so no manual re-run is offered. */
  rematching?: boolean;
  onApprove?: () => void;
  onAdd?: (item: { label: (typeof LABELS)[number]; text: string; strength: "mandatory" | "preferred"; quote: string }) => Promise<boolean>;
  onRerun: () => void;
  onEdit: (item: HiringRequirement, patch: Patch) => void;
}) {
  // Rejected rows are a decision already made; only proposed rows wait for approval.
  const unapproved = requirements.filter((item) => item.review_status === "proposed").length;
  return (
    <details open={awaitingApproval || unapproved > 0 || undefined}>
      <summary className="cursor-pointer text-sm font-semibold">
        {requirements.length === 0
          ? "Requirements · none yet"
          : `Requirements · Auto-extracted · ${unapproved > 0 ? `${unapproved} awaiting approval` : "Approved"}`}
      </summary>
      <div className="mt-3 space-y-3">
        <SourceLine source={source} proposed={requirements.length} />
        <RejectedLine source={source} />
        {unapproved > 0 && onApprove ? (
          <div role="status" className="proposal flex flex-wrap items-center gap-3 px-3 py-2">
            <span>
              <strong>{unapproved === 1 ? "1 requirement is" : `${unapproved} requirements are`} waiting for approval.</strong> The candidate pool stays
              provisional until they are approved. Approving re-runs matching on the approved requirements automatically.
            </span>
            <Button variant="primary" busy={busy} onClick={onApprove}>
              Approve requirements
            </Button>
          </div>
        ) : null}
        {poolStale && unapproved === 0 && !rematching ? (
          <div role="status" className="proposal px-3 py-2">
            <strong>Candidate pool may be stale.</strong> Requirements changed after matching.
            <Button className="ml-3" variant="primary" busy={busy} onClick={onRerun}>
              Re-run matching
            </Button>
          </div>
        ) : null}
        {requirements.length === 0 ? (
          <p className="text-mut">
            {awaitingApproval ? "No requirement was proposed. Add one from the job description below." : "Requirements appear here once extraction finishes."}
          </p>
        ) : (
          <Panel>
            {requirements.map((item) => (
              <RequirementRow key={`${item.id}-${item.review_status}-${item.text}`} item={item} busy={busy} onEdit={onEdit} onReject={onReject} />
            ))}
          </Panel>
        )}
        {onAdd ? <AddRequirement busy={busy} onAdd={onAdd} /> : null}
      </div>
    </details>
  );
}

function RequirementRow({
  item,
  busy,
  onEdit,
  onReject,
}: {
  item: HiringRequirement;
  busy: boolean;
  onEdit: (item: HiringRequirement, patch: Patch) => void;
  onReject?: (item: HiringRequirement) => void;
}) {
  const [text, setText] = useState(item.text);
  const [strength, setStrength] = useState(item.strength);
  const [label, setLabel] = useState(item.label as (typeof LABELS)[number]);
  const dirty = text !== item.text || strength !== item.strength || label !== item.label;
  const fieldId = `req-${item.id}`;

  return (
    <PanelRow>
      <div className="flex flex-wrap items-center gap-2">
        <StrengthTag strength={strength} />
        {item.review_status === "proposed" ? (
          <Tag tone="proposed">Proposed · not approved</Tag>
        ) : item.review_status === "rejected" ? (
          <Tag tone="unknown">Rejected · not matched on</Tag>
        ) : (
          <Tag tone="decided">Approved</Tag>
        )}
        {onReject && item.review_status !== "rejected" ? (
          <Button className="ml-auto" variant="danger" busy={busy} onClick={() => onReject(item)}>
            Reject requirement
          </Button>
        ) : null}
      </div>
      <div className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-2 md:grid-cols-[minmax(0,1fr)_9rem_9rem_auto] md:items-end">
        <div>
          <label htmlFor={`${fieldId}-text`} className="mb-1 block text-xs font-semibold">
            Requirement
          </label>
          <input id={`${fieldId}-text`} className={inputClass} value={text} onChange={(e) => setText(e.target.value)} />
          {label === "experience" ? <p className="mt-0.5 text-[12px] text-mut">Minimum years of experience, as a number.</p> : null}
        </div>
        <div>
          <label htmlFor={`${fieldId}-strength`} className="mb-1 block text-xs font-semibold">
            Strength
          </label>
          <select
            id={`${fieldId}-strength`}
            className={inputClass}
            value={strength}
            onChange={(e) => setStrength(e.target.value as "mandatory" | "preferred")}
          >
            <option value="mandatory">Mandatory</option>
            <option value="preferred">Preferred</option>
          </select>
        </div>
        <div>
          <label htmlFor={`${fieldId}-label`} className="mb-1 block text-xs font-semibold">
            Kind
          </label>
          <select id={`${fieldId}-label`} className={inputClass} value={label} onChange={(e) => setLabel(e.target.value as (typeof LABELS)[number])}>
            {LABELS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <Button
          busy={busy}
          disabled={!dirty}
          onClick={() =>
            onEdit(item, {
              ...(text !== item.text ? { text } : {}),
              ...(strength !== item.strength ? { strength } : {}),
              ...(label !== item.label ? { label } : {}),
            })
          }
        >
          Save edit
        </Button>
      </div>
      {dirty ? (
        <p className="mt-1 text-xs text-prop-ink">Saving an edit makes the candidate pool provisional until the requirement is approved again.</p>
      ) : null}
      {item.source_quote ? <EvidenceQuote quote={item.source_quote} source="Job description" /> : null}
    </PanelRow>
  );
}

/** Says plainly who proposed the requirements. A fallback is never presented as the model's work. */
export function SourceLine({ source, proposed }: { source: HiringRequestDetail["requirements_source"]; proposed?: number }) {
  if (!source?.model) return null;
  if (source.fallback) {
    // With nothing proposed, "proposed these" would point at nothing: say the reader found none.
    const empty = proposed === 0;
    const outcome = empty ? "the automatic text reader read it instead, and it proposed nothing" : "the automatic text reader proposed these";
    return (
      <p role="status" className="text-[13px] text-prop-ink">
        {source.fallback_reason === "description_too_long"
          ? `This job description is longer than the AI model reads, so ${outcome}.`
          : source.fallback_reason === "model_reply_malformed"
            ? `The AI model's answer could not be used, so ${outcome}.`
            : `The AI model was unavailable, so ${outcome}.`}{" "}
        {empty ? "Add a requirement from the job description below." : "Review them before approving."}
      </p>
    );
  }
  const model = source.model.startsWith("ollama:") ? `local AI model (${source.model.slice(7)})` : source.model === "deterministic-requirement-parser" ? "the automatic text reader" : source.model;
  return (
    <p className="text-[13px] text-mut">
      Proposed by {model}, from the job description only. Each one quotes the text it came from. Candidates are matched on them
      straight away, but the pool stays provisional, and nothing can be shortlisted or shared, until a person approves them.
    </p>
  );
}

const REASON: Record<string, string> = {
  blocked_attribute: "a protected characteristic",
  injected_instruction: "an instruction inside the text",
  unsupported_requirement: "not supported by the job description",
  malformed_output: "malformed",
};

/** Proposals the checks refused, by reason only. The refused text itself is never shown or stored. */
export function RejectedLine({ source }: { source: HiringRequestDetail["requirements_source"] }) {
  const rejected = Object.entries(source?.rejected ?? {}).filter(([, count]) => count > 0);
  if (rejected.length === 0) return null;
  const total = rejected.reduce((sum, [, count]) => sum + count, 0);
  return (
    <p className="text-[13px] text-bad-ink">
      {total === 1 ? "1 proposal was" : `${total} proposals were`} refused and not stored:{" "}
      {rejected.map(([code, count]) => `${count} ${REASON[code] ?? code.replaceAll("_", " ")}`).join(", ")}.
    </p>
  );
}

function AddRequirement({
  busy,
  onAdd,
}: {
  busy: boolean;
  onAdd: (item: { label: (typeof LABELS)[number]; text: string; strength: "mandatory" | "preferred"; quote: string }) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const [quote, setQuote] = useState("");
  const [label, setLabel] = useState<(typeof LABELS)[number]>("skill");
  const [strength, setStrength] = useState<"mandatory" | "preferred">("mandatory");
  return (
    <Panel as="section" className="space-y-3 p-4">
      <h3 className="text-[14px] font-semibold">Add a requirement</h3>
      <p className="text-[13px] text-mut">Copy the quote word for word from the job description. Protected characteristics are refused.</p>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-[minmax(0,1fr)_9rem_9rem]">
        <Field label="Requirement">{({ id }) => <input id={id} className={inputClass} value={text} onChange={(e) => setText(e.target.value)} />}</Field>
        <Field label="Kind">
          {({ id }) => (
            <select id={id} className={inputClass} value={label} onChange={(e) => setLabel(e.target.value as (typeof LABELS)[number])}>
              {LABELS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label="Strength">
          {({ id }) => (
            <select id={id} className={inputClass} value={strength} onChange={(e) => setStrength(e.target.value as "mandatory" | "preferred")}>
              <option value="mandatory">Mandatory</option>
              <option value="preferred">Preferred</option>
            </select>
          )}
        </Field>
      </div>
      <Field label="Quote from the job description">
        {({ id }) => <input id={id} className={inputClass} value={quote} onChange={(e) => setQuote(e.target.value)} />}
      </Field>
      <Button
        busy={busy}
        disabled={!text.trim() || !quote.trim()}
        onClick={async () => {
          if (await onAdd({ label, text: text.trim(), strength, quote: quote.trim() })) {
            setText("");
            setQuote("");
          }
        }}
      >
        Add requirement
      </Button>
    </Panel>
  );
}

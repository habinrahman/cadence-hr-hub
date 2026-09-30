"use client";

import { useState } from "react";
import type { HiringRequirement } from "@/lib/api";
import { EvidenceQuote } from "@/components/domain/evidence-quote";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { inputClass } from "@/components/ui/field";
import { Panel, PanelRow } from "@/components/ui/panel";
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
  onExtract,
  onApprove,
  onEdit,
}: {
  requirements: HiringRequirement[];
  busy: boolean;
  onExtract: () => void;
  onApprove: () => void;
  onEdit: (item: HiringRequirement, patch: Patch) => void;
}) {
  const [confirm, setConfirm] = useState<"extract" | "approve" | null>(null);
  const approved = requirements.filter((r) => r.review_status === "approved").length;
  const pending = requirements.length - approved;

  return (
    <div>
      {requirements.length === 0 ? (
        <div className="rounded border border-dashed border-rule-strong bg-panel px-4 py-5">
          <p className="font-semibold">No requirements yet</p>
          <p className="text-mut">
            Cadence reads labelled lines and common phrases in the description and proposes requirements. Nothing is matched
            until you approve them.
          </p>
          <div className="mt-3">
            <Button variant="primary" busy={busy} onClick={onExtract}>
              Propose requirements from the description
            </Button>
          </div>
        </div>
      ) : (
        <>
          <Panel>
            {requirements.map((item) => (
              <RequirementRow key={`${item.id}-${item.review_status}-${item.text}`} item={item} busy={busy} onEdit={onEdit} />
            ))}
          </Panel>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button variant="primary" busy={busy} disabled={pending === 0} onClick={() => setConfirm("approve")}>
              Approve {pending > 0 ? `${pending} proposed` : "requirements"}
            </Button>
            <Button variant="quiet" busy={busy} onClick={() => setConfirm("extract")}>
              Propose again
            </Button>
            <span className="text-xs text-mut">Approved requirements are the only ones matching uses.</span>
          </div>
        </>
      )}

      <ConfirmDialog
        open={confirm === "approve"}
        title="Approve these requirements?"
        body={<p>{pending} proposed requirement(s) will drive matching. You can still edit one afterwards, but it returns to proposed.</p>}
        confirmLabel="Approve"
        busy={busy}
        onConfirm={() => {
          setConfirm(null);
          onApprove();
        }}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm === "extract"}
        title="Propose the requirements again?"
        body={<p>This replaces the current list with a fresh proposal from the description. Approvals on the current list are lost.</p>}
        confirmLabel="Replace with new proposal"
        tone="danger"
        busy={busy}
        onConfirm={() => {
          setConfirm(null);
          onExtract();
        }}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}

function RequirementRow({
  item,
  busy,
  onEdit,
}: {
  item: HiringRequirement;
  busy: boolean;
  onEdit: (item: HiringRequirement, patch: Patch) => void;
}) {
  const [text, setText] = useState(item.text);
  const [strength, setStrength] = useState(item.strength);
  const [label, setLabel] = useState(item.label as (typeof LABELS)[number]);
  const dirty = text !== item.text || strength !== item.strength || label !== item.label;
  const approved = item.review_status === "approved";
  const fieldId = `req-${item.id}`;

  return (
    <PanelRow>
      <div className="flex flex-wrap items-center gap-2">
        {approved ? <Tag tone="decided">Approved</Tag> : <Tag tone="proposed">Proposed</Tag>}
        {approved ? null : <span className="text-xs text-prop-ink">Not used for matching yet</span>}
      </div>
      <div className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-2 md:grid-cols-[minmax(0,1fr)_9rem_9rem_auto] md:items-end">
        <div>
          <label htmlFor={`${fieldId}-text`} className="mb-1 block text-xs font-semibold">
            Requirement
          </label>
          <input id={`${fieldId}-text`} className={inputClass} value={text} onChange={(e) => setText(e.target.value)} />
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
      {dirty && approved ? <p className="mt-1 text-xs text-prop-ink">Saving an edit returns this requirement to proposed. Approve it again before it is used.</p> : null}
      {item.source_quote ? <EvidenceQuote quote={item.source_quote} source="Job description" /> : null}
    </PanelRow>
  );
}

"use client";

import { useState } from "react";
import type { CompareField, CompareItem, CompareValue, Comparison } from "@/lib/api";
import { ITEM_STATUS } from "@/lib/compare";
import { EvidenceQuote } from "@/components/domain/evidence-quote";
import { Tag } from "@/components/ui/tag";

export type EvidenceTarget = { side: "existing" | "incoming"; page: number | null; quote: string };

const SHOWN = 12;

function emptyText(item: CompareItem, side: "existing" | "incoming", field: CompareField): string {
  const state = side === "existing" ? field.existing_state : field.incoming_state;
  if (item.status === "unknown") return state === "unavailable" ? "No readable text" : "Nothing extracted";
  return side === "existing" ? "Not found in existing CV" : "Not found in incoming CV";
}

function Cell({
  value,
  side,
  item,
  field,
  onOpen,
}: {
  value: CompareValue;
  side: "existing" | "incoming";
  item: CompareItem;
  field: CompareField;
  onOpen: (target: EvidenceTarget) => void;
}) {
  if (!value) return <p className="text-[13px] text-mut">{emptyText(item, side, field)}</p>;
  const evidence = value.evidence;
  return (
    <div className="min-w-0">
      <p className="break-words">{value.label}</p>
      <details className="mt-0.5">
        <summary className="cursor-pointer text-xs font-semibold text-human-ink">
          Source{evidence.page ? ` · page ${evidence.page}` : ""}
        </summary>
        <EvidenceQuote quote={evidence.quote} page={evidence.page} verified />
        <button
          type="button"
          className="mb-1 text-xs font-semibold text-human-ink underline"
          onClick={() => onOpen({ side, page: evidence.page, quote: evidence.quote })}
        >
          Show in the {side} CV text
        </button>
      </details>
    </div>
  );
}

function Row({ item, field, onOpen }: { item: CompareItem; field: CompareField; onOpen: (target: EvidenceTarget) => void }) {
  const meta = ITEM_STATUS[item.status];
  return (
    <li className="border-t border-rule px-3.5 py-2.5 first:border-t-0 md:grid md:grid-cols-[minmax(0,1fr)_10.5rem_minmax(0,1fr)] md:items-start md:gap-3">
      <div className="min-w-0">
        <p className="text-[11px] font-bold uppercase tracking-wider text-mut md:hidden">Existing CV</p>
        <Cell value={item.existing} side="existing" item={item} field={field} onOpen={onOpen} />
      </div>
      <div className="my-1.5 md:my-0 md:text-center">
        <Tag tone={meta.tone}>
          <span aria-hidden="true">{meta.mark} </span>
          {meta.label}
        </Tag>
        {typeof item.similarity === "number" ? <p className="mt-0.5 text-xs text-mut">Word overlap {Math.round(item.similarity * 100)}%</p> : null}
      </div>
      <div className="min-w-0">
        <p className="text-[11px] font-bold uppercase tracking-wider text-mut md:hidden">Incoming CV</p>
        <Cell value={item.incoming} side="incoming" item={item} field={field} onOpen={onOpen} />
      </div>
    </li>
  );
}

function FieldBlock({ field, onOpen }: { field: CompareField; onOpen: (target: EvidenceTarget) => void }) {
  const [all, setAll] = useState(false);
  const shown = all ? field.items : field.items.slice(0, SHOWN);
  const differences = field.comparable ? field.items.filter((i) => i.status !== "same").length : 0;
  return (
    <section aria-labelledby={`field-${field.key}`} className="rounded border border-rule bg-panel">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule bg-inset px-3.5 py-1.5">
        <h3 id={`field-${field.key}`} className="text-[13px] font-bold">
          {field.label}
        </h3>
        <span className="text-xs text-mut">
          {!field.comparable
            ? "Not compared"
            : differences === 0
              ? "No differences"
              : `${differences} difference${differences === 1 ? "" : "s"}`}
        </span>
      </header>
      {field.note ? (
        <p className="hatch border-b border-rule px-3.5 py-1.5 text-[13px]" role="status">
          {field.note}
        </p>
      ) : null}
      {field.items.length === 0 ? (
        <p className="px-3.5 py-2.5 text-[13px] text-mut">Nothing was extracted from either CV for this section.</p>
      ) : (
        <ul>
          {shown.map((item, index) => (
            <Row key={`${item.status}-${item.label}-${index}`} item={item} field={field} onOpen={onOpen} />
          ))}
        </ul>
      )}
      {field.items.length > SHOWN ? (
        <div className="border-t border-rule px-3.5 py-1.5">
          <button type="button" aria-expanded={all} className="min-h-11 text-[13px] font-semibold text-human-ink underline sm:min-h-0" onClick={() => setAll(!all)}>
            {all ? "Show fewer" : `Show ${field.items.length - SHOWN} more`}
          </button>
        </div>
      ) : null}
      {field.key === "name" && field.stored_name ? (
        <p className="border-t border-rule px-3.5 py-1.5 text-xs text-mut">Name stored on the candidate profile: {field.stored_name}</p>
      ) : null}
    </section>
  );
}

/**
 * What differs, section by section. A difference is only claimed when both CVs produced items for the section;
 * otherwise the section says it was not compared and why.
 */
export function Changes({ comparison, onOpenEvidence }: { comparison: Comparison; onOpenEvidence: (target: EvidenceTarget) => void }) {
  return (
    <section aria-labelledby="changes-heading">
      <h2 id="changes-heading" className="mb-2 text-xs font-bold uppercase tracking-[0.07em] text-human-ink">
        What changed
      </h2>
      <div className="mb-1.5 hidden md:grid md:grid-cols-[minmax(0,1fr)_10.5rem_minmax(0,1fr)] md:gap-3 px-3.5 text-[11px] font-bold uppercase tracking-wider text-mut" aria-hidden="true">
        <span>Existing CV</span>
        <span className="text-center">Result</span>
        <span>Incoming CV</span>
      </div>
      <div className="space-y-3">
        {comparison.fields.map((field) => (
          <FieldBlock key={field.key} field={field} onOpen={onOpenEvidence} />
        ))}
      </div>
      <p className="mt-2 text-xs text-mut">
        Sections are read from each CV&apos;s text by a rule-based reader that looks for labelled headings. When it finds nothing
        in a section, that section is shown as not compared, and nothing in it is counted as a difference.
      </p>
    </section>
  );
}

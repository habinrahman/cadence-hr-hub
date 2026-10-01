import type { CompareSide, Comparison } from "@/lib/api";
import { documentStateMessage } from "@/lib/compare";
import { fileSize, plural, shortDateTime } from "@/lib/format";
import { Tag } from "@/components/ui/tag";

function Card({ title, kind, side, candidateName }: { title: string; kind: "existing" | "incoming"; side: CompareSide | null; candidateName: string | null }) {
  const document = side?.document ?? null;
  const problem = side ? documentStateMessage(side.state, kind) : documentStateMessage("no_document", kind);
  return (
    <section
      aria-label={title}
      className={`min-w-0 border bg-panel ${kind === "incoming" ? "border-human" : "border-rule-strong"}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-rule px-3.5 py-2">
        <h2 className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-mut">{title}</h2>
        {document ? (
          kind === "existing" ? (
            <Tag tone={document.is_current ? "neutral" : "unknown"}>{document.is_current ? "Current on file" : "Superseded"}</Tag>
          ) : (
            <Tag tone="neutral">{document.is_current ? "Now current" : "Awaiting decision"}</Tag>
          )
        ) : null}
      </header>
      <div className="px-3.5 py-3">
        {candidateName !== null ? <p className="break-words text-base font-bold">{candidateName || "Name not extracted"}</p> : null}
        {document ? (
          <dl className="mt-1.5 grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-1 text-[13px]">
            <dt className="text-mut">File</dt>
            <dd className="break-all font-mono text-[12px]" title={document.filename}>
              {document.filename}
            </dd>
            <dt className="text-mut">Uploaded</dt>
            <dd>{shortDateTime(document.received_at)}</dd>
            <dt className="text-mut">Size</dt>
            <dd>
              {plural(document.page_count, "page")} · {fileSize(document.byte_size)}
            </dd>
            <dt className="text-mut">Read as</dt>
            <dd>
              {document.text_source ?? "unknown source"}
              {document.language_code ? ` · ${document.language_code}` : ""}
            </dd>
          </dl>
        ) : null}
        {problem ? (
          <p className="hatch mt-2 border border-rule-strong px-2.5 py-1.5 text-[13px]" role="status">
            {problem}
          </p>
        ) : null}
      </div>
    </section>
  );
}

/** The two documents, side by side. The upload date is shown as an upload date and nothing more. */
export function DocumentCards({ comparison }: { comparison: Comparison }) {
  const existingName = comparison.candidate?.name ?? "";
  // The name each CV states for itself, read from its own text. Empty when the reader found none.
  const incomingName = comparison.fields.find((f) => f.key === "name")?.items[0]?.incoming?.label ?? "";
  return (
    <div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-2">
        <Card title="Previous CV" kind="existing" side={comparison.existing} candidateName={existingName} />
        <Card title="New CV" kind="incoming" side={comparison.incoming} candidateName={incomingName} />
      </div>
      <p className="mt-1.5 text-xs text-mut">
        Upload dates say when a file arrived, not which CV has newer content. Filenames are never used as evidence.
      </p>
    </div>
  );
}

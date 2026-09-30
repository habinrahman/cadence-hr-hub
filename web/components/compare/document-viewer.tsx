"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getDocumentPages, type CompareSide, type Comparison, type DocumentPages, type TextDiffLine } from "@/lib/api";
import { normalizeLine } from "@/lib/compare";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { Tabs } from "@/components/ui/tabs";
import type { EvidenceTarget } from "./field-comparison";

type Side = "existing" | "incoming";

function Panel({
  side,
  title,
  data,
  onlyHere,
  focus,
}: {
  side: Side;
  title: string;
  data: CompareSide | null;
  onlyHere: TextDiffLine[];
  focus: EvidenceTarget | null;
}) {
  const document = data?.document ?? null;
  const readable = data?.state === "ok" && document !== null;
  const [pages, setPages] = useState<DocumentPages | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const region = useRef<HTMLDivElement>(null);
  const differing = useMemo(() => new Set(onlyHere.map((line) => normalizeLine(line.text))), [onlyHere]);
  const quote = focus ? normalizeLine(focus.quote) : "";

  async function load() {
    if (!document || loading) return;
    setLoading(true);
    setError(null);
    try {
      setPages(await getDocumentPages(document.id));
    } catch (reason) {
      setError(reason);
    } finally {
      setLoading(false);
    }
  }

  // Evidence links open the text on the page the evidence came from.
  useEffect(() => {
    if (!focus || !readable) return;
    if (focus.page) setPage(focus.page);
    if (!pages && !loading) void load();
    region.current?.scrollIntoView({ block: "nearest" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus]);

  const current = pages?.pages.find((p) => p.number === page) ?? pages?.pages[0];

  return (
    <section aria-label={`${title} text`} className="min-w-0 rounded border border-rule bg-panel" ref={region}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-rule bg-inset px-3.5 py-1.5">
        <h3 className="text-[13px] font-bold">{title}</h3>
        {readable && !pages ? (
          <Button variant="secondary" busy={loading} onClick={load}>
            Open CV text
          </Button>
        ) : null}
      </header>
      {!readable ? (
        <p className="hatch px-3.5 py-3 text-[13px]" role="status">
          No readable text is on file for this CV, so there is nothing to show here.
        </p>
      ) : !pages && !loading && !error ? (
        <p className="px-3.5 py-3 text-[13px] text-mut">
          The text loads only when you open it. Opening CV text is recorded in the audit trail.
        </p>
      ) : null}
      {loading ? <div className="p-3.5" aria-busy="true"><Skeleton lines={6} /></div> : null}
      {error ? <div className="p-3"><ErrorState error={error} onRetry={load} /></div> : null}
      {pages && current ? (
        <div>
          <div className="flex flex-wrap items-center gap-1.5 border-b border-rule px-3.5 py-1.5">
            {pages.pages.length <= 8 ? (
              pages.pages.map((p) => (
                <button
                  key={p.number}
                  type="button"
                  aria-pressed={p.number === current.number}
                  onClick={() => setPage(p.number)}
                  className={`min-h-9 min-w-9 rounded-[3px] border px-2 text-[13px] font-semibold ${
                    p.number === current.number ? "border-human-ink bg-human-ink text-white" : "border-rule-strong bg-panel"
                  }`}
                >
                  <span className="sr-only">Page </span>
                  {p.number}
                </button>
              ))
            ) : (
              <label className="text-[13px]">
                <span className="mr-2 font-semibold">Page</span>
                <select className="min-h-9 rounded border border-rule-strong bg-panel px-2" value={current.number} onChange={(e) => setPage(Number(e.target.value))}>
                  {pages.pages.map((p) => (
                    <option key={p.number} value={p.number}>
                      {p.number} of {pages.pages.length}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <span className="text-xs text-mut">
              {onlyHere.length > 0 ? "Marked lines appear only in this CV." : "No lines are unique to this CV."}
            </span>
          </div>
          <div className="max-h-[32rem] overflow-y-auto px-3.5 py-2 font-mono text-[12px] leading-relaxed" tabIndex={0} aria-label={`${title}, page ${current.number}`}>
            {current.text.split("\n").map((line, index) => {
              const normal = normalizeLine(line);
              const unique = normal.length > 0 && differing.has(normal);
              const cited = normal.length > 2 && quote.length > 0 && quote.includes(normal);
              return (
                <div
                  key={index}
                  className={`whitespace-pre-wrap break-words ${unique ? "border-l-[3px] border-prop bg-prop-bg pl-1.5" : "pl-[9px]"} ${cited ? "outline outline-2 outline-human" : ""}`}
                >
                  {unique ? <span className="sr-only">Only in this CV: </span> : null}
                  {cited ? <span className="sr-only">Cited evidence: </span> : null}
                  {line || " "}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </section>
  );
}

/** The source text of both CVs. Side by side on wide screens, one at a time on a phone. */
export function DocumentCompare({ comparison, focus }: { comparison: Comparison; focus: EvidenceTarget | null }) {
  const [mobile, setMobile] = useState<Side>("incoming");
  useEffect(() => {
    if (focus) setMobile(focus.side);
  }, [focus]);
  const diff = comparison.text_diff;
  const panels: { side: Side; title: string; data: CompareSide | null; lines: TextDiffLine[] }[] = [
    { side: "existing", title: "Existing CV", data: comparison.existing, lines: diff?.existing_only ?? [] },
    { side: "incoming", title: "Incoming CV", data: comparison.incoming, lines: diff?.incoming_only ?? [] },
  ];
  return (
    <section aria-labelledby="docs-heading">
      <h2 id="docs-heading" className="mb-2 text-xs font-bold uppercase tracking-[0.07em] text-human-ink">
        Source documents
      </h2>
      {diff?.available ? (
        <p className="mb-2 text-[13px]">
          {diff.incoming_only_count === 0 && diff.existing_only_count === 0
            ? "The text of the two CVs is the same after collapsing spaces."
            : `${diff.incoming_only_count} line${diff.incoming_only_count === 1 ? "" : "s"} only in the incoming CV, ${diff.existing_only_count} only in the existing CV.`}{" "}
          <span className="text-xs text-mut">{diff.note}</span>
          {diff.truncated ? <span className="text-xs text-mut"> Only the first lines are marked.</span> : null}
        </p>
      ) : (
        <p className="mb-2 text-[13px] text-mut">A text comparison is not available for this pair.</p>
      )}
      <div className="md:hidden">
        <Tabs
          label="Choose a CV"
          value={mobile}
          onChange={(id) => setMobile(id as Side)}
          tabs={[
            { id: "existing", label: "Existing CV" },
            { id: "incoming", label: "Incoming CV" },
          ]}
        />
      </div>
      <div className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-2">
        {panels.map((p) => (
          <div
            key={p.side}
            id={`panel-${p.side}`}
            role="tabpanel"
            aria-labelledby={`tab-${p.side}`}
            className={mobile === p.side ? "block" : "hidden md:block"}
          >
            <Panel side={p.side} title={p.title} data={p.data} onlyHere={p.lines} focus={focus && focus.side === p.side ? focus : null} />
          </div>
        ))}
      </div>
    </section>
  );
}

import { Fragment } from "react";

function escapeRegExp(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function Highlighted({ text, terms }: { text: string; terms: string[] }) {
  const usable = terms.filter((t) => t.length >= 2);
  if (usable.length === 0) return <>{text}</>;
  const pattern = new RegExp(`(${usable.map(escapeRegExp).join("|")})`, "gi");
  const parts = text.split(pattern);
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <mark key={index} className="bg-[#ffe08a] px-px text-ink">
            {part}
          </mark>
        ) : (
          <Fragment key={index}>{part}</Fragment>
        ),
      )}
    </>
  );
}

/** Operational evidence: the quote, and exactly where it came from. */
export function EvidenceQuote({
  quote,
  page,
  verified,
  source,
  highlight,
}: {
  quote: string;
  page?: number | null;
  verified?: boolean;
  source?: string;
  highlight?: string;
}) {
  const terms = (highlight ?? "").split(/\s+/).filter(Boolean);
  let line: string;
  if (source) line = source;
  else if (verified === false) line = `CV${page ? ` p.${page}` : ""} · quote not verified`;
  else line = `CV${page ? ` p.${page}` : ""} ✓ verified`;
  return (
    <blockquote className="my-1.5 border-l-[3px] border-ev bg-gradient-to-r from-ev/10 to-transparent py-0.5 pl-2.5">
      <p className="break-words">
        <Highlighted text={quote} terms={terms} />
      </p>
      <footer className={`mt-0.5 font-mono text-[11px] font-semibold ${verified === false ? "text-prop-ink" : "text-ev-ink"}`}>
        {line}
      </footer>
    </blockquote>
  );
}

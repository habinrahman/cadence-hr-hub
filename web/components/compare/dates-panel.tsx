import type { CompareDateFact, CompareDates } from "@/lib/api";
import { shortDate, shortDateTime } from "@/lib/format";

function Fact({ fact }: { fact: CompareDateFact | undefined }) {
  if (!fact) return <span className="text-mut">Not found in the text</span>;
  return (
    <span>
      {shortDate(fact.date)} <span className="text-xs text-mut">· page {fact.page}</span>
    </span>
  );
}

const NEWER = { incoming: "the new CV", existing: "the previous CV", same: "neither (same date)" } as const;

/** Dates as the CVs state them, with their source page. Nothing here is inferred from a filename. */
export function DatesPanel({ dates }: { dates: CompareDates }) {
  return (
    <section aria-labelledby="dates-heading">
      <h2 id="dates-heading" className="mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-mut">
        Dates
      </h2>
      {dates.conflict ? (
        <p role="alert" className="mb-2 border border-prop bg-prop-bg px-3 py-2 text-[13px] font-semibold text-prop-ink">
          Date information conflicts. The version date the CVs label points to {dates.newer_by_labelled ? NEWER[dates.newer_by_labelled] : "one CV"},
          while the latest date mentioned points to {dates.newer_by_mentioned ? NEWER[dates.newer_by_mentioned] : "the other"}. Read both
          before deciding.
        </p>
      ) : null}
      <div className="overflow-x-auto border border-rule bg-panel">
        <table className="w-full border-collapse text-left text-[13px]">
          <caption className="sr-only">Dates read from each CV</caption>
          <thead>
            <tr className="bg-inset text-[11px] uppercase tracking-wider text-human-ink">
              <th scope="col" className="px-3 py-1.5 font-bold">Date</th>
              <th scope="col" className="px-3 py-1.5 font-bold">Previous CV</th>
              <th scope="col" className="px-3 py-1.5 font-bold">New CV</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-t border-rule align-top">
              <th scope="row" className="px-3 py-2 font-semibold">Version date the CV labels</th>
              <td className="px-3 py-2"><Fact fact={dates.existing?.labelled_version} /></td>
              <td className="px-3 py-2"><Fact fact={dates.incoming?.labelled_version} /></td>
            </tr>
            <tr className="border-t border-rule align-top">
              <th scope="row" className="px-3 py-2 font-semibold">Latest date mentioned in the text</th>
              <td className="px-3 py-2"><Fact fact={dates.existing?.latest_mentioned} /></td>
              <td className="px-3 py-2"><Fact fact={dates.incoming?.latest_mentioned} /></td>
            </tr>
            <tr className="border-t border-rule align-top">
              <th scope="row" className="px-3 py-2 font-semibold">Uploaded to Cadence</th>
              <td className="px-3 py-2">{shortDateTime(dates.uploaded.existing)}</td>
              <td className="px-3 py-2">{shortDateTime(dates.uploaded.incoming)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p className="mt-1.5 text-xs text-mut">
        The latest date mentioned can be a graduation or a planned date, so it is evidence, not proof of which CV is newer. The upload date
        only says when the file arrived.
      </p>
    </section>
  );
}

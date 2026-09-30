import type { ReactNode } from "react";

export type Column<T> = { header: string; cell: (row: T) => ReactNode; primary?: boolean; className?: string };

/** A real table from 640 px up; stacked cards below it. The primary column becomes the card heading. */
export function ResponsiveTable<T>({
  rows,
  rowKey,
  columns,
  caption,
}: {
  rows: T[];
  rowKey: (row: T) => string;
  columns: Column<T>[];
  caption: string;
}) {
  const primary = columns.find((c) => c.primary) ?? columns[0];
  const rest = columns.filter((c) => c !== primary);
  return (
    <>
      <table className="hidden w-full border-collapse text-left sm:table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th
                key={c.header}
                scope="col"
                className="border-b border-rule-strong bg-inset px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-human-ink"
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-t border-rule align-top">
              {columns.map((c) => (
                <td key={c.header} className={`px-3 py-2.5 ${c.className ?? ""}`}>
                  {c.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="divide-y divide-rule sm:hidden" aria-label={caption}>
        {rows.map((row) => (
          <li key={rowKey(row)} className="py-3">
            <div className="font-semibold break-words">{primary.cell(row)}</div>
            <dl className="mt-1.5 space-y-1.5">
              {rest.map((c) => (
                <div key={c.header}>
                  <dt className="text-[11px] font-bold uppercase tracking-wider text-mut">{c.header}</dt>
                  <dd className="break-words">{c.cell(row)}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}

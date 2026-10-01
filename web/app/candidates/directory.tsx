"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listCandidates, type CandidateRow } from "@/lib/api";
import { plural, relativeAge } from "@/lib/format";
import { Avatar } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icons";
import { Panel } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";

const PAGE = 25;
const SOURCE: Record<string, string> = { upload: "CV upload", excel: "Excel import" };

/** Every confirmed profile, newest first. Reading this list writes nothing to the audit trail. */
export function Directory() {
  const [rows, setRows] = useState<CandidateRow[]>([]);
  const [total, setTotal] = useState<number | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(true);

  function load(offset: number) {
    setBusy(true);
    setError(null);
    listCandidates(PAGE, offset)
      .then((page) => {
        setRows((current) => (offset === 0 ? page.candidates : [...current, ...page.candidates]));
        setTotal(page.total);
      })
      .catch(setError)
      .finally(() => setBusy(false));
  }

  useEffect(() => load(0), []);

  if (error) return <ErrorState error={error} onRetry={() => load(rows.length)} />;
  if (total === null) {
    return (
      <div aria-busy="true" aria-label="Loading candidates">
        <PanelSkeleton rows={4} />
      </div>
    );
  }
  if (total === 0) {
    return <EmptyState title="No confirmed profiles yet" body="Profiles appear here once an imported CV has been read and confirmed." />;
  }

  return (
    <section aria-label="All candidates">
      <Panel>
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-rule px-5 py-3.5">
          <p className="text-[14px]">
            <span className="text-[18px] font-semibold">{total}</span> <span className="text-mut">{total === 1 ? "confirmed profile" : "confirmed profiles"}</span>
          </p>
          <p className="text-[12.5px] text-mut">Newest update first. Opening a record is written to the audit trail.</p>
        </div>
        <div
          aria-hidden="true"
          className="hidden grid-cols-1 gap-4 border-b border-rule bg-inset px-5 py-2.5 font-mono text-[11px] uppercase tracking-[0.12em] text-mut xl:grid xl:grid-cols-[minmax(0,15rem)_minmax(0,11rem)_5.5rem_minmax(0,1fr)_7rem_7rem_2rem]"
        >
          <span>Candidate</span>
          <span>Latest role</span>
          <span>Experience</span>
          <span>Key skills</span>
          <span>Source</span>
          <span>Updated</span>
          <span />
        </div>
        <ul>
          {rows.map((row) => {
            const name = row.candidate_name ?? "Unnamed candidate";
            return (
              <li
                key={row.candidate_id}
                className="grid grid-cols-[minmax(0,1fr)] items-center gap-x-4 gap-y-2 border-t border-rule px-5 py-3.5 first:border-t-0 xl:grid-cols-[minmax(0,15rem)_minmax(0,11rem)_5.5rem_minmax(0,1fr)_7rem_7rem_2rem]"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <Avatar name={row.candidate_name} />
                  <Link href={`/candidates/${row.candidate_id}`} prefetch={false} className="min-w-0 break-words text-[14px] font-semibold text-ink no-underline hover:text-human-ink">
                    {name}
                  </Link>
                </div>
                <p className="min-w-0 truncate text-[13px]">{row.latest_title ?? <span className="text-mut">Not stated</span>}</p>
                <p className="text-[13px] tabular-nums">
                  {row.years_of_experience === null ? <span className="text-mut">Not stated</span> : `${row.years_of_experience} yrs`}
                </p>
                <ul className="flex min-w-0 flex-wrap gap-1.5">
                  {row.skills.length === 0 ? (
                    <li className="text-[13px] text-mut">None extracted</li>
                  ) : (
                    row.skills.slice(0, 4).map((skill) => (
                      <li key={skill} className="border border-rule bg-inset px-2 py-0.5 text-[12px]">
                        {skill}
                      </li>
                    ))
                  )}
                  {row.skills.length > 4 ? <li className="py-0.5 text-[12px] text-mut">+{row.skills.length - 4}</li> : null}
                </ul>
                <p className="text-[12.5px] text-mut">{SOURCE[row.source] ?? row.source}</p>
                <p className="text-[12.5px] text-mut">{relativeAge(row.updated_at)}</p>
                <Link
                  href={`/candidates/${row.candidate_id}`}
                  prefetch={false}
                  aria-label={`Open the record for ${name}`}
                  className="inline-flex h-9 items-center text-human-ink no-underline xl:w-8 xl:justify-center"
                >
                  <Icon name="arrowUpRight" size={17} />
                </Link>
              </li>
            );
          })}
        </ul>
        {rows.length < total ? (
          <div className="flex items-center justify-between gap-3 border-t border-rule px-5 py-3">
            <p className="text-[12.5px] text-mut">
              Showing {rows.length} of {plural(total, "profile")}
            </p>
            <Button busy={busy} onClick={() => load(rows.length)}>
              Show more
            </Button>
          </div>
        ) : null}
      </Panel>
    </section>
  );
}

"use client";

import Link from "next/link";
import { useState } from "react";
import type { CandidateGroup } from "@/lib/search-state";
import { SEARCH_REASON } from "@/lib/labels";
import { plural } from "@/lib/format";
import { EvidenceQuote } from "@/components/domain/evidence-quote";
import { Avatar } from "@/components/ui/avatar";
import { Icon } from "@/components/ui/icons";
import { Tag } from "@/components/ui/tag";

const SHOWN = 2;

/** One candidate in the results table: who, why they matched, and the passage that says so. */
export function ResultGroup({ group, highlight }: { group: CandidateGroup; highlight: string }) {
  const [all, setAll] = useState(false);
  const hits = all ? group.hits : group.hits.slice(0, SHOWN);
  const name = group.name ?? "Unnamed candidate";
  return (
    <li className="grid grid-cols-[minmax(0,1fr)] gap-x-6 gap-y-3 border-t border-rule px-5 py-4 first:border-t-0 xl:grid-cols-[17rem_minmax(0,17rem)_minmax(0,1fr)_2rem]">
      <div className="flex min-w-0 items-start gap-3">
        <Avatar name={group.name} />
        <div className="min-w-0">
          <h3 className="break-words text-[14.5px] font-semibold leading-tight">{name}</h3>
          <p className="mt-0.5 text-[12.5px] text-mut">
            {plural(group.hits.length, "matching passage")}
            {group.hits.some((h) => h.confirmed_profile === false) ? " · profile not confirmed" : ""}
          </p>
        </div>
      </div>

      <div className="min-w-0">
        <ul className="flex flex-wrap gap-1.5">
          {group.exact.map((reason) => (
            <li key={reason}>
              <Tag tone="ok">{SEARCH_REASON[reason] ?? reason}</Tag>
            </li>
          ))}
          {group.approximate.map((reason) => (
            <li key={reason}>
              <Tag tone="unknown">≈ {SEARCH_REASON[reason] ?? reason}</Tag>
            </li>
          ))}
        </ul>
        {group.approximateOnly ? (
          <p className="mt-1.5 text-[12px] font-semibold text-prop-ink">Only approximate wording matched. Read the CV before relying on this.</p>
        ) : null}
      </div>

      <div className="min-w-0 text-[13px]">
        <ul>
          {hits.map((hit) => (
            <li key={`${hit.document_id}-${hit.chunk_id ?? "profile"}`}>
              <EvidenceQuote
                quote={hit.evidence}
                highlight={highlight}
                source={hit.chunk_id ? "Passage from a CV" : "Profile fields"}
              />
            </li>
          ))}
        </ul>
        {group.hits.length > SHOWN ? (
          <button type="button" aria-expanded={all} className="min-h-11 text-[12.5px] font-semibold text-human-ink underline sm:min-h-0" onClick={() => setAll(!all)}>
            {all ? "Show fewer passages" : `Show ${plural(group.hits.length - SHOWN, "more passage")}`}
          </button>
        ) : null}
      </div>

      <div className="flex items-start xl:justify-end">
        {group.candidateId ? (
          <Link
            href={`/candidates/${group.candidateId}`}
            prefetch={false}
            aria-label={`Open the record for ${name}`}
            className="inline-flex h-9 items-center gap-1.5 text-[13px] font-semibold text-human-ink no-underline xl:w-8 xl:justify-center"
          >
            <span className="xl:sr-only">Open record</span>
            <Icon name="arrowUpRight" size={17} />
          </Link>
        ) : (
          <span className="text-[12px] text-mut">No profile linked</span>
        )}
      </div>
    </li>
  );
}

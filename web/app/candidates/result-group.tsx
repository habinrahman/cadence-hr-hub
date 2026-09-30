"use client";

import { useState } from "react";
import type { CandidateGroup } from "@/lib/search-state";
import { SEARCH_REASON } from "@/lib/labels";
import { plural } from "@/lib/format";
import { EvidenceQuote } from "@/components/domain/evidence-quote";
import { LinkButton } from "@/components/ui/button";
import { PanelRow } from "@/components/ui/panel";
import { Tag } from "@/components/ui/tag";

const SHOWN = 3;

export function ResultGroup({ group, highlight }: { group: CandidateGroup; highlight: string }) {
  const [all, setAll] = useState(false);
  const hits = all ? group.hits : group.hits.slice(0, SHOWN);
  return (
    <PanelRow>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="min-w-0 break-words text-base font-bold">{group.name ?? "Unnamed candidate"}</h3>
        {group.candidateId ? (
          <LinkButton href={`/candidates/${group.candidateId}`}>Open profile</LinkButton>
        ) : (
          <span className="text-xs text-mut">No profile linked</span>
        )}
      </div>

      <p className="mt-1.5 flex flex-wrap items-center gap-1.5">
        {group.exact.map((reason) => (
          <span key={reason} className="inline-flex items-center gap-1">
            <Tag tone="ok">Exact</Tag>
            <span className="text-xs">{SEARCH_REASON[reason] ?? reason}</span>
          </span>
        ))}
        {group.approximate.map((reason) => (
          <span key={reason} className="inline-flex items-center gap-1">
            <Tag tone="unknown">Approximate</Tag>
            <span className="text-xs">{SEARCH_REASON[reason] ?? reason}</span>
          </span>
        ))}
      </p>
      {group.approximateOnly ? (
        <p className="mt-1 text-xs font-semibold text-prop-ink">
          Only approximate wording matched. Read the CV before relying on this.
        </p>
      ) : null}

      <ul className="mt-1">
        {hits.map((hit) => (
          <li key={`${hit.document_id}-${hit.chunk_id ?? "profile"}`}>
            <EvidenceQuote
              quote={hit.evidence}
              highlight={highlight}
              source={`${hit.chunk_id ? "Passage from a CV" : "Profile fields"}${hit.confirmed_profile === false ? " · profile not confirmed" : ""}`}
            />
          </li>
        ))}
      </ul>
      {group.hits.length > SHOWN ? (
        <button type="button" className="text-xs font-semibold text-human-ink underline" onClick={() => setAll(!all)}>
          {all ? "Show fewer passages" : `Show ${plural(group.hits.length - SHOWN, "more passage")}`}
        </button>
      ) : null}
    </PanelRow>
  );
}

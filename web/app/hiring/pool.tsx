"use client";

import { useMemo, useState } from "react";
import type { CandidateMatch, PoolStatus } from "@/lib/api";
import { EMPTY_FILTERS, comparePool, filterPool, statusGroup, type PoolFilters } from "@/lib/pool-filters";
import { Button, LinkButton } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { inputClass } from "@/components/ui/field";
import { Panel } from "@/components/ui/panel";
import { Tag } from "@/components/ui/tag";
import { MatchCard, type ShortlistState } from "./matches";

const PAGE = 20;
const STATUSES: { id: PoolFilters["matchStatus"]; label: string }[] = [
  { id: "open", label: "In play" },
  { id: "eligible", label: "Eligible" },
  { id: "review", label: "Needs review" },
  { id: "excluded", label: "Excluded" },
  { id: "rejected", label: "Rejected" },
];

const STATUS_NOTE: Partial<Record<PoolFilters["matchStatus"], string>> = {
  excluded:
    "Excluded: the CV does not meet a mandatory requirement. Check the evidence; if Cadence read the CV wrongly, report a problem from the candidate's profile.",
  rejected: "Rejected by a recruiter for this request. Restore a candidate to put them back in the pool.",
};

/** Says which requirements the pool was matched on. Only a confirmed pool can be shortlisted or shared. */
export function PoolStatusBanner({ status, rematching = false }: { status: PoolStatus; rematching?: boolean }) {
  if (status !== "confirmed" && rematching) {
    return (
      <div role="status" className="proposal px-3 py-2.5">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Tag tone="proposed">Provisional</Tag>
          <span>
            <strong>Re-matching on the approved requirements</strong>
          </span>
        </p>
        <p className="mt-1 text-[13px]">
          This is still the provisional pool. When matching finishes, it is replaced by the confirmed pool and shortlisting
          switches on. This page updates by itself.
        </p>
      </div>
    );
  }
  if (status === "confirmed") {
    return (
      <div role="status" className="border border-ok/40 bg-ok-bg px-3 py-2.5">
        <p>
          <Tag tone="decided">Confirmed</Tag> <strong>Confirmed match pool</strong>
        </p>
        <p className="mt-1 text-[13px]">Matched against HR-approved requirements.</p>
        <p className="text-[13px]">Next: add the candidates you want to the shortlist, then review and approve &amp; send each one.</p>
      </div>
    );
  }
  return (
    <div role="status" className="proposal px-3 py-2.5">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Tag tone="proposed">Provisional</Tag>
        <span>
          <strong>Provisional match pool</strong> — HR approval required
        </span>
      </p>
      <p className="mt-1 text-[13px]">
        Based on automatically extracted requirements — review requirements before shortlisting. Shortlisting, rejecting and
        sharing stay off until HR approves the requirements and matching re-runs on them. You can read every candidate now.
      </p>
      <p className="mt-2">
        <LinkButton variant="primary" href="#requirements">
          Review requirements
        </LinkButton>
      </p>
    </div>
  );
}

export function Pool({
  matches,
  shortlist,
  shareApproved = {},
  busy,
  jobTitle,
  poolStatus = "provisional",
  rematching = false,
  onShortlistSelected,
  onReject,
  onShare,
  onRestore,
}: {
  matches: CandidateMatch[];
  shortlist: Record<string, ShortlistState>;
  shareApproved?: Record<string, boolean>;
  busy: boolean;
  jobTitle: string;
  poolStatus?: PoolStatus;
  /** An approval rematch is queued or running. */
  rematching?: boolean;
  onShortlistSelected: (matchIds: string[]) => void;
  onReject: (match: CandidateMatch) => void;
  onShare: (match: CandidateMatch) => void;
  onRestore?: (match: CandidateMatch) => void;
}) {
  const counts = useMemo(() => {
    const out: Record<PoolFilters["matchStatus"], number> = { open: 0, eligible: 0, review: 0, excluded: 0, rejected: 0 };
    for (const m of matches) {
      const group = statusGroup(m);
      out[group] += 1;
      if (group === "eligible" || group === "review") out.open += 1;
    }
    return out;
  }, [matches]);
  const [filters, setFilters] = useState<PoolFilters>(EMPTY_FILTERS);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [limit, setLimit] = useState(PAGE);
  const [rejecting, setRejecting] = useState<CandidateMatch | null>(null);
  const hasLocation = matches.some((m) => m.location);
  const locked = poolStatus !== "confirmed";
  const shown = useMemo(() => {
    const filtered = filterPool(matches, filters);
    // Shortlisted first, a recruiter's rejection last; otherwise eligible by score, then needs review, then excluded.
    const rank = (m: CandidateMatch) => (shortlist[m.candidate_id] === "yes" ? -1 : m.disposition === "rejected" ? 1 : 0);
    return [...filtered].sort((a, b) => rank(a) - rank(b) || comparePool(a, b));
  }, [matches, filters, shortlist]);

  const toggle = (id: string) =>
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="space-y-3">
      <PoolStatusBanner status={poolStatus} rematching={rematching} />
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <p id="pool-status" className="mb-1 text-xs font-semibold">
            Match status
          </p>
          <div role="radiogroup" aria-labelledby="pool-status" className="flex flex-wrap gap-1">
            {STATUSES.map((option) => {
              const on = filters.matchStatus === option.id;
              return (
                <button
                  key={option.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  className={`min-h-9 rounded-[3px] border px-2.5 text-xs font-semibold ${
                    on ? "border-human bg-human-bg text-human-ink" : "border-rule-strong bg-panel text-ink"
                  }`}
                  onClick={() => setFilters((cur) => ({ ...cur, matchStatus: option.id }))}
                >
                  {option.label} <span className="font-mono font-normal text-mut">{counts[option.id]}</span>
                </button>
              );
            })}
          </div>
        </div>
        <label className="text-xs font-semibold">
          Skill
          <input
            className={`${inputClass} mt-1`}
            value={filters.skill}
            onChange={(e) => setFilters((cur) => ({ ...cur, skill: e.target.value }))}
          />
        </label>
        {hasLocation ? (
          <label className="text-xs font-semibold">
            Location
            <input
              className={`${inputClass} mt-1`}
              value={filters.location}
              onChange={(e) => setFilters((cur) => ({ ...cur, location: e.target.value }))}
            />
          </label>
        ) : null}
        <label className="text-xs font-semibold">
          Minimum years
          <input
            type="number"
            min={0}
            className={`${inputClass} mt-1 w-28`}
            value={filters.minYears ?? ""}
            onChange={(e) =>
              setFilters((cur) => ({ ...cur, minYears: e.target.value === "" ? null : Number(e.target.value) }))
            }
          />
        </label>
      </div>
      <p className="text-sm text-mut">
        {shown.length} result{shown.length === 1 ? "" : "s"}
      </p>
      {STATUS_NOTE[filters.matchStatus] ? <p className="text-[13px]">{STATUS_NOTE[filters.matchStatus]}</p> : null}

      {shown.length === 0 ? (
        <p className="text-mut">No candidates match these filters.</p>
      ) : (
        <Panel>
          {shown.slice(0, limit).map((m, index) => {
            const state = shortlist[m.candidate_id] ?? "loading";
            const shortlistable = ["recommended", "needs_review"].includes(m.disposition);
            return (
              <MatchCard
                key={m.id}
                match={m}
                state={state}
                busy={busy}
                openMatrix={index === 0}
                locked={locked}
                shareApproved={shareApproved[m.candidate_id] === true}
                selectable={!locked && state !== "yes" && shortlistable}
                selected={selected.has(m.id)}
                onToggle={() => toggle(m.id)}
                onShortlist={() => onShortlistSelected([m.id])}
                onReject={() => setRejecting(m)}
                onShare={() => onShare(m)}
                onRestore={onRestore ? () => onRestore(m) : undefined}
              />
            );
          })}
        </Panel>
      )}
      {shown.length > limit ? (
        <Button onClick={() => setLimit(limit + PAGE)}>Show {Math.min(PAGE, shown.length - limit)} more</Button>
      ) : null}

      <div
        role="region"
        aria-label="Shortlist selection"
        className={`${locked ? "" : "sticky bottom-0 "}flex items-center justify-between gap-3 border border-rule bg-panel px-4 py-3`}
      >
        <span className="text-sm">
          {locked ? "Shortlisting is off until the requirements are approved." : `${selected.size} selected`}
        </span>
        <Button
          variant="primary"
          disabled={locked || selected.size === 0}
          busy={busy}
          onClick={() => {
            const ids = [...selected];
            setSelected(new Set());
            onShortlistSelected(ids);
          }}
        >
          Shortlist selected ({selected.size})
        </Button>
      </div>

      <ConfirmDialog
        open={rejecting !== null}
        title="Reject this candidate?"
        body={
          <p>
            Reject <strong>{rejecting?.candidate_name ?? "this candidate"}</strong> for {jobTitle}? The decision is recorded in the audit trail.
          </p>
        }
        confirmLabel="Reject candidate"
        tone="danger"
        busy={busy}
        onConfirm={() => {
          const m = rejecting;
          setRejecting(null);
          if (m) onReject(m);
        }}
        onCancel={() => setRejecting(null)}
      />
    </div>
  );
}

"use client";

import Link from "next/link";
import type { CandidateMatch, MatchRequirement } from "@/lib/api";
import { VERDICT } from "@/lib/labels";
import { matchBadge, requirementCounts } from "@/lib/pool-filters";
import { Button, LinkButton } from "@/components/ui/button";
import { PanelRow } from "@/components/ui/panel";
import { Tag } from "@/components/ui/tag";
import { RequirementMatrix, scoreLine, shownText } from "@/components/domain/requirement-matrix";

export type ShortlistState = "yes" | "no" | "unknown" | "loading";

/** "4.2 years experience" from the profile's value; null when the CV did not give it. */
export function yearsLine(years: number | null | undefined) {
  if (years == null || !Number.isFinite(years)) return null;
  const shown = Math.round(years * 10) / 10;
  return `${shown} ${shown === 1 ? "year" : "years"} experience`;
}

const VERDICT_MARK: Record<string, { mark: string; className: string }> = {
  meets: { mark: "✓", className: "text-ok-ink" },
  partial: { mark: "~", className: "text-prop-ink" },
  unmet: { mark: "✗", className: "text-bad-ink" },
  unknown: { mark: "?", className: "text-mut" },
};

/** The mandatory requirements holding a candidate at the gate, with their verdicts. Empty for an eligible one. */
function Blocking({ match }: { match: CandidateMatch }) {
  if (match.blocking_requirements.length === 0) return null;
  const tone = match.eligibility === "excluded" ? "text-bad-ink" : "text-prop-ink";
  return (
    <div aria-label="Blocking requirements" className={`text-[13px] ${tone}`}>
      <p className="font-semibold">Blocking:</p>
      <ul className="mt-0.5">
        {match.blocking_requirements.map((b) => (
          <li key={b.requirement_id}>
            {b.name} — {VERDICT[b.result]?.label ?? b.result}
          </li>
        ))}
      </ul>
      {match.eligibility === "needs_review" ? <p className="mt-0.5">Check the CV evidence before deciding.</p> : null}
    </div>
  );
}

/** Every requirement and its verdict, readable at a glance. The evidence sits under "Requirements and evidence". */
function VerdictList({ requirements }: { requirements: MatchRequirement[] }) {
  if (requirements.length === 0) return null;
  return (
    <ul aria-label="Requirement results" className="grid grid-cols-[minmax(0,1fr)] gap-x-6 gap-y-1 text-[13.5px] sm:grid-cols-2">
      {requirements.map((r) => {
        const mark = VERDICT_MARK[r.result] ?? VERDICT_MARK.unknown;
        return (
          <li key={r.requirement_id} className="flex min-w-0 items-baseline gap-2">
            <span aria-hidden="true" className={`w-3 shrink-0 text-center font-bold ${mark.className}`}>
              {mark.mark}
            </span>
            <span className="min-w-0 break-words">
              {shownText(r)}
              {r.strength === "mandatory" ? <span className="text-mut"> (mandatory)</span> : null}
              <span className={`font-semibold ${mark.className}`}> — {VERDICT[r.result]?.label ?? r.result}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function MatchCard({
  match,
  state,
  busy,
  openMatrix,
  locked = false,
  shareApproved = false,
  selectable = false,
  selected = false,
  onToggle,
  onShortlist,
  onReject,
  onShare,
  onRestore,
}: {
  match: CandidateMatch;
  state: ShortlistState;
  busy: boolean;
  openMatrix: boolean;
  /** A provisional pool: the card can be read and rejected, but not shortlisted or shared. */
  locked?: boolean;
  /** The share for this shortlisted candidate was approved (it may or may not have been sent). */
  shareApproved?: boolean;
  selectable?: boolean;
  selected?: boolean;
  onToggle?: () => void;
  onShortlist: () => void;
  onReject: () => void;
  onShare: () => void;
  /** Undo a recruiter's rejection. */
  onRestore?: () => void;
}) {
  const badge = matchBadge(match.disposition);
  const scored = match.eligibility === "eligible" && match.match_score != null;
  const shortlistable = ["recommended", "needs_review"].includes(match.disposition);
  const closed = match.disposition === "excluded" || match.disposition === "rejected";
  const name = match.candidate_name ?? "Unnamed candidate";

  return (
    <PanelRow hue={state === "yes" ? "share" : "match"} className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          {selectable ? (
            <input
              type="checkbox"
              className="mt-1.5 h-4 w-4"
              aria-label={`Select ${name}`}
              checked={selected}
              onChange={onToggle}
            />
          ) : null}
          <div className="min-w-0">
            <h3 className="break-words text-base font-bold">
              <Link href={`/candidates/${match.candidate_id}`} prefetch={false}>
                {name}
              </Link>
            </h3>
            <p className="mt-0.5 flex flex-wrap items-center gap-2">
              {state === "yes" ? <Tag tone="decided">Shortlisted</Tag> : null}
              {state === "unknown" && shortlistable ? <Tag tone="unknown">Shortlist state unknown</Tag> : null}
              <span className="font-semibold">
                {match.mandatory_total + match.preferred_total > 0 ? `${requirementCounts(match)} requirements met` : "No requirements compared"}
              </span>
            </p>
            {yearsLine(match.years_of_experience) ? (
              <p className="mt-1 text-[13px] text-mut">{yearsLine(match.years_of_experience)}</p>
            ) : null}
          </div>
        </div>
        <div className="shrink-0 text-right">
          {/* Only a candidate who meets every mandatory requirement gets a number; a held one gets its gate state. */}
          {scored ? (
            <p className="leading-none" aria-label={`Match score ${match.match_score} out of 100`}>
              <span className="text-[30px] font-semibold tracking-tight tabular-nums">{match.match_score}</span>
              <span className="ml-1 text-[14px] font-semibold text-mut">/ 100</span>
            </p>
          ) : (
            <p className="text-[13px] text-mut">No match score</p>
          )}
          <p className="mt-1.5">
            <Tag tone={badge.tone}>{badge.label}</Tag>
          </p>
        </div>
      </div>

      <Blocking match={match} />
      <VerdictList requirements={match.requirements} />

      {match.explanation && match.requirements.length === 0 ? <p className="text-mut">{match.explanation}</p> : null}

      <details open={openMatrix}>
        <summary className="cursor-pointer text-[13px] font-semibold text-human-ink">Requirements and evidence</summary>
        <div className="mt-2">
          <RequirementMatrix requirements={match.requirements} />
          {scored && scoreLine(match.requirements, match.match_score, match.match_score_exact) ? (
            <p className="mt-2 text-[13px] text-mut">
              {scoreLine(match.requirements, match.match_score, match.match_score_exact)}. Cadence scoring policy: the score is given
              only to candidates who meet every mandatory requirement, and ranks them. Mandatory requirements share 70 points and
              preferred ones 30 (one kind alone shares all 100). Meets earns the full share and partial half. 100 means every
              requirement in this request was met, not a perfect candidate.
            </p>
          ) : (
            <p className="mt-2 text-[13px] text-mut">
              No match score: {match.score_reason.charAt(0).toLowerCase() + match.score_reason.slice(1)}. The score ranks only
              candidates who meet every mandatory requirement, so a candidate held at that gate is not given one.
            </p>
          )}
        </div>
      </details>

      {shortlistable && state !== "yes" && !locked ? (
        <p className="text-[12.5px] text-prop-ink">
          <Tag tone="proposed">Proposed by Cadence</Tag> {badge.label}. The matcher never shortlists. A recruiter decides.
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        {state === "yes" ? (
          <Button variant="primary" busy={busy} disabled={locked} onClick={onShare}>
            Review share…
          </Button>
        ) : (
          <Button variant="primary" busy={busy} disabled={locked || !shortlistable} onClick={onShortlist}>
            Add to shortlist
          </Button>
        )}
        {/* The approval rematch rewrites each disposition, so a rejection made on a provisional pool would not last. */}
        <Button variant="danger" busy={busy} disabled={locked || closed} onClick={onReject}>
          Reject…
        </Button>
        <LinkButton variant="quiet" href={`/candidates/${match.candidate_id}`}>
          Open profile
        </LinkButton>
      </div>
      {locked && shortlistable ? (
        <p className="text-[12.5px] text-mut">
          Shortlist, reject and share are off while the pool is provisional. They switch on once HR approves the requirements
          and matching re-runs on them.
        </p>
      ) : state === "yes" && !locked ? (
        <p className="text-[12.5px] text-mut">
          {shareApproved
            ? "Shortlisted and the share was approved. Open the share review to see the send record."
            : "Shortlisted. The share is not approved yet. Review what would be shared, then approve & send."}
        </p>
      ) : null}
      {match.disposition === "rejected" ? (
        <p className="flex flex-wrap items-center gap-2">
          <Tag tone="decided">Decided</Tag> Rejected by a recruiter for this request.
          {onRestore ? (
            <Button busy={busy} disabled={locked} onClick={onRestore}>
              Restore to pool
            </Button>
          ) : null}
        </p>
      ) : null}
    </PanelRow>
  );
}

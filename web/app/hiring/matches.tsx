"use client";

import Link from "next/link";
import { useState } from "react";
import type { CandidateMatch } from "@/lib/api";
import { DISPOSITION } from "@/lib/labels";
import { Button, LinkButton } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Panel, PanelRow } from "@/components/ui/panel";
import { Tag } from "@/components/ui/tag";
import { countMet, RequirementMatrix } from "@/components/domain/requirement-matrix";

export type ShortlistState = "yes" | "no" | "unknown" | "loading";

const ORDER = ["recommended", "needs_review", "excluded", "rejected"];
const PAGE = 20;

export function Matches({
  matches,
  shortlist,
  busy,
  approvedCount,
  jobTitle,
  onRun,
  onShortlist,
  onReject,
  onShare,
}: {
  matches: CandidateMatch[];
  shortlist: Record<string, ShortlistState>;
  busy: boolean;
  approvedCount: number;
  jobTitle: string;
  onRun: () => void;
  onShortlist: (match: CandidateMatch) => void;
  onReject: (match: CandidateMatch) => void;
  onShare: (match: CandidateMatch) => void;
}) {
  const [rejecting, setRejecting] = useState<CandidateMatch | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const sorted = [...matches].sort((a, b) => {
    const rank = (m: CandidateMatch) => (shortlist[m.candidate_id] === "yes" ? -1 : ORDER.indexOf(m.disposition));
    return rank(a) - rank(b);
  });

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Button variant="primary" busy={busy} disabled={approvedCount === 0} onClick={onRun}>
          {matches.length ? "Run matching again" : "Run matching"}
        </Button>
        <span className="text-xs text-mut">
          {approvedCount === 0
            ? "Approve at least one requirement first. Matching uses approved requirements only."
            : "Matching compares approved requirements only. It never shortlists or shares anyone."}
        </span>
      </div>

      {matches.length === 0 ? (
        <p className="text-mut">Matching has not been run for this request.</p>
      ) : (
        <Panel>
          {sorted.slice(0, limit).map((m, index) => (
            <MatchCard
              key={m.id}
              match={m}
              state={shortlist[m.candidate_id] ?? "loading"}
              busy={busy}
              openMatrix={index < 3}
              onShortlist={() => onShortlist(m)}
              onReject={() => setRejecting(m)}
              onShare={() => onShare(m)}
            />
          ))}
        </Panel>
      )}
      {sorted.length > limit ? (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <Button onClick={() => setLimit(limit + PAGE)}>Show {Math.min(PAGE, sorted.length - limit)} more</Button>
          <span className="text-xs text-mut">
            {limit} of {sorted.length} candidates shown. Shortlisted candidates come first, then recommended, then needs review.
          </span>
        </div>
      ) : null}

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

function MatchCard({
  match,
  state,
  busy,
  openMatrix,
  onShortlist,
  onReject,
  onShare,
}: {
  match: CandidateMatch;
  state: ShortlistState;
  busy: boolean;
  openMatrix: boolean;
  onShortlist: () => void;
  onReject: () => void;
  onShare: () => void;
}) {
  const disposition = DISPOSITION[match.disposition] ?? { label: match.disposition, tone: "neutral" as const };
  const { met, total } = countMet(match.requirements);
  const shortlistable = ["recommended", "needs_review"].includes(match.disposition);
  const closed = match.disposition === "excluded" || match.disposition === "rejected";

  return (
    <PanelRow hue={state === "yes" ? "share" : "match"} className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="break-words text-base font-bold">
            <Link href={`/candidates/${match.candidate_id}`} prefetch={false}>
              {match.candidate_name ?? "Unnamed candidate"}
            </Link>
          </h3>
          <p className="mt-0.5 flex flex-wrap items-center gap-2">
            <Tag tone={disposition.tone}>{disposition.label}</Tag>
            {state === "yes" ? <Tag tone="decided">Shortlisted</Tag> : null}
            {state === "unknown" && shortlistable ? <Tag tone="unknown">Shortlist state unknown</Tag> : null}
            <span className="font-semibold">
              {met} of {total} requirements met
            </span>
          </p>
        </div>
      </div>

      {match.explanation ? <p className="text-mut">{match.explanation}</p> : null}

      <details open={openMatrix}>
        <summary className="cursor-pointer text-[13px] font-semibold text-human-ink">Requirements and evidence</summary>
        <div className="mt-2">
          <RequirementMatrix requirements={match.requirements} />
          <div className="mt-3 grid grid-cols-[minmax(0,1fr)] gap-3 text-[13px] md:grid-cols-2">
            <div>
              <p className="font-semibold">Strengths</p>
              {match.strengths.length ? (
                <ul className="list-disc pl-5">
                  {match.strengths.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-mut">None recorded.</p>
              )}
            </div>
            <div>
              <p className="font-semibold">Gaps</p>
              {match.gaps.length ? (
                <ul className="list-disc pl-5">
                  {match.gaps.map((g) => (
                    <li key={g}>{g}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-mut">None recorded.</p>
              )}
            </div>
          </div>
        </div>
      </details>

      {shortlistable && state !== "yes" ? (
        <div className="proposal px-3 py-2">
          <Tag tone="proposed">Proposed by Cadence</Tag> {disposition.label}. The matcher never shortlists. A recruiter decides.
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {state === "yes" ? (
          <Button variant="primary" busy={busy} onClick={onShare}>
            Review share…
          </Button>
        ) : (
          <Button variant="primary" busy={busy} disabled={!shortlistable} onClick={onShortlist}>
            Add to shortlist
          </Button>
        )}
        <Button variant="danger" busy={busy} disabled={closed} onClick={onReject}>
          Reject…
        </Button>
        <LinkButton variant="quiet" href={`/candidates/${match.candidate_id}`}>
          Open profile
        </LinkButton>
      </div>
      {match.disposition === "rejected" ? (
        <p>
          <Tag tone="decided">Decided</Tag> Rejected by a recruiter.
        </p>
      ) : null}
    </PanelRow>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  type CandidateMatch,
  type Dashboard,
  type HiringRequirement,
  addHiringRequirement,
  approveHiringRequirements,
  editHiringRequirement,
  getDashboard,
  getHiringRequest,
  getSharePreview,
  listHiringMatches,
  openPool,
  rejectHiringRequirement,
  rejectMatch,
  restoreMatch,
  retryProcessing,
  runHiringMatch,
  shortlistMatch,
} from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { deriveLifecycle } from "@/lib/lifecycle";
import { PHASE, requestPhase } from "@/lib/request-phase";
import { shortDate } from "@/lib/format";
import { useAsync } from "@/lib/use-async";
import { PageHeader, RuleHeading } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { StatusText } from "@/components/ui/tag";
import { Stepper } from "@/components/ui/stepper";
import { useToast } from "@/components/ui/toast";
import { type ShortlistState } from "./matches";
import { Pool } from "./pool";
import { ProcessingCard } from "./processing-card";
import { RequestRecord } from "./record";
import { Requirements } from "./requirements";
import { SharePanel } from "./share-panel";

const PROBE_LIMIT = 20;
const PROBE_CONCURRENCY = 4;

export function Workspace({ requestId, initialCandidate }: { requestId: string; initialCandidate: string | null }) {
  const { notify } = useToast();
  const detailQ = useAsync(() => getHiringRequest(requestId), [requestId]);
  const matchesQ = useAsync(() => listHiringMatches(requestId), [requestId]);
  const [viewerId, setViewerId] = useState<string | null>(null);
  const [shortlist, setShortlist] = useState<Record<string, ShortlistState>>({});
  const [shareApproved, setShareApproved] = useState<Record<string, boolean>>({});
  const [shareCandidate, setShareCandidate] = useState<string | null>(initialCandidate);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);

  const detail = detailQ.data;
  const matches = useMemo(() => matchesQ.data?.matches ?? [], [matchesQ.data]);
  // The pool is the candidates the matcher did not rule out. Excluded ones (an unmet mandatory requirement) and
  // ones a recruiter rejected are not offered for shortlisting, so the pool size matches "N candidates matched".
  const pool = useMemo(() => matches.filter((m) => ["recommended", "needs_review"].includes(m.disposition)), [matches]);
  const excludedCount = matches.filter((m) => m.eligibility === "excluded").length;
  const eligibleCount = pool.filter((m) => m.eligibility === "eligible").length;
  const reviewCount = pool.filter((m) => m.eligibility === "needs_review").length;

  const [desk, setDesk] = useState<Dashboard | null>(null);
  const [deskDone, setDeskDone] = useState(false);

  const refreshDesk = () =>
    getDashboard()
      .then((d) => {
        setDesk(d);
        setViewerId(d.viewer_id);
      })
      .catch(() => setViewerId(null))
      .finally(() => setDeskDone(true));

  useEffect(() => {
    void refreshDesk();
  }, []);

  // The matches list does not say who is shortlisted. The dashboard does: it lists shortlisted candidates and
  // the shares still awaiting approval, with the request and candidate in each link. When those lists are
  // complete (the count fits in the 20 it returns) they answer exactly and quietly.
  // Only when they are truncated do we ask the read-only share preview, which answers 409 for anyone not shortlisted.
  useEffect(() => {
    if (!deskDone || matches.length === 0) return;

    const linked = (items: { href: string }[]) => {
      const out = new Set<string>();
      for (const item of items) {
        const query = new URLSearchParams(item.href.split("?")[1] ?? "");
        const candidate = query.get("candidate");
        if (query.get("request") === requestId && candidate) out.add(candidate);
      }
      return out;
    };

    // The server says, per candidate, what was decided for this request. That is the truth; the dashboard lists and the
    // per-candidate probe below are only for an API that does not send it.
    if (matches.every((m) => m.shortlisted !== undefined)) {
      const state: Record<string, ShortlistState> = {};
      const approved: Record<string, boolean> = {};
      for (const m of matches) {
        state[m.candidate_id] = m.shortlisted ? "yes" : "no";
        approved[m.candidate_id] = Boolean(m.shortlisted && (m.share_approved || m.shared));
      }
      setShortlist(state);
      setShareApproved(approved);
      return;
    }

    if (desk && desk.counts.shortlisted_candidates <= desk.shortlisted_candidates.length) {
      const shortlisted = linked(desk.shortlisted_candidates);
      const awaiting = linked(desk.shares_awaiting_approval);
      const state: Record<string, ShortlistState> = {};
      const approved: Record<string, boolean> = {};
      for (const m of matches) {
        const yes = shortlisted.has(m.candidate_id);
        state[m.candidate_id] = yes ? "yes" : "no";
        approved[m.candidate_id] = yes && !awaiting.has(m.candidate_id);
      }
      setShortlist(state);
      setShareApproved(approved);
      return;
    }

    const targets = matches.filter((m) => ["recommended", "needs_review"].includes(m.disposition)).slice(0, PROBE_LIMIT);
    if (targets.length === 0) return;
    let cancelled = false;
    const queue = [...targets];
    const state: Record<string, ShortlistState> = {};
    const approved: Record<string, boolean> = {};

    async function worker() {
      while (queue.length > 0) {
        const match = queue.shift()!;
        try {
          const preview = await getSharePreview(requestId, match.candidate_id);
          state[match.candidate_id] = "yes";
          approved[match.candidate_id] = preview.approved;
        } catch (reason) {
          state[match.candidate_id] = reason instanceof ApiError && reason.code === "not_shortlisted" ? "no" : "unknown";
        }
      }
    }

    Promise.all(Array.from({ length: PROBE_CONCURRENCY }, worker)).then(() => {
      if (cancelled) return;
      setShortlist((current) => ({ ...current, ...state }));
      setShareApproved((current) => ({ ...current, ...approved }));
    });
    return () => {
      cancelled = true;
    };
  }, [matches, requestId, desk, deskDone]);

  async function run(action: () => Promise<unknown>, success?: string) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      if (success) notify(success);
      return true;
    } catch (reason) {
      setActionError(reason);
      return false;
    } finally {
      setBusy(false);
    }
  }

  const onRetry = async () => {
    if (await run(() => retryProcessing(requestId), "Processing restarted")) detailQ.reload();
  };
  const onEdit = async (
    item: HiringRequirement,
    patch: { text?: string; strength?: "mandatory" | "preferred"; label?: "skill" | "experience" | "education" | "certification" | "other" },
  ) => {
    if (await run(() => editHiringRequirement(requestId, item.id, patch), "Edit saved. The pool is provisional until you approve the requirements again.")) {
      detailQ.reload();
    }
  };
  const onApprove = async () => {
    if (await run(() => approveHiringRequirements(requestId), "Requirements approved. Re-matching on the approved requirements.")) detailQ.reload();
  };
  const onRejectRequirement = async (item: HiringRequirement) => {
    if (await run(() => rejectHiringRequirement(requestId, item.id), `"${item.text}" rejected. It is kept on record and not matched on.`)) {
      detailQ.reload();
    }
  };
  const onAdd = async (item: Parameters<typeof addHiringRequirement>[1]) => {
    const ok = await run(() => addHiringRequirement(requestId, item), "Requirement added. Approve the requirements to re-run matching.");
    if (ok) detailQ.reload();
    return ok;
  };
  const onRerun = async () => {
    if (await run(() => runHiringMatch(requestId), "Matching re-run. Nothing was shortlisted or shared.")) {
      setShortlist({});
      matchesQ.reload();
      detailQ.reload();
    }
  };
  const onShortlistSelected = async (matchIds: string[]) => {
    let done = 0;
    for (const id of matchIds) {
      const match = matches.find((m) => m.id === id);
      if (!match) continue;
      const ok = await run(() => shortlistMatch(requestId, id));
      if (ok) {
        done += 1;
        setShortlist((cur) => ({ ...cur, [match.candidate_id]: "yes" }));
      }
    }
    // run() already surfaces failures in the error banner; only toast what actually happened.
    if (done === matchIds.length) {
      notify("Shortlist updated. Nothing was shared.");
    } else if (done > 0) {
      notify(`Shortlisted ${done} of ${matchIds.length}. Nothing was shared.`);
    }
    // The cards are drawn from the server's per-candidate flags, so fetch them again. Without this the dashboard
    // refresh below re-ran the card state from the flags loaded before the click and un-shortlisted the card.
    if (done > 0) matchesQ.reload();
    void refreshDesk();
  };
  const onReject = async (match: CandidateMatch) => {
    if (await run(() => rejectMatch(requestId, match.id), "Rejection recorded. You can restore them from the Rejected filter.")) matchesQ.reload();
  };
  const onRestore = async (match: CandidateMatch) => {
    if (await run(() => restoreMatch(requestId, match.id), "Restored to the pool. They are not shortlisted.")) matchesQ.reload();
  };

  const requirements = detail?.requirements ?? [];
  const probed = matches.filter((m) => ["recommended", "needs_review"].includes(m.disposition)).slice(0, PROBE_LIMIT);
  const anyUnknown = probed.some((m) => shortlist[m.candidate_id] === "unknown");
  const shortlistedCount = Object.entries(shortlist).filter(([, v]) => v === "yes").length;
  const approvedShares = Object.entries(shareApproved).filter(([id, v]) => v && shortlist[id] === "yes").length;
  const reviewed = matches.filter((m) => m.disposition === "rejected").length + shortlistedCount;

  const steps = deriveLifecycle({
    processing: detail?.processing.stage ?? "received",
    poolStatus: detail?.processing.pool_status,
    matchCount: detail?.processing.matched_count ?? 0,
    reviewed,
    shortlisted: anyUnknown ? null : shortlistedCount,
    sharesApproved: approvedShares,
    shared: detail?.candidates_shared ?? 0,
  });

  const stage = detail?.processing.stage;
  // A provisional pool stays on screen while the approval rematch runs; it is never hidden from HR.
  const poolStatus = detail?.processing.pool_status ?? "provisional";
  const showPool = stage === "complete" || (stage === "matching" && matches.length > 0);
  // Acknowledge each finished match once, not once per visit: the confirmed pool that arrives after HR approves,
  // while this page stays open, is a new pool that HR is now looking at.
  const poolAck = useRef<string | null>(null);
  const matchedAt = detailQ.data?.last_match_completed_at ?? null;
  useEffect(() => {
    const key = `${requestId}:${matchedAt}`;
    if (stage !== "complete" || poolAck.current === key) return;
    poolAck.current = key;
    void openPool(requestId)
      .then(() => {
        detailQ.reload();
        return refreshDesk();
      })
      .catch(() => undefined);
    // refreshDesk and detailQ are recreated each render; one acknowledgement per finished match is enough.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage, requestId, matchedAt]);

  useEffect(() => {
    if (!stage || !["received", "extracting", "matching"].includes(stage)) return;
    const id = setInterval(() => {
      detailQ.reload();
      matchesQ.reload();
    }, 2000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  // When a rematch finishes, read the pool it produced (the last poll may predate it).
  const lastStage = useRef(stage);
  useEffect(() => {
    if (lastStage.current === "matching" && stage === "complete") matchesQ.reload();
    lastStage.current = stage;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  if (detailQ.error) return <ErrorState error={detailQ.error} onRetry={detailQ.reload} />;
  if (!detail) {
    return (
      <div aria-busy="true" aria-label="Loading request">
        <PanelSkeleton rows={4} />
      </div>
    );
  }

  const phase = requestPhase(detail.processing.stage, detail);
  const owner =
    detail.owner_user_id && viewerId ? (detail.owner_user_id === viewerId ? "owner: you" : "owner: another recruiter") : null;
  const shareName = matches.find((m) => m.candidate_id === shareCandidate)?.candidate_name ?? null;

  const requirementsSection = (
    <section id="requirements" aria-labelledby="h-req">
      <RuleHeading id="h-req">Requirements</RuleHeading>
      <Requirements
        requirements={requirements}
        busy={busy}
        poolStale={detail.pool_stale}
        source={detail.requirements_source ?? null}
        awaitingApproval={stage === "awaiting_approval"}
        rematching={stage === "matching"}
        onApprove={onApprove}
        onReject={onRejectRequirement}
        onAdd={onAdd}
        onRerun={onRerun}
        onEdit={onEdit}
      />
    </section>
  );

  return (
    <>
      <p className="mb-2 text-xs">
        <Link href="/hiring" prefetch={false}>
          ← All requests
        </Link>
      </p>
      <PageHeader
        eyebrow="Hiring request"
        title={detail.job_title}
        sub={
          <>
            Received from <strong className="font-semibold text-ink">{detail.company}</strong> · {shortDate(detail.received_at)}
            {owner ? ` · ${owner}` : ""}
          </>
        }
        actions={phase ? <StatusText tone={PHASE[phase].tone}>{PHASE[phase].label}</StatusText> : null}
      />

      <Stepper steps={steps} />

      {actionError ? (
        <div className="mt-4">
          <ErrorState error={actionError} />
        </div>
      ) : null}

      <div className="mt-6 grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-8">
          <ProcessingCard
            processing={detail.processing}
            status={detail.status}
            phase={phase}
            shortlisted={matchesQ.data ? (anyUnknown ? null : shortlistedCount) : undefined}
            shared={detail.candidates_shared}
            onRetry={onRetry}
          />

          {/* While the pool is provisional, approving the requirements is the next step, so they come first. */}
          {poolStatus !== "confirmed" ? requirementsSection : null}

          {showPool ? (
            <section id="pool" aria-labelledby="h-pool">
              <RuleHeading id="h-pool">Candidate pool</RuleHeading>
              <p className="mb-3 text-sm" aria-busy={matchesQ.data ? undefined : true}>
                {matchesQ.data
                  ? poolStatus === "confirmed"
                    ? `Shortlisted: ${shortlistedCount} of ${pool.length}`
                    : `${pool.length} candidate${pool.length === 1 ? "" : "s"} in the provisional pool`
                  : "Loading matched candidates…"}
                {matchesQ.data ? (
                  <span className="ml-3 text-mut">
                    Eligible: {eligibleCount} · Needs review: {reviewCount} · Excluded: {excludedCount}
                    {excludedCount > 0 ? " (a mandatory requirement not met — use the Excluded filter to check them)" : ""}
                  </span>
                ) : null}
              </p>
              {matchesQ.error ? (
                <ErrorState error={matchesQ.error} onRetry={matchesQ.reload} />
              ) : !matchesQ.data ? (
                <PanelSkeleton rows={3} />
              ) : (
                <Pool
                  matches={matches}
                  shortlist={shortlist}
                  shareApproved={shareApproved}
                  busy={busy}
                  jobTitle={detail.job_title}
                  poolStatus={poolStatus}
                  rematching={stage === "matching"}
                  onShortlistSelected={onShortlistSelected}
                  onReject={onReject}
                  onShare={(m) => setShareCandidate(m.candidate_id)}
                  onRestore={onRestore}
                />
              )}
            </section>
          ) : null}

          {poolStatus === "confirmed" ? requirementsSection : null}
        </div>

        <aside aria-label="Request record">
          <RequestRecord detail={detail} viewerId={viewerId} onChanged={detailQ.reload} />
        </aside>
      </div>

      <SharePanel
        requestId={requestId}
        candidateId={shareCandidate}
        candidateName={shareName}
        onClose={() => setShareCandidate(null)}
        onChanged={() => {
          if (shareCandidate) setShareApproved((current) => ({ ...current, [shareCandidate]: true }));
          detailQ.reload();
          matchesQ.reload(); // the per-candidate flags (approved, shared) come from the server
          void refreshDesk();
        }}
      />
    </>
  );
}

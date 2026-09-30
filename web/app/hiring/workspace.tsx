"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  type CandidateMatch,
  type Dashboard,
  type HiringRequirement,
  approveHiringRequirements,
  editHiringRequirement,
  extractHiringRequirements,
  getDashboard,
  getHiringRequest,
  getSharePreview,
  listHiringMatches,
  openHiringRequest,
  rejectMatch,
  runHiringMatch,
  shortlistMatch,
} from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { deriveLifecycle } from "@/lib/lifecycle";
import { REQUEST_STATUS } from "@/lib/labels";
import { shortDate } from "@/lib/format";
import { useAsync } from "@/lib/use-async";
import { PageHeader, SectionLabel } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { Stepper } from "@/components/ui/stepper";
import { Tag } from "@/components/ui/tag";
import { useToast } from "@/components/ui/toast";
import { Matches, type ShortlistState } from "./matches";
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

  const onExtract = async () => {
    if (await run(() => extractHiringRequirements(requestId), "Requirements proposed. Approve them before matching.")) {
      detailQ.reload();
    }
  };
  const onEdit = async (
    item: HiringRequirement,
    patch: { text?: string; strength?: "mandatory" | "preferred"; label?: "skill" | "experience" | "education" | "certification" | "other" },
  ) => {
    if (await run(() => editHiringRequirement(requestId, item.id, patch), "Edit saved. Approve the requirement again before it is used.")) {
      detailQ.reload();
    }
  };
  const onApprove = async () => {
    if (await run(() => approveHiringRequirements(requestId), "Requirements approved")) detailQ.reload();
  };
  const onRun = async () => {
    const ok = await run(async () => {
      await openHiringRequest(requestId);
      await runHiringMatch(requestId);
    }, "Matching finished. Nothing was shortlisted or shared.");
    if (ok) {
      setShortlist({});
      matchesQ.reload();
      detailQ.reload();
    }
  };
  const onShortlist = async (match: CandidateMatch) => {
    if (await run(() => shortlistMatch(requestId, match.id), "Added to the shortlist. Nothing was shared.")) {
      setShortlist((current) => ({ ...current, [match.candidate_id]: "yes" }));
      void refreshDesk();
    }
  };
  const onReject = async (match: CandidateMatch) => {
    if (await run(() => rejectMatch(requestId, match.id), "Rejection recorded")) matchesQ.reload();
  };

  const requirements = detail?.requirements ?? [];
  const approvedCount = requirements.filter((r) => r.review_status === "approved").length;
  const probed = matches.filter((m) => ["recommended", "needs_review"].includes(m.disposition)).slice(0, PROBE_LIMIT);
  const anyUnknown = probed.some((m) => shortlist[m.candidate_id] === "unknown");
  const shortlistedCount = Object.entries(shortlist).filter(([, v]) => v === "yes").length;
  const approvedShares = Object.entries(shareApproved).filter(([id, v]) => v && shortlist[id] === "yes").length;

  const steps = deriveLifecycle({
    requirements,
    matchCount: matches.length,
    shortlisted: anyUnknown ? null : shortlistedCount,
    sharesApproved: approvedShares,
    shared: detail?.candidates_shared ?? 0,
  });

  if (detailQ.error) return <ErrorState error={detailQ.error} onRetry={detailQ.reload} />;
  if (!detail) {
    return (
      <div aria-busy="true" aria-label="Loading request">
        <PanelSkeleton rows={4} />
      </div>
    );
  }

  const owner =
    detail.owner_user_id && viewerId ? (detail.owner_user_id === viewerId ? "owner: you" : "owner: another recruiter") : null;
  const shareName = matches.find((m) => m.candidate_id === shareCandidate)?.candidate_name ?? null;

  return (
    <>
      <p className="mb-2 text-xs">
        <Link href="/hiring" prefetch={false}>
          ← All requests
        </Link>
      </p>
      <PageHeader
        hue="req"
        title={detail.job_title}
        sub={
          <>
            <span className="font-semibold text-ink">{detail.company}</span> · received {shortDate(detail.received_at)}
            {owner ? ` · ${owner}` : ""}
          </>
        }
        actions={<Tag tone={detail.status === "open" ? "decided" : "neutral"}>{REQUEST_STATUS[detail.status] ?? detail.status}</Tag>}
      />

      <Stepper steps={steps} />
      <p className="mt-1.5 text-xs text-mut">
        Progress is worked out from requirement approvals, matches, the shortlist and share records. The request&apos;s stored status only
        says draft or open.
      </p>

      {actionError ? (
        <div className="mt-4">
          <ErrorState error={actionError} />
        </div>
      ) : null}

      <div className="mt-6 grid grid-cols-[minmax(0,1fr)] gap-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-8">
          <section aria-labelledby="h-req">
            <SectionLabel id="h-req">2 · Requirements</SectionLabel>
            <Requirements requirements={requirements} busy={busy} onExtract={onExtract} onApprove={onApprove} onEdit={onEdit} />
          </section>

          <section aria-labelledby="h-match">
            <SectionLabel id="h-match">3 · Candidates against approved requirements</SectionLabel>
            {matchesQ.error ? (
              <ErrorState error={matchesQ.error} onRetry={matchesQ.reload} />
            ) : (
              <Matches
                matches={matches}
                shortlist={shortlist}
                busy={busy}
                approvedCount={approvedCount}
                jobTitle={detail.job_title}
                onRun={onRun}
                onShortlist={onShortlist}
                onReject={onReject}
                onShare={(m) => setShareCandidate(m.candidate_id)}
              />
            )}
          </section>
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
          void refreshDesk();
        }}
      />
    </>
  );
}

"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  type ActivityEvent,
  type Comparison,
  type Review,
  decideReview,
  getActivity,
  getReview,
  getReviewComparison,
  getReviewRecord,
} from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { REASON_MESSAGE, WARNING_MESSAGE, decisionCopy, isDecided, recommendation } from "@/lib/compare";
import { relativeAge } from "@/lib/format";
import { labelAudit } from "@/lib/labels";
import { Changes, type EvidenceTarget } from "@/components/compare/field-comparison";
import { DatesPanel } from "@/components/compare/dates-panel";
import { DecisionPanel } from "@/components/compare/decision-panel";
import { DocumentCards } from "@/components/compare/document-cards";
import { DocumentCompare } from "@/components/compare/document-viewer";
import { Recommendation } from "@/components/compare/recommendation";
import { WhyRelated } from "@/components/compare/why-related";
import { AuditLine } from "@/components/domain/audit-line";
import { PageHeader } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { ErrorState, Notice } from "@/components/ui/states";
import { Tag } from "@/components/ui/tag";
import { useToast } from "@/components/ui/toast";

type Loaded = { review: Review; comparison: Comparison; activity: ActivityEvent[] };

export function CompareView() {
  const params = useSearchParams();
  const reviewParam = params.get("review");
  const documentParam = params.get("document");
  const { notify } = useToast();

  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [candidateId, setCandidateId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [focus, setFocus] = useState<EvidenceTarget | null>(null);
  const lock = useRef(false);

  const load = useCallback(
    async (chosen: string | null): Promise<Loaded> => {
      let review: Review;
      if (reviewParam) review = await getReviewRecord(reviewParam);
      else if (documentParam) review = await getReview(documentParam);
      else throw new ApiError(404, "not_found");
      const comparison = await getReviewComparison(review.id, chosen ?? undefined);
      const documentId = comparison.incoming?.document?.id ?? review.document_id ?? null;
      const activity = documentId ? (await getActivity(documentId)).events : [];
      return { review, comparison, activity };
    },
    [reviewParam, documentParam],
  );

  const refresh = useCallback(
    async (chosen: string | null) => {
      try {
        const next = await load(chosen);
        setLoaded(next);
        setError(null);
        setCandidateId((current) => chosen ?? current ?? next.comparison.candidate?.id ?? null);
      } catch (reason) {
        setError(reason);
      }
    },
    [load],
  );

  useEffect(() => {
    setLoaded(null);
    setError(null);
    void refresh(null);
  }, [refresh]);

  async function decide(action: string) {
    // A second click while the first is in flight must not send a second decision.
    if (lock.current || !loaded) return;
    lock.current = true;
    setBusy(true);
    setActionError(null);
    setNotice(null);
    let conflict = false;
    const needsTarget = action !== "create_separate_candidate" && loaded.comparison.candidates.length > 1;
    try {
      await decideReview(loaded.review.id, action, needsTarget ? (candidateId ?? undefined) : undefined);
      setStale(false);
      setNotice(`Decision recorded: ${decisionCopy(action).label}.`);
      notify("Decision recorded");
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) conflict = true;
      else setActionError(reason);
    } finally {
      await refresh(candidateId);
      // Say "already decided" together with the refreshed record, so the message never sits next to controls
      // that are about to disappear.
      if (conflict) setStale(true);
      lock.current = false;
      setBusy(false);
    }
  }

  if (error && !loaded) return <ErrorState error={error} onRetry={() => void refresh(candidateId)} />;
  if (!loaded) {
    return (
      <div aria-busy="true" aria-label="Loading comparison">
        <PanelSkeleton rows={3} />
      </div>
    );
  }

  const { review, comparison, activity } = loaded;
  const decided = isDecided(review.status);
  const documentId = comparison.incoming?.document?.id ?? null;
  const merged = comparison.warnings.includes("candidate_merged");
  const rec = recommendation(review);
  const record = activity.filter((e) => e.action === "duplicate_review_opened" || e.action === "duplicate_review_decided");
  const spreadsheet = comparison.reason === "excel_row";
  // Only judge the stored phone signal when the two CVs were actually read.
  const phoneField = comparison.available ? comparison.fields.find((f) => f.key === "phone") : undefined;
  // A phone section that could not be compared says nothing either way, so the stored signal stands.
  const signalContext = phoneField?.comparable ? { sharedPhone: phoneField.items.some((item) => item.status === "same") } : undefined;

  return (
    <>
      <p className="mb-2 flex flex-wrap gap-x-4 text-xs">
        <Link href="/queue" prefetch={false}>
          ← Review queue
        </Link>
        {documentId ? (
          <Link href={`/intake?document=${documentId}`} prefetch={false}>
            Open this file in Intake
          </Link>
        ) : null}
      </p>

      <PageHeader
        eyebrow="CV comparison"
        title="Previous CV vs new CV"
        sub="Cadence recommends. You decide. Compare the two CVs, check the evidence, then choose."
        actions={decided ? <Tag tone="decided">Decided</Tag> : <Tag tone="neutral">Awaiting your decision</Tag>}
      />

      <div className="space-y-2" aria-live="polite">
        {stale ? (
          <Notice tone="warn">This review has already been decided. It has been refreshed, and nothing was changed by your click.</Notice>
        ) : null}
        {notice ? (
          <Notice>
            {notice}
            {comparison.candidate?.id ? (
              <>
                {" "}
                <Link href={`/candidates/${comparison.candidate.id}`} prefetch={false} className="font-semibold">
                  Open {comparison.candidate.name ?? "the candidate"}&apos;s profile
                </Link>
              </>
            ) : null}
          </Notice>
        ) : null}
        {actionError ? <ErrorState error={actionError} /> : null}
        {error ? <ErrorState error={error} onRetry={() => void refresh(candidateId)} /> : null}
        {comparison.warnings.map((code) =>
          // Right after a decision the "already decided" warning only repeats the confirmation above it.
          WARNING_MESSAGE[code] && !((stale || notice) && code === "review_decided") ? (
            <Notice key={code} tone="warn">
              {WARNING_MESSAGE[code]}
            </Notice>
          ) : null,
        )}
      </div>

      {spreadsheet || !comparison.available ? (
        <div className="mt-4">
          <p role="status" className="hatch border border-rule-strong px-3 py-2.5">
            <span className="font-bold">Comparison unavailable. </span>
            {REASON_MESSAGE[comparison.reason ?? ""] ?? "The two CVs cannot be compared for this review."}
          </p>
          {spreadsheet ? (
            <p className="mt-2">
              Decide this one where the spreadsheet import is listed: <Link href="/data" prefetch={false}>Excel import</Link>.
            </p>
          ) : null}
        </div>
      ) : null}

      {!spreadsheet ? (
        <>
          {/*
            Reading order on a phone: the two CVs, then Cadence's recommendation and the decision, then the evidence.
            On a wide screen the recommendation and decision sit in the right column from the top, so they stay in view.
          */}
          <div className="mt-2 grid grid-cols-[minmax(0,1fr)] gap-x-8 gap-y-8 lg:grid-cols-[minmax(0,1fr)_23rem]">
            <div className="min-w-0 space-y-4 lg:col-start-1 lg:row-start-1">
              <DocumentCards comparison={comparison} />

              {comparison.candidates.length > 1 ? (
                <div>
                  <label htmlFor="which-candidate" className="mb-1 block text-[13px] font-semibold">
                    Compare with which existing candidate?
                  </label>
                  <select
                    id="which-candidate"
                    className="block min-h-11 w-full max-w-md border border-rule-strong bg-panel px-2.5 sm:min-h-9"
                    value={candidateId ?? ""}
                    disabled={decided}
                    onChange={(event) => {
                      setCandidateId(event.target.value);
                      setLoaded(null);
                      void refresh(event.target.value);
                    }}
                  >
                    {comparison.candidates.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name ?? "Unnamed candidate"}
                      </option>
                    ))}
                  </select>
                </div>
              ) : null}
            </div>

            <aside aria-label="Recommendation and decision" className="space-y-4 lg:sticky lg:top-24 lg:col-start-2 lg:row-span-2 lg:row-start-1 lg:self-start">
              <Recommendation review={review} comparison={comparison} candidateId={candidateId} context={signalContext} />
              <DecisionPanel
                review={review}
                recommendedAction={rec.action}
                busy={busy}
                candidateMerged={merged}
                candidateName={comparison.candidate?.name ?? null}
                onDecide={decide}
                record={
                  record.length > 0 ? (
                    <div>
                      <h3 className="mb-1 font-mono text-[10.5px] font-medium uppercase tracking-[0.12em] text-mut">Record</h3>
                      <ul className="space-y-1">
                        {record.map((event) => (
                          <AuditLine key={`${event.created_at}-${event.action}`} action={event.action} actorKind={event.actor_kind} at={event.created_at} />
                        ))}
                      </ul>
                      <p className="mt-1 text-xs text-mut">
                        {record[0]
                          ? `${labelAudit(record[0].action)} ${relativeAge(record[0].created_at)}. The audit trail is append-only.`
                          : ""}
                      </p>
                    </div>
                  ) : null
                }
              />
            </aside>

            <div className="min-w-0 space-y-8 lg:col-start-1 lg:row-start-2">
              <WhyRelated signals={review.evidence} candidateId={candidateId} confidence={review.confidence} context={signalContext} />
              {comparison.available ? (
                <>
                  <Changes comparison={comparison} onOpenEvidence={setFocus} />
                  {comparison.dates ? <DatesPanel dates={comparison.dates} /> : null}
                  <DocumentCompare comparison={comparison} focus={focus} />
                </>
              ) : null}
            </div>
          </div>
        </>
      ) : null}
    </>
  );
}

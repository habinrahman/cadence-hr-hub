"use client";

import { useEffect, useState } from "react";
import { getCandidate, getDocumentText } from "@/lib/api";
import { useAsync } from "@/lib/use-async";
import { CandidateHeader } from "@/components/domain/candidate-header";
import { ConfirmDialog, SlideOver } from "@/components/ui/dialog";
import { PanelSkeleton, Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { Facts } from "./facts";
import { History, Rail } from "./record";

export function CandidateView({ id }: { id: string }) {
  const { data: profile, error, loading, reload } = useAsync(() => getCandidate(id), [id]);
  const [confirming, setConfirming] = useState(false);
  const [textOpen, setTextOpen] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [textError, setTextError] = useState<unknown>(null);
  const [textLoading, setTextLoading] = useState(false);
  const [reviewDocument, setReviewDocument] = useState<string | null>(null);

  const current = profile?.documents.find((d) => d.is_current);

  // "Compare CVs" appears only when one of this candidate's files has a relationship review to open.
  // The profile says which file has one, so nothing is probed.
  useEffect(() => {
    setReviewDocument(profile?.documents.find((doc) => doc.review_id)?.id ?? null);
  }, [profile]);

  async function openText() {
    if (!current) return;
    setConfirming(false);
    setTextOpen(true);
    setTextLoading(true);
    setTextError(null);
    try {
      setText((await getDocumentText(current.id)).text);
    } catch (reason) {
      setTextError(reason);
    } finally {
      setTextLoading(false);
    }
  }

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !profile) {
    return (
      <div aria-busy="true" aria-label="Loading candidate">
        <Skeleton lines={2} className="mb-6 max-w-md" />
        <PanelSkeleton rows={4} />
      </div>
    );
  }

  return (
    <>
      <CandidateHeader profile={profile} compareHref={reviewDocument ? `/compare?document=${reviewDocument}` : null} />

      <div className="mt-8 grid grid-cols-[minmax(0,1fr)] gap-x-10 gap-y-10 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-10">
          <Facts profile={profile} />
          <History profile={profile} />
        </div>
        <aside aria-label="Skills, documents and provenance" className="min-w-0 lg:border-l lg:border-rule lg:pl-8">
          <Rail profile={profile} onShowText={current ? () => setConfirming(true) : undefined} />
        </aside>
      </div>

      <p className="mt-10 text-[12.5px] text-mut">This record is built from CVs and cannot be edited here.</p>

      <ConfirmDialog
        open={confirming}
        title="Open the CV text?"
        body={
          <p>
            You are about to read the full text of <span className="break-all font-mono">{current?.original_filename}</span>. This view is
            recorded in the audit trail.
          </p>
        }
        confirmLabel="Open CV text"
        onConfirm={openText}
        onCancel={() => setConfirming(false)}
      />
      <SlideOver open={textOpen} title="CV text" onClose={() => setTextOpen(false)}>
        {textLoading ? <Skeleton lines={8} /> : null}
        {textError ? <ErrorState error={textError} onRetry={openText} /> : null}
        {text !== null && !textLoading && !textError ? (
          text.trim() ? (
            <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed">{text}</pre>
          ) : (
            <p className="text-mut">No text was extracted from this file.</p>
          )
        ) : null}
      </SlideOver>
    </>
  );
}

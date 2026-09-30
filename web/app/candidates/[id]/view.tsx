"use client";

import { useState } from "react";
import { getCandidate, getDocumentText } from "@/lib/api";
import { useAsync } from "@/lib/use-async";
import { CandidateHeader } from "@/components/domain/candidate-header";
import { ConfirmDialog, SlideOver } from "@/components/ui/dialog";
import { PanelSkeleton, Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";
import { Facts } from "./facts";
import { Record } from "./record";

const SECTIONS = [
  { href: "#profile", label: "Profile" },
  { href: "#evidence", label: "Evidence" },
  { href: "#cvs", label: "CVs" },
  { href: "#record", label: "Record" },
];

export function CandidateView({ id }: { id: string }) {
  const { data: profile, error, loading, reload } = useAsync(() => getCandidate(id), [id]);
  const [confirming, setConfirming] = useState(false);
  const [textOpen, setTextOpen] = useState(false);
  const [text, setText] = useState<string | null>(null);
  const [textError, setTextError] = useState<unknown>(null);
  const [textLoading, setTextLoading] = useState(false);

  const current = profile?.documents.find((d) => d.is_current);

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
      <CandidateHeader profile={profile} onShowText={current ? () => setConfirming(true) : undefined} />

      <nav
        aria-label="Sections"
        className="sticky top-0 z-20 -mx-4 mt-4 flex gap-2 overflow-x-auto border-b border-rule bg-canvas px-4 py-2 lg:hidden"
      >
        {SECTIONS.map((s) => (
          <a
            key={s.href}
            href={s.href}
            className="inline-flex min-h-11 items-center rounded-[3px] border border-rule-strong bg-panel px-3 text-[13px] font-semibold no-underline"
          >
            {s.label}
          </a>
        ))}
      </nav>

      <div className="mt-6 grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Facts profile={profile} />
        <Record profile={profile} />
      </div>

      <p className="mt-8 text-xs text-mut">This profile is built from CVs and cannot be edited here.</p>

      <ConfirmDialog
        open={confirming}
        title="Open the CV text?"
        body={
          <p>
            You are about to read the full text of <span className="break-all font-mono">{current?.original_filename}</span>. This
            view is recorded in the audit trail.
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

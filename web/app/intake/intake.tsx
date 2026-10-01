"use client";

import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import {
  type ActivityEvent,
  type DocumentSummary,
  type Review,
  decideReview,
  getActivity,
  getDocument,
  getReview,
  listDocuments,
  uploadDocument,
} from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { PageHeader, Panel, SectionLabel } from "@/components/ui/panel";
import { EmptyState, ErrorState, Notice } from "@/components/ui/states";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { DocumentDetail } from "./document-detail";
import { FileList } from "./file-list";

const PROCESSING = new Set(["received", "extracting"]);
const REVIEW_OUTCOMES = new Set(["updated_cv", "duplicate", "different_candidate", "ambiguous"]);

export function Intake() {
  const params = useSearchParams();
  const { notify } = useToast();
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(params.get("document"));
  const [document, setDocument] = useState<DocumentSummary | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [activity, setActivity] = useState<ActivityEvent[]>([]);
  const [targetId, setTargetId] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const refreshList = useCallback(async () => {
    setDocuments((await listDocuments()).documents);
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    const next = await getDocument(id);
    setDocument(next);
    setActivity((await getActivity(id)).events);
    if (next.status === "needs_review" || REVIEW_OUTCOMES.has(next.identity_outcome ?? "")) {
      try {
        const opened = await getReview(id);
        setReview(opened);
        setTargetId(opened.candidate_id ?? opened.candidates[0]?.id ?? "");
      } catch {
        setReview(null);
      }
    } else {
      setReview(null);
    }
    return next;
  }, []);

  useEffect(() => {
    refreshList().catch(setError);
  }, [refreshList]);

  useEffect(() => {
    if (!selectedId) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const tick = async () => {
      try {
        const next = await loadDetail(selectedId);
        if (cancelled) return;
        if (PROCESSING.has(next.status)) timer = setTimeout(tick, 1500);
        else await refreshList();
      } catch (reason) {
        if (!cancelled) setError(reason);
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [selectedId, loadDetail, refreshList]);

  async function onUpload(file: File) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await uploadDocument(file);
      setSelectedId(result.id);
      if (!result.created) setNotice("This file is already in the hub. Identical bytes are the same document.");
      await refreshList();
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }

  async function onDecide(action: string) {
    if (!review) return;
    const needsTarget = action !== "create_separate_candidate" && review.candidates.length > 1;
    if (needsTarget && !targetId) {
      setError(new ApiError(422, "Choose which existing candidate this file belongs to."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await decideReview(review.id, action, needsTarget ? targetId : undefined);
      if (selectedId) {
        await loadDetail(selectedId);
        await refreshList();
      }
      setNotice("Decision recorded.");
      notify("Decision recorded");
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }

  function select(id: string) {
    setNotice(null);
    setError(null);
    setSelectedId(id);
  }

  return (
    <>
      <PageHeader
title="CV intake"
        sub="Upload a CV. Cadence reads it and, if it overlaps an existing profile, proposes a relationship. A recruiter confirms before any record changes."
      />

      <Panel as="section" className="mb-5 p-3">
        <label className="flex min-h-24 cursor-pointer flex-col items-center justify-center gap-1 rounded border border-dashed border-rule-strong px-4 py-6 text-center focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-human hover:bg-inset">
          <span className="font-bold">{busy ? "Working…" : "Choose a CV to upload"}</span>
          <span className="text-xs text-mut">PDF, Word, or an image of a scan</span>
          <input
            className="sr-only"
            type="file"
            accept=".pdf,.doc,.docx,.png,.jpg,.jpeg"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void onUpload(file);
              event.target.value = "";
            }}
          />
        </label>
        {notice ? (
          <div className="mt-3">
            <Notice>{notice}</Notice>
          </div>
        ) : null}
      </Panel>

      {error ? (
        <div className="mb-5">
          <ErrorState error={error} />
        </div>
      ) : null}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside aria-label="Files">
          <SectionLabel>Files</SectionLabel>
          {documents === null ? (
            <div aria-busy="true">
              <PanelSkeleton rows={4} />
            </div>
          ) : (
            <Panel>
              <FileList documents={documents} selectedId={selectedId} onSelect={select} />
            </Panel>
          )}
        </aside>

        <section aria-label="Selected file" aria-busy={selectedId !== null && !document}>
          {!selectedId ? (
            <EmptyState
              title="Select or upload a file"
              body="Open a file to see what was extracted and any proposed relationship to an existing profile."
            />
          ) : !document ? (
            <PanelSkeleton rows={3} />
          ) : (
            <DocumentDetail
              document={document}
              review={review}
              targetId={targetId}
              onTarget={setTargetId}
              busy={busy}
              onDecide={onDecide}
              activity={activity}
            />
          )}
        </section>
      </div>
    </>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { fetchPagePreview, type CompareDocument } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { clampPage, previewPath } from "@/lib/page-preview";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/states";

type Loaded = { url: string; pages: number; highlights: number };

/**
 * The real page of one CV, drawn by the server, with lines found only in this CV marked in amber and the selected
 * evidence outlined in blue. Only for a CV that belongs to the review being compared. Opening a page is audited.
 */
export function PageView({
  reviewId,
  candidateId,
  document,
  title,
  page,
  onPage,
  quote,
  autoOpen,
  textLayer,
}: {
  reviewId: string;
  candidateId: string | null;
  document: CompareDocument;
  title: string;
  page: number;
  onPage: (page: number) => void;
  quote: string | null;
  autoOpen: boolean;
  textLayer: boolean;
}) {
  const [opened, setOpened] = useState(false);
  const [image, setImage] = useState<Loaded | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [attempt, setAttempt] = useState(0);
  const current = useRef<string | null>(null);

  // Evidence links open the page they cite.
  useEffect(() => {
    if (autoOpen) setOpened(true);
  }, [autoOpen, quote]);

  useEffect(() => {
    if (!opened) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPagePreview(previewPath({ reviewId, documentId: document.id, page, candidateId, focus: quote }))
      .then(({ blob, pages, highlights }) => {
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        if (current.current) URL.revokeObjectURL(current.current);
        current.current = url;
        setImage({ url, pages, highlights });
      })
      .catch((reason) => {
        if (!cancelled) setError(reason);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [opened, reviewId, document.id, page, candidateId, quote, attempt]);

  useEffect(
    () => () => {
      if (current.current) URL.revokeObjectURL(current.current);
    },
    [],
  );

  const total = image?.pages ?? Math.max(document.page_count, 1);
  const status = error instanceof ApiError ? error.status : null;

  if (!opened) {
    return (
      <div className="px-3.5 py-3">
        <p className="text-[13px] text-mut">The page image loads only when you open it. Opening a page is recorded in the audit trail.</p>
        {!textLayer ? <p className="mt-1 text-[13px] text-mut">This PDF has no readable text layer, so nothing can be marked on it. The page is shown as stored.</p> : null}
        <Button className="mt-2" onClick={() => setOpened(true)}>
          Open page view
        </Button>
      </div>
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 border-b border-rule px-3.5 py-1.5">
        <Button aria-label={`${title}: previous page`} disabled={page <= 1} onClick={() => onPage(clampPage(page - 1, total))}>
          Previous
        </Button>
        <span className="text-[13px] font-semibold" aria-live="polite">
          Page {page} of {total}
        </span>
        <Button aria-label={`${title}: next page`} disabled={page >= total} onClick={() => onPage(clampPage(page + 1, total))}>
          Next
        </Button>
        {image && !error ? (
          <span className="text-xs text-mut">
            {image.highlights > 0 ? `${image.highlights} ${image.highlights === 1 ? "mark" : "marks"} on this page.` : "Nothing is marked on this page."}
          </span>
        ) : null}
      </div>
      <div className="max-h-[42rem] overflow-auto bg-inset p-2" aria-busy={loading}>
        {loading && !image ? <Skeleton lines={8} /> : null}
        {error ? (
          <div role="alert" className="border border-bad-ink/40 bg-panel px-3 py-2.5 text-[13px]">
            <p className="font-semibold text-bad-ink">
              {status === 422 ? "This page could not be drawn." : status === 404 ? "This page is not available." : status === 415 ? "No visual preview for this file." : "The page could not be loaded."}
            </p>
            <p className="mt-0.5 text-mut">The text view still shows this CV.</p>
            {status === 401 || status === 403 ? <ErrorState error={error} /> : null}
            <Button className="mt-2" onClick={() => setAttempt((n) => n + 1)}>
              Try again
            </Button>
          </div>
        ) : null}
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={image.url}
            alt={`${title}, page ${page} of ${total}`}
            className={`mx-auto h-auto max-w-full border border-rule bg-white ${loading ? "opacity-60" : ""}`}
          />
        ) : null}
      </div>
      <p className="border-t border-rule px-3.5 py-2 text-xs text-mut">
        Amber marks lines found only in this CV. Some lines may not be located on the page. A blue outline is the evidence you selected.
      </p>
    </div>
  );
}

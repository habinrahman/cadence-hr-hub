export const FOCUS_LIMIT = 300;
export const DEFAULT_WIDTH = 900;

const WORD_TYPES = new Set(["application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"]);

export type PreviewKind = "pdf" | "word" | "other";

/** Only PDFs are drawn. Anything else keeps to the text comparison. */
export function previewKind(mediaType: string | null | undefined): PreviewKind {
  if (mediaType === "application/pdf") return "pdf";
  if (mediaType && WORD_TYPES.has(mediaType)) return "word";
  return "other";
}

export function unavailableNotice(kind: PreviewKind): string {
  const what = kind === "word" ? "Word document" : "this file type";
  return `Visual preview unavailable for ${what}. Text comparison is available below.`;
}

/** Path of the page-image route for one CV in one review. The evidence quote is trimmed to the limit the server enforces. */
export function previewPath(args: {
  reviewId: string;
  documentId: string;
  page: number;
  candidateId?: string | null;
  focus?: string | null;
  width?: number;
}): string {
  const query = new URLSearchParams();
  if (args.candidateId) query.set("candidate_id", args.candidateId);
  const focus = (args.focus ?? "").replace(/\s+/g, " ").trim().slice(0, FOCUS_LIMIT);
  if (focus) query.set("focus", focus);
  query.set("width", String(args.width ?? DEFAULT_WIDTH));
  return `/reviews/${args.reviewId}/documents/${args.documentId}/pages/${args.page}/preview?${query.toString()}`;
}

/** Keeps a requested page inside 1..total. */
export function clampPage(page: number, total: number): number {
  if (!Number.isFinite(page) || total < 1) return 1;
  return Math.min(Math.max(1, Math.round(page)), total);
}

import type { HiringRequestDetail, ProcessingStage } from "@/lib/api";
import type { Tone } from "@/lib/labels";

/**
 * Where a request stands, in HR's words. There is no "completed": the backend has no action that closes a request.
 * Worked out from the processing stage and, once matching has run, from the pool the request detail reports.
 */
export type RequestPhase =
  | "processing"
  | "needs_requirement"
  | "needs_approval"
  | "matching"
  | "needs_rerun"
  | "ready"
  | "active"
  | "failed";

export const PHASE: Record<RequestPhase, { label: string; tone: Tone; note: string }> = {
  processing: { label: "Processing", tone: "neutral", note: "Reading the job description and matching candidates." },
  needs_requirement: { label: "Needs a requirement", tone: "proposed", note: "No requirement was proposed. Add one to start matching." },
  needs_approval: { label: "Needs requirement approval", tone: "proposed", note: "Approve the requirements to confirm the pool." },
  matching: { label: "Matching", tone: "neutral", note: "Matching candidates on the approved requirements." },
  needs_rerun: { label: "Needs re-run", tone: "proposed", note: "Requirements changed after matching. Re-run matching." },
  ready: { label: "Ready for review", tone: "ok", note: "Confirmed pool, not opened yet." },
  active: { label: "Active", tone: "ok", note: "Confirmed pool opened by HR." },
  failed: { label: "Processing failed", tone: "bad", note: "Open the request to retry." },
};

export type PhaseDetail = Pick<HiringRequestDetail, "requirements" | "processing" | "pool_opened_at" | "last_match_completed_at">;

/** Null when the stage alone cannot say, and the request detail has not been read yet. */
export function requestPhase(stage: ProcessingStage | string, detail?: PhaseDetail | null): RequestPhase | null {
  if (stage === "received" || stage === "extracting") return "processing";
  if (stage === "awaiting_approval") return "needs_requirement";
  if (stage === "matching") return "matching";
  if (stage === "failed") return "failed";
  if (stage !== "complete" || !detail) return null;
  if (detail.processing.pool_status !== "confirmed") {
    return detail.requirements.some((r) => r.review_status === "proposed") ? "needs_approval" : "needs_rerun";
  }
  const opened = detail.pool_opened_at;
  const matched = detail.last_match_completed_at;
  return !opened || (matched !== null && Date.parse(matched) > Date.parse(opened)) ? "ready" : "active";
}

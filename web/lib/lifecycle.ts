import type { PoolStatus, ProcessingStage } from "@/lib/api";

export type StepState = "done" | "current" | "locked";
export type Step = {
  key: "received" | "extracted" | "matched" | "review" | "shortlist" | "approved" | "shared";
  label: string;
  state: StepState;
  detail: string;
};
export type LifecycleInput = {
  /** Automatic processing. This is the source of truth for the first three steps. */
  processing: ProcessingStage;
  /** provisional until HR approves the requirements and the rematch confirms the pool. */
  poolStatus?: PoolStatus;
  matchCount: number;
  /** Matches HR shortlisted or rejected. */
  reviewed: number;
  /** null when the shortlist could not be read. */
  shortlisted: number | null;
  sharesApproved: number;
  shared: number;
};

/**
 * Requirements are extracted automatically and stay proposed, and candidates are matched on them at once. That pool is
 * provisional. HR approves the requirements, matching re-runs on the approved ones, and the pool is confirmed; only then
 * can it be shortlisted. An edit sends a requirement back to proposed and the pool back to provisional.
 */
export function deriveLifecycle(input: LifecycleInput): Step[] {
  const extracted = ["awaiting_approval", "matching", "complete"].includes(input.processing);
  const awaiting = input.processing === "awaiting_approval";
  const matched = input.processing === "complete";
  const confirmed = input.poolStatus === "confirmed";
  const shortlisted = input.shortlisted ?? 0;
  const reviewDone = input.reviewed > 0 || shortlisted > 0 || input.shared > 0;
  const shortlistDone = shortlisted > 0 || input.shared > 0;
  const approvedDone = input.sharesApproved > 0 || input.shared > 0;
  const sharedDone = input.shared > 0;
  const failed = input.processing === "failed";

  const raw: { key: Step["key"]; label: string; done: boolean; detail: string }[] = [
    { key: "received", label: "Received", done: true, detail: "Logged by Cadence HR" },
    {
      key: "extracted",
      label: "Requirements extracted",
      done: extracted,
      detail: failed ? "Processing failed" : awaiting ? "None proposed, add one" : extracted ? (confirmed ? "Approved by HR" : "Proposed, not approved") : "In progress",
    },
    {
      key: "matched",
      label: "Matching complete",
      done: matched,
      detail: matched
        ? `${input.matchCount} matched · ${confirmed ? "confirmed" : "provisional"}`
        : failed
          ? "Processing failed"
          : awaiting
            ? "Needs a requirement"
            : "In progress",
    },
    {
      key: "review",
      label: "HR review",
      done: reviewDone,
      detail: reviewDone
        ? `${input.reviewed} decided`
        : matched && !confirmed
          ? "Approve requirements first"
          : matched
            ? "Nothing decided yet"
            : "After matching",
    },
    {
      key: "shortlist",
      label: "Shortlisted",
      done: shortlistDone,
      detail:
        input.shortlisted === null && matched
          ? "State unknown"
          : shortlistDone
            ? `${shortlisted} shortlisted`
            : matched && !confirmed
              ? "Needs a confirmed pool"
              : "None yet",
    },
    {
      key: "approved",
      label: "Share approved",
      done: approvedDone,
      detail: approvedDone ? (sharedDone ? "Approved" : `${input.sharesApproved} approved, not sent`) : "Needs a shortlist",
    },
    { key: "shared", label: "Shared", done: sharedDone, detail: sharedDone ? `${input.shared} shared` : "Not sent" },
  ];

  let currentAssigned = false;
  return raw.map((step) => {
    if (step.done) return { key: step.key, label: step.label, state: "done", detail: step.detail };
    if (!currentAssigned) {
      currentAssigned = true;
      return { key: step.key, label: step.label, state: "current", detail: step.detail };
    }
    return { key: step.key, label: step.label, state: "locked", detail: step.detail };
  });
}

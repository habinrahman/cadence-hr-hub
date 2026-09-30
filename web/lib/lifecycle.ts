export type StepState = "done" | "current" | "locked";
export type Step = {
  key: "request" | "requirements" | "matches" | "share";
  label: string;
  state: StepState;
  detail: string;
};
export type LifecycleInput = {
  requirements: { review_status: string }[];
  matchCount: number;
  shortlisted: number | null;
  sharesApproved: number;
  shared: number;
};

/**
 * The request's stored status only reaches draft and open, so the lifecycle is derived
 * from requirement review status, matches, shortlist and share records.
 */
export function deriveLifecycle(input: LifecycleInput): Step[] {
  const approved = input.requirements.filter((r) => r.review_status === "approved").length;
  const pending = input.requirements.length - approved;
  const requirementsDone = approved > 0 && pending === 0;
  const shortlisted = input.shortlisted ?? 0;
  const reviewDone = shortlisted > 0 || input.shared > 0;
  const shareDone = input.shared > 0;

  const raw: { key: Step["key"]; label: string; done: boolean; detail: string }[] = [
    { key: "request", label: "Request", done: true, detail: "Saved" },
    {
      key: "requirements",
      label: "Requirements",
      done: requirementsDone,
      detail: input.requirements.length === 0 ? "None proposed yet" : `${approved} approved · ${pending} proposed`,
    },
    {
      key: "matches",
      label: "Review matches",
      done: reviewDone,
      detail:
        input.shortlisted === null && input.matchCount > 0
          ? `${input.matchCount} found · shortlist state unknown`
          : input.matchCount === 0
            ? "Matching not run"
            : `${input.matchCount} found · ${shortlisted} shortlisted`,
    },
    {
      key: "share",
      label: "Share",
      done: shareDone,
      detail: shareDone
        ? `${input.shared} shared`
        : input.sharesApproved > 0
          ? `${input.sharesApproved} approved, not sent`
          : "Approve, then send",
    },
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

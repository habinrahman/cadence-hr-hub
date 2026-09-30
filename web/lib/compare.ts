import type { CompareItemStatus, Comparison, EvidenceItem } from "@/lib/api";
import { RELATIONSHIP_LABELS, type Tone } from "@/lib/labels";

const DECIDED = new Set(["accepted_update", "recorded_duplicate", "created_separate"]);

export function isDecided(status: string): boolean {
  return DECIDED.has(status);
}

/** How each comparison result is worded. "Unknown" is never shown as a difference, and nothing is called removed. */
export const ITEM_STATUS: Record<CompareItemStatus, { label: string; tone: Tone; mark: string }> = {
  same: { label: "Same", tone: "neutral", mark: "=" },
  added: { label: "Added in incoming CV", tone: "ok", mark: "+" },
  changed: { label: "Changed", tone: "warn", mark: "~" },
  only_existing: { label: "Not found in incoming CV", tone: "warn", mark: "?" },
  unknown: { label: "Not compared", tone: "unknown", mark: "·" },
};

const pct = (value: number | null) => (value === null ? "" : `${Math.round(value * 100)}%`);

/**
 * One backend signal in plain words. The state meanings come from the scoring code:
 * cv_dates "matched" means the incoming CV mentions later dates than what is stored,
 * and the similarity signals are token overlap, not a meaning model.
 */
export function describeSignal(item: EvidenceItem): { text: string; kind: "match" | "mismatch" | "unknown" | "info" } {
  const value = item.value;
  const unknown = (text: string) => ({ text, kind: "unknown" as const });
  switch (item.code) {
    case "email":
    case "phone": {
      const noun = item.code === "email" ? "email address" : "phone number";
      if (item.state === "matched") return { text: `Same ${noun}`, kind: "match" };
      if (item.state === "unmatched") return { text: `Different ${noun}`, kind: "mismatch" };
      return unknown(`${item.code === "email" ? "Email" : "Phone"} not available on both CVs`);
    }
    case "name":
      return item.state === "recorded" ? { text: `Name similarity ${pct(value)}`, kind: "info" } : unknown("Name not available on both CVs");
    case "document_hash":
      return item.state === "matched"
        ? { text: "Identical file", kind: "match" }
        : { text: "Not a byte-identical file", kind: "info" };
    case "cv_dates":
      if (item.state === "matched") return { text: "Incoming CV mentions later dates", kind: "match" };
      if (item.state === "unmatched") return { text: "Incoming CV does not mention later dates", kind: "mismatch" };
      return unknown("Dates not available to compare");
    case "explicit_version":
      if (item.state === "matched") return { text: "Incoming CV's own version date is later", kind: "match" };
      if (item.state === "unmatched") return { text: "Incoming CV's own version date is not later", kind: "mismatch" };
      return unknown("No version date labelled on both CVs");
    case "employment":
      return item.state === "recorded" ? { text: `Employment overlap ${pct(value)}`, kind: "info" } : unknown("Employment not available on both CVs");
    case "education":
      return item.state === "recorded" ? { text: `Education overlap ${pct(value)}`, kind: "info" } : unknown("Education not available on both CVs");
    case "skills":
      return item.state === "recorded" ? { text: `Skills overlap ${pct(value)}`, kind: "info" } : unknown("Skills not available on both CVs");
    case "semantic":
      return item.state === "recorded"
        ? { text: `Word overlap ${pct(value)} (not a meaning model)`, kind: "info" }
        : unknown("Word overlap not available");
    default:
      return unknown(`${item.code.replaceAll("_", " ")}: ${item.state}`);
  }
}

export function summarize(comparison: Comparison) {
  const counts = { same: 0, added: 0, changed: 0, notFound: 0 };
  const notCompared: string[] = [];
  for (const field of comparison.fields) {
    if (!field.comparable) {
      notCompared.push(field.label);
      continue;
    }
    for (const item of field.items) {
      if (item.status === "same") counts.same += 1;
      else if (item.status === "added") counts.added += 1;
      else if (item.status === "changed") counts.changed += 1;
      else if (item.status === "only_existing") counts.notFound += 1;
    }
  }
  return { ...counts, notCompared, differences: counts.added + counts.changed + counts.notFound };
}

/** The system's suggestion. It is never worded as a decision. */
export function recommendation(review: {
  likely_relationship: string | null;
  recommended_action: string | null;
  confidence: number | null;
  ambiguous: boolean;
}): { headline: string; action: string | null; basis: string } {
  if (review.ambiguous) {
    return {
      headline: "This CV may belong to more than one existing profile",
      action: null,
      basis: "More than one existing profile looks related, so no action is proposed.",
    };
  }
  const headline: Record<string, string> = {
    updated_cv: "Likely an updated CV",
    duplicate: "Likely a duplicate",
    different_candidate: "Likely a different person",
  };
  const label = review.likely_relationship ? (headline[review.likely_relationship] ?? RELATIONSHIP_LABELS[review.likely_relationship]) : null;
  if (review.recommended_action) {
    return {
      headline: label ?? "Relationship proposed",
      action: review.recommended_action,
      basis: "Above the high-confidence setting configured for Cadence.",
    };
  }
  return {
    headline: label ? `${label}, but not certain` : "No relationship proposed",
    action: null,
    basis: "Below the high-confidence setting, so no action is proposed.",
  };
}

export type DecisionCopy = { label: string; title: string; body: string; confirmLabel: string; tone: "primary" | "danger" };

/** What each existing backend action actually does, taken from how the backend applies it. */
export function decisionCopy(action: string): DecisionCopy {
  switch (action) {
    case "accept_update":
      return {
        label: "Accept as updated CV",
        title: "Accept this update?",
        body: "The incoming CV becomes the candidate's current CV. The previous CV stays in the candidate's history and can still be opened.",
        confirmLabel: "Accept update",
        tone: "primary",
      };
    case "record_duplicate":
      return {
        label: "Record as duplicate",
        title: "Record this as a duplicate?",
        body: "The incoming CV is linked to this candidate as another application but does not become the current CV. The existing CV stays current.",
        confirmLabel: "Record duplicate",
        tone: "primary",
      };
    case "create_separate_candidate":
      return {
        label: "It's a different person",
        title: "Save as a different candidate?",
        body: "A new candidate is created from the incoming CV. The existing candidate is not changed.",
        confirmLabel: "Create separate candidate",
        tone: "danger",
      };
    default:
      return { label: action, title: "Confirm this decision?", body: "This decision is recorded.", confirmLabel: "Confirm", tone: "primary" };
  }
}

export function documentStateMessage(state: string, side: "existing" | "incoming"): string | null {
  switch (state) {
    case "ok":
      return null;
    case "needs_ocr":
      return `The ${side} CV is a scan that has not been read yet (OCR is pending or unavailable), so its text and fields cannot be compared.`;
    case "no_text":
      return `The ${side} CV has no readable text on file, so its text and fields cannot be compared.`;
    case "failed":
    case "quarantined":
      return `The ${side} CV was set aside during processing (${state}), so it cannot be compared.`;
    case "no_document":
      return `There is no ${side} CV on file for this candidate.`;
    default:
      return `The ${side} CV is not available for comparison.`;
  }
}

export function normalizeLine(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

export const REASON_MESSAGE: Record<string, string> = {
  excel_row: "This review comes from a spreadsheet row, so there are no two CVs to compare.",
  incoming_document_missing: "The incoming document is no longer on file.",
  no_candidate: "No existing candidate is linked to this review.",
  no_existing_document: "The existing candidate has no CV on file to compare with.",
};

export const WARNING_MESSAGE: Record<string, string> = {
  review_decided: "This review has already been decided. You are viewing the record; no further decision is possible.",
  candidate_merged: "This candidate was merged into another profile. Choose a decision that does not attach the CV to it.",
  multiple_candidates: "More than one existing profile looks related. Pick the right one before deciding.",
  identical_bytes: "The two files are byte-identical.",
  date_conflict: "Date information conflicts: the labelled version date and the latest date mentioned point to different CVs. Read both before deciding.",
  no_current_document: "The candidate has no current CV, so the most recent one is shown.",
};

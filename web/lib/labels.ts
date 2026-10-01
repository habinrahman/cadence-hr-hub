export type Tone = "proposed" | "decided" | "ok" | "warn" | "bad" | "unknown" | "neutral";
export type Hue = "rel" | "req" | "match" | "share";

export const SIGNAL_LABELS: Record<string, string> = {
  email: "Email",
  phone: "Phone",
  name: "Name",
  document_hash: "Identical file",
  cv_dates: "CV dates",
  explicit_version: "Version date in the CV",
  employment: "Employment",
  education: "Education",
  skills: "Skills",
  semantic: "Wording similarity",
};

export const SIGNAL_STATE_LABELS: Record<string, string> = {
  matched: "Match",
  unmatched: "No match",
  unknown: "Not available",
  recorded: "Compared",
};

export const ACTION_LABELS: Record<string, string> = {
  accept_update: "Merge & Update Profile",
  record_duplicate: "Delete Duplicate",
  create_separate_candidate: "Create New Candidate",
};

/** An Excel row has no CV to delete: its "duplicate" outcome only records another application. */
export function actionLabel(action: string, hasDocument = true): string {
  if (action === "record_duplicate" && !hasDocument) return "Record as duplicate";
  return ACTION_LABELS[action] ?? action;
}

export const RELATIONSHIP_LABELS: Record<string, string> = {
  updated_cv: "Updated CV",
  duplicate: "Duplicate",
  different_candidate: "Different candidate",
  new: "New candidate",
  ambiguous: "Needs a choice",
};

export const DOCUMENT_STATUS: Record<string, { label: string; note: string; tone: Tone }> = {
  received: { label: "Queued", note: "Waiting for the reader.", tone: "neutral" },
  extracting: { label: "Reading", note: "The reader is extracting text. This page updates on its own.", tone: "neutral" },
  extracted: { label: "Extracted", note: "Text and profile fields were read.", tone: "ok" },
  needs_review: {
    label: "Needs a decision",
    note: "A recruiter has to decide how this CV relates to an existing profile.",
    tone: "proposed",
  },
  needs_ocr: {
    label: "Needs OCR",
    note: "No text layer was found. The file cannot be searched until it is read by OCR.",
    tone: "warn",
  },
  profiled: { label: "Profiled", note: "Linked to a candidate profile.", tone: "ok" },
  failed: { label: "Failed", note: "Processing failed.", tone: "bad" },
  quarantined: {
    label: "Quarantined",
    note: "Set aside so it cannot become a profile. See the problem code.",
    tone: "bad",
  },
  archived: { label: "Archived", note: "Kept on record after the retention period.", tone: "unknown" },
};

export const QUEUE_TYPE: Record<string, { label: string; hue: Hue; why: string; cta: string }> = {
  relationship_review: {
    label: "CV relationship",
    hue: "rel",
    why: "A CV overlaps an existing profile. You decide whether it updates, duplicates or is a different person.",
    cta: "Review and decide",
  },
  requirement_approval: {
    label: "Requirements",
    hue: "req",
    why: "Proposed from the job description. The pool is provisional, and nothing can be shortlisted or shared, until you approve them.",
    cta: "Review requirements",
  },
  match_review: {
    label: "Match review",
    hue: "match",
    why: "Candidates matched on the requirements you approved. Matching never shortlists; you choose.",
    cta: "Review matches",
  },
  share_approval: {
    label: "Share approval",
    hue: "share",
    why: "Shortlisted. Nothing has left Cadence until you approve and send.",
    cta: "Review share",
  },
};

export const DISPOSITION: Record<string, { label: string; tone: Tone }> = {
  recommended: { label: "Recommended", tone: "proposed" },
  needs_review: { label: "Needs review", tone: "warn" },
  excluded: { label: "Excluded", tone: "bad" },
  rejected: { label: "Rejected", tone: "bad" },
};

export const VERDICT: Record<string, { label: string; tone: Tone }> = {
  meets: { label: "Meets", tone: "ok" },
  partial: { label: "Partial", tone: "warn" },
  unmet: { label: "Not met", tone: "bad" },
  unknown: { label: "Unknown", tone: "unknown" },
};

export const SEARCH_REASON: Record<string, string> = {
  keyword: "Keyword in the CV",
  trigram: "Similar wording",
  semantic: "Related wording",
  skill: "Skill",
  name: "Name",
  education: "Education",
  experience: "Experience",
  certificate: "Certificate",
  years: "Years of experience",
  job_title: "Job title",
  industry: "Industry experience",
  nationality: "Nationality written in the CV",
  filter: "Filter",
};

export const AUDIT_ACTION: Record<string, string> = {
  demo_reset: "Candidate repository reset",
  document_received: "File received",
  document_extracted: "Extraction finished",
  same_document: "Identical file recognised",
  duplicate_review_opened: "Recommendation prepared",
  duplicate_review_rescored: "Recommendation re-scored with the current rules",
  duplicate_review_decided: "Recruiter decided",
  accepted_update: "Accepted update",
  recorded_duplicate: "Marked duplicate",
  created_separate: "Saved as a different candidate",
  field_lock_kept: "Locked field kept",
  candidate_viewed: "Profile opened",
  pii_text_access: "CV text opened",
  review_comparison_viewed: "CV comparison opened",
  cv_preview_viewed: "CV page preview opened",
  shortlist_decision: "Shortlisted",
  share_approved: "Share approved",
  candidate_shared: "Candidate shared",
  candidate_share_failed: "Share failed",
  matching_run: "Matching run",
  hiring_request_created: "Request created",
  sourced_cv_attached: "CV attached",
  sourced_duplicate_detected: "Duplicate detected",
  sourced_review_decided: "Recruiter decision",
  sourced_candidate_created: "Candidate created",
  candidate_recommended: "Candidate proposed for a request",
  job_enqueued: "Background job queued",
  job_succeeded: "Background job finished",
  job_quarantined: "Background job set aside",
  document_needs_ocr: "File needs OCR",
  requirements_extracted: "Requirements proposed",
  requirements_changed: "Requirements changed",
  pool_opened: "Candidate pool opened",
  candidate_rejected: "Candidate rejected",
  candidate_restored: "Rejection undone, back in the pool",
  request_contact_changed: "Company contact set",
  sourced_candidate_attached: "Source added to an existing profile",
  profiles_merged: "Profiles merged",
  excel_import_completed: "Excel import finished",
  hiring_activity_exported: "Hiring activity exported",
  problem_report_created: "Problem reported",
  problem_report_updated: "Problem report updated",
  problem_report_status_changed: "Problem report status changed",
  problem_report_resolved: "Problem report resolved",
};

export const REPORT_STATUS: Record<string, { label: string; tone: Tone }> = {
  open: { label: "Open", tone: "warn" },
  in_progress: { label: "In progress", tone: "decided" },
  resolved: { label: "Resolved", tone: "ok" },
};

export const PROCESSING_STAGE: Record<string, string> = {
  received: "Received",
  extracting: "Extracting requirements",
  matching: "Matching candidates",
  complete: "Matching complete",
  failed: "Processing failed",
};

export const REQUEST_STATUS: Record<string, string> = {
  draft: "Draft",
  submitted: "Submitted",
  open: "Open",
  matching: "Matching",
  closed: "Closed",
  cancelled: "Cancelled",
};

export const SOURCE_TYPE: Record<string, string> = { linkedin: "LinkedIn", referral: "Referral", other: "Other" };

export function labelAudit(action: string): string {
  return AUDIT_ACTION[action] ?? action.replaceAll("_", " ");
}

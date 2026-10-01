import { apiError, ConnectionError, FileReadError } from "./errors";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const token = process.env.NEXT_PUBLIC_RECRUITER_TOKEN ?? "";

export type DocumentSummary = {
  id: string;
  status: string;
  original_filename: string;
  identity_outcome: string | null;
  candidate_id: string | null;
  is_current: boolean;
  error_code: string | null;
  received_at: string;
  extracted_contacts?: { kind: string; value: string }[];
};

export type EvidenceItem = {
  code: string;
  weight: number;
  state: string;
  value: number | null;
  candidate_id?: string;
};

export type Review = {
  id: string;
  document_id?: string | null;
  status: string;
  confidence: number | null;
  likely_relationship: string | null;
  recommended_action: string | null;
  offered_actions: string[];
  candidate_id: string | null;
  candidate_ids: string[];
  candidates: { id: string; display_name: string | null }[];
  ambiguous: boolean;
  evidence: EvidenceItem[];
  source?: string | null;
};

export type CandidateProfile = {
  id: string;
  display_name: string | null;
  summary: string | null;
  narrative: string | null;
  years_of_experience: number | null;
  source: string;
  sources: { source_type: string; source_reference: string }[];
  contacts: { kind: string; value: string }[];
  experiences: { employer: string; title: string | null }[];
  education: { institution: string; credential: string | null }[];
  skills: string[];
  certificates: { name: string; kind: string }[];
  qualifications: { name: string; kind: string }[];
  applications: {
    id: string;
    source: string;
    received_at: string;
    application_date: string | null;
    document_id: string | null;
  }[];
  documents: {
    id: string;
    original_filename: string;
    status: string;
    is_current: boolean;
    received_at: string;
    supersedes_document_id: string | null;
    /** The newest relationship review for this file, if there is one. */
    review_id?: string | null;
  }[];
  evidence: { field: string; value: string; quote: string; page: number | null; quote_verified: boolean }[];
  activity: { action: string; actor_kind: string; created_at: string }[];
};

export type ActivityEvent = {
  action: string;
  actor_kind: string;
  created_at: string;
  detail: Record<string, string | number | boolean | null>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw apiError(response.status, body.detail);
  }
  return response.json() as Promise<T>;
}

export function listDocuments() {
  return request<{ documents: DocumentSummary[] }>("/documents");
}

export function getDocument(id: string) {
  return request<DocumentSummary>(`/documents/${id}`);
}

export function getReview(id: string) {
  return request<Review>(`/documents/${id}/review`);
}

export function getReviewRecord(id: string) {
  return request<Review>(`/reviews/${id}`);
}

export function getCandidate(id: string) {
  return request<CandidateProfile>(`/candidates/${id}`);
}

export type DeskItem = {
  type: string;
  subject: string;
  status: string;
  created_at: string;
  href: string;
  /** Requirement approvals and confirmed pools: how many requirements or candidates the item stands for. */
  count?: number;
  /** Relationship reviews: what Cadence recommends, if it is confident enough to, and the signal strength out of 100. */
  relationship?: string | null;
  recommended_action?: string | null;
  confidence?: number | null;
};

export type Dashboard = {
  counts: {
    relationship_reviews: number;
    requirements_awaiting_approval: number;
    matches_awaiting_review: number;
    shortlisted_candidates: number;
    shares_awaiting_approval: number;
    open_problem_reports: number;
    active_hiring_requests: number;
    requests_received: number;
    new_matches: number;
    duplicate_reviews: number;
    reviews_needing_attention: number;
  };
  relationship_reviews: DeskItem[];
  requirements_awaiting_approval: DeskItem[];
  matches_awaiting_review: DeskItem[];
  shortlisted_candidates: DeskItem[];
  shares_awaiting_approval: DeskItem[];
  open_problem_reports: DeskItem[];
  recent_activity: (AuditEventView & { actor_kind: string })[];
  active_hiring_requests: DeskItem[];
  needs_you_now: DeskItem[];
  new_match_pools: DeskItem[];
  viewer_id: string;
};

/** One audit row as a person reads it: who, what, when, and the request, candidate or file it concerns. */
export type AuditEventView = {
  id: string;
  created_at: string;
  action: string;
  actor: { kind: string; name: string | null };
  request: { id: string; label: string } | null;
  candidate: { id: string; label: string } | null;
  document: { id: string; label: string } | null;
  detail: Record<string, unknown>;
};

export type AuditPage = { events: AuditEventView[]; next_before: string | null };

export function getAudit(params: { category?: string; before?: string | null; requestId?: string; candidateId?: string } = {}) {
  const query = new URLSearchParams();
  if (params.category) query.set("category", params.category);
  if (params.before) query.set("before", params.before);
  if (params.requestId) query.set("request_id", params.requestId);
  if (params.candidateId) query.set("candidate_id", params.candidateId);
  const suffix = query.toString();
  return request<AuditPage>(`/audit${suffix ? `?${suffix}` : ""}`);
}

export function getDashboard() {
  return request<Dashboard>("/dashboard");
}

export function getWorkQueue() {
  return request<{ items: DeskItem[] }>("/work-queue");
}

export function listHiringMatches(requestId: string) {
  return request<{ matches: CandidateMatch[] }>(`/hiring-requests/${requestId}/matches`);
}

export function getActivity(id: string) {
  return request<{ events: ActivityEvent[] }>(`/documents/${id}/activity`);
}

/** Resolves when the API answers its public health check. The browser is the one asking, so this tests the same route uploads use. */
export async function checkApiReachable(): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/health`, { cache: "no-store" });
  } catch {
    throw new ConnectionError(API_URL, "the request was blocked or got no response");
  }
  if (!response.ok) throw new ConnectionError(API_URL, `health check returned ${response.status}`);
}

export async function uploadDocument(file: File) {
  // Read the bytes first: an unreadable file is reported as that, not as a network failure, and a file
  // that changes on disk mid-upload (cloud sync, editors) cannot abort the request.
  let bytes: ArrayBuffer;
  try {
    bytes = await file.arrayBuffer();
  } catch {
    throw new FileReadError(file.name);
  }
  const body = new FormData();
  body.append("file", new File([bytes], file.name, { type: file.type }));
  try {
    return await request<{ id: string; status: string; created: boolean }>("/documents", {
      method: "POST",
      body,
    });
  } catch (error) {
    // fetch rejects with a TypeError only when no HTTP response arrived. An answer, even an error, is an ApiError.
    if (error instanceof TypeError) throw new ConnectionError(API_URL, "no response to the upload");
    throw error;
  }
}

export type DemoStatus = {
  documents: number;
  documents_by_status: Record<string, number>;
  identity_outcomes: Record<string, number>;
  candidates: number;
  pending_reviews: number;
  needs_ocr: number;
  quarantined: number;
  failed: number;
  processing: number;
  open_jobs: number;
  hiring_requests: number;
  matches: number;
  shortlisted: number;
  shares: number;
  last_reset_at: string | null;
  quarantine_records: number;
};

export function getDemoStatus() {
  return request<DemoStatus>("/demo/status");
}

export function resetDemoData() {
  return request<{ reset_at: string }>("/demo/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: "RESET" }),
  });
}

export type SourcedCandidate = {
  id: string;
  display_name: string;
  email: string | null;
  phone: string | null;
  source_type: string;
  source_reference: string;
  notes: string | null;
  /** None for a lead recorded before any CV exists. */
  document_id: string | null;
  document_status: string | null;
  identity_outcome: string | null;
  candidate_id: string | null;
  review_id: string | null;
  events: { action: string; actor_kind: string; created_at: string }[];
};

/** A profile a sourced lead may already be, with the reasons the check found. */
export type LeadMatch = { candidate_id: string; display_name: string | null; reasons: string[] };

export function submitSourcedCandidate(form: FormData) {
  return request<SourcedCandidate>("/sourced-candidates", { method: "POST", body: form });
}

export function getSourcedCandidate(id: string) {
  return request<SourcedCandidate>(`/sourced-candidates/${id}`);
}

export type HiringRequirement = {
  id: string;
  label: string;
  text: string;
  strength: "mandatory" | "preferred";
  source_quote: string | null;
  review_status: string;
};

export type MatchRequirement = {
  requirement_id: string;
  label: string;
  text: string;
  strength: string;
  result: string;
  evidence_id: string | null;
  evidence: string | null;
  retrieval: string | null;
  /** For an experience requirement: how the years were added up. The quote shows one dated role. */
  calculation?: string | null;
  /** Null unless the candidate passed the mandatory gate: the points only add up to a ranking score then. */
  points_possible?: number | null;
  points_earned?: number | null;
};

/** The mandatory gate. Decided from the requirement verdicts before any score. */
export type Eligibility = "eligible" | "needs_review" | "excluded";

export type BlockingRequirement = { requirement_id: string; name: string; result: string };

export type CandidateMatch = {
  id: string;
  candidate_id: string;
  candidate_name: string | null;
  disposition: string;
  /** What a recruiter already decided for this candidate on this request. Server truth; not inferred by the page. */
  shortlisted?: boolean;
  share_approved?: boolean;
  shared?: boolean;
  request_id?: string;
  requirement_met_ratio?: number | null;
  eligibility: Eligibility;
  /**
   * 0-100, whole number, for ranking candidates who meet every mandatory requirement. Null for anyone held at the
   * mandatory gate: that is "no score", not a low one. match_score_exact is the unrounded sum of the points.
   * This is not the CV relationship (same-person) score.
   */
  match_score: number | null;
  match_score_exact: number | null;
  score_max?: number;
  mandatory_met: number;
  mandatory_total: number;
  preferred_met: number;
  preferred_total: number;
  /** Mandatory requirements holding the candidate: unmet ones when excluded, partial or unknown ones when in review. */
  blocking_requirements: BlockingRequirement[];
  score_reason: string;
  processing_version?: number | null;
  explanation: string | null;
  strengths: string[];
  gaps: string[];
  requirements: MatchRequirement[];
  years_of_experience?: number | null;
  location?: string | null;
};

/** awaiting_approval: no requirement was proposed, so there is nothing to match on until HR adds one. */
export type ProcessingStage = "received" | "extracting" | "awaiting_approval" | "matching" | "complete" | "failed";

/**
 * provisional: matched on requirements HR has not approved (or a rematch is pending). Viewable, not shortlistable or shareable.
 * confirmed: matched on HR-approved requirements only.
 */
export type PoolStatus = "none" | "provisional" | "confirmed";

export type Processing = {
  stage: ProcessingStage;
  matched_count: number;
  requested_count: number | null;
  pool_status?: PoolStatus;
};

export type RequestNote = {
  id: string;
  body: string;
  kind: string;
  author_user_id: string;
  created_at: string | null;
};

export type RequestAttachment = { id: string; filename: string; media_type: string; byte_size: number };

export type RequestSummary = {
  id: string;
  company: string;
  job_title: string;
  status: string;
  received_at: string;
  processing: ProcessingStage;
  matched_count: number;
  requested_count: number | null;
};

export type HiringRequestDetail = {
  id: string;
  company: string;
  job_title: string;
  description: string;
  status: string;
  received_at: string;
  owner_user_id: string | null;
  notes: RequestNote[];
  updates: RequestNote[];
  next_steps: RequestNote[];
  attachments: RequestAttachment[];
  requirements: HiringRequirement[];
  candidates_found: number;
  candidates_shared: number;
  processing: Processing;
  pool_stale: boolean;
  /** Which reader proposed the current requirements. `fallback` means the model was not used. */
  requirements_source?: {
    model: string | null;
    prompt_version: string | null;
    fallback: boolean;
    /** Why the model did not answer: description_too_long, model_unreachable or model_reply_malformed. */
    fallback_reason?: string | null;
    /** Proposals that passed every check. */
    accepted?: number | null;
    /** Rejected proposals by reason code. Codes only, never the proposed text. */
    rejected?: Record<string, number>;
  } | null;
  pool_opened_at: string | null;
  last_match_completed_at: string | null;
  requested_count: number | null;
};

export function createHiringRequest(input: {
  company: string;
  job_title: string;
  description: string;
  received_at: string;
  requested_count?: number;
  contact_email?: string;
}) {
  return request<{ id: string; status: string }>("/hiring-requests", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function getHiringRequest(id: string) {
  return request<HiringRequestDetail>(`/hiring-requests/${id}`);
}

export function editHiringRequirement(
  requestId: string,
  requirementId: string,
  patch: {
    text?: string;
    strength?: "mandatory" | "preferred";
    label?: "skill" | "experience" | "education" | "certification" | "other";
    quote?: string;
  },
) {
  return request<HiringRequirement>(`/hiring-requests/${requestId}/requirements/${requirementId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export function addHiringRequirement(
  id: string,
  body: { label: "skill" | "experience" | "education" | "certification" | "other"; text: string; strength: "mandatory" | "preferred"; quote: string },
) {
  return request<HiringRequirement>(`/hiring-requests/${id}/requirements/manual`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** HR rejects one requirement. It is kept and labelled, never matched on, and a rematch runs if there is a pool. */
export function rejectHiringRequirement(requestId: string, requirementId: string) {
  return request<HiringRequirement>(`/hiring-requests/${requestId}/requirements/${requirementId}/reject`, { method: "POST" });
}

export function approveHiringRequirements(id: string, requirementIds?: string[]) {
  return request<{ requirements: HiringRequirement[] }>(`/hiring-requests/${id}/requirements/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ requirement_ids: requirementIds ?? null }),
  });
}

export function openPool(id: string) {
  return request<{ pool_opened_at: string | null }>(`/hiring-requests/${id}/pool/open`, { method: "POST" });
}

export function retryProcessing(id: string) {
  return request<{ job_id: string; status: string }>(`/hiring-requests/${id}/process/retry`, { method: "POST" });
}

export function runHiringMatch(id: string) {
  return request<{ matches: CandidateMatch[] }>(`/hiring-requests/${id}/matches`, { method: "POST" });
}

export function shortlistMatch(requestId: string, matchId: string) {
  return request<{ review_state: string }>(`/hiring-requests/${requestId}/matches/${matchId}/shortlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

export function rejectMatch(requestId: string, matchId: string) {
  return request<{ disposition: string }>(`/hiring-requests/${requestId}/matches/${matchId}/reject`, {
    method: "POST",
  });
}

/** Undo a rejection: the candidate goes back to what the requirement verdicts say. Nothing is shortlisted. */
export function restoreMatch(requestId: string, matchId: string) {
  return request<{ disposition: string }>(`/hiring-requests/${requestId}/matches/${matchId}/restore`, {
    method: "POST",
  });
}

export type ShareRecord = {
  id: string;
  status: string;
  destination: string;
  recipient: string | null;
  request_id: string | null;
  candidate_id: string;
  shortlist_id: string | null;
  sent_at: string | null;
  sender: string | null;
  audit: { id: string; action: string; created_at: string } | null;
};

/** The company contact a request's shortlist goes to. */
export function setRequestContact(requestId: string, contactEmail: string) {
  return request<{ id: string; contact_email: string }>(`/hiring-requests/${requestId}/contact`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contact_email: contactEmail }),
  });
}

export type SharePreview = {
  company: string;
  /** Null until a recruiter names the company contact; nothing is sent before that. */
  recipient: string | null;
  candidate: string;
  candidate_id: string;
  role: string;
  selected: {
    years_of_experience: number | null;
    /** The requirements of this request the candidate met. Not the raw skills list, which carries hobbies. */
    requirements_met: string[];
  };
  approved: boolean;
  sharing: ShareRecord | null;
};

export function getSharePreview(requestId: string, candidateId: string) {
  return request<SharePreview>(`/hiring-requests/${requestId}/candidates/${candidateId}/share`);
}

export function approveShare(requestId: string, candidateId: string) {
  return request<{ id: string; decision: string }>(
    `/hiring-requests/${requestId}/candidates/${candidateId}/share/approve`,
    { method: "POST" },
  );
}

export function sendShare(requestId: string, candidateId: string) {
  return request<ShareRecord>(`/hiring-requests/${requestId}/candidates/${candidateId}/share`, {
    method: "POST",
  });
}

export function decideReview(reviewId: string, action: string, candidateId?: string) {
  return request<Review>(`/reviews/${reviewId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, candidate_id: candidateId ?? null }),
  });
}

export type SearchHit = {
  candidate_id: string | null;
  candidate_name: string | null;
  document_id: string;
  chunk_id: string | null;
  confirmed_profile?: boolean;
  evidence: string;
  reasons: string[];
  retrieval_score: number;
};

export function searchCandidates(params: Record<string, string>) {
  const query = new URLSearchParams(params);
  return request<{ results: SearchHit[] }>(`/search?${query.toString()}`);
}

export type CandidateRow = {
  candidate_id: string;
  candidate_name: string | null;
  years_of_experience: number | null;
  latest_title: string | null;
  skills: string[];
  source: string;
  updated_at: string;
};

/** Read-only listing of confirmed profiles. Unlike opening a profile, it writes no audit event. */
export function listCandidates(limit: number, offset: number) {
  return request<{ total: number; limit: number; offset: number; candidates: CandidateRow[] }>(
    `/candidates?limit=${limit}&offset=${offset}`,
  );
}

export type MergeProfile = {
  id: string;
  display_name: string | null;
  source: string;
  merged_into_id: string | null;
  contacts: { kind: string; value: string }[];
  experiences: { employer: string; title: string | null }[];
  education: { institution: string; credential: string | null }[];
  skills: string[];
  document_count: number;
  application_count: number;
};

export type MergePreview = {
  survivor_id: string;
  absorbed_id: string;
  profiles: MergeProfile[];
};

export function previewMerge(leftId: string, rightId: string) {
  const query = new URLSearchParams({ left_id: leftId, right_id: rightId });
  return request<MergePreview>(`/profile-merges/preview?${query.toString()}`);
}

export function confirmMerge(leftId: string, rightId: string) {
  return request<MergePreview>("/profile-merges", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ left_id: leftId, right_id: rightId, confirm: true }),
  });
}

export type ProblemReport = {
  id: string;
  category: string;
  title: string;
  description: string;
  status: string;
  entity_type: string;
  entity_id: string | null;
  context: { error_code?: string; route?: string; action?: string };
  engineering_note: string | null;
  created_at?: string | null;
};

export function listProblemReports() {
  return request<{ reports: ProblemReport[] }>("/problem-reports");
}

export type ExcelImportReport = {
  id: string;
  row_count: number;
  valid_count: number;
  invalid_count: number;
  missing_required: number;
  malformed: number;
  duplicate_count: number;
  relationship_count: number;
  created_count: number;
  ignored_column_count: number;
  rows: {
    row: number;
    outcome: string;
    errors: string[];
    relationship: string | null;
    duplicate_of_row: number | null;
    review_id: string | null;
  }[];
};

export function importExcelCandidates(file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<ExcelImportReport>("/excel/candidates", { method: "POST", body });
}

export async function downloadHiringExport(start: string, end: string) {
  const headers = new Headers();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const response = await fetch(`${API_URL}/hiring-activity/export?start=${start}&end=${end}`, {
    headers,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw apiError(response.status, body.detail);
  }
  return response.blob();
}

export function createProblemReport(input: {
  category: string;
  title: string;
  description: string;
  entity_type: string;
  entity_id: string | null;
  context: { error_code?: string; route?: string; action?: string };
}) {
  return request<ProblemReport>("/problem-reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export function listHiringRequests() {
  return request<{ requests: RequestSummary[] }>("/hiring-requests");
}

export function addRequestNote(id: string, kind: "notes" | "updates" | "next-steps", body: string) {
  return request<{ id: string; kind: string }>(`/hiring-requests/${id}/${kind}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
}

export function addRequestAttachment(id: string, file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<{ id: string; filename: string }>(`/hiring-requests/${id}/attachments`, { method: "POST", body });
}

export function getDocumentText(id: string) {
  return request<{ id: string; text: string }>(`/documents/${id}/text`);
}

export function getExcelImport(id: string) {
  return request<ExcelImportReport>(`/excel/candidates/${id}`);
}

export type CompareEvidence = { quote: string; page: number | null };
export type CompareValue = { label: string; evidence: CompareEvidence } | null;
export type CompareItemStatus = "same" | "added" | "changed" | "only_existing" | "unknown";
export type CompareItem = {
  status: CompareItemStatus;
  label: string;
  existing: CompareValue;
  incoming: CompareValue;
  similarity?: number | null;
};
export type CompareFieldState = "extracted" | "not_extracted" | "unavailable";
export type CompareField = {
  key: string;
  label: string;
  comparable: boolean;
  existing_state: CompareFieldState;
  incoming_state: CompareFieldState;
  note: string | null;
  items: CompareItem[];
  stored_name?: string | null;
};
export type CompareDocument = {
  id: string;
  filename: string;
  media_type: string;
  byte_size: number;
  received_at: string;
  page_count: number;
  status: string;
  is_current: boolean;
  text_source: string | null;
  language_code: string | null;
  error_code: string | null;
};
export type CompareSide = { state: string; document: CompareDocument | null };
export type CompareDateFact = { date: string; page: number } | null;
export type CompareDates = {
  existing: { latest_mentioned: CompareDateFact; labelled_version: CompareDateFact } | null;
  incoming: { latest_mentioned: CompareDateFact; labelled_version: CompareDateFact } | null;
  uploaded: { existing: string | null; incoming: string | null };
  newer_by_mentioned: "incoming" | "existing" | "same" | null;
  newer_by_labelled: "incoming" | "existing" | "same" | null;
  conflict: boolean;
};
export type TextDiffLine = { page: number; text: string };
export type TextDiff = {
  available: boolean;
  note: string;
  incoming_only: TextDiffLine[];
  existing_only: TextDiffLine[];
  incoming_only_count: number;
  existing_only_count: number;
  truncated: boolean;
};
export type Comparison = {
  review_id: string;
  status: string;
  decided_at: string | null;
  available: boolean;
  reason: string | null;
  warnings: string[];
  candidates: { id: string; name: string | null; merged_into_id: string | null }[];
  candidate: { id: string; name: string | null; merged_into_id: string | null } | null;
  existing: CompareSide | null;
  incoming: CompareSide | null;
  identical_bytes: boolean;
  fields: CompareField[];
  dates: CompareDates | null;
  text_diff: TextDiff | null;
};

export function getReviewComparison(reviewId: string, candidateId?: string) {
  const query = candidateId ? `?candidate_id=${encodeURIComponent(candidateId)}` : "";
  return request<Comparison>(`/reviews/${reviewId}/comparison${query}`);
}

export type DocumentPages = { id: string; page_count: number; pages: { number: number; text: string }[] };

/** One rendered page of a CV in a review, as an image. The session token goes in the header, so it cannot be a plain <img src>. */
export async function fetchPagePreview(path: string): Promise<{ blob: Blob; pages: number; highlights: number }> {
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${API_URL}${path}`, { headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw apiError(response.status, body.detail);
  }
  return {
    blob: await response.blob(),
    pages: Number(response.headers.get("X-Preview-Pages") ?? 1),
    highlights: Number(response.headers.get("X-Preview-Highlights") ?? 0),
  };
}

export function getDocumentPages(id: string) {
  return request<DocumentPages>(`/documents/${id}/pages`);
}

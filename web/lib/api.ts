import { ApiError } from "./errors";

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
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`);
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
  };
  relationship_reviews: DeskItem[];
  requirements_awaiting_approval: DeskItem[];
  matches_awaiting_review: DeskItem[];
  shortlisted_candidates: DeskItem[];
  shares_awaiting_approval: DeskItem[];
  open_problem_reports: DeskItem[];
  recent_activity: { action: string; actor_kind: string; created_at: string }[];
  active_hiring_requests: DeskItem[];
  viewer_id: string;
};

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

export function uploadDocument(file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<{ id: string; status: string; created: boolean }>("/documents", {
    method: "POST",
    body,
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
  document_id: string;
  document_status: string | null;
  identity_outcome: string | null;
  candidate_id: string | null;
  review_id: string | null;
  events: { action: string; actor_kind: string; created_at: string }[];
};

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
};

export type CandidateMatch = {
  id: string;
  candidate_id: string;
  candidate_name: string | null;
  disposition: string;
  request_id?: string;
  requirement_met_ratio?: number | null;
  processing_version?: number | null;
  explanation: string | null;
  strengths: string[];
  gaps: string[];
  requirements: MatchRequirement[];
};

export type RequestNote = {
  id: string;
  body: string;
  kind: string;
  author_user_id: string;
  created_at: string | null;
};

export type RequestAttachment = { id: string; filename: string; media_type: string; byte_size: number };

export type RequestSummary = { id: string; company: string; job_title: string; status: string; received_at: string };

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
};

export function createHiringRequest(input: {
  company: string;
  job_title: string;
  description: string;
  received_at: string;
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

export function extractHiringRequirements(id: string) {
  return request<{ requirements: HiringRequirement[] }>(`/hiring-requests/${id}/requirements`, {
    method: "POST",
  });
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

export function approveHiringRequirements(id: string, requirementIds?: string[]) {
  return request<{ requirements: HiringRequirement[] }>(`/hiring-requests/${id}/requirements/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ requirement_ids: requirementIds ?? null }),
  });
}

export function openHiringRequest(id: string) {
  return request<{ id: string; status: string }>(`/hiring-requests/${id}/open`, { method: "POST" });
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

export type SharePreview = {
  company: string;
  recipient: string;
  candidate: string;
  candidate_id: string;
  role: string;
  selected: {
    years_of_experience: number | null;
    skills: string[];
    title: string | null;
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
    throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`);
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

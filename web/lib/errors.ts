export class ApiError extends Error {
  status: number;
  code: string;
  /** The server's structured detail when it sent one (for example the profiles a sourced lead may match). */
  detail: unknown;
  constructor(status: number, code: string, detail: unknown = null) {
    super(code);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

/** The browser could not complete the HTTP exchange: nothing came back, so the server never answered. */
export class ConnectionError extends Error {
  url: string;
  constructor(url: string, reason = "no response") {
    super(`Could not reach the API at ${url} (${reason})`);
    this.url = url;
  }
}

/** The chosen file could not be read from disk, so no request was sent for it. */
export class FileReadError extends Error {
  constructor(name: string) {
    super(`Could not read ${name} from disk`);
  }
}

/** The server's error detail as an ApiError: a string is the code; an object carries its own "code". */
export function apiError(status: number, detail: unknown): ApiError {
  if (typeof detail === "string") return new ApiError(status, detail);
  if (detail && typeof detail === "object" && typeof (detail as { code?: unknown }).code === "string") {
    return new ApiError(status, (detail as { code: string }).code, detail);
  }
  return new ApiError(status, `Request failed (${status})`);
}

export type ErrorKind = "auth" | "forbidden" | "missing" | "conflict" | "server" | "network" | "input";

const CONFLICT_WORDS: Record<string, string> = {
  requirements_not_approved: "Approve at least one requirement before running matching.",
  blocked_attribute: "That is a protected characteristic, so it cannot be a requirement.",
  unsupported_requirement: "The quote must be copied word for word from the job description, and the requirement must appear in it.",
  injected_instruction: "That text reads as an instruction, not a requirement.",
  request_not_open: "This request is not open for matching.",
  not_shortlisted: "This candidate has not been shortlisted for this request.",
  not_shortlistable: "Only recommended or needs-review candidates can be shortlisted.",
  approval_required: "Approve the share before sending it.",
  invalid_transition: "That action is not allowed in the current state.",
  human_required: "A recruiter has to take this action.",
  external_mail_blocked: "Sending is blocked outside the local mail catcher in this environment.",
  mail_delivery_failed: "The mail server did not accept the message. Nothing was recorded as sent.",
  empty_update: "Nothing to update.",
  unsafe_report_text:
    "Take out passwords, tokens, email addresses and long numbers such as phone numbers. Describe the problem in words; the engineer sees the linked record.",
  candidate_merged: "That profile was merged into another one since this review opened. Open the surviving profile, or create a new candidate.",
  recipient_missing: "Add the company contact email before sending. Nothing was sent.",
  invalid_recipient: "That is not a valid email address.",
  possible_existing: "This person may already be on file. Choose the existing profile or confirm a new one.",
  not_a_match: "That profile was not one of the possible matches. Choose one from the list.",
};

function clean(code: string): string {
  if (!code || code.includes("[object") || code.startsWith("{") || code.startsWith("[")) return "";
  return code.replaceAll("_", " ");
}

export function describeError(error: unknown): { kind: ErrorKind; title: string; body: string } {
  if (error instanceof ApiError) {
    const { status, code } = error;
    if (status === 401)
      return {
        kind: "auth",
        title: "Your session is not accepted",
        body: "The desk could not verify you. Sign in again or ask an administrator to check your access.",
      };
    if (status === 403)
      return {
        kind: "forbidden",
        title: "This role cannot open this",
        body: "Your role does not allow this action. Recruiter-only screens return this for other roles.",
      };
    if (status === 404) return { kind: "missing", title: "Not found", body: "That record does not exist or was removed." };
    if (status === 422)
      return { kind: "input", title: "Check the entries", body: CONFLICT_WORDS[code] ?? (clean(code) || "Some fields were not accepted.") };
    if (status === 409 || CONFLICT_WORDS[code])
      return {
        kind: "conflict",
        title: "Cannot do that now",
        body: CONFLICT_WORDS[code] ?? (clean(code) || "The record is in a different state."),
      };
    if (status === 413) return { kind: "input", title: "File too large", body: "Choose a smaller file." };
    if (status === 415)
      return { kind: "input", title: "File type not supported", body: "Use PDF, Word or an image of a scan." };
    if (status === 502)
      return { kind: "server", title: "Could not deliver", body: CONFLICT_WORDS[code] ?? "A downstream service failed." };
    if (status >= 500)
      return {
        kind: "server",
        title: "The server had a problem",
        body: "Try again. If it keeps happening, file a problem report.",
      };
    return { kind: "server", title: "Request failed", body: clean(code) || `Status ${status}.` };
  }
  if (error instanceof TypeError)
    return { kind: "network", title: "Cannot reach the server", body: "Check your connection and try again." };
  const message = error instanceof Error ? error.message : "";
  return { kind: "server", title: "Something went wrong", body: clean(message) || "Try again." };
}

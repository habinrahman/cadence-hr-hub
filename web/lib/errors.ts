export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

export type ErrorKind = "auth" | "forbidden" | "missing" | "conflict" | "server" | "network" | "input";

const CONFLICT_WORDS: Record<string, string> = {
  requirements_not_approved: "Approve at least one requirement before running matching.",
  request_not_open: "This request is not open for matching.",
  not_shortlisted: "This candidate has not been shortlisted for this request.",
  not_shortlistable: "Only recommended or needs-review candidates can be shortlisted.",
  approval_required: "Approve the share before sending it.",
  invalid_transition: "That action is not allowed in the current state.",
  human_required: "A recruiter has to take this action.",
  external_mail_blocked: "Sending is blocked outside the local mail catcher in this environment.",
  mail_delivery_failed: "The mail server did not accept the message. Nothing was recorded as sent.",
  empty_update: "Nothing to update.",
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
    if (status === 409 || CONFLICT_WORDS[code])
      return {
        kind: "conflict",
        title: "Cannot do that now",
        body: CONFLICT_WORDS[code] ?? (clean(code) || "The record is in a different state."),
      };
    if (status === 413) return { kind: "input", title: "File too large", body: "Choose a smaller file." };
    if (status === 415)
      return { kind: "input", title: "File type not supported", body: "Use PDF, Word or an image of a scan." };
    if (status === 422)
      return { kind: "input", title: "Check the entries", body: clean(code) || "Some fields were not accepted." };
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

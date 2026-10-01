import type { RequestSummary } from "@/lib/api";

export type RequestView = "all" | "processing" | "complete" | "closed";

export function filterRequests(rows: RequestSummary[], view: RequestView): RequestSummary[] {
  const done = (r: RequestSummary) => ["closed", "shared", "cancelled"].includes(r.status);
  if (view === "processing") return rows.filter((r) => !done(r) && r.processing !== "complete");
  if (view === "complete") return rows.filter((r) => !done(r) && r.processing === "complete");
  if (view === "closed") return rows.filter(done);
  return rows;
}

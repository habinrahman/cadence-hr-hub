"use client";

import { useSearchParams } from "next/navigation";
import { IndexView } from "./index-view";
import { NewRequest } from "./new-request";
import { Workspace } from "./workspace";

/** The backend links to /hiring?request=<id>[&candidate=<id>]. Keep that contract. */
export function HiringRoute() {
  const params = useSearchParams();
  const request = params.get("request");
  if (request) return <Workspace key={request} requestId={request} initialCandidate={params.get("candidate")} />;
  if (params.get("new")) return <NewRequest />;
  return <IndexView />;
}

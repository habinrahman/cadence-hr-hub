"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getDashboard, type Dashboard } from "@/lib/api";

export type DeskCounts = { decisions: number; reports: number; counts: Dashboard["counts"] } | null;

let cached: { at: number; value: DeskCounts } | null = null;
let inflight: Promise<DeskCounts> | null = null;

function load(force: boolean): Promise<DeskCounts> {
  if (!force && cached && Date.now() - cached.at < 5000) return Promise.resolve(cached.value);
  if (inflight) return inflight;
  inflight = getDashboard()
    .then((d) => {
      const c = d.counts;
      const value = {
        decisions:
          c.reviews_needing_attention ??
          c.relationship_reviews + c.requirements_awaiting_approval + c.matches_awaiting_review + c.shares_awaiting_approval,
        reports: c.open_problem_reports,
        counts: c,
      };
      cached = { at: Date.now(), value };
      return value;
    })
    .catch(() => null)
    .finally(() => {
      inflight = null;
    });
  return inflight;
}

/** Counts for the shell badges. Shared by the sidebar and header, refreshed on navigation. A failure shows no badge. */
export function useDeskCounts(): DeskCounts {
  const path = usePathname();
  const [value, setValue] = useState<DeskCounts>(cached?.value ?? null);
  useEffect(() => {
    let cancelled = false;
    load(false).then((next) => {
      if (!cancelled) setValue(next);
    });
    return () => {
      cancelled = true;
    };
  }, [path]);
  return value;
}

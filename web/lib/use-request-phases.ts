"use client";

import { useEffect, useState } from "react";
import { getHiringRequest, type ProcessingStage } from "@/lib/api";
import { requestPhase, type RequestPhase } from "@/lib/request-phase";

const CONCURRENCY = 4;

/**
 * The list endpoints give only the processing stage. A finished request needs its detail to say whether the pool is
 * provisional or confirmed, so only those are read, a few at a time. A row that could not be read stays unknown.
 */
export function useRequestPhases(rows: { id: string; processing: ProcessingStage | string }[]): Record<string, RequestPhase | null> {
  const [phases, setPhases] = useState<Record<string, RequestPhase | null>>({});
  const key = rows.map((r) => `${r.id}:${r.processing}`).join(",");

  useEffect(() => {
    let cancelled = false;
    const next: Record<string, RequestPhase | null> = {};
    const queue: string[] = [];
    for (const row of rows) {
      const phase = requestPhase(row.processing);
      if (phase !== null || row.processing !== "complete") next[row.id] = phase;
      else queue.push(row.id);
    }
    setPhases(next);
    if (queue.length === 0) return;

    async function worker() {
      while (queue.length > 0 && !cancelled) {
        const id = queue.shift()!;
        try {
          const detail = await getHiringRequest(id);
          if (!cancelled) setPhases((cur) => ({ ...cur, [id]: requestPhase(detail.processing.stage, detail) }));
        } catch {
          if (!cancelled) setPhases((cur) => ({ ...cur, [id]: null }));
        }
      }
    }
    void Promise.all(Array.from({ length: CONCURRENCY }, worker));
    return () => {
      cancelled = true;
    };
    // The key captures every row's id and stage.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return phases;
}

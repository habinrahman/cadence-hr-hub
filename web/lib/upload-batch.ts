import { ApiError, ConnectionError, FileReadError } from "./errors";

/** Why a file did not upload: no answer from the API, the file itself, or the server said no. */
export type FailureKind = "unreachable" | "unreadable" | "rejected" | "server" | "unexpected";

export type BatchFailure = { file: File; name: string; reason: string; kind: FailureKind };

export type BatchProgress = {
  total: number;
  done: number;
  /** Files the server accepted as new documents (queued for the worker). */
  created: number;
  /** Files whose identical bytes were already on record. Nothing new was created for them. */
  existing: number;
  failed: number;
};

export type BatchResult = BatchProgress & { failures: BatchFailure[] };

export const DEFAULT_CONCURRENCY = 4;

/** Folder pickers also return OS metadata files. They are not CVs and are not sent. */
export function isIgnored(name: string): boolean {
  const base = name.split(/[\\/]/).pop() ?? name;
  return base.startsWith(".") || base.startsWith("~$") || base.toLowerCase() === "thumbs.db" || base.toLowerCase() === "desktop.ini";
}

export function splitIgnored(files: File[]): { usable: File[]; ignored: File[] } {
  const usable: File[] = [];
  const ignored: File[] = [];
  for (const file of files) (isIgnored(file.name) ? ignored : usable).push(file);
  return { usable, ignored };
}

export function failureKind(error: unknown): FailureKind {
  if (error instanceof ConnectionError || error instanceof TypeError) return "unreachable";
  if (error instanceof FileReadError) return "unreadable";
  if (error instanceof ApiError) return error.status >= 500 ? "server" : "rejected";
  return "unexpected";
}

export function failureReason(error: unknown): string {
  if (error instanceof ConnectionError) return `Could not reach the API at ${error.url}`;
  if (error instanceof TypeError) return "Could not reach the API";
  if (error instanceof FileReadError) return "File could not be read from disk";
  if (error instanceof ApiError) {
    if (error.status === 415) return "File type not supported";
    if (error.status === 413) return "File too large";
    if (error.status === 401 || error.status === 403) return "Not allowed for this session";
    return error.code || `Server error (${error.status})`;
  }
  return error instanceof Error && error.message ? `Unexpected error: ${error.message}` : "Unexpected error";
}

/**
 * Sends files through `upload` with at most `concurrency` in flight. A failed file is recorded and the batch goes on.
 * Sending the same files again is safe: the server recognises identical bytes and creates nothing new.
 */
export async function uploadBatch(
  files: File[],
  upload: (file: File) => Promise<{ created: boolean }>,
  options: { concurrency?: number; onProgress?: (progress: BatchProgress) => void; signal?: AbortSignal } = {},
): Promise<BatchResult> {
  const concurrency = Math.max(1, Math.floor(options.concurrency ?? DEFAULT_CONCURRENCY));
  const state: BatchProgress = { total: files.length, done: 0, created: 0, existing: 0, failed: 0 };
  const failures: BatchFailure[] = [];
  let next = 0;

  const report = () => options.onProgress?.({ ...state });

  async function worker() {
    while (next < files.length && !options.signal?.aborted) {
      const file = files[next++];
      try {
        const result = await upload(file);
        if (result.created) state.created++;
        else state.existing++;
      } catch (error) {
        state.failed++;
        failures.push({ file, name: file.name, reason: failureReason(error), kind: failureKind(error) });
      }
      state.done++;
      report();
    }
  }

  report();
  await Promise.all(Array.from({ length: Math.min(concurrency, Math.max(files.length, 1)) }, worker));
  return { ...state, failures };
}

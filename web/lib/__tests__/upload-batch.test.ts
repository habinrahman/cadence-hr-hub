import { describe, it, expect } from "vitest";
import { ApiError, ConnectionError, FileReadError } from "@/lib/errors";
import { failureKind, failureReason, isIgnored, splitIgnored, uploadBatch, type BatchProgress } from "@/lib/upload-batch";

const file = (name: string) => new File(["x"], name);
const files = (n: number) => Array.from({ length: n }, (_, i) => file(`cv-${i}.pdf`));
const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe("uploadBatch", () => {
  it("never has more uploads in flight than the concurrency cap, and sends every file once", async () => {
    let inFlight = 0;
    let peak = 0;
    const sent: string[] = [];
    const result = await uploadBatch(
      files(23),
      async (f) => {
        inFlight++;
        peak = Math.max(peak, inFlight);
        sent.push(f.name);
        await tick();
        inFlight--;
        return { created: true };
      },
      { concurrency: 4 },
    );
    expect(peak).toBe(4);
    expect(new Set(sent).size).toBe(23);
    expect(result).toMatchObject({ total: 23, done: 23, created: 23, existing: 0, failed: 0 });
  });

  it("defaults to four at a time", async () => {
    let inFlight = 0;
    let peak = 0;
    await uploadBatch(files(12), async () => {
      inFlight++;
      peak = Math.max(peak, inFlight);
      await tick();
      inFlight--;
      return { created: true };
    });
    expect(peak).toBe(4);
  });

  it("reports progress after every file, ending at the total", async () => {
    const seen: BatchProgress[] = [];
    await uploadBatch(files(5), async () => ({ created: true }), { concurrency: 2, onProgress: (p) => seen.push(p) });
    expect(seen[0].done).toBe(0);
    expect(seen.at(-1)).toMatchObject({ total: 5, done: 5 });
    expect(seen.map((p) => p.done)).toEqual([...seen.map((p) => p.done)].sort((a, b) => a - b));
  });

  it("collects per-file failures with a reason and keeps going", async () => {
    const result = await uploadBatch(files(6), async (f) => {
      if (f.name === "cv-1.pdf") throw new ApiError(415, "unsupported_file");
      if (f.name === "cv-4.pdf") throw new ApiError(413, "file_too_large");
      if (f.name === "cv-5.pdf") throw new TypeError("Failed to fetch");
      return { created: true };
    });
    expect(result.done).toBe(6);
    expect(result.created).toBe(3);
    expect(result.failed).toBe(3);
    expect(Object.fromEntries(result.failures.map((f) => [f.name, f.reason]))).toEqual({
      "cv-1.pdf": "File type not supported",
      "cv-4.pdf": "File too large",
      "cv-5.pdf": "Could not reach the API",
    });
    expect(Object.fromEntries(result.failures.map((f) => [f.name, f.kind]))).toEqual({
      "cv-1.pdf": "rejected",
      "cv-4.pdf": "rejected",
      "cv-5.pdf": "unreachable",
    });
    expect(result.failures[0].file).toBeInstanceOf(File);
  });

  it("counts a repeat of already-stored files as existing, so a retry creates nothing new", async () => {
    const stored = new Set<string>();
    const upload = async (f: File) => {
      const created = !stored.has(f.name);
      stored.add(f.name);
      return { created };
    };
    const batch = files(8);
    const first = await uploadBatch(batch, upload);
    const again = await uploadBatch(batch, upload);
    expect(first).toMatchObject({ created: 8, existing: 0 });
    expect(again).toMatchObject({ created: 0, existing: 8, failed: 0 });
    expect(stored.size).toBe(8);
  });

  it("handles an empty batch and a cap larger than the batch", async () => {
    expect(await uploadBatch([], async () => ({ created: true }))).toMatchObject({ total: 0, done: 0 });
    expect(await uploadBatch(files(2), async () => ({ created: true }), { concurrency: 50 })).toMatchObject({ done: 2 });
  });

  it("stops picking up new files once aborted", async () => {
    const controller = new AbortController();
    const result = await uploadBatch(
      files(10),
      async () => {
        controller.abort();
        return { created: true };
      },
      { concurrency: 1, signal: controller.signal },
    );
    expect(result.done).toBe(1);
  });
});

describe("folder selection", () => {
  it("ignores operating system files but not CVs", () => {
    expect(isIgnored(".DS_Store")).toBe(true);
    expect(isIgnored("Thumbs.db")).toBe(true);
    expect(isIgnored("~$draft.docx")).toBe(true);
    expect(isIgnored("Resume FALL 2025 - Arnav Sharma.pdf")).toBe(false);
    const { usable, ignored } = splitIgnored([file("a.pdf"), file(".DS_Store"), file("b.docx")]);
    expect(usable.map((f) => f.name)).toEqual(["a.pdf", "b.docx"]);
    expect(ignored).toHaveLength(1);
  });

  it("explains failures in plain words", () => {
    expect(failureReason(new ApiError(403, "recruiter_required"))).toBe("Not allowed for this session");
    expect(failureReason(new ApiError(500, "boom"))).toBe("boom");
    expect(failureReason(new Error("x"))).toBe("Unexpected error: x");
  });

  it("never calls a failure a generic network error, and tells the causes apart", () => {
    const down = new ConnectionError("http://localhost:8000", "no response");
    expect(failureReason(down)).toBe("Could not reach the API at http://localhost:8000");
    expect(failureKind(down)).toBe("unreachable");
    expect(failureReason(new FileReadError("a.pdf"))).toBe("File could not be read from disk");
    expect(failureKind(new FileReadError("a.pdf"))).toBe("unreadable");
    expect(failureKind(new ApiError(500, "boom"))).toBe("server");
    expect(failureKind(new ApiError(415, "unsupported_file"))).toBe("rejected");
    expect(failureKind(new Error("x"))).toBe("unexpected");
    for (const e of [down, new FileReadError("a"), new ApiError(500, "b"), new Error("x"), new TypeError("f")]) expect(failureReason(e)).not.toMatch(/^Network error$/);
  });

  it("counts a total outage as every file failed and none accepted", async () => {
    const result = await uploadBatch(files(488), async () => {
      throw new ConnectionError("http://localhost:8000");
    });
    expect(result).toMatchObject({ total: 488, done: 488, created: 0, existing: 0, failed: 488 });
    expect(result.failures.every((f) => f.kind === "unreachable")).toBe(true);
  });

  it("retries only the failed files after an outage, with accurate counts", async () => {
    let up = false;
    const stored = new Set<string>();
    const upload = async (f: File) => {
      if (!up) throw new ConnectionError("http://localhost:8000");
      const created = !stored.has(f.name);
      stored.add(f.name);
      return { created };
    };
    const batch = files(9);
    const first = await uploadBatch(batch, upload);
    expect(first).toMatchObject({ created: 0, existing: 0, failed: 9 });
    up = true;
    const retry = await uploadBatch(first.failures.map((f) => f.file), upload);
    expect(retry).toMatchObject({ total: 9, created: 9, existing: 0, failed: 0 });
    expect(stored.size).toBe(9);
  });
});

"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { checkApiReachable, getDemoStatus, uploadDocument, type DemoStatus } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { plural } from "@/lib/format";
import { RELATIONSHIP_LABELS } from "@/lib/labels";
import { splitIgnored, uploadBatch, type BatchFailure, type BatchProgress } from "@/lib/upload-batch";
import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icons";
import { PageHeader, Panel, PanelHeader } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { ErrorState, Notice } from "@/components/ui/states";
import { ResetPanel } from "./reset-panel";

const POLL_MS = 2500;
/** "failed" means the server accepted none of the files, so nothing is being processed. */
type Phase = "idle" | "uploading" | "processing" | "done" | "failed";

export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return minutes > 0 ? `${minutes} min ${String(seconds).padStart(2, "0")} s` : `${seconds} s`;
}

function Stat({ label, value, note, tone }: { label: string; value: number | string; note?: string; tone?: "bad" | "warn" }) {
  const color = tone === "bad" ? "text-bad-ink" : tone === "warn" ? "text-prop-ink" : "text-ink";
  return (
    <div className="bg-panel px-5 py-4">
      <p className="text-[13px] text-mut">{label}</p>
      <p className={`mt-0.5 text-[24px] font-semibold leading-tight tracking-tight tabular-nums ${color}`}>{value}</p>
      {note ? <p className="mt-1 font-mono text-[11px] text-mut">{note}</p> : null}
    </div>
  );
}

export function DemoData() {
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [statusError, setStatusError] = useState<unknown>(null);
  const [pollHalted, setPollHalted] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [files, setFiles] = useState<File[]>([]);
  const [ignored, setIgnored] = useState(0);
  const [progress, setProgress] = useState<BatchProgress | null>(null);
  const [failures, setFailures] = useState<BatchFailure[]>([]);
  const [apiProblem, setApiProblem] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef<number | null>(null);
  const folderInput = useRef<HTMLInputElement | null>(null);
  // The input only exists once the status has loaded, so the directory flag is set when it mounts.
  const folderRef = useCallback((node: HTMLInputElement | null) => {
    folderInput.current = node;
    node?.setAttribute("webkitdirectory", "");
  }, []);
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async (haltOnError = false) => {
    try {
      setStatus(await getDemoStatus());
      setStatusError(null);
      setPollHalted(false);
    } catch (reason) {
      setStatusError(reason);
      // A failed background poll must not keep hammering the API; the error UI offers a manual retry.
      if (haltOnError) setPollHalted(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Live counts and a running clock while anything is being uploaded or read.
  useEffect(() => {
    if (phase !== "uploading" && phase !== "processing") return;
    if (pollHalted) return;
    const poll = setInterval(() => void refresh(true), POLL_MS);
    const tick = setInterval(() => startedAt.current && setElapsed(Date.now() - startedAt.current), 500);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
    };
  }, [phase, refresh, pollHalted]);

  // Uploads are finished; the batch is done when the worker has nothing left to read.
  useEffect(() => {
    if (phase === "processing" && status && status.processing === 0 && status.open_jobs === 0) {
      if (startedAt.current) setElapsed(Date.now() - startedAt.current);
      setPhase("done");
    }
  }, [phase, status]);

  function choose(list: FileList | null) {
    const { usable, ignored: skipped } = splitIgnored(Array.from(list ?? []));
    setFiles(usable);
    setIgnored(skipped.length);
    setProgress(null);
    setFailures([]);
    setApiProblem(null);
    setPhase("idle");
  }

  /** `base` is what earlier attempts already achieved. It is null for a fresh batch. */
  async function send(batch: File[], base: BatchProgress | null) {
    setApiProblem(null);
    try {
      await checkApiReachable();
    } catch (reason) {
      // Nothing is sent and nothing is claimed: the files stay selected so the same click can be repeated.
      setApiProblem(reason instanceof Error ? reason.message : "Could not reach the API");
      return;
    }
    if (base === null) startedAt.current = Date.now();
    setPhase("uploading");
    const result = await uploadBatch(batch, uploadDocument, {
      onProgress: (p) =>
        setProgress(
          base
            ? { total: base.total, done: base.done + p.done, created: base.created + p.created, existing: base.existing + p.existing, failed: p.failed }
            : p,
        ),
    });
    setFailures(result.failures);
    await refresh();
    const accepted = (base ? base.created + base.existing : 0) + result.created + result.existing;
    if (accepted === 0) {
      if (startedAt.current) setElapsed(Date.now() - startedAt.current);
      setPhase("failed");
      return;
    }
    setPhase("processing");
  }

  const start = () => void send(files, null);
  const retry = () => {
    if (!progress) return;
    void send(
      failures.map((f) => f.file),
      { ...progress, done: progress.done - progress.failed, failed: 0 },
    );
  };

  const busy = phase === "uploading";
  const inFlight = phase === "uploading" || phase === "processing";
  const read = status ? status.documents - status.processing : 0;
  const notUploaded = progress?.failed ?? 0;
  const reasons = Object.entries(
    failures.reduce<Record<string, number>>((acc, f) => ({ ...acc, [f.reason]: (acc[f.reason] ?? 0) + 1 }), {}),
  ).sort((a, b) => b[1] - a[1]);
  const nothingReached = failures.length > 0 && failures.every((f) => f.kind === "unreachable");

  return (
    <>
      <PageHeader
        eyebrow="Setup"
        title="Set up Candidate Repository"
        sub="Import the existing CV files to create your candidate database. Each CV becomes a candidate profile, or is recognised as an update or duplicate of someone already imported. Ambiguous cases go to HR Review. Every count below comes from the running system."
      />

      {statusError instanceof ApiError && statusError.status === 404 ? (
        <Notice tone="warn">Repository setup tools are only available when the API runs with ENVIRONMENT=local.</Notice>
      ) : statusError ? (
        <ErrorState error={statusError} onRetry={() => void refresh()} />
      ) : null}
      {!status && !statusError ? (
        <div aria-busy="true" aria-label="Loading repository status">
          <PanelSkeleton rows={3} />
        </div>
      ) : null}

      {status ? (
        <div className="space-y-6">
          <Panel as="section">
            <PanelHeader eyebrow="Initial import" title="Import CVs" />
            <div className="space-y-4 px-5 py-4">
              <p className="text-[14px]">
                Add the existing CV repository to Cadence. Each CV goes through the normal intake pipeline (<span className="font-mono text-[12.5px]">POST /documents</span>) and is read by the worker, four at a time. Importing the same file
                again does not create a second document, job or candidate.
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <input ref={folderRef} type="file" multiple hidden aria-label="Choose CV folder" onChange={(e) => choose(e.target.files)} />
                <input ref={fileInput} type="file" multiple hidden aria-label="Choose CV files" onChange={(e) => choose(e.target.files)} />
                <Button disabled={inFlight} onClick={() => folderInput.current?.click()}>
                  <Icon name="upload" size={16} /> Choose CV folder
                </Button>
                <Button disabled={inFlight} onClick={() => fileInput.current?.click()}>
                  Choose files
                </Button>
                <p className="text-[14px]" aria-live="polite">
                  {files.length > 0 ? `${plural(files.length, "CV")} selected` : "No files selected"}
                  {ignored > 0 ? <span className="text-mut"> · {plural(ignored, "system file")} ignored</span> : null}
                </p>
                <Button variant="primary" disabled={files.length === 0 || inFlight} busy={busy} onClick={start}>
                  Import CVs
                </Button>
              </div>

              {apiProblem ? (
                <div role="alert" className="border border-bad-ink/40 bg-bad-bg px-4 py-3 text-[13px]">
                  <p className="font-semibold text-bad-ink">The API is not reachable. Nothing was uploaded.</p>
                  <p className="mt-1 break-words">{apiProblem}</p>
                  <p className="mt-1 text-mut">Your files are still selected. Start or restart the API, then click Import again.</p>
                </div>
              ) : null}

              {progress ? (
                <div aria-live="polite" className="space-y-3 border-t border-rule pt-4" aria-label="This upload">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <p className="text-[15px] font-semibold">
                      
                      <span className={phase === "failed" || (phase === "done" && notUploaded > 0) ? "text-bad-ink" : undefined}>
                        {phase === "uploading"
                          ? "Importing CVs…"
                          : phase === "processing"
                            ? "Building candidate profiles. Extracting candidate information and checking for existing profiles."
                            : phase === "failed"
                              ? "Upload failed. The server accepted none of these files."
                              : notUploaded > 0
                                ? `Finished with ${plural(notUploaded, "file")} not uploaded`
                                : "Import complete"}
                      </span>
                    </p>
                    {phase !== "idle" ? (
                      <p className="font-mono text-[12px] text-mut">
                        {phase === "done" || phase === "failed" ? "Total time" : "Elapsed"}: {formatElapsed(elapsed)}
                      </p>
                    ) : null}
                  </div>
                  <div className="h-2 border border-rule bg-inset" role="progressbar" aria-label="Upload progress" aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.done}>
                    <div className="h-full bg-human" style={{ width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%` }} />
                  </div>
                  <div className="grid grid-cols-2 gap-px border border-rule bg-rule lg:grid-cols-4" aria-label="Counts for this upload only">
                    <Stat label="CVs selected" value={progress.total} note={`${progress.done} of ${progress.total} sent`} />
                    <Stat label="Accepted as new" value={progress.created} note="Queued for the worker" />
                    <Stat label="Already on record" value={progress.existing} note="Identical file, nothing new" />
                    <Stat label="Upload failed" value={progress.failed} tone={progress.failed > 0 ? "bad" : undefined} />
                  </div>
                </div>
              ) : null}

              {failures.length > 0 && !busy ? (
                <div role="alert" className="border border-bad-ink/40 bg-bad-bg px-4 py-3 text-[13px]">
                  <p className="font-semibold text-bad-ink">{plural(failures.length, "file")} did not upload</p>
                  <ul className="mt-1.5 space-y-0.5" aria-label="Reasons">
                    {reasons.map(([reason, count]) => (
                      <li key={reason} className="break-words">
                        {count} × {reason}
                      </li>
                    ))}
                  </ul>
                  {nothingReached ? <p className="mt-1.5 text-mut">No request reached the server. Check the API is running, then retry. Nothing was lost.</p> : null}
                  <ul className="mt-2 max-h-40 space-y-0.5 overflow-y-auto border-t border-bad-ink/20 pt-2" aria-label="Files that did not upload">
                    {failures.map((f, i) => (
                      <li key={`${f.name}-${i}`} className="break-words">
                        {f.name}: <span className="text-mut">{f.reason}</span>
                      </li>
                    ))}
                  </ul>
                  <Button className="mt-3" onClick={retry}>
                    Retry {plural(failures.length, "failed file")}
                  </Button>
                </div>
              ) : null}
            </div>
          </Panel>

          <Panel as="section">
            <PanelHeader eyebrow="Whole database" title="Candidate Repository" />
            <div className="grid grid-cols-[minmax(0,1fr)] gap-px border-b border-rule bg-rule sm:grid-cols-2 lg:grid-cols-4" aria-label="Counts from the running system">
              <Stat label="Documents" value={status.documents} />
              <Stat label="Read so far" value={read} note={status.processing > 0 ? `${status.processing} still queued or reading` : "Nothing waiting"} />
              <Stat label="Candidates" value={status.candidates} />
              <Stat label="Reviews required" value={status.pending_reviews} note="Duplicate or update, awaiting a person" tone={status.pending_reviews > 0 ? "warn" : undefined} />
              <Stat label="Need OCR" value={status.needs_ocr} note="No text layer" tone={status.needs_ocr > 0 ? "warn" : undefined} />
              <Stat label="Quarantined" value={status.quarantined} tone={status.quarantined > 0 ? "bad" : undefined} />
              <Stat label="Processing failed" value={status.failed} tone={status.failed > 0 ? "bad" : undefined} />
            </div>
            {Object.keys(status.identity_outcomes).length > 0 ? (
              <ul className="space-y-1 px-5 py-4 text-[13.5px]" aria-label="How each CV was matched to a profile">
                {Object.entries(status.identity_outcomes)
                  .sort((a, b) => b[1] - a[1])
                  .map(([code, count]) => (
                    <li key={code} className="flex justify-between gap-4">
                      <span>{RELATIONSHIP_LABELS[code] ?? code.replaceAll("_", " ")}</span>
                      <span className="font-mono tabular-nums">{count}</span>
                    </li>
                  ))}
              </ul>
            ) : null}
            <p className="border-t border-rule px-5 py-3 text-[12.5px] text-mut">
              These totals cover everything in the database, including documents loaded before this upload. They do not show whether this upload worked; see "This upload" above. Review individual CVs in <Link href="/intake">CV Intake</Link> and decisions in the{" "}
              <Link href="/queue">Review queue</Link>.
            </p>
          </Panel>

          <ResetPanel
            lastResetAt={status.last_reset_at}
            disabled={inFlight}
            onDone={() => {
              setFiles([]);
              setProgress(null);
              setFailures([]);
              setApiProblem(null);
              setPhase("idle");
              startedAt.current = null;
              setElapsed(0);
              void refresh();
            }}
          />
        </div>
      ) : null}
    </>
  );
}

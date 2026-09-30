"use client";

import { useEffect, useState } from "react";
import { approveShare, getSharePreview, sendShare, type SharePreview, type ShareRecord } from "@/lib/api";
import { shortDateTime } from "@/lib/format";
import { labelAudit } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, SlideOver } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState, Notice } from "@/components/ui/states";
import { Tag } from "@/components/ui/tag";
import { useToast } from "@/components/ui/toast";

/**
 * Sharing is two separate human steps: approve, then send. Nothing leaves Cadence until Send is confirmed.
 */
export function SharePanel({
  requestId,
  candidateId,
  candidateName,
  onClose,
  onChanged,
}: {
  requestId: string;
  candidateId: string | null;
  candidateName: string | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { notify } = useToast();
  const [preview, setPreview] = useState<SharePreview | null>(null);
  const [result, setResult] = useState<ShareRecord | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<"approve" | "send" | null>(null);

  useEffect(() => {
    if (!candidateId) return;
    let cancelled = false;
    setPreview(null);
    setResult(null);
    setError(null);
    setLoading(true);
    getSharePreview(requestId, candidateId)
      .then((p) => {
        if (cancelled) return;
        setPreview(p);
        setResult(p.sharing);
      })
      .catch((reason) => {
        if (!cancelled) setError(reason);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [requestId, candidateId]);

  async function approve() {
    if (!candidateId) return;
    setConfirm(null);
    setBusy(true);
    setError(null);
    try {
      await approveShare(requestId, candidateId);
      setPreview((current) => (current ? { ...current, approved: true } : current));
      notify("Share approved. Sending is a separate step.");
      onChanged();
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!candidateId) return;
    setConfirm(null);
    setBusy(true);
    setError(null);
    try {
      setResult(await sendShare(requestId, candidateId));
      notify("Share sent");
      onChanged();
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }

  const sent = result?.status === "sent";
  const name = preview?.candidate ?? candidateName ?? "this candidate";

  return (
    <SlideOver open={candidateId !== null} title={`Share review · ${candidateName ?? "candidate"}`} onClose={onClose}>
      {loading ? <Skeleton lines={6} /> : null}
      {error ? <ErrorState error={error} /> : null}
      {preview ? (
        <div className="space-y-5">
          <section aria-label="What leaves Cadence">
            <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-human-ink">What leaves Cadence</h3>
            <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1.5">
              <dt className="text-mut">Company</dt>
              <dd className="break-words font-semibold">{preview.company}</dd>
              <dt className="text-mut">Recipient</dt>
              <dd className="break-all font-mono text-[13px]">{preview.recipient}</dd>
              <dt className="text-mut">Candidate</dt>
              <dd className="break-words font-semibold">{preview.candidate}</dd>
              <dt className="text-mut">Role</dt>
              <dd className="break-words">{preview.role}</dd>
              <dt className="text-mut">Latest title</dt>
              <dd>{preview.selected.title ?? "Not recorded"}</dd>
              <dt className="text-mut">Experience</dt>
              <dd>{preview.selected.years_of_experience === null ? "Not recorded" : `${preview.selected.years_of_experience} years`}</dd>
              <dt className="text-mut">Skills</dt>
              <dd className="break-words">{preview.selected.skills.length ? preview.selected.skills.join(", ") : "None recorded"}</dd>
            </dl>
            <p className="mt-3 rounded border border-rule bg-inset px-3 py-2 text-[13px]">
              <strong>Not included:</strong> email address, phone number and the CV file.
            </p>
          </section>

          <section aria-label="Approval">
            <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-human-ink">Decision</h3>
            <ol className="space-y-3">
              <li className="flex flex-wrap items-center gap-3">
                <span className="w-24 font-semibold">1. Approve</span>
                {preview.approved ? (
                  <Tag tone="decided">Approved</Tag>
                ) : (
                  <Button variant="primary" busy={busy} onClick={() => setConfirm("approve")}>
                    Approve share…
                  </Button>
                )}
              </li>
              <li className="flex flex-wrap items-center gap-3">
                <span className="w-24 font-semibold">2. Send</span>
                {sent ? (
                  <Tag tone="ok">Sent</Tag>
                ) : (
                  <Button variant="primary" busy={busy} disabled={!preview.approved} onClick={() => setConfirm("send")}>
                    Send email…
                  </Button>
                )}
                {!preview.approved && !sent ? <span className="text-xs text-mut">Approve first.</span> : null}
              </li>
            </ol>
          </section>

          {sent && result ? (
            <section aria-label="Record of this share">
              <Notice>This share was sent. The record below comes from the server.</Notice>
              <dl className="mt-3 grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1.5 text-[13px]">
                <dt className="text-mut">Status</dt>
                <dd>{result.status}</dd>
                <dt className="text-mut">Recipient</dt>
                <dd className="break-all font-mono">{result.recipient ?? "—"}</dd>
                <dt className="text-mut">Sent</dt>
                <dd>{shortDateTime(result.sent_at)}</dd>
                <dt className="text-mut">Sender</dt>
                <dd>{result.sender ?? "—"}</dd>
                <dt className="text-mut">Destination</dt>
                <dd className="font-mono">{result.destination}</dd>
                <dt className="text-mut">Audit</dt>
                <dd>{result.audit ? labelAudit(result.audit.action) : "No audit row found"}</dd>
              </dl>
            </section>
          ) : null}
        </div>
      ) : null}

      <ConfirmDialog
        open={confirm === "approve"}
        title="Approve this share?"
        body={
          <p>
            Approve sharing <strong>{name}</strong> with <strong>{preview?.company}</strong> ({preview?.recipient}). Approving does not send
            anything.
          </p>
        }
        confirmLabel="Approve share"
        busy={busy}
        onConfirm={approve}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmDialog
        open={confirm === "send"}
        title="Send this share now?"
        body={
          <p>
            An email about <strong>{name}</strong> goes to <strong className="break-all">{preview?.recipient}</strong>. This cannot be undone.
          </p>
        }
        confirmLabel="Send email"
        tone="danger"
        busy={busy}
        onConfirm={send}
        onCancel={() => setConfirm(null)}
      />
    </SlideOver>
  );
}

"use client";

import { useEffect, useState } from "react";
import { approveShare, getSharePreview, sendShare, setRequestContact, type SharePreview, type ShareRecord } from "@/lib/api";
import { shortDateTime } from "@/lib/format";
import { labelAudit } from "@/lib/labels";
import { Button } from "@/components/ui/button";
import { inputClass } from "@/components/ui/field";
import { SlideOver } from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState, Notice } from "@/components/ui/states";
import { Tag } from "@/components/ui/tag";
import { useToast } from "@/components/ui/toast";

/**
 * One human decision on one screen: review what leaves Cadence, then "Approve & send". The button is the confirmation, and
 * the sentence beside it says what it does, so there is no second dialog. The server still records the approval and the
 * send separately (and refuses a send without an approval), so nothing leaves Cadence unless a recruiter clicked it.
 * If the approval was recorded but the mail did not go out, the same button offers "Send email" again.
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
  const [contact, setContact] = useState("");

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

  async function approveAndSend() {
    if (!candidateId) return;
    setBusy(true);
    setError(null);
    let recorded = preview?.approved === true;
    try {
      if (!recorded) {
        await approveShare(requestId, candidateId);
        recorded = true;
        setPreview((current) => (current ? { ...current, approved: true } : current));
      }
      setResult(await sendShare(requestId, candidateId));
      notify("Share approved and sent");
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
      // Tell the page only what the server now holds: an approval that was recorded, even if the mail failed.
      if (recorded) onChanged();
    }
  }

  async function saveContact() {
    setBusy(true);
    setError(null);
    try {
      const saved = await setRequestContact(requestId, contact.trim());
      setPreview((current) => (current ? { ...current, recipient: saved.contact_email } : current));
      notify("Company contact saved");
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
              <dd className="break-all font-mono text-[13px]">
                {preview.recipient ?? <span className="font-sans font-semibold text-bad-ink">Not set yet</span>}
              </dd>
              <dt className="text-mut">Candidate</dt>
              <dd className="break-words font-semibold">{preview.candidate}</dd>
              <dt className="text-mut">Role</dt>
              <dd className="break-words">{preview.role}</dd>
              <dt className="text-mut">Experience</dt>
              <dd>{preview.selected.years_of_experience === null ? "Not recorded" : `${preview.selected.years_of_experience} years`}</dd>
              <dt className="text-mut">Requirements met</dt>
              <dd className="break-words">
                {preview.selected.requirements_met.length ? preview.selected.requirements_met.join(", ") : "None recorded"}
              </dd>
            </dl>
            <p className="mt-3 rounded border border-rule bg-inset px-3 py-2 text-[13px]">
              <strong>Not included:</strong> email address, phone number, the CV file, and anything else on the CV (such
              as hobbies or other skills).
            </p>
          </section>

          <section aria-label="Approval">
            <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-human-ink">Decision</h3>
            {sent ? (
              <p>
                <Tag tone="ok">Sent</Tag>
              </p>
            ) : !preview.recipient ? (
              <form
                className="space-y-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  void saveContact();
                }}
              >
                <label htmlFor="share-contact" className="block text-[13.5px]">
                  Who at <strong className="break-words">{preview.company}</strong> receives this shortlist? Nothing can be sent
                  until you name the company contact.
                </label>
                <input
                  id="share-contact"
                  type="email"
                  className={inputClass}
                  value={contact}
                  placeholder="hiring@company.com"
                  onChange={(e) => setContact(e.target.value)}
                />
                <Button type="submit" busy={busy} disabled={!contact.trim()}>
                  Save company contact
                </Button>
              </form>
            ) : (
              <div className="space-y-3">
                <p className="text-[13.5px]">
                  {preview.approved ? (
                    <>Your approval is already recorded. </>
                  ) : (
                    <>Approving records your decision. </>
                  )}
                  An email about <strong className="break-words">{name}</strong> goes to{" "}
                  <strong className="break-words">{preview.recipient}</strong> now. This cannot be undone.
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <Button variant="primary" size="lg" busy={busy} onClick={approveAndSend}>
                    {preview.approved ? "Send email" : "Approve & send"}
                  </Button>
                  {preview.approved ? <Tag tone="decided">Approved, not sent yet</Tag> : null}
                </div>
              </div>
            )}
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

    </SlideOver>
  );
}

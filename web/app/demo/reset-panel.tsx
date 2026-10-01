"use client";

import { useState } from "react";
import { resetDemoData } from "@/lib/api";
import { shortDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, inputClass } from "@/components/ui/field";
import { Panel, PanelHeader } from "@/components/ui/panel";
import { ErrorState } from "@/components/ui/states";

export const RESET_PHRASE = "RESET";

export function phraseMatches(typed: string): boolean {
  return typed.trim() === RESET_PHRASE;
}

/** Wipes candidates, CVs, requests, matches, reviews and shares. Users, sign-in and the audit trail stay. */
export function ResetPanel({ lastResetAt, disabled, onDone }: { lastResetAt: string | null; disabled: boolean; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [resetAt, setResetAt] = useState<string | null>(null);

  function close() {
    setOpen(false);
    setTyped("");
  }

  async function confirm() {
    if (!phraseMatches(typed)) return;
    setBusy(true);
    setError(null);
    try {
      const result = await resetDemoData();
      setResetAt(result.reset_at);
      close();
      onDone();
    } catch (reason) {
      setError(reason);
    } finally {
      setBusy(false);
    }
  }

  const shown = resetAt ?? lastResetAt;
  return (
    <Panel as="section" className="border-bad-ink/40">
      <PanelHeader eyebrow="Danger zone" title="Reset candidate repository" />
      <div className="space-y-4 px-5 py-4 text-[14px]">
        <p>
          Removes every candidate, CV, application, hiring request, match, review, shortlist and share, so the repository starts empty. Users, sign-in and configuration
          are kept. The audit trail is never deleted, and the reset itself is recorded in it as <span className="font-mono text-[12.5px]">demo_reset</span>.
        </p>
        {error ? <ErrorState error={error} /> : null}
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="danger" disabled={disabled} onClick={() => setOpen(true)}>
            Reset candidate repository…
          </Button>
          <p className="text-[12.5px] text-mut" aria-live="polite">
            {shown ? `Last reset: ${shortDateTime(shown)}` : "No reset recorded yet."}
            {disabled ? " Wait for the upload to finish first." : ""}
          </p>
        </div>
      </div>
      <ConfirmDialog
        open={open}
        title="Reset the whole candidate repository?"
        tone="danger"
        confirmLabel="Reset candidate repository"
        busy={busy}
        confirmDisabled={!phraseMatches(typed)}
        onConfirm={confirm}
        onCancel={close}
        body={
          <div className="space-y-3">
            <p>This deletes every candidate, CV and request in this repository. It cannot be undone. The audit trail is kept.</p>
            <Field label={`Type ${RESET_PHRASE} to confirm`}>
              {({ id, describedBy }) => (
                <input
                  id={id}
                  aria-describedby={describedBy}
                  className={inputClass}
                  autoComplete="off"
                  value={typed}
                  onChange={(event) => setTyped(event.target.value)}
                />
              )}
            </Field>
          </div>
        }
      />
    </Panel>
  );
}

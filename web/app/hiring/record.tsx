"use client";

import { useState } from "react";
import { addRequestAttachment, addRequestNote, type HiringRequestDetail, type RequestNote } from "@/lib/api";
import { fileSize, shortDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Field, inputClass } from "@/components/ui/field";
import { Panel, PanelRow, SectionLabel } from "@/components/ui/panel";
import { ErrorState } from "@/components/ui/states";
import { useToast } from "@/components/ui/toast";

type Kind = "notes" | "updates" | "next-steps";

function who(note: RequestNote, viewerId: string | null) {
  if (!viewerId) return "A recruiter";
  return note.author_user_id === viewerId ? "You" : "Another recruiter";
}

export function RequestRecord({
  detail,
  viewerId,
  onChanged,
}: {
  detail: HiringRequestDetail;
  viewerId: string | null;
  onChanged: () => void;
}) {
  return (
    <div className="space-y-5">
      <section aria-label="Description">
        <SectionLabel>Description</SectionLabel>
        <Panel>
          <PanelRow>
            <p className="max-h-56 overflow-y-auto whitespace-pre-wrap break-words">{detail.description}</p>
          </PanelRow>
        </Panel>
      </section>
      <NoteSection title="Next steps" kind="next-steps" items={detail.next_steps} requestId={detail.id} viewerId={viewerId} onChanged={onChanged} />
      <NoteSection title="Updates" kind="updates" items={detail.updates} requestId={detail.id} viewerId={viewerId} onChanged={onChanged} />
      <NoteSection title="Notes" kind="notes" items={detail.notes} requestId={detail.id} viewerId={viewerId} onChanged={onChanged} />
      <Files detail={detail} onChanged={onChanged} />
    </div>
  );
}

function NoteSection({
  title,
  kind,
  items,
  requestId,
  viewerId,
  onChanged,
}: {
  title: string;
  kind: Kind;
  items: RequestNote[];
  requestId: string;
  viewerId: string | null;
  onChanged: () => void;
}) {
  const { notify } = useToast();
  const [open, setOpen] = useState(false);
  const [body, setBody] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (!body.trim()) {
      setFieldError("Write something first.");
      return;
    }
    setFieldError(null);
    setBusy(true);
    setFailure(null);
    try {
      await addRequestNote(requestId, kind, body.trim());
      setBody("");
      setOpen(false);
      notify(`${title.replace(/s$/, "")} added`);
      onChanged();
    } catch (reason) {
      setFailure(reason);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label={title}>
      <div className="flex items-center justify-between">
        <SectionLabel>
          {title} ({items.length})
        </SectionLabel>
        <Button variant="quiet" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Cancel" : "+ Add"}
        </Button>
      </div>
      {open ? (
        <form onSubmit={add} className="mb-2 space-y-2" noValidate>
          <Field label={`New ${title.toLowerCase().replace(/s$/, "")}`} error={fieldError}>
            {({ id, describedBy, invalid }) => (
              <textarea id={id} aria-describedby={describedBy} aria-invalid={invalid} className={`${inputClass} min-h-20`} value={body} onChange={(e) => setBody(e.target.value)} />
            )}
          </Field>
          {failure ? <ErrorState error={failure} /> : null}
          <Button type="submit" variant="primary" busy={busy}>
            Save
          </Button>
        </form>
      ) : null}
      {items.length === 0 ? (
        <p className="text-mut">None yet.</p>
      ) : (
        <Panel>
          {items.map((n) => (
            <PanelRow key={n.id}>
              <p className="whitespace-pre-wrap break-words">{n.body}</p>
              <p className="mt-0.5 text-xs text-mut">
                {who(n, viewerId)} · {shortDate(n.created_at)}
              </p>
            </PanelRow>
          ))}
        </Panel>
      )}
    </section>
  );
}

function Files({ detail, onChanged }: { detail: HiringRequestDetail; onChanged: () => void }) {
  const { notify } = useToast();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);

  async function upload(file: File) {
    setBusy(true);
    setFailure(null);
    try {
      await addRequestAttachment(detail.id, file);
      notify("File uploaded");
      onChanged();
    } catch (reason) {
      setFailure(reason);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Files">
      <SectionLabel>Files ({detail.attachments.length})</SectionLabel>
      {detail.attachments.length === 0 ? (
        <p className="text-mut">None yet.</p>
      ) : (
        <Panel>
          {detail.attachments.map((a) => (
            <PanelRow key={a.id}>
              <p className="break-all font-mono text-[12px] font-semibold">{a.filename}</p>
              <p className="text-xs text-mut">
                {a.media_type} · {fileSize(a.byte_size)}
              </p>
            </PanelRow>
          ))}
        </Panel>
      )}
      <label className="mt-2 inline-flex min-h-11 cursor-pointer items-center rounded border border-rule-strong bg-panel px-3 text-[13px] font-semibold focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-human hover:bg-inset sm:min-h-8">
        {busy ? "Uploading…" : "Upload a file"}
        <input
          type="file"
          className="sr-only"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
            event.target.value = "";
          }}
        />
      </label>
      <p className="mt-1 text-xs text-mut">Files are listed only. Downloading them is not available in this version.</p>
      {failure ? <div className="mt-2"><ErrorState error={failure} /></div> : null}
    </section>
  );
}

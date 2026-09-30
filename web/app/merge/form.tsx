"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { type MergePreview, confirmMerge, previewMerge, searchCandidates } from "@/lib/api";
import { ApiError } from "@/lib/errors";
import { plural } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Field, inputClass } from "@/components/ui/field";
import { PageHeader, Panel, PanelRow } from "@/components/ui/panel";
import { ErrorState, Notice } from "@/components/ui/states";
import { Tag } from "@/components/ui/tag";
import { useToast } from "@/components/ui/toast";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Picked = { id: string; name: string | null } | null;

export function MergeDesk() {
  const params = useSearchParams();
  const { notify } = useToast();
  const [left, setLeft] = useState<Picked>(() => (params.get("left") ? { id: params.get("left")!, name: null } : null));
  const [right, setRight] = useState<Picked>(() => (params.get("right") ? { id: params.get("right")!, name: null } : null));
  const [selectionError, setSelectionError] = useState<string | null>(null);
  const [preview, setPreview] = useState<MergePreview | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  async function onPreview(event: React.FormEvent) {
    event.preventDefault();
    if (!left || !right) {
      setSelectionError("Choose both profiles.");
      return;
    }
    if (left.id === right.id) {
      setSelectionError("Choose two different profiles.");
      return;
    }
    setSelectionError(null);
    setBusy(true);
    setFailure(null);
    setNotice(null);
    setPreview(null);
    try {
      setPreview(await previewMerge(left.id, right.id));
    } catch (reason) {
      setFailure(reason);
    } finally {
      setBusy(false);
    }
  }

  async function onConfirm() {
    if (!left || !right) return;
    setConfirming(false);
    setBusy(true);
    setFailure(null);
    try {
      const merged = await confirmMerge(left.id, right.id);
      setPreview(merged);
      const survivor = merged.profiles.find((item) => item.id === merged.survivor_id);
      setNotice(`Profiles joined. The kept profile is ${survivor?.display_name ?? "the older profile"}.`);
      notify("Profiles merged");
    } catch (reason) {
      setFailure(reason);
    } finally {
      setBusy(false);
    }
  }

  const survivor = preview?.profiles.find((p) => p.id === preview.survivor_id);
  const absorbed = preview?.profiles.find((p) => p.id === preview.absorbed_id);
  const alreadyMerged = preview ? preview.profiles.some((p) => p.merged_into_id) : false;

  return (
    <>
      <PageHeader
        hue="candidate"
        title="Merge two profiles"
        sub="Preview both profiles, then confirm. The older profile is kept. Documents and applications stay on record."
      />

      <Panel as="section" className="max-w-3xl p-5">
        <form onSubmit={onPreview} noValidate className="space-y-4">
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-2">
            <ProfilePicker label="First profile" value={left} onChange={setLeft} />
            <ProfilePicker label="Second profile" value={right} onChange={setRight} />
          </div>
          {selectionError ? (
            <p role="alert" className="text-xs font-semibold text-bad-ink">
              {selectionError}
            </p>
          ) : null}
          <Button type="submit" variant="primary" busy={busy}>
            Show both profiles
          </Button>
        </form>
      </Panel>

      {failure ? (
        <div className="mt-4 max-w-3xl">
          <ErrorState error={failure} />
        </div>
      ) : null}
      {notice ? (
        <div className="mt-4 max-w-3xl">
          <Notice>{notice}</Notice>
        </div>
      ) : null}

      {preview ? (
        <section className="mt-6 space-y-4" aria-label="Preview">
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-2">
            {preview.profiles.map((profile) => (
              <Panel key={profile.id} as="article">
                <PanelRow>
                  <p className="mb-1">
                    {profile.id === preview.survivor_id ? <Tag tone="ok">Kept</Tag> : <Tag tone="warn">Joined into the kept profile</Tag>}
                  </p>
                  <h2 className="break-words text-lg font-bold">{profile.display_name ?? "Unnamed candidate"}</h2>
                  <p className="text-mut">
                    {plural(profile.document_count, "document")} · {plural(profile.application_count, "application")}
                  </p>
                </PanelRow>
                <PanelRow>
                  <p className="mb-1 text-xs font-bold uppercase tracking-wider text-mut">Contact</p>
                  {profile.contacts.length === 0 ? (
                    <p className="text-mut">None stored.</p>
                  ) : (
                    <ul>
                      {profile.contacts.map((c) => (
                        <li key={`${c.kind}-${c.value}`}>
                          <span className="text-mut">{c.kind}: </span>
                          <span className="break-all font-mono text-[13px]">{c.value}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </PanelRow>
                <PanelRow>
                  <p className="mb-1 text-xs font-bold uppercase tracking-wider text-mut">Experience</p>
                  {profile.experiences.length === 0 ? (
                    <p className="text-mut">
                      <Tag tone="unknown">Not extracted</Tag>
                    </p>
                  ) : (
                    <ul>
                      {profile.experiences.map((e) => (
                        <li key={`${e.employer}-${e.title}`}>
                          {e.title ? `${e.title}, ` : ""}
                          {e.employer}
                        </li>
                      ))}
                    </ul>
                  )}
                  {profile.skills.length > 0 ? <p className="mt-2 text-mut">{profile.skills.join(", ")}</p> : null}
                </PanelRow>
              </Panel>
            ))}
          </div>
          {alreadyMerged ? (
            <Notice tone="warn">These profiles are already joined.</Notice>
          ) : (
            <Button variant="danger" busy={busy} onClick={() => setConfirming(true)}>
              Merge these profiles…
            </Button>
          )}
        </section>
      ) : null}

      <ConfirmDialog
        open={confirming}
        title="Merge these profiles?"
        body={
          <p>
            <strong>{absorbed?.display_name ?? "The second profile"}</strong> will be joined into{" "}
            <strong>{survivor?.display_name ?? "the older profile"}</strong>. Documents and applications stay on record. This is recorded in
            the audit trail and cannot be undone here.
          </p>
        }
        confirmLabel="Merge profiles"
        tone="danger"
        busy={busy}
        onConfirm={onConfirm}
        onCancel={() => setConfirming(false)}
      />
    </>
  );
}

/** Find a profile by name, or paste an id. Ids are never shown as the primary label. */
function ProfilePicker({ label, value, onChange }: { label: string; value: Picked; onChange: (next: Picked) => void }) {
  const [term, setTerm] = useState("");
  const [options, setOptions] = useState<{ id: string; name: string | null }[]>([]);
  const [searching, setSearching] = useState(false);
  const [problem, setProblem] = useState<unknown>(null);

  useEffect(() => {
    const trimmed = term.trim();
    if (trimmed.length < 2 || UUID.test(trimmed)) {
      setOptions([]);
      return;
    }
    const timer = setTimeout(() => {
      setSearching(true);
      setProblem(null);
      searchCandidates({ name: trimmed })
        .then((payload) => {
          const seen = new Map<string, { id: string; name: string | null }>();
          for (const hit of payload.results) {
            if (hit.candidate_id && !seen.has(hit.candidate_id)) seen.set(hit.candidate_id, { id: hit.candidate_id, name: hit.candidate_name });
          }
          setOptions([...seen.values()].slice(0, 5));
        })
        .catch((reason) => setProblem(reason instanceof ApiError ? reason : new Error("Search failed")))
        .finally(() => setSearching(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [term]);

  function submitId() {
    if (UUID.test(term.trim())) {
      onChange({ id: term.trim(), name: null });
      setTerm("");
    }
  }

  return (
    <div>
      <Field label={label} hint="Type a name to search, or paste a profile id and press Enter.">
        {({ id, describedBy }) => (
          <input
            id={id}
            aria-describedby={describedBy}
            className={inputClass}
            value={term}
            placeholder={value ? "Search to change…" : "Search by name"}
            onChange={(e) => setTerm(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && UUID.test(term.trim())) {
                e.preventDefault();
                submitId();
              }
            }}
          />
        )}
      </Field>
      {value ? (
        <p className="mt-2 flex flex-wrap items-center gap-2">
          <Tag tone="decided">Selected</Tag>
          <span className="break-words font-semibold">{value.name ?? "Profile chosen by id"}</span>
          <button type="button" className="text-xs font-semibold text-human-ink underline" onClick={() => onChange(null)}>
            Clear
          </button>
        </p>
      ) : null}
      <div aria-live="polite" className="mt-1">
        {searching ? <p className="text-xs text-mut">Searching…</p> : null}
        {problem ? <ErrorState error={problem} /> : null}
        {options.length > 0 ? (
          <ul className="mt-1 divide-y divide-rule rounded border border-rule bg-panel">
            {options.map((o) => (
              <li key={o.id}>
                <button
                  type="button"
                  className="block min-h-11 w-full px-3 py-2 text-left hover:bg-human-bg sm:min-h-9"
                  onClick={() => {
                    onChange(o);
                    setTerm("");
                    setOptions([]);
                  }}
                >
                  {o.name ?? "Unnamed candidate"}
                </button>
              </li>
            ))}
          </ul>
        ) : term.trim().length >= 2 && !searching && !UUID.test(term.trim()) && !problem ? (
          <p className="text-xs text-mut">No confirmed profile has that name.</p>
        ) : null}
      </div>
    </div>
  );
}

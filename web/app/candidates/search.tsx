"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { searchCandidates, type SearchHit } from "@/lib/api";
import { FILTERS, groupHits, hasCriteria, parseSearch, toQueryString } from "@/lib/search-state";
import { plural } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Field, inputClass } from "@/components/ui/field";
import { Menu, MenuItem } from "@/components/ui/menu";
import { PageHeader, Panel } from "@/components/ui/panel";
import { PanelSkeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { ResultGroup } from "./result-group";

const EXAMPLES = [
  { label: "Python and PostgreSQL", href: "/candidates?q=python+postgresql" },
  { label: "Chartered accountant, 5+ years", href: "/candidates?certificate=chartered&min_years=5" },
  { label: "Project manager in construction", href: "/candidates?job_title=project+manager&industry=construction" },
];

export function Search() {
  const router = useRouter();
  const params = useSearchParams();
  const applied = useMemo(() => parseSearch(new URLSearchParams(params.toString())), [params]);
  const [draft, setDraft] = useState<Record<string, string>>(applied);
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const runId = useRef(0);
  const announce = useRef<HTMLParagraphElement>(null);

  // Keep the form in step with the URL, then search whenever the URL carries criteria.
  const key = toQueryString(applied);
  useEffect(() => {
    setDraft(applied);
    if (!hasCriteria(applied)) {
      setHits(null);
      setError(null);
      return;
    }
    const id = ++runId.current;
    setBusy(true);
    setError(null);
    searchCandidates(applied)
      .then((payload) => {
        if (id === runId.current) setHits(payload.results);
      })
      .catch((reason) => {
        if (id === runId.current) {
          setHits(null);
          setError(reason);
        }
      })
      .finally(() => {
        if (id === runId.current) setBusy(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  const groups = useMemo(() => (hits ? groupHits(hits) : []), [hits]);
  const activeFilters = FILTERS.filter((f) => f.name in draft);
  const available = FILTERS.filter((f) => !(f.name in draft));
  const highlight = [applied.q ?? "", applied.skill ?? ""].join(" ");

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const qs = toQueryString(draft);
    router.replace(qs ? `/candidates?${qs}` : "/candidates");
  }

  function remove(name: string) {
    const next = { ...draft };
    delete next[name];
    setDraft(next);
    const qs = toQueryString(next);
    router.replace(qs ? `/candidates?${qs}` : "/candidates");
  }

  return (
    <>
      <PageHeader
        hue="candidate"
        title="Candidates"
        sub="Search inside confirmed CVs. Each result shows the candidate, why they matched, and the passage that says so."
      />

      <Panel as="section" className="mb-5 p-4">
        <form onSubmit={submit} role="search" aria-label="Candidate search">
          <Field label="Words in the CV">
            {({ id }) => (
              <input
                id={id}
                className={inputClass}
                value={draft.q ?? ""}
                placeholder="For example: python backend engineer postgresql"
                onChange={(event) => setDraft({ ...draft, q: event.target.value })}
              />
            )}
          </Field>

          {activeFilters.length > 0 ? (
            <div className="mt-3 grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-2">
              {activeFilters.map((f) => (
                <div key={f.name} className="flex items-end gap-2">
                  <div className="min-w-0 flex-1">
                    <Field label={f.label} hint={f.note}>
                      {({ id, describedBy }) => (
                        <input
                          id={id}
                          aria-describedby={describedBy}
                          className={inputClass}
                          inputMode={f.name === "min_years" ? "decimal" : undefined}
                          value={draft[f.name] ?? ""}
                          onChange={(event) => setDraft({ ...draft, [f.name]: event.target.value })}
                        />
                      )}
                    </Field>
                  </div>
                  <Button aria-label={`Remove the ${f.label} filter`} onClick={() => remove(f.name)}>
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            <Button type="submit" variant="primary" busy={busy}>
              Search
            </Button>
            {available.length > 0 ? (
              <Menu label="+ Add filter">
                {available.map((f) => (
                  <MenuItem key={f.name} onSelect={() => setDraft({ ...draft, [f.name]: draft[f.name] ?? " " })}>
                    {f.label}
                  </MenuItem>
                ))}
              </Menu>
            ) : null}
          </div>
          <p className="mt-3 text-xs text-mut">
            Filters combine with AND. Only confirmed profiles are searched. Nationality searches words already written in the CV.
          </p>
        </form>
      </Panel>

      {Object.keys(applied).length > 0 ? (
        <p className="mb-3 flex flex-wrap items-center gap-1.5" aria-label="Active criteria">
          {Object.entries(applied).map(([name, value]) => (
            <Chip key={name} onRemove={() => remove(name)} removeLabel={`Remove ${name === "q" ? "words" : name} criterion`}>
              <span className="text-mut">{name === "q" ? "Words" : (FILTERS.find((f) => f.name === name)?.label ?? name)}:</span> {value}
            </Chip>
          ))}
        </p>
      ) : null}

      <p ref={announce} role="status" aria-live="polite" className="sr-only">
        {busy ? "Searching" : hits ? `${plural(groups.length, "candidate")} found` : ""}
      </p>

      {error ? <ErrorState error={error} onRetry={() => router.refresh()} /> : null}

      {busy ? (
        <div aria-busy="true">
          <PanelSkeleton rows={3} />
        </div>
      ) : null}

      {!busy && !error && !hasCriteria(applied) ? (
        <EmptyState
          title="Search the CVs"
          body="Type words, add a filter, or start from an example."
          action={
            <ul className="flex flex-wrap justify-center gap-2">
              {EXAMPLES.map((e) => (
                <li key={e.href}>
                  <Link href={e.href} prefetch={false} className="inline-flex min-h-11 items-center rounded-[3px] border border-rule-strong bg-panel px-3 text-[13px] font-semibold no-underline hover:bg-inset">
                    {e.label}
                  </Link>
                </li>
              ))}
            </ul>
          }
        />
      ) : null}

      {!busy && !error && hits !== null && hasCriteria(applied) ? (
        groups.length === 0 ? (
          <EmptyState
            title="No matches"
            body="Nothing in the confirmed CVs fits every criterion. Remove the most specific filter and try again."
          />
        ) : (
          <section aria-label="Results">
            <p className="mb-2 text-mut">
              {plural(groups.length, "candidate")} · {plural(hits.length, "passage")} · ordered by relevance (no score shown)
            </p>
            <Panel>
              {groups.map((g) => (
                <ResultGroup key={g.key} group={g} highlight={highlight} />
              ))}
            </Panel>
          </section>
        )
      ) : null}
    </>
  );
}
